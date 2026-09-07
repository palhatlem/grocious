# grocious icon assets

The selected outline bag-g is reproduced as vector artwork for browser tabs and app icons.
The full header wordmark remains separate.

- grocious-icon.svg: scalable icon on a pale rounded background for light/dark browser chrome.
- favicon.ico: embedded 16, 24, 32, 48, 64, 128 and 256 px; served at /favicon.ico.
- grocious-icon-{size}.png: 16, 32, 48, 64, 128, 256, 512 and 1024 px.
- apple-touch-icon.png: opaque 180 px artwork; iOS applies the corner mask.
- grocious-pwa-{192,512}.png: ordinary app icons.
- grocious-maskable-{192,512}.png: opaque Android icons with the mark inside the safe circle.
- grocious-mask.svg: transparent monochrome artwork for Safari pinned tabs.
- grocious-pwa.svg: scalable counterpart for existing references.

Rebuild: install Pillow and CairoSVG in a development environment, then run
python scripts/build_icons.py. These are build tools, not application runtime dependencies.
Icon URLs use cache version 2. Existing installed shortcuts may need to be re-added to update their icon.
