from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path
import tempfile

from core.database import RunnerDB
from core.simulation import auto_seed, benchmark, elo_ratings, simulate_match, simulate_round_robin


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / 'runner.db'
        self.db = RunnerDB(self.db_path)
        with self.db.conn as conn:
            conn.execute("INSERT INTO tournaments(id,type,status,created_at,config_json) VALUES ('t1','round_robin','completed','2026-01-01','{}')")
            for team in ('A', 'B', 'C'):
                conn.execute("INSERT INTO teams(tournament_id,name,binary_dir,valid) VALUES ('t1',?,?,1)", (team, f'Bins/{team}'))
            matches = [('A','B',2,0,'A'),('B','C',1,1,None),('A','C',3,1,'A')]
            for i,(a,b,sa,sb,w) in enumerate(matches,1):
                conn.execute("INSERT INTO matches(tournament_id,match_number,team1,team2,score1,score2,winner,status,data_status) VALUES (?,?,?,?,?,?,?,?,?)", ('t1',i,a,b,sa,sb,w,'completed','ingested'))

    def tearDown(self):
        self.db.close(); self.tmp.cleanup()

    def test_elo_and_seeding(self):
        ratings = elo_ratings(self.db, 't1')
        self.assertGreater(ratings['A'], ratings['B'])
        seeds = auto_seed(self.db, 't1')
        self.assertEqual(seeds[0]['team'], 'A')
        self.assertEqual([x['seed'] for x in seeds], [1,2,3])

    def test_match_simulation_is_reproducible(self):
        ratings = elo_ratings(self.db, 't1')
        rates = __import__('core.simulation', fromlist=['team_goal_rates']).team_goal_rates(self.db, 't1')
        a = simulate_match('A','B',ratings,rates,2000,7)
        b = simulate_match('A','B',ratings,rates,2000,7)
        self.assertEqual(a, b)
        self.assertGreater(a['win_probability']['A'], a['win_probability']['B'])

    def test_tournament_simulation(self):
        result = simulate_round_robin(self.db, 't1', runs=1000, seed=7)
        self.assertEqual(result['format'], 'round_robin')
        self.assertEqual(len(result['ranking']), 3)
        self.assertAlmostEqual(sum(r['champion_probability'] for r in result['ranking']), 100.0, delta=0.2)

    def test_benchmark_contains_history(self):
        result = benchmark(self.db, 'A', 'B', 't1', runs=1000, seed=7)
        self.assertEqual(result['historical_head_to_head']['matches'], 1)
        self.assertIn('win_probability', result)


if __name__ == '__main__':
    unittest.main()
