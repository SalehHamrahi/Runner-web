from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import RunnerConfig
from core.database import RunnerDB
from core.logger import configure
from core.rules import rules_for
from core.tournament import utc_now
from core.match_ingestion import ingest_match_data


def get_latest_rcg_file() -> Path | None:
    rcg_files = list(ROOT.glob("*.rcg"))
    if not rcg_files:
        return None
    return max(rcg_files, key=lambda path: path.stat().st_mtime)


def parse_match_result(filename: str):
    pattern = r'^(\d{8}\d+)-(.+?)_(\d+)(?:_(\d+))?-vs-(.+?)_(\d+)(?:_(\d+))?\.rcg$'
    match = re.match(pattern, filename)
    if not match:
        return None

    return {
        "team1": match.group(2),
        "team1_score": int(match.group(3)),
        "team1_penalty": int(match.group(4)) if match.group(4) else None,
        "team2": match.group(5),
        "team2_score": int(match.group(6)),
        "team2_penalty": int(match.group(7)) if match.group(7) else None,
    }


def determine_winner(match_data, tournament_type: str, penalties_enabled: bool):
    rules = rules_for(tournament_type, penalties_enabled)
    return rules.resolve_winner(
        match_data["team1"],
        match_data["team1_score"],
        match_data["team2"],
        match_data["team2_score"],
        match_data["team1_penalty"],
        match_data["team2_penalty"],
    )


def append_legacy_result(match_data, winner: str) -> None:
    if match_data["team1_penalty"] is not None and match_data["team2_penalty"] is not None:
        line = (
            f'{match_data["team1"]} {match_data["team1_score"]}({match_data["team1_penalty"]}) '
            f'- ({match_data["team2_penalty"]}){match_data["team2_score"]} {match_data["team2"]} -> {winner}'
        )
    else:
        line = (
            f'{match_data["team1"]} {match_data["team1_score"]} - '
            f'{match_data["team2_score"]} {match_data["team2"]} -> {winner}'
        )

    with (ROOT / "Results.txt").open("a", encoding="utf-8") as result_file:
        result_file.write(line + "\n")


def main() -> int:
    config = RunnerConfig.load(ROOT / "config.conf")
    log_dir = Path(os.environ.get("RUNNER_LOG_DIR", str(ROOT / "logs")))
    logger = configure(log_dir, config.log_level)

    rcg_file = get_latest_rcg_file()
    if rcg_file is None:
        logger.error("No .rcg file found after match")
        print("NONE")
        return 1

    match_data = parse_match_result(rcg_file.name)
    if match_data is None:
        logger.error("Could not parse match result from RCG filename: %s", rcg_file.name)
        print("NONE")
        return 1

    try:
        winner = determine_winner(match_data, config.tournament_type, config.penalty_shoot_outs)
    except Exception as exc:
        logger.exception("Could not determine winner: %s", exc)
        print("NONE")
        return 1

    append_legacy_result(match_data, winner)

    tournament_id = os.environ.get("RUNNER_TOURNAMENT_ID")
    match_id = os.environ.get("RUNNER_MATCH_ID")
    if tournament_id and match_id:
        db = RunnerDB(Path(os.environ.get("RUNNER_DB", str(ROOT / "runner.db"))))
        try:
            exact_rcl = rcg_file.with_suffix('.rcl')
            if exact_rcl.exists():
                rcl_file = exact_rcl
            else:
                rcl_candidates = list(ROOT.glob("*.rcl"))
                rcl_file = max(rcl_candidates, key=lambda path: path.stat().st_mtime) if rcl_candidates else None
            db.finish_match(
                int(match_id),
                match_data["team1_score"],
                match_data["team2_score"],
                winner,
                utc_now(),
                match_data["team1_penalty"],
                match_data["team2_penalty"],
                str(rcg_file.relative_to(ROOT)),
                str(rcl_file.relative_to(ROOT)) if rcl_file else None,
            )
            if config.data_collection:
                tournament_dir = Path(os.environ.get("RUNNER_TOURNAMENT_DIR", str(ROOT / "tournaments" / tournament_id)))
                output_dir = tournament_dir / "matches" / f"match_{int(match_id)}_data"
                try:
                    ingest_match_data(db, int(match_id), rcg_file, output_dir, match_data["team1"], match_data["team2"], config.spatial_grid_x, config.spatial_grid_y, rcl_file, config.analytics_enabled)
                except Exception as exc:
                    db.set_match_data_status(int(match_id), "failed", {"error": str(exc)})
                    logger.exception("Match data processing failed for match %s: %s", match_id, exc)
        finally:
            db.close()

    logger.info(
        "Match result: %s %s-%s %s -> %s",
        match_data["team1"],
        match_data["team1_score"],
        match_data["team2_score"],
        match_data["team2"],
        winner,
    )
    print(winner)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
