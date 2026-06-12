from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ZZLAB_ROOT = Path("/Volumes/ZZLab_AI")
OUT_DIR = ZZLAB_ROOT / "Document/Lab_Big_Brother_Self_Documentation"
DISTILLATION = ZZLAB_ROOT / "Document/Lab_Notebook_Processing/html_deepseek_distilled/DEEPSEEK_DISTILLATION.json"
DISTILLATION_HTML = ZZLAB_ROOT / "Document/Lab_Notebook_Processing/html_deepseek_distilled/DEEPSEEK_DISTILLATION.html"
PIPELINE_DIR = ZZLAB_ROOT / "AI_Agent/Lab_Memory_Agent/scripts/notebook_pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import distill_html_with_deepseek as render_support  # type: ignore  # noqa: E402
import llm_provider  # type: ignore  # noqa: E402


SHARED_FILES = [
    "README.md",
    "AGENTS.md",
    "PROJECT_HANDOFF.md",
    "Document/AI_Agent_Migration_2026-06-11/conversation_records/WORK_LOG.md",
    "AI_Agent/Lab_Memory_Agent/manifest.yaml",
    "AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/SKILL.md",
    "AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/references/data_sources.md",
    "AI_Agent/Lab_Memory_Agent/scripts/notebook_pipeline/README.md",
    "AI_Agent/Lab_Memory_Agent/scripts/notebook_pipeline/llm_provider.py",
    "AI_Agent/Lab_Memory_Agent/scripts/notebook_pipeline/distill_html_with_deepseek.py",
    "AI_Agent/Lab_Memory_Agent/scripts/notebook_pipeline/daily_notebook_update.py",
    "AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/query_lab_notebook.py",
    "AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/serve_lab_senior_brother.py",
    "AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/telegram_lab_senior_brother.py",
    "AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/telegram_daily_digest.py",
    "AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/email_ingest.py",
    "AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/email_daily_digest.py",
    "AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/topic_distillation.py",
    "AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/update_self_knowledge.py",
    "AI_Agent/Lab_Memory_Agent/skills/auto-handoff/SKILL.md",
    "AI_Agent/Lab_Memory_Agent/skills/auto-handoff/scripts/update_handoff.py",
    "AI_Agent/Lab_Memory_Agent/skills/auto-handoff/scripts/sync_github.py",
    "AI_Agent/Lab_Memory_Agent/config/gmail_email_ingest.example.json",
]

LOCAL_FILES = [
    Path("/Users/wjj/Library/LaunchAgents/com.zzlab.lab-senior-brother-telegram.plist"),
    Path("/Users/wjj/Library/LaunchAgents/com.zzlab.email-ingest.plist"),
    Path("/Users/wjj/Library/LaunchAgents/com.zzlab.email-daily-digest.plist"),
    Path("/Users/wjj/Library/LaunchAgents/com.zzlab.lab-notebook-daily-update.plist"),
    Path("/Users/wjj/Library/LaunchAgents/com.zzlab.telegram-daily-digest.plist"),
]

MAX_FILE_CHARS = 18000
MAX_TOTAL_CHARS = 125000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_for_prompt(path: Path, rel: str) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if rel.endswith("WORK_LOG.md") and len(text) > MAX_FILE_CHARS:
        return "[TRUNCATED: latest work-log tail only]\n" + text[-MAX_FILE_CHARS:]
    if len(text) > MAX_FILE_CHARS:
        return text[:MAX_FILE_CHARS] + f"\n\n[TRUNCATED after {MAX_FILE_CHARS} chars]"
    return text


