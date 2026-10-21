# HTTP 工具

本文描述 `EXTERNAL_HTTP_CALL` 工具的真实保存结构。底层接口和字段仍使用 `plugin` / `pluginId` / `queryPlugin` 命名。

## API 与 CLI

| 操作 | 方法 | 路径 |
|---|---|---|
| 列表 | POST | `/api_v2/gpt/ap/queryPlugin` |
| 详情 | POST | `/api_v2/gpt/ap/queryPlugin`，body 带 `pluginId`、`convertStrategyV5=true` |
| 创建 | POST | `/api_v2/gpt/ap/createPlugin` |
| 更新 | POST | `/api_v2/gpt/ap/updatePlugin` |
| 删除 | POST | `/api_v2/gpt/ap/deletePlugin` |
| 调试（不保存） | POST | `/api_v2/gpt/ap/runHttpPlugin` |
| 根据真实响应构建输出 | POST | `/api_v2/gpt/ap/{projectId}/build/plugin` |

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher api list-plugins --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api get-plugin --id <tool_id> --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api create-plugin \
  --data-file /workspace/state/agent-builder/tool_<name>.json --pretty
${PLUGIN_ROOT}/bin/cxclaw-launcher api update-plugin \
  --data-file /workspace/state/agent-builder/tool_<name>.json --pretty
