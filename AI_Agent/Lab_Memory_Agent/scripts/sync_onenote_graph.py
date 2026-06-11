from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "onenote_sync.json"
DEFAULT_CACHE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ZZLabAIAgent" / "msal_token_cache.bin"


class HtmlTextExtractor(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self.parts)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def slugify(value: str, limit: int = 80) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value)
    value = value.strip("-")
    return (value or "untitled")[:limit].strip("-")


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def html_to_text(html: str) -> str:
    parser = HtmlTextExtractor()
    parser.feed(html)
    text = parser.get_text()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def graph_get(token: str, url: str, accept: str = "application/json") -> tuple[bytes, dict]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": accept,
            "User-Agent": "ZZLab-AI-Agent-OneNote-Sync/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            headers = dict(response.headers.items())
            return response.read(), headers
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Graph request failed {exc.code} for {url}\n{body}") from exc


def graph_json(token: str, url: str) -> dict:
    body, _headers = graph_get(token, url, "application/json")
    return json.loads(body.decode("utf-8"))


def graph_all(token: str, url: str) -> list[dict]:
    records: list[dict] = []
    while url:
        data = graph_json(token, url)
        records.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    return records


def get_token(config: dict, cache_path: Path, force_login: bool = False) -> str:
    try:
        import msal  # type: ignore
    except Exception as exc:
        raise RuntimeError("Missing dependency: install MSAL with `python -m pip install msal`.") from exc

    authority = f"https://login.microsoftonline.com/{config['tenant_id']}"
    cache = msal.SerializableTokenCache()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists():
        cache.deserialize(cache_path.read_text(encoding="utf-8"))

    app = msal.PublicClientApplication(
        client_id=config["client_id"],
        authority=authority,
        token_cache=cache,
    )
    scopes = config.get("scopes") or ["User.Read", "Notes.Read", "offline_access"]

    result = None
    accounts = app.get_accounts()
    if accounts and not force_login:
        result = app.acquire_token_silent(scopes=scopes, account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=scopes)
        if "user_code" not in flow:
            raise RuntimeError(f"Could not start device flow: {json.dumps(flow, indent=2)}")
        print(flow["message"])
        sys.stdout.flush()
        result = app.acquire_token_by_device_flow(flow)

    if cache.has_state_changed:
        cache_path.write_text(cache.serialize(), encoding="utf-8", newline="\n")

    if not result or "access_token" not in result:
        raise RuntimeError(json.dumps(result, ensure_ascii=False, indent=2))
    return result["access_token"]


def find_notebook(notebooks: list[dict], wanted_name: str) -> dict:
    wanted = wanted_name.casefold()
    exact = [nb for nb in notebooks if (nb.get("displayName") or "").casefold() == wanted]
    if exact:
        return exact[0]
    partial = [nb for nb in notebooks if wanted in (nb.get("displayName") or "").casefold()]
    if partial:
        return partial[0]
    names = ", ".join(sorted(nb.get("displayName", "<unnamed>") for nb in notebooks))
    raise RuntimeError(f"Notebook not found: {wanted_name}. Available notebooks: {names}")


def get_notebooks(token: str, graph_root: str) -> list[dict]:
    url = f"{graph_root}/me/onenote/notebooks?$top=100"
    return graph_all(token, url)


def get_sections(token: str, graph_root: str, notebook_id: str) -> list[dict]:
    params = urllib.parse.urlencode(
        {
            "$top": "100",
            "$expand": "parentNotebook($select=id,displayName)",
        }
    )
    sections = graph_all(token, f"{graph_root}/me/onenote/sections?{params}")
    return [
        section
        for section in sections
        if (section.get("parentNotebook") or {}).get("id") == notebook_id
    ]


def get_pages_for_section(token: str, section: dict) -> list[dict]:
    pages_url = section.get("pagesUrl")
    if not pages_url:
        return []
    delimiter = "&" if "?" in pages_url else "?"
    fields = "id,title,createdDateTime,lastModifiedDateTime,contentUrl,links,parentSection"
    return graph_all(token, f"{pages_url}{delimiter}$top=100&$select={fields}")


