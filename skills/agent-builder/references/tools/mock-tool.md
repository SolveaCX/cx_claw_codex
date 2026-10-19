# Mock / Excel / CSV 工具

Mock 工具不是新的 plugin 类型。保存到工具库时仍然是：

```json
{
  "type": "EXTERNAL_HTTP_CALL",
  "source": "MANUAL",
  "meta": {
    "category": "EXCEL",
    "fileName": "logistics.xlsx"
  }
}
```

`EXCEL` 表示构建来源和 UI 展示方式；真正的数据保存在 MockData 表中，工具的 HTTP 配置指向同一环境的 MockData 搜索接口。

## UI 与高级 CLI 的边界

详情页上传 Excel / CSV 时，浏览器只读取第一个 sheet，转换成 JSON 数组，并将日期格式化、其他单元格调用 `toString()`。入参与出参也按首行列名生成顶层 `string` 字段。因此 UI 路径适合偏扁平的字符串记录。

高级 CLI 可以直接向 MockData 写 JSON 数组，不是详情页的上传入口。它可以保留 number、boolean、object、array 等嵌套 JSON 类型；但是详情页的表格编辑器只按首条记录的顶层列展示。以后在 UI 打开、编辑并保存，数据会被 UI 当前表格状态全量重传，嵌套值可能被覆盖、字符串化或降级。需要保留嵌套类型时，后续仍使用 CLI 管理，并避免从 UI 重存数据。

`get-plugin` 只读取保存的工具定义，不会调用工具原来的 URL，也不会查询 MockData 内容。数据回查要单独用 `query-mock-data`。

## 标准创建流程

MockData 的 `mock_type` 必须包含工具 ID，所以创建顺序和普通 HTTP 工具有所不同：

1. `list-plugins --pretty` 查重，向用户说明将进行三类写操作：创建占位、全量替换 MockData、更新工具；取得确认。
2. 创建最小占位工具，取得服务端返回的 `id`。
3. 从 `fileName` 去掉最后一个扩展名得到 stem，再生成 `mock_type = <stem>_<id>`。例如 `logistics.mock.xlsx`、ID `321` 对应 `logistics.mock_321`。
4. 按该 ID 准备最终工具配置，先运行 `validate_tool_config.py` 静态验证。
5. 执行 `replace-mock-data --name <mock_type>` 全量替换数据。
6. 在最终 payload 的普通 `headerParams` 中配置 `X-Token`，再执行 `update-plugin --data-file ... --pretty`。配置中 `method=POST`，URL 指向 `/api_v2/gpt/mockdata/searchMockData/<mock_type>`。
7. 分别运行 `query-mock-data --name <mock_type>` 与 `get-plugin --id <id> --pretty` 回查数据和定义。

占位配置示例：

```json
{
  "name": "lookup_logistics_mock",
  "description": "按物流单号查询测试物流记录",
  "type": "EXTERNAL_HTTP_CALL",
  "source": "MANUAL"
}
```

```bash
cxclawctl api create-plugin \
  --data-file /workspace/state/agent-builder/mock_placeholder.json \
  --pretty
```

创建结果中的 ID 是后续所有步骤的同一个 `<tool_id>`。不要猜 ID，也不要在不同工具之间复用 `mock_type`。

## 数据文件与替换命令

`/workspace/state/agent-builder/logistics_mock_records.json`：

```json
[
  {
    "tracking_number": "TRACK-DEMO-001",
    "carrier": "DemoCarrier",
    "delivered": false,
    "latest_status": {
      "status": "InTransit",
      "description": "Package left the sorting center"
    },
    "events": [
      {
        "time": "2026-07-16T09:30:00+08:00",
        "location": "Shanghai",
        "description": "Departed facility"
      }
    ],
    "days_after_last_update": 1
  },
  {
    "tracking_number": "TRACK-DEMO-002",
    "carrier": "DemoCarrier",
    "delivered": true,
    "latest_status": {
      "status": "Delivered",
      "description": "Delivered to recipient"
    },
    "events": [],
    "days_after_last_update": 0
  }
]
```

为匹配字段设置稳定的顶层查询键；上例只使用 `tracking_number`。同一 `mock_type` 中，不同记录的查询键值组合不得重复；如果用 `tracking_number` 和 `carrier` 联合查询，则二者的组合必须唯一。组合重复时搜索只返回数据库结果中的第一条，结果不确定。

确认写操作后执行：

```bash
cxclawctl api replace-mock-data \
  --name logistics_mock_<tool_id> \
  --data-file /workspace/state/agent-builder/logistics_mock_records.json \
  --pretty
```

`--name` 在这两个命令中就是 `mock_type`。`replace-mock-data` 会先删除当前租户下相同 `mock_type` 的全部旧记录，再写入新数组；不是追加或局部更新。数组最多 10,000 条，空数组会清空该类型。每次执行都属于写操作，必须在执行前确认本次全量替换的类型、条数和影响环境。

