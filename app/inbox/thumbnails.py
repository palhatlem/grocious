"""Disposable previews; originals remain checksum-verified archive documents."""

import io
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageOps
import receipt_archive as archive
from .extract import _command


def thumbnail(rid):
    r = archive.read_receipt("inbox", rid)
    doc = next((d for d in r["documents"] if d["role"] == "derived" and d["mimetype"].startswith("image/")), None)
    if doc is None:
        doc = next((d for d in r["documents"] if d["mimetype"] == "application/pdf"), None)
    if doc is None:
        raise FileNotFoundError()
    source, _ = archive.document("inbox", rid, doc["filename"])
    directory = archive.root().parent / "cache" / "thumbs"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = directory / (doc["sha256"] + "-v1.jpg")
    if target.exists():
        return target
    if doc["mimetype"] == "application/pdf":
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "page"
            _command(["pdftoppm", "-f", "1", "-singlefile", "-scale-to", "240", "-png", str(source), str(out)])
            content = out.with_suffix(".png").read_bytes()
    else:
        content = source.read_bytes()
    with Image.open(io.BytesIO(content)) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((180, 240))
        fd, name = tempfile.mkstemp(dir=directory, prefix=".pending-")
        try:
            with os.fdopen(fd, "wb") as handle:
                image.save(handle, "JPEG")
            os.replace(name, target)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    return target
