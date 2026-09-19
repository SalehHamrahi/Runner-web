from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunnerConfig:
    fullstate: bool = True
    synch_mode: bool = True
    tournament_type: str = "stepladder"
    extra_halfs: int = 2
    penalty_shoot_outs: bool = False
    log_level: str = "INFO"
    data_collection: bool = True
    analytics_enabled: bool = True
    discord_enabled: bool = False
    discord_webhook_url: str = ""
    notify_match_finished: bool = True
    notify_tournament_finished: bool = True
    notify_team_crash: bool = True
    notify_server_crash: bool = True
    discord_username: str = "Runner"
    plugins_enabled: bool = False
    plugins_dir: str = "plugins"
    spatial_grid_x: int = 15
    spatial_grid_y: int = 9

    @classmethod
    def load(cls, path: Path) -> "RunnerConfig":
        values: dict[str, str] = {}
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()

        tournament_type = values.get("type", "stepladder")
        if tournament_type not in {"round_robin", "stepladder"}:
            raise ValueError(f"Unsupported tournament type: {tournament_type}")

        def as_bool(name: str, default: bool) -> bool:
            value = values.get(name, str(default)).lower()
            if value not in {"true", "false"}:
                raise ValueError(f"{name} must be true or false, got: {value}")
            return value == "true"

        try:
            extra_halfs = int(values.get("nr_extra_halfs", "2"))
            spatial_grid_x = int(values.get("spatial_grid_x", "15"))
            spatial_grid_y = int(values.get("spatial_grid_y", "9"))
        except ValueError as exc:
            raise ValueError("nr_extra_halfs/spatial_grid_x/spatial_grid_y must be integers") from exc
        return cls(
            fullstate=as_bool("fullstate", True),
            synch_mode=as_bool("synch_mode", True),
            tournament_type=tournament_type,
            extra_halfs=extra_halfs,
            penalty_shoot_outs=as_bool("penalty_shoot_outs", False),
            log_level=values.get("log_level", "INFO"),
            data_collection=as_bool("data_collection", True),
            analytics_enabled=as_bool("analytics_enabled", True),
            discord_enabled=as_bool("discord_enabled", False),
            discord_webhook_url=values.get("discord_webhook_url", ""),
            notify_match_finished=as_bool("notify_match_finished", True),
            notify_tournament_finished=as_bool("notify_tournament_finished", True),
            notify_team_crash=as_bool("notify_team_crash", True),
            notify_server_crash=as_bool("notify_server_crash", True),
            discord_username=values.get("discord_username", "Runner") or "Runner",
            plugins_enabled=as_bool("plugins_enabled", False),
            plugins_dir=values.get("plugins_dir", "plugins") or "plugins",
            spatial_grid_x=max(3, spatial_grid_x),
            spatial_grid_y=max(3, spatial_grid_y),
        )
