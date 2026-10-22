---
name: delivery
description: 正式交付业务编排。只负责阶段推进、用户确认和交付物汇总；具体意图、KB、批量回归能力通过其他 skill 的 interfaces 调用。
requires:
  skills: [kb-builder]
---

# Delivery

签约后正式交付编排 skill。职责是串联意图创建、知识库搭建和回归测试，不复制其他 skill 的内部职责。

## 边界原则

- 只调用其他 skill 暴露的 `interfaces/` 能力。
- 不在本 skill 维护 intent 创建、X-Token patch、KB crawl、QA 上传、批测 runner 的内部实现。
- Delivery 顶层状态只保存跨阶段引用。
- 每个阶段完成后先向用户确认，再进入下一阶段。

## 必读文件

| 阶段 | Interface |
|---|---|
| 意图分类 | `/skills/delivery/interfaces/classify.md` |
| Delivery agent / 策略创建 | `/skills/delivery/interfaces/create-agents.md` |
| 知识库，必做或确认已有 | `/skills/kb-builder/interfaces/web-kb.md` / `/skills/kb-builder/interfaces/qa-upload.md` |
| 回归测试 | `/skills/delivery/interfaces/delivery-test.md` |

## 顶层状态

状态文件：`/workspace/state/delivery/progress.json`。

每次开始处理 Delivery 前，先运行：

```bash
npx --yes @shulex/cxclawctl@latest script skills/delivery/scripts/plan.py --init
```

阶段完成后用 `plan.py` 更新顶层状态，例如：

```bash
npx --yes @shulex/cxclawctl@latest script skills/delivery/scripts/plan.py \
  --status agents_created \
  --set intent.created_log_path=/workspace/outputs/delivery/created_<ts>.json
```

需要汇总当前交付物时运行：

```bash
npx --yes @shulex/cxclawctl@latest script skills/delivery/scripts/render_summary.py
```

```json
{
  "status": "empty | classified | agents_created | kb_done | regression_done | done",
  "tenant": "",
  "brand_name": "",
  "intent": {
    "progress_path": "/workspace/state/delivery/progress.json",
    "classification_report_path": "",
    "classification_excel_path": "",
    "created_log_path": ""
  },
  "kb": {
    "required": true,
    "source_url": "",
    "directory_plan_path": "",
    "qa_plan_path": "",
    "upload_result_path": ""
  },
  "regression": {
    "input_path": "",
    "touch_point": "LIVE_CHAT",
    "results_path": "",
    "report_html": "",
    "report_md": ""
  },
  "updated_at": ""
}
```

## 起点判断

| 用户消息含 | 起点 |
|---|---|
| 「补充知识 / 提取 QA / 加进 KB」+ 知识源附件 | 知识库 |
| 「建知识库目录 / 搭知识库」+ 网站/知识来源 URL | 知识库 |
| 「上传 qa_plan.json」 | 知识库上传 |
| 「批量回归 / 跑测试」+ 测试用例 xlsx 或意图列表 | 回归测试 |
| 给了 xlsx 路径 | 意图分类 |
| 「接着上次」 | 读 `/workspace/state/delivery/progress.json` |

如果只输入 `/delivery` 或信息不足，询问：

```text
您想从哪个阶段开始？

1. 阶段一：意图分类与意图创建
2. 阶段二：知识库搭建
3. 阶段三：批量回归测试

请告诉我从哪一步开始以及已有素材路径。
```

## 流程

详见 `/skills/delivery/references/flow.md`。

## 可恢复缺口

Delivery 的固定广场 agent 只是默认来源，不是硬阻塞。执行创建脚本后如果 state 或 created log 出现
`preset_agent_missing` / `preset_agent_errors`，必须向用户说明缺失项，并询问是从零新建 CHAT_FLOW
agent，还是使用其他现有 agent 替代；不要直接报告“预置 Agent 不存在，必须开发修复后才能继续”。
