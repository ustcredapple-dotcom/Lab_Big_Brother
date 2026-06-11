# Lab Big Brother

Portable, auditable AI memory infrastructure for laboratory work.

The project separates evidence, structured memory, search indices, and AI operating skills so the same knowledge base can move between computers and AI agents without depending on chat history.

## Core Layout

```text
AI_Agent/Lab_Memory_Agent/
  config/       example integration configuration
  entries/      structured, source-linked memory entries
  inbox/        staging area for exported documents
  indices/      rebuildable search indices
  schemas/      memory entry schema
  scripts/      ingestion, indexing, search, and OneNote sync
  skills/       AI operating workflows
  sources/      original evidence
```

## Quick Start

```bash
cd AI_Agent/Lab_Memory_Agent
python3 scripts/rebuild_index.py
python3 scripts/search_memory.py "memory framework"
```

Place exported TXT, Markdown, HTML, MHTML, DOCX, or PDF files in `inbox/`, then run:

```bash
python3 scripts/ingest_exports.py
python3 scripts/rebuild_index.py
```

## Automatic Handoff

The `auto-handoff` skill maintains a concise current snapshot and an append-only local work log. After significant AI work, it can also commit and push public project changes to this repository.

The GitHub repository is public. Raw notebook exports, real memory entries, generated indices, local configuration, detailed work logs, and credentials are excluded by default. The complete operational record remains on the private shared volume.

## Repository

[ustcredapple-dotcom/Lab_Big_Brother](https://github.com/ustcredapple-dotcom/Lab_Big_Brother)

