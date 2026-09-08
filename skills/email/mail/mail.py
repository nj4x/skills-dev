#!/usr/bin/env python3
"""
mail.py — IMAP/SMTP CLI for Claude Code's mail skill.

Credentials are loaded from ~/.claude/skills/mail/.env (preferred) then
the process environment. Never pass secrets on the command line.

All output is JSON on stdout. Errors: {"error":..,"detail":..} + exit 1.
Stderr is reserved for unexpected tracebacks.
"""
import argparse
import email
import email.utils
import imaplib
import json
import os
import re
import smtplib
import socket
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html.parser import HTMLParser
from pathlib import Path

# ---------------------------------------------------------------------------
# Credential loading
# ---------------------------------------------------------------------------

_SKILL_DIR = Path(__file__).parent
_ENV_FILE = _SKILL_DIR / ".env"


def _load_dotenv():
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _creds():
    _load_dotenv()
    missing = [v for v in ("MAIL_USER", "MAIL_PASSWORD", "MAIL_IMAP_HOST", "MAIL_SMTP_HOST") if not os.environ.get(v)]
    if missing:
        _exit_error("missing_credentials", f"Required env vars not set: {', '.join(missing)}. Run setup-check for details.")
    return {
        "user": os.environ["MAIL_USER"],
        "password": os.environ["MAIL_PASSWORD"],
        "imap_host": os.environ["MAIL_IMAP_HOST"],
        "imap_port": int(os.environ.get("MAIL_IMAP_PORT", 993)),
        "smtp_host": os.environ["MAIL_SMTP_HOST"],
        "smtp_port": int(os.environ.get("MAIL_SMTP_PORT", 465)),
        # SSL auto-detect: 993/465 → SSL, 587 → STARTTLS, anything else → plain
        "imap_ssl": os.environ.get("MAIL_IMAP_SSL", "").lower() not in ("false", "0", "no")
                    if "MAIL_IMAP_SSL" in os.environ
                    else int(os.environ.get("MAIL_IMAP_PORT", 993)) == 993,
        "imap_starttls": os.environ.get("MAIL_IMAP_STARTTLS", "").lower() in ("true", "1", "yes"),
        "smtp_ssl": os.environ.get("MAIL_SMTP_SSL", "").lower() not in ("false", "0", "no")
                    if "MAIL_SMTP_SSL" in os.environ
                    else int(os.environ.get("MAIL_SMTP_PORT", 465)) == 465,
    }


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _out(data):
    print(json.dumps(data, ensure_ascii=False, default=str))


def _exit_error(error, detail=""):
    _out({"error": error, "detail": detail})
    sys.exit(1)


# ---------------------------------------------------------------------------
# IMAP connection
# ---------------------------------------------------------------------------

def _imap_connect(c):
    try:
        if c["imap_ssl"]:
            conn = imaplib.IMAP4_SSL(c["imap_host"], c["imap_port"])
        else:
            conn = imaplib.IMAP4(c["imap_host"], c["imap_port"])
            if c.get("imap_starttls"):
                conn.starttls()
        conn.login(c["user"], c["password"])
        return conn
    except imaplib.IMAP4.error as e:
        _exit_error("imap_auth_failed", str(e))
    except (socket.gaierror, OSError) as e:
        _exit_error("imap_connect_failed", str(e))


def _imap_select(conn, folder):
    typ, data = conn.select(f'"{folder}"')
    if typ != "OK":
        _exit_error("folder_not_found", f'Could not SELECT folder "{folder}": {data}')


# ---------------------------------------------------------------------------
# ENVELOPE parsing
# ---------------------------------------------------------------------------

def _parse_addr(addr_tuple):
    if not addr_tuple:
        return ""
    parts = []
    for a in addr_tuple:
        name = a[2] or b""
        mailbox = a[2] or b""
        host = a[3] or b""
        if isinstance(mailbox, bytes):
            mailbox = mailbox.decode("utf-8", "replace")
        if isinstance(host, bytes):
            host = host.decode("utf-8", "replace")
        if isinstance(name, bytes):
            name = name.decode("utf-8", "replace")
        full = f"{mailbox}@{host}" if host else mailbox
        parts.append(full)
    return ", ".join(parts)


