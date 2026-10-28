"""Build the personal Windows installation and create a desktop shortcut."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_paths import DATA_DIR, migrate_data


def main():
    if sys.platform != 'win32':
        raise SystemExit('Build on your Windows PC with its activated virtual environment.')
    if importlib.util.find_spec('PyInstaller') is None:
        raise SystemExit('Install the builder first: python -m pip install pyinstaller==6.22.3')
    # Do not overwrite a running application, including its detector.
    result = subprocess.run(['powershell.exe','-NoProfile','-Command',
        "Get-Process -Name 'Deadlock Foresight','ForesightDetector' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"],
        capture_output=True, text=True)
    if result.stdout.strip():
        raise SystemExit('Close Deadlock Foresight before rebuilding.')
    from PySide6.QtCore import QLockFile
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(DATA_DIR / 'application.lock'))
    if not lock.tryLock(0):
        raise SystemExit('Close the app (including any Python copy) before building.')
    try:
        for path in ('hero_ids.json','screen_config.json','portraits','screen_templates',
                     'assets/hero_portraits','assets/foresight.ico'):
            if not (ROOT / path).exists(): raise SystemExit(f'Missing required asset: {path}')
        print('Checking source tests...', flush=True)
        subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-q'],
                       cwd=ROOT, check=True)
        print('Building the interface and detector...', flush=True)
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                        str(ROOT / 'DeadlockForesight.spec')], cwd=ROOT, check=True)
        folder = ROOT / 'dist' / 'Deadlock Foresight'
        worker = folder / 'ForesightDetector.exe'
        check = subprocess.run([str(worker), '--self-test'], capture_output=True, text=True,
                               encoding='utf-8', errors='replace', timeout=120,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        if check.returncode or 'FORESIGHT_WORKER_OK' not in check.stdout:
            raise RuntimeError('Packaged detector check failed:\n' + check.stdout + check.stderr)
        copied = migrate_data(ROOT / 'data', DATA_DIR)
        print('Migrated: ' + (', '.join(copied) if copied else 'existing user data retained'))
        print(f'Your data lives in: {DATA_DIR}')
        print('Original project data was not removed.', flush=True)
        subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                        '-File', str(ROOT / 'tools' / 'create_shortcut.ps1'),
                        '-Executable', str(folder / 'Deadlock Foresight.exe')], check=True)
        print(f'\nReady: {folder / "Deadlock Foresight.exe"}')
        print('Use the desktop shortcut. Keep the entire dist/Deadlock Foresight folder together.')
    finally:
        lock.unlock()


if __name__ == '__main__':
    try:
        main()
    except (subprocess.SubprocessError, OSError, RuntimeError) as error:
        print(f'Build stopped: {error}', file=sys.stderr)
        raise SystemExit(1)
