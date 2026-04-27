# FinQuanta API 接口设计书

## 一、目标

为后续：
- Web 端运营化
- 微信小程序接入
- 多用户权限
- 远程触发 OpenClaw 与系统任务

提供统一 API 骨架。

## 二、当前实现文件

- `api_server/main.py`
- `api_server/auth.py`
- `api_server/schemas.py`

## 三、当前已提供接口

### 1. 健康检查

`GET /health`

返回：
```json
{
  "ok": true,
  "service": "finquanta-api",
  "env": "prod",
  "runtime_mode": "local",
  "db_backend": "sqlite",
  "redis_cache": false
}
```

### 2. 登录

`POST /api/auth/login`

请求：
```json
{
  "username": "admin",
  "password": "admin123"
}
```

返回：
```json
{
  "ok": true,
  "token": "xxxx",
  "role": "admin",
  "message": "登录成功"
}
```

### 3. 统一快照

`GET /api/snapshot/system`

说明：
- 返回 `system_snapshot`
- 供桌面端 / Web 端 / 小程序统一读取

### 4. 运行中心

`GET /api/ops/tasks`

获取最近任务运行记录。

`GET /api/ops/events`

获取最近系统事件记录。

`GET /api/ops/center`

运行中心聚合视图，当前包含：
- `snapshot` / `tasks` / `events` / `operations`
- `registry`（provider/strategy 清单 + 计数 + meta）
- `registry_sync`（增量同步状态，含 `payload_mode` / `changed` / `cached` / token）

可选查询参数：
- `registry_token`：传入上次 `registry.meta.change_token`，未变化时返回精简 `registry`（列表为空，仅保留计数和 meta）。

### 5. 组合摘要

`GET /api/portfolio/summary`

返回：
- 手动仓摘要
- AI 四仓摘要
- 全仓 totals

### 6. OpenClaw 权重

`GET /api/openclaw/weights`

返回自主学习引擎输出的策略权重。

### 6.1 Registry 接口

`GET /api/registry`

返回统一 registry 概览（providers + strategies + meta）。

`GET /api/registry/providers`

返回 provider 注册清单。

`GET /api/registry/strategies`

返回策略注册清单。

### 7. 触发 OpenClaw 全流程

`POST /api/openclaw/pipeline/run`

请求：
```json
{
  "dry_run": false,
  "boards": ["人工智能", "芯片", "量子科技"]
}
```

### 7.1 OpenClaw 后台状态

`GET /api/openclaw/daemon/status`

返回：
- daemon 运行状态、下一任务、禁用任务
- OpenClaw 后台配置、上次执行、告警状态、告警策略、最近执行历史
- 无人值守交易安全闸配置、今日用量、仿真门禁、最近回放历史
- 最近 OpenClaw 关键配置变更审计

### 7.2 无人值守交易安全闸

`GET /api/openclaw/unattended-trade-guard`

返回当前安全闸配置、今日 usage、仿真门禁状态和安全闸回放历史。

`POST /api/openclaw/unattended-trade-guard`

请求字段包括：
- `unattended_buy_enabled`
- `max_daily_buy_amount`
- `max_single_buy_amount`
- `max_batch_buy_amount`
- `max_batch_buy_count`
- `max_symbol_daily_buy_count`
- `max_sector_daily_buy_amount`
- `max_sector_daily_buy_count`
- `buy_cooldown_minutes`
- `require_simulation_pass`
- `simulation_min_success_runs`
- `blacklist`
- `whitelist`

关键参数变更后会重置仿真门禁，要求重新完成连续成功试运行。

`POST /api/openclaw/unattended-trade-guard/replay`

无下单回放安全闸。默认使用 `last_scan_results`，也可传入 `items` 或 `decisions`。回放不会真实下单，也不会持久写入日内交易 usage，但会记录最近回放审计历史。

请求：
```json
{
  "limit": 10,
  "shares": 100,
  "mode": "auto",
  "use_real_price": false,
  "items": [
    {
      "code": "300750",
      "name": "宁德时代",
      "price": 10.0,
      "sector": "新能源",
      "action": "buy"
    }
  ]
}
```

返回：
```json
{
  "ok": true,
  "source": "request",
  "input_count": 1,
  "approved_count": 1,
  "rejected_count": 0,
  "skipped_count": 0
}
```

### 7.3 OpenClaw 配置审计与回滚

