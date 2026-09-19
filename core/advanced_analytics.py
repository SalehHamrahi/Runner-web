from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from typing import Any

from .database import RunnerDB


VERSION = 1


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pct(value: float) -> float:
    return round(value * 100.0, 2)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _build_pass_links(conn, match_id: int, team1: str, team2: str):
    teams = (team1, team2)
    player_at_cycle: dict[tuple[int, str, int], tuple[float, float]] = {}
    for row in conn.execute(
        "SELECT cycle, team, unum, x, y FROM match_player_frames WHERE match_id=?",
        (match_id,),
    ):
        player_at_cycle[(int(row["cycle"]), row["team"], int(row["unum"]))] = (
            _safe_float(row["x"]), _safe_float(row["y"])
        )

    passes: list[dict[str, Any]] = []
    rows = []
    for row in conn.execute(
        """SELECT cycle, team, unum, x, y, confidence, details_json
           FROM match_data_events
           WHERE match_id=? AND event_type='pass' ORDER BY cycle""",
        (match_id,),
    ):
        details = {}
        try:
            details = json.loads(row["details_json"]) if row["details_json"] else {}
        except json.JSONDecodeError:
            pass
        receiver_team = details.get("receiver_team")
        receiver_unum = details.get("receiver_unum")
        if receiver_team not in teams or receiver_unum is None:
            continue
        src = player_at_cycle.get((int(row["cycle"]), row["team"], int(row["unum"])))
        dst = player_at_cycle.get((int(row["cycle"]), receiver_team, int(receiver_unum)))
        if src is None:
            src = (_safe_float(row["x"]), _safe_float(row["y"]))
        if dst is None:
            dst = src
        direction = 1.0 if row["team"] == team1 else -1.0
        forward_delta = (dst[0] - src[0]) * direction
        distance = math.hypot(dst[0] - src[0], dst[1] - src[1])
        progressive = forward_delta >= 3.0
        final_third_entry = ((dst[0] * direction) >= 17.5)
        item = {
            "cycle": int(row["cycle"]),
            "team": row["team"],
            "unum": int(row["unum"]),
            "receiver_team": receiver_team,
            "receiver_unum": int(receiver_unum),
            "distance": round(distance, 3),
            "forward_delta": round(forward_delta, 3),
            "progressive": progressive,
            "final_third_entry": final_third_entry,
            "confidence": row["confidence"],
        }
        passes.append(item)
        rows.append(item)
    return passes


def _team_style(team: str, row: dict[str, Any], cycles: int) -> dict[str, Any]:
    possession = _safe_float(row.get("possession_pct"))
    territory = _safe_float(row.get("avg_territory")) * 100.0
    space = _safe_float(row.get("avg_space_control")) * 100.0
    pressure = _safe_float(row.get("avg_ball_pressure"))
    passes = _safe_float(row.get("passes_completed"))
    shots = _safe_float(row.get("shots"))
    progressive = _safe_float(row.get("progressive_passes"))
    final_entries = _safe_float(row.get("final_third_entries"))
    pass_rate = passes / max(1.0, cycles) * 1000.0
    style_scores = {
        "possession": 0.50 * possession + 0.20 * territory + 0.15 * space + 0.15 * min(100.0, pass_rate),
        "direct": 0.45 * min(100.0, shots * 5.0) + 0.35 * min(100.0, progressive * 8.0) + 0.20 * max(0.0, 60.0 - possession),
        "high_press": 0.65 * min(100.0, pressure * 30.0) + 0.20 * territory + 0.15 * min(100.0, final_entries * 8.0),
        "counter_attack": 0.55 * min(100.0, final_entries * 8.0) + 0.25 * min(100.0, shots * 4.0) + 0.20 * max(0.0, 55.0 - possession),
    }
    ranked = sorted(style_scores.items(), key=lambda item: item[1], reverse=True)
    labels = {
        "possession": "Possession / Build-up",
        "direct": "Direct Play",
        "high_press": "High Press",
        "counter_attack": "Counter Attack",
    }
    return {
        "team": team,
        "primary_style": labels[ranked[0][0]],
        "scores": {labels[k]: round(v, 2) for k, v in ranked},
        "profile": {
            "possession": round(possession, 2),
            "territory": round(territory, 2),
            "space": round(space, 2),
            "pressure": round(pressure, 4),
            "passes_per_1000_cycles": round(pass_rate, 2),
        },
    }


