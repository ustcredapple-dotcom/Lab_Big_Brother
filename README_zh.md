# Lab Big Brother 中文总览

这是 ZZLab 的可迁移、可审计 AI 记忆基础设施。它的目标很朴素：让实验室的 notebook、聊天记录、邮件、PDF、说明书和决策记录变成一个可查询、可维护、能交接给下一个 AI 的知识系统。

项目把证据、结构化记忆、搜索索引和 AI 操作流程分开保存。这样换电脑、换 AI、换入口时，不需要依赖某一次聊天历史。

## 目录结构

```text
AI_Agent/Lab_Memory_Agent/
  config/       示例集成配置
  entries/      带来源的结构化记忆条目
  inbox/        临时放导出资料的入口
  indices/      可重建搜索索引
  schemas/      记忆条目格式
  scripts/      摄入、索引、搜索、notebook 同步脚本
  skills/       给 AI 使用的操作流程
  sources/      原始证据
```

## 实验室大师兄

`AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/` 是 GPT/Codex/Telegram/Lark 面向实验室 notebook 的 RAG 接口。

当你问“之前做过吗”“怎么测”“参数是多少”“谁负责”“证据在哪”时，大师兄会：

1. 从 notebook HTML、Telegram/Lark/email 记录、PDF 和文本附件里检索小证据块。
2. 用 Qwen embedding + 词法召回做混合检索。
3. 让 Qwen rerank 判断哪些证据能直接回答问题。
4. 基于证据给出短回答，并在需要时附 HTML 详情。

旧的加权关键词搜索只保留作调试，正常使用默认走 RAG。

示例：

```bash
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/query_lab_notebook.py \
  "我们之前做过 DDS 验收吗？怎么做的？" \
  --include-source-snippets
```

## Web UI 状态

网页端大师兄默认已经退役，只保留给本地调试。日常入口应该用 Codex、Telegram、Lark 或 Gmail 转发。

本地调试时可以运行：

```bash
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/serve_lab_senior_brother.py
```

然后打开 `http://127.0.0.1:8765/`。

不要随便把网页端通过 ngrok 暴露到公网。只有用户明确要求时，才用 Basic Auth 保护后再开公网隧道。

## 自我认知刷新

每次显著更新后，运行：

```bash
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/update_self_knowledge.py
```

这个脚本会让大师兄重新蒸馏自己的代码、文档、交接状态和服务配置，写进私有自我说明书和 notebook 的 `Lab Big Brother System` 部分。

## 每日 notebook 维护

```bash
python3 AI_Agent/Lab_Memory_Agent/scripts/notebook_pipeline/daily_notebook_update.py
```

每日更新流程会合并新的 HTML 导出、跳过重复页面、更新 HTML manifest、比较每日差异，只把新增或改动页面送给 Qwen 蒸馏，最后合并进现有 distilled index。

首次建立 baseline 时建议：

```bash
python3 AI_Agent/Lab_Memory_Agent/scripts/notebook_pipeline/daily_notebook_update.py --no-deepseek
```

## Chunk RAG 索引

```bash
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/rag_query_engine.py --build-index
```

私有 chunk 索引在：

```text
/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/rag_chunk_index/
```

Notebook、Telegram、Lark 和 email 的每日 digest 会在蒸馏后刷新这个索引。索引和查询详情渲染前都会脱敏，避免泄露密码、token、API key、验证码。

## RAGFlow 和 AnythingLLM

RAGFlow 是未来可考虑的重型 RAG 后端，但当前 Mac 没有 Docker runtime，而且机器是 ARM64，暂不作为默认路径。

AnythingLLM 是更轻的现成 RAG 候选。代码已经有可选 `rag_engine=anythingllm` 适配器，会调用 `/api/v1/workspace/{slug}/chat` 的 query 模式。只有 AnythingLLM 服务安装、导入、隐私设置和回归测试都通过后，才应该切换线上入口。

最小配置示例：

```json
{
  "rag_engine": "anythingllm",
  "anythingllm_base_url": "http://127.0.0.1:3001/api",
  "anythingllm_workspace_slug": "zzlab",
  "anythingllm_mode": "query"
}
```

API key 放在 `Key/AnythingLLM API Key.txt`，或通过 `ANYTHINGLLM_API_KEY` 提供。

## Telegram 入口

```bash
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/telegram_lab_senior_brother.py
```

支持：

- `/id`: 查看当前 chat ID。
- `/ask 问题` 或 `查 问题`: 查询实验室记忆。
- `/note 内容` 或 `记 内容`: 记一条笔记。
- `/allow CHAT_ID`: 给已授权用户添加新 Telegram ID。
- `开始记`: 进入连续记录模式。
- `停止记`: 回到默认查询模式。
- `/status`、`/help`。

Telegram 默认不长期保存普通查询、寒暄和文件请求。只有笔记、上传文件、模式变更和管理操作会作为 durable record 保存。短期追问上下文只存在私有 state JSON 中，用来理解“那具体怎么测”这类追问。

## Lark 入口

```bash
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/lark_lab_senior_brother.py
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/lark_daily_digest.py
```

Lark 使用国际版 `https://open.larksuite.com` 和 WebSocket 事件连接，不需要 ngrok。bot 被拉进群后默认记录群消息；群里只有 @ 大师兄或使用命令时才回复。

要接收群里每一条消息，Lark app 需要授权官方 scope `Read all messages in associated group chat` 并订阅 `Receive message` 事件。

诊断 Lark 状态：

```bash
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/lark_lab_senior_brother.py --check-online
```

`tenant_access_token_ok=true` 说明 App ID/App Secret 正确；还必须看到 `bot_enabled=true`，应用才能被拉进聊天、接收消息事件、以大师兄身份回复。如果 Lark 返回 `app do not have bot`，需要在 Lark developer console 里启用 Bot/机器人能力，并重新发布应用。

## Gmail 转发入口

```bash
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/email_ingest.py
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/email_daily_digest.py
```

Gmail app password 只能存在私有 `Key/gmail_app_password.txt`，不能进入 GitHub。邮件正文、附件、PDF 和文本类文件会被归档，夜间 digest 会把有价值的内容按主题补进 notebook 蒸馏结果。

## 快速开始

```bash
cd AI_Agent/Lab_Memory_Agent
python3 scripts/rebuild_index.py
python3 scripts/search_memory.py "memory framework"
```

导出的 TXT、Markdown、HTML、MHTML、DOCX 或 PDF 可以先放到 `inbox/`，然后运行：

```bash
python3 scripts/ingest_exports.py
python3 scripts/rebuild_index.py
```

## 自动交接

`auto-handoff` skill 会维护一份当前快照和一份追加式工作日志。显著工作后，它会更新交接、同步 GitHub，并刷新大师兄自我认知。

公开 GitHub 只放可复用代码和公共文档。原始 notebook、真实记忆条目、生成索引、本地配置、详细工作日志和凭据默认不公开。

## 代码仓库

[ustcredapple-dotcom/Lab_Big_Brother](https://github.com/ustcredapple-dotcom/Lab_Big_Brother)
