# OpenClaw 无人值守部署运维手册

适用范围：Windows 主机上常驻运行 `FinQuanta API + daemon + OpenClaw pipeline`，实现工作日无需打开桌面客户端也能自动完成选股、研判、审批、安全闸、执行、推送和复盘。

## 1. 部署目标

无人值守 OpenClaw 的生产化目标不是“能跑一次”，而是满足以下条件：

- API 进程可在用户登录后或开机后自动启动，并在异常退出后自动重启。
- daemon 已随 API 启动，且 `openclaw_pipeline` 未被禁用。
- OpenClaw 后台配置可在桌面端、Web 端或 API 查询。
- 无人值守交易安全闸默认开启，且默认禁止无人值守买入。
- 告警策略启用，错误/告警状态能进入系统事件和推送链路。
- 每次后台执行会记录 `last_run`、最近历史、仿真门禁状态、trace 摘要和 Coordinator 编排摘要。

## 2. 上线前检查

如需交付到生产机器，先在开发/构建机器生成 Windows 部署包：

```bat
build_windows_release.bat
```

正式发版建议使用 clean git 质量闸，避免把未提交的临时改动打进生产包：

```bat
build_windows_release.bat --require-clean-git
```

输出目录为 `dist\releases\FinQuanta-windows-<时间戳>`，同时生成同名 zip。部署包会包含源码、启动/安装脚本、运维文档、`.env.api.example` 和 `.env.api.production.example`，不会包含日志、缓存、本地数据库、虚拟环境或旧构建产物。包内会生成 `RELEASE_INFO.json` 和 `DEPLOYMENT_CHECKSUMS.sha256`，用于追溯构建时间、git commit、文件数量和完整性。

生产机器解压后先校验文件完整性：

```bat
verify_windows_release.bat
```

在生产机器解压后，先复制并编辑 API 环境文件：

```bat
copy .env.api.production.example .env.api
notepad .env.api
```

然后执行发布包验收编排：

```bat
accept_windows_release.bat
```

该命令会按顺序执行完整性校验和 strict 落地预检，检查 Python 版本、关键脚本/目录、checksum 清单以及 `.env.api` 中的 API/daemon 基础配置。

`FINQUANTA_ENV=prod` 时，strict 预检还会阻止常见生产弱配置：API 仍使用 SQLite、`FINQUANTA_CORS_ORIGINS=*`、`FINQUANTA_OBSERVABILITY_READ_TOKEN` 为空、OpenClaw Gateway 启用但 `FINQUANTA_OPENCLAW_GATEWAY_TOKEN` 为空，或生产模板中的 `CHANGE_ME_*` 占位符尚未替换。

验收完成后会在包根目录生成 `ACCEPTANCE_REPORT.json`，记录 release info、执行参数、每一步命令、退出码、耗时、stdout/stderr 摘要和最终结果。交接时保留该文件。

API 常驻并完成至少一次后台 OpenClaw 执行后，运行最终验收：

```bat
accept_windows_release.bat --smoke-openclaw
```

最终验收会在上述检查基础上增加严格 OpenClaw daemon smoke：计划任务、daemon active、last_run、readiness 和管理员安全自检都必须通过。

若要把真实交易通道只读安全检查也写入验收报告：

```bat
accept_windows_release.bat --smoke-openclaw --check-trade-safety --require-buy-disabled
```

确认 Python 环境和依赖：

```bat
python --version
python -m pip install -r requirements.txt
accept_windows_release.bat --check-deps
```

`--check-deps` 会检查核心 Python 依赖；如果希望 OpenClaw、PostgreSQL、Redis、WebEngine 等可选能力缺失也直接失败，可使用 `accept_windows_release.bat --check-deps --strict-deps`。

确认 API 能启动：

```bat
start_api.bat
```

另开终端执行基础冒烟：

```bat
check_api.bat
smoke_api.bat relaxed
```

如果使用 OpenClaw Gateway，先确认网关可达：

```bat
start_openclaw.bat
python infra\check_openclaw_gateway.py --strict
```

## 3. 常驻运行方案

### 3.1 推荐方案：Windows 计划任务

当前用户登录后启动，并立即运行：

```bat
install_api_task.bat --start
```

开机即启动，不等待用户登录。需要管理员终端：

```bat
install_api_task.bat --system --start
```

查看任务：

```bat
schtasks /Query /TN "FinQuantaApiService" /V /FO LIST
```

停止任务：

```bat
schtasks /End /TN "FinQuantaApiService"
```

卸载任务：

```bat
uninstall_api_task.bat
```

