"""
组合跟踪器
- 每日净值记录（收益曲线）
- 策略效果分组对比
- 风控指标增强（夏普/最大连亏/盈亏比）
- 交易滑点模拟
- 操作日志统一记录
- 数据自动清理
"""
import logging
import numpy as np
from datetime import datetime, date, timedelta

from api_server.config import settings

from desktop.data_access import get_kv_json, get_repo

_log = logging.getLogger("portfolio_tracker")

_NAV_DDL_SQLITE = """
    CREATE TABLE IF NOT EXISTS daily_nav (
        date TEXT NOT NULL,
        mode TEXT NOT NULL,
        equity REAL,
        cash REAL,
        positions_value REAL,
        n_positions INTEGER,
        daily_return REAL,
        PRIMARY KEY (date, mode)
    );
    CREATE TABLE IF NOT EXISTS operation_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        module TEXT,
        action TEXT,
        detail TEXT
    );
"""


def _ensure_tables():
    if settings.db_backend == "postgres":
        return
    get_repo().executescript(_NAV_DDL_SQLITE)


def _upsert_daily_nav(
    repo,
    today_str: str,
    mode: str,
    eq: float,
    cash_val: float,
    pos_val: float,
    n_pos: int,
    daily_ret: float,
) -> None:
    if settings.db_backend == "postgres":
        repo.execute(
            """
            INSERT INTO daily_nav (date, mode, equity, cash, positions_value, n_positions, daily_return)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT (date, mode) DO UPDATE SET
            equity=EXCLUDED.equity, cash=EXCLUDED.cash, positions_value=EXCLUDED.positions_value,
            n_positions=EXCLUDED.n_positions, daily_return=EXCLUDED.daily_return
            """,
            (
                today_str,
                mode,
                round(eq, 2),
                round(cash_val, 2),
                round(pos_val, 2),
                n_pos,
                round(daily_ret, 4),
            ),
        )
    else:
        repo.execute(
            "INSERT OR REPLACE INTO daily_nav VALUES (?,?,?,?,?,?,?)",
            (
                today_str,
                mode,
                round(eq, 2),
                round(cash_val, 2),
                round(pos_val, 2),
                n_pos,
                round(daily_ret, 4),
            ),
        )


# ═══════════════════════════════════════
# 1. 每日净值记录
# ═══════════════════════════════════════

def record_daily_nav():
    """记录每日各仓位净值（收盘后调用）。"""
    _ensure_tables()
    from desktop.ai_portfolio import get_comparison

    comp = get_comparison()
    today_str = date.today().isoformat()
    repo = get_repo()

    for mode in ["full_auto", "auto", "custom", "quantum"]:
        c = comp.get(mode, {})
        eq = c.get("equity", 1_000_000)
        cash_val = c.get("cash", 0)
        pos_val = eq - cash_val
        n_pos = c.get("positions", 0)

        prev = repo.fetchone(
            "SELECT equity FROM daily_nav WHERE mode=? ORDER BY date DESC LIMIT 1",
            (mode,),
        )
        prev_eq = prev[0] if prev else 1_000_000
        daily_ret = (eq / prev_eq - 1) * 100 if prev_eq > 0 else 0

        _upsert_daily_nav(
            repo, today_str, mode, eq, cash_val, pos_val, n_pos, daily_ret,
        )

    try:
        pf = get_kv_json("manual_portfolio")
        if pf and isinstance(pf, dict):
            m_cash = pf.get("cash", 1_000_000)
            m_pos = pf.get("positions", [])
            m_val = sum(p.get("entry_price", 0) * p.get("shares", 0) for p in m_pos)
            m_eq = m_cash + m_val
            prev = repo.fetchone(
                "SELECT equity FROM daily_nav WHERE mode='manual_portfolio' ORDER BY date DESC LIMIT 1",
                (),
            )
            prev_eq = prev[0] if prev else 1_000_000
            daily_ret = (m_eq / prev_eq - 1) * 100 if prev_eq > 0 else 0
            _upsert_daily_nav(
                repo,
                today_str,
                "manual_portfolio",
                m_eq,
                m_cash,
                m_val,
                len(m_pos),
                daily_ret,
            )
    except Exception:
        pass

    _log.info("daily NAV recorded")


def get_nav_history(mode: str, days: int = 60) -> list[dict]:
    """获取净值历史。"""
    _ensure_tables()
    repo = get_repo()
    rows = repo.fetchall(
        "SELECT date, equity, daily_return FROM daily_nav "
        "WHERE mode=? ORDER BY date DESC LIMIT ?",
        (mode, days),
    )
    return [{"date": r[0], "equity": r[1], "daily_return": r[2]} for r in reversed(rows)]


# ═══════════════════════════════════════
# 2. 策略效果分组对比
# ═══════════════════════════════════════

