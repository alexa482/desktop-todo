# Build on macOS with: python3 -m PyInstaller --clean --noconfirm "My To Do List.spec"
from pathlib import Path

root = Path(SPECPATH)
# The seed is a read-only first-launch snapshot, never the live task database.
datas = [(str(root / 'tasks.json'), 'seed'),
         (str(root / 'assets' / 'Todolistappicon.icns'), 'assets')]
# Include all photographs, including formats currently ignored by the slideshow.
for photo in sorted((root / 'assets' / 'backgrounds').iterdir()):
    if photo.is_file() and not photo.name.startswith('.'):
        datas.append((str(photo), 'assets/backgrounds'))

a = Analysis([str(root / 'app.py')], pathex=[str(root)], binaries=[], datas=datas,
             hiddenimports=['PIL.ImageTk', 'PIL._tkinter_finder', 'tkinter'],
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='My To Do List',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, argv_emulation=False, target_arch='arm64',
          codesign_identity=None, entitlements_file=None)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='My To Do List')
app = BUNDLE(collection, name='My To Do List.app',
             icon=str(root / 'assets' / 'Todolistappicon.icns'),
             bundle_identifier='local.alexayang.mytodolist',
             info_plist={'CFBundleDisplayName': 'My To Do List',
                         'CFBundleShortVersionString': '1.0.0',
                         'CFBundleVersion': '1',
                         'NSHighResolutionCapable': True})
