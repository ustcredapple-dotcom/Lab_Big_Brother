# 实验室大师兄中文说明

大师兄是实验室 notebook 和通信记录的 RAG 管家。它的工作不是机械搜关键词，而是先找证据、再让 Qwen 基于证据回答，并在证据不足时明确说不知道。

## 核心查询流程

事实类问题必须先跑查询，不要凭记忆回答。

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/query_lab_notebook.py \
  "USER QUESTION" \
  --include-source-snippets \
  --format json
```

默认引擎是 `--engine rag`：

- 加载私有 chunk 索引 `/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/rag_chunk_index/`。
- 用 Qwen embedding 和词法召回找小证据块。
- 让 Qwen rerank，判断哪些 chunk 能直接回答。
- 用选中的证据生成回答。

旧的关键词引擎只用于调试：

```bash
--engine lexical
```

## 回答格式

回答实验室历史问题时，应该包含：

- 结论：做过、可能做过、不清楚，或没找到证据。
- 做法：流程、参数、设备、人员或决策。
- 证据：页面标题和 HTML 路径。
- 注意事项：不确定性、缺失数据、建议继续看的来源。

Telegram/Lark 上可以更短，但仍然要自然、可追溯、不要机械写“置信度 high”。

## 数据源

需要路径和层级时看：

- `references/data_sources.md`
- `references/data_sources_zh.md`

核心索引：

```text
/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html_deepseek_distilled/DEEPSEEK_DISTILLATION.json
/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/rag_chunk_index/chunks.jsonl
```

源 HTML：

```text
/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/Lab_Notebook_Original_2026-06-11/
```

## 维护规则

新 notebook HTML 导入后：

1. 用 `build_html_notebook_index.py` 刷新 `HTML_INDEX.html` 和 `HTML_MANIFEST.json`。
2. 用 `distill_html_with_deepseek.py` 刷新 Qwen 蒸馏结果。脚本名保留 `deepseek` 是为了兼容旧流程。
3. 必要时重建 chunk RAG：

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/rag_query_engine.py --build-index
```

4. 用代表性问题测试检索质量。
5. 显著改动后更新 `PROJECT_HANDOFF.md` 和 `WORK_LOG.md`。
6. 刷新大师兄自我认知：

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/update_self_knowledge.py
```

日常增量维护优先用：

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/scripts/notebook_pipeline/daily_notebook_update.py
```

## Web UI

网页端默认退役，只保留本地调试。不要主动启动或公开暴露，除非用户明确要求。

本地调试：

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/serve_lab_senior_brother.py
```

打开 `http://127.0.0.1:8765/`。

不要把 ngrok authtoken、Basic Auth 密码、Qwen key 或 notebook 分享秘密写进 skill、GitHub 或交接文件。

## RAG 后端

当前生产路径是本地 chunk RAG。

RAGFlow 是未来重型后端候选，但当前 Mac 没有 Docker runtime，且 ARM64 与公开预构建镜像不完全匹配，所以不作为默认。

AnythingLLM 是更轻的现成后端候选。`rag_query_engine.py` 已支持：

```json
{
  "rag_engine": "anythingllm",
  "anythingllm_base_url": "http://127.0.0.1:3001/api",
  "anythingllm_workspace_slug": "zzlab",
  "anythingllm_mode": "query"
}
```

只有安装、导入、隐私设置和回归问题都通过后，才切线上 Telegram/Lark/email。

## Telegram

启动：

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/telegram_lab_senior_brother.py
```

支持：

- `/id`
- `/ask QUESTION` 或 `查 QUESTION`
- `/note TEXT` 或 `记 TEXT`
- `/allow CHAT_ID`
- `开始记`
- `停止记`
- `/status`
- `/help`

Telegram 默认不长期保存普通查询和寒暄。只持久化笔记、上传文件、模式变化和管理操作。短期上下文保存在私有 state JSON 中，用来理解连续追问。

上传文件会按日期和发送者归档。PDF、文本、Markdown、HTML、CSV/JSON 会抽文本或生成 HTML 预览；图片会用 Qwen vision 生成预览；STEP/EXE 等二进制工程文件只存元数据。

## Lark

启动：

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/lark_lab_senior_brother.py
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/lark_daily_digest.py
```

Lark 使用国际版 `https://open.larksuite.com`，通过 WebSocket 收事件，不需要 ngrok。

bot 被拉进群后默认记录可收到的群消息。群里只有 @ 大师兄或显式命令时才回复；私聊可以直接回复。

## Gmail

启动：

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/email_ingest.py
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/email_daily_digest.py
```

Gmail app password 只能放在：

```text
/Volumes/ZZLab_AI/Key/gmail_app_password.txt
```

缺少密码文件时，ingester 应该干净退出，而不是阻塞其他服务。

## 安全边界

- 不要输出或提交任何 key、密码、cookie、token、验证码。
- Qwen 蒸馏只是导航层，不是最终真相。
- 源 HTML 和原始 archive 才是证据层。
- 找不到证据时自然说不知道，不要硬答。
