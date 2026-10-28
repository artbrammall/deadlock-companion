# Deadlock Foresight: personal Windows build

## Install this update

Close the app. Extract the patch into your existing `deadlock-foresight` project,
merging folders and replacing matching files. Keep the assets, recognition
portraits, screen templates and `hero_ids.json` already in your project.

In VS Code's terminal with the virtual environment activated:

```powershell
python -m pip install pyinstaller==6.22.3
python tools/build_windows.py
```

The build runs the test suite, creates the GUI and detector executables, checks
the packaged detector's imports and assets without screen capture or network
requests, copies existing personal data if needed, and creates a Desktop shortcut.
If a step fails, stop and share the output. The script does not ask for admin rights.

When it finishes, close VS Code and open **Deadlock Foresight** from your Desktop.
Check the saved roster and counts, then close the window. No ranked game is needed
for this launch check. Live capture still needs to be observed during normal play.

## Where the files live

Executable:

```text
dist\Deadlock Foresight\Deadlock Foresight.exe
```

Keep the **whole** `dist\Deadlock Foresight` folder together. The `_internal`
folder and `ForesightDetector.exe` are required. The Desktop shortcut points to
this location; don't move only the executable to your Desktop.

Personal data:

```text
%LOCALAPPDATA%\DeadlockForesight\
```

Paste that path into File Explorer to find `foresight.db` (roster, counts and
balance setting), statistics and lineup caches, `debug_live`, and `app.log`.
Both `python app.py` and the executable now use that same persistent data folder.
One normal app instance can run at a time. Preview uses separate temporary storage.

## Migration and backups

On the first build or normal source launch, the app copies `data\companion.db`
(or `data\foresight.db` if already renamed) to `foresight.db` in the personal data
folder. SQLite's backup API copies the full database, including committed WAL
transactions. The original stays in your project as a backup.

Existing destination files are never overwritten. The current statistics,
recorded lineups and opportunity cache are copied if absent. Historical evaluation
reports and other experimental files remain in the original project `data` folder;
new tool outputs use the new personal data folder. Do not copy old backups over a
newer active database after using the packaged app.

The old database name intentionally remains in migration code and its tests so
existing installations can be recognised. Visible branding, the executable and
shortcut use Deadlock Foresight. The active database uses the new name.

## Updating the app later

Edit your Python source as usual. Inspect the interface without a game:

```powershell
python app.py --preview
```

Close the normal app before rebuilding:

```powershell
python tools/build_windows.py
```

Rebuilding replaces the packaged program and refreshes the Desktop shortcut.
Personal data is outside the build folder and is retained. Do not delete the
source project or its virtual environment if you want to keep editing/rebuilding.

The icon is an original geometric brass emblem based on the interface emblem.
Hero artwork retains the source credits already supplied in your assets folder.

## Technical notes and validation

The windowed GUI launches a separate console-capable detector through QProcess's
redirected input/output pipes. This keeps the existing structured event and stop
protocol while avoiding recursively launching the GUI as if it were Python.
The detector uses PyInstaller's early console hiding option as well.
Closing the app requests detector shutdown and retains the existing five-second
forced-stop fallback for blocked network requests. Unexpected GUI errors are
written to a rotating app.log and shown in a dialog.

The packaging-related Python files and spec were syntax checked; the complete
71-test source suite passed on Linux, including migration, WAL preservation,
no-overwrite behaviour, command routing, and a real child-process shutdown check.
The Windows executables cannot be built or exercised in the Linux workspace.
Your build runs the packaged detector check on Windows before creating the shortcut.
This is a personal build, without an installer, signing or automatic updates.

References used for the packaging design:
https://www.pyinstaller.org/en/stable/runtime-information.html
https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html
https://doc.qt.io/qtforpython-6/PySide6/QtCore/QProcess.html

The patch_manifest.txt file lists exactly which project files this patch changes.
Suggested commit: Package Deadlock Foresight for Windows with persistent user data
