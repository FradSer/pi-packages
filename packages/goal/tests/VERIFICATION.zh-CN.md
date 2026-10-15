# Goal 简化与 TUI 验收记录

验收日期：2026-10-08。全部显示头、触发条件与底部状态见 @../TUI.zh-CN.md；行为要求见 @../features/goal.feature。

## 最终结果

| 验收 | 结果 |
| --- | --- |
| Goal 与 pi-kit 的 pytest | 131 passed；不是整个仓库测试总数 |
| 简化契约 Node harness | 40 个 Given/When/Then 场景通过 |
| Goal 源码及测试类型检查 | 通过 |
| 仓库 extension 类型检查 | 通过；并行 e2e 修改曾出现未使用函数错误，最后重跑已消失 |
| packed-manifest 检查 | 19 个 workspace package 通过 |
| Goal dry-run 打包 | 通过 |
| 宿主真实 Pi CLI／交互 TUI | 13 个场景通过，PTY 同步帧验证 80 列至 40 列长中文尾部 |
| 原生 SDK 请求预检拒绝 | GOAL_NATIVE_REJECTION_OK；拒绝的请求没有授权后续恢复 |
| 独立状态／并发复查 | 已发现缺陷全部修复，最终未报告未解决问题 |
| 故障注入 | 临时删除接受修订的计费分支，回归失败；随后源码逐字恢复，40 场景重新通过 |

## Docker 隔离验收

执行 `sh packages/goal/tests/goal_docker.sh`，使用 `node:24-bookworm-slim`、**最新的 Pi**（默认在运行时从 registry 解析，`PI_VERSION` 可固定基线）和 pnpm **11.21.0**。先打包 Goal 与必需依赖 pi-kit，再从 tarball 安装；不挂载宿主凭据、Pi 设置或其他扩展。

Pi 的 packages 配置仅为 `/isolated/node_modules/@fradser/pi-goal`。pi-kit 是运行依赖，测试 provider 仅用于驱动可重复的模型响应。

- 13 个 CLI／TUI 场景：完成、三次未达标、空更新、检查错误、连续阻塞、长中文及检查取消；交互路径包括暂停、查看、恢复、清除。
- 4 个正常自动加载场景：空更新与长中文，各自 CLI／TUI。此路径由已安装 Goal 自动加载，不由 fixture 注册 Goal。
- 已安装打包源码执行：40 个简化契约、13 个存储、35 个调度、14 个真实 SDK 会话场景，共 102 个行为场景。
- 最终 Docker tarball 的全部 `src/*.ts` 已与当前工作区逐项比对；验收后仅清理了无效行尾空白，运行逻辑一致。
- Docker 测试容器在结束时自动移除，结果日志与 tarball 保留供复核。

最终证据目录：`/var/folders/vn/whfnt01d4b19zg44txbtznbc0000gn/T/goal-docker-dIHF2dgw`，其中 `verification.log` 记录 Pi 版本、唯一 package 配置、全部结果和 tarball SHA256。

```json
{"packages":["/isolated/node_modules/@fradser/pi-goal"],"goalSha256":"89868632c2b5b332602c311cbf32ead9bb615d9d027f5fd68e925963355efff3","kitSha256":"59a6d77f051fbfbf2f04709a13764655ffebd108339626c7960a53b218382ee9"}
```

## 修复与证据范围

先建立新契约并运行旧实现的 RED 复现，再修复。独立审查新增的计费／并发缺陷也逐项 RED→GREEN：跨线程取消检查计费及封顶、暂停修订计费、过期恢复、跨目标 unmet 清理、旧检查错误停止新要求、暂停后的主模型用量、交叉线程消息用量。

长期目标、完成条件和报告在默认终端帧中显示完整尾部。完成／清除后开放记录消失，不创建或更新归档；测试保留并比对旧历史文件。已删除专用研究、独立 ledger、next_action 和三次拒绝自动暂停。

## 限制与环境信息

所有模型响应由脚本 provider 控制；原生完成检查使用注入式 stand-in。无工具检查的 subprocess 参数、完整目标、报告解析及凭据隔离由专门测试验证。本次没有请求真实远程模型，不宣称真实模型判定质量。

`pnpm check:install` 报宿主有 10 个无关 package 未配置：agent-teams、btw、context、keyboard、monitor、plan-mode、recap、skill-router、utils、vision。Goal 不在缺失列表，Docker 唯一 Goal 安装验收通过；未改变这些无关宿主安装项。

本次未运行全部仓库的 pytest，不发布包、不修改远程分支、不删除原有历史。