```

大 JSON 不要内联到 `--data`。创建前必须先查重、静态验证并确认写入；创建后用返回的 ID 执行 `get-plugin` 回查。

`update-plugin` 是完整对象更新，payload 需要带 `pluginId`；可基于 `get-plugin` 返回的完整定义修改目标字段。

## 完整外层结构

```json
{
  "name": "lookup_order",
  "description": "按订单号查询订单是否存在",
  "type": "EXTERNAL_HTTP_CALL",
  "source": "MANUAL",
  "visible": true,
  "meta": {
    "category": "MANUAL",
    "externalHttpCallConfig": {
      "url": "https://example.com/api/order",
      "method": "POST",
      "headerParams": [
        {
          "name": "Content-Type",
          "description": "JSON request",
          "value": "application/json"
        }
      ],
      "requestParam": {
        "items": []
      },
      "responseParam": {
        "items": []
      },
      "actionStatuses": []
    }
  }
}
```

- 普通接口使用 `meta.category: "MANUAL"`，并提供非空 `url`。`method` 使用接口真实方法。
- Header 结构为 `name`、`value`、`description`。Authorization、X-Token 等鉴权值和普通 Header 一样写入 `value`。
- 工具只能放到 AGENT 节点的 `usedPlugins`，或由 TOOL 节点引用；不要放进 Output 区域。

## 参数 schema

`requestParam.items` 和 `responseParam.items` 的每个元素都是 `HttpParamDTO.Item`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | string | 必须非空、不能包含 `.`，同一层级必须唯一 |
| `description` | string | 参数说明；建议始终提供 |
| `required` | boolean | 是否必填，主要用于请求参数 |
| `type` | string | `string` / `integer` / `number` / `date` / `boolean` / `array` / `object` |
| `effect` | boolean | 是否对模型/返回结果生效，通常为 `true` |
| `source` | string | 请求值来源，缺省语义为 `LLM` |
| `ref` | object | 可选字段映射，服务端 Pair 结构通常是 `{"key":"...","value":"..."}` |
| `value` | any | `source: "CUSTOMIZE"` 时的固定值 |
| `listSubItem` | Item | `type: "array"` 时必填，描述唯一的元素类型 |
| `objectItems` | Item[] | `type: "object"` 时必填且非空，描述对象字段 |

`source` 常见取值：`LLM`、`CONVERSATION`、`ORDER`、`LOGISTIC`、`TICKET`、`AGENT_OUTPUT`、`CUSTOMIZE`、`METADATA`。使用非 `LLM` 来源前，应确认对应运行时确实提供该数据。

复杂类型示例：

```json
{
  "name": "data",
  "description": "response body",
  "type": "object",
  "effect": true,
  "objectItems": [
    {
      "name": "items",
      "description": "order lines",
      "type": "array",
      "effect": true,
      "listSubItem": {
        "name": "item",
        "description": "one line",
        "type": "object",
        "effect": true,
        "objectItems": [
          {
            "name": "quantity",
            "description": "quantity",
            "type": "integer",
            "effect": true
          }
        ]
      }
    }
  ]
}
```

`array` 的 `listSubItem.name` 是元素描述名，不进入状态映射路径；上例数量字段的精确 `apiName` 是 `data.items.quantity`。

## actionStatuses

`actionStatuses` 用于 TOOL 节点启用 `enableActionStatus=true` 后的分支。每项结构是：

```json
{
  "name": "found",
  "condition": {
    "or": [
      {
        "rules": [
          {
            "type": "GENERIC",
            "apiName": "data.exists",
            "apiType": "BOOLEAN",
            "relation": "EQUAL",
            "values": [true]
          }
        ]
      }
    ]
  }
}
```

- `condition.or` 中的组彼此是 OR；同一组的 `rules` 彼此是 AND。
- 每条规则必须完整提供 `type`、`apiName`、`apiType`、`relation`、`values`。当前普通 HTTP 状态规则使用 `type: "GENERIC"`。
- `apiName` 必须是 `responseParam.items` 中字段的完整精确路径。对象层级以 `.` 连接；数组元素描述名不计入路径。不能只写叶子名，也不能用参数 `name` 自带点号来伪造路径。
- `object` 本身不能作为状态条件；应选择其可比较的后代字段。
- 最后一项必须是默认状态，后端与 UI 兼容两种空条件：`"condition": {}` 或 `"condition": {"or": []}`。新建配置推荐 canonical `"condition": {}`；`{"or": []}` 同样合法，不能判为非法。默认状态只能放最后。

### 参数类型到 apiType

| response `type` | 可用 `apiType` |
|---|---|
| `string` | `TEXT` |
| `integer` / `number` | `NUMBER` |
| `date` | `DATE_TO_NOW` 或 `NOW_TO_DATE` |
| `boolean` | `BOOLEAN` |
| `array` | `ARRAY_SIZE` |
| `object` | 不支持作为条件 |

### apiType 到 relation

| `apiType` | 可用 `relation` | `values` 规则 |
|---|---|---|
| `TEXT` | `CONTAIN`, `NOT_CONTAIN`, `IS_EMPTY`, `NOT_EMPTY`, `EQUAL`, `NOT_EQUAL` | `CONTAIN` / `NOT_CONTAIN` 可有一个或多个字符串；`EQUAL` / `NOT_EQUAL` 一个字符串 |
| `NUMBER` | `GREATER_THAN`, `GREATER_THAN_OR_EQUAL`, `LESS_THAN`, `LESS_THAN_OR_EQUAL`, `BETWEEN`, `EQUAL`, `NOT_EQUAL`, `IS_EMPTY`, `NOT_EMPTY` | JSON 数值或前端保存的数值字符串；`BETWEEN` 恰好两个，其余比较恰好一个 |
| `DATE_TO_NOW` / `NOW_TO_DATE` | 同 `NUMBER` | JSON 数值或数值字符串；`BETWEEN` 恰好两个 |
| `ARRAY_SIZE` | 同 `NUMBER` | JSON 数值或数值字符串；`BETWEEN` 恰好两个 |
| `BOOLEAN` | `EQUAL`, `NOT_EQUAL`, `IS_EMPTY`, `NOT_EMPTY` | 后端同时接受 JSON boolean `true` / `false` 和前端保存的字符串 `"true"` / `"false"`；手写 JSON 推荐 boolean |

`IS_EMPTY` / `NOT_EMPTY` 的 `values` 必须是空数组 `[]`。虽然底层 `LogicalRelationEnum` 还包含 `IN`、`NOT_IN`、`EXACT_CONTAINS`、`NOT_EXACT_CONTAINS`，当前工具详情页和静态 validator 不接受它们用于上述 HTTP 状态映射；不要在新配置中使用。

## 合法完整示例：`data.exists` boolean

```json
{
  "name": "lookup_order",
  "description": "按订单号查询订单是否存在",
  "type": "EXTERNAL_HTTP_CALL",
  "source": "MANUAL",
  "visible": true,
  "meta": {
    "category": "MANUAL",
    "externalHttpCallConfig": {
      "url": "https://example.com/api/order",
      "method": "POST",
      "headerParams": [
        {
          "name": "Content-Type",
          "description": "JSON request",
          "value": "application/json"
        }
      ],
      "requestParam": {
        "items": [
          {
            "name": "order_id",
            "description": "订单号",
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
            "name": "data",
            "description": "查询结果",
            "type": "object",
            "effect": true,
            "objectItems": [
              {
                "name": "exists",
                "description": "订单是否存在",
                "type": "boolean",
                "effect": true
              }
            ]
          }
        ]
      },
      "actionStatuses": [
        {
          "name": "found",
          "condition": {
            "or": [
              {
                "rules": [
                  {
                    "type": "GENERIC",
                    "apiName": "data.exists",
                    "apiType": "BOOLEAN",
                    "relation": "EQUAL",
                    "values": [true]
                  }
                ]
              }
            ]
          }
        },
        {
          "name": "not_found_or_error",
          "condition": {}
        }
      ]
    }
  }
}
```

旧错误 case 常把它写成 `apiName: "exists"`、`apiType: "TEXT"`、`relation: "eq"`、`values: ["true"]`。真正的错误有三处：路径缺少父级 `data`；boolean 必须映射到 `BOOLEAN`；关系必须是大写枚举 `EQUAL`。`values: ["true"]` 是前端可能保存的兼容格式，后端可接受；手写 JSON 时仍推荐更明确的 `values: [true]`。

## 静态验证与写入

```bash
python3 /skills/agent-builder/scripts/tools/validate_tool_config.py \
  --data-file /workspace/state/agent-builder/tool_lookup_order.json \
  --pretty
