# FinQuanta

基于 PyQt6 的 A 股 AI 量化交易桌面客户端，配套 FastAPI 服务、小程序与 OpenClaw 等扩展能力。

## 运行模式与数据策略

当前版本同时支持两种产品运行模式：

- **本地模式（桌面优先）**：桌面端默认使用本地 SQLite（`data_cache/quant.db`），安装即用。
- **平台模式（服务优先）**：API / 服务化部署推荐使用 PostgreSQL，详见 `.env.api.example` 与 [基础设施升级说明](doc/基础设施升级_服务化部署说明.md)。

现阶段桌面与 API 不要求天然一致；如果需要跨端一致，应通过明确的同步、导入导出或平台规则设计实现，而不是默认假设共库。

Web 端当前优先走 API，在 API 不可用时仍保留本地兼容回退，作为渐进式服务化过渡方案。

## 入口与调度权威

推荐把生产入口收敛为一套明确组合：

| 场景 | 推荐入口 | 说明 |
|------|----------|------|
| 桌面本地 | `python run_desktop.py` | 人工操作与确认 |
| API / 平台 | `uvicorn api_server.main:app …` + `FINQUANTA_API_AUTOSTART_DAEMON=1` | API 托管 daemon |
| Windows 计划任务 | `install_daemon_task.bat` | **与 API autostart 二选一**，勿双开 |

- 桌面本地使用 `python run_desktop.py`，适合单机操作与人工确认。
- 平台/API 使用 `python -m uvicorn api_server.main:app --host 0.0.0.0 --port 9000`，并通过 `FINQUANTA_API_AUTOSTART_DAEMON=1` 让 API 托管 daemon。
- Windows 计划任务仅用于本机无人值守场景；若已经由 API 常驻托管 daemon，请设 `FINQUANTA_API_AUTOSTART_DAEMON=0`，避免重复实例（第二实例会跳过并在 `kv_store.daemon_skip_reason` 留痕）。

### 扫描数据契约（P0）

- **`last_scan_results`**：选股雷达 / daemon 10:05 扫描写入，供 AI、自定义仓、OpenClaw 读取。
- **`last_scan_results_meta`**：记录 `source`（`daemon` / `ui`）、`strategy_id`、写入时间。
- **`FINQUANTA_AI_SCAN_SOURCE`**：`latest`（默认）| `daemon` | `ui` | `resonance` — AI 仓与自定义仓 Top3 消费规则。
- **策略竞技场**使用 `arena_snapshot_{date}`，**不会覆盖** `last_scan_results`。

AI 决策一次性计划任务的时间由 `FINQUANTA_AI_SCHEDULER_MORNING_TIME` 和 `FINQUANTA_AI_SCHEDULER_AFTERNOON_TIME` 控制，`desktop.auto_scheduler` 与 `install_scheduler.bat` 共用同一组默认值。

## 文档

- [系统介绍](doc/FinQuanta_系统介绍文档.md)
- [基础设施与服务化部署](doc/基础设施升级_服务化部署说明.md)
- [API 接口设计](doc/FinQuanta_API接口设计书.md)
- [OpenClaw 无人值守部署运维手册](doc/OpenClaw_无人值守部署运维手册.md)
- [OpenClaw 无人值守上线交接清单](doc/OpenClaw_上线交接清单.md)
- [观测栈端到端演示与运维手册](doc/观测栈端到端演示与运维手册.md)

## 快速启动

### 1) 启动 API（默认 9000）

```bash
python -m uvicorn api_server.main:app --host 0.0.0.0 --port 9000
```

### 2) 启动桌面端

```bash
python run_desktop.py
```

### 3) 启动 Web 端

```bash
streamlit run web_app.py --server.port 8501 --server.address 0.0.0.0
```

### 4) 启动 OpenClaw Gateway（可选，推荐联调）

```bash
start_openclaw.bat
```

仅做健康探测（不拉起新实例）：

```bash
start_openclaw.bat --health-only
```

或直接使用 Python 检查脚本（严格模式，不可达则返回非 0）：

```bash
python infra/check_openclaw_gateway.py --strict
```

## 运行中心增量同步（Web/API）

`GET /api/ops/center` 当前支持 registry 增量同步：

- `registry.meta.change_token`：当前 registry 版本 token
- `registry_changed`：是否发生变更
- `registry_sync.payload_mode`：`full` 或 `compact`
- `registry_sync.cached`：服务端 registry 缓存命中状态

调用建议：

