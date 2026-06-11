# Inbox

Put exported OneNote materials here before running:

```powershell
python .\scripts\ingest_exports.py
python .\scripts\rebuild_index.py
```

Supported formats:

- `.txt`, `.md`, `.log`, `.csv`, `.tsv`, `.json`, `.yaml`, `.yml`
- `.html`, `.htm`
- `.mht`, `.mhtml`
- `.docx`
- `.pdf` if `pypdf` is installed

The script copies original files into `sources/imported/` and creates draft entries in `entries/`.
