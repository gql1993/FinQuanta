# OpenClaw 无人值守上线交接清单

适用范围：将 `FinQuanta API + daemon + OpenClaw pipeline` 交付到 Windows 实机或生产环境，进行无人值守运行、只读验收、值班和回滚。

## 1. 交接结论

交接时按以下状态签收：

- `可上线`: 所有硬门槛通过，生产安全报告为 `ready`。
- `可灰度`: OpenClaw 主链路、仿真门禁和交易通道安全检查通过，但仍存在非交易阻塞项。
- `不可上线`: daemon/readiness/仿真门禁/交易安全闸任一硬门槛失败。

当前建议默认按 `可灰度` 处理：保持无人值守买入关闭，只允许卖出降风险；等默认 admin 密码、admin token、Gateway token 处理完毕后再进入正式生产签收。

## 2. 上线硬门槛

上线前必须满足：

- API 可常驻运行，`/health` 返回正常。
- Windows 计划任务或服务已安装，API 异常退出后能自动恢复。
- `/api/openclaw/daemon/status` 的 `openclaw.readiness.ready == true`。
- 无人值守交易安全闸已开启，且上线早期 `unattended_buy_enabled == false`。
- 仿真门禁已通过，`consecutive_success_runs >= required_success_runs`。
- `e2e_openclaw_unattended.bat --require-buy-disabled --require-simulation-pass` 通过。
- `check_trade_channel_safety.bat --require-buy-disabled --require-last-run-success --require-simulation-pass` 通过。
- `GET /api/admin/production-security-report` 为 `ready`，或明确记录所有未处理风险及责任人。

## 3. 交付文件

交接时至少保留：

- `RELEASE_INFO.json`: 构建时间、git commit、文件数量和排除策略。
- `DEPLOYMENT_CHECKSUMS.sha256`: 部署包完整性清单。
- `ACCEPTANCE_REPORT.json`: 发布包验收报告。
- `logs/openclaw_unattended_e2e_report.json`: 无人值守 E2E 验收报告。
- `logs/trade_channel_safety_report.json`: 真实交易通道只读安全检查报告。
- `logs/openclaw_history_replay_report.json`: 历史回放/仿真报告。

## 4. 标准验收命令

基础发布包验收：

```bat
verify_windows_release.bat
accept_windows_release.bat
```

无人值守最终验收：

```bat
e2e_openclaw_unattended.bat --require-buy-disabled --require-simulation-pass
check_trade_channel_safety.bat --require-buy-disabled --require-last-run-success --require-simulation-pass --output-json logs\trade_channel_safety_report.json
replay_openclaw_history.bat --output logs\openclaw_history_replay_report.json
```

发布报告编排：

```bat
accept_windows_release.bat --smoke-openclaw --check-trade-safety --require-buy-disabled --require-simulation-pass --openclaw-e2e
```

## 5. 值班入口

值班优先看：

- `GET /api/ops/health`: 运维健康快照，含 daemon、OpenClaw、仿真门禁、认证安全、事件和 runbook。
- `GET /api/openclaw/daemon/status`: OpenClaw daemon 细节、last_run、alert_state、history、安全闸。
- `GET /api/admin/production-security-report`: 生产权限与认证审计报告。
- `GET /api/admin/auth-audit`: 登录、改密、撤销 token、清理 token 审计。
- `GET /api/openclaw/config-audit`: Coordinator、安全闸、告警策略、回滚审计。

## 6. 生产权限交接

账号分工：

- `viewer`: 只读查看状态和审计。
- `operator`: 日常值班，允许触发 OpenClaw pipeline、学习、回放和任务。
- `admin`: 只在变更窗口使用，允许修改安全闸、Coordinator、告警策略和回滚配置。

上线前处理：

- 修改默认 `admin/admin123` 密码。
- 撤销多余 admin token，仅保留必要会话。
- 清理过期或异常 token。
- 确认 OpenClaw 配置审计中的 `actor` 可追溯到实际操作者。

## 7. 真实交易灰度

默认灰度顺序：

1. 保持无人值守买入关闭，只允许卖出降风险。
2. 观察至少 3 个交易日，确认 daemon、告警、历史回放和 E2E 稳定。
3. 小额度开启无人值守买入，例如单票 2000、单批 3000、每日 5000。
4. 每次放宽额度前重新运行 E2E、交易通道安全检查和历史回放。
5. 任何 error 或连续 warning 后，先关闭无人值守买入再排查。

## 8. 回滚与停机

停止无人值守入口：

```bat
uninstall_api_task.bat
```

风险降级：

- 在桌面或 Web 端关闭 `允许无人值守买入`。
- 必要时执行 `POST /api/openclaw/unattended-trade-guard/reset` 恢复安全闸默认值。
- 对 Coordinator、安全闸、告警策略误改，优先使用配置审计回滚。

## 9. 当前已知待处理项

截至本清单整理时，实机仍需人工处理：

- 默认 `admin/admin123` 密码仍可用，生产签收前必须修改。
- 活跃 admin token 较多，建议改密后自动撤销旧 token，或按账号执行 token revoke。
- `FINQUANTA_OPENCLAW_GATEWAY_TOKEN` 未配置，生产环境应配置。
- ServerChan 当日额度可能被验收耗尽，建议正式值班使用企业微信或备用通道。
