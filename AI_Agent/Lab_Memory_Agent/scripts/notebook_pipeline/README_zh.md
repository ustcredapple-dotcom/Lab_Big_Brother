# Lab Notebook HTML Pipeline 中文说明

这个目录保存当前 lab notebook 工作流中可以公开的代码。核心原则是：HTML 优先，原始 archive 不动，生成索引和蒸馏结果都可以重建。

## 当前流程

1. 原始 OneNote archive 保存在 `Document/Lab_Notebook_Original_2026-06-11/`。
2. 用修补过的 `one2html` 路径把活跃 OneNote sections 转成本地 HTML。
3. HTML 树保存在 `Document/Lab_Notebook_Processing/html/active/`。
4. 用 `build_html_notebook_index.py` 生成 `HTML_INDEX.html` 和 `HTML_MANIFEST.json`。
5. 人类和 AI 都直接读 HTML。
6. 可选：用 `distill_html_locally.py` 生成本地摘要，不调用外部 API。
7. 经项目负责人批准后，用 `distill_html_with_deepseek.py` 生成 Qwen 蒸馏总览。脚本名保留 `deepseek` 是为了兼容旧流程。

## 刷新 HTML 索引

```bash
python build_html_notebook_index.py \
  --html-root /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/Lab_Notebook_Original_2026-06-11 \
  --index /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/HTML_INDEX.html \
  --manifest /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/HTML_MANIFEST.json
```

## 生成本地蒸馏

```bash
python distill_html_locally.py \
  --html-root /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/Lab_Notebook_Original_2026-06-11 \
  --manifest /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/HTML_MANIFEST.json \
  --output-dir /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html_distilled
```

## 生成 Qwen 蒸馏

```bash
python distill_html_with_deepseek.py \
  --html-root /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/Lab_Notebook_Original_2026-06-11 \
  --manifest /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/HTML_MANIFEST.json \
  --output-dir /Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html_deepseek_distilled
```

## 每日增量更新

```bash
python daily_notebook_update.py
```

每日 updater 会：

- 可选地先运行一个私有 pre-sync 命令。
- 可选地把新的 incoming HTML 导出合并到 active HTML 树。
- 跳过重复页面，避免同一页存两遍。
- 重建 `HTML_INDEX.html` 和 `HTML_MANIFEST.json`。
- 把当前 manifest 和页面文本与前一天快照对比。
- 在 `Document/Lab_Notebook_Processing/daily_updates/changes/` 下写带时间戳的 JSON/Markdown 变更日志。
- 只把新增或修改页面发给 Qwen。
- 把更新后的页面记录合并进 `html_deepseek_distilled/DEEPSEEK_DISTILLATION.json/html`。

私有每日配置示例：

```json
{
  "pre_sync_command": "",
  "incoming_html_root": "/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/incoming",
  "cleanup_incoming_html": true
}
```

`incoming_html_root` 应该是临时 one2html 风格导出树。`cleanup_incoming_html=true` 时，确认与 active 内容重复的 incoming 页面和附件会被清理；active HTML 树仍是唯一长期可读副本。

首次 baseline 建议不调用外部蒸馏：

```bash
python daily_notebook_update.py --no-deepseek
```

## 输出文件

- `HTML_INDEX.html`: 人类和 AI 友好的页面索引。
- `HTML_MANIFEST.json`: 机器可读元数据，包含 section、page、timestamp、source ID、hash 和文本预览。
- `html_distilled/LOCAL_DISTILLATION.html`: 不调用外部 API 的本地摘要。
- `html_distilled/LOCAL_DISTILLATION.json`: 机器可读本地摘要。
- `html_deepseek_distilled/DEEPSEEK_DISTILLATION.html`: Qwen 生成的 notebook digest，路径名保留旧称。
- `html_deepseek_distilled/DEEPSEEK_DISTILLATION.json`: 机器可读 Qwen 蒸馏结果。
- `daily_updates/`: 私有每日快照、文本 diff、日志和增量状态。

## 安全规则

- 永远不要覆盖原始 OneNote archive。
- 不要把凭据或 notebook 分享秘密复制进代码、文档、HTML、日志或 GitHub。
- 私有 notebook 内容和生成 HTML 不进入公开仓库。
- 保留 HTML 树里的相对链接，确保附件可读。
- 只有项目负责人明确批准时，才把 notebook 内容发给外部 API。
- 不要把云 token、密码或分享秘密放进 daily updater 配置或日志。
