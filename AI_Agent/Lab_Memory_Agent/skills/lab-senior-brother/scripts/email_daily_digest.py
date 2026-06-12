from __future__ import annotations

import argparse
import html
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


ZZLAB_ROOT = Path("/Volumes/ZZLab_AI")
PROCESSING = ZZLAB_ROOT / "Document/Lab_Notebook_Processing"
DISTILLATION = PROCESSING / "html_deepseek_distilled/DEEPSEEK_DISTILLATION.json"
DISTILLATION_HTML = PROCESSING / "html_deepseek_distilled/DEEPSEEK_DISTILLATION.html"
DEFAULT_FOLDER_NAME = "email文件和邮件记录"
DEEPSEEK_KEY = ZZLAB_ROOT / "Key/Deepseek Key.txt"
SCRIPT_DIR = Path(__file__).resolve().parents[3] / "scripts/notebook_pipeline"
CHANNEL_SECTION = "Email Records"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def target_date(value: str) -> date:
    if value:
        return date.fromisoformat(value)
    return datetime.now().astimezone().date() - timedelta(days=1)


def load_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(root.glob("*/email_records.jsonl")):
        sender = path.parent.name
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            item["_sender_folder"] = sender
            records.append(item)
    return records


def read_text_file(path_value: str, limit: int) -> str:
    if not path_value:
        return ""
    path = Path(path_value)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:limit]


def read_text_extracts(records: list[dict[str, Any]], limit: int = 40000) -> str:
    parts = []
    remaining = limit
    for record in records:
        body = read_text_file(record.get("body_text", ""), min(remaining, 8000))
        if body.strip():
            chunk = f"\n\n[EMAIL BODY] {record.get('subject', '')}\nFrom: {record.get('from', '')}\n{body}"
            parts.append(chunk[:remaining])
            remaining -= len(chunk)
        for attachment in record.get("attachments", []):
            extract = read_text_file(attachment.get("text_extract", ""), min(remaining, 10000))
            if not extract.strip():
                continue
            chunk = f"\n\n[ATTACHMENT TEXT] {attachment.get('filename', '')}\n{extract}"
            parts.append(chunk[:remaining])
            remaining -= len(chunk)
            if remaining <= 0:
                return "".join(parts)
        if remaining <= 0:
            break
    return "".join(parts)


def compact_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for index, item in enumerate(records, start=1):
        attachments = [
            {
                "filename": attachment.get("filename"),
                "path": attachment.get("path"),
                "mime_type": attachment.get("mime_type"),
                "text_preview": attachment.get("text_preview", ""),
            }
            for attachment in item.get("attachments", [])
        ]
        compact.append(
            {
                "id": f"email-{index}",
                "date": item.get("date"),
                "sender": item.get("from"),
                "subject": item.get("subject"),
                "text_preview": (item.get("text_preview") or "")[:3000],
                "html_preview": item.get("html_preview"),
                "attachments": attachments,
            }
        )
    return compact


def record_attachments(records: list[dict[str, Any]]) -> list[str]:
    attachments = []
    seen = set()
    for item in records:
        for attachment in item.get("attachments", []):
            path = attachment.get("path", "")
            if path and path not in seen:
                seen.add(path)
                attachments.append(path)
    return attachments


