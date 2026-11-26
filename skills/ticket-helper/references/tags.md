# 查看工单标签

处理客服工单标签，不使用 Agent 域标签树接口。完整标签树、名称搜索、单张工单标签和批量查询均由 ticket-helper 承接。

## 查看单张工单的标签

先确认对外工单号，使用 `ticket tags`；参数名是 ticketNum。分别展示 userTags（人工标签）与 aiTags（AI 标签），保留层级路径，不把同名节点合并。

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket tags --params-json '{"ticketNum":"ST-123"}'
```

## 查看完整标签树与按名称找标签

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket catalog-tags
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket catalog-tag-search --params-json '{"tagName":"物流延迟"}'
```

搜索结果为路径数组，节点名称使用 nodeName。展示准确 ID 与完整路径；同名标签需区分路径，不自动选择第一项。用户想找带这个标签的工单时，将确定的标签 ID 传给 `ticket list` 的 tagList。

## 批量查看标签

先从工单详情/列表取得内部整数 ID，再查批量标签；不能把工单号放进 ticketIdList。

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket tags-batch --params-json '{"ticketIdList":[101,102]}'
```

参数较多时将 `{"ticketIdList":[101,102]}` 保存到文件，通过 `--params-file` 传入。保留每张工单与其标签的对应关系，不把缺失结果视为无标签。

## 当前范围

本期只读。绑定、解绑等修改接口暂不接；后续操作能力仍归 ticket-helper。标签分布、趋势及报表归 ticket-analytics，AI 打标策略配置查询归 ticket-admin。
