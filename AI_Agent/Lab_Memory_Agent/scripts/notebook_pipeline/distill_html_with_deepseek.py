from __future__ import annotations

import argparse
import hashlib
import html
import html.parser
import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


class TextParser(html.parser.HTMLParser):
    BLOCK_TAGS = {"p", "div", "br", "tr", "table", "li", "h1", "h2", "h3"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.attachments: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr = dict(attrs)
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "img":
            src = (attr.get("src") or "").strip()
            alt = (attr.get("alt") or "").strip()
            if src:
                self.attachments.append(src)
            if alt:
                self.parts.append(f"\n[image alt text] {alt}\n")
        if tag == "embed":
            src = (attr.get("src") or "").strip()
            if src:
                self.attachments.append(src)
                self.parts.append(f"\n[embedded attachment] {src}\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        text = "".join(self.parts).replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_deepseek_key(path: Path) -> str:
    raw = path.read_text(encoding="utf-8").strip()
    parts = raw.replace("：", ":").replace("=", " ").replace(":", " ").split()
    for part in parts:
        if part.startswith("sk-"):
            return part
    if raw.startswith("sk-"):
        return raw
    raise SystemExit(f"No DeepSeek sk-token found in {path}")


def extract_html(path: Path) -> tuple[str, list[str]]:
    parser = TextParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    attachments = []
    seen = set()
    for item in parser.attachments:
        if item not in seen:
            seen.add(item)
            attachments.append(item)
    return parser.text(), attachments


def call_deepseek(key: str, model: str, messages: list[dict], timeout: int, retries: int) -> tuple[dict, dict, str]:
    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "stream": False,
    }
    last_error = None
    for attempt in range(1, retries + 1):
        result = subprocess.run(
            [
                "curl",
                "-sS",
                "https://api.deepseek.com/chat/completions",
                "-H",
                f"Authorization: Bearer {key}",
                "-H",
                "Content-Type: application/json",
                "-d",
                json.dumps(payload, ensure_ascii=False),
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        if result.returncode:
            last_error = result.stderr.strip() or f"curl exited {result.returncode}"
        else:
            data = json.loads(result.stdout)
            if data.get("error"):
                last_error = json.dumps(data["error"], ensure_ascii=False)
            else:
                content = data["choices"][0]["message"]["content"]
                return json.loads(content), data.get("usage", {}), data.get("model", model)
        if attempt < retries:
            time.sleep(2 * attempt)
    raise RuntimeError(last_error or "DeepSeek request failed")


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[TRUNCATED FOR REQUEST SIZE]"


def distill_page(key: str, model: str, section: str, page: dict, source_text: str, attachments: list[str], timeout: int) -> tuple[dict, dict, str]:
    prompt = f"""
Return valid JSON only. Distill this laboratory notebook HTML page into a compact, source-faithful knowledge record.

Required JSON keys:
- one_sentence_summary: string
- what_happened: array of short factual bullets
- important_facts: array of facts preserving quantities, dates, names, devices, wavelengths, frequencies, file names, and status when present
- decisions_or_conclusions: array
- open_questions_or_next_steps: array
- people_organizations_equipment: array
- tags: array of short tags
- confidence_notes: array of uncertainty notes

Rules:
1. Use only the provided page text and attachment names.
2. Do not invent facts.
3. Prefer Chinese for Chinese source pages and English for English source pages.
4. Keep every bullet concise but independently understandable.

Section: {section}
Page title: {page['title']}
Created: {page.get('created', '')}
Updated: {page.get('updated', '')}
Source HTML: {page['html']}
Attachments: {json.dumps(attachments[:60], ensure_ascii=False)}

PAGE TEXT:
{truncate(source_text, 45000)}
"""
    return call_deepseek(
        key,
        model,
        [
            {"role": "system", "content": "You are a careful laboratory notebook archivist. Always return JSON only."},
            {"role": "user", "content": prompt},
        ],
        timeout=timeout,
        retries=3,
    )


def summarize_section(key: str, model: str, section_name: str, pages: list[dict], timeout: int) -> tuple[dict, dict, str]:
    prompt = f"""
Return valid JSON only. Create a section-level digest from these page records.

Required JSON keys:
- section_summary: string
- main_topics: array
- key_results: array
- important_assets_or_attachments: array
- people_and_responsibilities: array
- recommended_reading_order: array of page titles
- follow_up_items: array

Section: {section_name}
Page records:
{json.dumps(pages, ensure_ascii=False)}
"""
    return call_deepseek(
        key,
        model,
        [
            {"role": "system", "content": "You are a careful laboratory notebook archivist. Always return JSON only."},
            {"role": "user", "content": prompt},
        ],
        timeout=timeout,
        retries=3,
    )


def summarize_notebook(key: str, model: str, sections: list[dict], timeout: int) -> tuple[dict, dict, str]:
    prompt = f"""
Return valid JSON only. Create a notebook-level digest from these section records.

Required JSON keys:
- notebook_summary: string
- top_level_topics: array
- high_value_pages: array of objects with title and why
- operational_state: array
- risks_or_open_questions: array
- suggested_next_index_improvements: array

Section records:
{json.dumps(sections, ensure_ascii=False)}
"""
    return call_deepseek(
        key,
        model,
        [
            {"role": "system", "content": "You are a careful laboratory notebook archivist. Always return JSON only."},
            {"role": "user", "content": prompt},
        ],
        timeout=timeout,
        retries=3,
    )


def link_for(html_path: str) -> str:
    return quote("../html/active/Lab_Notebook_Original_2026-06-11/" + html_path, safe="/#%")


def list_items(items: list) -> str:
    return "".join(f"<li>{html.escape(str(item))}</li>" for item in items)


def render_html(data: dict) -> str:
    section_html = []
    for section in data["sections"]:
        page_rows = []
        for page in section["pages"]:
            distilled = page["distilled"]
            page_rows.append(
                "<tr>"
                f"<td><a href=\"{html.escape(link_for(page['html']))}\">{html.escape(page['title'])}</a></td>"
                f"<td>{html.escape(', '.join(distilled.get('tags', [])))}</td>"
                f"<td>{html.escape(distilled.get('one_sentence_summary', ''))}</td>"
                "</tr>"
            )
        digest = section["distilled"]
        section_html.append(
            "<section>"
            f"<h2>{html.escape(section['section'])}</h2>"
            f"<p>{html.escape(digest.get('section_summary', ''))}</p>"
            f"<h3>Main Topics</h3><ul>{list_items(digest.get('main_topics', []))}</ul>"
            f"<h3>Key Results</h3><ul>{list_items(digest.get('key_results', []))}</ul>"
            "<table><thead><tr><th>Page</th><th>Tags</th><th>Summary</th></tr></thead>"
            f"<tbody>{''.join(page_rows)}</tbody></table>"
            "</section>"
        )
    notebook = data["notebook"]
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>ZZLab Notebook DeepSeek Distillation</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; margin: 32px; line-height: 1.5; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
    th {{ background: #f5f5f5; }}
    section {{ margin-top: 2rem; border-top: 1px solid #ddd; padding-top: 1rem; }}
  </style>
</head>
<body>
  <h1>ZZLab Notebook DeepSeek Distillation</h1>
  <p>Generated at {html.escape(data['generated_at'])}. Source format remains HTML; this file is a navigational derivative.</p>
  <h2>Notebook Summary</h2>
  <p>{html.escape(notebook.get('notebook_summary', ''))}</p>
  <h3>Top-Level Topics</h3><ul>{list_items(notebook.get('top_level_topics', []))}</ul>
  <h3>Risks or Open Questions</h3><ul>{list_items(notebook.get('risks_or_open_questions', []))}</ul>
  {''.join(section_html)}
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Distill HTML lab notebook pages with DeepSeek.")
    parser.add_argument("--html-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, default=Path("/Volumes/ZZLab_AI/Key/Deepseek Key.txt"))
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    key = read_deepseek_key(args.key_file)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)

    usage_records = []
    sections = []
    for section in manifest["sections"]:
        page_records = []
        for page in section["pages"]:
            source = args.html_root / page["html"]
            source_text, attachments = extract_html(source)
            distilled, usage, actual_model = distill_page(key, args.model, section["section"], page, source_text, attachments, args.timeout)
            page_record = {
                "section": section["section"],
                "title": page["title"],
                "html": page["html"],
                "source_sha256": sha256(source),
                "created": page.get("created", ""),
                "updated": page.get("updated", ""),
                "attachments": attachments,
                "distilled": distilled,
            }
            page_records.append(page_record)
            usage_records.append({"kind": "page", "section": section["section"], "title": page["title"], "usage": usage, "model": actual_model})
            print(json.dumps({"page": page["title"], "tokens": usage.get("total_tokens")}, ensure_ascii=False), flush=True)
        section_distilled, usage, actual_model = summarize_section(key, args.model, section["section"], page_records, args.timeout)
        usage_records.append({"kind": "section", "section": section["section"], "usage": usage, "model": actual_model})
        sections.append({"section": section["section"], "page_count": len(page_records), "distilled": section_distilled, "pages": page_records})

    notebook_distilled, usage, actual_model = summarize_notebook(key, args.model, sections, args.timeout)
    usage_records.append({"kind": "notebook", "usage": usage, "model": actual_model})
    output = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "method": "deepseek_html_distillation",
        "requested_model": args.model,
        "source_manifest": str(args.manifest),
        "html_root": str(args.html_root),
        "notebook": notebook_distilled,
        "sections": sections,
        "usage": usage_records,
    }
    (args.output_dir / "DEEPSEEK_DISTILLATION.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "DEEPSEEK_DISTILLATION.html").write_text(render_html(output), encoding="utf-8")
    print(json.dumps({"sections": len(sections), "pages": sum(section["page_count"] for section in sections), "output": str(args.output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
