# Inbox 中文说明

`inbox/` 是临时导入区。把从 OneNote 或其他地方导出的材料先放这里，再运行导入和索引脚本。

Windows PowerShell 示例：

```powershell
python .\scripts\ingest_exports.py
python .\scripts\rebuild_index.py
```

支持格式：

- `.txt`, `.md`, `.log`, `.csv`, `.tsv`, `.json`, `.yaml`, `.yml`
- `.html`, `.htm`
- `.mht`, `.mhtml`
- `.docx`
- `.pdf`，前提是安装了 `pypdf`

脚本会把原始文件复制到 `sources/imported/`，并在 `entries/` 里生成草稿记忆条目。

注意：`inbox/` 里的真实实验室材料默认是私有的，不进入公开 GitHub。
