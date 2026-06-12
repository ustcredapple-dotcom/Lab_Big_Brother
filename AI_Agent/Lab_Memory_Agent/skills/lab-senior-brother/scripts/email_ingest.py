from __future__ import annotations

import argparse
import email.utils
import fcntl
import hashlib
import html
import imaplib
import json
import mimetypes
import re
import sys
from datetime import datetime
from email import policy
from email.message import EmailMessage, Message
from pathlib import Path
from typing import Any


ZZLAB_ROOT = Path("/Volumes/ZZLab_AI")
PROCESSING = ZZLAB_ROOT / "Document/Lab_Notebook_Processing"
DEFAULT_CONFIG = PROCESSING / "email_ingest_config.json"
DEFAULT_STATE = PROCESSING / "email_ingest_state.json"
DEFAULT_PASSWORD_FILE = ZZLAB_ROOT / "Key/gmail_app_password.txt"
DEFAULT_DAILY_ROOT = ZZLAB_ROOT
DEFAULT_FOLDER_NAME = "email文件和邮件记录"
DEFAULT_EMAIL = "ultracoldhku@gmail.com"

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".htm",
    ".log",
    ".ini",
    ".cfg",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_config() -> dict[str, Any]:
    return {
        "email_address": DEFAULT_EMAIL,
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "mailbox": "INBOX",
        "password_file": str(DEFAULT_PASSWORD_FILE),
        "daily_root": str(DEFAULT_DAILY_ROOT),
        "email_folder_name": DEFAULT_FOLDER_NAME,
        "state_file": str(DEFAULT_STATE),
        "only_unseen": True,
        "max_messages_per_run": 50,
        "mark_seen_after_archive": False,
        "ignored_senders": [
            "google-noreply@google.com",
            "no-reply@accounts.google.com",
            "no-reply@google.com",
        ],
    }


def load_config(path: Path) -> dict[str, Any]:
    config = default_config()
    if path.exists():
        config.update(read_json(path, {}))
    else:
        write_json(path, config)
    return config


def read_password(path: Path) -> str | None:
    if not path.exists():
        return None
    password = path.read_text(encoding="utf-8").strip().replace(" ", "")
    return password or None


def slugify(value: str, fallback: str = "unknown") -> str:
    value = value.strip().lower()
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"[^a-z0-9._@+-]+", "_", value)
    value = value.strip("._-")
    return value[:80] or fallback


def safe_filename(value: str, fallback: str) -> str:
    name = Path(value or fallback).name.strip()
    name = re.sub(r"[\x00-\x1f/\\:]+", "_", name)
    name = name.strip(" .")
    return name[:160] or fallback


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_addresses(value: str | None) -> str:
    if not value:
        return ""
    return ", ".join(email.utils.formataddr(pair) for pair in email.utils.getaddresses([value]))


def first_email_address(value: str | None) -> str:
    if not value:
        return ""
    pairs = email.utils.getaddresses([value])
    if not pairs:
        return value.strip().casefold()
    return (pairs[0][1] or pairs[0][0]).strip().casefold()


def sender_folder_name(message: Message) -> str:
    pairs = email.utils.getaddresses([str(message.get("from", ""))])
    if pairs:
        name, address = pairs[0]
        return slugify(address or name, "unknown_sender")
    return "unknown_sender"


def message_datetime(message: Message) -> datetime:
    raw = str(message.get("date", ""))
    parsed = email.utils.parsedate_to_datetime(raw) if raw else None
    if parsed is None:
        return datetime.now().astimezone()
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed.astimezone()


