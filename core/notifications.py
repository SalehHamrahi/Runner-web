from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request

from core.config import RunnerConfig
from core.database import RunnerDB


@dataclass(frozen=True)
class DiscordNotificationConfig:
    enabled: bool
    webhook_url: str
    notify_match_finished: bool
    notify_tournament_finished: bool
    notify_team_crash: bool
    notify_server_crash: bool
    username: str = "Runner"


EVENT_PERMISSION = {
    "match_finished": "notify_match_finished",
    "tournament_finished": "notify_tournament_finished",
    "team_crash": "notify_team_crash",
    "server_crash": "notify_server_crash",
}


def _get_bool(values: dict[str, str], name: str, default: bool = False) -> bool:
    raw = values.get(name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def load_notification_config(config_path: Path) -> DiscordNotificationConfig:
    values: dict[str, str] = {}
    if config_path.exists():
        for raw in config_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()

    webhook_url = os.environ.get("RUNNER_DISCORD_WEBHOOK_URL", values.get("discord_webhook_url", "")).strip()
    return DiscordNotificationConfig(
        enabled=_get_bool(values, "discord_enabled", False),
        webhook_url=webhook_url,
        notify_match_finished=_get_bool(values, "notify_match_finished", True),
        notify_tournament_finished=_get_bool(values, "notify_tournament_finished", True),
        notify_team_crash=_get_bool(values, "notify_team_crash", True),
        notify_server_crash=_get_bool(values, "notify_server_crash", True),
        username=values.get("discord_username", "Runner") or "Runner",
    )


def permission_enabled(config: DiscordNotificationConfig, event_type: str) -> bool:
    permission = EVENT_PERMISSION.get(event_type)
    return bool(config.enabled and config.webhook_url and permission and getattr(config, permission, False))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _discord_payload(event_type: str, title: str, description: str, fields: list[tuple[str, str]] | None, username: str) -> dict[str, Any]:
    color_map = {
        "match_finished": 0x22D3EE,
        "tournament_finished": 0xA78BFA,
        "team_crash": 0xF59E0B,
        "server_crash": 0xEF4444,
    }
    embed: dict[str, Any] = {
        "title": title,
        "description": description,
        "color": color_map.get(event_type, 0x64748B),
        "timestamp": _utc_now(),
        "footer": {"text": "Runner Tournament Platform"},
    }
    if fields:
        embed["fields"] = [
            {"name": name, "value": str(value), "inline": True}
            for name, value in fields[:25]
        ]
    return {"username": username, "embeds": [embed]}


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(value)}"
    except (TypeError, ValueError):
        return "—"


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "—"


def _standings(conn, tournament_id: str) -> list[dict[str, Any]]:
    team_rows = conn.execute(
        "SELECT name FROM teams WHERE tournament_id=? ORDER BY name", (tournament_id,)
    ).fetchall()
    matches = [dict(r) for r in conn.execute(
        "SELECT team1, team2, score1, score2, winner, status FROM matches WHERE tournament_id=? ORDER BY COALESCE(match_number,id)",
        (tournament_id,),
    )]
    table = {
        row["name"]: {"team": row["name"], "played": 0, "wins": 0, "draws": 0,
                       "losses": 0, "gf": 0, "ga": 0, "gd": 0, "points": 0}
        for row in team_rows
    }
    for match in matches:
        if match.get("status") != "completed" or match.get("score1") is None or match.get("score2") is None:
            continue
        a, b = match["team1"], match["team2"]
        sa, sb = int(match["score1"]), int(match["score2"])
        for team, gf, ga in ((a, sa, sb), (b, sb, sa)):
            table.setdefault(team, {"team": team, "played": 0, "wins": 0, "draws": 0,
                                     "losses": 0, "gf": 0, "ga": 0, "gd": 0, "points": 0})
            table[team]["played"] += 1
            table[team]["gf"] += gf
            table[team]["ga"] += ga
        winner = match.get("winner")
        if winner == a or (not winner and sa > sb):
            table[a]["wins"] += 1
            table[a]["points"] += 3
            table[b]["losses"] += 1
        elif winner == b or (not winner and sb > sa):
            table[b]["wins"] += 1
            table[b]["points"] += 3
            table[a]["losses"] += 1
        else:
            table[a]["draws"] += 1
            table[b]["draws"] += 1
            table[a]["points"] += 1
            table[b]["points"] += 1
    for row in table.values():
        row["gd"] = row["gf"] - row["ga"]
    return sorted(table.values(), key=lambda x: (-x["points"], -x["gd"], -x["gf"], x["team"]))


