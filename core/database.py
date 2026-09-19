from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tournaments (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    config_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS teams (
    tournament_id TEXT NOT NULL,
    name TEXT NOT NULL,
    binary_dir TEXT NOT NULL,
    start_script TEXT,
    valid INTEGER NOT NULL,
    validation_message TEXT,
    PRIMARY KEY (tournament_id, name),
    FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id TEXT NOT NULL,
    match_number INTEGER,
    team1 TEXT NOT NULL,
    team2 TEXT NOT NULL,
    score1 INTEGER,
    score2 INTEGER,
    penalty1 INTEGER,
    penalty2 INTEGER,
    winner TEXT,
    status TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    rcg_file TEXT,
    rcl_file TEXT,
    data_status TEXT NOT NULL DEFAULT 'pending',
    data_summary_json TEXT,
    FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id TEXT NOT NULL,
    match_id INTEGER,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    context_json TEXT,
    FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS match_ball_frames (
    match_id INTEGER NOT NULL,
    cycle INTEGER NOT NULL,
    playmode TEXT,
    left_score INTEGER,
    right_score INTEGER,
    x REAL NOT NULL,
    y REAL NOT NULL,
    vx REAL NOT NULL,
    vy REAL NOT NULL,
    PRIMARY KEY (match_id, cycle),
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS match_player_frames (
    match_id INTEGER NOT NULL,
    cycle INTEGER NOT NULL,
    side TEXT NOT NULL,
    team TEXT NOT NULL,
    unum INTEGER NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    vx REAL NOT NULL,
    vy REAL NOT NULL,
    body REAL,
    neck REAL,
    focus_x REAL,
    focus_y REAL,
    stamina REAL,
    effort REAL,
    recovery REAL,
    capacity REAL,
    kick_count INTEGER,
    player_type INTEGER,
    state TEXT,
    counters_json TEXT,
    PRIMARY KEY (match_id, cycle, side, unum),
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS match_spatial_frames (
    match_id INTEGER NOT NULL,
    cycle INTEGER NOT NULL,
    ball_x REAL NOT NULL,
    ball_y REAL NOT NULL,
    region TEXT NOT NULL,
    possession_team TEXT,
    possession_unum INTEGER,
    possession_confidence TEXT,
    left_ball_pressure REAL NOT NULL,
    right_ball_pressure REAL NOT NULL,
    left_territory REAL NOT NULL,
    right_territory REAL NOT NULL,
    left_space_control REAL NOT NULL,
    right_space_control REAL NOT NULL,
    space_control_margin REAL NOT NULL,
    PRIMARY KEY (match_id, cycle),
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS match_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    cycle INTEGER NOT NULL,
    subcycle INTEGER NOT NULL,
    team TEXT NOT NULL,
    unum INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    raw_action TEXT NOT NULL,
    args_json TEXT,
    attention_side TEXT,
    attention_unum INTEGER,
    say_text TEXT,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS match_data_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    cycle INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    team TEXT,
    unum INTEGER,
    x REAL,
    y REAL,
    confidence TEXT NOT NULL,
    details_json TEXT,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ball_match_cycle ON match_ball_frames(match_id, cycle);
CREATE INDEX IF NOT EXISTS idx_players_match_cycle ON match_player_frames(match_id, cycle);
CREATE INDEX IF NOT EXISTS idx_spatial_match_cycle ON match_spatial_frames(match_id, cycle);
CREATE INDEX IF NOT EXISTS idx_data_events_match_cycle ON match_data_events(match_id, cycle);
CREATE INDEX IF NOT EXISTS idx_actions_match_cycle ON match_actions(match_id, cycle);
CREATE INDEX IF NOT EXISTS idx_actions_match_type ON match_actions(match_id, action_type);

CREATE TABLE IF NOT EXISTS match_analytics_summary (
    match_id INTEGER PRIMARY KEY,
    analytics_version INTEGER NOT NULL,
    summary_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS match_team_statistics (
    match_id INTEGER NOT NULL,
    team TEXT NOT NULL,
    possession_cycles INTEGER NOT NULL,
    possession_pct REAL NOT NULL,
    possession_segments INTEGER NOT NULL,
    passes_completed INTEGER NOT NULL,
    passes_received INTEGER NOT NULL,
    kick_actions INTEGER NOT NULL,
    pass_attempts_estimated INTEGER NOT NULL,
    pass_accuracy_pct REAL,
    shots INTEGER NOT NULL,
    goals INTEGER NOT NULL,
    turnovers INTEGER NOT NULL,
    interceptions INTEGER NOT NULL,
    avg_ball_pressure REAL NOT NULL,
    avg_territory REAL NOT NULL,
    avg_space_control REAL NOT NULL,
    PRIMARY KEY (match_id, team),
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS match_player_statistics (
    match_id INTEGER NOT NULL,
    team TEXT NOT NULL,
    unum INTEGER NOT NULL,
    actions INTEGER NOT NULL,
    touch_cycles INTEGER NOT NULL,
    passes_completed INTEGER NOT NULL,
    shots INTEGER NOT NULL,
    goals INTEGER NOT NULL,
    movement_distance REAL NOT NULL,
    avg_pressure_when_possessed REAL NOT NULL,
    PRIMARY KEY (match_id, team, unum),
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS match_possession_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    team TEXT,
    start_cycle INTEGER NOT NULL,
    end_cycle INTEGER NOT NULL,
    cycles INTEGER NOT NULL,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS match_state_action_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    cycle INTEGER NOT NULL,
    team TEXT NOT NULL,
    unum INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    outcome TEXT NOT NULL,
    ball_x REAL,
    ball_y REAL,
    pressure REAL,
    space_control REAL,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS simulation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id TEXT,
    simulation_type TEXT NOT NULL,
    runs INTEGER NOT NULL,
    seed INTEGER,
    parameters_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS benchmark_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id TEXT,
    team1 TEXT NOT NULL,
    team2 TEXT NOT NULL,
    runs INTEGER NOT NULL,
    seed INTEGER,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS match_advanced_analytics (
    match_id INTEGER PRIMARY KEY,
    analytics_version INTEGER NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notification_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id TEXT,
    match_id INTEGER,
    event_type TEXT NOT NULL,
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT,
    FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_notification_history_created ON notification_history(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notification_history_event ON notification_history(event_type, status);
"""


class RunnerDB:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(matches)")}
        if 'data_status' not in columns:
            self.conn.execute("ALTER TABLE matches ADD COLUMN data_status TEXT NOT NULL DEFAULT 'pending'")
        if 'data_summary_json' not in columns:
            self.conn.execute("ALTER TABLE matches ADD COLUMN data_summary_json TEXT")
        player_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(match_player_frames)")}
        for name, sql_type in {
            'focus_x': 'REAL', 'focus_y': 'REAL', 'effort': 'REAL', 'recovery': 'REAL',
            'capacity': 'REAL', 'player_type': 'INTEGER', 'state': 'TEXT', 'counters_json': 'TEXT'
        }.items():
            if name not in player_columns:
                self.conn.execute(f"ALTER TABLE match_player_frames ADD COLUMN {name} {sql_type}")

    def close(self) -> None:
        self.conn.close()

    def create_tournament(self, tournament_id: str, tournament_type: str, config: dict[str, Any], created_at: str) -> None:
        self.conn.execute(
            "INSERT INTO tournaments (id, type, status, created_at, config_json) VALUES (?, ?, 'created', ?, ?)",
            (tournament_id, tournament_type, created_at, json.dumps(config, sort_keys=True)),
        )
        self.conn.commit()

    def update_tournament_status(self, tournament_id: str, status: str, timestamp: str, field: str) -> None:
        if field not in {"started_at", "finished_at"}:
            raise ValueError(f"Unsupported timestamp field: {field}")
        self.conn.execute(
            f"UPDATE tournaments SET status = ?, {field} = ? WHERE id = ?",
            (status, timestamp, tournament_id),
        )
        self.conn.commit()

    def register_team(self, tournament_id: str, name: str, binary_dir: str, start_script: str | None, valid: bool, message: str) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO teams
               (tournament_id, name, binary_dir, start_script, valid, validation_message)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (tournament_id, name, binary_dir, start_script, int(valid), message),
        )
        self.conn.commit()

    def start_match(self, tournament_id: str, team1: str, team2: str, match_number: int, started_at: str) -> int:
        cur = self.conn.execute(
            """INSERT INTO matches
               (tournament_id, match_number, team1, team2, status, started_at)
               VALUES (?, ?, ?, ?, 'running', ?)""",
            (tournament_id, match_number, team1, team2, started_at),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_match(self, match_id: int, score1: int, score2: int, winner: str, finished_at: str,
                     penalty1: int | None = None, penalty2: int | None = None,
                     rcg_file: str | None = None, rcl_file: str | None = None) -> None:
        self.conn.execute(
            """UPDATE matches SET score1=?, score2=?, penalty1=?, penalty2=?, winner=?,
               status='completed', finished_at=?, rcg_file=?, rcl_file=? WHERE id=?""",
            (score1, score2, penalty1, penalty2, winner, finished_at, rcg_file, rcl_file, match_id),
        )
        self.conn.commit()

    def record_event(self, tournament_id: str, level: str, message: str, created_at: str,
                     match_id: int | None = None, context: dict[str, Any] | None = None) -> None:
        self.conn.execute(
            """INSERT INTO events
               (tournament_id, match_id, level, message, created_at, context_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (tournament_id, match_id, level, message, created_at, json.dumps(context, sort_keys=True) if context else None),
        )
        self.conn.commit()

    def store_match_data(self, match_id: int, summary: dict[str, Any], balls: list[dict[str, Any]],
                         players: list[dict[str, Any]], spatial: list[dict[str, Any]],
                         events: list[dict[str, Any]]) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM match_ball_frames WHERE match_id=?", (match_id,))
            self.conn.execute("DELETE FROM match_player_frames WHERE match_id=?", (match_id,))
            self.conn.execute("DELETE FROM match_spatial_frames WHERE match_id=?", (match_id,))
            self.conn.execute("DELETE FROM match_actions WHERE match_id=?", (match_id,))
            self.conn.execute("DELETE FROM match_data_events WHERE match_id=?", (match_id,))
            self.conn.executemany(
                """INSERT INTO match_ball_frames
                   (match_id, cycle, playmode, left_score, right_score, x, y, vx, vy)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(match_id, b['cycle'], b.get('playmode'), b.get('left_score'), b.get('right_score'), b['x'], b['y'], b['vx'], b['vy']) for b in balls],
            )
            self.conn.executemany(
                """INSERT INTO match_player_frames
                   (match_id, cycle, side, team, unum, x, y, vx, vy, body, neck, focus_x, focus_y,
                    stamina, effort, recovery, capacity, kick_count, player_type, state, counters_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(match_id, p['cycle'], p['side'], p['team'], p['unum'], p['x'], p['y'], p['vx'], p['vy'],
                  p.get('body'), p.get('neck'), p.get('focus_x'), p.get('focus_y'), p.get('stamina'),
                  p.get('effort'), p.get('recovery'), p.get('capacity'), p.get('kick_count'), p.get('player_type'),
                  p.get('state'), json.dumps(p.get('counters'), ensure_ascii=False)) for p in players],
            )
            self.conn.executemany(
                """INSERT INTO match_spatial_frames
                   (match_id, cycle, ball_x, ball_y, region, possession_team, possession_unum,
                    possession_confidence, left_ball_pressure, right_ball_pressure, left_territory,
                    right_territory, left_space_control, right_space_control, space_control_margin)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(match_id, s['cycle'], s['ball_x'], s['ball_y'], s['region'], s.get('possession_team'), s.get('possession_unum'), s.get('possession_confidence'), s['left_ball_pressure'], s['right_ball_pressure'], s['left_territory'], s['right_territory'], s['left_space_control'], s['right_space_control'], s['space_control_margin']) for s in spatial],
            )
            action_rows = summary.pop('_actions_rows', []) if '_actions_rows' in summary else []
            self.conn.executemany(
                """INSERT INTO match_actions
                   (match_id, cycle, subcycle, team, unum, action_type, raw_action, args_json, attention_side, attention_unum, say_text)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(match_id, a['cycle'], a['subcycle'], a['team'], a['unum'], a['action_type'], a['raw_action'],
                  json.dumps(a.get('args', []), ensure_ascii=False), a.get('attention_side'), a.get('attention_unum'), a.get('say_text'))
                 for a in action_rows],
            )
            self.conn.executemany(
                """INSERT INTO match_data_events
                   (match_id, cycle, event_type, team, unum, x, y, confidence, details_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(match_id, e['cycle'], e['event_type'], e.get('team'), e.get('unum'), e.get('x'), e.get('y'), e.get('confidence', 'medium'), json.dumps(e.get('details', {}), ensure_ascii=False, sort_keys=True)) for e in events],
            )
            self.conn.execute(
                "UPDATE matches SET data_status='ingested', data_summary_json=? WHERE id=?",
                (json.dumps(summary, ensure_ascii=False, sort_keys=True), match_id),
            )

    def store_analytics(self, match_id: int, summary: dict[str, Any], team_rows: list[dict[str, Any]],
                        player_rows: list[dict[str, Any]], segments: list[dict[str, Any]],
                        state_action_rows: list[dict[str, Any]]) -> None:
        from datetime import datetime, timezone
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.conn:
            self.conn.execute("DELETE FROM match_analytics_summary WHERE match_id=?", (match_id,))
            self.conn.execute("DELETE FROM match_team_statistics WHERE match_id=?", (match_id,))
            self.conn.execute("DELETE FROM match_player_statistics WHERE match_id=?", (match_id,))
            self.conn.execute("DELETE FROM match_possession_segments WHERE match_id=?", (match_id,))
            self.conn.execute("DELETE FROM match_state_action_outcomes WHERE match_id=?", (match_id,))
            self.conn.execute(
                "INSERT INTO match_analytics_summary(match_id, analytics_version, summary_json, created_at) VALUES (?, ?, ?, ?)",
                (match_id, int(summary.get("analytics_version", 1)), json.dumps(summary, ensure_ascii=False, sort_keys=True), created_at),
            )
            self.conn.executemany(
                """INSERT INTO match_team_statistics
                   (match_id, team, possession_cycles, possession_pct, possession_segments, passes_completed,
                    passes_received, kick_actions, pass_attempts_estimated, pass_accuracy_pct, shots, goals,
                    turnovers, interceptions, avg_ball_pressure, avg_territory, avg_space_control)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(match_id, r["team"], r["possession_cycles"], r["possession_pct"], r["possession_segments"],
                  r["passes_completed"], r["passes_received"], r["kick_actions"], r["pass_attempts_estimated"],
                  r["pass_accuracy_pct"], r["shots"], r["goals"], r["turnovers"], r["interceptions"],
                  r["avg_ball_pressure"], r["avg_territory"], r["avg_space_control"]) for r in team_rows],
            )
            self.conn.executemany(
                """INSERT INTO match_player_statistics
                   (match_id, team, unum, actions, touch_cycles, passes_completed, shots, goals, movement_distance, avg_pressure_when_possessed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(match_id, r["team"], r["unum"], r["actions"], r["touch_cycles"], r["passes_completed"],
                  r["shots"], r["goals"], r["movement_distance"], r["avg_pressure_when_possessed"]) for r in player_rows],
            )
            self.conn.executemany(
                "INSERT INTO match_possession_segments(match_id, team, start_cycle, end_cycle, cycles) VALUES (?, ?, ?, ?, ?)",
                [(match_id, s.get("team"), s["start_cycle"], s["end_cycle"], s["cycles"]) for s in segments],
            )
            self.conn.executemany(
                """INSERT INTO match_state_action_outcomes
                   (match_id, cycle, team, unum, action_type, outcome, ball_x, ball_y, pressure, space_control)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(match_id, r["cycle"], r["team"], r["unum"], r["action_type"], r["outcome"],
                  r["ball_x"], r["ball_y"], r["pressure"], r["space_control"]) for r in state_action_rows],
            )


    def store_advanced_analytics(self, match_id: int, data: dict[str, Any], version: int = 1) -> None:
        self.conn.execute(
            """INSERT INTO match_advanced_analytics(match_id, analytics_version, data_json, created_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(match_id) DO UPDATE SET
                 analytics_version=excluded.analytics_version,
                 data_json=excluded.data_json,
                 created_at=CURRENT_TIMESTAMP""",
            (match_id, version, json.dumps(data, ensure_ascii=False, sort_keys=True)),
        )
        self.conn.commit()
    def latest_tournament(self) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM tournaments ORDER BY created_at DESC LIMIT 1").fetchone()

    def get_match(self, match_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()

    def set_match_data_status(self, match_id: int, status: str, summary: dict[str, Any] | None = None) -> None:
        self.conn.execute(
            "UPDATE matches SET data_status=?, data_summary_json=? WHERE id=?",
            (status, json.dumps(summary, ensure_ascii=False, sort_keys=True) if summary is not None else None, match_id),
        )
        self.conn.commit()
