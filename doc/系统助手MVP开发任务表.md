# FinQuanta 系统助手 MVP 开发任务表

## 目标
在 `FinQuanta AI` 现有问答基础上，补齐 `查询`、`解释`、`执行任务`、`修改数据`、`审计确认` 五类基础能力。

## 交付物
- `infra/assistant_actions_init.sql`
- `desktop/assistant_audit.py`
- `desktop/assistant_permissions.py`
- `desktop/assistant_intents.py`
- `desktop/assistant_actions.py`
- `desktop/system_assistant.py`

## P0 基础链路
| 编号 | 任务 | 产出 | 依赖 | 验收标准 |
|---|---|---|---|---|
| P0-1 | 建立系统助手动作表 | `assistant_actions` / `assistant_action_logs` | 无 | 能记录待确认、已执行、失败动作 |
| P0-2 | 建立审计访问层 | `desktop/assistant_audit.py` | P0-1 | 能创建动作、写执行日志、查最近动作 |
| P0-3 | 建立意图白名单与权限层 | `desktop/assistant_permissions.py` | 无 | 非白名单动作被拒绝 |
| P0-4 | 建立自然语言意图解析骨架 | `desktop/assistant_intents.py` | P0-3 | 能识别查询、解释、任务执行、配置修改 |
| P0-5 | 建立动作执行分发层 | `desktop/assistant_actions.py` | P0-2, P0-3, P0-4 | 能执行查询、解释、指定任务 |
| P0-6 | 建立系统助手统一入口 | `desktop/system_assistant.py` | P0-2, P0-4, P0-5 | 能处理输入、生成待确认动作、执行并回写审计 |

## P1 首批可用能力
| 编号 | 任务 | 产出 | 依赖 | 验收标准 |
|---|---|---|---|---|
| P1-1 | 查询系统总览 | `query.system_snapshot` | P0-5 | 能返回总资产、现金、持仓、市场状态 |
| P1-2 | 查询走势验证概况 | `query.trend_verify_summary` | P0-5 | 能返回总信号、准确率、均值 |
| P1-3 | 解释走势验证为空 | `explain.trend_verify_empty` | P0-5 | 能说明数据不足和行情滞后原因 |
| P1-4 | 执行走势验证校准 | `run.calibrate_trend_verify` | P0-5 | 能调用校准并返回结果 |
| P1-5 | 执行日线补同步 | `run.refresh_latest_kline` | P0-5 | 能调用补同步并返回结果 |
| P1-6 | 修改手动仓现金 | `update.manual_portfolio_cash` | P0-5 | 先预览，再确认执行 |
| P1-7 | 修改调度时间 | `update.scheduler_time` | P0-5 | 先预览，再确认执行 |

## P2 UI 接入
| 编号 | 任务 | 产出 | 依赖 | 验收标准 |
|---|---|---|---|---|
| P2-1 | AI 聊天面板接入系统助手 | `desktop/panels/ai_chat.py` | P1 | 用户输入可触发系统助手链路 |
| P2-2 | 动作确认卡片 | `确认执行/取消` UI | P1 | 修改类动作必须先确认 |
| P2-3 | 执行结果卡片 | 结果展示区 | P1 | 成功/失败和摘要可见 |
| P2-4 | 审计历史面板 | 新页签或运行中心扩展 | P0-2 | 可查看最近动作及状态 |

## 首批意图白名单
### 查询
- `query.system_snapshot`
- `query.market_state`
- `query.task_runs`
- `query.system_events`
- `query.trend_verify_summary`
- `query.trend_verify_record`

### 解释
- `explain.trend_verify_empty`
- `explain.task_failure`

### 执行
- `run.refresh_snapshot`
- `run.refresh_latest_kline`
- `run.calibrate_trend_verify`

### 修改
- `update.scheduler_time`
- `update.manual_portfolio_cash`

## 风险边界
- 禁止直接下单
- 禁止执行任意 Shell
- 禁止执行任意 Python
- 禁止无确认修改配置
- 禁止删除历史数据

## 联调建议
1. 先在纯 Python 层验证 `system_assistant.handle_user_message()`
2. 再接 `AIChatPanel`
3. 最后补确认卡片和动作历史页
