"""Long-running IMAP IDLE intake. No scheduler and no web authentication bypass."""

import logging
import os
import ssl
import time
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr

import receipt_archive as archive
from . import store

log = logging.getLogger("inbox-mail")


def status(**updates):
    import json

    path = archive.root() / "inbox" / "mail_status.json"
    previous = json.loads(path.read_text()) if path.exists() else {"errors": 0}
    archive.atomic_json(path, {**previous, **updates})


def process_message(client, uid, raw):
    """Archive first, move only after all attachments are durably ingested."""
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    sender = parseaddr(msg.get("From", ""))[1]
    try:
        result = store.ingest(
            raw,
            "message.eml",
            "message/rfc822",
            {"channel": "mail", "sender": sender, "sender_domain": sender.rpartition("@")[2]},
        )
    except (ValueError, OSError):
        client.move([uid], os.getenv("IMAP_FAILED", "Grocious/Failed"))
        raise
    client.move([uid], os.getenv("IMAP_DONE", "Grocious/Done"))
    status(last_ingest=store.now())
    return result


def session():
    from imapclient import IMAPClient

    security = os.getenv("IMAP_SECURITY", "starttls")
    if security not in ("starttls", "ssl", "none"):
        raise ValueError("Invalid IMAP_SECURITY")
    context = ssl.create_default_context()
    if os.getenv("TLS_VERIFY", "1") == "0":
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    with IMAPClient(
        os.environ["IMAP_HOST"],
        port=int(os.getenv("IMAP_PORT", "1143")),
        ssl=security == "ssl",
        ssl_context=context,
        timeout=60,
    ) as client:
        if security == "starttls":
            client.starttls(context)
        client.login(os.environ["IMAP_USER"], os.environ["IMAP_PASSWORD"])
        for folder in (
            os.getenv("IMAP_FOLDER", "Grocious/Inbox"),
            os.getenv("IMAP_DONE", "Grocious/Done"),
            os.getenv("IMAP_FAILED", "Grocious/Failed"),
        ):
            if not client.folder_exists(folder):
                client.create_folder(folder)
        client.select_folder(os.getenv("IMAP_FOLDER", "Grocious/Inbox"))
        status(connected=True, last_seen=store.now())
        while True:
            for uid in client.search(["ALL"]):
                try:
                    payload = client.fetch([uid], ["BODY.PEEK[]"])[uid][b"BODY[]"]
                    process_message(client, uid, payload)
                except ValueError:
                    log.warning("Message rejected; retained in failed folder")
            client.idle()
            try:
                client.idle_check(timeout=min(int(os.getenv("IMAP_IDLE_TIMEOUT", "1500")), 1500))
            finally:
                client.idle_done()
            status(connected=True, last_seen=store.now())


def main():
    logging.basicConfig(level=logging.INFO)
    failures = 0
    while True:
        try:
            session()
            failures = 0
        except Exception:
            failures += 1
            status(connected=False, errors=failures, last_seen=store.now())
            log.warning("IMAP disconnected; reconnecting (attempt %d)", failures)
            time.sleep(min(300, 2 ** min(failures, 8)))


if __name__ == "__main__":
    main()