def get_strategy_comparison() -> dict:
    """从走势验证按策略分组统计。"""
    repo = get_repo()
    rows = repo.fetchall(
        """
        SELECT strategy, COUNT(*) as total,
               SUM(CASE WHEN correct=1 THEN 1 ELSE 0 END) as wins,
               AVG(pnl_1d) as avg1, AVG(pnl_5d) as avg5, AVG(pnl_10d) as avg10
        FROM trend_verify WHERE correct >= 0
        GROUP BY strategy ORDER BY AVG(pnl_5d) DESC
        """,
        (),
    )

    result = []
    for strategy, total, wins, avg1, avg5, avg10 in rows:
        acc = wins / total * 100 if total > 0 else 0
        result.append({
            "strategy": strategy or "SEPA",
            "total": total, "wins": wins,
            "accuracy": round(acc, 1),
            "avg_pnl_1d": round(avg1 or 0, 2),
            "avg_pnl_5d": round(avg5 or 0, 2),
            "avg_pnl_10d": round(avg10 or 0, 2),
        })
    return result


# ═══════════════════════════════════════
# 3. 风控指标增强
# ═══════════════════════════════════════

def get_enhanced_risk_metrics(mode: str = "auto") -> dict:
    """计算增强风控指标：夏普比率、最大连续亏损天数、盈亏比。"""
    _ensure_tables()
    repo = get_repo()
    rows = repo.fetchall(
        "SELECT daily_return FROM daily_nav WHERE mode=? ORDER BY date",
        (mode,),
    )

    if len(rows) < 5:
        return {"sharpe": 0, "max_loss_streak": 0, "profit_factor": 0, "calmar": 0}

    returns = [r[0] for r in rows]

    mean_ret = np.mean(returns)
    std_ret = np.std(returns)
    sharpe = (mean_ret * 250) / (std_ret * np.sqrt(250)) if std_ret > 0 else 0

    max_streak = 0
    current_streak = 0
    for r in returns:
        if r < 0:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0

    gains = [r for r in returns if r > 0]
    losses = [abs(r) for r in returns if r < 0]
    avg_gain = np.mean(gains) if gains else 0
    avg_loss = np.mean(losses) if losses else 1
    profit_factor = avg_gain / avg_loss if avg_loss > 0 else 0

    cum = np.cumprod([1 + r / 100 for r in returns])
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    max_dd = abs(float(np.min(dd))) if len(dd) > 0 else 0
    annual_ret = (cum[-1] ** (250 / len(returns)) - 1) if len(returns) > 0 else 0
    calmar = annual_ret / max_dd if max_dd > 0 else 0

    return {
        "sharpe": round(float(sharpe), 2),
        "max_loss_streak": max_streak,
        "profit_factor": round(float(profit_factor), 2),
        "calmar": round(float(calmar), 2),
        "max_drawdown": round(float(max_dd * 100), 2),
        "total_days": len(returns),
    }


# ═══════════════════════════════════════
# 4. 滑点模拟
# ═══════════════════════════════════════

SLIPPAGE_RATE = 0.001  # 0.1% 单边滑点

def apply_slippage(price: float, is_buy: bool) -> float:
    """应用滑点：买入价上调、卖出价下调。"""
    if is_buy:
        return round(price * (1 + SLIPPAGE_RATE), 2)
    return round(price * (1 - SLIPPAGE_RATE), 2)


# ═══════════════════════════════════════
# 5. 操作日志
# ═══════════════════════════════════════

def log_operation(module: str, action: str, detail: str):
    """统一记录操作日志。"""
    _ensure_tables()
    try:
        get_repo().execute(
            "INSERT INTO operation_log (timestamp, module, action, detail) VALUES (?,?,?,?)",
            (datetime.now().isoformat(), module, action, detail),
        )
    except Exception as e:
        _log.warning(f"log_operation error: {e}")


def get_operation_log(limit: int = 50) -> list[dict]:
    """获取操作日志。"""
    _ensure_tables()
    rows = get_repo().fetchall(
        "SELECT timestamp, module, action, detail FROM operation_log ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    return [{"time": r[0], "module": r[1], "action": r[2], "detail": r[3]} for r in rows]


# ═══════════════════════════════════════
# 6. 数据自动清理
# ═══════════════════════════════════════

def cleanup_old_data(keep_days: int = 730):
    """清理超过 keep_days 天的日线数据和日志。"""
    cutoff = (date.today() - timedelta(days=keep_days)).isoformat()
    log_cutoff = (date.today() - timedelta(days=180)).isoformat()
    repo = get_repo()
    n_kline = n_log = 0
    with repo.conn() as conn:
        if settings.db_backend == "postgres":
            with conn.cursor() as cur:
                cur.execute("DELETE FROM daily_kline WHERE date < %s", (cutoff,))
                n_kline = cur.rowcount
                cur.execute("DELETE FROM operation_log WHERE timestamp < %s", (log_cutoff,))
                n_log = cur.rowcount
        else:
            c1 = conn.execute("DELETE FROM daily_kline WHERE date < ?", (cutoff,))
            n_kline = c1.rowcount
            c2 = conn.execute("DELETE FROM operation_log WHERE timestamp < ?", (log_cutoff,))
            n_log = c2.rowcount

    _log.info(f"cleanup: deleted {n_kline} klines (before {cutoff}), {n_log} logs")
    return {"klines_deleted": n_kline, "logs_deleted": n_log}