`GET /api/openclaw/config-audit?limit=30`

返回 Coordinator 策略、无人值守交易安全闸、后台告警策略的最近配置变更记录。

`POST /api/openclaw/config-audit/rollback`

按审计记录回滚配置。当前请求一般使用 `audit_index=0` 回滚最近一条记录；服务端只回滚该审计记录中变更过的字段，并会追加一条 `rollback` 审计记录。

请求：
```json
{
  "audit_index": 0
}
```

### 8. 触发自主学习

`POST /api/openclaw/learn/run`

请求：
```json
{
  "dry_run": false
}
```

## 四、鉴权机制

当前版本使用 API token 鉴权：

- 表：`api_users`
- 表：`api_tokens`
- 默认账号：`admin / admin123`
- 角色：`admin` / `operator` / `viewer`

OpenClaw 生产权限边界：

- `openclaw:run`：允许触发 OpenClaw pipeline、学习和安全闸回放，`admin` 与 `operator` 默认具备。
- `openclaw:admin`：允许修改或重置 Coordinator 策略、无人值守交易安全闸、后台告警策略，以及执行配置审计回滚，仅 `admin` 默认具备。
- `viewer` 只能查看状态、审计和运行结果，不能触发运行或修改配置。

管理员安全自检：

`GET /api/admin/security-check`

返回默认 `admin/admin123` 是否仍有效、用户角色分布、active/expired/invalid token 数量，以及 `ready/warning/error` 级别的安全发现。上线前应确保 `default_admin_password=false` 且 `status=ready`。

`POST /api/admin/tokens/cleanup-expired`

清理所有过期或过期时间异常的 API token，并写入认证审计日志。用于安全自检发现 `tokens.expired` 或 `tokens.invalid` 后的治理闭环。

后续建议：
1. JWT 或 Session
2. 小程序微信登录绑定
3. 高风险操作二次确认或审批流

## 五、当前状态与已实现端点矩阵

> 以下为当前代码已落地并可调用的接口集合（以 `api_server/main.py` 为准）。

### 1) 健康与依赖

| 分组 | 方法 | 路径 | 说明 |
|---|---|---|---|
| health | GET | `/health` | 服务状态、运行模式、后端类型 |
| health | GET | `/health/deps` | 数据库与缓存依赖健康检查 |

### 2) 认证与权限管理

| 分组 | 方法 | 路径 | 说明 |
|---|---|---|---|
| auth | POST | `/api/auth/login` | 登录并获取 token |
| auth | GET | `/api/auth/profile` | 当前身份 |
| auth | POST | `/api/auth/change-password` | 修改密码 |
| auth | POST | `/api/auth/logout` | 登出 |
| admin | GET | `/api/admin/users` | 用户列表 |
| admin | POST | `/api/admin/users` | 新增/更新用户 |
| admin | DELETE | `/api/admin/users/{username}` | 删除用户 |
| admin | POST | `/api/admin/tokens/revoke` | 撤销用户 token |
| admin | POST | `/api/admin/tokens/cleanup-expired` | 清理过期/异常 token |
| admin | GET | `/api/admin/auth-audit` | 认证审计日志 |
| admin | GET | `/api/admin/security-check` | 管理员安全自检 |

### 3) 运行中心与任务

| 分组 | 方法 | 路径 | 说明 |
|---|---|---|---|
| ops | GET | `/api/ops/tasks` | 最近任务运行记录 |
| ops | GET | `/api/ops/events` | 最近系统事件 |
| ops | GET | `/api/ops/center` | 运行中心聚合视图（含 registry） |
| message | GET | `/api/messages` | 统一消息流 |
| task | POST | `/api/task/trigger/{task_key}` | 通用任务触发 |
| scan | GET | `/api/scan/latest` | 最近扫描结果 |
| scan | POST | `/api/scan/run` | 扫描触发 |

### 4) 组合与快照

| 分组 | 方法 | 路径 | 说明 |
|---|---|---|---|
| snapshot | GET | `/api/snapshot/system` | 系统统一快照 |
| portfolio | GET | `/api/portfolio/summary` | 组合摘要 |
| portfolio | GET | `/api/portfolio/positions` | 持仓明细 |
| portfolio | GET | `/api/portfolio/recommendations` | 推荐列表 |

### 5) AI / OpenClaw / Registry

