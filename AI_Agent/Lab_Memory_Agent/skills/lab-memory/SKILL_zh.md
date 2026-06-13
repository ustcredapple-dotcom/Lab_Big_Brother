# Lab Memory 中文说明

`lab-memory` 是通用实验室记忆包的操作指南。它比“大师兄”更底层，关心的是：证据在哪里、结构化记忆条目怎么写、索引怎么重建。

## 记忆包结构

- `entries/`: 结构化记忆条目。
- `sources/`: 原始证据。
- `indices/`: 可重建索引。
- `manifest.yaml`: 路径和策略总表。

## 使用流程

1. 先读 `manifest.yaml`，理解路径和策略。
2. 如果 `indices/memory_index.jsonl` 存在，先查索引。
3. 只加载最相关的 `entries/*.md`。
4. 用 `source_refs` 引用证据；必要时去 `sources/` 查看原始材料。
5. 如果记录缺失、过旧、低置信度或互相冲突，回答时明确不确定。

## 回答规则

- 先给直接答案。
- 事实性陈述要引用 memory entry ID 或来源路径。
- `hypothesis` 和 `confidence: low` 不能当成确定事实。
- 不要忽略 `status: superseded`，如果有新条目应优先使用新条目。
- 两条记录冲突时，报告冲突，不要编一个折中答案。
- 不要暴露敏感内容，除非用户已授权且记忆包策略允许。

## 添加新记忆

1. 把原始来源保存在 `sources/`。
2. 在 `entries/` 创建小而清楚的记忆条目。
3. 包含稳定的：

   - `id`
   - `type`
   - `status`
   - `date`
   - `source_refs`
   - `confidence`
   - `summary`

4. 重建索引：

```bash
python3 scripts/rebuild_index.py
```

## 更新已有记忆

- 优先添加新条目，并把旧条目标成 `superseded`。
- 保留旧记录用于审计。
- 只要事实仍依赖某个来源，就不要删掉 source reference。