def render_html(day: date, root: Path, records: list[dict[str, Any]], output: Path) -> None:
    by_sender: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_sender.setdefault(record.get("_sender_folder", "unknown"), []).append(record)
    sections = []
    for sender, items in sorted(by_sender.items()):
        entries = []
        for item in items:
            attachments = "".join(
                f"<li>{html.escape(attachment.get('filename', ''))} - {html.escape(attachment.get('mime_type', ''))}</li>"
                for attachment in item.get("attachments", [])
            )
            entries.append(
                "<article>"
                f"<h3>{html.escape(item.get('date', ''))} | {html.escape(item.get('subject') or '(no subject)')}</h3>"
                f"<p><strong>From:</strong> {html.escape(item.get('from', ''))}</p>"
                f"<p>{html.escape(item.get('text_preview', ''))}</p>"
                f"<p><a href=\"{html.escape(item.get('html_preview', ''))}\">Readable email HTML</a></p>"
                f"<ul>{attachments}</ul>"
                "</article>"
            )
        sections.append(f"<section><h2>{html.escape(sender)}</h2>{''.join(entries)}</section>")
    body = f"""<!DOCTYPE html>
<html lang="zh-Hans">
<head>
  <meta charset="UTF-8">
  <title>Email Records {day.isoformat()}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; margin: 28px; line-height: 1.55; }}
    section {{ border-top: 1px solid #ddd; margin-top: 1rem; padding-top: 1rem; }}
    article {{ margin: 0.75rem 0; padding: 0.75rem; background: #f8f8f8; }}
  </style>
</head>
<body>
  <h1>Email Records {html.escape(day.isoformat())}</h1>
  <p>Source root: {html.escape(str(root))}</p>
  {''.join(sections) if sections else '<p>No email records.</p>'}
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(body, encoding="utf-8")


def local_distill(day: date, records: list[dict[str, Any]]) -> dict[str, Any]:
    facts = []
    attachments = []
    for record in records:
        subject = record.get("subject") or "(no subject)"
        sender = record.get("from") or record.get("_sender_folder", "unknown")
        preview = (record.get("text_preview") or "").strip()
        facts.append(f"{day.isoformat()} email from {sender}: {subject}. {preview[:500]}")
        for attachment in record.get("attachments", []):
            attachments.append(f"{attachment.get('filename')} ({attachment.get('mime_type')})")
    return {
        "one_sentence_summary": f"{day.isoformat()} email records: {len(records)} archived messages.",
        "what_happened": facts[:20],
        "important_facts": facts[:20],
        "decisions_or_conclusions": [],
        "open_questions_or_next_steps": [],
        "people_organizations_equipment": sorted({record.get("_sender_folder", "unknown") for record in records}),
        "tags": ["email", "gmail", "daily-record", day.isoformat()],
        "confidence_notes": ["Generated from archived Gmail records; binary attachments are indexed by metadata only."],
        "important_assets_or_attachments": attachments[:40],
    }


def deepseek_distill(day: date, records: list[dict[str, Any]], text_extracts: str) -> dict[str, Any]:
    try:
        import sys

        sys.path.insert(0, str(SCRIPT_DIR))
        import distill_html_with_deepseek as deepseek  # type: ignore

        key = deepseek.read_deepseek_key(DEEPSEEK_KEY)
        compact_records = [
            {
                "date": item.get("date"),
                "sender": item.get("from"),
                "subject": item.get("subject"),
                "text_preview": (item.get("text_preview") or "")[:2000],
                "html_preview": item.get("html_preview"),
                "attachments": [
                    {
                        "filename": attachment.get("filename"),
                        "mime_type": attachment.get("mime_type"),
                        "text_preview": attachment.get("text_preview", ""),
                    }
                    for attachment in item.get("attachments", [])
                ],
            }
            for item in records
        ]
        prompt = f"""
Return valid JSON only. Distill one day of ZZLab forwarded Gmail records into a compact lab-memory page.

Required keys:
- one_sentence_summary
- what_happened
- important_facts
- decisions_or_conclusions
- open_questions_or_next_steps
- people_organizations_equipment
- tags
- confidence_notes
- important_assets_or_attachments

Rules:
1. Use only the email records and text extracts below.
2. Preserve experimental facts, dates, numbers, devices, senders, vendors, purchase details, file names, and follow-ups.
3. If a message is just a forwarded source, focus on the forwarded content, not mail transport boilerplate.
4. Non-text files should be described by filename/type only.
5. Prefer Chinese unless source text is English-only.

Date: {day.isoformat()}
Email records:
{json.dumps(compact_records, ensure_ascii=False)}