1. 首次不带 `registry_token` 拉全量（`payload_mode=full`）  
2. 后续带上上次 token：`/api/ops/center?registry_token=<token>`  
3. 若 `registry_changed=false`，返回精简 registry（只保留计数和 meta）

## 缓存相关配置

在 `.env.api.example` 可配置：

- `FINQUANTA_REGISTRY_CACHE_TTL`：服务端 registry 内存缓存 TTL（秒，默认 30）
- `FINQUANTA_WEB_OPS_CENTER_CACHE_TTL`：Web 运行中心客户端节流缓存 TTL（秒，默认 5）
- `FINQUANTA_SNAPSHOT_CACHE_TTL`：快照缓存 TTL（秒，默认 120）
- `FINQUANTA_API_TOKEN_TTL_DAYS`：API 登录 token 默认有效期天数（默认 7，范围 1~90）
- `FINQUANTA_AUTH_MAX_ACTIVE_TOKENS`：认证安全检查允许的活跃 token 阈值（默认 20）
- `FINQUANTA_AUTH_MAX_ADMIN_TOKENS`：认证安全检查允许的活跃 admin token 阈值（默认 2）
- `FINQUANTA_AUTH_MAX_TOKEN_AGE_DAYS`：活跃 token 最大创建年龄天数（默认 7）
- `FINQUANTA_AUTH_FAILED_AUTH_THRESHOLD`：最近认证失败告警阈值（默认 5）
- `FINQUANTA_API_AUTOSTART_DAEMON`：API 启动时是否自动拉起后台 daemon（默认 1）。API 进程常驻后，工作日会按调度表自动执行任务。
- `FINQUANTA_DAEMON_BOARDS`：daemon 默认关注板块，逗号分隔（如 `人工智能,芯片,量子科技`）。10:25 会触发 `OpenClaw自主全流程`，无需打开桌面客户端。
- `FINQUANTA_AI_SCHEDULER_MORNING_TIME` / `FINQUANTA_AI_SCHEDULER_AFTERNOON_TIME`：AI 决策一次性计划任务时间（默认 `10:15` / `14:00`），供 `desktop.auto_scheduler` 与 `install_scheduler.bat` 使用。
- `FINQUANTA_ALERT_APPROVAL_REJECTED_THRESHOLD`：审批拒绝次数告警阈值（默认 5）
- `FINQUANTA_ALERT_APPROVAL_DURATION_MS_THRESHOLD`：审批耗时最大值告警阈值 ms（默认 3000）
- `FINQUANTA_ALERT_EVENT_ERROR_THRESHOLD`：事件 error 总量告警阈值（默认 10）
- `FINQUANTA_ALERT_APPROVAL_REJECTED_DAILY_THRESHOLD`：单日审批拒绝次数阈值（默认 5）
- `FINQUANTA_ALERT_POLICY_NAME`：告警策略名称（默认 `baseline-v1`）
- `FINQUANTA_OBSERVABILITY_TREND_WINDOW_DAYS`：趋势报表窗口天数（默认 7）
- `FINQUANTA_OBSERVABILITY_TREND_EVENT_LIMIT`：趋势报表读取事件数上限（默认 500）
- `FINQUANTA_TRACE_SAMPLE_RATIO`：trace 采样比例（0~1，默认 1.0）
- `FINQUANTA_TRACE_SPAN_BUFFER_SIZE`：内存 span 缓冲区上限（默认 2000）
- `FINQUANTA_OTEL_COLLECTOR_ENDPOINT`：OTEL Collector 端点（当前用于配置对齐与后续接入）
- `FINQUANTA_OTEL_EXPORT_TIMEOUT_SECONDS`：Collector 上报超时秒数（默认 5.0）
- `FINQUANTA_OTEL_EXPORT_RETRIES`：Collector 上报重试次数（默认 2）
- `FINQUANTA_OTEL_EXPORT_BACKOFF_SECONDS`：重试退避基数秒（默认 0.2）
- `FINQUANTA_OTEL_BREAKER_FAIL_THRESHOLD`：熔断触发失败阈值（默认 3）
- `FINQUANTA_OTEL_BREAKER_COOLDOWN_SECONDS`：熔断冷却秒数（默认 30）
- `FINQUANTA_OTEL_BATCH_SIZE`：批量上报大小（默认 100）
- `FINQUANTA_TRACE_VISUAL_BACKEND`：trace 可视化后端预设（`otlp/tempo/jaeger`）
- `FINQUANTA_TRACE_VISUAL_BACKEND_BASE_URL`：可视化后端 OTLP base URL（如 `http://127.0.0.1:4318`）
- `FINQUANTA_TRACE_VISUAL_TENANT_ID`：Tempo 多租户 `X-Scope-OrgID`（可选）
- `FINQUANTA_OBSERVABILITY_READ_TOKEN`：观测只读 token（用于 dashboard 免登录读取）
- `FINQUANTA_STRUCTURED_LOG_PATH`：结构化日志文件路径（默认 `logs/observability/structured.log`，用于 Loki 采集）
- `FINQUANTA_STRUCTURED_LOG_MAX_BYTES`：结构化日志单文件最大大小（默认 10MB）
- `FINQUANTA_STRUCTURED_LOG_BACKUP_COUNT`：结构化日志轮转保留文件数（默认 5）
- `FINQUANTA_ALERT_ROUTE_SUPPRESS_SECONDS`：告警抑制窗口秒数（默认 300）
- `FINQUANTA_ALERT_ROUTE_ESCALATE_AFTER`：同类告警升级阈值（默认 3）
- `FINQUANTA_ALERT_ROUTE_DEFAULT_CHANNELS`：默认通知通道列表（逗号分隔）
- `FINQUANTA_ALERT_ROUTE_ESCALATION_CHANNELS`：升级通知通道列表（逗号分隔）
- `FINQUANTA_ALERT_DISPATCH_RECEIPT_LIMIT`：告警发送回执内存保留上限（默认 1000）
- `FINQUANTA_OPENCLAW_GATEWAY_ENABLED`：是否启用 OpenClaw Gateway 优先调用（默认 1；关闭后走本地回退）
- `FINQUANTA_OPENCLAW_GATEWAY_BASE`：OpenClaw Gateway base URL（默认 `http://127.0.0.1:18789`）
- `FINQUANTA_OPENCLAW_GATEWAY_HOST` / `FINQUANTA_OPENCLAW_GATEWAY_PORT`：`start_openclaw.bat` 启动与探测使用的主机/端口（默认 `127.0.0.1:18789`）
- `FINQUANTA_OPENCLAW_GATEWAY_TIMEOUT_SECONDS`：Gateway 调用超时秒数（默认 8.0）
- `FINQUANTA_OPENCLAW_GATEWAY_TOKEN`：Gateway 访问 token（可选）
- OpenClaw 后台告警策略支持 `notify_on_success`、`notify_on_warning`、`notify_on_error`、`min_level`、`success_summary_interval_seconds`、`default_channels`、`escalation_channels`，可通过 `/api/openclaw/daemon/alert-policy` 修改。
- `FINQUANTA_OPENCLAW_GATEWAY_PIPELINE_PATHS`：pipeline 路径候选（逗号分隔，按顺序重试）
- `FINQUANTA_OPENCLAW_GATEWAY_LEARN_PATHS`：learn 路径候选（逗号分隔，按顺序重试）