def _decode_header_field(raw):
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    decoded, enc = email.header.decode_header(raw)[0]
    if isinstance(decoded, bytes):
        return decoded.decode(enc or "utf-8", "replace")
    return decoded


# ---------------------------------------------------------------------------
# HTML → plain text
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False
        if tag in ("p", "br", "div", "tr"):
            self._parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)

    def get_text(self):
        return "".join(self._parts)


def _html_to_text(html_bytes, charset="utf-8"):
    try:
        html = html_bytes.decode(charset, "replace")
    except Exception:
        html = html_bytes.decode("utf-8", "replace")
    p = _TextExtractor()
    p.feed(html)
    return p.get_text()


# ---------------------------------------------------------------------------
# Subcommand: list
# ---------------------------------------------------------------------------

def cmd_list(args):
    c = _creds()
    conn = _imap_connect(c)
    _imap_select(conn, args.folder)

    filt = args.filter or "unread"
    if filt == "unread":
        criteria = "UNSEEN"
    elif filt == "all":
        criteria = "ALL"
    elif filt.startswith("from:"):
        addr = filt[5:]
        criteria = f'FROM "{addr}"'
    elif filt.startswith("subject:"):
        subj = filt[8:]
        criteria = f'SUBJECT "{subj}"'
    else:
        criteria = "ALL"

    typ, data = conn.uid("SEARCH", None, criteria)
    if typ != "OK":
        _exit_error("search_failed", str(data))

    uid_list = data[0].split() if data[0] else []
    if getattr(args, "newest_first", False):
        uid_list = list(reversed(uid_list))
    # apply offset and limit
    uid_list = uid_list[args.offset:]
    uid_list = uid_list[:args.limit]

    if not uid_list:
        _out([])
        conn.logout()
        return

    uid_str = b",".join(uid_list)
    fetch_cmd = "(FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS (DATE FROM TO SUBJECT)])"
    typ, fetch_data = conn.uid("FETCH", uid_str, fetch_cmd)
    if typ != "OK":
        _exit_error("fetch_failed", str(fetch_data))

    # Response alternates: tuple(meta_bytes, header_bytes), bytes(' UID XXXXX)')
    results = []
    i = 0
    while i < len(fetch_data):
        item = fetch_data[i]
        i += 1
        if not isinstance(item, tuple):
            continue
        meta_str = item[0].decode("utf-8", "replace") if isinstance(item[0], bytes) else str(item[0])
        header_bytes = item[1] if isinstance(item[1], bytes) else b""

        # UID is in the trailing bytes item that follows this tuple
        uid_val = ""
        if i < len(fetch_data) and isinstance(fetch_data[i], bytes):
            trailer = fetch_data[i].decode("utf-8", "replace")
            uid_match = re.search(r"UID (\d+)", trailer)
            if uid_match:
                uid_val = uid_match.group(1)
            i += 1
        # fallback: try the meta string
        if not uid_val:
            uid_match = re.search(r"UID (\d+)", meta_str)
            uid_val = uid_match.group(1) if uid_match else ""

        size_match = re.search(r"RFC822\.SIZE (\d+)", meta_str)
        flags_match = re.search(r"FLAGS \(([^)]*)\)", meta_str)
        size_val = int(size_match.group(1)) if size_match else 0
        flags_val = flags_match.group(1).split() if flags_match else []

        msg = email.message_from_bytes(header_bytes)
        results.append({
            "uid": uid_val,
            "folder": args.folder,
            "date": str(msg.get("Date", "")),
            "from": str(msg.get("From", "")),
            "to": str(msg.get("To", "")),
            "subject": _decode_header_field(msg.get("Subject", "")),
            "size": size_val,
            "flags": flags_val,
        })

    conn.logout()
    _out(results)


