from __future__ import annotations

import argparse
import hashlib
import html
import html.parser
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


KEYWORDS = {
    "artiq": "ARTIQ",
    "dds": "DDS",
    "ttl": "TTL",
    "laser": "laser",
    "aom": "AOM",
    "eom": "EOM",
    "mot": "MOT",
    "cavity": "cavity",
    "vacuum": "vacuum",
    "ion": "ion",
    "atom": "atom",
    "optical": "optical",
    "temperature": "temperature",
    "purchase": "purchase",
    "quotation": "quotation",
    "renovation": "renovation",
    "computer": "computer",
    "website": "website",
    "验收": "验收",
    "真空": "真空",
    "激光": "激光",
    "离子阱": "离子阱",
    "采购": "采购",
    "报价": "报价",
    "温度": "温度",
    "烘烤": "烘烤",
}

NEXT_STEP_PATTERNS = (
    "next",
    "todo",
    "should",
    "need",
    "pending",
    "issue",
    "problem",
    "下一步",
    "需要",
    "建议",
    "问题",
    "联系",
    "待",
)

FACT_PATTERNS = re.compile(
    r"(\d+(?:\.\d+)?\s?(?:nm|MHz|GHz|kHz|mW|W|V|A|mm|cm|m|Torr|Pa|℃|C|dbm|dBm|USD|HKD|RMB|¥|%))|(\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b)|(\b\d{1,2}/\d{1,2}/20\d{2}\b)"
)


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
            alt = (attr.get("alt") or "").strip()
            src = (attr.get("src") or "").strip()
            if alt:
                self.parts.append(f"\n[image] {alt}\n")
            if src:
                self.attachments.append(src)
        if tag == "embed":
            src = (attr.get("src") or "").strip()
            if src:
                self.parts.append(f"\n[embedded attachment] {src}\n")
                self.attachments.append(src)

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


def extract(path: Path) -> tuple[str, list[str]]:
    parser = TextParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    attachments = []
    seen = set()
    for item in parser.attachments:
        if item not in seen:
            seen.add(item)
            attachments.append(item)
    return parser.text(), attachments


def split_sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[。！？.!?])\s+|\n+", text)
    return [re.sub(r"\s+", " ", item).strip() for item in raw if len(item.strip()) > 8]


def tags_for(text: str) -> list[str]:
    lowered = text.casefold()
    tags = [label for key, label in KEYWORDS.items() if key.casefold() in lowered]
    return sorted(set(tags), key=tags.index)[:12]


def important_facts(sentences: list[str]) -> list[str]:
    scored = []
    for sentence in sentences:
        score = 0
        if FACT_PATTERNS.search(sentence):
            score += 3
        if any(word in sentence.casefold() for word in ("result", "conclusion", "problem", "issue", "原因", "结果", "问题", "方案", "完成", "验收")):
            score += 2
        if 20 <= len(sentence) <= 260:
            score += 1
        if score:
            scored.append((score, sentence))
    return [item for _, item in sorted(scored, key=lambda pair: (-pair[0], len(pair[1])))[:8]]


def next_steps(sentences: list[str]) -> list[str]:
    found = []
    for sentence in sentences:
        lowered = sentence.casefold()
        if any(pattern in lowered for pattern in NEXT_STEP_PATTERNS):
            found.append(sentence)
    return found[:6]


def summarize(text: str, title: str) -> str:
    sentences = split_sentences(text)
    if sentences:
        return sentences[0][:320]
    preview = re.sub(r"\s+", " ", text).strip()
    return preview[:320] if preview else f"No readable text extracted for {title}."


def distill_page(html_root: Path, page: dict, section: str) -> dict:
    path = html_root / page["html"]
    text, attachments = extract(path)
    sentences = split_sentences(text)
    return {
        "section": section,
        "title": page["title"],
        "html": page["html"],
        "sha256": sha256(path),
        "created": page.get("created", ""),
        "updated": page.get("updated", ""),
        "summary": summarize(text, page["title"]),
        "tags": tags_for(f"{section}\n{page['title']}\n{text}"),
        "important_facts": important_facts(sentences),
        "next_steps_or_questions": next_steps(sentences),
        "attachments": attachments[:30],
        "text_characters": len(text),
    }


def section_summary(section: dict, pages: list[dict]) -> dict:
    tag_counts = Counter(tag for page in pages for tag in page["tags"])
    facts = []
    for page in pages:
        facts.extend(page["important_facts"][:2])
    return {
        "section": section["section"],
        "page_count": len(pages),
        "summary": f"{section['section']} contains {len(pages)} pages. Main tags: {', '.join(tag for tag, _ in tag_counts.most_common(8)) or 'none detected'}.",
        "top_tags": [tag for tag, _ in tag_counts.most_common(12)],
        "highlight_facts": facts[:12],
        "pages": pages,
    }


def rel(path: str) -> str:
    return quote("../html/active/Lab_Notebook_Original_2026-06-11/" + path, safe="/#%")


def render_html(data: dict) -> str:
    sections = []
    for section in data["sections"]:
        rows = []
        for page in section["pages"]:
            rows.append(
                "<tr>"
                f"<td><a href=\"{html.escape(rel(page['html']))}\">{html.escape(page['title'])}</a></td>"
                f"<td>{html.escape(', '.join(page['tags']))}</td>"
                f"<td>{html.escape(page['summary'])}</td>"
                "</tr>"
            )
        facts = "".join(f"<li>{html.escape(fact)}</li>" for fact in section["highlight_facts"])
        sections.append(
            "<section>"
            f"<h2>{html.escape(section['section'])}</h2>"
            f"<p>{html.escape(section['summary'])}</p>"
            f"<h3>Highlights</h3><ul>{facts}</ul>"
            "<table><thead><tr><th>Page</th><th>Tags</th><th>Local Summary</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
            "</section>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>ZZLab Notebook Local Distillation</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; margin: 32px; line-height: 1.5; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
    th {{ background: #f5f5f5; }}
    section {{ margin-top: 2rem; border-top: 1px solid #ddd; padding-top: 1rem; }}
  </style>
</head>
<body>
  <h1>ZZLab Notebook Local Distillation</h1>
  <p>Generated at {html.escape(data['generated_at'])}. This distillation was produced locally from HTML without external API calls.</p>
  <p>Sections: {len(data['sections'])}; pages: {sum(section['page_count'] for section in data['sections'])}.</p>
  {''.join(sections)}
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local HTML/JSON distillation from notebook HTML.")
    parser.add_argument("--html-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sections = []
    for section in manifest["sections"]:
        pages = [distill_page(args.html_root, page, section["section"]) for page in section["pages"]]
        sections.append(section_summary(section, pages))
    data = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "method": "local_html_distillation",
        "source_manifest": str(args.manifest),
        "sections": sections,
    }
    (args.output_dir / "LOCAL_DISTILLATION.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "LOCAL_DISTILLATION.html").write_text(render_html(data), encoding="utf-8")
    print(json.dumps({"sections": len(sections), "pages": sum(section["page_count"] for section in sections), "output": str(args.output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
