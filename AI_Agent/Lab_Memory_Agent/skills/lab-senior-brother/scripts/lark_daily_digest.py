from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


ZZLAB_ROOT = Path("/Volumes/ZZLab_AI")
DEFAULT_FOLDER_NAME = "lark文档和消息记录"
DEFAULT_CONFIG = ZZLAB_ROOT / "Document/Lab_Notebook_Processing/lark_bot_config.json"
MEMORY_KINDS = {"chat", "note", "file"}
CHANNEL_SECTION = "Lark Records"

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import topic_distillation  # noqa: E402


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


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


def read_text_extracts(records: list[dict[str, Any]], limit: int = 16000) -> str:
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
                "id": f"lark-{index}",
                "time": item.get("created_at"),
                "person": item.get("_person_folder"),
                "kind": item.get("kind"),
                "chat_id": item.get("chat_id"),
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
  <title>Lark Records {day.isoformat()}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; margin: 28px; line-height: 1.55; }}
    section {{ border-top: 1px solid #ddd; margin-top: 1rem; padding-top: 1rem; }}
    article {{ margin: 0.75rem 0; padding: 0.75rem; background: #f8f8f8; }}
  </style>
</head>
<body>
  <h1>Lark Records {html.escape(day.isoformat())}</h1>
  <p>Source root: {html.escape(str(root))}</p>
  {''.join(sections) if sections else '<p>No Lark records.</p>'}
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(body, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Distill daily Lark records into topic-first lab memory.")
    parser.add_argument("--date", default="")
    parser.add_argument("--root", type=Path, default=ZZLAB_ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--folder-name", default="")
    args = parser.parse_args()

    config = read_json(args.config, {})
    day = target_date(args.date)
    folder_name = args.folder_name or config.get("lark_folder_name") or DEFAULT_FOLDER_NAME
    memory_kinds = set(config.get("digest_memory_kinds") or sorted(MEMORY_KINDS))
    root = args.root / day.isoformat() / folder_name
    output = root / f"lark_records_{day.isoformat()}.html"
    records = load_records(root) if root.exists() else []
    memory_records = [item for item in records if item.get("kind") in memory_kinds]
    render_html(day, root, records, output)
    topic_result = topic_distillation.upsert_topic_supplements(
        source="lark",
        day=day,
        html_path=output,
        compact_records=compact_records(memory_records),
        text_extracts=read_text_extracts(memory_records),
        attachments=record_attachments(memory_records),
        channel_section=CHANNEL_SECTION,
    )
    print(
        json.dumps(
            {
                "date": day.isoformat(),
                "records": len(records),
                "memory_records": len(memory_records),
                "html": str(output),
                "topic_groups": topic_result.get("groups", 0),
                "topic_pages": topic_result.get("pages", []),
                "filtered_records": topic_result.get("filtered_records", []),
                "removed_channel_page": topic_result.get("removed_channel_page", False),
                "pruned_channel_section": topic_result.get("pruned_channel_section", False),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
