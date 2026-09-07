"""Inbox web routes. No remote URL fetching and no active mail/HTML rendering."""

import io
import json
from flask import Blueprint, abort, jsonify, redirect, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge
import receipt_archive as archive
import themes
from . import store
from .extract import MAX_BYTES
from .heuristics import CATEGORIES

bp = Blueprint("inbox", __name__)


def wants_json():
    return request.is_json or request.accept_mimetypes.best == "application/json"


def record(rid):
    try:
        return archive.read_receipt("inbox", rid)
    except (ValueError, FileNotFoundError):
        abort(404)


def context():
    import webgui

    return dict(themes=themes.load_themes(), demo=webgui.DEMO, categories=CATEGORIES)


@bp.errorhandler(ValueError)
def invalid(error):
    if wants_json():
        return jsonify(error=str(error)), 400
    return render_template("inbox_error.html", error=str(error), **context()), 400


@bp.errorhandler(RequestEntityTooLarge)
def too_large(error):
    return invalid(ValueError("Maksimalt 32 MB per fil og 10 filer per opplasting"))[0], 413


@bp.route("/inbox", methods=["GET", "POST"])
def queue():
    if request.method == "POST":
        files = request.files.getlist("files")
        if len(files) > 10:
            raise ValueError("Maksimalt 10 filer")
        payloads = [(f.read(MAX_BYTES + 1), f.filename or "receipt", f.mimetype) for f in files if f.filename]
        if not payloads:
            # Shared URLs are archived as text, NEVER fetched by the server.
            text = "\n".join(request.form.get(k, "") for k in ("title", "text", "url")).strip()
            if not text:
                raise ValueError("Velg en fil eller del tekst")
            payloads = [(text.encode(), "shared.txt", "text/plain")]
        if any(not b or len(b) > MAX_BYTES for b, _, _ in payloads):
            raise ValueError("Filen er tom eller større enn 32 MB")
        intake = dict(
            channel="share" if any(k in request.form for k in ("title", "text", "url")) else "upload",
            user_agent=request.user_agent.string[:500],
        )
        results = [store.ingest(data, name, mime, intake) for data, name, mime in payloads]
        if wants_json():
            return jsonify(results), 200 if all(r["duplicate"] for r in results) else 201
        return redirect("/inbox/" + results[0]["rid"] if len(results) == 1 else "/inbox?new=" + str(len(results)), 303)
    import webgui

    if webgui.DEMO and not webgui.app.testing:
        from .demo import seed

        seed()
    state = request.args.get("state", "needs_review")
    if state not in ("needs_review", "confirmed", "discarded", "linked", "all"):
        raise ValueError("Ugyldig filter")
    rows = archive.summary("inbox")["receipts"]
    rows = sorted(
        (r for r in rows if state == "all" or r.get("review", {}).get("state") == state),
        key=lambda r: r.get("intake", {}).get("received_at", ""),
        reverse=True,
    )
    return render_template("inbox_list.html", rows=rows, counts=store.summary(), state=state, **context())


@bp.get("/inbox/<rid>")
def detail(rid):
    r = record(rid)
    images = [d for d in r["documents"] if d["mimetype"] in ("image/jpeg", "image/png", "image/webp")]
    pdf = next((d for d in r["documents"] if d["mimetype"] == "application/pdf"), None)
    return render_template(
        "inbox_detail.html",
        r=r,
        images=images,
        pdf=pdf,
        lines_json=json.dumps(r["lines"], ensure_ascii=False),
        **context(),
    )


@bp.post("/inbox/<rid>/corrections")
def corrections(rid):
    record(rid)
    values = request.get_json() if request.is_json else request.form.to_dict()
    if not isinstance(values, dict):
        raise ValueError("Ugyldige korrigeringer")
    if isinstance(values.get("lines"), str):
        try:
            values["lines"] = json.loads(values["lines"])
        except ValueError as e:
            raise ValueError("Varelinjene må være gyldig JSON") from e
    store.correct(rid, values)
    return jsonify(record(rid)) if wants_json() else redirect("/inbox/" + rid, 303)


@bp.post("/inbox/<rid>/state")
def state(rid):
    record(rid)
    values = request.get_json() if request.is_json else request.form
    store.state(rid, values.get("state"))
    return jsonify(record(rid)) if wants_json() else redirect("/inbox/" + rid, 303)


@bp.get("/api/inbox/summary")
def summary():
    return jsonify(store.summary())


@bp.get("/inbox/<rid>.<fmt>")
def download(rid, fmt):
    r = record(rid)
    if fmt == "csv":
        return (
            archive.receipt_csv(r),
            200,
            {"Content-Type": "text/csv", "Content-Disposition": f"attachment;filename=inbox-{rid}.csv"},
        )
    if fmt == "pdf":
        doc = next((d for d in r["documents"] if d["mimetype"] == "application/pdf"), None)
        if doc:
            path, _ = archive.document("inbox", rid, doc["filename"])
            return send_file(path, mimetype="application/pdf", as_attachment=True)
        from reportlab.pdfgen.canvas import Canvas

        buf = io.BytesIO()
        pdf = Canvas(buf)
        for i, line in enumerate(
            [
                r.get("store") or "Ukjent butikk",
                r.get("date") or "Ukjent dato",
                "Generert kopi - se originalfil i arkivet",
            ]
            + [f"{l.get('name', '')}: {l.get('amount')}" for l in r["lines"]]
        ):
            if i and i % 40 == 0:
                pdf.showPage()
            pdf.drawString(30, 800 - (i % 40) * 18, line[:100])
        pdf.save()
        return send_file(
            io.BytesIO(buf.getvalue()), mimetype="application/pdf", as_attachment=True, download_name="laget-kopi.pdf"
        )
    from webgui import archived_download

    return archived_download("inbox", rid, fmt)


@bp.get("/inbox/<rid>/file/<filename>")
def file(rid, filename):
    record(rid)
    try:
        path, doc = archive.document("inbox", rid, filename)
    except (ValueError, FileNotFoundError):
        abort(404)
    inline = doc["mimetype"] in ("image/png", "image/jpeg", "image/webp", "application/pdf")
    response = send_file(path, mimetype=doc["mimetype"], as_attachment=not inline, download_name=filename)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
    response.headers["Cache-Control"] = "private, no-store"
    return response