def _match_notification_payload(db_path: Path, match_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    db = RunnerDB(db_path)
    try:
        match = db.conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
        if not match:
            return payload

        match = dict(match)
        team1, team2 = match["team1"], match["team2"]
        score1, score2 = match["score1"], match["score2"]
        winner = match.get("winner") or "Draw"
        score = f"{team1} **{score1 if score1 is not None else '—'} - {score2 if score2 is not None else '—'}** {team2}"
        if match.get("penalty1") is not None and match.get("penalty2") is not None:
            score += f"\n🥅 Penalties: **{match['penalty1']} - {match['penalty2']}**"

        fields: list[tuple[str, str]] = [
            ("🏆 Winner", winner),
            ("🆔 Match", f"#{match.get('match_number') or match_id}"),
        ]

        stats = [dict(r) for r in db.conn.execute(
            "SELECT * FROM match_team_statistics WHERE match_id=? ORDER BY team", (match_id,)
        )]
        by_team = {row["team"]: row for row in stats}
        if team1 in by_team and team2 in by_team:
            a, b = by_team[team1], by_team[team2]
            fields.extend([
                ("⚽ Goals", f"{_fmt_int(a.get('goals'))} - {_fmt_int(b.get('goals'))}"),
                ("🎯 Shots", f"{_fmt_int(a.get('shots'))} - {_fmt_int(b.get('shots'))}"),
                ("🔄 Passes", f"{_fmt_int(a.get('passes_completed'))} - {_fmt_int(b.get('passes_completed'))}"),
                ("📊 Possession", f"{_fmt_pct(a.get('possession_pct'))} - {_fmt_pct(b.get('possession_pct'))}"),
                ("✅ Pass Accuracy", f"{_fmt_pct(a.get('pass_accuracy_pct'))} - {_fmt_pct(b.get('pass_accuracy_pct'))}"),
            ])

        enriched = dict(payload)
        enriched["title"] = f"⚽ Match Finished — {winner}"
        enriched["description"] = score
        enriched["fields"] = fields
        return enriched
    finally:
        db.close()


def _tournament_notification_payload(db_path: Path, tournament_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    db = RunnerDB(db_path)
    try:
        tournament = db.conn.execute("SELECT * FROM tournaments WHERE id=?", (tournament_id,)).fetchone()
        if not tournament:
            return payload

        matches = [dict(r) for r in db.conn.execute(
            "SELECT * FROM matches WHERE tournament_id=? ORDER BY COALESCE(match_number,id)", (tournament_id,)
        )]
        completed = [m for m in matches if m.get("status") == "completed"]
        total_goals = sum(int(m.get("score1") or 0) + int(m.get("score2") or 0) for m in completed)
        standings = _standings(db.conn, tournament_id)

        description = f"Tournament `{tournament_id}` completed successfully."
        fields: list[tuple[str, str]] = [
            ("🎮 Matches", f"{len(completed)} / {len(matches)} completed"),
            ("⚽ Goals", str(total_goals)),
        ]

        tournament_type = tournament["type"]
        if tournament_type == "round_robin" and standings:
            lines = []
            for index, row in enumerate(standings[:6], 1):
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(index, f"{index}.")
                lines.append(
                    f"{medal} **{row['team']}** — {row['points']} pts "
                    f"({row['played']}P {row['wins']}W {row['draws']}D {row['losses']}L, GD {row['gd']})"
                )
            standings_text = "\n".join(lines)
            fields.append(("📊 Final Standings", standings_text[:1024]))
        elif completed:
            final = completed[-1]
            winner = final.get("winner") or "Draw"
            fields.append(("🏆 Final Match", f"{final['team1']} {final.get('score1','—')} - {final.get('score2','—')} {final['team2']}"))
            fields.append(("👑 Final Winner", winner))

        enriched = dict(payload)
        enriched["title"] = "🏆 Tournament Finished"
        enriched["description"] = description
        enriched["fields"] = fields
        return enriched
    finally:
        db.close()


def send_discord(config_path: Path, db_path: Path, event_type: str, tournament_id: str | None = None,
                 match_id: int | None = None, payload: dict[str, Any] | None = None) -> bool:
    config = load_notification_config(config_path)
    payload = dict(payload or {})
    if not permission_enabled(config, event_type):
        return False

    if event_type == "match_finished" and match_id is not None:
        payload = _match_notification_payload(db_path, match_id, payload)
    elif event_type == "tournament_finished" and tournament_id:
        payload = _tournament_notification_payload(db_path, tournament_id, payload)

    db = RunnerDB(db_path)
    history_id: int | None = None
    try:
        with db.conn:
            cur = db.conn.execute(
                """INSERT INTO notification_history
                   (tournament_id, match_id, event_type, channel, status, message, payload_json, created_at)
                   VALUES (?, ?, ?, 'discord', 'pending', ?, ?, ?)""",
                (
                    tournament_id,
                    match_id,
                    event_type,
                    payload.get("title", event_type),
                    json.dumps(payload, ensure_ascii=False),
                    _utc_now(),
                ),
            )
            history_id = int(cur.lastrowid)

        body = _discord_payload(
            event_type,
            payload.get("title", "Runner Notification"),
            payload.get("description", ""),
            payload.get("fields"),
            config.username,
        )
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            config.webhook_url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "Runner/1.0"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=4) as response:
                response.read(1)
        except Exception as exc:
            if history_id is not None:
                with db.conn:
                    db.conn.execute(
                        "UPDATE notification_history SET status='failed', error=?, sent_at=? WHERE id=?",
                        (str(exc), _utc_now(), history_id),
                    )
            return False

        if history_id is not None:
            with db.conn:
                db.conn.execute(
                    "UPDATE notification_history SET status='sent', sent_at=? WHERE id=?",
                    (_utc_now(), history_id),
                )
        return True
    finally:
        db.close()


def dispatch_async(config_path: Path, db_path: Path, event_type: str,
                   tournament_id: str | None = None, match_id: int | None = None,
                   payload: dict[str, Any] | None = None) -> None:
    config = load_notification_config(config_path)
    if not permission_enabled(config, event_type):
        return

    message = json.dumps({
        "config": str(config_path),
        "db": str(db_path),
        "event_type": event_type,
        "tournament_id": tournament_id,
        "match_id": match_id,
        "payload": payload or {},
    }, ensure_ascii=False)
    subprocess.Popen(
        [sys.executable, "-m", "core.notifications", "_send", message],
        cwd=str(config_path.parent),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def list_history(db: RunnerDB, limit: int = 100) -> list[dict[str, Any]]:
    rows = db.conn.execute(
        """SELECT id, tournament_id, match_id, event_type, channel, status,
                  message, error, created_at, sent_at
           FROM notification_history
           ORDER BY id DESC LIMIT ?""",
        (max(1, min(limit, 500)),),
    ).fetchall()
    return [dict(row) for row in rows]


def _cli_send(serialized: str) -> int:
    spec = json.loads(serialized)
    send_discord(
        Path(spec["config"]),
        Path(spec["db"]),
        spec["event_type"],
        spec.get("tournament_id"),
        spec.get("match_id"),
        spec.get("payload"),
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "_send":
        raise SystemExit(_cli_send(sys.argv[2]))
    raise SystemExit(2)
