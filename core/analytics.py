from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from .database import RunnerDB
from .advanced_analytics import analyze_advanced


class AnalyticsError(RuntimeError):
    pass


def _json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def _consecutive_segments(values: list[tuple[int, str | None]]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    current_team = None
    start_cycle = None
    last_cycle = None
    for cycle, team in values:
        if team == current_team:
            last_cycle = cycle
            continue
        if current_team is not None and start_cycle is not None and last_cycle is not None:
            segments.append({
                "team": current_team,
                "start_cycle": start_cycle,
                "end_cycle": last_cycle,
                "cycles": last_cycle - start_cycle + 1,
            })
        current_team = team
        start_cycle = cycle
        last_cycle = cycle
    if current_team is not None and start_cycle is not None and last_cycle is not None:
        segments.append({
            "team": current_team,
            "start_cycle": start_cycle,
            "end_cycle": last_cycle,
            "cycles": last_cycle - start_cycle + 1,
        })
    return segments


def _distance_from_frames(frames: list[dict[str, Any]]) -> float:
    if len(frames) < 2:
        return 0.0
    frames = sorted(frames, key=lambda row: row["cycle"])
    distance = 0.0
    for a, b in zip(frames, frames[1:]):
        if b["cycle"] != a["cycle"]:
            distance += math.hypot(b["x"] - a["x"], b["y"] - a["y"])
    return distance


def _goal_team(match: dict[str, Any], event: dict[str, Any]) -> str | None:
    return event.get("team")


def analyze_match(db: RunnerDB, match_id: int, output_dir: Path | None = None) -> dict[str, Any]:
    match = db.get_match(match_id)
    if match is None:
        raise AnalyticsError(f"Match {match_id} not found")
    if match["data_status"] != "ingested":
        raise AnalyticsError(f"Match {match_id} data is not ingested (status={match['data_status']})")

    team1 = match["team1"]
    team2 = match["team2"]
    teams = [team1, team2]

    balls = [dict(row) for row in db.conn.execute(
        "SELECT * FROM match_ball_frames WHERE match_id=? ORDER BY cycle", (match_id,)
    )]
    players = [dict(row) for row in db.conn.execute(
        "SELECT * FROM match_player_frames WHERE match_id=? ORDER BY cycle, side, unum", (match_id,)
    )]
    spatial = [dict(row) for row in db.conn.execute(
        "SELECT * FROM match_spatial_frames WHERE match_id=? ORDER BY cycle", (match_id,)
    )]
    actions = [dict(row) for row in db.conn.execute(
        "SELECT * FROM match_actions WHERE match_id=? ORDER BY cycle, subcycle, id", (match_id,)
    )]
    events = [dict(row) for row in db.conn.execute(
        "SELECT * FROM match_data_events WHERE match_id=? ORDER BY cycle, id", (match_id,)
    )]

    spatial_by_cycle = {row["cycle"]: row for row in spatial}
    players_by_key: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    players_by_cycle: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in players:
        players_by_key[(row["team"], row["unum"])].append(row)
        players_by_cycle[row["cycle"]].append(row)

    event_rows: list[dict[str, Any]] = []
    for row in events:
        row = dict(row)
        row["details"] = _json(row.pop("details_json", None))
        event_rows.append(row)

    goal_rows = [row for row in event_rows if row["event_type"] == "goal"]
    pass_rows = [row for row in event_rows if row["event_type"] == "pass"]
    shot_rows = [row for row in event_rows if row["event_type"] == "shot"]
    kick_actions = [row for row in actions if row["action_type"] == "kick"]

    # Possession segments and changes.
    possession_values = [(row["cycle"], row["possession_team"]) for row in spatial]
    segments = _consecutive_segments(possession_values)
    possession_cycles = {team: 0 for team in teams}
    possession_sequences: list[str] = []
    for row in spatial:
        team = row["possession_team"]
        if team in possession_cycles:
            possession_cycles[team] += 1
            possession_sequences.append(team)
    possession_total = sum(possession_cycles.values())
    possession_pct = {
        team: (100.0 * possession_cycles[team] / possession_total if possession_total else 0.0)
        for team in teams
    }
    possession_changes = 0
    previous = None
    for team in possession_sequences:
        if previous is not None and team != previous:
            possession_changes += 1
        previous = team

    # Player/event helpers.
    pass_by_team = {team: 0 for team in teams}
    passes_received = {team: 0 for team in teams}
    shots_by_team = {team: 0 for team in teams}
    goals_by_team = {team: 0 for team in teams}
    interceptions_by_team = {team: 0 for team in teams}
    turnovers_by_team = {team: 0 for team in teams}
    for row in pass_rows:
        if row["team"] in pass_by_team:
            pass_by_team[row["team"]] += 1
        receiver_team = row["details"].get("receiver_team")
        if receiver_team in passes_received:
            passes_received[receiver_team] += 1
    for row in shot_rows:
        if row["team"] in shots_by_team:
            shots_by_team[row["team"]] += 1
    for row in goal_rows:
        team = _goal_team(match, row)
        if team in goals_by_team:
            goals_by_team[team] += 1
    for row in event_rows:
        if row["event_type"] == "turnover":
            if row["team"] in turnovers_by_team:
                turnovers_by_team[row["team"]] += 1
        elif row["event_type"] == "interception":
            if row["team"] in interceptions_by_team:
                interceptions_by_team[row["team"]] += 1

    # Action outcome correlation: identify which kick produced a pass/shot/goal.
    event_by_cycle = defaultdict(list)
    for row in event_rows:
        event_by_cycle[row["cycle"]].append(row)
    action_outcomes: list[dict[str, Any]] = []
    for action in kick_actions:
        candidates = []
        for cycle in range(action["cycle"], action["cycle"] + 4):
            candidates.extend(event_by_cycle.get(cycle, []))
        outcome = "unresolved"
        outcome_event = None
        for candidate in candidates:
            if candidate["team"] != action["team"]:
                continue
            if candidate["event_type"] in {"pass", "shot", "goal"}:
                outcome = candidate["event_type"]
                outcome_event = candidate
                break
        action_outcomes.append({
            "cycle": action["cycle"],
            "team": action["team"],
            "unum": action["unum"],
            "action_type": action["action_type"],
            "outcome": outcome,
            "outcome_cycle": outcome_event["cycle"] if outcome_event else None,
        })

    # Team-level spatial metrics.
    team_rows: list[dict[str, Any]] = []
    for team in teams:
        side = "l" if team == team1 else "r"
        pressure_key = "left_ball_pressure" if side == "l" else "right_ball_pressure"
        territory_key = "left_territory" if side == "l" else "right_territory"
        space_key = "left_space_control" if side == "l" else "right_space_control"
        pressure_values = [float(row[pressure_key]) for row in spatial]
        territory_values = [float(row[territory_key]) for row in spatial]
        space_values = [float(row[space_key]) for row in spatial]
        avg_pressure = sum(pressure_values) / len(pressure_values) if pressure_values else 0.0
        avg_territory = sum(territory_values) / len(territory_values) if territory_values else 0.0
        avg_space = sum(space_values) / len(space_values) if space_values else 0.0
        kick_count = sum(1 for action in kick_actions if action["team"] == team)
        inferred_passes = pass_by_team[team]
        inferred_shots = shots_by_team[team]
        pass_attempts = max(0, kick_count - inferred_shots)
        pass_accuracy = (100.0 * inferred_passes / pass_attempts) if pass_attempts else None
        team_rows.append({
            "match_id": match_id,
            "team": team,
            "possession_cycles": possession_cycles.get(team, 0),
            "possession_pct": round(possession_pct.get(team, 0.0), 4),
            "possession_segments": sum(1 for segment in segments if segment["team"] == team),
            "passes_completed": inferred_passes,
            "passes_received": passes_received.get(team, 0),
            "kick_actions": kick_count,
            "pass_attempts_estimated": pass_attempts,
            "pass_accuracy_pct": round(pass_accuracy, 4) if pass_accuracy is not None else None,
            "shots": inferred_shots,
            "goals": goals_by_team[team],
            "turnovers": turnovers_by_team[team],
            "interceptions": interceptions_by_team[team],
            "avg_ball_pressure": round(avg_pressure, 6),
            "avg_territory": round(avg_territory, 6),
            "avg_space_control": round(avg_space, 6),
        })

    # Player-level metrics.
    player_rows: list[dict[str, Any]] = []
    for key in sorted(players_by_key):
        team, unum = key
        frames = players_by_key[key]
        touches = sum(1 for row in spatial if row["possession_team"] == team and row["possession_unum"] == unum)
        player_passes = sum(1 for row in pass_rows if row["team"] == team and row["unum"] == unum)
        player_shots = sum(1 for row in shot_rows if row["team"] == team and row["unum"] == unum)
        player_goals = sum(1 for row in goal_rows if row["team"] == team and row["unum"] == unum)
        player_actions = sum(1 for row in actions if row["team"] == team and row["unum"] == unum)
        movement = _distance_from_frames(frames)
        pressure = []
        side = frames[0]["side"] if frames else ("l" if team == team1 else "r")
        pressure_key = "right_ball_pressure" if side == "l" else "left_ball_pressure"
        for row in spatial:
            if row["possession_team"] == team and row["possession_unum"] == unum:
                pressure.append(float(row[pressure_key]))
        player_rows.append({
            "match_id": match_id,
            "team": team,
            "unum": unum,
            "actions": player_actions,
            "touch_cycles": touches,
            "passes_completed": player_passes,
            "shots": player_shots,
            "goals": player_goals,
            "movement_distance": round(movement, 6),
            "avg_pressure_when_possessed": round(sum(pressure) / len(pressure), 6) if pressure else 0.0,
        })

    # State -> Action -> Outcome records for later ML use.
    state_action_rows: list[dict[str, Any]] = []
    for item in action_outcomes:
        cycle = item["cycle"]
        spatial_row = spatial_by_cycle.get(cycle)
        state_action_rows.append({
            "match_id": match_id,
            "cycle": cycle,
            "team": item["team"],
            "unum": item["unum"],
            "action_type": item["action_type"],
            "outcome": item["outcome"],
            "ball_x": spatial_row["ball_x"] if spatial_row else None,
            "ball_y": spatial_row["ball_y"] if spatial_row else None,
            "pressure": (spatial_row["right_ball_pressure"] if item["team"] == team1 else spatial_row["left_ball_pressure"]) if spatial_row else None,
            "space_control": (spatial_row["left_space_control"] if item["team"] == team1 else spatial_row["right_space_control"]) if spatial_row else None,
        })

    summary = {
        "match_id": match_id,
        "teams": teams,
        "score": [match["score1"], match["score2"]],
        "winner": match["winner"],
        "cycles": len(balls),
        "possession": {team: round(possession_pct.get(team, 0.0), 4) for team in teams},
        "possession_changes": possession_changes,
        "possession_segments": len(segments),
        "goals": goals_by_team,
        "passes_completed": pass_by_team,
        "shots": shots_by_team,
        "interceptions": interceptions_by_team,
        "turnovers": turnovers_by_team,
        "actions": len(actions),
        "events": len(events),
        "state_action_outcomes": len(state_action_rows),
        "analytics_version": 2,
    }

    db.store_analytics(match_id, summary, team_rows, player_rows, segments, state_action_rows)

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        _write_csv(output_dir / "team_statistics.csv", team_rows)
        _write_csv(output_dir / "player_statistics.csv", player_rows)
        _write_csv(output_dir / "possession_segments.csv", segments)
        _write_csv(output_dir / "state_action_outcomes.csv", state_action_rows)
        _write_csv(output_dir / "analytics_events.csv", event_rows)
        (output_dir / "analytics.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    advanced = analyze_advanced(db, match_id)
    summary["advanced_version"] = advanced.get("version")
    summary["advanced_records"] = len(advanced.get("player_ratings", []))
    if output_dir is not None:
        (output_dir / "advanced_analytics.json").write_text(
            json.dumps(advanced, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        _write_csv(output_dir / "momentum.csv", advanced.get("momentum", []))
        _write_csv(output_dir / "team_styles.csv", [
            {"team": s.get("team"), "primary_style": s.get("primary_style"), **{f"score_{k}": v for k, v in s.get("scores", {}).items()}}
            for s in advanced.get("team_styles", [])
        ])
        _write_csv(output_dir / "player_ratings.csv", advanced.get("player_ratings", []))
        _write_csv(output_dir / "tactical_comparison.csv", advanced.get("comparison", []))
    return summary
