import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

import app_paths


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'; self.source.mkdir()
        self.target = self.root / 'target'
    def tearDown(self):
        self.temp.cleanup()
    def database(self, path, hero):
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE roster (hero TEXT PRIMARY KEY)')
            db.execute('INSERT INTO roster VALUES (?)', (hero,))
            db.execute('CREATE TABLE recommendation_sessions(id TEXT PRIMARY KEY, last_seen REAL, hero TEXT)')
            db.execute("INSERT INTO recommendation_sessions VALUES ('test', 42, ?)", (hero,))
            db.execute('CREATE TABLE balance_settings(key TEXT PRIMARY KEY, value INTEGER)')
            db.execute("INSERT INTO balance_settings VALUES ('enabled', 1)")
    def test_migration_preserves_roster_counts_settings_and_source(self):
        source = self.source / 'companion.db'; self.database(source, 'haze')
        self.assertEqual(app_paths.migrate_data(self.source, self.target), ['foresight.db'])
        for path in (source, self.target / 'foresight.db'):
            with closing(sqlite3.connect(path)) as db, db:
                self.assertEqual(db.execute('SELECT hero FROM roster').fetchall(), [('haze',)])
                self.assertEqual(db.execute('SELECT hero FROM recommendation_sessions').fetchall(), [('haze',)])
                self.assertEqual(db.execute('SELECT value FROM balance_settings').fetchone()[0], 1)
    def test_existing_destination_is_never_overwritten(self):
        self.database(self.source / 'companion.db', 'haze')
        self.target.mkdir(); self.database(self.target / 'foresight.db', 'wraith')
        self.assertEqual(app_paths.migrate_data(self.source, self.target), [])
        with closing(sqlite3.connect(self.target / 'foresight.db')) as db, db:
            self.assertEqual(db.execute('SELECT hero FROM roster').fetchone()[0], 'wraith')
    def test_committed_wal_rows_are_copied(self):
        source = self.source / 'companion.db'; self.database(source, 'haze')
        with closing(sqlite3.connect(source)) as db, db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute("INSERT INTO roster VALUES ('wraith')"); db.commit()
            app_paths.migrate_data(self.source, self.target)
        with closing(sqlite3.connect(self.target / 'foresight.db')) as db, db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM roster').fetchone()[0], 2)
    def test_invalid_database_does_not_publish_partial_file(self):
        (self.source / 'companion.db').write_bytes(b'not a database')
        with self.assertRaises(sqlite3.DatabaseError):
            app_paths.migrate_data(self.source, self.target)
        self.assertFalse((self.target / 'foresight.db').exists())
        self.assertEqual(list(self.target.iterdir()), [])
    def test_cache_copy_preserves_existing_and_excludes_unrelated_files(self):
        (self.source / 'hero_stats.json').write_text('{"old": true}')
        (self.source / 'real_lineups.json').write_text('{"lineups": []}')
        (self.source / 'private.txt').write_text('ignored')
        self.target.mkdir(); (self.target / 'hero_stats.json').write_text('{"new": true}')
        app_paths.migrate_data(self.source, self.target)
        self.assertEqual(json.loads((self.target / 'hero_stats.json').read_text()), {'new':True})
        self.assertTrue((self.target / 'real_lineups.json').exists())
        self.assertFalse((self.target / 'private.txt').exists())
    def test_new_database_name_takes_precedence(self):
        self.database(self.source / 'companion.db', 'haze')
        self.database(self.source / 'foresight.db', 'wraith')
        app_paths.migrate_data(self.source, self.target)
        with closing(sqlite3.connect(self.target / 'foresight.db')) as db, db:
            self.assertEqual(db.execute('SELECT hero FROM roster').fetchone()[0], 'wraith')
    def test_frozen_worker_is_a_separate_executable(self):
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys,'executable',str(self.root/'Deadlock Foresight.exe')):
            executable, args = app_paths.worker_command()
        self.assertEqual(Path(executable), self.root/'ForesightDetector.exe')
        self.assertEqual(args,['--gui'])
    def test_source_worker_runs_python_with_entry_script(self):
        with patch.object(sys,'frozen',False,create=True):
            executable, args = app_paths.worker_command()
        self.assertEqual(executable,sys.executable)
        self.assertEqual(Path(args[1]).name,'detector_entry.py')
    def test_data_override_is_independent_of_working_directory(self):
        with patch.dict(os.environ, {'DEADLOCK_FORESIGHT_DATA_DIR':str(self.target)}):
            self.assertEqual(app_paths.user_data_dir(),self.target)
    def test_frozen_data_initialisation_does_not_copy_bundled_data(self):
        with patch.object(sys,'frozen',True,create=True), patch.object(app_paths,'DATA_DIR',self.target), patch.object(app_paths,'migrate_data') as copy:
            app_paths.ensure_data()
            copy.assert_not_called()
        self.assertTrue(self.target.is_dir())

    def test_gui_worker_pipe_and_close_protocol(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QProcess
        from app import ForesightWindow
        from balance_history import BalanceHistory
        qt = QApplication.instance() or QApplication([])
        worker = self.root / 'fake_worker.py'
        worker.write_text("import sys\nprint('READY', flush=True)\nfor line in sys.stdin:\n    if line.strip() == 'stop': break\n")
        with patch('app.worker_command', return_value=(sys.executable, ['-u', str(worker)])), patch('app.BalanceHistory', side_effect=lambda: BalanceHistory(self.root / 'test.db')):
            window = ForesightWindow()
        try:
            self.assertTrue(window.process.waitForStarted(3000))
            window.process.waitForReadyRead(3000)
            qt.processEvents()
            self.assertIn('READY', window.log.toPlainText())
            window.close()
            if window.process.state() != QProcess.ProcessState.NotRunning:
                self.assertTrue(window.process.waitForFinished(3000))
            qt.processEvents()
            self.assertEqual(window.process.state(), QProcess.ProcessState.NotRunning)
            self.assertFalse(window.timer.isActive())
        finally:
            if window.process.state() != QProcess.ProcessState.NotRunning:
                window.process.kill(); window.process.waitForFinished(3000)
            window.close()

    def test_migration_closes_connections_even_when_backup_fails(self):
        # Keep references alive so garbage collection cannot hide leaked handles.
        original_connect = sqlite3.connect
        for corrupt in (False, True):
            with self.subTest(corrupt=corrupt):
                source = self.root / ('bad' if corrupt else 'good')
                source.mkdir()
                database = source / 'companion.db'
                if corrupt:
                    database.write_bytes(b'not a database')
                else:
                    self.database(database, 'haze')
                opened = []
                def tracked_connect(*args, **kwargs):
                    connection = original_connect(*args, **kwargs)
                    opened.append(connection)
                    return connection
                with patch.object(app_paths.sqlite3, 'connect', side_effect=tracked_connect):
                    if corrupt:
                        with self.assertRaises(sqlite3.DatabaseError):
                            app_paths.migrate_data(source, self.root / 'bad_destination')
                    else:
                        app_paths.migrate_data(source, self.root / 'good_destination')
                self.assertEqual(len(opened), 2)
                for connection in opened:
                    with self.assertRaises(sqlite3.ProgrammingError):
                        connection.execute('SELECT 1')


if __name__ == '__main__':
    unittest.main()