def get_body_parts(message: Message) -> tuple[str, str]:
    text_parts: list[str] = []
    html_parts: list[str] = []
    if isinstance(message, EmailMessage):
        text_body = message.get_body(preferencelist=("plain",))
        html_body = message.get_body(preferencelist=("html",))
        if text_body and not text_body.get_content_disposition():
            text_parts.append(str(text_body.get_content()))
        if html_body and not html_body.get_content_disposition():
            html_parts.append(str(html_body.get_content()))
    if not text_parts and not html_parts:
        for part in message.walk() if message.is_multipart() else [message]:
            if part.get_content_disposition() == "attachment":
                continue
            content_type = part.get_content_type()
            try:
                payload = part.get_content()
            except Exception:
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    payload = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            if content_type == "text/plain":
                text_parts.append(str(payload))
            elif content_type == "text/html":
                html_parts.append(str(payload))
    return "\n\n".join(p.strip() for p in text_parts if p.strip()), "\n\n".join(p.strip() for p in html_parts if p.strip())


def html_to_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw_html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_text_like(path: Path, mime_type: str) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    return mime_type.startswith("text/") or mime_type in {
        "application/json",
        "application/xml",
        "application/xhtml+xml",
        "application/x-yaml",
    }


def extract_pdf_text(path: Path, limit: int = 50000) -> str:
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        parts = []
        remaining = limit
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                continue
            chunk = f"\n\n[page {index}]\n{text.strip()}"
            parts.append(chunk[:remaining])
            remaining -= len(chunk)
            if remaining <= 0:
                break
        return "".join(parts).strip()
    except Exception as exc:
        return f"[PDF text extraction failed: {type(exc).__name__}: {exc}]"


def extract_attachment_text(path: Path, mime_type: str) -> str:
    if path.suffix.lower() == ".pdf" or mime_type == "application/pdf":
        return extract_pdf_text(path)
    if is_text_like(path, mime_type):
        return path.read_text(encoding="utf-8", errors="replace")[:50000]
    return ""


def render_record_html(record: dict[str, Any], body_text: str, body_html: str, output: Path) -> None:
    attachments = "".join(
        "<li>"
        f"{html.escape(item.get('filename', ''))} "
        f"({html.escape(item.get('mime_type', ''))}, {item.get('size', 0)} bytes)"
        "</li>"
        for item in record.get("attachments", [])
    )
    body_section = body_html if body_html.strip() else f"<pre>{html.escape(body_text)}</pre>"
    page = f"""<!DOCTYPE html>
<html lang="zh-Hans">
<head>
  <meta charset="UTF-8">
  <title>{html.escape(record.get("subject") or "Email Record")}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; margin: 28px; line-height: 1.55; }}
    header {{ border-bottom: 1px solid #ddd; margin-bottom: 1rem; padding-bottom: 1rem; }}
    dt {{ font-weight: 650; }}
    dd {{ margin: 0 0 0.45rem 0; }}
    .body {{ border-top: 1px solid #ddd; margin-top: 1rem; padding-top: 1rem; }}
    pre {{ white-space: pre-wrap; background: #f7f7f7; padding: 1rem; }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(record.get("subject") or "(no subject)")}</h1>
    <dl>
      <dt>From</dt><dd>{html.escape(record.get("from", ""))}</dd>
      <dt>To</dt><dd>{html.escape(record.get("to", ""))}</dd>
      <dt>Date</dt><dd>{html.escape(record.get("date", ""))}</dd>
      <dt>Message-ID</dt><dd>{html.escape(record.get("message_id", ""))}</dd>
    </dl>
  </header>
  <h2>Attachments</h2>
  <ul>{attachments or "<li>No attachments</li>"}</ul>
  <section class="body">{body_section}</section>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_markdown(path: Path, record: dict[str, Any]) -> None:
    attachments = "\n".join(f"- {item.get('filename')} ({item.get('mime_type')})" for item in record.get("attachments", []))
    section = f"""## {record.get("created_at", "")} | {record.get("subject") or "(no subject)"}

- From: {record.get("from", "")}
- To: {record.get("to", "")}
- Date: {record.get("date", "")}
- Message-ID: {record.get("message_id", "")}
- HTML: {record.get("html_preview", "")}