# ---------------------------------------------------------------------------
# Subcommand: read
# ---------------------------------------------------------------------------

class _FetchError(Exception):
    """Raised by _read_single when a UID cannot be fetched."""


def _read_single(conn, uid, folder, text_only):
    """Fetch and parse one message by UID. Returns a dict; raises _FetchError on failure."""
    typ, data = conn.uid("FETCH", uid.encode(), "(RFC822)")
    if typ != "OK" or not data or data == [None] or not isinstance(data[0], tuple):
        raise _FetchError(
            f"Could not fetch UID {uid} from folder '{folder}'. "
            "If the message was moved, retry with --folder <folder>.",
        )

    raw = data[0][1]
    msg = email.message_from_bytes(raw)

    body_plain = []
    body_html = []
    attachments = []

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                fname = part.get_filename() or "unknown"
                try:
                    payload = part.get_payload(decode=True) or b""
                except Exception:
                    payload = b""
                attachments.append({"filename": fname, "size": len(payload)})
            elif ct == "text/plain":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                body_plain.append(payload.decode(charset, "replace"))
            elif ct == "text/html":
                # Always extract HTML→text; --text-only only controls the preference
                # order, not whether HTML is parsed (avoids empty body on HTML-only mail).
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                body_html.append(_html_to_text(payload, charset))
    else:
        ct = msg.get_content_type()
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        if ct == "text/plain":
            body_plain.append(payload.decode(charset, "replace"))
        elif ct == "text/html":
            body_html.append(_html_to_text(payload, charset))

    body = "\n\n".join(body_plain) if body_plain else "\n\n".join(body_html)

    return {
        "uid": uid,
        "from": str(msg.get("From", "")),
        "to": str(msg.get("To", "")),
        "cc": str(msg.get("Cc", "")),
        "subject": _decode_header_field(msg.get("Subject", "")),
        "date": str(msg.get("Date", "")),
        "message_id": str(msg.get("Message-ID", "")),
        "body": body,
        "attachments": attachments,
    }


def cmd_read(args):
    c = _creds()
    conn = _imap_connect(c)
    _imap_select(conn, args.folder)

    if len(args.uids) == 1:
        try:
            result = _read_single(conn, args.uids[0], args.folder, args.text_only)
        except _FetchError as e:
            conn.logout()
            _exit_error("fetch_failed", str(e))
            return
        conn.logout()
        _out(result)
    else:
        results = []
        for uid in args.uids:
            try:
                results.append(_read_single(conn, uid, args.folder, args.text_only))
            except _FetchError as e:
                results.append({"uid": uid, "error": "fetch_failed", "detail": str(e)})
        conn.logout()
        _out(results)


# ---------------------------------------------------------------------------
# Subcommand: send
# ---------------------------------------------------------------------------

_ADDR_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def cmd_send(args):
    c = _creds()

    to_addr = args.to.strip()
    if not _ADDR_RE.search(to_addr):
        _exit_error("invalid_address", f'"{to_addr}" does not look like a valid email address.')

    subject = args.subject or ""
    body = args.body or ""
    in_reply_to = ""
    references = ""

    if args.reply_to_uid:
        conn = _imap_connect(c)
        folder = args.folder or "INBOX"
        _imap_select(conn, folder)
        typ, data = conn.uid("FETCH", args.reply_to_uid.encode(), "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID REFERENCES SUBJECT)])")
        if typ == "OK" and data and isinstance(data[0], tuple):
            orig = email.message_from_bytes(data[0][1])
            orig_mid = str(orig.get("Message-ID", "")).strip()
            orig_refs = str(orig.get("References", "")).strip()
            orig_subj = _decode_header_field(orig.get("Subject", ""))
            if orig_mid:
                in_reply_to = orig_mid
                references = (orig_refs + " " + orig_mid).strip() if orig_refs else orig_mid
            if not subject:
                subject = orig_subj if orig_subj.lower().startswith("re:") else f"Re: {orig_subj}"
        conn.logout()

    msg = MIMEMultipart("alternative")
    msg["From"] = c["user"]
    msg["To"] = to_addr
    if args.cc:
        msg["Cc"] = args.cc
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references

    msg.attach(MIMEText(body, "plain", "utf-8"))

    recipients = [to_addr] + ([args.cc] if args.cc else [])

    try:
        if c["smtp_ssl"]:
            server = smtplib.SMTP_SSL(c["smtp_host"], c["smtp_port"], timeout=30)
        else:
            server = smtplib.SMTP(c["smtp_host"], c["smtp_port"], timeout=30)
            server.ehlo()
            server.starttls()
            server.ehlo()
        server.login(c["user"], c["password"])
        server.sendmail(c["user"], recipients, msg.as_string())
        mid = msg.get("Message-ID", "")
        server.quit()
    except smtplib.SMTPException as e:
        _exit_error("smtp_error", str(e))
    except (socket.gaierror, OSError) as e:
        _exit_error("smtp_connect_failed", str(e))

    _out({"status": "sent", "to": to_addr, "subject": subject, "message_id": mid})


