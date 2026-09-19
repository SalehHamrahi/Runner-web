import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from core.database import RunnerDB
from core.notifications import load_notification_config, send_discord


class FakeResponse:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, *_args):
        return b''


class TestNotifications(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = self.root / 'config.conf'
        self.config.write_text(
            'discord_enabled=true\n'
            'discord_webhook_url=https://discord.test/webhook\n'
            'notify_match_finished=true\n'
            'notify_tournament_finished=true\n'
            'notify_team_crash=true\n'
            'notify_server_crash=true\n',
            encoding='utf-8',
        )
        self.db_path = self.root / 'runner.db'
        self.db = RunnerDB(self.db_path)
        self.db.create_tournament('t1', 'round_robin', {}, 'now')
        for team in ('A', 'B', 'C'):
            self.db.register_team('t1', team, f'Bins/{team}', None, True, 'OK')
        self.match_id = self.db.start_match('t1', 'A', 'B', 1, 'now')
        self.db.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_config_permissions(self):
        cfg = load_notification_config(self.config)
        self.assertTrue(cfg.enabled)
        self.assertTrue(cfg.notify_match_finished)
        self.assertTrue(cfg.notify_server_crash)

    @patch('core.notifications.request.urlopen', return_value=FakeResponse())
    def test_sent_notification_is_recorded(self, urlopen):
        self.assertTrue(send_discord(
            self.config, self.db_path, 'match_finished', 't1', self.match_id,
            {'title': 'Match Finished', 'description': 'A 2 - 0 B', 'fields': [('Winner', 'A')]},
        ))
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                'SELECT status, channel, event_type FROM notification_history'
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual(rows, [('sent', 'discord', 'match_finished')])
        self.assertTrue(urlopen.called)

    @patch('core.notifications.request.urlopen', return_value=FakeResponse())
    def test_match_notification_contains_database_stats(self, urlopen):
        db = RunnerDB(self.db_path)
        db.finish_match(self.match_id, 2, 1, 'A', 'later')
        db.store_analytics(
            self.match_id,
            {'analytics_version': 1},
            [
                {'team': 'A', 'possession_cycles': 60, 'possession_pct': 55.5, 'possession_segments': 3, 'passes_completed': 24,
                 'passes_received': 24, 'kick_actions': 30, 'pass_attempts_estimated': 26, 'pass_accuracy_pct': 92.3,
                 'shots': 8, 'goals': 2, 'turnovers': 4, 'interceptions': 2, 'avg_ball_pressure': 0, 'avg_territory': 0, 'avg_space_control': 0},
                {'team': 'B', 'possession_cycles': 45, 'possession_pct': 44.5, 'possession_segments': 2, 'passes_completed': 18,
                 'passes_received': 18, 'kick_actions': 22, 'pass_attempts_estimated': 20, 'pass_accuracy_pct': 90.0,
                 'shots': 5, 'goals': 1, 'turnovers': 5, 'interceptions': 1, 'avg_ball_pressure': 0, 'avg_territory': 0, 'avg_space_control': 0},
            ],
            [], [], [],
        )
        db.close()

        captured = {}
        def fake_urlopen(req, timeout=4):
            captured['body'] = json.loads(req.data.decode('utf-8'))
            return FakeResponse()

        with patch('core.notifications.request.urlopen', side_effect=fake_urlopen):
            self.assertTrue(send_discord(
                self.config, self.db_path, 'match_finished', 't1', self.match_id, {}
            ))

        embed = captured['body']['embeds'][0]
        self.assertIn('A **2 - 1** B', embed['description'])
        values = {item['name']: item['value'] for item in embed['fields']}
        self.assertEqual(values['🏆 Winner'], 'A')
        self.assertEqual(values['⚽ Goals'], '2 - 1')
        self.assertEqual(values['🎯 Shots'], '8 - 5')
        self.assertEqual(values['📊 Possession'], '55.5% - 44.5%')
        self.assertEqual(values['✅ Pass Accuracy'], '92.3% - 90.0%')

    @patch('core.notifications.request.urlopen', return_value=FakeResponse())
    def test_tournament_notification_contains_final_standings(self, urlopen):
        db = RunnerDB(self.db_path)
        db.finish_match(self.match_id, 2, 0, 'A', 'later')
        match2 = db.start_match('t1', 'B', 'C', 2, 'later')
        db.finish_match(match2, 1, 1, 'Draw', 'later')
        db.update_tournament_status('t1', 'completed', 'later', 'finished_at')
        db.close()

        captured = {}
        def fake_urlopen(req, timeout=4):
            captured['body'] = json.loads(req.data.decode('utf-8'))
            return FakeResponse()

        with patch('core.notifications.request.urlopen', side_effect=fake_urlopen):
            self.assertTrue(send_discord(
                self.config, self.db_path, 'tournament_finished', 't1', payload={}
            ))

        embed = captured['body']['embeds'][0]
        self.assertEqual(embed['title'], '🏆 Tournament Finished')
        values = {item['name']: item['value'] for item in embed['fields']}
        self.assertEqual(values['🎮 Matches'], '2 / 2 completed')
        self.assertEqual(values['⚽ Goals'], '4')
        self.assertIn('**A** — 3 pts', values['📊 Final Standings'])
        self.assertIn('**B** — 1 pts', values['📊 Final Standings'])

    @patch('core.notifications.request.urlopen', side_effect=URLError('offline'))
    def test_failed_notification_is_recorded(self, urlopen):
        self.assertFalse(send_discord(
            self.config, self.db_path, 'server_crash', 't1', self.match_id,
            {'title': 'Server Crash', 'description': 'rcssserver stopped'},
        ))
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                'SELECT status, error FROM notification_history'
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row[0], 'failed')
        self.assertIn('offline', row[1])

    def test_disabled_permission_does_not_record(self):
        self.config.write_text('discord_enabled=true\ndiscord_webhook_url=https://discord.test/webhook\nnotify_match_finished=false\n', encoding='utf-8')
        self.assertFalse(send_discord(
            self.config, self.db_path, 'match_finished', 't1', self.match_id,
            {'title': 'Match Finished'},
        ))
        conn = sqlite3.connect(self.db_path)
        try:
            count = conn.execute('SELECT COUNT(*) FROM notification_history').fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 0)


if __name__ == '__main__':
    unittest.main()
