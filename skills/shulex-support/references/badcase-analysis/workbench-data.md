# 工作台数据契约 v1

批量交付时读取。先完成诊断和可交付数据的脱敏，再填JSON；不要重写HTML/CSS/交互或自行拼Excel。固定模板由CLI维护，统计从case计算；人审与模型判断仍由排查流程负责。

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" badcase render \
  --data-file <诊断数据绝对路径.json> \
  --output-dir <交付目录绝对路径>
```

这是本地渲染命令，无网络和租户写入，不需要context。生成 `badcase-report.html` 和 `badcase-details.xlsx`，已有同名文件会被替换；要保留旧交付物就指定新的批次目录。JSON留在任务内部位置，不额外交付。校验失败先修复数据，不通过放宽分类或编造证据绕过校验。

## 顶层结构

所有列出的字段必填；未知文本用空字符串，集合用空数组。ID始终是字符串。时间使用带时区或说明的可读文本，不让模板猜时区。diagnosis、recommendation、evidence、gaps支持Markdown段落、加粗、列表、引用和代码块；其余元信息为纯文本。不传HTML，模板安全渲染，不改变证据内容。HTML渲染Markdown，XLSX保留分段和编号并去除格式标记，仍为固定10列。只传已审阅、脱敏的可交付内容，不传完整接口响应、凭据或签名链接。模板不代替内容脱敏或事实核验。

| 字段 | 内容 |
|---|---|
| schemaVersion | 固定数字 `1` |
| batch | 本批元信息，见下表 |
| cases | 逐条问题，见下表 |
| conversations | 去重会话快照，见下表 |
| fixes | 修复项数组，每项含 `fixId`、`title`、`priority`、`ready`（布尔，是否方案就绪）；覆盖case从cases.fixId关联，不另填数量 |

### batch

| 字段 | 内容 |
|---|---|
| tenantName / accountId / environment | 租户名、租户ID、环境 |
| scope | 实际输入范围 |
| snapshotAt / generatedAt | 诊断快照时间、交付生成时间 |
| notice | 影响阅读判断的限制；没有则空，不添加泛化免责声明 |
| sourceCount / includedCount / excludedCount | 非负整数，源记录=纳入+排除；缺证但纳入的case计入纳入数 |
| findings | 数组，每项 `title`、`summary`、`caseIds`；结论有依据，引用的case必须存在 |

### cases[]

| 字段 | 内容 |
|---|---|
| caseId / source | 稳定问题ID、原表Sheet及行号等来源。拆分问题共享同一source；不同source数等于includedCount |
| chatId / agentId / agentName | 查询确认的ID和名称；未知留空，agentId为空时名称也为空 |
| flowVersion | 对象 `{ "historical": "v3", "current": "v7" }`，对应本case的agentId。historical是会话实际运行版本，current是本次取证读取的当前发布版本；未知值用空字符串。新诊断填写此字段，旧数据兼容省略；不得从正文猜版本或用草稿替代当前发布版本。版本号已知不代表已取得该版配置，配置缺口仍记入gaps |
| problem | 忠实原反馈，必要时补清上下文 |
| primary / secondary | 既定一级/二级分类；配对校验，未知留空 |
| classificationReason | 二级空白原因：`uncovered`（分类未覆盖）、`insufficient`（证据不足）、`nonissue`（非问题）、`unreviewed`（旧数据尚未复核）；有二级分类时空字符串。分类未覆盖必须提供suggestedCategory |
| classificationGap | 二级空白的原因，空白分类时不可省略 |
| suggestedCategory | 分类未覆盖时的模型建议，非正式类别；不适用则空 |
| diagnosis / recommendation | 业务语言的问题定位、可执行修复建议，遵循core-flow |
| evidence / technical | 最少证据摘录、可展开的完整ID/版本/路径等技术定位；不把内部原始响应整体塞入 |
| gaps | 具体缺口；会话或目标消息缺失时必须说明 |
| certainty | `confirmed`（直接原因已确认）或 `partial`（仍需补证） |
| priority | `P0` / `P1` / `P2` / `P3`；P3只在用户口径使用时保留，未指定时按输出契约默认口径 |
| treatment / status | 既定处理方式和修复状态；处理方式可空，修复状态必须有效 |
| fixId | 关联修复项ID，未形成修复项可空 |
| conversationId / targetMessageId | 对应会话快照与本问题目标消息；不可取得时空并填gaps。目标消息必须属于该会话，chatId也须一致 |

### conversations[]

| 字段 | 内容 |
|---|---|
| conversationId / chatId | 本批内快照唯一ID、会话ID。一个会话不同快照使用不同conversationId |
| snapshotAt / completeness | 取证时间与完整性说明，不能把部分记录称为完整会话 |
| messages | 保留来源顺序，每项见下表；不要按展示需要重新生成对话 |

| 消息字段 | 内容 |
|---|---|
| id | 原始消息ID，在本快照内唯一；没有ID的记录可保留可追溯的来源位置标识，不能伪称后端ID |
| role | `customer` / `ai` / `human` / `event` / `unknown`；根据消息角色与动作判断，不只看单一role字段 |
| text | 已脱敏的原始最终内容，保留原有Markdown，不为排版改写消息；HTML按Markdown展示，原始HTML按文本显示，图片只显示占位说明，不自动加载外部资源。动作事件明确作为event，模型中间输出不冒充对客消息；缺失留空 |
| time / turn | 可取得的时间与轮次，字符串 |
| attachments | 附件类型及不可预览原因等文本数组；本模板不嵌入附件原文件或远程预览链接 |

## 渲染后检查

命令校验分类、修复状态、唯一ID、来源数量及case/会话/消息/修复项引用，生成两份同源产物。它不能证明诊断正确或原始会话完整。仍按batch-output的交付验收检查事实、可读性和代表case，并确认本批没有字段缺失导致错误展示。模板迭代用合成数据回归，客户原文不要提交到仓库。
