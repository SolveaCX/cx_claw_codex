# Frontend Rendering 场景详细说明

端到端验证 CXClaw 对 AI 消息、Markdown、工具事件和 Subagent 事件的实时渲染。这里测试的是真实事件流与刷新后的历史回放，不是静态 HTML。

## 执行约束

1. 优先在标准版执行并观察；内部员工再切换专业版复核。普通用户只验标准版。
2. 除了明确的“AI 消息边界”步骤，连续工具调用之间不要输出解释文字。
3. 测试文件只写入 `/workspace/tmp/runtime-inspector/frontend-rendering/`。
4. 先观察流式执行过程，再刷新当前会话，确认历史回放的内容、顺序和分组一致。
5. 不要自行宣称视觉 PASS。执行完输出验收清单，让用户确认实际界面。

## scenario `markdown`

在一条 AI 消息中原样输出下面的 Markdown 格式矩阵。不要放进一个外层代码块：

````markdown
# 一级标题
## 二级标题
### 三级标题

普通正文包含 **粗体**、*斜体*、~~删除线~~、`inline_code` 和 [可点击链接](https://example.com/cxclaw-render-test)。

> 这是一段引用。
> 第二行用于检查换行和左侧引用线。

- 无序列表第一项
- 无序列表第二项
  - 二级列表

1. 有序列表第一项
2. 有序列表第二项

- [x] 已完成事项
- [ ] 未完成事项

| 字段 | 状态 | 说明 |
|---|---:|---|
| Markdown | PASS | 表格、对齐与长文本换行 |
| Tool block | RUNNING | 等待后续场景 |

```json
{
  "name": "cxclaw-render-test",
  "enabled": true,
  "count": 3
}
```

```bash
printf 'frontend-rendering-ok\n'
```

中英文混排：CXClaw 支持 customer support、订单号 `ORDER-20260717-001`，以及长链接 https://example.com/a/very/long/path/that/must/wrap/inside/the/message/container?source=runtime-inspector&mode=standard 。
````

检查标题字号层级、段落间距、列表缩进、表格横向溢出、代码块滚动、链接点击区域和长文本换行。

## scenario `process`

### 第一组：连续成功工具

连续调用以下工具，中间不输出 AI 文本：

1. `execute`：`command` 使用 `mkdir -p /workspace/tmp/runtime-inspector/frontend-rendering && python3 -c 'import time; time.sleep(3); print("timer-ok")'`，`description` 写“等待 3 秒验证运行态计时”。
2. `write_file`：写入 `/workspace/tmp/runtime-inspector/frontend-rendering/sample.md`，内容固定为 `# Render fixture\n\nSecond line with **bold text**.`。
3. `ls`：列出 `/workspace/tmp/runtime-inspector/frontend-rendering/`。
4. `read_file`：读取刚写入的 `sample.md`。

观察点：

- 四个工具属于同一个过程块。
- 当前步骤显示旋转图标和递增计时。
- 完成步骤变为绿色勾，不常驻显示耗时；hover 绿色勾时显示耗时 Tooltip。
- 全部完成后过程块自动收拢，点击可展开全部步骤。
- 每个步骤显示与工具类型匹配的图标、友好名称和关键参数摘要。

### AI 消息边界

第一组结束后，单独输出一条 AI 消息：

> 过程分组边界：第一组结束，下面开始第二组。

然后再调用工具。该 AI 消息必须截断前一个过程块，后续工具进入新过程块。

### 第二组：失败状态

调用 `execute`，`command` 使用 `sh -c 'echo intentional-render-error >&2; exit 7'`，`description` 写“触发预期失败状态”。这是预期失败；收到工具错误后不要重试，继续输出一句“预期失败已返回，前端渲染测试继续。”，用于确认错误不阻断后续 AI 消息。

观察失败图标、错误文案、过程块展开状态，以及错误后最终 AI 消息是否正常显示。

## scenario `subagent`

调用一次 `task` / General Purpose Subagent，任务说明使用下面的要求：

```text
这是 CXClaw 前端渲染自检。先用 ls 查看 /skills/runtime-inspector，再用 read_file 读取 /skills/runtime-inspector/SKILL.md；两次工具调用之间不要输出解释文字。然后输出一句“Subagent AI 消息边界”。最后用 grep 在 /skills/runtime-inspector/SKILL.md 中搜索 frontend。不要修改任何文件。
```

观察点：

- Subagent 是独立过程块，不与外层普通工具混排。
- Subagent 内部连续工具按同一规则聚合。
- Subagent 内部 AI 消息会截断内部过程组，后续工具新开一组。
- 外层和内层各自展示运行、完成和耗时状态，不出现重复 footer。失败状态由 `process` scenario 单独覆盖。

如果当前 runtime 没有 `task` 工具，明确报告“当前运行时不支持 Subagent 渲染场景”，不要用普通工具伪造 Subagent。

## scenario `all`

按 `markdown` → `process` → `subagent` 顺序直接执行，不额外添加阶段标题或开场说明。`process` 中规定的 AI 边界消息必须保留；禁止在要求连续的工具调用之间插入说明。

## 验收清单

| 检查项 | PASS 条件 |
|---|---|
| 用户消息 | 深色气泡；skill 使用图标 + skill 名，不显示 `/skill-name` |
| AI 消息 | Markdown 层级正确；最后一条消息只有一行操作栏 |
| 连续工具 | 无 AI 消息时聚合为一个过程块 |
| AI 边界 | AI 消息前后拆成两个过程块 |
| 运行步骤 | 旋转图标 + 实时计时 |
| 完成步骤 | 绿色勾；仅 hover 显示耗时 |
| 失败步骤 | 错误状态明确且不影响后续消息 |
| Subagent | 独立块；内部递归应用相同分组规则 |
| 标准/专业 | 标准版精简、专业版保留明细，消息内容一致 |
| 历史回放 | 刷新后顺序、分组、状态和 Markdown 与实时态一致 |