### 3.2 备选方案：真正 Windows Service

如果需要进入 Windows Service 管理体系，使用 NSSM 托管 `start_api_service.bat`。先下载 `nssm.exe`，放入 `PATH`，或通过 `--nssm` 指定路径。

管理员终端执行：

```bat
install_api_windows_service.bat --start
```

指定 NSSM 路径：

```bat
install_api_windows_service.bat --nssm C:\tools\nssm\nssm.exe --start
```

查看服务：

```bat
sc query "FinQuantaApiService"
```

停止服务：

```bat
net stop "FinQuantaApiService"
```

卸载服务：

```bat
uninstall_api_windows_service.bat
```

## 4. OpenClaw 后台配置

默认配置在 API 启动时读取，运行后也可通过桌面设置页或 Web OpenClaw 运行中心修改。

关键配置：

- 执行时间：默认 `10:25`，保存在 `sched_time_overrides.openclaw_pipeline`。
- 关注板块：默认 `人工智能,芯片,量子科技`，保存在 `openclaw_daemon_boards`。
- 告警策略：保存在 `openclaw_daemon_alert_policy`。
- 无人值守交易安全闸：保存在 `openclaw_unattended_trade_guard`。

常用 API：

```text
GET  /api/openclaw/daemon/status
GET  /api/openclaw/daemon/alert-policy
POST /api/openclaw/daemon/alert-policy
GET  /api/openclaw/unattended-trade-guard
POST /api/openclaw/unattended-trade-guard
POST /api/openclaw/unattended-trade-guard/reset
```

## 5. 上线验收

先做只读检查：

```bat
smoke_openclaw_daemon.bat
```

计划任务或服务启动后，做严格检查：

```bat
smoke_openclaw_daemon.bat --require-task --require-daemon-active
```

完成至少一次后台 OpenClaw 测试后，再要求 `last_run`：

```bat
smoke_openclaw_daemon.bat --require-task --require-daemon-active --require-last-run
```

生产上线前，建议把就绪度和管理员安全自检也作为硬门槛：

```bat
smoke_openclaw_daemon.bat --require-task --require-daemon-active --require-last-run --require-ready --require-security-ready
```

`--require-ready` 会要求 `/api/openclaw/daemon/status` 中 `openclaw.readiness.status == ready`。如果未就绪，输出会包含 `summary`，用于定位 daemon、调度、告警策略、安全闸、仿真门禁或回放记录问题。

`--require-security-ready` 会要求 `/api/admin/security-check` 返回 `status=ready`。该检查需要 smoke 登录账号具备管理员权限；如默认 `admin/admin123` 仍可登录，会直接失败。

桌面端验收：

- 设置页可以看到后台 OpenClaw 执行时间、关注板块、上次执行、告警策略、安全闸配置。
- 点击“立即测试后台 OpenClaw”后，`上次后台执行` 会刷新。
- OpenClaw 运行中心可以看到后台状态、last run、告警策略、安全闸、仿真门禁和最近历史。

Web 端验收：

- 登录 API 后进入 `OpenClaw -> 运行中心`。
- 可以看到后台 OpenClaw 状态和最近历史。
- 展开“配置无人值守交易安全闸”，保存配置后无报错。
- 关键安全闸参数变更后，仿真门禁应变为未通过，并显示重置原因。

## 5.1 无下单回放仿真

上线前或改完安全闸后，可以用最近一次扫描结果回放审批和安全闸链路。该脚本不会下单，也不会持久写入日内 usage。

使用 `kv_store.last_scan_results`：

```bat
replay_openclaw_guard.bat --limit 10 --output logs\openclaw_guard_replay.json
```

使用自定义 JSON 文件：

```bat
replay_openclaw_guard.bat --input replay_items.json --shares 100 --mode auto
```

输入 JSON 可以是候选列表，也可以是决策列表。常用字段：

```json
[
  {
    "action": "buy",
    "code": "300750",
    "name": "宁德时代",
    "price": 10.0,
    "shares": 100,
    "sector": "新能源",
    "reason": "回放验证"
  }
]
```

验收重点：

- `approved_count` 和 `rejected_count` 是否符合安全闸预期。
- 拒绝原因是否命中黑名单、单票额度、批次额度、板块集中度、冷却时间或仿真门禁。
- `captured_writes` 只出现在报告里，不会写回 `kv_store`。

真实交易通道只读安全检查：

```bat
check_trade_channel_safety.bat --require-buy-disabled --require-last-run-success --output-json logs\trade_channel_safety_report.json
```