## 最终工具配置

最终配置仍使用 HTTP 工具参数 schema。`X-Token` 与其他 Header 一样配置在 `headerParams` 中。

```json
{
  "pluginId": 321,
  "name": "lookup_logistics_mock",
  "description": "按物流单号查询测试物流记录",
  "type": "EXTERNAL_HTTP_CALL",
  "source": "MANUAL",
  "visible": true,
  "meta": {
    "category": "EXCEL",
    "fileName": "logistics_mock.json",
    "externalHttpCallConfig": {
      "url": "https://<current-host>/api_v2/gpt/mockdata/searchMockData/logistics_mock_321",
      "method": "POST",
      "headerParams": [
        {
          "name": "X-Token",
          "description": "MockData API token",
          "value": "<X_TOKEN>"
        }
      ],
      "requestParam": {
        "items": [
          {
            "name": "tracking_number",
            "description": "物流单号，MockData 顶层查询键",
            "required": true,
            "type": "string",
            "effect": true,
            "source": "LLM"
          }
        ]
      },
      "responseParam": {
        "items": [
          {
            "name": "tracking_number",
            "description": "物流单号",
            "type": "string",
            "effect": true
          },
          {
            "name": "carrier",
            "description": "物流商",
            "type": "string",
            "effect": true
          },
          {
            "name": "delivered",
            "description": "是否签收",
            "type": "boolean",
            "effect": true
          },
          {
            "name": "latest_status",
            "description": "最新状态",
            "type": "object",
            "effect": true,
            "objectItems": [
              {
                "name": "status",
                "description": "状态码",
                "type": "string",
                "effect": true
              },
              {
                "name": "description",
                "description": "状态描述",
                "type": "string",
                "effect": true
              }
            ]
          },
          {
            "name": "events",
            "description": "物流事件",
            "type": "array",
            "effect": true,
            "listSubItem": {
              "name": "event",
              "description": "单条事件",
              "type": "object",
              "effect": true,
              "objectItems": [
                {
                  "name": "time",
                  "description": "发生时间",
                  "type": "string",
                  "effect": true
                },
                {
                  "name": "location",
                  "description": "发生地点",
                  "type": "string",
                  "effect": true
                },
                {
                  "name": "description",
                  "description": "事件描述",
                  "type": "string",
                  "effect": true
                }
              ]
            }
          },
          {
            "name": "days_after_last_update",
            "description": "距上次更新天数",
            "type": "integer",
            "effect": true
          }
        ]
      },
      "actionStatuses": []
    }
  }
}
```

不要从被替代的原工具复制 URL 或 Header。Mock 工具必须使用当前环境 MockData URL 和当前环境凭据；原接口的域名、认证信息和业务 Header 都不应残留。

用实际 `<tool_id>`、host 和安全注入后的本地 state 文件做静态验证，再更新：

```bash
python3 /skills/agent-builder/scripts/tools/validate_tool_config.py \
  --data-file /workspace/state/agent-builder/tool_lookup_logistics_mock.json \
  --pretty

cxclawctl api update-plugin \
  --data-file /workspace/state/agent-builder/tool_lookup_logistics_mock.json \
  --pretty
```

## 搜索语义

MockData 搜索接口只保留请求 JSON 中的顶层 primitive/wrapper 值和 string；object、array 等复杂值不会进入查询条件。所有保留下来的顶层条件按 AND 精确匹配：

```json
{
  "tracking_number": "TRACK-DEMO-001",
  "carrier": "DemoCarrier",
  "ignored_nested_filter": {
    "status": "InTransit"
  }
}
```

实际匹配条件只有 `tracking_number` AND `carrier`。接口返回第一条命中记录；没有命中时返回：

```json
{"message":"no result"}
```

因此请求参数应优先只暴露必要的顶层查询键，保证不同记录的查询键值组合不重复；不要设计依赖嵌套字段过滤的 Mock 工具。

## 回查与调试边界

```bash
cxclawctl api query-mock-data \
  --name logistics_mock_<tool_id> --pretty

cxclawctl api get-plugin --id <tool_id> --pretty
```

回查时确认：数据条数和嵌套类型正确；工具仍是 `EXTERNAL_HTTP_CALL`；`meta.category=EXCEL`；`fileName`、URL 中的 `mock_type` 与 ID 一致；方法为 POST；Header 为 `X-Token`。

`run-plugin` 会真实调用 MockData 搜索接口。只有用户明确要求或授权时才运行，不能因为它通常是只读查询就自动执行。若今后工具 URL 被改成任何写接口，运行前还必须对具体请求和影响范围做额外确认。

若 Mock 工具配置 `actionStatuses`，默认分支可使用 `"condition": {}` 或 UI 兼容形态 `"condition": {"or": []}`；两者都表示空条件且都合法。新建配置推荐前者。
