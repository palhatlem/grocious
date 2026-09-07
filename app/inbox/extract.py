"""Bounded extraction; HTML and e-mail are rendered as inert plain text."""

import io
import os
import subprocess
import tempfile
from email import policy
from email.parser import BytesParser
from pathlib import Path

MAX_BYTES = 32 * 1024 * 1024
MAX_PAGES = 20
MAX_PIXELS = 40000000


def _command(args):
    try:
        return subprocess.run(args, check=True, capture_output=True, timeout=45).stdout
    except (OSError, subprocess.SubprocessError) as e:
        raise ValueError("Kunne ikke lese PDF-filen") from e


def extract(data, filename, mimetype=""):
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Filen er tom eller større enn 32 MB")
    suffix = Path(filename).suffix.lower()
    text, children, derived = "", [], []
    engine, kind = "none", "text"
    if data.startswith(b"%PDF-"):
        mime, ext = "application/pdf", "pdf"
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "input.pdf"
            src.write_bytes(data)
            info = _command(["pdfinfo", str(src)]).decode(errors="replace")
            pages = next((int(l.split(":")[1]) for l in info.splitlines() if l.startswith("Pages:")), 1)
            if pages > MAX_PAGES:
                raise ValueError("Maksimalt 20 PDF-sider per fil")
            text = _command(["pdftotext", "-layout", str(src), "-"]).decode(errors="replace")
            kind, engine = ("pdf-text", "pdftotext") if len(text.strip()) >= 40 * pages else ("pdf-scan", "none")
            if kind == "pdf-scan":
                _command(["pdftoppm", "-scale-to", "2000", "-png", str(src), str(Path(tmp) / "page")])
                derived.extend((p.read_bytes(), "png", "image/png") for p in sorted(Path(tmp).glob("page-*.png")))
    elif suffix == ".eml" or mimetype == "message/rfc822":
        mime, ext, kind = "message/rfc822", "eml", "eml"
        msg = BytesParser(policy=policy.default).parsebytes(data)
        body = msg.get_body(preferencelist=("plain", "html"))
        if body:
            text = body.get_content()
            if body.get_content_type() == "text/html":
                import html2text

                text = html2text.html2text(text)
        for part in msg.walk():
            if part.is_multipart() or not part.get_filename():
                continue
            payload = part.get_payload(decode=True)
            if payload:
                children.append((payload, part.get_filename(), part.get_content_type()))
        if len(children) > 10 or sum(len(c[0]) for c in children) > MAX_BYTES:
            raise ValueError("For mange eller for store e-postvedlegg")
    elif suffix in (".html", ".htm") or mimetype == "text/html":
        import html2text

        mime, ext, kind, engine = "text/html", "html", "html", "html2text"
        text = html2text.html2text(data.decode("utf-8", errors="replace"))
    elif suffix == ".txt" or mimetype == "text/plain":
        mime, ext = "text/plain", "txt"
        text = data.decode("utf-8", errors="replace")
    else:
        from PIL import Image, ImageOps
        import pillow_heif

        pillow_heif.register_heif_opener()
        Image.MAX_IMAGE_PIXELS = MAX_PIXELS
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.width * image.height > MAX_PIXELS:
                    raise ValueError("Bildet er for stort")
                fmt = image.format
                if fmt not in ("JPEG", "PNG", "WEBP", "HEIF"):
                    raise ValueError("Bildeformatet støttes ikke")
                mime, ext = {
                    "JPEG": ("image/jpeg", "jpg"),
                    "PNG": ("image/png", "png"),
                    "WEBP": ("image/webp", "webp"),
                    "HEIF": ("image/heic", "heic"),
                }[fmt]
                image = ImageOps.exif_transpose(image).convert("RGB")
                image.thumbnail((int(os.getenv("GROCIOUS_LLM_MAX_IMAGE_PX", "2000")),) * 2)
                out = io.BytesIO()
                image.save(out, "JPEG", quality=90)
                derived.append((out.getvalue(), "jpg", "image/jpeg"))
        except (OSError, Image.DecompressionBombError) as e:
            raise ValueError("Ugyldig bilde eller filformat") from e
        kind = "image"
    if len(text) > 200000:
        raise ValueError("For mye tekst i filen")
    return dict(text=text, children=children, derived=derived, mimetype=mime, extension=ext, kind=kind, engine=engine)
