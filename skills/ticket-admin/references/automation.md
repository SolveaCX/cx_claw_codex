# 自动规则与工作台视图

对应设置 → 效率 → 自动规则（`/settings/automation`）。页面包含分单规则、合并/关单、表单邮件识别；触发器是独立菜单，见 `<PLUGIN_ROOT>/skills/ticket-admin/references/triggers.md`。
命令入口为 `node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket`，参数用 `--params-json` 或 `--params-file`。

## 分单规则

先用 `ticket admin-automation-list` 读列表，按 ID 用 `ticket admin-automation-get --params-json '{"id":"123"}'` 取规则；`ticket admin-automation-task` 查已有任务。解释条件、分配对象及当前状态，不启动任务。

## 合并/关单

读取与产品页面一致的配置项，再用 `ticket admin-inactivity` 查客户未响应自动关单计时策略。区分启停状态、等待时长、适用范围和当前工单事实。

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket admin-settings-list --params-json '{"types":["auto_close_ticket","auto_merge_ticket","auto_assign_online_agent_only","clear_agent_after_reply"]}'
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket admin-inactivity
```

## 表单邮件识别

分别核对表单发件邮箱名单和仅按邮件引用关系合并的邮箱名单，不能用一份名单代替另一份。

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" ticket admin-settings-list --params-json '{"types":["form_sender_emails","email_reference_only_merge"]}'
```

## 工作台视图（设置菜单外）

查看公共/私人视图用 `ticket admin-views-public`、`ticket admin-views-private`；按 ID 读视图条件用 `ticket admin-view --params-json '{"id":"123"}'`。
按视图查询实际工单列表由 ticket-helper 承接；这里解释保存的筛选条件，不保存或修改视图。