## 可观测性端点（第一版）

- `GET /api/observability/metrics`：返回当前进程内存指标快照（counters/histograms）
- `GET /api/observability/alerts`：按阈值对指标做告警评估，返回 `ok/alerting` 与告警列表
- `GET /api/observability/metrics/prometheus`：Prometheus 文本导出（`text/plain`）
- `GET /api/observability/metrics/otel`：OTEL 风格 JSON 导出（resource/scope/metrics 结构）
- `GET /api/observability/traces`：最近 trace span 列表（采样后）
- `GET /api/observability/traces/index`：最近 trace 链路索引（按 trace 聚合 span 数量/状态）
- `GET /api/observability/traces/trace/{trace_id}`：按 trace_id（支持 trace_id_hex）查看链路明细与摘要
- `GET /api/observability/traces/otel`：OTEL 风格 trace 导出（支持 `trace_id` 过滤，并返回 `summary/graph` 可视化维度）
- `GET /api/observability/traces/config`：当前 trace 采样与缓冲配置
- `GET /api/observability/traces/backends/presets`：Tempo/Jaeger/OTLP 路由预设（含 headers/route）
- `POST /api/openclaw/pipeline/run` / `POST /api/openclaw/learn/run` / `POST /api/task/trigger/{task_key}`：支持接收 `traceparent`，执行结果透出 `trace` 关联信息（跨服务链路）
- `GET /api/observability/dashboard/template`：观测面板字段模板（trace index/span table/trace graph）
- `GET /api/observability/dashboard/panel-input`：可直接给面板消费的聚合输入（trace+alerts+collector+template）
- `GET /api/observability/collector/state`：Collector 上报状态（失败计数/熔断状态）
- `POST /api/observability/collector/push`：Collector 批量上报入口（支持 `signal`、`dry_run`、`trace_id` 定向上报）
- `GET /api/observability/trace/context`：traceparent 上下文解析与传播骨架
- `GET /api/observability/trends`：审批/事件趋势报表（按窗口聚合 daily totals）
- `GET /api/observability/alerts/policy`：当前告警策略与阈值配置
- `GET /api/observability/alerts/routing`：策略级告警路由配置（通知/抑制/升级）
- `POST /api/observability/alerts/route`：按当前告警执行路由决策（支持 `dry_run`）
- `GET /api/observability/alerts/routing/state`：告警路由状态快照（seen/suppress）
- `POST /api/observability/alerts/dispatch`：执行路由后的真实通知发送（支持 `dry_run`）并产出回执
- `GET /api/observability/alerts/dispatch/receipts`：查询告警发送回执（最新优先）
- `GET /api/ops/health`：无人值守运维健康快照，汇总 daemon、OpenClaw readiness、仿真门禁、认证安全、最近事件和指标摘要，返回 `ready/warning/error` 与 runbook 建议。
- `GET /api/admin/production-security-report`：生产权限与认证审计报告，汇总默认密码、角色、token 卫生、近期认证失败和建议动作。

