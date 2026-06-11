from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from PIL import Image as PILImage
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[Node | str] = field(default_factory=list)


class TreeParser(html.parser.HTMLParser):
    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag.lower(), {key: value or "" for key, value in attrs})
        self.stack[-1].children.append(node)
        if tag.lower() not in self.VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self.VOID_TAGS:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def find_first(node: Node, tag: str) -> Node | None:
    if node.tag == tag:
        return node
    for child in node.children:
        if isinstance(child, Node):
            found = find_first(child, tag)
            if found:
                return found
    return None


def find_all(node: Node, tag: str) -> list[Node]:
    found = []
    if node.tag == tag:
        found.append(node)
    for child in node.children:
        if isinstance(child, Node):
            found.extend(find_all(child, tag))
    return found


def class_names(node: Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


def node_text(node: Node, exclude_tags: set[str] | None = None) -> str:
    exclude_tags = exclude_tags or {"script", "style"}
    parts = []
    for child in node.children:
        if isinstance(child, str):
            parts.append(child)
        elif child.tag == "br":
            parts.append("\n")
        elif child.tag not in exclude_tags and child.tag != "img":
            parts.append(node_text(child, exclude_tags))
    text = "".join(parts).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    return text.strip()


def parse_page(path: Path) -> tuple[str, dict[str, str], Node]:
    parser = TreeParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    title_node = find_first(parser.root, "title")
    title = node_text(title_node) if title_node else path.stem
    metadata = {}
    for meta in find_all(parser.root, "meta"):
        name = meta.attrs.get("name")
        if name:
            metadata[name] = meta.attrs.get("content", "")
    body = find_first(parser.root, "body") or parser.root
    return title, metadata, body


def epoch_text(value: str) -> str:
    if not value or not value.isdigit():
        return ""
    return datetime.fromtimestamp(int(value), tz=timezone.utc).astimezone().isoformat(timespec="minutes")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def page_order(index_html: Path, section_dir: Path) -> list[Path]:
    parser = TreeParser()
    parser.feed(index_html.read_text(encoding="utf-8", errors="replace"))
    ordered = []
    for anchor in find_all(parser.root, "a"):
        href = anchor.attrs.get("href", "")
        if not href.lower().endswith(".html"):
            continue
        candidate = (index_html.parent / href).resolve()
        if candidate.parent == section_dir.resolve() and candidate.is_file() and candidate not in ordered:
            ordered.append(candidate)
    if ordered:
        return ordered
    return sorted(section_dir.glob("*.html"), key=lambda path: path.name.casefold())


FONT_NAME = "ZZLabNotebookFont"


def make_styles(font_file: Path) -> dict[str, ParagraphStyle]:
    pdfmetrics.registerFont(TTFont(FONT_NAME, str(font_file)))
    base = getSampleStyleSheet()
    return {
        "section": ParagraphStyle(
            "Section",
            parent=base["Title"],
            fontName=FONT_NAME,
            fontSize=24,
            leading=31,
            alignment=TA_CENTER,
            spaceAfter=14,
        ),
        "page": ParagraphStyle(
            "PageTitle",
            parent=base["Heading1"],
            fontName=FONT_NAME,
            fontSize=18,
            leading=24,
            alignment=TA_LEFT,
            spaceAfter=8,
            textColor=colors.HexColor("#202020"),
        ),
        "meta": ParagraphStyle(
            "Meta",
            parent=base["Normal"],
            fontName=FONT_NAME,
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#666666"),
            spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName=FONT_NAME,
            fontSize=10,
            leading=15,
            spaceAfter=6,
            wordWrap="CJK",
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["BodyText"],
            fontName=FONT_NAME,
            fontSize=10,
            leading=15,
            leftIndent=12,
            firstLineIndent=-8,
            spaceAfter=4,
            wordWrap="CJK",
        ),
        "caption": ParagraphStyle(
            "Caption",
            parent=base["Normal"],
            fontName=FONT_NAME,
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#666666"),
            spaceAfter=6,
            wordWrap="CJK",
        ),
    }


def paragraph(text: str, style: ParagraphStyle) -> Paragraph | None:
    text = text.strip()
    if not text:
        return None
    return Paragraph(escape(text).replace("\n", "<br/>"), style)


def image_flowable(node: Node, page_dir: Path, max_width: float, max_height: float, styles: dict) -> list:
    source = node.attrs.get("src", "")
    if not source or source.startswith(("http://", "https://", "data:")):
        caption = paragraph(node.attrs.get("alt", ""), styles["caption"])
        return [caption] if caption else []
    path = (page_dir / source).resolve()
    if not path.is_file():
        caption = paragraph(f"[Missing image: {source}] {node.attrs.get('alt', '')}", styles["caption"])
        return [caption] if caption else []
    try:
        with PILImage.open(path) as image:
            width, height = image.size
        scale = min(max_width / width, max_height / height, 1.0)
        flowable = Image(str(path), width=width * scale, height=height * scale)
        flowable.hAlign = "LEFT"
        items = [flowable, Spacer(1, 3)]
        alt = node.attrs.get("alt", "").strip()
        if alt and len(alt) < 500:
            caption = paragraph(alt, styles["caption"])
            if caption:
                items.append(caption)
        return items
    except Exception as exc:
        caption = paragraph(f"[Unreadable image: {source}; {type(exc).__name__}]", styles["caption"])
        return [caption] if caption else []


def table_flowable(node: Node, styles: dict, max_width: float) -> list:
    rows = []
    for row_node in find_all(node, "tr"):
        cells = []
        for cell in [child for child in row_node.children if isinstance(child, Node) and child.tag in {"td", "th"}]:
            cells.append(Paragraph(escape(node_text(cell)) or " ", styles["body"]))
        if cells:
            rows.append(cells)
    if not rows:
        return []
    columns = max(len(row) for row in rows)
    for row in rows:
        row.extend([""] * (columns - len(row)))
    table = Table(rows, colWidths=[max_width / columns] * columns, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#999999")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F2")),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return [table, Spacer(1, 7)]


def render_node(node: Node, page_dir: Path, styles: dict, max_width: float, max_height: float) -> list:
    if node.tag in {"script", "style", "head", "title", "meta"}:
        return []
    if node.tag == "img":
        return image_flowable(node, page_dir, max_width, max_height, styles)
    if node.tag == "table":
        return table_flowable(node, styles, max_width)
    if node.tag == "li":
        items = []
        text = node_text(node)
        item = paragraph(f"• {text}", styles["bullet"])
        if item:
            items.append(item)
        for image in find_all(node, "img"):
            items.extend(image_flowable(image, page_dir, max_width, max_height, styles))
        return items
    if node.tag == "p":
        items = []
        item = paragraph(node_text(node), styles["body"])
        if item:
            items.append(item)
        for image in find_all(node, "img"):
            items.extend(image_flowable(image, page_dir, max_width, max_height, styles))
        return items
    if node.tag == "div" and "title" in class_names(node):
        return []
    if node.tag == "div" and "outline-element" in class_names(node):
        block_children = [
            child
            for child in node.children
            if isinstance(child, Node) and child.tag in {"p", "ol", "ul", "table", "div", "img"}
        ]
        if not block_children:
            item = paragraph(node_text(node), styles["body"])
            items = [item] if item else []
            for image in find_all(node, "img"):
                items.extend(image_flowable(image, page_dir, max_width, max_height, styles))
            return items
    items = []
    for child in node.children:
        if isinstance(child, Node):
            items.extend(render_node(child, page_dir, styles, max_width, max_height))
    return items


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont(FONT_NAME, 8)
    canvas.setFillColor(colors.HexColor("#777777"))
    canvas.drawRightString(A4[0] - 15 * mm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


def main() -> None:
    parser = argparse.ArgumentParser(description="Render one2html section output as a readable PDF.")
    parser.add_argument("--section-index", type=Path, required=True)
    parser.add_argument("--section-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-one", type=Path, required=True)
    parser.add_argument("--font-file", type=Path, required=True)
    args = parser.parse_args()

    font_file = args.font_file.resolve()
    if not font_file.is_file():
        parser.error(f"font file does not exist: {font_file}")
    styles = make_styles(font_file)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    pages = page_order(args.section_index.resolve(), args.section_dir.resolve())
    story = [
        Spacer(1, 55 * mm),
        Paragraph(escape(args.section_dir.name), styles["section"]),
        Paragraph(f"Source: {escape(args.source_one.name)}", styles["meta"]),
        Paragraph(f"Pages: {len(pages)}", styles["meta"]),
    ]
    page_records = []
    max_width = A4[0] - 30 * mm
    max_image_height = A4[1] - 45 * mm
    for page_number, html_path in enumerate(pages, start=1):
        title, metadata, body = parse_page(html_path)
        story.append(PageBreak())
        story.append(Paragraph(escape(title), styles["page"]))
        meta_parts = [f"Source page: {html_path.name}"]
        page_id = metadata.get("X-Original-Page-Id", "")
        created = epoch_text(metadata.get("X-Created-Time", ""))
        updated = epoch_text(metadata.get("X-Updated-Time", ""))
        if page_id:
            meta_parts.append(f"OneNote page ID: {page_id}")
        if created:
            meta_parts.append(f"Created: {created}")
        if updated:
            meta_parts.append(f"Updated: {updated}")
        story.append(Paragraph("<br/>".join(escape(part) for part in meta_parts), styles["meta"]))
        flowables = render_node(body, html_path.parent, styles, max_width, max_image_height)
        if flowables:
            story.extend(flowables)
        else:
            story.append(Paragraph("[No readable page content extracted]", styles["meta"]))
        page_records.append(
            {
                "order": page_number,
                "title": title,
                "html": html_path.name,
                "onenote_page_id": page_id,
                "created": created,
                "updated": updated,
            }
        )

    document = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=args.section_dir.name,
        author="ZZLab AI Notebook Pipeline",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    reader = PdfReader(str(output))
    manifest = {
        "section": args.section_dir.name,
        "source_one": str(args.source_one),
        "source_sha256": sha256(args.source_one),
        "source_bytes": args.source_one.stat().st_size,
        "pdf": str(output),
        "pdf_sha256": sha256(output),
        "pdf_bytes": output.stat().st_size,
        "pdf_pages": len(reader.pages),
        "onenote_pages": len(page_records),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "embedded_font": str(font_file),
        "rendering_note": "Readable derivative generated from one2html output; original free-form OneNote positioning may be normalized.",
        "pages": page_records,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: manifest[key] for key in ("section", "onenote_pages", "pdf_pages", "pdf_bytes", "pdf_sha256")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