def collect_sources(root: Path) -> tuple[list[dict[str, Any]], str]:
    manifest = []
    blocks = []
    total = 0
    for rel in SHARED_FILES:
        path = root / rel
        if not path.exists():
            continue
        text = read_for_prompt(path, rel)
        if total + len(text) > MAX_TOTAL_CHARS:
            text = text[: max(0, MAX_TOTAL_CHARS - total)] + "\n\n[TRUNCATED by total prompt budget]"
        manifest.append(
            {
                "path": rel,
                "sha256": sha256(path),
                "chars": path.stat().st_size,
                "included_chars": len(text),
                "source_kind": "shared_project_file",
            }
        )
        blocks.append(f"\n\n===== FILE: {rel} =====\n{text}")
        total += len(text)
        if total >= MAX_TOTAL_CHARS:
            break
    for path in LOCAL_FILES:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")[:6000]
        manifest.append(
            {
                "path": str(path),
                "sha256": sha256(path),
                "chars": path.stat().st_size,
                "included_chars": len(text),
                "source_kind": "local_runtime_file",
            }
        )
        blocks.append(f"\n\n===== LOCAL RUNTIME FILE: {path} =====\n{text}")
    return manifest, "".join(blocks)


def as_items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value:
        return [str(value)]
    return []


def markdown_doc(distilled: dict[str, Any], manifest: list[dict[str, Any]], generated_at: str, model: str) -> str:
    sections = [
        ("这是什么", "what_it_is"),
        ("设计原则", "design_principles"),
        ("当前能力", "current_capabilities"),
        ("用户入口", "user_interfaces"),
        ("数据源与记忆", "data_sources_and_memory"),
        ("摄取与消化流程", "ingestion_and_digest_workflows"),
        ("AI Provider 与模型", "ai_provider_and_models"),
        ("自动化与服务", "automation_and_services"),
        ("重要路径", "important_paths"),
        ("关键脚本职责", "key_scripts_and_responsibilities"),
        ("安全与隐私边界", "safety_and_privacy_boundaries"),
        ("怎么使用", "how_to_use"),
        ("怎么维护", "how_to_maintain"),
        ("已知限制", "known_limitations"),
        ("下一步", "next_steps"),
        ("自我查询示例", "self_query_examples"),
    ]
    lines = [
        "# 实验室大师兄自我说明书",
        "",
        f"- Generated at: {generated_at}",
        f"- Model: {model}",
        f"- Source files: {len(manifest)}",
        "",
        "## 一句话总结",
        "",
        str(distilled.get("one_sentence_summary", "")).strip(),
    ]
    for title, key in sections:
        lines.extend(["", f"## {title}", ""])
        values = as_items(distilled.get(key))
        lines.extend([f"- {item}" for item in values] or ["- No item recorded."])
    lines.extend(["", "## 来源清单", ""])
    for item in manifest:
        lines.append(f"- `{item['path']}` ({item['source_kind']}, included {item['included_chars']} chars)")
    return "\n".join(lines) + "\n"


def html_doc(distilled: dict[str, Any], manifest: list[dict[str, Any]], generated_at: str, model: str) -> str:
    sections = [
        ("这是什么", "what_it_is"),
        ("设计原则", "design_principles"),
        ("当前能力", "current_capabilities"),
        ("用户入口", "user_interfaces"),
        ("数据源与记忆", "data_sources_and_memory"),
        ("摄取与消化流程", "ingestion_and_digest_workflows"),
        ("AI Provider 与模型", "ai_provider_and_models"),
        ("自动化与服务", "automation_and_services"),
        ("重要路径", "important_paths"),
        ("关键脚本职责", "key_scripts_and_responsibilities"),
        ("安全与隐私边界", "safety_and_privacy_boundaries"),
        ("怎么使用", "how_to_use"),
        ("怎么维护", "how_to_maintain"),
        ("已知限制", "known_limitations"),
        ("下一步", "next_steps"),
        ("自我查询示例", "self_query_examples"),
    ]
    body_sections = []
    for title, key in sections:
        items = as_items(distilled.get(key))
        lis = "".join(f"<li>{html.escape(item)}</li>" for item in items) or "<li>No item recorded.</li>"
        body_sections.append(f"<section><h2>{html.escape(title)}</h2><ul>{lis}</ul></section>")
    manifest_lis = "".join(
        f"<li><code>{html.escape(item['path'])}</code> ({html.escape(item['source_kind'])}, included {item['included_chars']} chars)</li>"
        for item in manifest
    )
    return f"""<!DOCTYPE html>
<html lang="zh-Hans">
<head>
  <meta charset="UTF-8">
  <title>实验室大师兄自我说明书</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; margin: 28px; line-height: 1.6; max-width: 1100px; }}
    section {{ border-top: 1px solid #ddd; padding-top: 1rem; margin-top: 1rem; }}
    code {{ background: #f6f8fa; padding: 0.1rem 0.25rem; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>实验室大师兄自我说明书</h1>
  <p><b>Generated at:</b> {html.escape(generated_at)}<br><b>Model:</b> {html.escape(model)}<br><b>Source files:</b> {len(manifest)}</p>
  <section><h2>一句话总结</h2><p>{html.escape(str(distilled.get("one_sentence_summary", "")))}</p></section>
  {''.join(body_sections)}
  <section><h2>来源清单</h2><ul>{manifest_lis}</ul></section>
</body>
</html>
"""


