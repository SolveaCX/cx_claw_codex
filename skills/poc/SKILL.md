---
name: poc
description: 售前 POC 业务编排。只负责阶段推进、用户确认和交付物汇总；具体意图、Agent、KB、批测能力通过其他 skill 的 interfaces 调用。
requires:
  skills: [agent-builder, kb-builder]
---

# POC

执行命令时，将 `<PLUGIN_ROOT>` 替换为当前 CXClaw 插件根目录，并统一通过 `node "<PLUGIN_ROOT>/plugin-cli.mjs"` 调用与插件同版本的 CLI；禁止直接调用 npm `latest`。

售前 POC 编排 skill。职责是把现有原子能力串成业务流程，不复制其他 skill 的内部职责。

## 边界原则

- 只调用其他 skill 暴露的 `interfaces/` 能力，不读取或复述其他 skill 的完整内部流程。
- 不在本 skill 维护 intent 创建、chatflow graph、KB crawl、QA 上传、批测 runner 的实现细节。
- 顶层状态只保存跨阶段引用，不复制底层 skill 的完整 state。
- 每个会产生外部写入或业务结果变化的阶段完成后，先向用户确认，再进入下一阶段。

## 必读文件

按需读取以下 interface：

| 阶段 | Interface |
|---|---|
| 意图分类 | `/skills/poc/interfaces/classify.md` |
| POC agent / 策略创建 | `/skills/poc/interfaces/create-agents.md` |
| 兜底 chatflow agent | `/skills/agent-builder/interfaces/fallback-chatflow.md` |
| 知识库，可选 | `/skills/kb-builder/interfaces/web-kb.md` / `/skills/kb-builder/interfaces/qa-upload.md` |
| POC 标准 KB 目录规范 | `/skills/poc/references/kb-directory.md` |
| POC 批测与手册 | `/skills/poc/interfaces/poc-test.md` |

## 顶层状态

状态文件：`/workspace/state/poc/progress.json`。

每次开始处理 POC 前，先运行：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" poc plan --init
```

阶段完成后用 `delivery plan` 更新顶层状态，例如：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" poc plan \
  --status business_agents_created \
  --set intent.created_log_path=/workspace/outputs/poc/created_<ts>.json
```

需要汇总当前交付物时运行：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" poc render-summary
```

状态只记录跨阶段引用：

```json
{
  "status": "empty | classified | business_agents_created | fallback_agent_created | fallback_strategy_linked | kb_done | cases_ready | test_done | done",
  "tenant": "",
  "brand_name": "",
  "brand_website": "",
  "intent": {
    "progress_path": "/workspace/state/poc/progress.json",
    "created_log_path": "",
    "classification_report_path": "",
    "classification_excel_path": ""
  },
  "fallback_agent": {
    "agent_id": "",
    "agent_name": "",
    "created": false
  },
  "kb": {
    "enabled": false,
    "source_url": "",
    "directory_plan_path": "",
    "qa_plan_path": "",
    "upload_result_path": ""
  },
  "test": {
    "agents": [],
    "cases_json_path": "",
    "results_path": "",
    "manual_path": ""
  },
  "updated_at": ""
}
```

## 起点判断

按用户消息判断起点，命中即跳；都没命中时询问用户从哪个阶段开始。

| 用户消息含 | 起点 |
|---|---|
| 「指定 agent / 用现有 agent / 跳过意图 / 直接测试」 | 批测与手册 |
| 「补充知识 / 提取 QA / 加进 KB」+ 知识源附件 | 知识库 |
| 「建知识库目录 / 搭知识库」+ 网站/知识来源 URL | 知识库 |
| 「上传 qa_plan.json」 | 知识库上传 |
| 给了 xlsx 路径 | 意图分类 |
| 「接着上次」 | 读 `/workspace/state/poc/progress.json`，缺失时再看底层状态引用 |

如果只输入 `/poc` 或信息不足，询问：

```text
您想从哪个阶段开始？

1. 阶段一：意图分类与场景创建
2. 阶段二：知识库搭建（可选）
3. 阶段三：批量测试 + POC 手册

请告诉我从哪一步开始以及已有素材路径。
```

## 流程

详见 `/skills/poc/references/flow.md`。

## 可恢复缺口

POC 的预置业务 agent 只是默认来源，不是硬阻塞。执行创建脚本后如果 state 或 created log 出现
`preset_agent_missing` / `preset_agent_errors`，必须向用户说明缺失项，并询问是从零新建 CHAT_FLOW 业务
agent，还是使用其他现有 agent 替代；不要直接报告“预置 Agent 不存在，必须开发修复后才能继续”。
