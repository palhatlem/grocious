"""Rebuild the selected bag-g icon: pip install cairosvg pillow; python scripts/build_icons.py."""

from pathlib import Path
import io
import json
import cairosvg
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app/static/brand"
INK, PAPER = "#1d2021", "#f8f6ef"
# Vector rendering of the selected outline bag-g, including its intact bowl and descending tail.
MARK = """<g fill="none" stroke="COLOR" stroke-linecap="round" stroke-linejoin="round">
<path stroke-width="8" d="M99 79V44C99 27 78 12 63 12C48 12 27 27 26 42
L24 73Q23 81 34 81H97M99 44V94C99 109 83 121 65 121C49 121 36 116 28 106"/>
<rect x="51" y="29" width="25" height="9" rx="4.5" stroke-width="3.5"/>
</g>"""


def svg(scale=0.88, background=True, rounded=True):
    padding = 64 * (1 - scale)
    bg = f'<rect width="128" height="128" rx="{24 if rounded else 0}" fill="{PAPER}"/>' if background else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">{bg}'
        f'<g transform="translate({padding} {padding}) scale({scale})">'
        + MARK.replace("COLOR", INK if background else "#000000")
        + "</g></svg>\n"
    )


def render(source, size):
    return cairosvg.svg2png(bytestring=source.encode(), output_width=size, output_height=size)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    standard = svg()
    (OUT / "grocious-icon.svg").write_text(standard)
    (OUT / "grocious-pwa.svg").write_text(standard)
    (OUT / "grocious-mask.svg").write_text(svg(background=False))
    for size in (16, 32, 48, 64, 128, 256, 512, 1024):
        (OUT / f"grocious-icon-{size}.png").write_bytes(render(standard, size))
    (OUT / "apple-touch-icon.png").write_bytes(render(svg(scale=0.78, rounded=False), 180))
    for size in (192, 512):
        (OUT / f"grocious-pwa-{size}.png").write_bytes(render(standard, size))
        (OUT / f"grocious-maskable-{size}.png").write_bytes(render(svg(scale=0.65, rounded=False), size))
    ico = Image.open(io.BytesIO(render(standard, 256)))
    ico.save(OUT / "favicon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    manifest_path = ROOT / "app/static/manifest.webmanifest"
    manifest = json.loads(manifest_path.read_text())
    manifest["icons"] = [
        {
            "src": f"/static/brand/grocious-{kind}-{size}.png?v=2",
            "sizes": f"{size}x{size}",
            "type": "image/png",
            "purpose": purpose,
        }
        for kind, purpose in (("pwa", "any"), ("maskable", "maskable"))
        for size in (192, 512)
    ]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
