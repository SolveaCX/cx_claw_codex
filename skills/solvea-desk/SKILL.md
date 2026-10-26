---
name: solvea-desk
description: 查询、分析和管理 Shulex Desk / Tars 工单；支持当前工单筛选、历史报表及工单标签查询、绑定和解绑。
requires:
  libs: []
---

# Shulex Desk

执行命令时，将 `<PLUGIN_ROOT>` 替换为当前 CXClaw 插件根目录，并统一通过 `node "<PLUGIN_ROOT>/plugin-cli.mjs"` 调用与插件同版本的 CLI；禁止直接调用 npm `latest`。
需要授权的命令会自动打开钉钉并等待结果。若命令仍在运行，持续轮询同一执行 session 直到结束；不要让用户回复“已授权”后再继续。

Shulex Desk / Tars 客服台工单的唯一入口。它与 GPT 标签树配置、CX 产品售后工单是不同的数据和操作面，不要混用。

## 场景路由

| 用户诉求 | 必读文档 |
|---|---|
| 当前工单列表、筛选、正文分类 | `/skills/solvea-desk/references/tickets/query.md` |
| 标签树、工单标签、绑定或解绑 | `/skills/solvea-desk/references/tickets/tags.md` |
| 指标、趋势、时效、明细、XLSX 或报表 | `/skills/solvea-desk/references/report/workflow.md` |

## 共用约束

- 查询和修改只使用上述文档指定的受控脚本，不直接 curl Tars 接口。
- 标签写入前必须确认目标工单和当前标签，并通过标签树或搜索获得准确的 Tars 标签 ID；不得使用 GPT 标签树 ID，也不得根据名称猜 ID。
- 向用户展示工单号、操作类型、标签名称和 ID，获得明确确认后才能向脚本传 `--confirm`。
- `aiTags` 只读；绑定和解绑只操作并核验 `userTags`。
- 搜索返回多个同名或相近标签路径时让用户选择，不自动取第一个。
- 新任务只写 `/workspace/state/solvea-desk/`、`/workspace/outputs/solvea-desk/` 和 `/workspace/tmp/solvea-desk/`。

## 历史报表任务

先读取 `/workspace/state/solvea-desk/latest_task.json`。新路径不存在时，可以**只读**检查 `/workspace/state/desk-report/latest_task.json` 及其 task 目录，以继续分析或重新渲染旧任务。

历史回退仅用于读取：任何新任务和新 fetch 都必须写入 `/workspace/state/solvea-desk/`，不得向旧 `desk-report` 目录写入。

## 相邻能力边界

- GPT 标签树、标签组、标签节点配置：使用 `solvea-kit`，接口位于 `/api_v2/gpt/label/project/...`。
- CX 产品售后咨询、创建或追加售后工单：使用 `shulex-support`。
- Agent 会话指标、趋势和原始会话下钻：使用 `agent-analytics`。