## Windows 常驻运行 API

OpenClaw 的无人值守调度由 API 启动时自动拉起的 daemon 执行。要做到“不打开桌面客户端也能在工作日自动运行”，请让 API 常驻：

```bat
install_api_task.bat --start
```

这会创建当前用户登录后启动的计划任务 `FinQuantaApiService`，并立即启动。API 退出后会由 `start_api_service.bat` 自动重启，日志写入 `logs\api_service.log`。

如果希望以真正 Windows Service 形态运行，可使用 NSSM 托管同一个 wrapper。先下载 `nssm.exe` 并放入 `PATH`，或通过 `--nssm` 指定路径，然后用管理员身份运行：

```bat
install_api_windows_service.bat --start
```

指定 NSSM 路径：

```bat
install_api_windows_service.bat --nssm C:\tools\nssm\nssm.exe --start
```

卸载 Windows Service：

```bat
uninstall_api_windows_service.bat
```

如需开机即启动（不等用户登录），用管理员身份运行：

```bat
install_api_task.bat --system --start
```

卸载：

```bat
uninstall_api_task.bat
```

无人值守链路冒烟检查：

```bat
smoke_openclaw_daemon.bat
```

更严格地确认计划任务已安装、daemon 正在运行、已有后台 OpenClaw 运行记录：

```bat
smoke_openclaw_daemon.bat --require-task --require-daemon-active --require-last-run
```

生产上线前增加就绪度和管理员安全门槛：

```bat
smoke_openclaw_daemon.bat --require-task --require-daemon-active --require-last-run --require-ready --require-security-ready
```

`--require-security-ready` 会检查 `GET /api/admin/security-check`，需要使用管理员 smoke 账号，并要求默认 `admin/admin123` 已修改。

完整上线验收、值守和排障流程见 [OpenClaw 无人值守部署运维手册](doc/OpenClaw_无人值守部署运维手册.md)。

生成 Windows 部署包：

```bat
build_windows_release.bat
```

正式发版建议要求工作区干净：

```bat
build_windows_release.bat --require-clean-git
```

默认输出到 `dist\releases\FinQuanta-windows-<时间戳>` 并生成同名 zip。打包会包含源码、启动/安装脚本、文档、`.env.api.example` 和 `.env.api.production.example`，排除日志、缓存、本地数据库、虚拟环境和旧构建产物。包内包含 `RELEASE_INFO.json`，记录构建时间、git commit、文件数量和排除策略。解压或拷贝到生产机器后可执行完整性校验：

```bat
verify_windows_release.bat
```

随后复制并编辑 `.env.api`，再执行落地预检：

```bat
copy .env.api.production.example .env.api
notepad .env.api
accept_windows_release.bat
```

生产环境 strict 预检会提示并阻止常见弱配置，例如 SQLite 生产库、`CORS=*`、观测只读 token 为空、OpenClaw Gateway 启用但 token 为空，或 `CHANGE_ME_*` 占位符尚未替换。

验收会在包根目录生成 `ACCEPTANCE_REPORT.json`，记录每一步命令、退出码、耗时、stdout/stderr 摘要和最终结果，便于交接留档。

