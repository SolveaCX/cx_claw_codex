# 流程图读取规范

从流程图、白板草图、决策树或 SOP 大图生成 CHAT_FLOW 时，先把图片理解成结构化摘要，再按 `node-selection.md` 选节点、按 `graph-spec.md` 写 source JSON。

## 大图读取

先由主 agent 对用户上传图片调用一次 `read_file`，拿 overview 和 tile manifest。主 agent 负责全局调度：先从 overview 识别入口、主分支、终点、布局方向和明显缺口，再决定是否需要读取局部 tile。普通小图或 overview 已足够清楚时，不需要 subagent。

如果图片过大并返回 tile manifest（`/store/read_file_images/.../tile_r{row}_c{col}.jpg`），创建 chatflow 前必须先完成全图覆盖式理解：不能只根据 overview 或少量 tile 开始构图，也不要一次性读取全部 tile。

按迭代方式读图：

1. 主 agent 先读 overview 和 manifest，确认行列范围、流程方向、主要区域、入口/终点候选和明显缺口。
2. 主 agent 写出当前理解：`已识别区域`、`待确认区域`、`需要读取的 tile 范围`。
3. 每次只派 subagent 读取一个局部连续区域，例如入口区、某条主流程、某个下方分支或某组看不清的节点。
4. subagent 只读取主 agent 指定的少量 tile，输出局部摘要：`区域位置`、`入口/出口`、`节点文字`、`边/流转`、`条件分支`、`跨 tile 连接点`、`转人工/结束点`、`看不清的问题`。
5. 主 agent 合并局部摘要后更新全局结构和缺口列表；如果入口、主要分支、跨 tile 连接、结束节点或关键话术仍未覆盖，再派下一次 subagent 读必要 tile。
6. 只有主要流程、关键分支、跨 tile 连接点和结束节点均已覆盖后，才能开始落 chatflow。
7. 如果仍有看不清的区域，必须在摘要里显式标注不确定点；不能臆造节点、边或话术。

给 subagent 的 prompt 写清：

- 原图虚拟路径、tile manifest、待读 tile 列表和本次局部目标；subagent 不会自动看到主 agent 已读过的内容。
- 只读指定 tile；除非指定 tile 明显不够且会影响本次目标，才最多补读相邻 tile，并在摘要里说明原因。
- 只输出结构化摘要，不生成 chatflow JSON，不调用 CLI，不写文件，不探索 `/skills/`、`/skill-lib/` 或凭证文件。
- 每个 subagent 只负责一个局部区域，并输出压缩后的结构化摘要。

## 结构化摘要

读图完成后先写摘要，再建 source：

```text
Direction: top-to-bottom / left-to-right / mixed
Entry: <入口节点文字>
Terminal nodes: <结束/转人工/子流程>

Nodes:
- <编号> <原图文字> | role=<业务作用> | outgoing=<出口>

Edges:
- <from> --<条件/按钮/状态>--> <to>

Unclear:
- <看不清或需要用户确认的点>
```

## 落图顺序

1. 识别入口、终点、转人工点。
2. 用 `node-selection.md` 为每个业务节点选择 CHAT_FLOW 节点类型。
3. 用 `graph-spec.md` 写 source JSON 和 edges。
4. 只读取实际用到的 `nodes/*.md` 补字段和资源依赖。

## 视觉到节点的快速提示

- 矩形且由确定状态必然发送的固定回复：通常是 `REPLY(TEMPLATE)`，先查模板库。若图中表达的是某个
  模型节点必须遵循的 PE/输出话术约束，则保留在该节点的实际文本字段，不因“固定话术”标签强制改成 REPLY。
- 菱形简单条件：通常是 `IF_ELSE`。
- 用户选项/按钮：通常是 `QUESTION(USER_REPLY)`。
- 流程图中的 Y/N、True/False、满足/不满足：默认是条件分支，不是用户按钮；Y 表示条件满足，N 表示条件不满足，通常映射为 `IF_ELSE` 的 case/FALSE 或工具 `actionStatus`。只有明确写着“请用户选择是/否”时才映射为 `QUESTION(USER_REPLY)`。
- 查询接口/调用系统：`TOOL -> IF_ELSE` 或 `AGENT(with tools, next_steps)`。
- 知识库回答：默认 `RAG_REPLY`。
- 红色转人工：`TRANSFER_TO_HUMAN`。
- 结束：默认连共享 `$finish`。
