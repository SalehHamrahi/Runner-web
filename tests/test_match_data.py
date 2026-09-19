from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from core.database import RunnerDB
from core.match_data import derive_events_and_spatial, parse_rcg, parse_rcl
from core.match_ingestion import ingest_match_data


RCG = '''ULG6
(team 0 Alpha Beta 0 0)
(playmode 0 before_kick_off)
(show 0 ((b) 0 0 0 0) ((l 1) 0 0 -10 0 0 0 0 (v h 180) (fp 1 2) (s 8000 1 1 130600) (c 0 0 0 0 0 0 0 0 0 0 0)) ((r 1) 0 0 10 0 0 0 180 0 (v h 180) (s 8000 1 1) (c 0 0 0 0 0 0 0 0 0 0 0)))
(show 1 ((b) 1 0 2 0) ((l 1) 0 0 0 0 0 0 0 0 (v h 180) (s 8000 1 1) (c 1 0 0 0 0 0 0 0 0 0 0)) ((l 2) 0 0 3 0 0 0 0 0 (v h 180) (s 8000 1 1) (c 0 0 0 0 0 0 0 0 0 0 0)) ((r 1) 0 0 20 0 0 0 180 0 (v h 180) (s 8000 1 1) (c 0 0 0 0 0 0 0 0 0 0 0)))
(team 100 Alpha Beta 1 0)
(playmode 100 goal_l)
(show 100 ((b) 52.5 0 0 0) ((l 1) 0 0 52 0 0 0 0 0 (v h 180) (s 8000 1 1) (c 1 0 0 0 0 0 0 0 0 0 0)) ((r 1) 0 0 20 0 0 0 180 0 (v h 180) (s 8000 1 1) (c 0 0 0 0 0 0 0 0 0 0 0)))
'''


class MatchDataTests(unittest.TestCase):
    def test_rcg_parse_and_goal(self):
        with TemporaryDirectory() as tmp:
            rcg = Path(tmp) / 'match.rcg'
            rcg.write_text(RCG, encoding='utf-8')
            balls, players, events = parse_rcg(rcg, 1)
            self.assertEqual(len(balls), 3)
            self.assertEqual(len(players), 7)
            goals = [event for event in events if event.event_type == 'goal']
            self.assertEqual(len(goals), 1)
            self.assertEqual(goals[0].team, 'Alpha')

    def test_duplicate_show_cycle_is_deduplicated(self):
        with TemporaryDirectory() as tmp:
            rcg = Path(tmp) / 'duplicate.rcg'
            duplicate = RCG.replace(
                '(team 100 Alpha Beta 1 0)\n(playmode 100 goal_l)\n',
                '(team 100 Alpha Beta 1 0)\n(playmode 100 goal_l)\n'
                '(show 100 ((b) 52.5 0 0 0) ((l 1) 0 0 52 0 0 0 0 0 (v h 180) (s 8000 1 1) (c 1 0 0 0 0 0 0 0 0 0 0)) ((r 1) 0 0 20 0 0 0 180 0 (v h 180) (s 8000 1 1) (c 0 0 0 0 0 0 0 0 0 0 0)))\n'
            )
            rcg.write_text(duplicate, encoding='utf-8')
            balls, players, _ = parse_rcg(rcg, 1)
            self.assertEqual([b.cycle for b in balls], [0, 1, 100])
            keys = {(p.cycle, p.side, p.unum) for p in players}
            self.assertEqual(len(players), len(keys))

    def test_spatial_metrics(self):
        with TemporaryDirectory() as tmp:
            rcg = Path(tmp) / 'match.rcg'
            rcg.write_text(RCG, encoding='utf-8')
            balls, players, events = parse_rcg(rcg, 1)
            spatial, derived, _ = derive_events_and_spatial(1, balls, players, events)
            self.assertEqual(len(spatial), 3)
            self.assertTrue(all('left_space_control' in row for row in spatial))
            self.assertTrue(all('left_ball_pressure' in row for row in spatial))

    def test_rcl_parse_actions(self):
        with TemporaryDirectory() as tmp:
            rcl = Path(tmp) / 'match.rcl'
            rcl.write_text(
                '29,0\tRecv Alpha_7: (kick 100 45)(attentionto our 11)(done)\n'
                '30,0\tRecv Alpha_7: (dash 80)(say "hello world")(done)\n'
                '30,0\tRecv Coach: (done)\n',
                encoding='utf-8',
            )
            actions = parse_rcl(rcl, 1, {'Alpha': 'Alpha'})
            self.assertEqual([a.action_type for a in actions], ['kick', 'attentionto', 'dash', 'say'])
            self.assertEqual(actions[0].cycle, 29)
            self.assertEqual(actions[0].attention_unum, None)
            self.assertEqual(actions[1].attention_unum, 11)
            self.assertEqual(actions[3].say_text, 'hello world')

    def test_rich_player_state(self):
        with TemporaryDirectory() as tmp:
            rcg = Path(tmp) / 'match.rcg'
            rcg.write_text(RCG, encoding='utf-8')
            _, players, _ = parse_rcg(rcg, 1)
            p = players[0]
            self.assertEqual(p.player_type, 0)
            self.assertIsNotNone(p.focus_x)
            self.assertIsNotNone(p.effort)
            self.assertIsNotNone(p.capacity)
            self.assertTrue(p.counters)

    def test_database_ingestion(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            rcg = root / 'match.rcg'
            rcg.write_text(RCG, encoding='utf-8')
            db_path = root / 'runner.db'
            db = RunnerDB(db_path)
            db.create_tournament('t1', 'stepladder', {}, '2026-01-01T00:00:00+00:00')
            match_id = db.start_match('t1', 'Alpha', 'Beta', 1, '2026-01-01T00:00:00+00:00')
            db.finish_match(match_id, 1, 0, 'Alpha', '2026-01-01T00:01:00+00:00')
            summary = ingest_match_data(db, match_id, rcg, root / 'data', 'Alpha', 'Beta')
            self.assertEqual(summary['cycles'], 3)
            self.assertEqual(db.get_match(match_id)['data_status'], 'ingested')
            counts = db.conn.execute('SELECT COUNT(*) FROM match_ball_frames WHERE match_id=?', (match_id,)).fetchone()[0]
            self.assertEqual(counts, 3)
            db.close()


if __name__ == '__main__':
    unittest.main()
