from __future__ import annotations

import argparse
import hashlib
import html
import html.parser
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["Node | str"] = field(default_factory=list)


class TreeParser(html.parser.HTMLParser):
    VOID_TAGS = {"br", "hr", "img", "input", "link", "meta"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag.lower(), {key: value or "" for key, value in attrs})
        self.stack[-1].children.append(node)
        if tag.lower() not in self.VOID_TAGS:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag.lower():
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def parse_html(path: Path) -> Node:
    parser = TreeParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return parser.root


def find_all(node: Node, tag: str) -> list[Node]:
    found = [node] if node.tag == tag else []
    for child in node.children:
        if isinstance(child, Node):
            found.extend(find_all(child, tag))
    return found


def find_first(node: Node, tag: str) -> Node | None:
    if node.tag == tag:
        return node
    for child in node.children:
        if isinstance(child, Node):
            found = find_first(child, tag)
            if found:
                return found
    return None


def text_of(node: Node | None) -> str:
    if node is None:
        return ""
    parts = []
    for child in node.children:
        if isinstance(child, str):
            parts.append(child)
        elif child.tag == "br":
            parts.append("\n")
        elif child.tag not in {"script", "style", "head"}:
            parts.append(text_of(child))
    text = "".join(parts).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    return text.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def epoch_text(value: str) -> str:
    if not value or not value.isdigit():
        return ""
    return datetime.fromtimestamp(int(value), tz=timezone.utc).astimezone().isoformat(timespec="minutes")


def metadata(path: Path) -> tuple[str, dict[str, str], str]:
    root = parse_html(path)
    title = text_of(find_first(root, "title")) or path.stem
    meta = {}
    for item in find_all(root, "meta"):
        name = item.attrs.get("name")
        if name:
            meta[name] = item.attrs.get("content", "")
    body_text = text_of(find_first(root, "body"))
    return title, meta, body_text


def page_order(section_index: Path, section_dir: Path) -> list[Path]:
    root = parse_html(section_index)
    ordered = []
    for anchor in find_all(root, "a"):
        href = anchor.attrs.get("href", "")
        if not href.lower().endswith(".html"):
            continue
        candidate = (section_index.parent / href).resolve()
        if candidate.parent == section_dir.resolve() and candidate.is_file() and candidate not in ordered:
            ordered.append(candidate)
    return ordered or sorted(section_dir.glob("*.html"), key=lambda path: path.name.casefold())


def rel_link(path: Path, base: Path) -> str:
    return quote(path.relative_to(base).as_posix(), safe="/#%")


def build_manifest(html_root: Path) -> dict:
    notebook_indexes = [path for path in sorted(html_root.glob("*.html")) if (html_root / path.stem).is_dir()]
    records = []
    for section_index in notebook_indexes:
        section = section_index.stem
        section_dir = html_root / section
        pages = []
        for order, page in enumerate(page_order(section_index, section_dir), start=1):
            title, meta, body_text = metadata(page)
            pages.append(
                {
                    "order": order,
                    "title": title,
                    "html": page.relative_to(html_root).as_posix(),
                    "sha256": sha256(page),
                    "onenote_page_id": meta.get("X-Original-Page-Id", ""),
                    "created": epoch_text(meta.get("X-Created-Time", "")),
                    "updated": epoch_text(meta.get("X-Updated-Time", "")),
                    "text_preview": re.sub(r"\s+", " ", body_text)[:260],
                }
            )
        records.append(
            {
                "section": section,
                "index_html": section_index.relative_to(html_root).as_posix(),
                "page_count": len(pages),
                "pages": pages,
            }
        )
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "html_root": str(html_root),
        "source": "one2html active notebook output",
        "policy": "HTML is the primary notebook derivative for humans and AI agents.",
        "sections": records,
    }


def render_index(manifest: dict, output: Path, html_root: Path) -> str:
    rows = []
    for section in manifest["sections"]:
        for page in section["pages"]:
            rows.append(
                "<tr>"
                f"<td>{html.escape(section['section'])}</td>"
                f"<td>{page['order']}</td>"
                f"<td><a href=\"{html.escape(rel_link(html_root / page['html'], output.parent))}\">{html.escape(page['title'])}</a></td>"
                f"<td>{html.escape(page.get('updated') or page.get('created') or '')}</td>"
                f"<td>{html.escape(page.get('text_preview', ''))}</td>"
                "</tr>"
            )
    section_cards = []
    for section in manifest["sections"]:
        section_cards.append(
            "<li>"
            f"<a href=\"{html.escape(rel_link(html_root / section['index_html'], output.parent))}\">{html.escape(section['section'])}</a>"
            f" <span>{section['page_count']} pages</span>"
            "</li>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>ZZLab Notebook HTML Index</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; margin: 32px; line-height: 1.45; }}
    h1, h2 {{ margin-bottom: 0.35rem; }}
    .note {{ color: #555; max-width: 980px; }}
    ul {{ padding-left: 1.25rem; }}
    li span {{ color: #777; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
    th, td {{ border: 1px solid #d0d0d0; padding: 8px; vertical-align: top; }}
    th {{ background: #f5f5f5; text-align: left; }}
    td:nth-child(2) {{ text-align: right; width: 4rem; }}
    td:nth-child(4) {{ white-space: nowrap; }}
    a {{ color: #0645ad; }}
  </style>
</head>
<body>
  <h1>ZZLab Notebook HTML Index</h1>
  <p class="note">Generated at {html.escape(manifest['generated_at'])}. HTML is the primary notebook derivative for humans and AI agents. The original OneNote archive remains authoritative.</p>
  <h2>Sections</h2>
  <ul>
    {''.join(section_cards)}
  </ul>
  <h2>Pages</h2>
  <table>
    <thead><tr><th>Section</th><th>#</th><th>Page</th><th>Updated</th><th>Preview</th></tr></thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an AI-friendly index for one2html notebook output.")
    parser.add_argument("--html-root", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.html_root.resolve())
    args.index.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.index.write_text(render_index(manifest, args.index.resolve(), args.html_root.resolve()), encoding="utf-8")
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pages = sum(section["page_count"] for section in manifest["sections"])
    print(json.dumps({"sections": len(manifest["sections"]), "pages": pages, "index": str(args.index)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