```

只有输出 `"valid": true` 才继续请求用户确认并创建。该命令取代“只确认 JSON 能解析”的弱校验：它还会拒绝非法类型、同层重名、缺失复杂类型子项、错误字段路径、类型/关系/值不匹配，以及默认状态位置错误。

创建完成后：

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher api get-plugin --id <tool_id> --pretty
```

以回查结果确认名称、URL、方法、参数树和 `actionStatuses` 已按预期保存。

## 调试安全边界

`run-plugin` / `runHttpPlugin` 会真实访问目标 URL，不是纯校验：

`run-plugin --data-file` 接收 envelope，而不是裸 `externalHttpCallConfig`。例如：

```json
{
  "externalHttpCallConfig": {
    "url": "https://example.com/api/order",
    "method": "POST",
    "headerParams": [
      {
        "name": "Content-Type",
        "value": "application/json"
      }
    ],
    "requestParam": {
      "items": []
    },
    "responseParam": {
      "items": []
    },
    "actionStatuses": []
  },
  "externalHttpCallRequestBody": {
    "order_id": "ORDER-DEMO-001"
  }
}
```

```bash
${PLUGIN_ROOT}/bin/cxclaw-launcher api run-plugin \
  --data-file /workspace/state/agent-builder/run_tool_config.json \
  --pretty
```

- 仅当用户明确要求或明确授权实际调试时执行。
- GET 等只读接口也不能因“创建工具”而默认调用。
- POST / PUT / PATCH / DELETE 等可能写数据的接口，执行前额外确认本次请求体和影响范围。
- 不得将“上线前必须运行”作为强制步骤；未授权时只做静态验证和保存结果回查。
