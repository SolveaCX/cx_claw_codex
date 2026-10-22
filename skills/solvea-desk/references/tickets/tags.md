# Tars 工单标签

本模块操作 Shulex Desk / Tars 工单标签，不是 `/api_v2/gpt/label/project/...` 下的 GPT 标签树。所有命令使用受控脚本：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" solvea-desk tags <subcommand>
```

## 查询

完整标签树：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" solvea-desk tags list-tags
```

查询单个工单的人工标签和 AI 标签：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" solvea-desk tags get-ticket-tags \
  --ticket-number "<对外工单号>"
```

响应中的 `userTags` 是人工标签，`aiTags` 是只读 AI 标签。

批量查询使用工单内部整数 ID，不接受对外工单号。先把参数写入 `/workspace/state/solvea-desk/ticket_ids.json`：

```json
{"ticketIdList": [101, 102]}
```

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" solvea-desk tags batch-get-ticket-tags \
  --ticket-ids-file /workspace/state/solvea-desk/ticket_ids.json
```

按节点名称搜索标签路径：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" solvea-desk tags search-tags \
  --name "物流延迟"
```

搜索结果是路径数组，节点名称字段为 `nodeName`。标签写操作使用搜索结果中的准确 ID；同名或相近路径必须让用户选择，不能自动取第一项。

## 写操作边界

写操作只接受 Tars 标签查询返回的准确 ID 和名称。把参数写入 `/workspace/state/solvea-desk/tags.json`：

```json
{
  "tags": [
    {"id": 123, "name": "物流延迟"}
  ]
}
```

必须依次执行：

1. 使用 `solvea-desk fetch-tickets` 或准确工单号确认目标工单。
2. 使用 `get-ticket-tags` 读取当前 `userTags` 和 `aiTags`。
3. 使用 `list-tags` 或 `search-tags` 获得标签 ID 和名称。
4. 不带 `--confirm` 运行写命令，取得包含 `before` 和 `requested` 的预览；此时脚本只读取，不发送 POST。
5. 向用户展示工单号、绑定或解绑、标签名称和 ID，并等待明确确认。
6. 用户确认后才增加 `--confirm`。脚本会写入后重新读取标签，并输出 `before`、`requested`、`after`、`server_result` 和 `verified`。

绑定：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" solvea-desk tags bind-tags \
  --ticket-number "<对外工单号>" \
  --tags-file /workspace/state/solvea-desk/tags.json

# 用户明确确认后
node "<PLUGIN_ROOT>/plugin-cli.mjs" solvea-desk tags bind-tags \
  --ticket-number "<对外工单号>" \
  --tags-file /workspace/state/solvea-desk/tags.json \
  --confirm
```

解绑使用相同参数，将子命令换成 `unbind-tags`。

脚本只通过 `after.userTags` 核验结果；`aiTags` 永远只读。写接口返回成功但后置核验失败时，命令非零退出并保留前后证据，不得向用户宣称成功。
