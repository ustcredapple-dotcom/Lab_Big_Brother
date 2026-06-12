from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any


ZZLAB_ROOT = Path("/Volumes/ZZLab_AI")
PROCESSING = ZZLAB_ROOT / "Document/Lab_Notebook_Processing"
DISTILLATION = PROCESSING / "html_deepseek_distilled/DEEPSEEK_DISTILLATION.json"
DISTILLATION_HTML = PROCESSING / "html_deepseek_distilled/DEEPSEEK_DISTILLATION.html"
DEEPSEEK_KEY = ZZLAB_ROOT / "Key/Deepseek Key.txt"
SCRIPT_DIR = Path(__file__).resolve().parents[3] / "scripts/notebook_pipeline"
CHANNEL_SECTIONS = {"Telegram Records", "Email Records"}
UNSORTED_SECTION = "Unsorted Communication Records"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def slugify(value: str, fallback: str = "general") -> str:
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"[^\w\u4e00-\u9fff .,+()-]+", "_", value)
    value = value.strip(" ._-")
    return value[:80] or fallback


def render_distillation_html(data: dict[str, Any]) -> None:
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        import distill_html_with_deepseek as deepseek  # type: ignore

        DISTILLATION_HTML.write_text(deepseek.render_html(data), encoding="utf-8")
    except Exception:
        pass


def section_directory(data: dict[str, Any]) -> list[dict[str, Any]]:
    directory = []
    for section in data.get("sections", []):
        name = section.get("section", "")
        if not name or name in CHANNEL_SECTIONS or name == UNSORTED_SECTION:
            continue
        distilled = section.get("distilled", {}) or {}
        pages = []
        for page in section.get("pages", [])[:25]:
            page_distilled = page.get("distilled", {}) or {}
            pages.append(
                {
                    "title": page.get("title", ""),
                    "summary": page_distilled.get("one_sentence_summary", ""),
                    "tags": as_list(page_distilled.get("tags"))[:8],
                }
            )
        directory.append(
            {
                "section": name,
                "page_count": section.get("page_count", len(section.get("pages", []))),
                "summary": distilled.get("section_summary", ""),
                "main_topics": as_list(distilled.get("main_topics"))[:12],
                "key_results": as_list(distilled.get("key_results"))[:12],
                "pages": pages,
            }
        )
    return directory


def local_group(source: str, day: date, compact_records: list[dict[str, Any]], attachments: list[str]) -> list[dict[str, Any]]:
    facts = []
    for record in compact_records[:30]:
        label = record.get("subject") or record.get("kind") or record.get("id")
        preview = record.get("text_preview") or record.get("text") or ""
        facts.append(f"{label}: {str(preview)[:500]}")
    return [
        {
            "section": UNSORTED_SECTION,
            "topic_title": f"{source.title()} supplement {day.isoformat()}",
            "record_ids": [record.get("id") for record in compact_records],
            "distilled": {
                "one_sentence_summary": f"{day.isoformat()} {source} records could not be confidently matched to an existing topic.",
                "what_happened": facts,
                "important_facts": facts,
                "decisions_or_conclusions": [],
                "open_questions_or_next_steps": [],
                "people_organizations_equipment": [],
                "tags": [source, "communication-supplement", day.isoformat(), "unsorted"],
                "confidence_notes": ["Local fallback used; no topic classification was available."],
                "important_assets_or_attachments": attachments[:40],
            },
        }
    ]


