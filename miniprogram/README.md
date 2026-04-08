# FinQuanta 微信小程序前端骨架

## 目录说明

- `app.js / app.json / app.wxss`：小程序全局配置
- `utils/request.js`：统一 API 请求层
- `pages/login`：登录页
- `pages/dashboard`：总览页
- `pages/scan`：选股页
- `pages/portfolio`：AI仓页
- `pages/openclaw`：OpenClaw 页
- `pages/messages`：消息中心页
- `pages/stock`：个股详情页
- `pages/verify`：走势验证页

## 已对接的后端接口

- `POST /api/auth/login`
- `GET /api/auth/profile`
- `GET /api/snapshot/system`
- `GET /api/scan/latest`
- `POST /api/scan/run`
- `GET /api/portfolio/summary`
- `GET /api/portfolio/positions`
- `GET /api/openclaw/weights`
- `POST /api/openclaw/pipeline/run`
- `POST /api/openclaw/learn/run`
- `GET /api/ops/center`
- `GET /api/messages`
- `GET /api/stock/{code}`
- `GET /api/stock/{code}/kline`
- `GET /api/stock/{code}/verify`
- `POST /api/task/trigger/{task_key}`

## 使用方式

1. 用微信开发者工具打开 `miniprogram` 目录
2. 在 `utils/request.js` 中修改 `API_BASE`
3. 先运行后端：

```bash
uvicorn api_server.main:app --host 0.0.0.0 --port 9000
```

4. 再用小程序调试器运行

## 当前阶段

这是第一版**可运行骨架**，重点完成：

- 登录
- 总览
- 选股查看与触发扫描
- AI仓摘要查看
- OpenClaw 全流程与学习触发
- 消息中心

后续可继续补：

- 交易审批流
- 个股 K 线图
- 走势验证详情
- 用户权限细化
