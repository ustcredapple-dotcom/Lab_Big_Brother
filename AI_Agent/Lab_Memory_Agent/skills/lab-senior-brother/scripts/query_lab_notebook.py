from __future__ import annotations

import argparse
import html.parser
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ROOT = Path("/Volumes/ZZLab_AI")
DEFAULT_DISTILLATION = DEFAULT_ROOT / "Document/Lab_Notebook_Processing/html_deepseek_distilled/DEEPSEEK_DISTILLATION.json"
DEFAULT_HTML_ROOT = DEFAULT_ROOT / "Document/Lab_Notebook_Processing/html/active/Lab_Notebook_Original_2026-06-11"


class TextParser(html.parser.HTMLParser):
    BLOCK_TAGS = {"p", "div", "br", "tr", "table", "li", "h1", "h2", "h3"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "head"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "img":
            alt = dict(attrs).get("alt") or ""
            if alt.strip():
                self.parts.append(f"\n[image] {alt.strip()}\n")
        if tag == "embed":
            src = dict(attrs).get("src") or ""
            if src.strip():
                self.parts.append(f"\n[attachment] {src.strip()}\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "head"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        self.parts.append(data)

    def text(self) -> str:
        text = "".join(self.parts).replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


@dataclass
class PageHit:
    score: float
    section: str
    title: str
    html: str
    source_sha256: str
    distilled: dict[str, Any]
    attachments: list[str]
    snippet: str = ""


def flatten(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(flatten(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(f"{key}: {flatten(item)}" for key, item in value.items())
    return str(value)


def cjk_ngrams(text: str) -> list[str]:
    chars = re.findall(r"[\u3400-\u9fff]", text)
    grams = chars[:]
    grams.extend("".join(chars[index : index + 2]) for index in range(max(0, len(chars) - 1)))
    grams.extend("".join(chars[index : index + 3]) for index in range(max(0, len(chars) - 2)))
    return grams


def query_terms(query: str) -> list[str]:
    terms = []
    terms.extend(term.casefold() for term in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.+-]{1,}", query))
    terms.extend(cjk_ngrams(query))
    seen = set()
    unique = []
    for term in terms:
        if term and term not in seen:
            seen.add(term)
            unique.append(term)
    return unique


def weighted_text(page: dict[str, Any]) -> tuple[str, dict[str, str]]:
    distilled = page.get("distilled", {})
    fields = {
        "title": page.get("title", ""),
        "section": page.get("section", ""),
        "summary": distilled.get("one_sentence_summary", ""),
        "what_happened": flatten(distilled.get("what_happened", [])),
        "important_facts": flatten(distilled.get("important_facts", [])),
        "decisions_or_conclusions": flatten(distilled.get("decisions_or_conclusions", [])),
        "open_questions_or_next_steps": flatten(distilled.get("open_questions_or_next_steps", [])),
        "people_organizations_equipment": flatten(distilled.get("people_organizations_equipment", [])),
        "tags": flatten(distilled.get("tags", [])),
        "attachments": flatten(page.get("attachments", [])),
    }
    return "\n".join(fields.values()).casefold(), fields


def score_page(query: str, terms: list[str], page: dict[str, Any]) -> float:
    haystack, fields = weighted_text(page)
    score = 0.0
    phrase = query.casefold().strip()
    if phrase and phrase in haystack:
        score += 12.0
    weights = {
        "title": 5.0,
        "section": 3.0,
        "summary": 3.0,
        "what_happened": 2.2,
        "important_facts": 2.5,
        "decisions_or_conclusions": 2.5,
        "open_questions_or_next_steps": 2.0,
        "people_organizations_equipment": 1.5,
        "tags": 2.0,
        "attachments": 1.2,
    }
    for name, text in fields.items():
        lowered = text.casefold()
        for term in terms:
            if term in lowered:
                score += weights[name]
    return score


def html_text(path: Path) -> str:
    parser = TextParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return parser.text()


def make_snippet(text: str, terms: list[str], length: int = 360) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    lowered = compact.casefold()
    positions = [lowered.find(term.casefold()) for term in terms if term and lowered.find(term.casefold()) >= 0]
    if not positions:
        return compact[:length]
    center = min(positions)
    start = max(0, center - length // 3)
    end = min(len(compact), start + length)
    return compact[start:end]


def load_pages(distillation: Path) -> list[dict[str, Any]]:
    data = json.loads(distillation.read_text(encoding="utf-8"))
    pages = []
    for section in data.get("sections", []):
        for page in section.get("pages", []):
            page = dict(page)
            page.setdefault("section", section.get("section", ""))
            pages.append(page)
    return pages


def search(query: str, distillation: Path, html_root: Path, top_k: int, include_source_snippets: bool) -> dict[str, Any]:
    terms = query_terms(query)
    hits = []
    for page in load_pages(distillation):
        score = score_page(query, terms, page)
        if score <= 0:
            continue
        snippet = ""
        if include_source_snippets:
            source = html_root / page["html"]
            if source.is_file():
                snippet = make_snippet(html_text(source), terms)
        hits.append(
            PageHit(
                score=score,
                section=page.get("section", ""),
                title=page.get("title", ""),
                html=str(html_root / page.get("html", "")),
                source_sha256=page.get("source_sha256", ""),
                distilled=page.get("distilled", {}),
                attachments=page.get("attachments", []),
                snippet=snippet,
            )
        )
    hits.sort(key=lambda hit: hit.score, reverse=True)
    selected = hits[:top_k]
    if not selected:
        likely_done = "unknown"
        confidence = "low"
    elif selected[0].score >= 20:
        likely_done = "yes"
        confidence = "high"
    elif selected[0].score >= 8:
        likely_done = "likely"
        confidence = "medium"
    else:
        likely_done = "unknown"
        confidence = "low"
    return {
        "query": query,
        "likely_done_before": likely_done,
        "confidence": confidence,
        "top_score": selected[0].score if selected else 0,
        "evidence_count": len(selected),
        "evidence": [
            {
                "score": hit.score,
                "section": hit.section,
                "title": hit.title,
                "html": hit.html,
                "source_sha256": hit.source_sha256,
                "summary": hit.distilled.get("one_sentence_summary", ""),
                "what_happened": hit.distilled.get("what_happened", []),
                "important_facts": hit.distilled.get("important_facts", []),
                "decisions_or_conclusions": hit.distilled.get("decisions_or_conclusions", []),
                "open_questions_or_next_steps": hit.distilled.get("open_questions_or_next_steps", []),
                "people_organizations_equipment": hit.distilled.get("people_organizations_equipment", []),
                "tags": hit.distilled.get("tags", []),
                "attachments": hit.attachments[:10],
                "source_snippet": hit.snippet,
            }
            for hit in selected
        ],
    }


def render_text(result: dict[str, Any]) -> str:
    lines = [
        f"Query: {result['query']}",
        f"Likely done before: {result['likely_done_before']} (confidence: {result['confidence']}, top score: {result['top_score']:.1f})",
        "",
        "Evidence:",
    ]
    for index, item in enumerate(result["evidence"], start=1):
        lines.extend(
            [
                f"{index}. {item['section']} / {item['title']} (score {item['score']:.1f})",
                f"   HTML: {item['html']}",
                f"   Summary: {item['summary']}",
            ]
        )
        facts = item.get("important_facts") or []
        if facts:
            lines.append("   Important facts:")
            for fact in facts[:4]:
                lines.append(f"   - {fact}")
        decisions = item.get("decisions_or_conclusions") or []
        if decisions:
            lines.append("   Decisions/conclusions:")
            for decision in decisions[:3]:
                lines.append(f"   - {decision}")
        if item.get("source_snippet"):
            lines.append(f"   Source snippet: {item['source_snippet']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the ZZLab notebook DeepSeek distillation and source HTML.")
    parser.add_argument("query", help="Question or keywords to search for.")
    parser.add_argument("--distillation", type=Path, default=DEFAULT_DISTILLATION)
    parser.add_argument("--html-root", type=Path, default=DEFAULT_HTML_ROOT)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--include-source-snippets", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    result = search(args.query, args.distillation, args.html_root, args.top_k, args.include_source_snippets)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_text(result), end="")


if __name__ == "__main__":
    main()