def classify_with_deepseek(
    source: str,
    day: date,
    data: dict[str, Any],
    compact_records: list[dict[str, Any]],
    text_extracts: str,
    attachments: list[str],
) -> list[dict[str, Any]]:
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        import distill_html_with_deepseek as deepseek  # type: ignore

        key = deepseek.read_deepseek_key(DEEPSEEK_KEY)
        directory = section_directory(data)
        prompt = f"""
Return valid JSON only. You are updating the ZZLab master notebook memory.

Task:
Classify these {source} records by laboratory topic, then distill each topic group as a supplemental notebook page.

Important policy:
- The source channel ({source}) is evidence provenance, not the archive topic.
- Do not create or choose "Email Records" or "Telegram Records" as a target section.
- If a record clearly supplements an existing section, put it in that section.
- If a record is administrative/noise or cannot be matched to a lab topic, use exactly "{UNSORTED_SECTION}".
- Preserve source paths, dates, names, numbers, device names, vendors, file names, and follow-ups.
- Do not invent facts. If relevance is weak, put it in "{UNSORTED_SECTION}".

Existing topic sections:
{json.dumps(directory, ensure_ascii=False)}

Input source: {source}
Input date: {day.isoformat()}
Input records:
{json.dumps(compact_records, ensure_ascii=False)}

Readable body/file extracts:
{text_extracts[:45000]}

Return JSON with this schema:
{{
  "groups": [
    {{
      "section": "one existing section name, or {UNSORTED_SECTION}",
      "topic_title": "short human topic title, not the source channel",
      "record_ids": ["ids included in this group"],
      "distilled": {{
        "one_sentence_summary": "...",
        "what_happened": ["..."],
        "important_facts": ["..."],
        "decisions_or_conclusions": ["..."],
        "open_questions_or_next_steps": ["..."],
        "people_organizations_equipment": ["..."],
        "tags": ["..."],
        "confidence_notes": ["..."],
        "important_assets_or_attachments": ["..."]
      }}
    }}
  ]
}}
"""
        result, _usage, _model = deepseek.call_deepseek(
            key,
            "deepseek-chat",
            [
                {"role": "system", "content": "You are a careful laboratory archivist. Always return JSON only."},
                {"role": "user", "content": prompt},
            ],
            timeout=180,
            retries=3,
        )
        groups = result.get("groups", [])
        if not isinstance(groups, list) or not groups:
            return local_group(source, day, compact_records, attachments)
        return groups
    except Exception as exc:
        groups = local_group(source, day, compact_records, attachments)
        groups[0]["distilled"].setdefault("confidence_notes", []).append(
            f"DeepSeek topic classification failed; local fallback used: {type(exc).__name__}: {exc}"
        )
        return groups


def ensure_section(data: dict[str, Any], section_name: str) -> dict[str, Any]:
    for section in data.setdefault("sections", []):
        if section.get("section") == section_name:
            return section
    section = {
        "section": section_name,
        "page_count": 0,
        "distilled": {
            "section_summary": "Communication records that could not yet be confidently matched to a specific notebook topic.",
            "main_topics": ["unsorted communication records"],
            "key_results": [],
            "important_assets_or_attachments": [],
            "people_and_responsibilities": [],
            "recommended_reading_order": [],
            "follow_up_items": [],
        },
        "pages": [],
    }
    data["sections"].append(section)
    return section


def valid_section_names(data: dict[str, Any]) -> set[str]:
    return {section.get("section", "") for section in data.get("sections", []) if section.get("section")} | {UNSORTED_SECTION}


def normalize_groups(data: dict[str, Any], source: str, day: date, groups: list[dict[str, Any]], compact_records: list[dict[str, Any]], attachments: list[str]) -> list[dict[str, Any]]:
    valid_sections = valid_section_names(data) - CHANNEL_SECTIONS
    valid_ids = {str(record.get("id")) for record in compact_records}
    normalized = []
    used_ids: set[str] = set()
    for group in groups:
        section = str(group.get("section") or UNSORTED_SECTION).strip()
        if section not in valid_sections:
            section = UNSORTED_SECTION
        record_ids = [str(item) for item in as_list(group.get("record_ids")) if str(item) in valid_ids]
        if not record_ids:
            continue
        used_ids.update(record_ids)
        distilled = group.get("distilled")
        if not isinstance(distilled, dict):
            distilled = {}
        distilled.setdefault("one_sentence_summary", f"{day.isoformat()} {source} supplemental records.")
        distilled.setdefault("what_happened", [])
        distilled.setdefault("important_facts", [])
        distilled.setdefault("decisions_or_conclusions", [])
        distilled.setdefault("open_questions_or_next_steps", [])
        distilled.setdefault("people_organizations_equipment", [])
        distilled.setdefault("tags", [])
        distilled.setdefault("confidence_notes", [])
        distilled.setdefault("important_assets_or_attachments", attachments[:40])
        tags = [str(item) for item in as_list(distilled.get("tags"))]
        for tag in [source, "communication-supplement", day.isoformat()]:
            if tag not in tags:
                tags.append(tag)
        distilled["tags"] = tags
        notes = [str(item) for item in as_list(distilled.get("confidence_notes"))]
        provenance = f"Supplement distilled from {source} records archived on {day.isoformat()}."
        if provenance not in notes:
            notes.append(provenance)
        distilled["confidence_notes"] = notes
        normalized.append(
            {
                "section": section,
                "topic_title": str(group.get("topic_title") or f"{source} supplement").strip(),
                "record_ids": record_ids,
                "distilled": distilled,
            }
        )
    missing_records = [record for record in compact_records if str(record.get("id")) not in used_ids]
    if missing_records:
        normalized.extend(local_group(source, day, missing_records, attachments))
    return normalized