安装依赖后，可追加运行时依赖检查：

```bat
python -m pip install -r requirements.txt
accept_windows_release.bat --check-deps
```

API 常驻并完成至少一次后台 OpenClaw 执行后，运行最终验收：

```bat
accept_windows_release.bat --smoke-openclaw
```

如果要把真实交易通道只读安全检查也写入 `ACCEPTANCE_REPORT.json`：

```bat
accept_windows_release.bat --smoke-openclaw --check-trade-safety --require-buy-disabled
```

安全闸无下单回放：

```bat
replay_openclaw_guard.bat --limit 10 --output logs\openclaw_guard_replay.json
```

真实交易通道只读安全检查（不触发下单）：

```bat
check_trade_channel_safety.bat --require-buy-disabled --require-last-run-success --output-json logs\trade_channel_safety_report.json
```

该检查会读取 API、管理员安全自检、OpenClaw daemon、无人值守交易安全闸和最近后台执行记录。上线早期建议保持 `--require-buy-disabled`，确认无人值守买入仍关闭，仅保留卖出降风险能力。

全链路历史回放/仿真报告（不下单）：

```bat
replay_openclaw_history.bat --output logs\openclaw_history_replay_report.json
```

该报告会汇总后台 OpenClaw 运行历史、成功率、仿真门禁、安全闸回放、AI 决策准确率和走势验证摘要，便于上线前复盘。

无人值守 OpenClaw 端到端验收（只读，不下单）：

```bat
e2e_openclaw_unattended.bat --require-buy-disabled --require-simulation-pass
```

若要写入发布验收报告：

```bat
accept_windows_release.bat --smoke-openclaw --check-trade-safety --require-buy-disabled --require-simulation-pass --openclaw-e2e
```

## 冒烟与排错速查

执行：

```bash
python infra/smoke_refactor_core.py
python infra/smoke_api.py
python infra/e2e_minimal.py
```

批处理双模式（Gateway 检查策略）：

```bash
smoke_api.bat strict
smoke_api.bat relaxed
```

- `strict`：Gateway 不可达直接失败（适合 CI）
- `relaxed`：Gateway 不可达仅提示，继续执行 API 冒烟（适合本地开发）
- 也可用环境变量设置默认：`FINQUANTA_SMOKE_GATEWAY_MODE=strict|relaxed`

若 `smoke_api` 报 API 不可达：

- 先确认 API 是否已启动（默认 `http://127.0.0.1:9000`）
- 或设置正确的 `FINQUANTA_API_BASE`
- 再重跑 `python infra/smoke_api.py`

## Dashboard 示例文件

仓库内已提供可落地的面板示例：

- `infra/dashboard_examples/grafana_tempo_trace_dashboard.json`
- `infra/dashboard_examples/grafana_alert_linkage_dashboard.json`
- `infra/dashboard_examples/grafana_trace_alerts_logs_trilink_dashboard.json`
- `infra/dashboard_examples/jaeger_saved_queries.json`

快速联调可执行：

```bash
python infra/demo_trace_panel_input.py
```

生成 Grafana provisioning（datasource + dashboard provider + dashboards_json）：

```bash
python infra/setup_grafana_provisioning.py --overwrite
```

默认输出目录：`infra/grafana/provisioning/`

## Docker Compose 观测栈（一键）

启动前建议确保 API 已启动（默认 `http://127.0.0.1:9000`），然后执行：

```bash
python infra/oneclick_observability_stack.py --api-base http://127.0.0.1:9000 --overwrite --up
```

停止观测栈：

```bash
python infra/oneclick_observability_stack.py --down
```

默认地址：

- Grafana: `http://127.0.0.1:3000`（`admin/admin`）
- Tempo API: `http://127.0.0.1:3200`
- Loki API: `http://127.0.0.1:3100`
- Tempo OTLP HTTP: `http://127.0.0.1:4318/v1/traces`

说明：

- 观测栈包含 `Grafana + Tempo + Loki + Promtail`
- Promtail 会采集 `FINQUANTA_STRUCTURED_LOG_PATH`（默认 `logs/observability/structured.log`）
- 三联看板示例：`infra/dashboard_examples/grafana_trace_alerts_logs_trilink_dashboard.json`
- 可通过环境变量自定义 Grafana 管理员：`FINQUANTA_GRAFANA_ADMIN_USER` / `FINQUANTA_GRAFANA_ADMIN_PASSWORD`

健康检查：

```bash
python infra/check_observability_stack.py
```
