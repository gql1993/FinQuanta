# FinQuanta 小程序页面清单与接口映射表

## 一、目标

本文档用于把当前 FinQuanta 的桌面端 / Web 端能力，映射为微信小程序可落地的页面结构与接口调用关系。

设计原则：

1. 小程序优先承担“查看 + 审批 + 触发”
2. 不在第一版做复杂参数编辑
3. 所有核心数据统一来自 API 服务层
4. 与桌面端共享 `system_snapshot`、任务日志、系统事件和业务结果

---

## 二、小程序页面结构（建议版本）

```text
首页
├─ 1. 总览页
├─ 2. 选股页
├─ 3. AI仓页
├─ 4. OpenClaw页
├─ 5. 个股分析页
├─ 6. 走势验证页
└─ 7. 消息中心页
```

---

## 三、页面清单

### 1. 总览页（Home）

**目标：**
让用户在微信里一眼看到系统整体状态。

**展示内容：**

1. 五仓对比（手动仓 + 完全自主 + AI推荐 + 自定义 + 量子仓）
2. 市场状态机（强趋势 / 轮动 / 风险收缩 / 中性）
3. 风险快照（VaR95 / VaR99 / HHI / 最大敞口）
4. 总资产 / 总可用现金 / 总持仓数

**对应 API：**

- `GET /api/snapshot/system`

---

### 2. 选股页（Scan）

**目标：**
查看最新选股结果并可远程触发扫描。

**展示内容：**

1. 最近扫描结果
2. 强烈买入列表
3. 板块信息
4. 当前最强策略
5. 当前最强板块

**可操作：**

1. 点击“立即扫描”
2. 点击股票进入个股分析页

**对应 API：**

- `GET /api/scan/latest`
- `POST /api/scan/run`
- `GET /api/snapshot/system`

---

### 3. AI仓页（Portfolio）

**目标：**
查看 AI 四仓 + 手动仓状态，后续支持审批。

**展示内容：**

1. 各仓收益率
2. 各仓交易数
3. 各仓持仓列表
4. 完全自主仓 / AI推荐仓 / 自定义仓 / 量子仓 详情

**可操作（第二阶段）：**

1. 批准 AI 推荐
2. 拒绝 AI 推荐
3. 查看持仓建议与卖出建议

**对应 API：**

- `GET /api/portfolio/summary`
- `GET /api/portfolio/positions`
- `POST /api/approval/trade`（当前为占位）

---

### 4. OpenClaw 页（Ops / Pipeline）

**目标：**
远程查看 OpenClaw 当前状态，并可触发核心任务。

**展示内容：**

1. 数据源状态
2. 运行中心（任务运行 + 系统事件）
3. 策略权重
4. 最近学习结果

**可操作：**

1. 启动全流程
2. 启动学习
3. 触发扫描
4. 触发风险计算
5. 触发回测

**对应 API：**

- `GET /api/ops/center`
- `GET /api/openclaw/weights`
- `POST /api/openclaw/pipeline/run`
- `POST /api/openclaw/learn/run`
- `POST /api/task/trigger/{task_key}`

---

### 5. 个股分析页（Stock）

**目标：**
查看单只股票的行情、K线、验证记录。

**展示内容：**

1. 股票基本信息
2. 最新价、涨跌幅、60日高低点
3. K 线图数据
4. 该股票在走势验证中的历史记录

**可操作：**

1. 搜索股票代码
2. 从其他页面跳转进入

**对应 API：**

- `GET /api/stock/{code}`
- `GET /api/stock/{code}/kline`
- `GET /api/stock/{code}/verify`

---

### 6. 走势验证页（Verify）

**目标：**
查看策略信号的实际表现和校准结果。

**展示内容：**

1. 总信号数
2. 准确率
3. 1日/2日/3日/5日均涨
4. 各信号列表
5. 分析原因

**后续可操作：**

1. 手动触发一次校准
2. 查看某条信号的详细分析

**对应 API（建议后续补）**

- `GET /api/verify/summary`
- `GET /api/verify/records`
- `POST /api/task/trigger/verify`

当前可通过：
- `GET /api/stock/{code}/verify`
- `GET /api/snapshot/system`
部分实现。

---

### 7. 消息中心页（Messages）

**目标：**
在小程序内查看最近预警、推送、操作、系统事件。

**展示内容：**

1. 止损止盈预警
2. 强烈买入推送
3. OpenClaw 执行事件
4. 手动仓/AI仓操作事件

**对应 API：**

- `GET /api/messages`

---

## 四、接口映射总表

| 页面 | 数据读取接口 | 动作接口 |
|---|---|---|
| 总览页 | `/api/snapshot/system` | 无 |
| 选股页 | `/api/scan/latest` | `/api/scan/run` |
| AI仓页 | `/api/portfolio/summary` `/api/portfolio/positions` | `/api/approval/trade` |
| OpenClaw页 | `/api/ops/center` `/api/openclaw/weights` | `/api/openclaw/pipeline/run` `/api/openclaw/learn/run` `/api/task/trigger/{task_key}` |
| 个股页 | `/api/stock/{code}` `/api/stock/{code}/kline` `/api/stock/{code}/verify` | 无 |
| 走势验证页 | （建议补）`/api/verify/summary` `/api/verify/records` | （建议补）`/api/task/trigger/verify` |
| 消息中心 | `/api/messages` | 无 |

---

## 五、已具备 / 待补齐

### 已具备接口

- `POST /api/auth/login`
- `GET /api/auth/profile`
- `GET /api/snapshot/system`
- `GET /api/ops/tasks`
- `GET /api/ops/events`
- `GET /api/ops/center`
- `GET /api/scan/latest`
- `POST /api/scan/run`
- `GET /api/portfolio/summary`
- `GET /api/portfolio/positions`
- `GET /api/openclaw/weights`
- `POST /api/openclaw/pipeline/run`
- `POST /api/openclaw/learn/run`
- `GET /api/stock/{code}`
- `GET /api/stock/{code}/kline`
- `GET /api/stock/{code}/verify`
- `GET /api/messages`
- `POST /api/task/trigger/{task_key}`
- `POST /api/approval/trade`（占位）

### 下一步待补齐接口

1. `/api/verify/summary`
2. `/api/verify/records`
3. `/api/settings/push`
4. `/api/settings/ai`
5. `/api/rotation/strategy`
6. `/api/rotation/sector`

---

## 六、小程序前端实现建议

### 方式

建议采用：

- **Taro + React**
或
- **uni-app**

原因：

1. 比原生小程序更易维护
2. 后续可复用为 H5
3. 便于与现有 Web 设计语言统一

### 页面优先级

#### MVP 第一版

1. 总览页
2. 选股页
3. AI仓页
4. OpenClaw页
5. 消息中心页

#### 第二版

1. 个股分析页
2. 走势验证页
3. 审批入口

#### 第三版

1. 参数设置
2. 自定义板块管理
3. 更细粒度任务触发

---

## 七、当前状态结论

从系统工程角度看：

> **FinQuanta 已经具备小程序版最核心的后端基础。**

具体表现为：

1. 有统一快照
2. 有统一任务运行日志
3. 有统一系统事件日志
4. 有统一 AI 仓摘要
5. 有 OpenClaw 任务触发入口
6. 有初步鉴权模型

因此，下一步已经不是“能不能做小程序”，而是：

> **什么时候开始做小程序前端，以及用什么前端框架来做。**

