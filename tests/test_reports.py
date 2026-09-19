from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.database import RunnerDB
from core.reports import export_match, export_tournament


class ReportsExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / 'runner.db'
        self.db = RunnerDB(self.db_path)
        with self.db.conn as conn:
            conn.execute("INSERT INTO tournaments(id,type,status,created_at,config_json) VALUES ('t1','round_robin','completed','2026-01-01','{}')")
            for team in ('A', 'B'):
                conn.execute("INSERT INTO teams(tournament_id,name,binary_dir,valid) VALUES ('t1',?,?,1)", (team, f'Bins/{team}'))
            conn.execute("INSERT INTO matches(tournament_id,match_number,team1,team2,score1,score2,winner,status,data_status) VALUES ('t1',1,'A','B',2,1,'A','completed','ingested')")
            self.match_id = conn.execute('SELECT id FROM matches').fetchone()[0]
            cols = ['match_id','team','possession_cycles','possession_pct','possession_segments','passes_completed','passes_received','kick_actions','pass_attempts_estimated','pass_accuracy_pct','shots','goals','turnovers','interceptions','avg_ball_pressure','avg_territory','avg_space_control']
            for team, poss in [('A', 60), ('B', 40)]:
                vals = [self.match_id, team, poss, poss, 2, 20, 15, 25, 30, 60, 2, 1, 4, 3, .5, .6, .55]
                conn.execute(f"INSERT INTO match_team_statistics ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", vals)
            for team, unum, x, y in [('A', 7, 10, 3), ('A', 9, 20, -4), ('B', 7, -10, 2), ('B', 10, -20, -3)]:
                conn.execute("INSERT INTO match_player_frames(match_id,cycle,side,team,unum,x,y,vx,vy) VALUES (?,?,?,?,?,?,?,?,?)", (self.match_id, 100, 'l' if team == 'A' else 'r', team, unum, x, y, 0, 0))
            conn.execute("INSERT INTO match_data_events(match_id,cycle,event_type,team,unum,x,y,confidence,details_json) VALUES (?,?,?,?,?,?,?,?,?)", (self.match_id, 100, 'goal', 'A', 7, 10, 3, 'high', '{}'))
        self.db.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_match_exports(self):
        for fmt in ('json', 'html', 'csv', 'graphics', 'pdf'):
            path = export_match(self.db_path, self.match_id, fmt, self.root / 'reports')
            self.assertTrue(path.exists(), fmt)
            self.assertGreater(path.stat().st_size, 0, fmt)
        payload = json.loads((self.root / 'reports' / 'match' / str(self.match_id) / 'match_report.json').read_text())
        self.assertEqual(payload['match']['team1'], 'A')

    def test_tournament_exports(self):
        for fmt in ('json', 'html', 'csv', 'graphics', 'pdf'):
            path = export_tournament(self.db_path, 't1', fmt, self.root / 'reports')
            self.assertTrue(path.exists(), fmt)
            self.assertGreater(path.stat().st_size, 0, fmt)


if __name__ == '__main__':
    unittest.main()
