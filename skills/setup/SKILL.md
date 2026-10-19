---
name: setup
description: 安装 CXClaw 后完成钉钉登录、租户选择和本地环境自检。
---

# CXClaw Setup

1. 运行 `${PLUGIN_ROOT}/bin/cxclaw-launcher login --server <公司提供的 solvea-kit 地址>`。
2. 请用户在钉钉授权页完成验证。不要代替用户授权，也不要展示或记录 token。
3. 运行 `${PLUGIN_ROOT}/bin/cxclaw-launcher tenant search <租户名称> --env prod`。
4. 用户确认目标租户后，运行 `${PLUGIN_ROOT}/bin/cxclaw-launcher tenant use <accountId> --env prod --purpose <用途>`。
5. 运行 `${PLUGIN_ROOT}/bin/cxclaw-launcher doctor`。只有 doctor 成功才报告安装完成。

写操作必须先展示 preview，等待用户明确确认后，再提交服务端返回的一次性确认凭证和幂等键。