Attachments:
{attachments or "- None"}

Text preview:

```text
{(record.get("text_preview") or "")[:2000]}
```

"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(section)


def archive_message(uid: str, raw_bytes: bytes, config: dict[str, Any]) -> dict[str, Any]:
    message = email.message_from_bytes(raw_bytes, policy=policy.default)
    dt = message_datetime(message)
    day_root = Path(config.get("daily_root") or str(DEFAULT_DAILY_ROOT)) / dt.date().isoformat()
    sender_root = day_root / (config.get("email_folder_name") or DEFAULT_FOLDER_NAME) / sender_folder_name(message)
    raw_root = sender_root / "raw_eml"
    body_root = sender_root / "bodies"
    html_root = sender_root / "email_html"
    attachment_root = sender_root / "attachments"
    extract_root = sender_root / "text_extracts"
    for folder in [raw_root, body_root, html_root, attachment_root, extract_root]:
        folder.mkdir(parents=True, exist_ok=True)

    message_id = str(message.get("message-id", "")).strip()
    subject = str(message.get("subject", "")).strip()
    digest = sha256_bytes(raw_bytes)[:12]
    stem = safe_filename(f"{dt.strftime('%H%M%S')}_{slugify(subject, 'no_subject')}_{digest}", f"email_{digest}")
    raw_path = raw_root / f"{stem}.eml"
    raw_path.write_bytes(raw_bytes)

    body_text, body_html = get_body_parts(message)
    if not body_text and body_html:
        body_text = html_to_text(body_html)
    body_text_path = body_root / f"{stem}.txt"
    body_html_path = body_root / f"{stem}_original.html"
    body_text_path.write_text(body_text, encoding="utf-8")
    if body_html:
        body_html_path.write_text(body_html, encoding="utf-8")

    attachments: list[dict[str, Any]] = []
    for index, part in enumerate(message.iter_attachments() if isinstance(message, EmailMessage) else [], start=1):
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        filename = safe_filename(part.get_filename() or f"attachment_{index}", f"attachment_{index}")
        destination = attachment_root / filename
        if destination.exists():
            destination = attachment_root / f"{Path(filename).stem}_{digest}{Path(filename).suffix}"
        destination.write_bytes(payload)
        mime_type = part.get_content_type() or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        extract_text = extract_attachment_text(destination, mime_type)
        extract_path = ""
        text_preview = ""
        if extract_text.strip():
            extract_path_obj = extract_root / f"{destination.name}.txt"
            extract_path_obj.write_text(extract_text, encoding="utf-8")
            extract_path = str(extract_path_obj)
            text_preview = extract_text[:1200]
        attachments.append(
            {
                "filename": filename,
                "path": str(destination),
                "mime_type": mime_type,
                "size": len(payload),
                "sha256": sha256_bytes(payload),
                "text_extract": extract_path,
                "text_preview": text_preview,
            }
        )

    record = {
        "kind": "email",
        "uid": uid,
        "created_at": now_iso(),
        "date": dt.isoformat(timespec="seconds"),
        "from": normalize_addresses(str(message.get("from", ""))),
        "to": normalize_addresses(str(message.get("to", ""))),
        "cc": normalize_addresses(str(message.get("cc", ""))),
        "subject": subject,
        "message_id": message_id,
        "raw_eml": str(raw_path),
        "body_text": str(body_text_path),
        "body_html": str(body_html_path) if body_html else "",
        "text_preview": body_text[:2000],
        "attachments": attachments,
    }
    preview_path = html_root / f"{stem}.html"
    record["html_preview"] = str(preview_path)
    render_record_html(record, body_text, body_html, preview_path)
    append_jsonl(sender_root / "email_records.jsonl", record)
    append_markdown(sender_root / "email_records.md", record)
    return record