# ---------------------------------------------------------------------------
# Subcommand: move
# ---------------------------------------------------------------------------

def cmd_move(args):
    c = _creds()
    conn = _imap_connect(c)
    _imap_select(conn, args.folder)

    uid = args.uid.encode()
    target = args.target_folder

    typ, data = conn.uid("COPY", uid, f'"{target}"')
    if typ != "OK":
        _exit_error("move_failed", f'COPY to "{target}" failed: {data}. Check that the folder exists (run: folders).')

    typ2, data2 = conn.uid("STORE", uid, "+FLAGS", r"(\Deleted)")
    if typ2 != "OK":
        conn.logout()
        _out({"status": "partial", "uid": args.uid, "to": target,
              "detail": "Copied to target but could not set \\Deleted on source."})
        return

    conn.expunge()
    conn.logout()
    _out({"status": "moved", "uid": args.uid, "from": args.folder, "to": target})


# ---------------------------------------------------------------------------
# Subcommand: flag
# ---------------------------------------------------------------------------

def cmd_flag(args):
    c = _creds()
    conn = _imap_connect(c)
    _imap_select(conn, args.folder)

    uid = args.uid.encode()
    action = args.action

    warning = None
    if action == "read":
        conn.uid("STORE", uid, "+FLAGS", r"(\Seen)")
    elif action == "unread":
        conn.uid("STORE", uid, "-FLAGS", r"(\Seen)")
    elif action == "star":
        conn.uid("STORE", uid, "+FLAGS", r"(\Flagged)")
    elif action == "delete":
        warning = "Message will be permanently deleted (EXPUNGE). Prefer move to Trash if you want recovery."
        conn.uid("STORE", uid, "+FLAGS", r"(\Deleted)")
        conn.expunge()
    else:
        conn.logout()
        _exit_error("unknown_action", f'Unknown flag action "{action}". Use: read, unread, star, delete.')

    conn.logout()
    result = {"status": "ok", "uid": args.uid, "action": action}
    if warning:
        result["warning"] = warning
    _out(result)


# ---------------------------------------------------------------------------
# Subcommand: folders
# ---------------------------------------------------------------------------

def cmd_folders(args):
    c = _creds()
    conn = _imap_connect(c)
    typ, data = conn.list('""', '"*"')
    conn.logout()
    if typ != "OK":
        _exit_error("list_failed", str(data))

    folders = []
    for item in data:
        if not item:
            continue
        if isinstance(item, bytes):
            item = item.decode("utf-8", "replace")
        # Format: (\HasNoChildren) "/" "INBOX"
        m = re.search(r'"([^"]+)"\s*$|(\S+)\s*$', item)
        if m:
            folders.append(m.group(1) or m.group(2))

    _out(folders)


# ---------------------------------------------------------------------------
# Subcommand: setup-check
# ---------------------------------------------------------------------------

