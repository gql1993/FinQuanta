-- FinQuanta PostgreSQL 初始化脚手架
-- 说明：
-- 1. 当前仍以 SQLite 为主，本文件用于后续 PostgreSQL 迁移准备
-- 2. 先创建最核心的业务表，后续可逐步补齐

CREATE TABLE IF NOT EXISTS kv_store (
    key TEXT PRIMARY KEY,
    value JSONB,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stock_list (
    code TEXT PRIMARY KEY,
    name TEXT,
    updated_at TIMESTAMP
);

-- 与 desktop/db.py init_db（SQLite）对齐
CREATE TABLE IF NOT EXISTS financial (
    code TEXT PRIMARY KEY,
    name TEXT,
    pe_dynamic DOUBLE PRECISION,
    pb DOUBLE PRECISION,
    total_mv DOUBLE PRECISION,
    circ_mv DOUBLE PRECISION,
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS predictions (
    code TEXT NOT NULL,
    strategy TEXT NOT NULL,
    predict_date DATE NOT NULL,
    horizon TEXT NOT NULL,
    predicted_price DOUBLE PRECISION,
    actual_price DOUBLE PRECISION,
    PRIMARY KEY (code, strategy, predict_date, horizon)
);
CREATE INDEX IF NOT EXISTS idx_predictions_code ON predictions(code);

CREATE TABLE IF NOT EXISTS board_stocks (
    board TEXT NOT NULL,
    code TEXT NOT NULL,
    PRIMARY KEY (board, code)
);
CREATE INDEX IF NOT EXISTS idx_board_stocks_board ON board_stocks(board);
CREATE INDEX IF NOT EXISTS idx_board_stocks_code ON board_stocks(code);

CREATE TABLE IF NOT EXISTS daily_kline (
    code TEXT NOT NULL,
    date DATE NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    amount DOUBLE PRECISION,
    pct_change DOUBLE PRECISION,
    PRIMARY KEY (code, date)
);
CREATE INDEX IF NOT EXISTS idx_daily_kline_code ON daily_kline(code);
CREATE INDEX IF NOT EXISTS idx_daily_kline_date ON daily_kline(date);

CREATE TABLE IF NOT EXISTS ai_positions (
    id BIGSERIAL PRIMARY KEY,
    mode TEXT,
    code TEXT,
    name TEXT,
    entry_date DATE,
    entry_price DOUBLE PRECISION,
    shares INTEGER,
    stop_loss DOUBLE PRECISION,
    status TEXT,
    exit_date DATE,
    exit_price DOUBLE PRECISION,
    exit_reason TEXT,
    pnl DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS idx_ai_positions_mode_status ON ai_positions(mode, status);
CREATE INDEX IF NOT EXISTS idx_ai_positions_code ON ai_positions(code);

CREATE TABLE IF NOT EXISTS ai_trade_log (
    id BIGSERIAL PRIMARY KEY,
    mode TEXT,
    timestamp TIMESTAMP,
    action TEXT,
    code TEXT,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_ai_trade_log_mode_time ON ai_trade_log(mode, timestamp DESC);

CREATE TABLE IF NOT EXISTS ai_decision_memory (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP,
    mode TEXT,
    boards TEXT,
    decisions JSONB,
    analysis TEXT,
    intel_summary TEXT,
    candidates_count INTEGER,
    market_regime TEXT,
    actual_results TEXT,
    calibrated INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ai_decision_memory_mode_time ON ai_decision_memory(mode, timestamp DESC);

CREATE TABLE IF NOT EXISTS trend_verify (
    id BIGSERIAL PRIMARY KEY,
    code TEXT,
    name TEXT,
    board TEXT,
    signal_date DATE,
    signal_price DOUBLE PRECISION,
    score INTEGER,
    signal_type TEXT,
    strategy TEXT,
    vcp TEXT,
    breakout TEXT,
    price_1d DOUBLE PRECISION,
    price_2d DOUBLE PRECISION,
    price_3d DOUBLE PRECISION,
    price_5d DOUBLE PRECISION,
    price_10d DOUBLE PRECISION,
    price_20d DOUBLE PRECISION,
    price_60d DOUBLE PRECISION,
    pnl_1d DOUBLE PRECISION,
    pnl_2d DOUBLE PRECISION,
    pnl_3d DOUBLE PRECISION,
    pnl_5d DOUBLE PRECISION,
    pnl_10d DOUBLE PRECISION,
    pnl_20d DOUBLE PRECISION,
    pnl_60d DOUBLE PRECISION,
    analysis TEXT,
    correct INTEGER DEFAULT -1,
    last_calibrated DATE,
    status TEXT DEFAULT 'tracking'
);
CREATE INDEX IF NOT EXISTS idx_trend_verify_code_date ON trend_verify(code, signal_date);

CREATE TABLE IF NOT EXISTS system_event_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP,
    source TEXT,
    category TEXT,
    level TEXT,
    title TEXT,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS task_run_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP,
    task_name TEXT,
    trigger_source TEXT,
    status TEXT,
    elapsed_ms DOUBLE PRECISION,
    summary TEXT,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS operation_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP,
    module TEXT,
    action TEXT,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS daily_nav (
    date DATE NOT NULL,
    mode TEXT NOT NULL,
    equity DOUBLE PRECISION,
    cash DOUBLE PRECISION,
    positions_value DOUBLE PRECISION,
    n_positions INTEGER,
    daily_return DOUBLE PRECISION,
    PRIMARY KEY (date, mode)
);

CREATE TABLE IF NOT EXISTS api_users (
    username TEXT PRIMARY KEY,
    password TEXT,
    role TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS api_tokens (
    token TEXT PRIMARY KEY,
    username TEXT,
    role TEXT,
    expires_at TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS auth_audit_log (
    id TEXT PRIMARY KEY,
    timestamp TEXT,
    actor TEXT,
    username TEXT,
    action TEXT,
    success INTEGER,
    detail TEXT
);

-- 与 api_server/assistant_service、desktop/panels/ai_chat 对齐
CREATE TABLE IF NOT EXISTS ai_chat_history (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    role TEXT,
    content TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ai_chat_history_session ON ai_chat_history(session_id);
CREATE INDEX IF NOT EXISTS idx_ai_chat_history_created ON ai_chat_history(created_at DESC);

-- OpenClaw 自主学习（与 desktop/openclaw_learner.py SQLite DDL 对齐）
CREATE TABLE IF NOT EXISTS openclaw_learning (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP,
    module TEXT,
    metric TEXT,
    value DOUBLE PRECISION,
    detail TEXT,
    applied INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS openclaw_strategy_weights (
    strategy TEXT PRIMARY KEY,
    weight DOUBLE PRECISION DEFAULT 1.0,
    accuracy DOUBLE PRECISION DEFAULT 0,
    avg_pnl_5d DOUBLE PRECISION DEFAULT 0,
    sample_count INTEGER DEFAULT 0,
    last_updated TIMESTAMP
);

-- 自定义仓跟踪（与 desktop/custom_portfolio.py SQLite DDL 对齐）
CREATE TABLE IF NOT EXISTS custom_tracking (
    id BIGSERIAL PRIMARY KEY,
    code TEXT,
    name TEXT,
    board TEXT,
    buy_date DATE,
    buy_price DOUBLE PRECISION,
    shares INTEGER,
    score INTEGER,
    price_5d DOUBLE PRECISION,
    price_20d DOUBLE PRECISION,
    price_60d DOUBLE PRECISION,
    price_120d DOUBLE PRECISION,
    pnl_5d DOUBLE PRECISION,
    pnl_20d DOUBLE PRECISION,
    pnl_60d DOUBLE PRECISION,
    pnl_120d DOUBLE PRECISION,
    last_calibrated DATE,
    status TEXT DEFAULT 'tracking'
);
