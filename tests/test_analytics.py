from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from core.analytics import analyze_match
from core.database import RunnerDB
from core.match_ingestion import ingest_match_data

RCG = '''ULG6
(team 0 Alpha Beta 0 0)
(playmode 0 before_kick_off)
(show 0 ((b) 0 0 0 0) ((l 1) 0 0 -10 0 0 0 0 0 (v h 180) (s 8000 1 1 130600) (c 0 0 0 0 0 0 0 0 0 0 0)) ((l 2) 0 0 -5 0 0 0 0 0 (v h 180) (s 8000 1 1) (c 0 0 0 0 0 0 0 0 0 0 0)) ((r 1) 0 0 10 0 0 0 180 0 (v h 180) (s 8000 1 1) (c 0 0 0 0 0 0 0 0 0 0 0)))
(show 1 ((b) 0 0 0 0) ((l 1) 0 0 -2 0 0 0 0 0 (v h 180) (s 8000 1 1) (c 0 0 0 0 0 0 0 0 0 0 0)) ((l 2) 0 0 -4 0 0 0 0 0 (v h 180) (s 8000 1 1) (c 0 0 0 0 0 0 0 0 0 0 0)) ((r 1) 0 0 8 0 0 0 180 0 (v h 180) (s 8000 1 1) (c 0 0 0 0 0 0 0 0 0 0 0)))
(team 2 Alpha Beta 1 0)
(playmode 2 goal_l)
(show 2 ((b) 52 0 0 0) ((l 1) 0 0 50 0 0 0 0 0 (v h 180) (s 8000 1 1) (c 1 0 0 0 0 0 0 0 0 0 0)) ((l 2) 0 0 20 0 0 0 0 0 (v h 180) (s 8000 1 1) (c 0 0 0 0 0 0 0 0 0 0 0)) ((r 1) 0 0 30 0 0 0 180 0 (v h 180) (s 8000 1 1) (c 0 0 0 0 0 0 0 0 0 0 0)))
'''
RCL = '1,0 Recv Alpha_1: (kick 100 0)(done)\n1,0 Recv Alpha_1: (turn 20)(done)\n'


class AnalyticsTests(unittest.TestCase):
    def test_analytics_pipeline(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            rcg = root / 'match.rcg'
            rcl = root / 'match.rcl'
            rcg.write_text(RCG, encoding='utf-8')
            rcl.write_text(RCL, encoding='utf-8')
            db = RunnerDB(root / 'runner.db')
            db.create_tournament('t1', 'stepladder', {}, '2026-01-01T00:00:00+00:00')
            match_id = db.start_match('t1', 'Alpha', 'Beta', 1, '2026-01-01T00:00:00+00:00')
            db.finish_match(match_id, 1, 0, 'Alpha', '2026-01-01T00:01:00+00:00')
            ingest_match_data(db, match_id, rcg, root / 'data', 'Alpha', 'Beta', rcl_file=rcl, run_analytics=False)
            summary = analyze_match(db, match_id, root / 'data' / 'analytics')
            self.assertEqual(summary['match_id'], match_id)
            self.assertEqual(summary['goals']['Alpha'], 1)
            self.assertGreaterEqual(summary['actions'], 2)
            self.assertGreaterEqual(summary['state_action_outcomes'], 1)
            team_count = db.conn.execute('SELECT COUNT(*) FROM match_team_statistics WHERE match_id=?', (match_id,)).fetchone()[0]
            player_count = db.conn.execute('SELECT COUNT(*) FROM match_player_statistics WHERE match_id=?', (match_id,)).fetchone()[0]
            self.assertEqual(team_count, 2)
            self.assertGreater(player_count, 0)
            self.assertTrue((root / 'data' / 'analytics' / 'analytics.json').exists())
            db.close()

    def test_analytics_is_reproducible(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            rcg = root / 'match.rcg'
            rcg.write_text(RCG, encoding='utf-8')
            db = RunnerDB(root / 'runner.db')
            db.create_tournament('t1', 'stepladder', {}, '2026-01-01T00:00:00+00:00')
            match_id = db.start_match('t1', 'Alpha', 'Beta', 1, '2026-01-01T00:00:00+00:00')
            db.finish_match(match_id, 1, 0, 'Alpha', '2026-01-01T00:01:00+00:00')
            ingest_match_data(db, match_id, rcg, root / 'data', 'Alpha', 'Beta', run_analytics=False)
            first = analyze_match(db, match_id)
            second = analyze_match(db, match_id)
            self.assertEqual(first, second)
            db.close()


if __name__ == '__main__':
    unittest.main()

class AdvancedAnalyticsTests(unittest.TestCase):
    def test_advanced_analytics(self):
        from core.advanced_analytics import analyze_advanced
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            rcg = root / 'match.rcg'
            rcg.write_text(RCG, encoding='utf-8')
            db = RunnerDB(root / 'runner.db')
            db.create_tournament('t1', 'stepladder', {}, '2026-01-01T00:00:00+00:00')
            match_id = db.start_match('t1', 'Alpha', 'Beta', 1, '2026-01-01T00:00:00+00:00')
            db.finish_match(match_id, 1, 0, 'Alpha', '2026-01-01T00:01:00+00:00')
            ingest_match_data(db, match_id, rcg, root / 'data', 'Alpha', 'Beta', run_analytics=False)
            analyze_match(db, match_id)
            advanced = analyze_advanced(db, match_id)
            self.assertEqual(advanced['version'], 1)
            self.assertEqual(set(advanced['teams']), {'Alpha', 'Beta'})
            self.assertEqual(len(advanced['team_styles']), 2)
            self.assertGreater(len(advanced['momentum']), 0)
            self.assertEqual(len(advanced['player_ratings']), 3)
            self.assertIn('recent_form', advanced)
            self.assertTrue(db.conn.execute('SELECT 1 FROM match_advanced_analytics WHERE match_id=?', (match_id,)).fetchone())
            db.close()
