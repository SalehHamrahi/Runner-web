from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class TeamValidation:
    name: str
    directory: Path
    start_script: Path | None
    local_start: Path | None
    valid: bool
    message: str


def _extract_teamname(start_script: Path) -> str | None:
    for line in start_script.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"^\s*teamname\s*=\s*['\"]([^'\"]+)['\"]\s*$", line)
        if match:
            return match.group(1).strip()
    return None


def validate_team(root: Path, team: str) -> TeamValidation:
    directory = root / "Bins" / team
    if not directory.is_dir():
        return TeamValidation(team, directory, None, None, False, "team directory not found")

    start_script = None
    for candidate in (directory / "start", directory / "start.sh"):
        if candidate.is_file():
            start_script = candidate
            break
    if start_script is None:
        return TeamValidation(team, directory, None, None, False, "start or start.sh not found")

    local_start = directory / "localStartAll"
    if not local_start.is_file():
        return TeamValidation(team, directory, start_script, None, False, "localStartAll not found")
    if not local_start.stat().st_mode & 0o111:
        return TeamValidation(team, directory, start_script, local_start, False, "localStartAll is not executable")

    teamname = _extract_teamname(start_script)
    if teamname and teamname != team:
        return TeamValidation(
            team,
            directory,
            start_script,
            local_start,
            False,
            f"directory name '{team}' does not match teamname '{teamname}'",
        )

    return TeamValidation(team, directory, start_script, local_start, True, "ok")


def validate_teams(root: Path, teams: list[str]) -> list[TeamValidation]:
    return [validate_team(root, team) for team in teams]
