"""Persistent #1 recommendations; sessions use a documented inactivity heuristic."""
from contextlib import contextmanager
import sqlite3
import time
import uuid
from pathlib import Path

DATABASE = Path(__file__).resolve().parent / 'data' / 'companion.db'
SESSION_GAP = 120


class BalanceHistory:
    def __init__(self, path=DATABASE):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS recommendation_sessions '
                       '(id TEXT PRIMARY KEY, last_seen REAL NOT NULL, hero TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS balance_settings '
                       '(key TEXT PRIMARY KEY, value INTEGER NOT NULL)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    def enabled(self):
        with self.connect() as db:
            row = db.execute("SELECT value FROM balance_settings WHERE key='enabled'").fetchone()
        return bool(row and row[0])

    def set_enabled(self, enabled):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO balance_settings VALUES ('enabled', ?)", (int(enabled),))

    def session(self, now=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            row = db.execute('SELECT id, last_seen FROM recommendation_sessions '
                             'ORDER BY last_seen DESC LIMIT 1').fetchone()
            if row and 0 <= now - row[1] < SESSION_GAP:
                session_id = row[0]
                db.execute('UPDATE recommendation_sessions SET last_seen=? WHERE id=?', (now, session_id))
            else:
                session_id = uuid.uuid4().hex
                db.execute('INSERT INTO recommendation_sessions VALUES (?, ?, NULL)', (session_id, now))
        return session_id

    def touch(self, session_id, now=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute('UPDATE recommendation_sessions SET last_seen=? WHERE id=?', (now, session_id))

    def counts(self, excluding=None):
        with self.connect() as db:
            rows = db.execute('SELECT hero, COUNT(*) FROM recommendation_sessions '
                              'WHERE hero IS NOT NULL AND (? IS NULL OR id != ?) GROUP BY hero',
                              (excluding, excluding)).fetchall()
        return dict(rows)

    def record(self, session_id, hero):
        # Replace the current session's #1; never increment per scan or reroll.
        with self.connect() as db:
            db.execute('UPDATE recommendation_sessions SET hero=? WHERE id=?', (hero, session_id))

    def reset(self):
        # Keep session boundaries, clear only hero counts.
        with self.connect() as db:
            db.execute('UPDATE recommendation_sessions SET hero=NULL')
