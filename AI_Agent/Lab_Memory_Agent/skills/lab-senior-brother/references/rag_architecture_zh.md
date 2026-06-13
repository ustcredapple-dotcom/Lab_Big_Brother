# 实验室大师兄 RAG 架构

## 这里的 RAG 是什么意思

RAG 指的是检索增强生成，也就是：

1. 先从实验室记忆库里找出相关证据。
2. 再让大模型基于这些证据推理。
3. 最后给出有出处、能追溯、并且知道不确定性的回答。

对实验室大师兄来说，RAG 不是一个关键词搜索框，而是一条证据流水线。它要回答的是这类问题：之前做过吗、怎么做的、参数是多少、谁负责、证据在哪。

## 当前状态

系统现在已经有一套共享的本地 chunk-level RAG 流程：

- 原始资料会以 HTML notebook 页面和每日 Telegram/Lark/email 归档的形式保存。
- Qwen 会把页面蒸馏成紧凑的 JSON/HTML 目录。
- `rag_query_engine.py` 会在 `/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/rag_chunk_index/` 下建立私有本地 chunk 索引。
- Notebook 页面、源 HTML、Telegram/Lark 记录、Gmail 记录、PDF、文本文件、Markdown/HTML/CSV/JSON，以及 Qwen vision 生成的图片预览，都会被切成小证据块。
- 检索使用 Qwen `text-embedding-v4` 语义向量和加权词法召回的混合方式；然后 Qwen 会对候选证据块重新排序，判断哪些能直接回答问题，并生成短回答。
- Telegram、Lark 和 CLI 都调用同一个共享 chunk RAG 引擎。旧的 page-level Qwen 证据选择器只作为 chunk RAG 失败时的 fallback。
- 每日 notebook、Telegram、Lark、email digest 脚本会在新记忆蒸馏后刷新 chunk 索引。
- 索引前和生成查询详情 HTML 前都会做敏感信息脱敏，避免暴露密码、token、API key、验证码等内容。

旧的加权关键词搜索仍然保留，但只用于调试，例如：

```bash
query_lab_notebook.py --engine lexical
```

## 目标架构

成熟版 RAG 系统应该长这样：

1. 数据摄入

   - 原始文件保持私有且不被改写。
   - 可读资料转成干净的文本或 HTML。
   - 保存来源路径、来源渠道、日期、作者或发送者、页面标题、附件路径和内容 hash。

2. 切块

   - 把 notebook 页面、digest、邮件正文、Lark/Telegram 记录、PDF 和文本附件切成证据块。
   - 使用稳定的 chunk ID。
   - 为实验流程和参数保留足够上下文。

3. 建索引

   - 在私有生成记忆区保存可重建的 chunk 索引。
   - 每个 chunk 应包含正文、摘要、标签、主题分区、时间戳、来源路径和来源 hash。
   - 如果配置了批准使用的 embedding provider，就加入语义向量。
   - 保留词法 fallback，用来精确匹配零件号、日期、供应商名和文件名。

4. 检索

   - 使用混合检索：语义向量搜索 + 词法/BM25 风格的精确匹配。
   - 扩展实验室常见别名，例如：“烤真空” -> “真空烘烤”，“finess” -> “finesse”，“腔精细度” -> “cavity finesse”。
   - 返回候选证据块，而不是只返回整页。

5. 重排序

   - 让 Qwen 对候选 chunk 做 rerank，判断哪些能直接回答当前问题。
   - 如果匹配很弱，就拒绝回答，不要硬把无关内容拼成答案。

6. 回答

   - 给出简洁自然的回答。
   - 引用来源标题和路径。
   - 证据不存在或含糊时，说“师兄我也不知道”。
   - 永远不要暴露凭据或无关个人数据。

7. 反馈

   - 记录失败查询和漏掉的别名，但不要保存闲聊。
   - 用这些失败案例改进切块、别名表和主题分类。

## 运行规则

所有面向用户的入口都应该调用同一个 RAG 引擎：

- Codex skill / CLI
- Telegram bot
- Lark bot
- 如果以后重新启用本地 debug web UI，也应该走同一个引擎

不要让一个入口使用纯机械关键词搜索，而另一个入口使用 Qwen 证据选择。这样会导致 Telegram 上的大师兄和 Codex 里的大师兄表现不一致。

## RAGFlow 选项

RAGFlow 是未来可考虑的重型后端。它提供 UI、文档解析、模板切块、多路召回、rerank、基于证据的引用和 API。

但它应该被当作可选后端，而不是立刻替换当前轻量本地 RAG。原因是：当前 Mac 没有安装 Docker runtime，并且机器是 ARM64，而 RAGFlow 公开预构建 Docker 镜像主要偏 x86。官方自托管前提包括 Docker/Compose、至少 16 GB 内存和至少 50 GB 磁盘空间。

推荐接入路径：

1. Telegram/Lark/email 生产环境继续默认使用本地 chunk RAG。
2. 只有在 Docker Desktop、OrbStack 或 Colima 安装并验证后，再部署 RAGFlow。
3. 把 RAGFlow 当实验后端，喂给它同一套规范化 HTML/text 导出。
4. 在 `query_notebook` 里增加后端开关：默认 `local_chunk`，只有 RAGFlow API 配置好且健康时才切到 `ragflow`。
5. 在切换任何线上入口前，用回归问题对比回答质量。

## AnythingLLM 选项

AnythingLLM 是比 RAGFlow 更轻的现成 RAG 后端候选。它提供桌面 app、Docker/自托管路径、开发者 API、内置文档流水线、默认 LanceDB 向量存储、多种 LLM/embedder 集成、来源引用、agent，以及可选 telemetry 控制。

如果实验室想要一个现成 RAG UI 和 API，但不想一上来部署完整 RAGFlow 栈，AnythingLLM 是更适合作为近期测试的候选。

已经实现的适配器：

- `rag_query_engine.py` 支持 `rag_engine=anythingllm`。
- 默认调用 AnythingLLM workspace chat API：`/api/v1/workspace/{slug}/chat`，并使用 `mode=query`，让回答尽量基于 workspace 里的来源证据。
- 密钥读取位置包括：`anythingllm_api_key`、`ANYTHINGLLM_API_KEY`、`anythingllm_api_key_path`，或 `Key/AnythingLLM API Key.txt`。
- 运行时必要配置包括：`anythingllm_base_url`、`anythingllm_workspace_slug` 和 API key。默认 base URL 是 `http://127.0.0.1:3001/api`。

推荐接入路径：

1. 在 AnythingLLM 安装并通过回归测试前，本地 chunk RAG 继续作为生产路径。
2. Telegram/Lark/email 集成应优先使用 AnythingLLM Docker/API 或 bare-metal server 模式。桌面 app 适合人类浏览，但不适合作稳定服务后端。
3. 如果处理私有实验室材料，需要关闭 telemetry 或完成隐私设置检查。
4. 喂给 AnythingLLM 的应该是现有流水线生成的规范化 HTML/text 导出，而不是原始密钥或私有配置。
5. 只有在健康检查、摄入、检索、引用和延迟都验证过后，才把线上配置切到 `rag_engine=anythingllm`。

最小配置示例：

```json
{
  "rag_engine": "anythingllm",
  "anythingllm_base_url": "http://127.0.0.1:3001/api",
  "anythingllm_workspace_slug": "zzlab",
  "anythingllm_mode": "query"
}
```

## 回归测试问题

每次改检索、切块、索引或后端切换后，都应该用这些问题测试：

- `cavity 的 finesse 是多少`
- `我们烤过真空吗`
- `DDS 怎么验收`
- `实验室有几台电脑`