def fetch_candidate_uids(connection: imaplib.IMAP4_SSL, config: dict[str, Any]) -> list[str]:
    criterion = "UNSEEN" if config.get("only_unseen", True) else "ALL"
    status, data = connection.uid("search", None, criterion)
    if status != "OK":
        raise RuntimeError(f"IMAP search failed: {status} {data!r}")
    uids = data[0].decode().split() if data and data[0] else []
    max_messages = int(config.get("max_messages_per_run") or 50)
    return uids[-max_messages:]


def ingest(config_path: Path, dry_run: bool = False) -> dict[str, Any]:
    config = load_config(config_path)
    password_file = Path(config.get("password_file") or str(DEFAULT_PASSWORD_FILE))
    password = read_password(password_file)
    if not password:
        return {
            "skipped": True,
            "reason": "missing_password_file",
            "password_file": str(password_file),
            "config": str(config_path),
        }

    state_path = Path(config.get("state_file") or str(DEFAULT_STATE))
    state = read_json(state_path, {"processed_uids": [], "processed_message_ids": []})
    processed_uids = set(str(item) for item in state.get("processed_uids", []))
    processed_message_ids = set(str(item) for item in state.get("processed_message_ids", []))

    archived: list[dict[str, Any]] = []
    ignored = 0
    ignored_senders = {str(item).strip().casefold() for item in config.get("ignored_senders", []) if str(item).strip()}
    email_address = config.get("email_address") or DEFAULT_EMAIL
    with imaplib.IMAP4_SSL(config.get("imap_host", "imap.gmail.com"), int(config.get("imap_port", 993))) as connection:
        connection.login(email_address, password)
        connection.select(config.get("mailbox", "INBOX"))
        for uid in fetch_candidate_uids(connection, config):
            if uid in processed_uids:
                continue
            status, data = connection.uid("fetch", uid, "(BODY.PEEK[] FLAGS)")
            if status != "OK" or not data:
                continue
            raw = b""
            for item in data:
                if isinstance(item, tuple) and item[1]:
                    raw = item[1]
                    break
            if not raw:
                continue
            message = email.message_from_bytes(raw, policy=policy.default)
            message_id = str(message.get("message-id", "")).strip()
            sender_address = first_email_address(str(message.get("from", "")))
            if sender_address in ignored_senders:
                ignored += 1
                processed_uids.add(uid)
                if message_id:
                    processed_message_ids.add(message_id)
                continue
            if message_id and message_id in processed_message_ids:
                processed_uids.add(uid)
                continue
            if dry_run:
                archived.append({"uid": uid, "subject": str(message.get("subject", "")), "message_id": message_id})
            else:
                record = archive_message(uid, raw, config)
                archived.append(record)
            processed_uids.add(uid)
            if message_id:
                processed_message_ids.add(message_id)
            if config.get("mark_seen_after_archive") and not dry_run:
                connection.uid("store", uid, "+FLAGS", "(\\Seen)")

    state["processed_uids"] = sorted(processed_uids, key=lambda item: (0, int(item)) if item.isdigit() else (1, item))[-5000:]
    state["processed_message_ids"] = sorted(processed_message_ids)[-5000:]
    state["updated_at"] = now_iso()
    if not dry_run:
        write_json(state_path, state)
    return {"skipped": False, "archived": len(archived), "ignored": ignored, "records": archived}


def ingest_with_lock(config_path: Path, dry_run: bool = False) -> dict[str, Any]:
    config = load_config(config_path)
    state_path = Path(config.get("state_file") or str(DEFAULT_STATE))
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"skipped": True, "reason": "already_running"}
        return ingest(config_path, dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive new Gmail messages for ZZLab Big Brother.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(ingest_with_lock(args.config, args.dry_run), ensure_ascii=False, default=str))
    except imaplib.IMAP4.error as exc:
        print(json.dumps({"skipped": True, "reason": "imap_auth_or_access_error", "error": str(exc)}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