def upsert_distillation(html_path: Path, md_path: Path, json_path: Path, manifest_path: Path, distilled: dict[str, Any], generated_at: str) -> None:
    data = json.loads(DISTILLATION.read_text(encoding="utf-8")) if DISTILLATION.exists() else {"sections": []}
    section_name = "Lab Big Brother System"
    section = next((item for item in data.setdefault("sections", []) if item.get("section") == section_name), None)
    if section is None:
        section = {
            "section": section_name,
            "page_count": 0,
            "distilled": {
                "section_summary": "Self-documentation for the ZZLab Lab Big Brother AI system.",
                "main_topics": ["self documentation", "architecture", "maintenance", "interfaces", "automation"],
                "key_results": [],
                "important_assets_or_attachments": [],
                "people_and_responsibilities": [],
                "recommended_reading_order": [],
                "follow_up_items": [],
            },
            "pages": [],
        }
        data["sections"].append(section)
    page_distilled = {
        "one_sentence_summary": distilled.get("one_sentence_summary", ""),
        "what_happened": as_items(distilled.get("what_it_is")) + as_items(distilled.get("current_capabilities"))[:8],
        "important_facts": as_items(distilled.get("important_paths")) + as_items(distilled.get("key_scripts_and_responsibilities"))[:12],
        "decisions_or_conclusions": as_items(distilled.get("design_principles")) + as_items(distilled.get("safety_and_privacy_boundaries"))[:8],
        "open_questions_or_next_steps": as_items(distilled.get("next_steps")) + as_items(distilled.get("known_limitations"))[:6],
        "people_organizations_equipment": ["ZZLab", "实验室大师兄", "Qwen3.7-Plus", "Telegram Bot", "Gmail", "OneNote HTML notebook"],
        "tags": list(dict.fromkeys(as_items(distilled.get("tags")) + ["lab-big-brother", "self-documentation", "architecture", "qwen", "telegram", "gmail"])),
        "confidence_notes": as_items(distilled.get("confidence_notes"))
        + ["Generated from project code, README/SKILL docs, PROJECT_HANDOFF, work-log tail, and local LaunchAgent plists. Secrets were not read."],
        "important_assets_or_attachments": [str(md_path), str(html_path), str(json_path), str(manifest_path)] + as_items(distilled.get("important_assets_or_attachments")),
    }
    page = {
        "section": section_name,
        "title": "实验室大师兄自我说明书",
        "html": str(html_path),
        "source_sha256": sha256(html_path),
        "created": generated_at,
        "updated": generated_at,
        "attachments": [str(md_path), str(json_path), str(manifest_path)],
        "distilled": page_distilled,
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
    section["distilled"]["key_results"] = [
        "大师兄 has a self-documentation page in the notebook index.",
        "The current system uses Qwen3.7-Plus for text and vision-backed workflows.",
    ]
    section["distilled"]["important_assets_or_attachments"] = [str(html_path), str(md_path), str(json_path)]
    section["distilled"]["follow_up_items"] = as_items(distilled.get("next_steps"))[:10]
    data["generated_at"] = generated_at
    data.setdefault("incremental_updates", []).append(
        {
            "detected_at": generated_at,
            "source_channel": "self-documentation",
            "records_day": generated_at[:10],
            "html": str(html_path),
            "topic_supplement_pages": [{"section": section_name, "title": page["title"]}],
        }
    )
    DISTILLATION.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    DISTILLATION_HTML.write_text(render_support.render_html(data), encoding="utf-8")


def build_prompt(manifest: list[dict[str, Any]], blocks: str) -> str:
    return f"""
Return valid JSON only. Distill the current ZZLab "实验室大师兄 / Lab Big Brother" system from the provided code, docs, handoff, work log tail, and launch configuration.

Purpose:
- Let 大师兄 understand itself.
- Record what has been built, how it works, where its memory lives, how humans/AI should maintain it, and what safety boundaries matter.
- This will be written into the lab documentation and into the notebook knowledge index.

Rules:
1. Use only the provided source texts.
2. Do not mention or infer any secret value. You may mention private file paths for credentials but never contents.
3. Prefer Chinese, with English technical identifiers preserved.
4. Be practical and operational: future AI should be able to resume maintenance from this.
5. Keep bullets concise but specific.

Required JSON keys:
- one_sentence_summary
- what_it_is
- design_principles
- current_capabilities
- user_interfaces
- data_sources_and_memory
- ingestion_and_digest_workflows
- ai_provider_and_models
- automation_and_services
- important_paths
- key_scripts_and_responsibilities
- safety_and_privacy_boundaries
- how_to_use
- how_to_maintain
- known_limitations
- next_steps
- self_query_examples
- important_assets_or_attachments
- tags
- confidence_notes

SOURCE MANIFEST:
{json.dumps(manifest, ensure_ascii=False)}

SOURCE TEXTS:
{blocks}
"""


def update_self_knowledge(root: Path = ZZLAB_ROOT) -> dict[str, Any]:
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    manifest, blocks = collect_sources(root)
    key = llm_provider.read_api_key(root / "Key/Qwen Key.txt")
    distilled, usage, model = llm_provider.call_json(
        key=key,
        model="qwen3.7-plus",
        messages=[
            {"role": "system", "content": "You are a careful systems archivist for a laboratory AI agent. Always return JSON only."},
            {"role": "user", "content": build_prompt(manifest, blocks)},
        ],
        timeout=240,
        retries=2,
        provider="qwen",
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "LAB_BIG_BROTHER_SELF_KNOWLEDGE.json"
    md_path = OUT_DIR / "LAB_BIG_BROTHER_SELF_KNOWLEDGE.md"
    html_path = OUT_DIR / "LAB_BIG_BROTHER_SELF_KNOWLEDGE.html"
    manifest_path = OUT_DIR / "SOURCE_MANIFEST.json"
    payload = {"generated_at": generated_at, "model": model, "usage": usage, "source_manifest": manifest, "distilled": distilled}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps({"generated_at": generated_at, "sources": manifest}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(markdown_doc(distilled, manifest, generated_at, model), encoding="utf-8")
    html_path.write_text(html_doc(distilled, manifest, generated_at, model), encoding="utf-8")
    upsert_distillation(html_path, md_path, json_path, manifest_path, distilled, generated_at)
    return {
        "generated_at": generated_at,
        "model": model,
        "source_count": len(manifest),
        "markdown": str(md_path),
        "html": str(html_path),
        "json": str(json_path),
        "distillation_section": "Lab Big Brother System",
        "page_title": "实验室大师兄自我说明书",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh Lab Big Brother self-knowledge documentation and notebook index page.")
    parser.add_argument("--root", type=Path, default=ZZLAB_ROOT)
    args = parser.parse_args()
    print(json.dumps(update_self_knowledge(args.root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
