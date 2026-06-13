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
DEFAULT_FOLDER_NAME = "telegram文件和聊天记录"
DEEPSEEK_KEY = ZZLAB_ROOT / "Key/Qwen Key.txt"
MEMORY_KINDS = {"note", "file"}

SCRIPT_DIR = Path(__file__).resolve().parents[3] / "scripts/notebook_pipeline"
CHANNEL_SECTION = "Telegram Records"


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
    for path in sorted(root.glob("*/chat_records.jsonl")):
        person = path.parent.name
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            item["_person_folder"] = person
            records.append(item)
    return records


def read_text_extracts(records: list[dict[str, Any]], limit: int = 12000) -> str:
    parts = []
    remaining = limit
    for record in records:
        for file_item in record.get("files", []):
            text_path = file_item.get("text_extract")
            if not text_path:
                continue
            path = Path(text_path)
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if not text.strip():
                continue
            chunk = f"\n\n[TEXT FILE] {path.name}\n{text[:remaining]}"
            parts.append(chunk)
            remaining -= len(chunk)
            if remaining <= 0:
                return "".join(parts)
    return "".join(parts)


def compact_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for index, item in enumerate(records, start=1):
        files = [
            {
                "name": Path(file_item.get("path", "")).name,
                "path": file_item.get("path", ""),
                "mime_type": file_item.get("mime_type", ""),
                "text_preview": file_item.get("text_preview", ""),
            }
            for file_item in item.get("files", [])
        ]
        compact.append(
            {
                "id": f"telegram-{index}",
                "time": item.get("created_at"),
                "person": item.get("_person_folder"),
                "kind": item.get("kind"),
                "text": item.get("text", "")[:3000],
                "files": files,
            }
        )
    return compact


def record_attachments(records: list[dict[str, Any]]) -> list[str]:
    attachments = []
    seen = set()
    for item in records:
        for file_item in item.get("files", []):
            path = file_item.get("path", "")
            if path and path not in seen:
                seen.add(path)
                attachments.append(path)
    return attachments


def refresh_rag_index() -> dict[str, Any]:
    try:
        import rag_query_engine  # type: ignore

        return rag_query_engine.refresh_index_quietly()
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def render_html(day: date, root: Path, records: list[dict[str, Any]], output: Path) -> None:
    by_person: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_person.setdefault(record.get("_person_folder", "unknown"), []).append(record)
    sections = []
    for person, items in sorted(by_person.items()):
        entries = []
        for item in items:
            files = "".join(
                f"<li>{html.escape(Path(file_item.get('path', '')).name)} - {html.escape(file_item.get('mime_type', ''))}</li>"
                for file_item in item.get("files", [])
            )
            entries.append(
                "<article>"
                f"<h3>{html.escape(item.get('created_at', ''))} | {html.escape(item.get('kind', ''))}</h3>"
                f"<p>{html.escape(item.get('text', ''))}</p>"
                f"<ul>{files}</ul>"
                "</article>"
            )
        sections.append(f"<section><h2>{html.escape(person)}</h2>{''.join(entries)}</section>")
    body = f"""<!DOCTYPE html>
<html lang="zh-Hans">
<head>
  <meta charset="UTF-8">
  <title>Telegram Records {day.isoformat()}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; margin: 28px; line-height: 1.55; }}
    section {{ border-top: 1px solid #ddd; margin-top: 1rem; padding-top: 1rem; }}
    article {{ margin: 0.75rem 0; padding: 0.75rem; background: #f8f8f8; }}
  </style>
</head>
<body>
  <h1>Telegram Records {html.escape(day.isoformat())}</h1>
  <p>Source root: {html.escape(str(root))}</p>
  {''.join(sections) if sections else '<p>No Telegram records.</p>'}
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(body, encoding="utf-8")


def local_distill(day: date, records: list[dict[str, Any]]) -> dict[str, Any]:
    notes = [item.get("text", "") for item in records if item.get("kind") in {"note", "file"} and item.get("text")]
    queries = [item.get("text", "") for item in records if item.get("kind") == "query" and item.get("text")]
    file_count = sum(len(item.get("files", [])) for item in records)
    people = sorted({item.get("_person_folder", "unknown") for item in records})
    return {
        "one_sentence_summary": f"{day.isoformat()} Telegram records: {len(notes)} note/file text entries, {len(queries)} queries, {file_count} files.",
        "what_happened": notes[:20],
        "important_facts": notes[:20],
        "decisions_or_conclusions": [],
        "open_questions_or_next_steps": queries[:20],
        "people_organizations_equipment": people,
        "tags": ["telegram", "daily-record", day.isoformat()],
        "confidence_notes": ["Generated from Telegram chat records; non-text files are indexed by metadata only."],
    }


def deepseek_distill(day: date, records: list[dict[str, Any]], text_extracts: str) -> dict[str, Any]:
    try:
        import sys

        sys.path.insert(0, str(SCRIPT_DIR))
        import distill_html_with_deepseek as deepseek  # type: ignore

        key = deepseek.read_deepseek_key(DEEPSEEK_KEY)
        compact_records = [
            {
                "time": item.get("created_at"),
                "person": item.get("_person_folder"),
                "kind": item.get("kind"),
                "text": item.get("text", "")[:2000],
                "files": [
                    {
                        "name": Path(file_item.get("path", "")).name,
                        "mime_type": file_item.get("mime_type", ""),
                        "text_preview": file_item.get("text_preview", ""),
                    }
                    for file_item in item.get("files", [])
                ],
            }
            for item in records
        ]
        prompt = f"""
