# 实验室大师兄数据源中文说明

这份文档说明大师兄当前查 notebook 和实验室记忆时用哪些文件。

## 主要索引和资料

- Qwen 蒸馏 JSON：`/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html_deepseek_distilled/DEEPSEEK_DISTILLATION.json`
- Qwen 人类可读总览：`/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html_deepseek_distilled/DEEPSEEK_DISTILLATION.html`
- HTML manifest：`/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/HTML_MANIFEST.json`
- HTML index：`/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/HTML_INDEX.html`
- 源 HTML 根目录：`/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/Lab_Notebook_Original_2026-06-11/`
- 原始 OneNote archive：`/Volumes/ZZLab_AI/Document/Lab_Notebook_Original_2026-06-11/`

## 怎么理解这些层级

- `DEEPSEEK_DISTILLATION.json/html` 是第一层查找目录。名字保留 `deepseek` 是兼容旧流程，当前默认模型是 Qwen。
- 源 HTML 是证据层。回答关键事实时，最好能追到源 HTML。
- 原始 OneNote archive 是最终权威来源，不应覆盖或破坏。
- chunk RAG 索引是可重建的查询加速层，不是唯一事实来源。

## 当前 notebook 覆盖范围

- `Artiq Program`: 2 页
- `Equipment Purchasing`: 20 页
- `Yb ultracold ion-atom hybrid`: 22 页

## Web UI

本地调试：

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/serve_lab_senior_brother.py
```

启动后打开：

```text
http://127.0.0.1:8765/
```

网页端默认不作为日常入口，也不默认公网暴露。

## 公网隧道注意事项

- Web server 支持通过 `--access-user` / `--access-password` 或环境变量 `LAB_SENIOR_BROTHER_USER` / `LAB_SENIOR_BROTHER_PASSWORD` 开启 Basic Auth。
- ngrok 只负责把公网 URL 转发到本地 `8765` 端口。
- 运行时密码、ngrok authtoken、API key 都只能放在私有本地文件，不能放进公开仓库。
- 公网 URL 会让远程用户访问查询 UI，也可能消耗 Qwen API 额度，只能分享给可信用户。

## 绝对不要公开

不要暴露 `/Volumes/ZZLab_AI/Key/` 里的任何凭据。
