#!/usr/bin/env python3
from __future__ import annotations

import json
import mimetypes
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from core.simulation import simulate_round_robin, benchmark as run_benchmark, auto_seed as get_seeding
from core.reports import export_match, export_tournament

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / 'web' / 'static'


def row_to_dict(row):
    return dict(row) if row is not None else None


class DashboardAPI:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def notifications_history(self, limit: int = 50):
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT id, tournament_id, match_id, event_type, channel, status,
                          message, error, created_at, sent_at
                   FROM notification_history
                   ORDER BY id DESC LIMIT ?""",
                (max(1, min(limit, 500)),),
            )
            return [dict(r) for r in rows]

    def summary(self):
        with self.connect() as conn:
            tournament_count = conn.execute('SELECT COUNT(*) FROM tournaments').fetchone()[0]
            match_count = conn.execute('SELECT COUNT(*) FROM matches').fetchone()[0]
            team_count = conn.execute('SELECT COUNT(DISTINCT name) FROM teams').fetchone()[0]
            completed = conn.execute("SELECT COUNT(*) FROM matches WHERE status='completed'").fetchone()[0]
            recent = [dict(r) for r in conn.execute(
                '''SELECT id, tournament_id, match_number, team1, team2, score1, score2, winner,
                          status, data_status, started_at, finished_at
                   FROM matches ORDER BY id DESC LIMIT 10''')]
            tournaments = [dict(r) for r in conn.execute(
                '''SELECT id, type, status, created_at, started_at, finished_at,
                          (SELECT COUNT(*) FROM matches m WHERE m.tournament_id=t.id) AS matches,
                          (SELECT COUNT(*) FROM matches m WHERE m.tournament_id=t.id AND m.status='completed') AS completed_matches
                   FROM tournaments t ORDER BY created_at DESC LIMIT 10''')]
        return {'counts': {'tournaments': tournament_count, 'matches': match_count,
                           'teams': team_count, 'completed_matches': completed},
                'recent_matches': recent, 'tournaments': tournaments}

    def tournaments(self):
        with self.connect() as conn:
            rows = conn.execute(
                '''SELECT t.id, t.type, t.status, t.created_at, t.started_at, t.finished_at,
                          COUNT(m.id) AS matches,
                          SUM(CASE WHEN m.status='completed' THEN 1 ELSE 0 END) AS completed_matches
                   FROM tournaments t LEFT JOIN matches m ON m.tournament_id=t.id
                   GROUP BY t.id ORDER BY t.created_at DESC''')
            return [dict(r) for r in rows]

    def tournament(self, tournament_id: str):
        with self.connect() as conn:
            t = conn.execute('SELECT * FROM tournaments WHERE id=?', (tournament_id,)).fetchone()
            if not t:
                return None
            matches = [dict(r) for r in conn.execute(
                '''SELECT id, match_number, team1, team2, score1, score2, penalty1, penalty2,
                          winner, status, data_status, started_at, finished_at
                   FROM matches WHERE tournament_id=? ORDER BY COALESCE(match_number, id)''', (tournament_id,))]
            teams = [dict(r) for r in conn.execute(
                'SELECT name, valid, validation_message FROM teams WHERE tournament_id=? ORDER BY name',
                (tournament_id,))]
        standings = self._standings(matches, [x['name'] for x in teams])
        return {'tournament': dict(t), 'matches': matches, 'teams': teams, 'standings': standings}

    @staticmethod
    def _standings(matches, teams):
        table = {t: {'team': t, 'played': 0, 'wins': 0, 'draws': 0, 'losses': 0,
                     'gf': 0, 'ga': 0, 'gd': 0, 'points': 0} for t in teams}
        for m in matches:
            if m.get('status') != 'completed' or m.get('score1') is None or m.get('score2') is None:
                continue
            a, b = m['team1'], m['team2']
            sa, sb = int(m['score1']), int(m['score2'])
            for team, gf, ga in ((a, sa, sb), (b, sb, sa)):
                table.setdefault(team, {'team': team, 'played': 0, 'wins': 0, 'draws': 0, 'losses': 0,
                                        'gf': 0, 'ga': 0, 'gd': 0, 'points': 0})
                table[team]['played'] += 1
                table[team]['gf'] += gf
                table[team]['ga'] += ga
            winner = m.get('winner')
            if winner == a:
                table[a]['wins'] += 1; table[a]['points'] += 3; table[b]['losses'] += 1
            elif winner == b:
                table[b]['wins'] += 1; table[b]['points'] += 3; table[a]['losses'] += 1
            elif sa > sb:
                table[a]['wins'] += 1; table[a]['points'] += 3; table[b]['losses'] += 1
            elif sb > sa:
                table[b]['wins'] += 1; table[b]['points'] += 3; table[a]['losses'] += 1
            else:
                table[a]['draws'] += 1; table[b]['draws'] += 1
                table[a]['points'] += 1; table[b]['points'] += 1
        for row in table.values():
            row['gd'] = row['gf'] - row['ga']
        return sorted(table.values(), key=lambda x: (-x['points'], -x['gd'], -x['gf'], x['team']))

    def tournament_intelligence(self, tournament_id: str):
        with self.connect() as conn:
            rows = [dict(r) for r in conn.execute(
                """SELECT id, team1, team2, score1, score2, winner, status, finished_at, started_at
                   FROM matches WHERE tournament_id=? ORDER BY COALESCE(finished_at, started_at), id""",
                (tournament_id,),
            )]
            team_rows = [dict(r) for r in conn.execute(
                """SELECT m.team1 AS team, ts.* FROM matches m
                   JOIN match_team_statistics ts ON ts.match_id=m.id AND ts.team=m.team1
                   WHERE m.tournament_id=? AND m.status='completed'
                   UNION ALL
                   SELECT m.team2 AS team, ts.* FROM matches m
                   JOIN match_team_statistics ts ON ts.match_id=m.id AND ts.team=m.team2
                   WHERE m.tournament_id=? AND m.status='completed'""",
                (tournament_id, tournament_id),
            )]
        teams = sorted({t for m in rows for t in (m['team1'], m['team2'])})
        elo = {t: 1500.0 for t in teams}
        form = {t: [] for t in teams}
        streak = {t: 0 for t in teams}
        longest = {t: 0 for t in teams}
        records = {"largest_win": None, "highest_scoring_match": None, "most_goals": None, "best_possession": None}
        for m in rows:
            if m.get('status') != 'completed' or m.get('score1') is None or m.get('score2') is None:
                continue
            a,b=m['team1'],m['team2']; sa,sb=int(m['score1']),int(m['score2'])
            winner=m.get('winner')
            actual=1.0 if winner==a or (not winner and sa>sb) else 0.0 if winner==b or (not winner and sb>sa) else 0.5
            expected=1.0/(1.0+10**((elo[b]-elo[a])/400.0))
            k=32.0
            elo[a]+=k*(actual-expected); elo[b]+=k*((1-actual)-(1-expected))
            for team, result in ((a,'W' if actual==1 else 'L' if actual==0 else 'D'),(b,'L' if actual==1 else 'W' if actual==0 else 'D')):
                form[team].append(result)
                if result=='W': streak[team]+=1; longest[team]=max(longest[team],streak[team])
                else: streak[team]=0
            gd=abs(sa-sb)
            if records['largest_win'] is None or gd > records['largest_win']['goal_difference']:
                records['largest_win']={"match_id":m['id'],"score":f"{sa}-{sb}","winner":winner or (a if sa>sb else b),"goal_difference":gd}
            total=sa+sb
            if records['highest_scoring_match'] is None or total > records['highest_scoring_match']['goals']:
                records['highest_scoring_match']={"match_id":m['id'],"score":f"{sa}-{sb}","goals":total}
        aggregate={t:{"team":t,"played":0,"wins":0,"draws":0,"losses":0,"gf":0,"ga":0,"points":0,"elo":round(elo[t],1),"form":''.join(form[t][-5:]),"longest_win_streak":longest[t]} for t in teams}
        for m in rows:
            if m.get('status')=='completed':
                aggregate[m['team1']]['played'] += 1
                aggregate[m['team2']]['played'] += 1
        for m in rows:
            if m.get('status')!='completed': continue
            a,b=m['team1'],m['team2']; sa,sb=int(m['score1'] or 0),int(m['score2'] or 0)
            aggregate[a]['gf']+=sa; aggregate[a]['ga']+=sb; aggregate[b]['gf']+=sb; aggregate[b]['ga']+=sa
            w=m.get('winner')
            if w==a or (not w and sa>sb): aggregate[a]['wins']+=1; aggregate[b]['losses']+=1; aggregate[a]['points']+=3
            elif w==b or (not w and sb>sa): aggregate[b]['wins']+=1; aggregate[a]['losses']+=1; aggregate[b]['points']+=3
            else: aggregate[a]['draws']+=1; aggregate[b]['draws']+=1; aggregate[a]['points']+=1; aggregate[b]['points']+=1
        for t,v in aggregate.items(): v['gd']=v['gf']-v['ga']
        for tr in team_rows:
            # recover max average possession from analytics over tournament
            t=tr['team']; aggregate[t].setdefault('possession_values',[]).append(float(tr.get('possession_pct') or 0))
        for t,v in aggregate.items():
            vals=v.pop('possession_values',[]); v['avg_possession_pct']=round(sum(vals)/len(vals),2) if vals else 0.0
        ranking=sorted(aggregate.values(), key=lambda x:(-x['points'],-x['gd'],-x['gf'],-x['elo'],x['team']))
        records['most_goals']=max(teams,key=lambda t:aggregate[t]['gf']) if teams else None
        records['best_possession']=max(teams,key=lambda t:aggregate[t]['avg_possession_pct']) if teams else None
        return {"tournament_id":tournament_id,"ranking":ranking,"records":records,"matches_completed":sum(1 for m in rows if m.get('status')=='completed')}

    def simulation(self, tournament_id: str, runs: int = 5000, seed: int = 42):
        db = self._db_obj()
        try: return simulate_round_robin(db, tournament_id, runs, seed)
        finally: db.close()

    def benchmark(self, team1: str, team2: str, tournament_id: str | None = None, runs: int = 5000, seed: int = 42):
        db = self._db_obj()
        try: return run_benchmark(db, team1, team2, tournament_id, runs, seed)
        finally: db.close()

    def seeding(self, tournament_id: str):
        db = self._db_obj()
        try: return get_seeding(db, tournament_id)
        finally: db.close()

    def _db_obj(self):
        from core.database import RunnerDB
        return RunnerDB(self.db_path)

    def match(self, match_id: int):
        with self.connect() as conn:
            m = conn.execute('SELECT * FROM matches WHERE id=?', (match_id,)).fetchone()
            if not m:
                return None
            analytics = conn.execute('SELECT * FROM match_analytics_summary WHERE match_id=?', (match_id,)).fetchone()
            advanced = conn.execute('SELECT * FROM match_advanced_analytics WHERE match_id=?', (match_id,)).fetchone()
            teams = [dict(r) for r in conn.execute('SELECT * FROM match_team_statistics WHERE match_id=? ORDER BY team', (match_id,))]
            players = [dict(r) for r in conn.execute('SELECT * FROM match_player_statistics WHERE match_id=? ORDER BY team, unum', (match_id,))]
            events = []
            for r in conn.execute('SELECT * FROM match_data_events WHERE match_id=? ORDER BY cycle, id LIMIT 5000', (match_id,)):
                d = dict(r)
                try:
                    d['details'] = json.loads(d.pop('details_json')) if d.get('details_json') else {}
                except json.JSONDecodeError:
                    d['details'] = {}
                events.append(d)
            segments = [dict(r) for r in conn.execute(
                'SELECT team, start_cycle, end_cycle, cycles FROM match_possession_segments WHERE match_id=? ORDER BY start_cycle', (match_id,))]
            action_outcomes = [dict(r) for r in conn.execute(
                'SELECT cycle, team, unum, action_type, outcome, ball_x, ball_y, pressure, space_control FROM match_state_action_outcomes WHERE match_id=? ORDER BY cycle LIMIT 3000', (match_id,))]
        analytics_summary = json.loads(analytics['summary_json']) if analytics else None
        advanced_data = json.loads(advanced['data_json']) if advanced else None
        return {'match': dict(m), 'analytics': analytics_summary, 'advanced': advanced_data, 'team_statistics': teams,
                'player_statistics': players, 'events': events, 'possession_segments': segments,
                'action_outcomes': action_outcomes}

    def advanced(self, match_id: int):
        with self.connect() as conn:
            row = conn.execute('SELECT data_json FROM match_advanced_analytics WHERE match_id=?', (match_id,)).fetchone()
        if not row:
            return None
        try:
            return json.loads(row['data_json'])
        except json.JSONDecodeError:
            return None

    def visual_data(self, match_id: int):
        with self.connect() as conn:
            match = conn.execute('SELECT * FROM matches WHERE id=?', (match_id,)).fetchone()
            if not match:
                return None
            team_names = [match['team1'], match['team2']]
            # Final frame and average player position are both useful: final for replay-like view,
            # average for tactical shape.
            last_cycle = conn.execute('SELECT MAX(cycle) FROM match_player_frames WHERE match_id=?', (match_id,)).fetchone()[0]
            final_players = [dict(r) for r in conn.execute(
                'SELECT team, unum, x, y, vx, vy, stamina, effort, body, neck FROM match_player_frames WHERE match_id=? AND cycle=? ORDER BY team, unum',
                (match_id, last_cycle or 0))]
            avg_players = [dict(r) for r in conn.execute(
                'SELECT team, unum, AVG(x) AS x, AVG(y) AS y, AVG(vx) AS vx, AVG(vy) AS vy, AVG(stamina) AS stamina FROM match_player_frames WHERE match_id=? GROUP BY team, unum ORDER BY team, unum',
                (match_id,))]
            ball_rows = [dict(r) for r in conn.execute(
                'SELECT cycle, x, y, vx, vy, playmode, left_score, right_score FROM match_ball_frames WHERE match_id=? ORDER BY cycle', (match_id,))]
            step = max(1, len(ball_rows) // 500)
            ball = ball_rows[::step]
            spatial_rows = [dict(r) for r in conn.execute(
                'SELECT cycle, ball_x, ball_y, possession_team, possession_unum, possession_confidence, left_ball_pressure, right_ball_pressure, left_territory, right_territory, left_space_control, right_space_control, space_control_margin FROM match_spatial_frames WHERE match_id=? ORDER BY cycle', (match_id,))]
            sstep = max(1, len(spatial_rows) // 320)
            spatial = spatial_rows[::sstep]
            event_rows = []
            for r in conn.execute(
                "SELECT cycle, event_type, team, unum, x, y, confidence, details_json FROM match_data_events WHERE match_id=? AND event_type IN ('goal','shot','pass','turnover','interception','playmode') ORDER BY cycle,id LIMIT 3000", (match_id,)):
                d = dict(r)
                try:
                    d['details'] = json.loads(d.pop('details_json')) if d.get('details_json') else {}
                except json.JSONDecodeError:
                    d['details'] = {}
                event_rows.append(d)
            action_rows = [dict(r) for r in conn.execute(
                'SELECT cycle, subcycle, team, unum, action_type, raw_action FROM match_actions WHERE match_id=? ORDER BY cycle, subcycle, id LIMIT 1200', (match_id,))]
            action_outcomes = [dict(r) for r in conn.execute(
                'SELECT cycle, team, unum, action_type, outcome, ball_x, ball_y, pressure, space_control FROM match_state_action_outcomes WHERE match_id=? ORDER BY cycle LIMIT 1200', (match_id,))]
            shots = [e for e in event_rows if e['event_type'] in {'shot', 'goal'}]
            passes = []
            for e in event_rows:
                if e['event_type'] != 'pass':
                    continue
                details = e.get('details') or {}
                receiver = details.get('receiver_unum')
                receiver_team = details.get('receiver_team')
                if receiver is not None and receiver_team:
                    passes.append({'cycle': e['cycle'], 'team': e['team'], 'unum': e['unum'],
                                   'x': e['x'], 'y': e['y'], 'receiver_team': receiver_team,
                                   'receiver_unum': receiver, 'outcome': details.get('outcome', 'pass_completed'),
                                   'confidence': e['confidence']})
        return {'match': dict(match), 'team_names': team_names, 'last_cycle': last_cycle,
                'final_players': final_players, 'average_players': avg_players, 'ball': ball,
                'spatial': spatial, 'events': event_rows, 'shots': shots, 'passes': passes,
                'actions': action_rows, 'action_outcomes': action_outcomes}

    def replay_meta(self, match_id: int):
        with self.connect() as conn:
            m = conn.execute('SELECT id, team1, team2, score1, score2, winner FROM matches WHERE id=?', (match_id,)).fetchone()
            if not m:
                return None
            last_ball = conn.execute('SELECT MAX(cycle) FROM match_ball_frames WHERE match_id=?', (match_id,)).fetchone()[0]
            last_player = conn.execute('SELECT MAX(cycle) FROM match_player_frames WHERE match_id=?', (match_id,)).fetchone()[0]
            event_count = conn.execute('SELECT COUNT(*) FROM match_data_events WHERE match_id=?', (match_id,)).fetchone()[0]
            first_cycle = conn.execute('SELECT MIN(cycle) FROM match_ball_frames WHERE match_id=?', (match_id,)).fetchone()[0]
            last_cycle = max(x or 0 for x in (last_ball, last_player))
            return {**dict(m), 'first_cycle': first_cycle or 0, 'last_cycle': last_cycle, 'event_count': event_count}

    def replay_chunk(self, match_id: int, start: int, end: int, step: int = 2):
        step = max(1, min(int(step), 20))
        start = max(0, int(start)); end = max(start, int(end))
        with self.connect() as conn:
            m = conn.execute('SELECT id, team1, team2 FROM matches WHERE id=?', (match_id,)).fetchone()
            if not m:
                return None
            ball_rows = [dict(r) for r in conn.execute(
                """SELECT cycle, x, y, vx, vy, playmode, left_score, right_score
                   FROM match_ball_frames
                   WHERE match_id=? AND cycle BETWEEN ? AND ? ORDER BY cycle""",
                (match_id, start, end))]
            spatial_rows = {int(r['cycle']): dict(r) for r in conn.execute(
                """SELECT cycle, possession_team, possession_unum, possession_confidence,
                          left_ball_pressure, right_ball_pressure, left_territory, right_territory,
                          left_space_control, right_space_control, space_control_margin
                   FROM match_spatial_frames
                   WHERE match_id=? AND cycle BETWEEN ? AND ? ORDER BY cycle""",
                (match_id, start, end))}
            wanted = [int(r['cycle']) for r in ball_rows if (int(r['cycle']) - start) % step == 0]
            if ball_rows and (not wanted or wanted[-1] != int(ball_rows[-1]['cycle'])):
                wanted.append(int(ball_rows[-1]['cycle']))
            wanted_set = set(wanted)
            players_by = {}
            for r in conn.execute(
                """SELECT cycle, team, unum, x, y, vx, vy, body, neck, stamina, effort, recovery,
                          kick_count, player_type, state
                   FROM match_player_frames
                   WHERE match_id=? AND cycle BETWEEN ? AND ? ORDER BY cycle, team, unum""",
                (match_id, start, end)):
                c = int(r['cycle'])
                if c in wanted_set:
                    players_by.setdefault(c, []).append(dict(r))
            events_by = {}
            for r in conn.execute(
                """SELECT cycle, event_type, team, unum, x, y, confidence, details_json
                   FROM match_data_events
                   WHERE match_id=? AND cycle BETWEEN ? AND ?
                     AND event_type IN ('goal','shot','pass','turnover','interception','playmode')
                   ORDER BY cycle, id""", (match_id, start, end)):
                c = int(r['cycle']); d = dict(r)
                try:
                    d['details'] = json.loads(d.pop('details_json')) if d.get('details_json') else {}
                except json.JSONDecodeError:
                    d['details'] = {}
                events_by.setdefault(c, []).append(d)
            actions_by = {}
            if wanted:
                placeholders = ','.join('?' for _ in wanted)
                for r in conn.execute(
                    f"""SELECT cycle, team, unum, action_type, raw_action
                        FROM match_actions
                        WHERE match_id=? AND cycle IN ({placeholders})
                        ORDER BY cycle, subcycle, id""",
                    (match_id, *wanted)):
                    actions_by.setdefault(int(r['cycle']), []).append(dict(r))
        frames = []
        ball_map = {int(r['cycle']): r for r in ball_rows}
        for c in wanted:
            b = ball_map.get(c)
            if not b:
                continue
            frames.append({
                'cycle': c,
                'ball': {k: b[k] for k in ('x','y','vx','vy')},
                'playmode': b.get('playmode'),
                'score': {'left': b.get('left_score'), 'right': b.get('right_score')},
                'players': players_by.get(c, []),
                'spatial': spatial_rows.get(c, {}),
                'events': events_by.get(c, []),
                'actions': actions_by.get(c, []),
            })
        return {'match': dict(m), 'start': start, 'end': end, 'step': step, 'frames': frames}

    def export_match_report(self, match_id: int, fmt: str):
        path = export_match(self.db_path, match_id, fmt, ROOT / 'reports')
        return path

    def export_tournament_report(self, tournament_id: str, fmt: str):
        path = export_tournament(self.db_path, tournament_id, fmt, ROOT / 'reports')
        return path

    def match_graphics(self, match_id: int):
        with self.connect() as conn:
            m = conn.execute('SELECT id, tournament_id, match_number FROM matches WHERE id=?', (match_id,)).fetchone()
        if not m:
            return None
        # Lazy import keeps matplotlib out of the critical Tournament path.
        from Analyzer.graphics import generate_match_graphics
        out = ROOT / 'tournaments' / str(m['tournament_id']) / 'matches' / f"match_{m['match_number']}_data" / 'analytics' / 'graphics'
        files = generate_match_graphics(self.db_path, match_id, out)
        return {name: f"/api/graphics/{match_id}/{Path(path).name}" for name, path in files.items()}

    def tournament_graphics(self, tournament_id: str):
        from Analyzer.graphics import generate_tournament_graphics
        out = ROOT / 'tournaments' / tournament_id / 'analytics' / 'graphics'
        files = generate_tournament_graphics(self.db_path, tournament_id, out)
        return {name: f"/api/tournament-graphics-file/{tournament_id}/{Path(path).name}" for name, path in files.items()}


class Handler(BaseHTTPRequestHandler):
    api: DashboardAPI | None = None

    def _send_json(self, payload, status=HTTPStatus.OK):
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _serve_file(self, target: Path, download: bool = False):
        if not target.exists() or not target.is_file():
            self._send_json({'error': 'file not found'}, HTTPStatus.NOT_FOUND)
            return

        ctype = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
        size = target.stat().st_size

        try:
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(size))
            self.send_header('Cache-Control', 'no-store' if download else 'public, max-age=60')
            if download:
                self.send_header('Content-Disposition', f"attachment; filename=\"{target.name}\"")
            self.end_headers()

            # Stream files so large PDF/ZIP/HTML downloads do not require the
            # entire artifact in memory and can stop cleanly if the browser
            # closes the connection while downloading.
            with target.open('rb') as fh:
                while True:
                    chunk = fh.read(64 * 1024)
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        return
        except (BrokenPipeError, ConnectionResetError):
            return

    def _serve_static(self, path: str):
        rel = 'index.html' if path in {'/', ''} else path.removeprefix('/')
        target = (WEB_DIR / rel).resolve()
        if WEB_DIR.resolve() not in target.parents and target != WEB_DIR.resolve():
            self._send_json({'error': 'invalid path'}, HTTPStatus.BAD_REQUEST); return
        if not target.exists() or not target.is_file():
            self._send_json({'error': 'not found'}, HTTPStatus.NOT_FOUND); return
        self._serve_file(target)

    def do_GET(self):
        try:
            parsed = __import__('urllib.parse', fromlist=['urlparse']).urlparse(self.path)
            path = parsed.path
            if path == '/api/health':
                self._send_json({'ok': True, 'service': 'runner-web'}); return
            if path == '/api/summary':
                self._send_json(self.api.summary()); return
            if path == '/api/notifications':
                q = __import__('urllib.parse', fromlist=['parse_qs']).parse_qs(parsed.query)
                limit = max(1, min(500, int(q.get('limit', ['50'])[0])))
                self._send_json(self.api.notifications_history(limit)); return
            if path == '/api/tournaments':
                self._send_json(self.api.tournaments()); return
            if path.startswith('/api/tournaments/'):
                parts = path.split('/')
                if len(parts) == 4:
                    item = self.api.tournament(parts[3])
                    self._send_json(item or {'error': 'tournament not found'}, HTTPStatus.OK if item else HTTPStatus.NOT_FOUND); return
                if len(parts) == 5 and parts[4] == 'intelligence':
                    item = self.api.tournament_intelligence(parts[3])
                    self._send_json(item or {'error': 'tournament not found'}, HTTPStatus.OK if item else HTTPStatus.NOT_FOUND); return
                if len(parts) == 5 and parts[4] == 'simulation':
                    q = __import__('urllib.parse', fromlist=['parse_qs']).parse_qs(parsed.query)
                    runs = max(100, min(100000, int(q.get('runs', ['5000'])[0])))
                    seed = int(q.get('seed', ['42'])[0])
                    self._send_json(self.api.simulation(parts[3], runs, seed)); return
                if len(parts) == 5 and parts[4] == 'seeding':
                    self._send_json({'tournament_id': parts[3], 'seeding': self.api.seeding(parts[3])}); return
                if len(parts) == 5 and parts[4] == 'graphics':
                    item = self.api.tournament_graphics(parts[3]); self._send_json(item); return
            if path.startswith('/api/reports/match/'):
                parts = path.split('/')
                if len(parts) != 6:
                    self._send_json({'error': 'invalid match report path'}, HTTPStatus.BAD_REQUEST); return
                try: match_id = int(parts[4])
                except ValueError:
                    self._send_json({'error': 'invalid match id'}, HTTPStatus.BAD_REQUEST); return
                fmt = parts[5]
                if fmt not in {'json','html','csv','pdf','graphics'}:
                    self._send_json({'error': 'unsupported report format'}, HTTPStatus.BAD_REQUEST); return
                target = self.api.export_match_report(match_id, fmt)
                self._serve_file(target, download=True); return
            if path.startswith('/api/reports/tournament/'):
                parts = path.split('/')
                if len(parts) != 6:
                    self._send_json({'error': 'invalid tournament report path'}, HTTPStatus.BAD_REQUEST); return
                tournament_id = parts[4]; fmt = parts[5]
                if fmt not in {'json','html','csv','pdf','graphics'}:
                    self._send_json({'error': 'unsupported report format'}, HTTPStatus.BAD_REQUEST); return
                target = self.api.export_tournament_report(tournament_id, fmt)
                self._serve_file(target, download=True); return
            if path.startswith('/api/tournament-graphics-file/'):
                parts = path.split('/')
                if len(parts) != 5:
                    self._send_json({'error': 'invalid graphics path'}, HTTPStatus.BAD_REQUEST); return
                tournament_id, filename = parts[3], parts[4]
                allowed = {'results_wdl.png', 'tournament_network.png'}
                if filename not in allowed:
                    self._send_json({'error': 'invalid graphics file'}, HTTPStatus.BAD_REQUEST); return
                target = ROOT / 'tournaments' / tournament_id / 'analytics' / 'graphics' / filename
                if not target.exists(): self.api.tournament_graphics(tournament_id)
                self._serve_file(target); return
            if path.startswith('/api/graphics/'):
                parts = path.split('/')
                if len(parts) != 5:
                    self._send_json({'error': 'invalid graphics path'}, HTTPStatus.BAD_REQUEST); return
                try: match_id = int(parts[3])
                except ValueError:
                    self._send_json({'error': 'invalid match id'}, HTTPStatus.BAD_REQUEST); return
                filename = parts[4]
                allowed = {'match_overview.png', 'shot_map.png', 'passing_network.png'}
                if filename not in allowed:
                    self._send_json({'error': 'invalid graphics file'}, HTTPStatus.BAD_REQUEST); return
                with self.api.connect() as conn:
                    m = conn.execute('SELECT tournament_id, match_number FROM matches WHERE id=?', (match_id,)).fetchone()
                if not m:
                    self._send_json({'error': 'match not found'}, HTTPStatus.NOT_FOUND); return
                target = ROOT / 'tournaments' / str(m['tournament_id']) / 'matches' / f"match_{m['match_number']}_data" / 'analytics' / 'graphics' / filename
                if not target.exists(): self.api.match_graphics(match_id)
                self._serve_file(target); return
            if path == '/api/benchmark':
                q = __import__('urllib.parse', fromlist=['parse_qs']).parse_qs(parsed.query)
                team1 = q.get('team1', [''])[0]; team2 = q.get('team2', [''])[0]
                if not team1 or not team2:
                    self._send_json({'error': 'team1 and team2 are required'}, HTTPStatus.BAD_REQUEST); return
                tournament_id = q.get('tournament_id', [None])[0]
                runs = max(100, min(100000, int(q.get('runs', ['5000'])[0])))
                seed = int(q.get('seed', ['42'])[0])
                self._send_json(self.api.benchmark(team1, team2, tournament_id, runs, seed)); return
            if path.startswith('/api/matches/'):
                parts = path.split('/')
                if len(parts) >= 5 and parts[4] == 'replay':
                    try:
                        match_id = int(parts[3])
                    except ValueError:
                        self._send_json({'error': 'invalid match id'}, HTTPStatus.BAD_REQUEST); return
                    q = __import__('urllib.parse', fromlist=['parse_qs']).parse_qs(parsed.query)
                    if len(parts) == 6 and parts[5] == 'meta':
                        item = self.api.replay_meta(match_id)
                    else:
                        start = int(q.get('start', ['0'])[0])
                        end = int(q.get('end', [str(start + 600)])[0])
                        step = int(q.get('step', ['2'])[0])
                        item = self.api.replay_chunk(match_id, start, end, step)
                    self._send_json(item or {'error': 'match not found'}, HTTPStatus.OK if item else HTTPStatus.NOT_FOUND); return
            if path.startswith('/api/matches/'):
                parts = path.split('/')
                if len(parts) < 4:
                    self._send_json({'error': 'invalid match path'}, HTTPStatus.BAD_REQUEST); return
                try: match_id = int(parts[3])
                except ValueError:
                    self._send_json({'error': 'invalid match id'}, HTTPStatus.BAD_REQUEST); return
                if len(parts) == 4:
                    item = self.api.match(match_id)
                elif len(parts) == 5 and parts[4] == 'visuals':
                    item = self.api.visual_data(match_id)
                elif len(parts) == 5 and parts[4] == 'advanced':
                    item = self.api.advanced(match_id)
                elif len(parts) == 5 and parts[4] == 'graphics':
                    item = self.api.match_graphics(match_id)
                else:
                    self._send_json({'error': 'unknown match endpoint'}, HTTPStatus.NOT_FOUND); return
                self._send_json(item or {'error': 'match not found'}, HTTPStatus.OK if item else HTTPStatus.NOT_FOUND); return
            self._serve_static(path)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:
            self._send_json({'error': str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, fmt, *args):
        print(f'[web] {self.address_string()} - {fmt % args}')


def serve(db_path: Path, host: str = '127.0.0.1', port: int = 8000):
    from core.database import RunnerDB
    db = RunnerDB(db_path); db.close()
    Handler.api = DashboardAPI(db_path)
    server = ThreadingHTTPServer((host, port), Handler)
    print(f'Runner Web Dashboard: http://{host}:{port}')
    print(f'Database: {db_path}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