def analyze_advanced(db: RunnerDB, match_id: int) -> dict[str, Any]:
    match = db.get_match(match_id)
    if not match:
        raise ValueError(f"Match {match_id} not found")

    team1, team2 = match["team1"], match["team2"]
    teams = [team1, team2]
    with db.conn as conn:
        team_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM match_team_statistics WHERE match_id=? ORDER BY team", (match_id,)
        )]
        player_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM match_player_statistics WHERE match_id=? ORDER BY team, unum", (match_id,)
        )]
        spatial = [dict(r) for r in conn.execute(
            "SELECT * FROM match_spatial_frames WHERE match_id=? ORDER BY cycle", (match_id,)
        )]
        events = []
        for r in conn.execute(
            "SELECT cycle, event_type, team, unum, x, y, confidence, details_json FROM match_data_events WHERE match_id=? ORDER BY cycle, id",
            (match_id,),
        ):
            d = dict(r)
            try:
                d["details"] = json.loads(d.pop("details_json")) if d.get("details_json") else {}
            except json.JSONDecodeError:
                d["details"] = {}
            events.append(d)
        passes = _build_pass_links(conn, match_id, team1, team2)

        goals = [e for e in events if e["event_type"] == "goal"]
        shots = [e for e in events if e["event_type"] in {"shot", "goal"}]
        cycles = len(spatial)
        team_map = {r["team"]: r for r in team_rows}

        # Advanced passing/territory metrics.
        for team in teams:
            row = team_map.get(team)
            if not row:
                continue
            team_passes = [p for p in passes if p["team"] == team]
            row["progressive_passes"] = sum(1 for p in team_passes if p["progressive"])
            row["final_third_entries"] = sum(1 for p in team_passes if p["final_third_entry"])
            row["avg_pass_distance"] = round(_mean([p["distance"] for p in team_passes]), 3)
            row["forward_pass_share"] = round(
                100.0 * row["progressive_passes"] / len(team_passes), 2
            ) if team_passes else 0.0
            row["shot_rate_per_1000_cycles"] = round(
                1000.0 * sum(1 for s in shots if s["team"] == team) / max(1, cycles), 3
            )
            row["goal_rate_per_1000_cycles"] = round(
                1000.0 * sum(1 for g in goals if g["team"] == team) / max(1, cycles), 3
            )

        # Momentum in fixed windows. Score is 0..100 and is comparative, not a match rating.
        window = 120
        momentum: list[dict[str, Any]] = []
        for start in range(0, cycles, window):
            end = min(cycles - 1, start + window - 1)
            subset = [s for s in spatial if start <= int(s["cycle"]) <= end]
            if not subset:
                continue
            goals_w = Counter(g["team"] for g in goals if start <= int(g["cycle"]) <= end)
            shots_w = Counter(s["team"] for s in shots if start <= int(s["cycle"]) <= end)
            poss = {}
            for team in teams:
                own = sum(1 for s in subset if s["possession_team"] == team)
                terr_key = "left_territory" if team == team1 else "right_territory"
                space_key = "left_space_control" if team == team1 else "right_space_control"
                press_key = "left_ball_pressure" if team == team1 else "right_ball_pressure"
                terr = _mean([_safe_float(s[terr_key]) for s in subset])
                space = _mean([_safe_float(s[space_key]) for s in subset])
                press = _mean([_safe_float(s[press_key]) for s in subset])
                poss_share = own / max(1, len(subset))
                poss[team] = {
                    "possession": poss_share,
                    "territory": terr,
                    "space": space,
                    "pressure": press,
                }
            shot_total = sum(shots_w.values()) or 1
            goal_total = sum(goals_w.values()) or 1
            for team in teams:
                score = (
                    0.35 * poss[team]["possession"] * 100.0
                    + 0.25 * poss[team]["territory"] * 100.0
                    + 0.20 * poss[team]["space"] * 100.0
                    + 0.15 * (shots_w[team] / shot_total) * 100.0
                    + 0.05 * (goals_w[team] / goal_total) * 100.0
                )
                momentum.append({"cycle_start": start, "cycle_end": end, "team": team, "score": round(_clamp(score), 2)})

        # Team style and tactical comparison.
        styles = [_team_style(team, team_map.get(team, {}), cycles) for team in teams]
        comparison_metrics = [
            ("possession_pct", "Possession", "pct"),
            ("passes_completed", "Passes", "count"),
            ("progressive_passes", "Progressive passes", "count"),
            ("final_third_entries", "Final-third entries", "count"),
            ("shots", "Shots", "count"),
            ("avg_territory", "Territory", "pct_fraction"),
            ("avg_space_control", "Space control", "pct_fraction"),
            ("avg_ball_pressure", "Ball pressure", "raw"),
            ("avg_pass_distance", "Average pass distance", "raw"),
        ]
        comparison = []
        a = team_map.get(team1, {})
        b = team_map.get(team2, {})
        for key, label, kind in comparison_metrics:
            av, bv = _safe_float(a.get(key)), _safe_float(b.get(key))
            if kind == "pct_fraction":
                av, bv = av * 100.0, bv * 100.0
            comparison.append({
                "metric": key,
                "label": label,
                "team1": round(av, 3),
                "team2": round(bv, 3),
                "difference": round(av - bv, 3),
                "leader": team1 if av > bv else team2 if bv > av else None,
            })

        # Player ratings: analytical heuristic, explicitly not a simulator rating.
        player_ratings = []
        for p in player_rows:
            score = 5.0
            score += min(2.5, _safe_float(p["passes_completed"]) * 0.12)
            score += min(2.0, _safe_float(p["goals"]) * 1.5)
            score += min(1.0, _safe_float(p["shots"]) * 0.15)
            score += min(0.8, _safe_float(p["touch_cycles"]) / 40.0)
            score += min(0.7, _safe_float(p["movement_distance"]) / 1000.0)
            score -= min(1.5, _safe_float(p["avg_pressure_when_possessed"]) * 0.25)
            player_ratings.append({
                "team": p["team"], "unum": p["unum"], "rating": round(_clamp(score, 0, 10), 2),
                "basis": "analytical heuristic; not an official simulator rating",
            })
        player_ratings.sort(key=lambda x: (-x["rating"], x["team"], x["unum"]))

        # Transition and counter-attack indicators.
        transitions = []
        prev = None
        for s in spatial:
            cur = s.get("possession_team")
            cycle = int(s["cycle"])
            if cur in teams and prev and cur != prev["team"]:
                transitions.append({"cycle": cycle, "from": prev["team"], "to": cur, "type": "possession_change"})
            if cur in teams:
                prev = {"team": cur, "cycle": cycle}
        counter_attacks = 0
        for t in transitions:
            start = t["cycle"]
            end = start + 60
            if any(e["team"] == t["to"] and e["event_type"] in {"shot", "goal"} and start <= int(e["cycle"]) <= end for e in shots):
                counter_attacks += 1
        transition_summary = {
            "possession_changes": len(transitions),
            "quick_shot_transitions": counter_attacks,
            "transitions_per_1000_cycles": round(1000.0 * len(transitions) / max(1, cycles), 3),
        }

        # Recent form from completed tournament matches.
        recent_form = {}
        tournament_id = match["tournament_id"]
        match_rows = list(conn.execute(
            """SELECT id, team1, team2, score1, score2, winner, status
               FROM matches WHERE tournament_id=? AND status='completed' ORDER BY COALESCE(finished_at, started_at), id""",
            (tournament_id,),
        ))
        for team in teams:
            form = []
            for m in reversed(match_rows):
                if team not in (m["team1"], m["team2"]):
                    continue
                opponent = m["team2"] if team == m["team1"] else m["team1"]
                result = "D"
                if m["winner"] == team:
                    result = "W"
                elif m["winner"] and m["winner"] != team and m["winner"] in (m["team1"], m["team2"]):
                    result = "L"
                elif m["score1"] is not None and m["score2"] is not None:
                    a_score = int(m["score1"] if team == m["team1"] else m["score2"])
                    b_score = int(m["score2"] if team == m["team1"] else m["score1"])
                    result = "W" if a_score > b_score else "L" if a_score < b_score else "D"
                form.append({"match_id": int(m["id"]), "opponent": opponent, "result": result})
                if len(form) >= 5:
                    break
            recent_form[team] = {"results": list(reversed(form)), "string": " ".join(x["result"] for x in reversed(form))}

        data = {
            "version": VERSION,
            "match_id": match_id,
            "teams": teams,
            "team_styles": styles,
            "comparison": comparison,
            "momentum": momentum,
            "player_ratings": player_ratings,
            "transitions": transition_summary,
            "recent_form": recent_form,
            "passing": {
                "progressive_passes": {team: team_map.get(team, {}).get("progressive_passes", 0) for team in teams},
                "final_third_entries": {team: team_map.get(team, {}).get("final_third_entries", 0) for team in teams},
                "average_pass_distance": {team: team_map.get(team, {}).get("avg_pass_distance", 0.0) for team in teams},
            },
            "records": {
                "top_player": player_ratings[0] if player_ratings else None,
                "most_shots_team": max(teams, key=lambda t: _safe_float(team_map.get(t, {}).get("shots"))) if teams else None,
                "most_possession_team": max(teams, key=lambda t: _safe_float(team_map.get(t, {}).get("possession_pct"))) if teams else None,
            },
        }

    db.store_advanced_analytics(match_id, data, VERSION)
    return data
