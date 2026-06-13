# Lab Notebook HTML Pipeline

中文人类版：`README_zh.md`。

This directory contains the public-safe code for the active lab notebook workflow.

## Current Workflow

The notebook workflow is HTML-first:

1. Preserve the original OneNote archive under `Document/Lab_Notebook_Original_2026-06-11/`.
2. Convert active OneNote sections to local HTML with the patched `one2html` path.
3. Store the HTML tree under `Document/Lab_Notebook_Processing/html/active/`.
4. Generate `HTML_INDEX.html` and `HTML_MANIFEST.json` with `build_html_notebook_index.py`.
5. Let humans and AI agents read the HTML directly.
6. Optionally generate a local distilled overview with `distill_html_locally.py`.
7. With project-owner approval, generate a Qwen distilled overview with `distill_html_with_deepseek.py`. The script name is retained for compatibility.

## Script

Generate or refresh the HTML index:

```bash
python build_html_notebook_index.py \
  --html-root /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/Lab_Notebook_Original_2026-06-11 \
  --index /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/HTML_INDEX.html \
  --manifest /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/HTML_MANIFEST.json
```

Generate or refresh the local distillation:

```bash
python distill_html_locally.py \
  --html-root /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/Lab_Notebook_Original_2026-06-11 \
  --manifest /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/HTML_MANIFEST.json \
  --output-dir /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html_distilled
```

Generate or refresh the Qwen distillation:

```bash
python distill_html_with_deepseek.py \
  --html-root /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/Lab_Notebook_Original_2026-06-11 \
  --manifest /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/HTML_MANIFEST.json \
  --output-dir /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html_deepseek_distilled
```

Run the daily incremental updater:

```bash
python daily_notebook_update.py
```

The daily updater:

- optionally runs a private pre-sync command before indexing;
- optionally merges a fresh incoming HTML export into the active HTML tree;
- skips duplicate pages so identical HTML is not stored twice;
- rebuilds `HTML_INDEX.html` and `HTML_MANIFEST.json`;
- compares the current manifest and extracted page text against the previous daily snapshot;
- writes timestamped JSON and Markdown change logs under `Document/Lab_Notebook_Processing/daily_updates/changes/`;
- sends only added or modified pages to Qwen;
- merges those refreshed page records into `html_deepseek_distilled/DEEPSEEK_DISTILLATION.json/html`.

Private daily config can set:

```json
{
  "pre_sync_command": "",
  "incoming_html_root": "/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/incoming",
  "cleanup_incoming_html": true
}
```

`incoming_html_root` should be a temporary one2html-style export tree. When `cleanup_incoming_html` is true, duplicate incoming page HTML and referenced attachment files are removed after they are confirmed to match active content. The active HTML tree remains the single durable readable copy.

The first baseline run should use `--no-deepseek` so existing pages are recorded without paying to redistill the whole notebook:

```bash
python daily_notebook_update.py --no-deepseek
```

## Outputs

- `HTML_INDEX.html`: human- and AI-friendly page index with links and previews.
- `HTML_MANIFEST.json`: machine-readable metadata for sections, pages, timestamps, source IDs, hashes, and text previews.
- `html_distilled/LOCAL_DISTILLATION.html`: local condensed overview generated without external API calls.
- `html_distilled/LOCAL_DISTILLATION.json`: machine-readable local distillation.
- `html_deepseek_distilled/DEEPSEEK_DISTILLATION.html`: Qwen-generated notebook digest. The path name is kept for compatibility.
- `html_deepseek_distilled/DEEPSEEK_DISTILLATION.json`: machine-readable Qwen distillation with page, section, and notebook summaries.
- `daily_updates/`: private daily snapshots, text diffs, logs, and incremental-update state.

## Safety Rules

- Never overwrite the original OneNote archive.
- Do not copy credentials or notebook-sharing secrets into code, docs, HTML, logs, or GitHub.
- Keep private notebook content and generated HTML out of the public repository.
- Preserve relative links inside the HTML tree so attachments remain readable.
- Send notebook content to external APIs only with explicit project-owner approval.
- Do not put cloud tokens, passwords, or sharing secrets in the daily updater config or logs.
