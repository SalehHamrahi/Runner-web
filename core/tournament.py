from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

from .config import RunnerConfig
from .database import RunnerDB
from .logger import get_logger


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_tournament_id(tournament_type: str, root: Path) -> str:
    base = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    prefix = re.sub(r"[^a-zA-Z0-9_-]+", "-", tournament_type).lower()
    candidate = f"{base}-{prefix}"
    index = 1
    while (root / "tournaments" / candidate).exists():
        index += 1
        candidate = f"{base}-{prefix}-{index:02d}"
    return candidate


def create_tournament(root: Path, config: RunnerConfig, team_names: list[str]) -> tuple[str, Path, RunnerDB]:
    tournament_id = make_tournament_id(config.tournament_type, root)
    tournament_dir = root / "tournaments" / tournament_id
    (tournament_dir / "logs").mkdir(parents=True, exist_ok=True)
    (tournament_dir / "matches").mkdir(parents=True, exist_ok=True)
    (tournament_dir / "reports").mkdir(parents=True, exist_ok=True)

    db = RunnerDB(root / "runner.db")
    db.create_tournament(
        tournament_id,
        config.tournament_type,
        {
            "fullstate": config.fullstate,
            "synch_mode": config.synch_mode,
            "extra_halfs": config.extra_halfs,
            "penalty_shoot_outs": config.penalty_shoot_outs,
            "data_collection": config.data_collection,
            "spatial_grid_x": config.spatial_grid_x,
            "spatial_grid_y": config.spatial_grid_y,
            "teams": team_names,
        },
        utc_now(),
    )
    (tournament_dir / "metadata.json").write_text(
        __import__("json").dumps(
            {
                "id": tournament_id,
                "type": config.tournament_type,
                "created_at": utc_now(),
                "teams": team_names,
            },
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )
    get_logger().info("Created tournament %s (%s)", tournament_id, config.tournament_type)
    return tournament_id, tournament_dir, db
