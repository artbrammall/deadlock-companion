# Build on Windows: python -m PyInstaller --noconfirm --clean DeadlockForesight.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_all
root = Path(SPECPATH)
assets = [(str(root / path), path) for path in ('assets', 'portraits', 'screen_templates')]
assets += [(str(root / name), '.') for name in ('hero_ids.json', 'screen_config.json')]
icon = str(root / 'assets' / 'foresight.ico')

gui_a = Analysis([str(root / 'foresight.py')], pathex=[str(root)], datas=assets,
                 excludes=['tkinter', 'matplotlib', 'sklearn', 'scipy', 'pytest'],
                 noarchive=False)
gui = EXE(PYZ(gui_a.pure), gui_a.scripts, [], exclude_binaries=True,
          name='Deadlock Foresight', console=False, icon=icon, upx=False)

dx_data, dx_binaries, dx_imports = collect_all('dxcam')
worker_a = Analysis([str(root / 'detector_entry.py')], pathex=[str(root)],
                    datas=dx_data, binaries=dx_binaries, hiddenimports=dx_imports,
                    excludes=['PySide6', 'tkinter', 'matplotlib', 'sklearn', 'scipy', 'pytest'],
                    noarchive=False)
worker = EXE(PYZ(worker_a.pure), worker_a.scripts, [], exclude_binaries=True,
             name='ForesightDetector', console=True, hide_console='hide-early',
             icon=icon, upx=False)
COLLECT(gui, worker, gui_a.binaries, gui_a.datas, worker_a.binaries, worker_a.datas,
        name='Deadlock Foresight', strip=False, upx=False)