| 分组 | 方法 | 路径 | 说明 |
|---|---|---|---|
| assistant | GET | `/api/assistant/context` | 助手上下文 |
| assistant | GET | `/api/assistant/sessions` | 会话列表 |
| assistant | GET | `/api/assistant/session/{session_id}` | 会话消息 |
| assistant | POST | `/api/assistant/ask` | 助手问答 |
| openclaw | GET | `/api/openclaw/weights` | 策略权重 |
| openclaw | GET | `/api/openclaw/sources` | 数据源状态 |
| openclaw | GET | `/api/openclaw/daemon/status` | 后台 OpenClaw / daemon / 安全闸状态 |
| openclaw | GET | `/api/openclaw/config-audit` | OpenClaw 关键配置变更审计 |
| openclaw | POST | `/api/openclaw/config-audit/rollback` | 回滚审计记录对应的配置变更 |
| openclaw | GET | `/api/openclaw/daemon/alert-policy` | 后台告警策略 |
| openclaw | POST | `/api/openclaw/daemon/alert-policy` | 更新后台告警策略 |
| openclaw | POST | `/api/openclaw/daemon/alert-policy/reset` | 恢复默认后台告警策略 |
| openclaw | GET | `/api/openclaw/unattended-trade-guard` | 无人值守交易安全闸 |
| openclaw | POST | `/api/openclaw/unattended-trade-guard` | 更新无人值守交易安全闸 |
| openclaw | POST | `/api/openclaw/unattended-trade-guard/reset` | 恢复默认安全闸 |
| openclaw | POST | `/api/openclaw/unattended-trade-guard/replay` | 无下单回放安全闸 |
| openclaw | POST | `/api/openclaw/pipeline/run` | 全流程执行 |
| openclaw | POST | `/api/openclaw/learn/run` | 自主学习 |
| registry | GET | `/api/registry` | provider/strategy/notifier/workflow 总览 |
| registry | GET | `/api/registry/providers` | provider 清单 |
| registry | GET | `/api/registry/strategies` | strategy 清单 |
| registry | GET | `/api/registry/notifiers` | notifier 清单 |
| registry | GET | `/api/registry/workflows` | workflow 清单 |

### 6) 股票与验证

| 分组 | 方法 | 路径 | 说明 |
|---|---|---|---|
| stock | GET | `/api/stock/{code}` | 个股摘要 |
| stock | GET | `/api/stock/{code}/kline` | K 线 |
| stock | GET | `/api/stock/{code}/verify` | 个股验证记录 |
| verify | GET | `/api/verify/summary` | 验证统计 |
| verify | GET | `/api/verify/records` | 验证明细 |
| verify | POST | `/api/verify/calibrate` | 校准执行 |

### 7) 设置与审批

| 分组 | 方法 | 路径 | 说明 |
|---|---|---|---|
| settings | GET | `/api/settings/ai` | 读取 AI 配置 |
| settings | POST | `/api/settings/ai` | 保存 AI 配置 |
| settings | GET | `/api/settings/push` | 读取推送配置 |
| settings | POST | `/api/settings/push` | 保存推送配置 |
| settings | POST | `/api/settings/push/test` | 推送测试 |
| approval | POST | `/api/approval/trade` | 交易审批执行 |
| sync | POST | `/api/sync/export` | 导出运行态数据（可直接返回或写文件） |
| sync | POST | `/api/sync/import` | 从导出文件导入运行态数据 |

### 8) ops center 增量同步说明（当前实现）

- 首次请求：`GET /api/ops/center`（不带 token，返回全量 registry）
- 后续请求：`GET /api/ops/center?registry_token=<change_token>`
- 返回关键字段：
  - `registry_changed`：是否变化
  - `registry_sync.payload_mode`：`full` / `compact`
  - `registry_sync.cached`：服务端 registry 缓存命中
  - `registry.meta.change_token`：当前 token

## 六、运行方式

后续启动命令建议：

```bash
uvicorn api_server.main:app --host 0.0.0.0 --port 9000
```

冒烟验证命令：

```bash
python infra/smoke_refactor_core.py
python infra/smoke_api.py
```

若 `smoke_api` 提示 API 不可达，请先启动上面的 uvicorn 命令，或设置正确的 `FINQUANTA_API_BASE`。

## 七、意义

该 API 骨架的作用不是立即替代桌面版，而是：

1. 将核心能力服务化
2. 为 Web / 小程序 / 多用户打基础
3. 让未来产品化演进有稳定入口

