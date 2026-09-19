from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def get_teams(file_path: Path, bins_dir: Path) -> list[str]:
    teams: list[str] = []
    for raw in file_path.read_text(encoding="utf-8").splitlines():
        team = raw.strip()
        if not team or team.startswith("#"):
            continue
        if not (bins_dir / team).is_dir():
            print(f"\033[33mBinary not found for\033[0m {team}. [\033[33mWarning\033[0m]")
        teams.append(team)
    return teams


def generate_round_robin(teams: list[str], output: Path) -> None:
    lines: list[str] = []
    for offset in range(1, len(teams)):
        for index in range(len(teams) - offset):
            lines.extend((teams[index], teams[index + offset], "---"))
    output.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")


if __name__ == "__main__":
    teams_file = ROOT / "teams.txt"
    bins_dir = ROOT / "Bins"
    games_file = ROOT / "Games.txt"
    teams = get_teams(teams_file, bins_dir)
    if not teams:
        print("\033[31mteams.txt is empty [ERROR]\033[0m")
        raise SystemExit(1)
    generate_round_robin(teams, games_file)
    print(f"Generated {len(teams) * (len(teams) - 1) // 2} matches in {games_file.name}")