该命令只读取状态，不会触发 pipeline、不会调用执行接口、不会下单。上线早期建议要求 `--require-buy-disabled`，确认无人值守买入保持关闭；等仿真门禁、回放和管理员安全自检全部通过后，再进入小额度买入灰度。

全链路历史回放/仿真报告：

```bat
replay_openclaw_history.bat --output logs\openclaw_history_replay_report.json
```

该报告不下单，会汇总后台 OpenClaw 运行历史、成功率、仿真门禁、安全闸回放、AI 决策准确率和走势验证摘要。上线评审时可与 `trade_channel_safety_report.json` 一起留档。

无人值守 OpenClaw 端到端验收：

```bat
e2e_openclaw_unattended.bat --require-buy-disabled --require-simulation-pass
```

该命令会通过 API 验证 health、登录、daemon ready、管理员安全自检、历史回放 API、安全闸回放 API，并本地执行交易通道安全检查和历史回放脚本。它只读验收，不会触发 pipeline 或下单。

若要写入发布验收报告：

```bat
accept_windows_release.bat --smoke-openclaw --check-trade-safety --require-buy-disabled --require-simulation-pass --openclaw-e2e
```

## 6. 安全闸上线策略

默认推荐顺序：

1. 保持 `允许无人值守买入` 关闭，只允许卖出降风险。
2. 手动触发后台 OpenClaw 测试，确认 daemon、trace、告警和历史记录正常。
3. 开启仿真门禁，要求至少 3 次连续成功或 warning 运行。
4. 小额度开启无人值守买入，例如单票 2000、单批 3000、每日 5000。
5. 观察至少 3 个交易日，再逐步放宽额度。

建议初始参数：

```text
每日买入金额上限: 5000
单票买入金额上限: 2000
每日买入次数上限: 2
单批买入金额上限: 3000
单批买入次数上限: 1
单票日内买入次数: 1
板块日内买入金额: 3000
板块日内买入次数: 1
买入冷却时间: 60 分钟
仿真成功运行次数: 3
```

## 7. 日常值守

每日开盘后检查：

```bat
smoke_openclaw_daemon.bat --require-daemon-active
```

查看 API wrapper 日志：

```bat
type logs\api_service.log
```

查看 NSSM stdout/stderr：

```bat
type logs\api_service_stdout.log
type logs\api_service_stderr.log
```

在 Web 或桌面运行中心重点看：

- `Daemon` 是否运行中。
- `OpenClaw调度` 是否启用。
- `上次后台执行` 是否为 success 或 warning。
- `告警策略` 的连续失败次数、抑制次数、最近推送时间。
- `仿真门禁` 是否通过。
- 最近历史中是否连续 error。

## 8. 常见故障

### API 不可达

现象：

```text
[ERROR] API unreachable
```

处理：

```bat
start_api.bat
check_api.bat
```

如由计划任务托管：

```bat
schtasks /Run /TN "FinQuantaApiService"
schtasks /Query /TN "FinQuantaApiService" /V /FO LIST
```

### daemon 未运行

检查 API 是否设置自动启动 daemon：

```bat
set FINQUANTA_API_AUTOSTART_DAEMON
```

`start_api.bat` 默认会设置 `FINQUANTA_API_AUTOSTART_DAEMON=1`。如果自定义启动命令，需显式设置该变量。

### OpenClaw 后台没有 last_run

说明 daemon 已启动但还没到调度时间，或任务被禁用。可在桌面设置页点击“立即测试后台 OpenClaw”，或等待下一个交易日调度。

严格冒烟要等至少一次后台执行后再跑：

```bat
smoke_openclaw_daemon.bat --require-last-run
```

### 仿真门禁一直未通过

常见原因：

- 刚修改过 Coordinator 策略或安全闸关键参数，系统已强制重置仿真门禁。
- 最近后台运行状态为 error。
- 所需连续成功次数设置过高。

处理：

1. 查看 `last_run.summary` 和系统事件。
2. 修复 error 后连续跑后台测试。
3. 临时降低 `simulation_min_success_runs` 只用于联调，生产环境恢复为 3 或更高。

### 告警没有推送

检查：

- 推送渠道是否配置。
- 告警策略是否启用。
- 是否仍在静默窗口内。
- 是否达到连续失败升级阈值。
- `notify_on_warning` / `notify_on_error` 是否允许当前状态推送。
- `notify_on_success` 是否开启成功摘要；若开启，`success_summary_interval_seconds` 会限制成功摘要频率。
- `min_level` 是否过滤了低级别状态。
- `default_channels` 与 `escalation_channels` 是否符合值班要求。