def cmd_setup_check(args):
    _load_dotenv()
    report = {}
    missing = [v for v in ("MAIL_USER", "MAIL_PASSWORD", "MAIL_IMAP_HOST", "MAIL_SMTP_HOST") if not os.environ.get(v)]
    report["env_file_found"] = _ENV_FILE.exists()
    report["missing_vars"] = missing

    if missing:
        _out({"status": "error", **report, "detail": f"Set missing vars in {_ENV_FILE} or environment."})
        sys.exit(1)

    c = _creds()
    report["user"] = c["user"]

    # IMAP check
    try:
        if c["imap_ssl"]:
            _conn = imaplib.IMAP4_SSL(c["imap_host"], c["imap_port"])
        else:
            _conn = imaplib.IMAP4(c["imap_host"], c["imap_port"])
            if c.get("imap_starttls"):
                _conn.starttls()
        _conn.login(c["user"], c["password"])
        _conn.noop()
        _conn.logout()
        report["imap"] = "ok"
    except Exception as e:
        report["imap"] = f"error: {e}"

    # SMTP check
    try:
        if c["smtp_ssl"]:
            s = smtplib.SMTP_SSL(c["smtp_host"], c["smtp_port"], timeout=15)
        else:
            s = smtplib.SMTP(c["smtp_host"], c["smtp_port"], timeout=15)
            s.ehlo()
            s.starttls()
            s.ehlo()
        s.login(c["user"], c["password"])
        s.quit()
        report["smtp"] = "ok"
    except Exception as e:
        report["smtp"] = f"error: {e}"

    ok = report["imap"] == "ok" and report["smtp"] == "ok"
    report["status"] = "ok" if ok else "error"
    _out(report)
    if not ok:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(description="IMAP/SMTP CLI for Claude Code's mail skill.")
    sub = p.add_subparsers(dest="cmd", required=True)

    # list
    ls = sub.add_parser("list", help="List messages")
    ls.add_argument("--folder", default="INBOX")
    ls.add_argument("--filter", default="unread",
                    help="unread | all | from:ADDR | subject:TEXT")
    ls.add_argument("--limit", type=int, default=20)
    ls.add_argument("--offset", type=int, default=0)
    ls.add_argument("--newest-first", action="store_true",
                    help="Return most recent messages first")
    ls.set_defaults(func=cmd_list)

    # read
    rd = sub.add_parser("read", help="Read one or more messages by UID")
    rd.add_argument("uids", nargs="+", metavar="uid",
                    help="One or more UIDs; outputs a JSON array when more than one is given")
    rd.add_argument("--folder", default="INBOX")
    rd.add_argument("--text-only", action="store_true",
                    help="Prefer plain text; falls back to HTML-extracted text if no plain part")
    rd.set_defaults(func=cmd_read)

    # send
    sn = sub.add_parser("send", help="Send a message")
    sn.add_argument("--to", required=True)
    sn.add_argument("--cc", default="")
    sn.add_argument("--subject", default="")
    sn.add_argument("--body", default="")
    sn.add_argument("--reply-to-uid", default="")
    sn.add_argument("--folder", default="INBOX",
                    help="Source folder when fetching original for reply")
    sn.set_defaults(func=cmd_send)

    # move
    mv = sub.add_parser("move", help="Move a message to another folder")
    mv.add_argument("uid")
    mv.add_argument("target_folder")
    mv.add_argument("--folder", default="INBOX")
    mv.set_defaults(func=cmd_move)

    # flag
    fl = sub.add_parser("flag", help="Flag/unflag a message")
    fl.add_argument("uid")
    fl.add_argument("action", choices=["read", "unread", "star", "delete"])
    fl.add_argument("--folder", default="INBOX")
    fl.set_defaults(func=cmd_flag)

    # folders
    fo = sub.add_parser("folders", help="List all folders")
    fo.set_defaults(func=cmd_folders)

    # setup-check
    sc = sub.add_parser("setup-check", help="Validate credentials and connectivity")
    sc.set_defaults(func=cmd_setup_check)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