Text extracts from email bodies and readable attachments:
{text_extracts[:40000]}
"""
        distilled, _usage, _model = deepseek.call_deepseek(
            key,
            "deepseek-chat",
            [
                {"role": "system", "content": "You are a careful laboratory archivist. Always return JSON only."},
                {"role": "user", "content": prompt},
            ],
            timeout=180,
            retries=3,
        )
        return distilled
    except Exception as exc:
        fallback = local_distill(day, records)
        fallback.setdefault("confidence_notes", []).append(f"DeepSeek digest failed; local fallback used: {type(exc).__name__}: {exc}")
        return fallback


def upsert_distillation(day: date, html_path: Path, records: list[dict[str, Any]], distilled: dict[str, Any]) -> None:
    data = read_json(DISTILLATION, {"sections": [], "usage": []})
    section_name = "Email Records"
    section = None
    for item in data.setdefault("sections", []):
        if item.get("section") == section_name:
            section = item
            break
    if section is None:
        section = {
            "section": section_name,
            "page_count": 0,
            "distilled": {
                "section_summary": "Daily forwarded Gmail records and attachment metadata.",
                "main_topics": ["email records", "gmail"],
                "key_results": [],
                "important_assets_or_attachments": [],
                "people_and_responsibilities": [],
                "recommended_reading_order": [],
                "follow_up_items": [],
            },
            "pages": [],
        }
        data["sections"].append(section)
    page = {
        "section": section_name,
        "title": f"Email Records {day.isoformat()}",
        "html": str(html_path),
        "source_sha256": "",
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "updated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "attachments": [attachment.get("path", "") for item in records for attachment in item.get("attachments", [])],
        "distilled": distilled,
    }
    pages = section.setdefault("pages", [])
    for index, existing in enumerate(pages):
        if existing.get("title") == page["title"]:
            pages[index] = page
            break
    else:
        pages.append(page)
    pages.sort(key=lambda item: item.get("title", ""))
    section["page_count"] = len(pages)
    data["generated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    data.setdefault("incremental_updates", []).append(
        {
            "detected_at": data["generated_at"],
            "email_records_day": day.isoformat(),
            "html": str(html_path),
            "records": len(records),
        }
    )
    write_json(DISTILLATION, data)
    try:
        import sys

        sys.path.insert(0, str(SCRIPT_DIR))
        import distill_html_with_deepseek as deepseek  # type: ignore

        DISTILLATION_HTML.write_text(deepseek.render_html(data), encoding="utf-8")
    except Exception:
        pass


def remove_distillation_page(day: date) -> bool:
    if not DISTILLATION.exists():
        return False
    data = read_json(DISTILLATION, {"sections": []})
    section_name = "Email Records"
    target_title = f"Email Records {day.isoformat()}"
    removed = False
    for section in data.get("sections", []):
        if section.get("section") != section_name:
            continue
        pages = section.setdefault("pages", [])
        kept = [page for page in pages if page.get("title") != target_title]
        if len(kept) != len(pages):
            section["pages"] = kept
            section["page_count"] = len(kept)
            removed = True
    if not removed:
        return False
    data["generated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    data.setdefault("incremental_updates", []).append(
        {
            "detected_at": data["generated_at"],
            "email_records_day": day.isoformat(),
            "records": 0,
            "action": "removed_empty_email_records_page",
        }
    )
    write_json(DISTILLATION, data)
    try:
        import sys

        sys.path.insert(0, str(SCRIPT_DIR))
        import distill_html_with_deepseek as deepseek  # type: ignore

        DISTILLATION_HTML.write_text(deepseek.render_html(data), encoding="utf-8")
    except Exception:
        pass
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Distill daily Gmail records into lab memory.")
    parser.add_argument("--date", default="")
    parser.add_argument("--root", type=Path, default=ZZLAB_ROOT)
    parser.add_argument("--folder-name", default=DEFAULT_FOLDER_NAME)
    args = parser.parse_args()

    day = target_date(args.date)
    root = args.root / day.isoformat() / args.folder_name
    output = root / f"email_records_{day.isoformat()}.html"
    records = load_records(root) if root.exists() else []
    render_html(day, root, records, output)
    topic_result = {"groups": 0, "pages": [], "removed_channel_page": False}
    if records:
        import topic_distillation

        topic_result = topic_distillation.upsert_topic_supplements(
            source="email",
            day=day,
            html_path=output,
            compact_records=compact_records(records),
            text_extracts=read_text_extracts(records),
            attachments=record_attachments(records),
            channel_section=CHANNEL_SECTION,
        )
    else:
        import topic_distillation

        topic_result = topic_distillation.upsert_topic_supplements(
            source="email",
            day=day,
            html_path=output,
            compact_records=[],
            text_extracts="",
            attachments=[],
            channel_section=CHANNEL_SECTION,
        )
    print(
        json.dumps(
            {
                "date": day.isoformat(),
                "records": len(records),
                "html": str(output),
                "distilled": bool(records),
                "topic_groups": topic_result.get("groups", 0),
                "topic_pages": topic_result.get("pages", []),
                "removed_channel_page": topic_result.get("removed_channel_page", False),
                "pruned_channel_section": topic_result.get("pruned_channel_section", False),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