def entry_frontmatter(page: dict, section: dict, text_path: Path, html_path: Path, html_hash: str, tag: str) -> str:
    page_id = page["id"]
    title = page.get("title") or "Untitled"
    modified = page.get("lastModifiedDateTime", "")
    date_part = modified[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", modified) else datetime.now().date().isoformat()
    summary = re.sub(r"\s+", " ", title).strip()
    source_refs = [text_path.relative_to(ROOT).as_posix(), html_path.relative_to(ROOT).as_posix()]
    safe_title = title.replace('"', '\\"')
    safe_section = (section.get("displayName") or "").replace('"', '\\"')
    return f"""---
id: onenote-{slugify(page_id, 72)}
title: "{safe_title}"
type: notebook_page
status: active
date: {date_part}
projects: []
people: []
tags: ["{tag}", "onenote", "{safe_section}"]
source_refs: ["{source_refs[0]}", "{source_refs[1]}"]
confidence: high
onenote_page_id: "{page_id}"
onenote_section: "{safe_section}"
last_modified: "{modified}"
content_hash: "{html_hash}"
summary: "{summary.replace('"', '\\"')}"
---
"""


def write_page_entry(page: dict, section: dict, text: str, text_path: Path, html_path: Path, html_hash: str, tag: str) -> Path:
    entry_id = f"onenote-{slugify(page['id'], 72)}"
    entry_path = ROOT / "entries" / f"{entry_id}.md"
    frontmatter = entry_frontmatter(page, section, text_path, html_path, html_hash, tag)
    body = f"""
## OneNote Page

- Section: `{section.get('displayName', '')}`
- Last modified: `{page.get('lastModifiedDateTime', '')}`
- Web URL: {((page.get('links') or {}).get('oneNoteWebUrl') or {}).get('href', '')}

## Extracted Text

{text}
"""
    entry_path.parent.mkdir(parents=True, exist_ok=True)
    entry_path.write_text(frontmatter + body, encoding="utf-8", newline="\n")
    return entry_path


def sync(config: dict, token: str, list_only: bool = False) -> None:
    graph_root = config.get("graph_root", "https://graph.microsoft.com/v1.0").rstrip("/")
    sync_root = ROOT / config.get("sync_root", "sources/onenote_graph")
    stamp = now_stamp()
    raw_dir = sync_root / "raw" / stamp
    html_root = sync_root / "html"
    text_root = sync_root / "text"
    state_path = ROOT / "indices" / "onenote_sync_state.json"
    state = load_json(state_path) if state_path.exists() else {"pages": {}}

    notebooks = get_notebooks(token, graph_root)
    if list_only:
        for nb in notebooks:
            print(f"{nb.get('displayName')} | id={nb.get('id')}")
        return

    notebook = find_notebook(notebooks, config["notebook_name"])
    sections = get_sections(token, graph_root, notebook["id"])
    pages: list[dict] = []
    for section in sections:
        section_pages = get_pages_for_section(token, section)
        for page in section_pages:
            page["_section"] = {
                "id": section.get("id"),
                "displayName": section.get("displayName"),
            }
        pages.extend(section_pages)

    write_json(raw_dir / "notebooks.json", notebooks)
    write_json(raw_dir / "sections.json", sections)
    write_json(raw_dir / "pages.json", pages)

    changed = 0
    skipped = 0
    for page in pages:
        page_id = page["id"]
        modified = page.get("lastModifiedDateTime", "")
        existing = (state.get("pages") or {}).get(page_id, {})
        if existing.get("lastModifiedDateTime") == modified and existing.get("html_path"):
            skipped += 1
            continue

        html_bytes, _headers = graph_get(token, page["contentUrl"], "text/html")
        html = html_bytes.decode("utf-8", errors="replace")
        html_hash = hashlib.sha256(html_bytes).hexdigest()
        section = page["_section"]
        section_slug = slugify(section.get("displayName") or "section")
        page_slug = slugify(page.get("title") or page_id)

        html_path = html_root / section_slug / f"{page_slug}-{slugify(page_id, 24)}.html"
        text_path = text_root / section_slug / f"{page_slug}-{slugify(page_id, 24)}.txt"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html, encoding="utf-8", newline="\n")
        text = html_to_text(html)
        text_path.write_text(text, encoding="utf-8", newline="\n")
        entry_path = write_page_entry(page, section, text, text_path, html_path, html_hash, config.get("entry_tag", "onenote-graph-sync"))

        state.setdefault("pages", {})[page_id] = {
            "title": page.get("title"),
            "section": section.get("displayName"),
            "lastModifiedDateTime": modified,
            "content_hash": html_hash,
            "html_path": html_path.relative_to(ROOT).as_posix(),
            "text_path": text_path.relative_to(ROOT).as_posix(),
            "entry_path": entry_path.relative_to(ROOT).as_posix(),
            "synced_at": stamp,
        }
        changed += 1
        time.sleep(0.1)

    state["last_sync"] = stamp
    state["notebook"] = {"id": notebook.get("id"), "displayName": notebook.get("displayName")}
    state["page_count"] = len(pages)
    write_json(state_path, state)
    print(f"Notebook: {notebook.get('displayName')}")
    print(f"Sections: {len(sections)}")
    print(f"Pages: {len(pages)}")
    print(f"Changed pages: {changed}")
    print(f"Skipped pages: {skipped}")
    print(f"State: {state_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync OneNote notebook content from Microsoft Graph into the memory pack.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to onenote_sync.json")
    parser.add_argument("--cache", default=str(DEFAULT_CACHE), help="Local MSAL token cache path. Keep this off shared NAS.")
    parser.add_argument("--login", action="store_true", help="Force a new device-code login.")
    parser.add_argument("--list-notebooks", action="store_true", help="List visible notebooks and exit.")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        raise SystemExit(f"Config not found: {config_path}. Copy config/onenote_sync.example.json to config/onenote_sync.json first.")
    config = load_json(config_path)
    token = get_token(config, Path(args.cache), force_login=args.login)
    sync(config, token, list_only=args.list_notebooks)


if __name__ == "__main__":
    main()
