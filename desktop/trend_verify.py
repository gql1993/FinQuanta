"""
走势验证模块
记录每次选股雷达产生的"强烈建议买入"信号，跟踪其未来实际走势，
定期校准并分析预测准确率。
"""
import os
import json
import numpy as np
from datetime import datetime, date, timedelta

from api_server.config import settings

from desktop.data_sync import refresh_latest_kline
from desktop.data_access import RepoCompatConnection


def _init_table():
    if settings.db_backend == "postgres":
        return
    conn = RepoCompatConnection()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS trend_verify (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        name TEXT,
        board TEXT,
        signal_date TEXT,
        signal_price REAL,
        score INTEGER,
        signal_type TEXT,
        strategy TEXT,
        vcp TEXT,
        breakout TEXT,
        -- 未来实际价格
        price_1d REAL, price_2d REAL,
        price_3d REAL, price_5d REAL, price_10d REAL, price_20d REAL, price_60d REAL,
        -- 未来实际收益
        pnl_1d REAL, pnl_2d REAL,
        pnl_3d REAL, pnl_5d REAL, pnl_10d REAL, pnl_20d REAL, pnl_60d REAL,
        -- 分析
        analysis TEXT,
        correct INTEGER DEFAULT -1,
        last_calibrated TEXT,
        status TEXT DEFAULT 'tracking'
    );
    CREATE INDEX IF NOT EXISTS idx_tv_code ON trend_verify(code);
    CREATE INDEX IF NOT EXISTS idx_tv_date ON trend_verify(signal_date);
    """)
    conn.commit()
    conn.close()


_init_table()


def _ensure_schema(conn) -> None:
    """兼容旧库结构，补齐新字段。"""
    alter_sqls = [
        "ALTER TABLE trend_verify ADD COLUMN price_1d REAL",
        "ALTER TABLE trend_verify ADD COLUMN price_2d REAL",
        "ALTER TABLE trend_verify ADD COLUMN root_cause TEXT",
        "ALTER TABLE trend_verify ADD COLUMN failure_tags TEXT",
        "ALTER TABLE trend_verify ADD COLUMN improvement_hint TEXT",
        "ALTER TABLE trend_verify ADD COLUMN market_regime TEXT",
    ]
    for sql in alter_sqls:
        try:
            conn.execute(sql)
        except Exception:
            pass


def _serialize_tags(tags: list[str]) -> str:
    return json.dumps(list(dict.fromkeys([str(tag).strip() for tag in tags if str(tag).strip()])), ensure_ascii=False)


def _parse_tags(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed if str(x).strip()]
    except Exception:
        pass
    return [part.strip() for part in str(raw).split("；") if part.strip()]


def _build_common_filters(
    *,
    status: str = "",
    strategy: str = "",
    board: str = "",
    root_cause: str = "",
    market_regime: str = "",
    failed_only: bool = False,
    since_days: int = 0,
) -> tuple[list[str], list]:
    where_parts: list[str] = []
    params: list = []

    if status:
        where_parts.append("status=?")
        params.append(status)
    if strategy:
        where_parts.append("LOWER(strategy)=LOWER(?)")
        params.append(strategy)
    if board:
        where_parts.append("board=?")
        params.append(board)
    if root_cause:
        where_parts.append("root_cause=?")
        params.append(root_cause)
    if market_regime:
        where_parts.append("market_regime=?")
        params.append(market_regime)
    if failed_only:
        where_parts.append("correct=0")
    if since_days and since_days > 0:
        cutoff = (date.today() - timedelta(days=since_days)).isoformat()
        where_parts.append("signal_date>=?")
        params.append(cutoff)

    return where_parts, params


def _classify_failure_profile(metrics: dict) -> dict:
    """基于结构化指标给出失败根因和改进建议。"""
    best_pnl = float(metrics.get("best_pnl", 0) or 0)
    max_gain = float(metrics.get("max_gain", 0) or 0)
    max_loss = float(metrics.get("max_loss", 0) or 0)
    index_pnl = float(metrics.get("index_pnl", 0) or 0)
    ma_break = bool(metrics.get("ma_break"))
    weak_volume = bool(metrics.get("weak_volume"))
    consecutive_down = int(metrics.get("consecutive_down", 0) or 0)
    market_regime = str(metrics.get("market_regime", "中性") or "中性")

    tags: list[str] = []
    if market_regime:
        tags.append(market_regime)

    if best_pnl > 0:
        if max_gain >= 8:
            tags.append("趋势延续")
            tags.append("突破确认")
            return {
                "root_cause": "信号有效",
                "failure_tags": tags,
                "improvement_hint": "该信号整体有效，可保留当前条件并补充分批止盈。",
                "market_regime": market_regime,
            }
        tags.append("弱转强")
        return {
            "root_cause": "信号基本有效",
            "failure_tags": tags,
            "improvement_hint": "可保留该策略，同时增加持有纪律和回撤容忍区间。",
            "market_regime": market_regime,
        }

    if index_pnl <= -2.5:
        tags.extend(["市场拖累", "大盘走弱"])
        return {
            "root_cause": "市场拖累",
            "failure_tags": tags,
            "improvement_hint": "建议增加指数趋势过滤和风险开关，弱市减少追涨型信号。",
            "market_regime": market_regime,
        }

    if max_gain >= 5:
        tags.extend(["冲高回落", "兑现不足"])
        return {
            "root_cause": "冲高回落",
            "failure_tags": tags,
            "improvement_hint": "建议增加突破后跟随确认和分批止盈规则，避免假突破回落。",
            "market_regime": market_regime,
        }

    if weak_volume:
        tags.extend(["动能不足", "量能未确认"])
        return {
            "root_cause": "动能不足",
            "failure_tags": tags,
            "improvement_hint": "建议提高量比/放量确认阈值，缩量突破信号需要更严格过滤。",
            "market_regime": market_regime,
        }

    if ma_break:
        tags.extend(["跌破均线", "趋势破位"])
        return {
            "root_cause": "趋势破位",
            "failure_tags": tags,
            "improvement_hint": "建议加入20日线/50日线失守退出条件，避免趋势结构被破坏后继续持有。",
            "market_regime": market_regime,
        }

    if consecutive_down >= 4 or max_loss <= -8:
        tags.extend(["趋势反转", "止损不足"])
        return {
            "root_cause": "趋势反转",
            "failure_tags": tags,
            "improvement_hint": "建议强化次日确认与止损规则，对连续走弱的信号更快止损。",
            "market_regime": market_regime,
        }

    tags.extend(["个股弱势", "题材不强"])
    return {
        "root_cause": "个股弱势",
        "failure_tags": tags,
        "improvement_hint": "建议叠加板块强度、相对强弱和主线题材过滤，减少弱势个股误触发。",
        "market_regime": market_regime,
    }


def _build_failure_attribution(code: str, sig_date: str, sig_price: float, updates: dict, conn) -> dict:
    """构建结构化失败归因。"""
    pnl1 = updates.get("pnl_1d")
    pnl2 = updates.get("pnl_2d")
    pnl3 = updates.get("pnl_3d")
    pnl5 = updates.get("pnl_5d")

    cur_after = conn.execute(
        "SELECT date, close, high, low, volume FROM daily_kline "
        "WHERE code=? AND date>=? ORDER BY date LIMIT 30",
        (code, sig_date),
    )
    rows_after = cur_after.fetchall()
    cur_before = conn.execute(
        "SELECT close, high, low, volume FROM daily_kline "
        "WHERE code=? AND date<? ORDER BY date DESC LIMIT 60",
        (code, sig_date),
    )
    rows_before = cur_before.fetchall()

    if len(rows_after) < 2:
        return {
            "root_cause": "数据不足",
            "failure_tags": _serialize_tags(["数据不足"]),
            "improvement_hint": "等待更多交易日数据后再归因。",
            "market_regime": "未知",
        }

    closes_a = [float(r[1]) for r in rows_after]
    highs_a = [float(r[2]) for r in rows_after]
    lows_a = [float(r[3]) for r in rows_after]
    vols_a = [float(r[4]) for r in rows_after]

    best_pnl = pnl5 if pnl5 is not None else pnl3 if pnl3 is not None else pnl2 if pnl2 is not None else pnl1 if pnl1 is not None else 0
    n_a = min(len(closes_a), 10)
    max_gain = (max(highs_a[:n_a]) / sig_price - 1) * 100 if sig_price > 0 and n_a > 0 else 0
    max_loss = (min(lows_a[:n_a]) / sig_price - 1) * 100 if sig_price > 0 and n_a > 0 else 0

    weak_volume = False
    if len(vols_a) >= 3:
        vol_sig = vols_a[0]
        vol_avg_after = float(np.mean(vols_a[1:min(6, len(vols_a))]))
        weak_volume = vol_avg_after > 0 and vol_sig < vol_avg_after * 0.5

    ma_break = False
    if len(rows_before) >= 20:
        closes_b = [float(r[0]) for r in reversed(rows_before)]
        ma20_b = float(np.mean(closes_b[-20:]))
        cur_price = closes_a[min(len(closes_a) - 1, 4)]
        ma_break = sig_price > ma20_b and cur_price < ma20_b

    consecutive_down = 0
    if len(closes_a) >= 5:
        consecutive_down = sum(
            1 for i in range(1, min(6, len(closes_a)))
            if closes_a[i] < closes_a[i - 1]
        )

    index_pnl = 0.0
    market_regime = "中性"
    try:
        idx_rows = conn.execute(
            "SELECT close FROM daily_kline WHERE code='000300' AND date>=? ORDER BY date LIMIT 10",
            (sig_date,),
        ).fetchall()
        if len(idx_rows) >= 3:
            index_pnl = (float(idx_rows[-1][0]) / float(idx_rows[0][0]) - 1) * 100
            if index_pnl <= -2.5:
                market_regime = "弱市"
            elif index_pnl >= 2.5:
                market_regime = "强市"
    except Exception:
        pass

    structured = _classify_failure_profile(
        {
            "best_pnl": best_pnl,
            "max_gain": max_gain,
            "max_loss": max_loss,
            "index_pnl": index_pnl,
            "weak_volume": weak_volume,
            "ma_break": ma_break,
            "consecutive_down": consecutive_down,
            "market_regime": market_regime,
        }
    )
    return {
        "root_cause": structured["root_cause"],
        "failure_tags": _serialize_tags(structured.get("failure_tags", [])),
        "improvement_hint": structured["improvement_hint"],
        "market_regime": structured["market_regime"],
    }


def _get_latest_market_date(conn) -> str:
    """返回本地行情库中的最新交易日。"""
    try:
        row = conn.execute("SELECT MAX(date) FROM daily_kline").fetchone()
        return row[0] if row and row[0] else ""
    except Exception:
        return ""


def _refresh_tracking_klines(rows: list[tuple]) -> dict:
    """
    在校准前定向补最近待验证股票的日线。
    仅刷新 tracking 记录涉及到的股票，避免走势验证日期跑在行情库前面。
    """
    codes = sorted({code for _, code, _, _ in rows if code})
    if not codes:
        return {"codes_processed": 0, "fetched": 0, "rows_updated": 0, "failed": 0}
    try:
        return refresh_latest_kline(
            codes=codes,
            max_codes=len(codes),
            stale_after_days=1,
        )
    except Exception:
        return {"codes_processed": 0, "fetched": 0, "rows_updated": 0, "failed": 0}


def record_signals(candidates: list[dict], strategy: str = "SEPA"):
    """
    从选股扫描结果中记录信号到走势验证表。
    自动去重（同一天同一股票不重复记录）。
    不再要求"强烈买入"标签——评分 ≥ 40 的候选均记录。
    """
    conn = RepoCompatConnection()
    today = date.today().isoformat()
    signal_day = _get_latest_market_date(conn) or today
    if signal_day > today:
        signal_day = today

    # 预加载板块映射：code → board
    board_map = {}
    try:
        for r in conn.execute("SELECT code, board FROM board_stocks"):
            if r[0] not in board_map:
                board_map[r[0]] = r[1]
    except Exception:
        pass

    recorded = 0
    for c in candidates:
        code = c.get("代码", "")
        if not code:
            continue

        # 评分阈值：≥40 或有明确买入标签
        score = 0
        try:
            score = int(c.get("评分", "0"))
        except (ValueError, TypeError):
            pass
        buy_advice = c.get("建议买入", "")
        if score < 40 and "买入" not in buy_advice:
            buy_advice = "建议买入" if score >= 40 else buy_advice
            if score < 40:
                continue
        if not buy_advice:
            buy_advice = "建议买入"

        # 去重
        cur = conn.execute(
            "SELECT id FROM trend_verify WHERE code=? AND signal_date=?",
            (code, signal_day),
        )
        if cur.fetchone():
            continue

        price_str = c.get("价格", "0")
        try:
            price = float(str(price_str).replace(",", ""))
        except (ValueError, TypeError):
            price = 0

        # 板块：优先用候选数据 → board_stocks → 按代码推断市场板块
        board = c.get("板块", "") or board_map.get(code, "")
        if not board:
            if code.startswith("60"):
                board = "沪市主板"
            elif code.startswith("00"):
                board = "深市主板"
            elif code.startswith("30"):
                board = "创业板"
            elif code.startswith("68"):
                board = "科创板"

        conn.execute(
            "INSERT INTO trend_verify "
            "(code,name,board,signal_date,signal_price,score,signal_type,strategy,vcp,breakout) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                code, c.get("名称", ""), board,
                signal_day, price, score,
                buy_advice, strategy,
                c.get("VCP", ""), c.get("突破", ""),
            ),
        )
        recorded += 1

    conn.commit()
    conn.close()
    return recorded


def record_routed_blocked_decisions(
    blocked_items: list[dict],
    *,
    raw_decisions: list[dict] | None = None,
    strategy: str = "CoordinatorRoute",
) -> int:
    """
    记录被协调者策略分流拦截的买入样本，用于后续复盘“没买”的机会成本。
    与普通选股信号不同，这里只记录 action=buy 的被拦截决策。
    """
    if not blocked_items:
        return 0

    conn = RepoCompatConnection()
    _ensure_schema(conn)
    today = date.today().isoformat()
    signal_day = _get_latest_market_date(conn) or today
    if signal_day > today:
        signal_day = today

    raw_map = {
        str(item.get("code", "") or ""): item
        for item in (raw_decisions or [])
        if str(item.get("code", "") or "")
    }
    board_map = {}
    try:
        for r in conn.execute("SELECT code, board FROM board_stocks"):
            if r[0] not in board_map:
                board_map[r[0]] = r[1]
    except Exception:
        pass

    recorded = 0
    for item in blocked_items:
        action = str(item.get("action", "") or "").lower()
        code = str(item.get("code", "") or "")
        if action != "buy" or not code:
            continue

        raw = raw_map.get(code, {})
        name = item.get("name", "") or raw.get("name", "")
        board = item.get("board", "") or raw.get("board", "") or board_map.get(code, "")
        reason = item.get("reason", "") or raw.get("reason", "")
        price = item.get("price", 0) or raw.get("price", 0)
        try:
            price = float(price or 0)
        except (TypeError, ValueError):
            price = 0
        if price <= 0:
            try:
                row = conn.execute(
                    "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1",
                    (code,),
                ).fetchone()
                price = float(row[0]) if row and row[0] else 0
            except Exception:
                price = 0

        exists = conn.execute(
            "SELECT id FROM trend_verify WHERE code=? AND signal_date=? AND strategy=? AND signal_type=?",
            (code, signal_day, strategy, "routed_blocked"),
        ).fetchone()
        if exists:
            continue

        conn.execute(
            "INSERT INTO trend_verify "
            "(code,name,board,signal_date,signal_price,score,signal_type,strategy,vcp,breakout,analysis,root_cause,failure_tags,improvement_hint,market_regime) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                code,
                name,
                board,
                signal_day,
                price,
                int(raw.get("score", raw.get("total", 0)) or 0),
                "routed_blocked",
                strategy,
                "",
                "",
                f"协调者分流拦截：{reason}" if reason else "协调者分流拦截，待后验验证",
                "待验证",
                _serialize_tags(["协调者分流", "机会成本复盘"]),
                "观察后续走势，评估分流策略是否过严或有效规避风险。",
                "未知",
            ),
        )
        recorded += 1

    conn.commit()
    conn.close()
    return recorded


def calibrate(max_age_days: int = 90) -> dict:
    """
    校准所有未完成校准的记录：
    读取信号日之后的实际日线数据，计算 3/5/10/20/60 日实际收益，
    判断信号是否正确（5日内上涨即为正确）。
    """
    # 校准所有 tracking 状态的记录（信号日至少在昨天或更早）
    cutoff = (date.today() - timedelta(days=1)).isoformat()
    conn = RepoCompatConnection()
    cur = conn.execute(
        "SELECT id, code, signal_date, signal_price FROM trend_verify "
        "WHERE status='tracking' AND signal_date<=? ORDER BY signal_date",
        (cutoff,),
    )
    rows = cur.fetchall()
    conn.close()

    # 先定向补齐待验证股票的最新日线，再重新打开连接做校准。
    _refresh_tracking_klines(rows)

    conn = RepoCompatConnection()
    _ensure_schema(conn)

    updated = 0
    for tid, code, sig_date, sig_price in rows:
        if sig_price <= 0:
            continue

        cur2 = conn.execute(
            "SELECT date, close FROM daily_kline WHERE code=? AND date>=? ORDER BY date",
            (code, sig_date),
        )
        klines = cur2.fetchall()
        if len(klines) < 2:
            continue

        updates = {}
        for days, p_col, pnl_col in [
            (1, "price_1d", "pnl_1d"),
            (2, "price_2d", "pnl_2d"),
            (3, "price_3d", "pnl_3d"),
            (5, "price_5d", "pnl_5d"),
            (10, "price_10d", "pnl_10d"),
            (20, "price_20d", "pnl_20d"),
            (60, "price_60d", "pnl_60d"),
        ]:
            if len(klines) > days:
                actual = klines[days][1]
                pnl = (actual / sig_price - 1) * 100
                updates[p_col] = round(actual, 2)
                updates[pnl_col] = round(pnl, 2)

        if not updates:
            continue

        # 判断是否正确（优先用 5 日，次选 3 日/2 日/1 日做临时判断）
        pnl5 = updates.get("pnl_5d")
        pnl3 = updates.get("pnl_3d")
        pnl2 = updates.get("pnl_2d")
        pnl1 = updates.get("pnl_1d")
        if pnl5 is not None:
            correct = 1 if pnl5 > 0 else 0
        elif pnl3 is not None:
            correct = 1 if pnl3 > 0 else 0
        elif pnl2 is not None:
            correct = 1 if pnl2 > 0 else 0
        elif pnl1 is not None:
            correct = 1 if pnl1 > 0 else 0
        else:
            correct = -1

        # 自动分析原因
        analysis = _auto_analyze(code, sig_date, sig_price, updates, conn)
        structured = _build_failure_attribution(code, sig_date, sig_price, updates, conn)

        set_parts = [f"{k}=?" for k in updates]
        set_parts.extend([
            "correct=?", "analysis=?", "root_cause=?", "failure_tags=?",
            "improvement_hint=?", "market_regime=?", "last_calibrated=?",
        ])
        vals = list(updates.values()) + [
            correct,
            analysis,
            structured.get("root_cause", ""),
            structured.get("failure_tags", ""),
            structured.get("improvement_hint", ""),
            structured.get("market_regime", ""),
            date.today().isoformat(),
        ]

        # 超过60天的标记完成
        days_since = (date.today() - date.fromisoformat(sig_date)).days
        if days_since >= 60:
            set_parts.append("status=?")
            vals.append("completed")

        vals.append(tid)
        conn.execute(
            f"UPDATE trend_verify SET {','.join(set_parts)} WHERE id=?", vals
        )
        updated += 1

    conn.commit()
    conn.close()
    return {"updated": updated, "total": len(rows)}


def _auto_analyze(code: str, sig_date: str, sig_price: float,
                  updates: dict, conn) -> str:
    """多维度自动分析信号正确/错误的原因。"""
    pnl1 = updates.get("pnl_1d")
    pnl2 = updates.get("pnl_2d")
    pnl3 = updates.get("pnl_3d")
    pnl5 = updates.get("pnl_5d")
    pnl10 = updates.get("pnl_10d")
    pnl20 = updates.get("pnl_20d")
    reasons = []

    # 读取信号前后走势
    cur_after = conn.execute(
        "SELECT date, close, high, low, volume FROM daily_kline "
        "WHERE code=? AND date>=? ORDER BY date LIMIT 30",
        (code, sig_date),
    )
    rows_after = cur_after.fetchall()

    cur_before = conn.execute(
        "SELECT close, high, low, volume FROM daily_kline "
        "WHERE code=? AND date<? ORDER BY date DESC LIMIT 60",
        (code, sig_date),
    )
    rows_before = cur_before.fetchall()

    if len(rows_after) < 2:
        return "数据不足，待后续校准"

    closes_a = [r[1] for r in rows_after]
    highs_a = [r[2] for r in rows_after]
    lows_a = [r[3] for r in rows_after]
    vols_a = [r[4] for r in rows_after]

    # ── 1. 信号有效性判断 ──
    best_pnl = pnl5 or pnl3 or pnl2 or pnl1 or 0
    if best_pnl > 5:
        reasons.append(f"✅ 信号有效，短期涨{best_pnl:.1f}%")
    elif best_pnl > 0:
        reasons.append(f"✅ 信号基本有效，小涨{best_pnl:.1f}%")
    elif best_pnl > -3:
        reasons.append(f"⚠ 信号中性，微跌{best_pnl:.1f}%")
    else:
        reasons.append(f"❌ 信号失效，跌{best_pnl:.1f}%")

    # ── 2. 极值分析 ──
    n_a = min(len(closes_a), 10)
    if n_a >= 3:
        max_gain = (max(highs_a[:n_a]) / sig_price - 1) * 100
        max_loss = (min(lows_a[:n_a]) / sig_price - 1) * 100
        if max_gain > 8:
            reasons.append(f"期间最高涨{max_gain:.1f}%")
        if max_loss < -8:
            reasons.append(f"期间最低跌{max_loss:.1f}%")
        if max_gain > 5 and best_pnl < 0:
            reasons.append("冲高回落，未及时止盈")
        if max_loss < -5 and best_pnl > 0:
            reasons.append("先跌后涨，抗住考验")

    # ── 3. 量能分析 ──
    if len(vols_a) >= 3:
        vol_sig = vols_a[0]
        vol_avg_after = float(np.mean(vols_a[1:min(6, len(vols_a))]))
        if vol_avg_after > 0:
            if vol_sig > vol_avg_after * 1.5:
                reasons.append("信号日放量确认")
            elif vol_sig < vol_avg_after * 0.5:
                reasons.append("信号日缩量，动能不足")
        # 后续量能变化
        if len(vols_a) >= 5:
            vol_trend = vols_a[1] < vols_a[2] < vols_a[3] if len(vols_a) >= 4 else False
            if vol_trend and best_pnl < 0:
                reasons.append("后续量能递增但价跌，抛压重")

    # ── 4. 均线支撑/阻力 ──
    if len(rows_before) >= 50:
        closes_b = [r[0] for r in reversed(rows_before)]
        ma5_b = float(np.mean(closes_b[-5:]))
        ma20_b = float(np.mean(closes_b[-20:]))
        ma50_b = float(np.mean(closes_b[-50:]))

        if sig_price > ma5_b > ma20_b > ma50_b:
            reasons.append("信号时多头排列完整")
        elif sig_price < ma20_b:
            reasons.append("信号时已破20日线，趋势偏弱")

        # 信号后是否跌破均线
        if len(closes_a) >= 5:
            cur_price = closes_a[-1]
            if cur_price < ma20_b and sig_price > ma20_b:
                reasons.append("后续跌破20日线")
            elif cur_price > ma50_b and sig_price < ma50_b:
                reasons.append("后续站上50日线")

    # ── 5. 形态分析 ──
    if len(closes_a) >= 5:
        # 连涨/连跌
        up_days = sum(1 for i in range(1, min(6, len(closes_a))) if closes_a[i] > closes_a[i-1])
        dn_days = min(5, len(closes_a)-1) - up_days
        if up_days >= 4:
            reasons.append(f"后续{up_days}日连涨")
        elif dn_days >= 4:
            reasons.append(f"后续{dn_days}日连跌")

        # 高开低走 vs 低开高走（第二天）
        if len(rows_after) >= 2:
            next_open_approx = highs_a[1] if closes_a[1] > closes_a[0] else lows_a[1]
            if closes_a[1] > closes_a[0] * 1.02:
                reasons.append("次日大涨确认")
            elif closes_a[1] < closes_a[0] * 0.98:
                reasons.append("次日大跌否定信号")

    # ── 6. 中长期趋势 ──
    if pnl10 is not None:
        if pnl10 > 10:
            reasons.append(f"10日趋势良好(+{pnl10:.1f}%)")
        elif pnl10 < -10:
            reasons.append(f"10日趋势恶化({pnl10:.1f}%)")
    if pnl20 is not None:
        if pnl20 > 15:
            reasons.append(f"中期趋势强劲(20日+{pnl20:.1f}%)")
        elif pnl20 < -10:
            reasons.append(f"中期趋势反转(20日{pnl20:.1f}%)")

    # ── 7. 大盘环境 ──
    try:
        idx_rows = conn.execute(
            "SELECT close FROM daily_kline WHERE code='000300' AND date>=? ORDER BY date LIMIT 10",
            (sig_date,),
        ).fetchall()
        if len(idx_rows) >= 3:
            idx_pnl = (idx_rows[-1][0] / idx_rows[0][0] - 1) * 100
            if idx_pnl < -2 and best_pnl < 0:
                reasons.append(f"大盘下跌{idx_pnl:.1f}%拖累")
            elif idx_pnl > 2 and best_pnl > 0:
                reasons.append(f"大盘上涨{idx_pnl:.1f}%助推")
            elif idx_pnl > 2 and best_pnl < 0:
                reasons.append(f"大盘涨{idx_pnl:.1f}%但个股逆市下跌，个股问题")
    except Exception:
        pass

    return "；".join(reasons) if reasons else "待分析"


def get_records(
    limit: int = 100,
    status: str = "",
    strategy: str = "",
    board: str = "",
    root_cause: str = "",
    market_regime: str = "",
    failed_only: bool = False,
    since_days: int = 0,
) -> list[dict]:
    """获取走势验证记录。"""
    conn = RepoCompatConnection()
    _ensure_schema(conn)

    where_parts, params = _build_common_filters(
        status=status,
        strategy=strategy,
        board=board,
        root_cause=root_cause,
        market_regime=market_regime,
        failed_only=failed_only,
        since_days=since_days,
    )
    where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    cur = conn.execute(
        f"SELECT id, code, name, board, signal_date, signal_price, score, signal_type, "
        f"strategy, vcp, breakout, "
        f"pnl_1d, pnl_2d, pnl_3d, pnl_5d, pnl_10d, pnl_20d, pnl_60d, "
        f"correct, analysis, root_cause, failure_tags, improvement_hint, market_regime, "
        f"last_calibrated, status "
        f"FROM trend_verify {where} ORDER BY signal_date DESC LIMIT ?",
        tuple(params + [limit]),
    )
    results = []
    for r in cur.fetchall():
        results.append({
            "id": r[0],
            "code": r[1], "name": r[2], "board": r[3],
            "signal_date": r[4], "signal_price": r[5], "score": r[6],
            "signal_type": r[7], "strategy": r[8],
            "vcp": r[9], "breakout": r[10],
            "pnl_1d": r[11], "pnl_2d": r[12],
            "pnl_3d": r[13], "pnl_5d": r[14], "pnl_10d": r[15],
            "pnl_20d": r[16], "pnl_60d": r[17],
            "correct": r[18], "analysis": r[19],
            "root_cause": r[20] or "",
            "failure_tags": _parse_tags(r[21]),
            "improvement_hint": r[22] or "",
            "market_regime": r[23] or "",
            "calibrated": r[24], "status": r[25],
        })
    conn.close()
    return results


def batch_analyze_failures(
    limit: int = 80,
    strategy: str = "",
    board: str = "",
    since_days: int = 365,
) -> dict:
    """批量归因最近失败信号，补齐结构化标签。"""
    conn = RepoCompatConnection()
    _ensure_schema(conn)
    where_parts, params = _build_common_filters(
        strategy=strategy,
        board=board,
        failed_only=True,
        since_days=since_days,
    )
    where = f"WHERE {' AND '.join(where_parts)}" if where_parts else "WHERE correct=0"
    cur = conn.execute(
        "SELECT id, code, signal_date, signal_price, pnl_1d, pnl_2d, pnl_3d, pnl_5d, pnl_10d, pnl_20d, "
        "correct, analysis "
        "FROM trend_verify "
        f"{where} "
        "ORDER BY signal_date DESC LIMIT ?",
        tuple(params + [limit]),
    )
    rows = cur.fetchall()

    updated = 0
    for row in rows:
        tid, code, sig_date, sig_price, pnl_1d, pnl_2d, pnl_3d, pnl_5d, pnl_10d, pnl_20d, correct, analysis = row
        updates = {
            "pnl_1d": pnl_1d,
            "pnl_2d": pnl_2d,
            "pnl_3d": pnl_3d,
            "pnl_5d": pnl_5d,
            "pnl_10d": pnl_10d,
            "pnl_20d": pnl_20d,
        }
        if not analysis or analysis in {"待分析", "-"}:
            analysis = _auto_analyze(code, sig_date, sig_price, updates, conn)
        structured = _build_failure_attribution(code, sig_date, sig_price, updates, conn)
        conn.execute(
            "UPDATE trend_verify SET analysis=?, root_cause=?, failure_tags=?, improvement_hint=?, market_regime=?, last_calibrated=? "
            "WHERE id=?",
            (
                analysis,
                structured.get("root_cause", ""),
                structured.get("failure_tags", ""),
                structured.get("improvement_hint", ""),
                structured.get("market_regime", ""),
                date.today().isoformat(),
                tid,
            ),
        )
        updated += 1

    conn.commit()
    conn.close()
    return {"updated": updated, "total": len(rows)}


def get_failure_summary(
    limit: int = 200,
    strategy: str = "",
    board: str = "",
    market_regime: str = "",
    since_days: int = 365,
) -> dict:
    """汇总失败信号的根因、标签和策略分布。"""
    conn = RepoCompatConnection()
    _ensure_schema(conn)
    where_parts, params = _build_common_filters(
        strategy=strategy,
        board=board,
        market_regime=market_regime,
        failed_only=True,
        since_days=since_days,
    )
    where = f"WHERE {' AND '.join(where_parts)}" if where_parts else "WHERE correct=0"
    cur = conn.execute(
        "SELECT strategy, root_cause, failure_tags, market_regime "
        f"FROM trend_verify {where} "
        "ORDER BY signal_date DESC LIMIT ?",
        tuple(params + [limit]),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return {"failed_total": 0, "top_root_causes": [], "top_tags": [], "by_strategy": [], "top_market_regimes": []}

    from collections import Counter

    root_counter = Counter()
    tag_counter = Counter()
    market_counter = Counter()
    strategy_totals = Counter()
    strategy_causes: dict[str, Counter] = {}

    for strategy, root_cause, failure_tags, market_regime in rows:
        strategy_name = strategy or "UNKNOWN"
        strategy_totals[strategy_name] += 1
        if root_cause:
            root_counter[root_cause] += 1
            strategy_causes.setdefault(strategy_name, Counter())[root_cause] += 1
        if market_regime:
            market_counter[market_regime] += 1
        for tag in _parse_tags(failure_tags):
            tag_counter[tag] += 1

    by_strategy = []
    for strategy_name, total in strategy_totals.most_common(5):
        top_cause = ""
        if strategy_causes.get(strategy_name):
            top_cause = strategy_causes[strategy_name].most_common(1)[0][0]
        by_strategy.append({
            "strategy": strategy_name,
            "failed": total,
            "top_cause": top_cause,
        })

    return {
        "failed_total": len(rows),
        "top_root_causes": [{"label": label, "count": count} for label, count in root_counter.most_common(5)],
        "top_tags": [{"label": label, "count": count} for label, count in tag_counter.most_common(6)],
        "top_market_regimes": [{"label": label, "count": count} for label, count in market_counter.most_common(3)],
        "by_strategy": by_strategy,
    }


def update_record_analysis(record_id: int, analysis: str) -> bool:
    """保存单条记录的 AI 深度分析结果。"""
    if not record_id or not analysis:
        return False
    conn = RepoCompatConnection()
    _ensure_schema(conn)
    conn.execute(
        "UPDATE trend_verify SET analysis=?, last_calibrated=? WHERE id=?",
        (analysis, date.today().isoformat(), record_id),
    )
    conn.commit()
    conn.close()
    return True


def get_accuracy_stats() -> dict:
    """统计选股信号的历史准确率。"""
    conn = RepoCompatConnection()
    cur = conn.execute(
        "SELECT correct, pnl_1d, pnl_2d, pnl_3d, pnl_5d, pnl_10d, pnl_20d, signal_type "
        "FROM trend_verify WHERE correct>=0"
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return {"total": 0}

    total = len(rows)
    correct = sum(1 for r in rows if r[0] == 1)
    pnl1_list = [r[1] for r in rows if r[1] is not None]
    pnl2_list = [r[2] for r in rows if r[2] is not None]
    pnl3_list = [r[3] for r in rows if r[3] is not None]
    pnl5_list = [r[4] for r in rows if r[4] is not None]
    pnl10_list = [r[5] for r in rows if r[5] is not None]
    pnl20_list = [r[6] for r in rows if r[6] is not None]

    by_type = {}
    for r in rows:
        st = r[7] or "unknown"
        by_type.setdefault(st, {"total": 0, "correct": 0, "pnl5": []})
        by_type[st]["total"] += 1
        if r[0] == 1:
            by_type[st]["correct"] += 1
        if r[4] is not None:
            by_type[st]["pnl5"].append(r[4])

    type_stats = {}
    for st, d in by_type.items():
        type_stats[st] = {
            "total": d["total"],
            "accuracy": round(d["correct"] / d["total"] * 100, 1) if d["total"] > 0 else 0,
            "avg_pnl5": round(np.mean(d["pnl5"]), 2) if d["pnl5"] else 0,
        }

    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total * 100, 1),
        "avg_pnl_1d": round(np.mean(pnl1_list), 2) if pnl1_list else 0,
        "avg_pnl_2d": round(np.mean(pnl2_list), 2) if pnl2_list else 0,
        "avg_pnl_3d": round(np.mean(pnl3_list), 2) if pnl3_list else 0,
        "avg_pnl_5d": round(np.mean(pnl5_list), 2) if pnl5_list else 0,
        "avg_pnl_10d": round(np.mean(pnl10_list), 2) if pnl10_list else 0,
        "avg_pnl_20d": round(np.mean(pnl20_list), 2) if pnl20_list else 0,
        "by_type": type_stats,
    }
