-- FinQuanta 系统助手动作与审计表
-- 说明：
-- 1. 该文件优先服务 SQLite，本项目现阶段也可作为 PostgreSQL 迁移参考。
-- 2. JSON 内容统一先按 TEXT 保存，应用层负责序列化/反序列化。

CREATE TABLE IF NOT EXISTS assistant_actions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_text TEXT NOT NULL,
    intent TEXT NOT NULL,
    target TEXT,
    action TEXT,
    action_key TEXT,
    arguments_json TEXT,
    preview_json TEXT,
    risk_level TEXT DEFAULT 'low',
    requires_confirmation INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    created_at TEXT NOT NULL,
    confirmed_at TEXT,
    executed_at TEXT,
    error_text TEXT
);

CREATE INDEX IF NOT EXISTS idx_assistant_actions_session
ON assistant_actions(session_id);

CREATE INDEX IF NOT EXISTS idx_assistant_actions_status
ON assistant_actions(status);

CREATE INDEX IF NOT EXISTS idx_assistant_actions_created
ON assistant_actions(created_at DESC);

CREATE TABLE IF NOT EXISTS assistant_action_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id TEXT NOT NULL,
    step TEXT,
    level TEXT DEFAULT 'info',
    message TEXT,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_assistant_action_logs_action
ON assistant_action_logs(action_id, created_at DESC);