def remove_channel_page(data: dict[str, Any], channel_section: str, day: date) -> bool:
    target_title = f"{channel_section} {day.isoformat()}"
    removed = False
    for section in data.get("sections", []):
        if section.get("section") != channel_section:
            continue
        pages = section.setdefault("pages", [])
        kept = [page for page in pages if page.get("title") != target_title]
        if len(kept) != len(pages):
            section["pages"] = kept
            section["page_count"] = len(kept)
            removed = True
    return removed


def prune_empty_channel_sections(data: dict[str, Any]) -> bool:
    sections = data.get("sections", [])
    kept = [
        section
        for section in sections
        if section.get("section") not in CHANNEL_SECTIONS or section.get("pages")
    ]
    if len(kept) == len(sections):
        return False
    data["sections"] = kept
    return True


def upsert_topic_supplements(
    *,
    source: str,
    day: date,
    html_path: Path,
    compact_records: list[dict[str, Any]],
    text_extracts: str,
    attachments: list[str],
    channel_section: str,
) -> dict[str, Any]:
    data = read_json(DISTILLATION, {"sections": [], "usage": []})
    removed_channel_page = remove_channel_page(data, channel_section, day)
    pruned_channel_section = prune_empty_channel_sections(data)
    if not compact_records:
        if removed_channel_page or pruned_channel_section:
            data["generated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            write_json(DISTILLATION, data)
            render_distillation_html(data)
        return {
            "groups": 0,
            "pages": [],
            "removed_channel_page": removed_channel_page,
            "pruned_channel_section": pruned_channel_section,
        }

    groups = classify_with_deepseek(source, day, data, compact_records, text_extracts, attachments)
    groups = normalize_groups(data, source, day, groups, compact_records, attachments)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    pages_written = []
    for index, group in enumerate(groups, start=1):
        section_name = group["section"]
        section = ensure_section(data, section_name)
        topic = slugify(group.get("topic_title", ""), "communication supplement")
        title = f"{topic} Supplement {day.isoformat()} [{source}]"
        page = {
            "section": section_name,
            "title": title,
            "html": str(html_path),
            "source_sha256": "",
            "created": now,
            "updated": now,
            "source_channel": source,
            "source_record_ids": group.get("record_ids", []),
            "attachments": attachments,
            "distilled": group["distilled"],
        }
        pages = section.setdefault("pages", [])
        for page_index, existing in enumerate(pages):
            if existing.get("title") == title:
                pages[page_index] = page
                break
        else:
            pages.append(page)
        pages.sort(key=lambda item: item.get("title", ""))
        section["page_count"] = len(pages)
        pages_written.append({"section": section_name, "title": title, "record_ids": group.get("record_ids", [])})

    data["generated_at"] = now
    data.setdefault("incremental_updates", []).append(
        {
            "detected_at": now,
            "source_channel": source,
            "records_day": day.isoformat(),
            "html": str(html_path),
            "records": len(compact_records),
            "topic_supplement_pages": pages_written,
            "removed_channel_page": removed_channel_page,
            "pruned_channel_section": pruned_channel_section,
        }
    )
    write_json(DISTILLATION, data)
    render_distillation_html(data)
    return {
        "groups": len(groups),
        "pages": pages_written,
        "removed_channel_page": removed_channel_page,
        "pruned_channel_section": pruned_channel_section,
    }
