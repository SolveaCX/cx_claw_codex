# 变量系统字段

变量系统字段为策略条件、工具参数、CHAT_FLOW 节点和 Agent prompt 提供结构化上下文。配置事实源是 Tars；CHAT_FLOW 画布的字段接口只用于画布兼容，不能代替这里的管理流程。

## 查询与初始化

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher api get-ai-field-guide --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api list-managed-ai-fields --page 1 --page-size 50 --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api get-managed-ai-field --id <field_id> --pretty
```

若 `get-ai-field-guide` 显示未初始化，先说明将创建系统预装字段，得到确认后再执行：

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher api initialize-ai-fields --pretty
```

## 创建与更新

先列出或读取已有字段，展示名称、描述、数据类型、选项、应用范围和预期用途，再请求确认。确认后的 JSON 写入 `/workspace/state/solvea-kit/`，通过 CLI 提交：

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher api create-managed-ai-field \
  --data-file /workspace/state/solvea-kit/ai_field_create.json --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api update-managed-ai-field \
  --data-file /workspace/state/solvea-kit/ai_field_update.json --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api toggle-managed-ai-field --id <field_id> --pretty
```

常用字段：`name`、`description`、`dataType`、`aiFieldValueDTOS`（单选/多选选项）、`applyRang`、`useAgent`、`parentId`。不要猜测数据类型编码或应用范围；先读取同租户同类型字段作为模板。

## 删除

删除前必须先读取详情和列表中的 `usedIn`。字段已被使用时，不承诺可删除；先说明影响并引导用户迁移 Agent、策略、模板或 CHAT_FLOW 引用。仅在字段未使用且用户确认后执行：

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher api delete-managed-ai-field --id <field_id> --pretty
```

## 使用场景

| 场景 | 说明 |
|---|---|
| 策略条件 | 条件实体或 metadata 依赖变量系统字段提取结果 |
| 工具参数 | 工具 requestParam 可从 LLM / METADATA / 固定值等来源取值 |
| CHAT_FLOW | QUESTION(VARIABLE)、IF_ELSE、TOOL、VARIABLE_PROCESS 等节点会引用变量系统字段 |
| AGENT / REPLY prompt | 通过 `ai_field_ids` 引用变量系统字段 |

## 边界

- 排查变量提取异常走 `shulex-support` Agent 会话诊断场景的 M4 变量系统字段链路。
- CHAT_FLOW 内如何引用变量、如何把上游输出桥接到变量系统字段，走 `agent-builder` 的 chatflow 文档。
