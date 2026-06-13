# ZZLab AI 中文文档索引

这份索引给人类阅读。英文原文和代码仍是机器执行时的权威来源；中文版本用于快速理解项目在做什么、怎么维护、哪里不能碰。

## 先读这几个

- [中文总览](README_zh.md): 项目是什么、大师兄是什么、有哪些入口。
- [项目协作规则](AGENTS_zh.md): 新 AI 或人接手时必须遵守的工作规则。
- 当前交接快照中文私有版：`Document/Human_Docs_ZH/PROJECT_HANDOFF_zh.md`。这个文件只在共享盘私有 `Document/` 目录，不进入公开 GitHub。
- 英文当前交接快照：`PROJECT_HANDOFF.md`。这是自动交接系统维护的当前状态源文件，私有。

## 大师兄和 RAG

- [实验室大师兄中文说明](AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/SKILL_zh.md): 大师兄怎么查 notebook、Telegram/Lark/email 怎么接入、维护时要做什么。
- [RAG 架构中文说明](AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/references/rag_architecture_zh.md): 当前 RAG、目标 RAG、RAGFlow/AnythingLLM 选择。
- [数据源中文说明](AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/references/data_sources_zh.md): notebook、HTML、蒸馏目录和索引在哪里。

## 记忆包和交接

- [记忆包 manifest 中文说明](AI_Agent/Lab_Memory_Agent/manifest_zh.md): `manifest.yaml` 里的路径、策略和数据类型是什么意思。
- [自动交接中文说明](AI_Agent/Lab_Memory_Agent/skills/auto-handoff/SKILL_zh.md): 每次显著工作后如何更新交接、同步 GitHub、刷新大师兄自我认知。
- [通用 lab-memory skill 中文说明](AI_Agent/Lab_Memory_Agent/skills/lab-memory/SKILL_zh.md): 如何读写可迁移实验室记忆条目。

## Notebook 流水线

- [HTML pipeline 中文说明](AI_Agent/Lab_Memory_Agent/scripts/notebook_pipeline/README_zh.md): OneNote/HTML 导出、索引、每日增量更新、蒸馏流程。
- [Inbox 中文说明](AI_Agent/Lab_Memory_Agent/inbox/README_zh.md): 临时导入资料该放哪里、支持哪些格式。

## 维护原则

- 不把密码、token、cookie、API key、验证码写进文档或 GitHub。
- `Document/`、`Key/`、每日聊天/邮件归档和生成索引默认是私有数据。
- 公开 GitHub 只放可复用代码、示例配置和不含私密内容的说明文档。
- 如果中文文档和代码行为冲突，以代码、配置和英文源文档为准，然后更新中文文档。
