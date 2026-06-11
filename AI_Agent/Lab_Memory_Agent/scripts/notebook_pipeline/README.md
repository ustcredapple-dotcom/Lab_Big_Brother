# Lab Notebook Processing Pipeline

This directory contains the reusable private-data pipeline code. The code may be mirrored to GitHub, but notebook content, generated derivatives, state files, and credentials must remain outside the public repository.

## Stages

1. Parse active OneNote sections with the patched one2html build.
2. Render each section as a readable PDF with render_onenote_section_pdf.py.
3. Submit PDFs to MinerU with mineru_pdf_to_md.py.
4. Classify MinerU Markdown and build the archive index with deepseek_archive_notebook.py.

## Credentials

Do not put tokens in command history, source files, state manifests, or GitHub.

- MinerU token: create Key/MinerU Key.txt, Key/MinerU Token.txt, or Key/mineru_token.txt.
- DeepSeek key: Key/Deepseek Key.txt.

## MinerU Command

Run from a Python 3 environment:

    python mineru_pdf_to_md.py \
      --pdf-dir /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/pdf \
      --raw-dir /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/mineru_raw \
      --markdown-dir /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/markdown \
      --state-file /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/manifests/mineru_batch.json

The script uses MinerU local-file batch upload, polls the batch result, downloads result zip files, preserves raw output, and copies the primary Markdown files into the clean Markdown directory.

## DeepSeek Command

    python deepseek_archive_notebook.py \
      --markdown-dir /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/markdown \
      --archive-dir /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/archive \
      --manifest-dir /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/manifests/deepseek

The script uses JSON Output, restricts classifications to the local taxonomy, preserves source Markdown, writes per-document provenance manifests, and rebuilds both INDEX.md and INDEX.json.

## Official API References

- MinerU API documentation: https://mineru.net/apiManage/docs
- DeepSeek API documentation: https://api-docs.deepseek.com/
- DeepSeek JSON Output guide: https://api-docs.deepseek.com/guides/json_mode

## Safety Rules

- Never overwrite the original OneNote archive.
- Never print or store credential values.
- Keep MinerU raw output separate from clean Markdown.
- Preserve source hashes and source names in all derivative manifests.
- Treat DeepSeek summaries as navigation aids, not as replacements for source records.
