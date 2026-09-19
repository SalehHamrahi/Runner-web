from __future__ import annotations

from pathlib import Path

from .analytics import analyze_match
from .database import RunnerDB
from .logger import get_logger
from .match_data import derive_events_and_spatial, parse_rcg, parse_rcl, save_match_data


def ingest_match_data(db: RunnerDB, match_id: int, rcg_file: Path, output_dir: Path,
                      left_team: str | None = None, right_team: str | None = None,
                      grid_x: int = 15, grid_y: int = 9, rcl_file: Path | None = None,
                      run_analytics: bool = True) -> dict:
    logger = get_logger()
    balls, players, raw_events = parse_rcg(rcg_file, match_id, left_team, right_team)
    if not balls:
        raise ValueError(f"No RCG show frames could be parsed from {rcg_file}")
    spatial, events, _goals = derive_events_and_spatial(match_id, balls, players, raw_events, grid_x, grid_y)
    actions = parse_rcl(rcl_file, match_id, {left_team or 'Left': left_team or 'Left', right_team or 'Right': right_team or 'Right'}) if rcl_file and rcl_file.exists() else []
    summary = save_match_data(output_dir, rcg_file, balls, players, spatial, events, rcl_file, actions)
    summary['_actions_rows'] = [a.__dict__ for a in actions]
    db.store_match_data(match_id, summary, [b.__dict__ for b in balls], [p.__dict__ for p in players], spatial, [e.__dict__ for e in events])
    summary.pop('_actions_rows', None)
    if run_analytics:
        analytics_dir = output_dir / "analytics"
        try:
            analytics_summary = analyze_match(db, match_id, analytics_dir)
            summary["analytics"] = analytics_summary
        except Exception as exc:
            summary["analytics_error"] = str(exc)
            logger.exception("analytics analytics failed for match %s: %s", match_id, exc)
    db.set_match_data_status(match_id, "ingested", summary)
    logger.info("match data layer + analytics data processed for match %s: %s", match_id, summary)
    return summary
