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
{"ok": true, "service": "finquanta-api"}
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

### 5. 组合摘要

`GET /api/portfolio/summary`

返回：
- 手动仓摘要
- AI 四仓摘要
- 全仓 totals

### 6. OpenClaw 权重

`GET /api/openclaw/weights`

返回自主学习引擎输出的策略权重。

### 7. 触发 OpenClaw 全流程

`POST /api/openclaw/pipeline/run`

请求：
```json
{
  "dry_run": false,
  "boards": ["人工智能", "芯片", "量子科技"]
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

当前版本为演示级鉴权：

- 表：`api_users`
- 表：`api_tokens`
- 默认账号：`admin / admin123`

后续建议：
1. 密码哈希化
2. JWT 或 Session
3. 角色权限分层：admin / operator / viewer
4. 小程序微信登录绑定

## 五、下一步接口建议

### 应新增接口

1. `/api/scan/run`
2. `/api/scan/latest`
3. `/api/stock/{code}`
4. `/api/stock/{code}/kline`
5. `/api/openclaw/run-center`
6. `/api/settings/push`
7. `/api/settings/ai`
8. `/api/task/trigger/{task}`

### 面向小程序的核心接口优先级

高优先级：
- `/api/snapshot/system`
- `/api/portfolio/summary`
- `/api/ops/tasks`
- `/api/ops/events`
- `/api/openclaw/pipeline/run`

中优先级：
- `/api/scan/latest`
- `/api/stock/{code}/kline`
- `/api/openclaw/weights`

## 六、运行方式

后续启动命令建议：

```bash
uvicorn api_server.main:app --host 0.0.0.0 --port 9000
```

## 七、意义

该 API 骨架的作用不是立即替代桌面版，而是：

1. 将核心能力服务化
2. 为 Web / 小程序 / 多用户打基础
3. 让未来产品化演进有稳定入口

