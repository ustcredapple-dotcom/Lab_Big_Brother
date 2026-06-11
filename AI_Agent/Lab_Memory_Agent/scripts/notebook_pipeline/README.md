# Lab Notebook HTML Pipeline

This directory contains the public-safe code for the active lab notebook workflow.

## Current Workflow

The notebook workflow is HTML-first:

1. Preserve the original OneNote archive under `Document/Lab_Notebook_Original_2026-06-11/`.
2. Convert active OneNote sections to local HTML with the patched `one2html` path.
3. Store the HTML tree under `Document/Lab_Notebook_Processing/html/active/`.
4. Generate `HTML_INDEX.html` and `HTML_MANIFEST.json` with `build_html_notebook_index.py`.
5. Let humans and AI agents read the HTML directly.

## Script

Generate or refresh the HTML index:

```bash
python build_html_notebook_index.py \
  --html-root /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/Lab_Notebook_Original_2026-06-11 \
  --index /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/HTML_INDEX.html \
  --manifest /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/HTML_MANIFEST.json
```

## Outputs

- `HTML_INDEX.html`: human- and AI-friendly page index with links and previews.
- `HTML_MANIFEST.json`: machine-readable metadata for sections, pages, timestamps, source IDs, hashes, and text previews.

## Safety Rules

- Never overwrite the original OneNote archive.
- Do not copy credentials or notebook-sharing secrets into code, docs, HTML, logs, or GitHub.
- Keep private notebook content and generated HTML out of the public repository.
- Preserve relative links inside the HTML tree so attachments remain readable.
