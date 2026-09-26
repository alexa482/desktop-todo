"""Generate the standard macOS iconset and ICNS from the user's photograph."""
from pathlib import Path
import subprocess
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets'
iconset = ASSETS / 'Todolistappicon.iconset'
iconset.mkdir(exist_ok=True)
with Image.open(ASSETS / 'Todolistappicon.jpg') as source:
    square = ImageOps.fit(ImageOps.exif_transpose(source).convert('RGB'),
                          (1024, 1024), method=Image.Resampling.LANCZOS)
    for points in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            pixels = points * scale
            suffix = '@2x' if scale == 2 else ''
            square.resize((pixels, pixels), Image.Resampling.LANCZOS).save(
                iconset / f'icon_{points}x{points}{suffix}.png')
subprocess.run(['/usr/bin/iconutil', '-c', 'icns', str(iconset),
                '-o', str(ASSETS / 'Todolistappicon.icns')], check=True)
print(ASSETS / 'Todolistappicon.icns')
