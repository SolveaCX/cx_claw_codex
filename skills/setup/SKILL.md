---
name: setup
description: 安装 CXClaw 后完成钉钉登录、租户选择和本地环境自检。
---

# CXClaw Setup

1. 后续命令统一使用 `node "<PLUGIN_ROOT>/plugin-cli.mjs"`。运行
   `node "<PLUGIN_ROOT>/plugin-cli.mjs" auth status`；已经登录时不要重复授权，未登录再运行
   `node "<PLUGIN_ROOT>/plugin-cli.mjs" auth login --server <公司提供的 shulex-cloud 授权地址>`。
2. 请用户在钉钉授权页完成验证。不要代替用户授权，也不要展示或记录 token。
3. 用户要求测试环境时运行 `node "<PLUGIN_ROOT>/plugin-cli.mjs" tenant search <租户名称> --env test`；生产环境必须明确使用 `--env prod`，不能自行推断。
4. 用户确认目标租户后，运行 `node "<PLUGIN_ROOT>/plugin-cli.mjs" tenant use <accountId> --env <test|prod> --purpose <用途>`。
5. 运行 `node "<PLUGIN_ROOT>/plugin-cli.mjs" doctor` 和
   `node "<PLUGIN_ROOT>/plugin-cli.mjs" update --install-scheduler`。只有两步都成功才报告安装完成。

写操作必须先调用同一业务命令的 `--phase preview` 并展示结果；等待用户明确确认后，使用 `--phase commit --confirmation-token-stdin --idempotency-key <key>` 提交。不得把确认凭证写入命令参数、文件或日志。