Return valid JSON only. Distill one day of ZZLab Telegram records into a compact lab-memory page.

Required keys:
- one_sentence_summary
- what_happened
- important_facts
- decisions_or_conclusions
- open_questions_or_next_steps
- people_organizations_equipment
- tags
- confidence_notes

Rules:
1. Use only the Telegram records and text extracts below.
2. Non-text files should be described by filename/type only.
3. Preserve experimental facts, dates, numbers, devices, and follow-ups.
4. Prefer Chinese unless source text is English-only.

Date: {day.isoformat()}
Records:
{json.dumps(compact_records, ensure_ascii=False)}

Text extracts from uploaded text files:
{text_extracts[:20000]}
"""
        distilled, _usage, _model = deepseek.call_deepseek(
            key,
            "qwen3.7-plus",
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
        fallback.setdefault("confidence_notes", []).append(f"Qwen digest failed; local fallback used: {type(exc).__name__}: {exc}")
        return fallback


def upsert_distillation(day: date, html_path: Path, records: list[dict[str, Any]], distilled: dict[str, Any]) -> None:
    data = read_json(DISTILLATION, {"sections": [], "usage": []})
    section_name = "Telegram Records"
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
                "section_summary": "Daily Telegram notes and uploaded-file metadata.",
                "main_topics": ["telegram records"],
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
        "title": f"Telegram Records {day.isoformat()}",
        "html": str(html_path),
        "source_sha256": "",
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "updated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "attachments": [file_item.get("path", "") for item in records for file_item in item.get("files", [])],
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
            "telegram_records_day": day.isoformat(),
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Distill daily Telegram records into lab memory.")
    parser.add_argument("--date", default="")
    parser.add_argument("--root", type=Path, default=ZZLAB_ROOT)
    parser.add_argument("--folder-name", default=DEFAULT_FOLDER_NAME)
    args = parser.parse_args()

    day = target_date(args.date)
    root = args.root / day.isoformat() / args.folder_name
    output = root / f"telegram_records_{day.isoformat()}.html"
    records = load_records(root) if root.exists() else []
    memory_records = [item for item in records if item.get("kind") in MEMORY_KINDS]
    render_html(day, root, records, output)
    topic_result = {"groups": 0, "pages": [], "removed_channel_page": False}
    if memory_records:
        import topic_distillation

        topic_result = topic_distillation.upsert_topic_supplements(
            source="telegram",
            day=day,
            html_path=output,
            compact_records=compact_records(memory_records),
            text_extracts=read_text_extracts(memory_records),
            attachments=record_attachments(memory_records),
            channel_section=CHANNEL_SECTION,
        )
    else:
        import topic_distillation

        topic_result = topic_distillation.upsert_topic_supplements(
            source="telegram",
            day=day,
            html_path=output,
            compact_records=[],
            text_extracts="",
            attachments=[],
            channel_section=CHANNEL_SECTION,
        )
    rag_index = refresh_rag_index()
    print(
        json.dumps(
            {
                "date": day.isoformat(),
                "records": len(records),
                "memory_records": len(memory_records),
                "html": str(output),
                "distilled": bool(memory_records),
                "topic_groups": topic_result.get("groups", 0),
                "topic_pages": topic_result.get("pages", []),
                "filtered_records": topic_result.get("filtered_records", []),
                "removed_channel_page": topic_result.get("removed_channel_page", False),
                "pruned_channel_section": topic_result.get("pruned_channel_section", False),
                "rag_index": {
                    "chunk_count": rag_index.get("chunk_count"),
                    "chunks_with_vectors": rag_index.get("chunks_with_vectors"),
                    "error": rag_index.get("error") or rag_index.get("embedding_error", ""),
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
