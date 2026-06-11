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

## 实验室大师兄

`AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/` is the GPT-facing lab notebook query interface.

Use it when asking whether the lab has done something before and how it was done. The skill queries the DeepSeek-distilled notebook index first, then points back to the source HTML evidence.

Example:

```bash
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/query_lab_notebook.py \
  "我们之前做过 DDS 验收吗？怎么做的？" \
  --include-source-snippets
```

Local web UI:

```bash
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/serve_lab_senior_brother.py
```

Then open `http://127.0.0.1:8765/`. The browser talks to a local Python server; the DeepSeek API key is read only by the server and is not embedded in the HTML page.

The UI includes a `中文 / English` toggle for the final answer language.

Public sharing can be enabled by running the same local server behind an ngrok tunnel. Keep the tunnel protected with Basic Auth and store runtime credentials only in local private configuration, never in Git:

```bash
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/serve_lab_senior_brother.py \
  --access-user "$LAB_SENIOR_BROTHER_USER" \
  --access-password "$LAB_SENIOR_BROTHER_PASSWORD"
ngrok http 8765
```

The public URL may change when ngrok is restarted unless a reserved domain is configured. Anyone with the URL and Basic Auth credentials can query the notebook interface and may consume DeepSeek API quota.

Nightly notebook maintenance:

```bash
python3 AI_Agent/Lab_Memory_Agent/scripts/notebook_pipeline/daily_notebook_update.py
```

This builds a fresh HTML manifest, compares it with the previous snapshot, writes timestamped JSON/Markdown change logs, and sends only added or modified pages to DeepSeek before merging those page records back into the distilled index. A macOS LaunchAgent can run the script every day at `00:00`; keep any cloud-sync command in private local configuration, not in Git.

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
