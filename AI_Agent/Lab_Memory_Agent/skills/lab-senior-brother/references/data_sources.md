# 实验室大师兄数据源

Use these files as the current notebook knowledge base:

- Qwen distilled index: `/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html_deepseek_distilled/DEEPSEEK_DISTILLATION.json`
- Qwen human overview: `/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html_deepseek_distilled/DEEPSEEK_DISTILLATION.html`
- HTML manifest: `/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/HTML_MANIFEST.json`
- HTML index: `/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/HTML_INDEX.html`
- Source HTML root: `/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/Lab_Notebook_Original_2026-06-11/`
- Original OneNote archive: `/Volumes/ZZLab_AI/Document/Lab_Notebook_Original_2026-06-11/`

The distilled JSON is the first-pass lookup index. The source HTML is the evidence layer. The original OneNote archive remains authoritative.

Current notebook coverage:

- `Artiq Program`: 2 pages
- `Equipment Purchasing`: 20 pages
- `Yb ultracold ion-atom hybrid`: 22 pages

Do not expose credentials from `/Volumes/ZZLab_AI/Key/`.

Local web interface:

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/serve_lab_senior_brother.py
```

Open `http://127.0.0.1:8765/` after the server starts.

Public tunnel notes:

- The web server supports Basic Auth through `--access-user` / `--access-password` or `LAB_SENIOR_BROTHER_USER` / `LAB_SENIOR_BROTHER_PASSWORD`.
- ngrok is used only as a transport from the public URL to local port `8765`.
- Runtime credentials and ngrok authtokens live in private local files, not in the public repository.
- A public tunnel gives remote users access to the query UI and can consume Qwen API quota, so share the URL and login only with trusted users.