相关状态可在 `GET /api/openclaw/daemon/status` 的 `openclaw.alert_state` 和 `openclaw.alert_policy` 中查看。
`openclaw.alert_state.routing` 会记录最近一次通知决策，包括状态、是否升级、是否启用、命中的通道，便于解释“为什么没推送”。

## 8.1 运维健康快照

无人值守运行时，值班优先查看：

```powershell
curl -H "Authorization: Bearer <TOKEN>" http://127.0.0.1:9000/api/ops/health
```

该端点会汇总 daemon 自检、OpenClaw readiness、仿真门禁、认证安全、最近系统事件、任务记录和 metrics 摘要，并输出：

- `status`: `ready` / `warning` / `error`
- `findings`: 需要处理的风险项
- `runbook`: 建议排查步骤
- `signals`: 原始信号摘要，便于继续跳转到 `/api/openclaw/daemon/status`、`/api/ops/events` 或观测面板

如果 `status != ready`，先按 `runbook` 处理，再重新运行 `e2e_openclaw_unattended.bat` 和 `check_trade_channel_safety.bat`。

## 8.2 生产权限边界

无人值守 OpenClaw 的运行和配置分开授权：

- `operator` 可触发 OpenClaw pipeline、学习和安全闸回放，对应 `openclaw:run` / `openclaw:learn`。
- `admin` 才能修改或重置 Coordinator 策略、无人值守交易安全闸、后台告警策略，以及执行配置审计回滚，对应 `openclaw:admin`。
- `viewer` 只用于状态查看和审计查看，不用于生产操作。

上线时建议只给日常值班账号 `operator`，把 `admin` 用于变更窗口内的安全闸、策略和回滚操作。

上线前执行管理员安全自检：

```text
GET /api/admin/security-check
```

生产权限与认证审计汇总：

```text
GET /api/admin/production-security-report
```

该报告比普通安全自检更适合上线门禁，会汇总默认密码、角色分布、活跃 token、admin token、旧 token 和近期认证失败，并输出 `checklist` 与 `recommended_actions`。

或通过严格 smoke 一并检查：

```bat
smoke_openclaw_daemon.bat --require-security-ready
```

验收要求：

- `status=ready`。
- `default_admin_password=false`，默认 `admin/admin123` 已修改。
- 账号角色分布符合交接清单，过期或异常 token 已清理。
- 日常值班使用 `operator`，`admin` 只用于变更窗口；活跃 admin token 数应低于阈值。
- OpenClaw Coordinator、安全闸、告警策略和配置回滚审计中的 `actor` 应能追溯到实际操作者。

如果安全自检提示存在过期或异常 token，执行：

```text
POST /api/admin/tokens/cleanup-expired
```

该操作只删除过期或过期时间异常的 token，并会写入 `GET /api/admin/auth-audit`。

相关阈值可通过环境变量调整：`FINQUANTA_API_TOKEN_TTL_DAYS`、`FINQUANTA_AUTH_MAX_ACTIVE_TOKENS`、`FINQUANTA_AUTH_MAX_ADMIN_TOKENS`、`FINQUANTA_AUTH_MAX_TOKEN_AGE_DAYS`、`FINQUANTA_AUTH_FAILED_AUTH_THRESHOLD`。

## 9. 回滚

回滚最近一次关键配置变更：

```text
POST /api/openclaw/config-audit/rollback
{"audit_index": 0}
```

桌面端在 `OpenClaw -> 运行中心 -> 配置审计` 点击 `回滚最近配置变更`。Web 端在 `OpenClaw -> 运行中心 -> 最近配置变更审计` 点击同名按钮。回滚只恢复该审计记录中变更过的字段，并会追加一条新的 `rollback` 审计记录，便于追溯。

停止无人值守入口：

```bat
uninstall_api_task.bat
uninstall_api_windows_service.bat
```

恢复默认安全闸：

```text
POST /api/openclaw/unattended-trade-guard/reset
```

在桌面或 Web 端关闭 `允许无人值守买入`，保留卖出降风险能力。

## 10. 交接清单

最终签收建议使用独立清单：[OpenClaw 无人值守上线交接清单](OpenClaw_上线交接清单.md)。

- API 启动方式：计划任务或 Windows Service。
- API 地址和登录账号。
- OpenClaw 执行时间和关注板块。
- 告警策略：静默窗口、升级阈值、推送渠道。
- 安全闸参数：买入额度、批次限制、板块限制、冷却时间、黑白名单。
- 最近一次严格冒烟输出。
- 最近一次后台 OpenClaw `last_run` 状态。
