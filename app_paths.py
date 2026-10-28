"""Bundled assets and persistent user data live in separate locations."""
import os
from contextlib import closing
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ASSET_DIR = Path(__file__).resolve().parent

def user_data_dir():
    override = os.environ.get('DEADLOCK_FORESIGHT_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local')))
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local' / 'share')))
    return base / 'DeadlockForesight'

DATA_DIR = user_data_dir()
DATABASE = DATA_DIR / 'foresight.db'


def migrate_data(source, destination):
    """Copy only missing files. SQLite backup includes committed WAL contents.

    An atomic hard link publishes each completed file without replacing a file
    another process may have created. Originals are never edited or removed.
    """
    source, destination = Path(source).resolve(), Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if source == destination or not source.is_dir():
        return []
    copied = []
    # Prefer the new database name if a source copy was already renamed.
    candidates = [(source / name, destination / 'foresight.db')
                  for name in ('foresight.db', 'companion.db') if (source / name).is_file()]
    for name in ('hero_stats.json', 'real_lineups.json', 'real_opportunity_cache.json'):
        if (source / name).is_file(): candidates.append((source / name, destination / name))
    for src, dst in candidates:
        if dst.exists(): continue
        fd, temporary = tempfile.mkstemp(prefix='.migration-', dir=destination)
        os.close(fd)
        temporary = Path(temporary)
        try:
            if src.suffix == '.db':
                with closing(sqlite3.connect(src.as_uri() + '?mode=ro', uri=True)) as old:
                    with closing(sqlite3.connect(temporary)) as new:
                        old.backup(new)
                        if new.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                            raise ValueError(f'Database integrity check failed: {src}')
            else:
                shutil.copyfile(src, temporary)
            try:
                os.link(temporary, dst)
                copied.append(dst.name)
            except FileExistsError:
                pass  # Existing personal data always wins.
        finally:
            temporary.unlink(missing_ok=True)
    return copied


def ensure_data():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not getattr(sys, 'frozen', False):
        migrate_data(ASSET_DIR / 'data', DATA_DIR)
    return DATA_DIR


def worker_command():
    if getattr(sys, 'frozen', False):
        return str(Path(sys.executable).parent / 'ForesightDetector.exe'), ['--gui']
    return sys.executable, ['-u', str(ASSET_DIR / 'detector_entry.py'), '--gui']
