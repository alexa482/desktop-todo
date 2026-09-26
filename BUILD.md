# macOS build (Apple Silicon)

Use Python 3.12 with Tkinter on macOS. Install pinned build dependencies:

```sh
python3 -m pip install -r requirements-build.txt
python3 scripts/build_icon.py
python3 -B -m unittest -v test_app
PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller-cache" python3 -m PyInstaller --clean --noconfirm "My To Do List.spec"
```

Result: `dist/My To Do List.app`. Copy that entire bundle to `/Applications`.
The build includes Python, Tk/Tcl, Pillow, all background photos, and the ICNS icon.
The icon source is `assets/Todolistappicon.jpg`; it is not a slideshow image.

Normal source runs continue to use the project's `tasks.json`.
The packaged app uses `~/Library/Application Support/My To Do List/tasks.json`.
On its first launch, a read-only snapshot of tasks.json taken at build time is
copied there. Existing user data is never replaced by the snapshot on app updates.
Rebuild to include later changes to bundled photos or the initial snapshot.

This personal build is ad-hoc signed, not Developer ID signed or notarized.
It targets Apple Silicon (arm64). Keep a backup of Application Support task data
before transferring to another computer. The personal seed snapshot is included
in the bundle; omit personal data before distributing the app to other people.
