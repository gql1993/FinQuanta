"""
自动卖出引擎
5 种卖出规则 + ATR 跟踪止损更新

完全自主仓、AI推荐仓、自定义仓、量子仓：交易时间内自动执行卖出

规则优先级：
  1. 止损触发（现价 ≤ 止损线）→ 立即卖出
  2. ATR 跟踪止损（每日上移止损线，现价跌破新止损）→ 卖出
  3. 时间止损（持有 > 25 天且亏损 > 2%）→ 卖出
  4. 止盈保护（盈利 ≥ 20% 且当日跌 ≥ 3%）→ 卖出半仓
  5. VCP 失败（突破后 3 天内跌回买入价以下）→ 卖出
"""
import json
import logging
import numpy as np
from datetime import datetime, date, timedelta

from desktop.data_access import get_repo

_log = logging.getLogger("auto_sell")

# "manual" is the legacy storage mode for the AI recommendation portfolio.
# Keep it in the sell-risk loop so older AI positions are not orphaned.
_SELL_MONITORED_MODES = ("full_auto", "auto", "manual", "custom", "quantum")


def _get_price(code: str, repo) -> float:
    """获取最新价格（实时→日K兜底）。"""
    try:
        from desktop.realtime_data import get_realtime_quotes
        q = get_realtime_quotes([code], force=False)
        px = q.get(code, {}).get("price", 0)
        if px and px > 0:
            return float(px)
    except Exception:
        pass
    row = repo.fetchone(
        "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1",
        (code,),
    )
    return float(row[0]) if row else 0.0


def _get_prev_close(code: str, repo) -> float:
    """获取昨日收盘价。"""
    rows = repo.fetchall(
        "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 2",
        (code,),
    )
    return float(rows[1][0]) if len(rows) >= 2 else 0.0


def _calc_atr(code: str, repo, period: int = 20) -> float:
    """计算 ATR。"""
    rows = repo.fetchall(
        "SELECT high, low, close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT ?",
        (code, period + 1),
    )
    if len(rows) < period + 1:
        return 0.0
    rows = list(reversed(rows))
    tr_list = []
    for i in range(1, len(rows)):
        h, l, prev_c = rows[i][0], rows[i][1], rows[i-1][2]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_list.append(tr)
    return float(np.mean(tr_list[-period:])) if tr_list else 0.0


def _sell_monitored_modes() -> tuple[str, ...]:
    legacy = ("full_auto", "auto", "manual", "custom", "quantum")
    try:
        from desktop.arena.participants import arena_modes

        return legacy + arena_modes()
    except Exception:
        return legacy


def check_sell_signals(mode: str = "full_auto") -> list[dict]:
    """
    检查指定仓位的所有持仓，返回卖出信号列表。
    每个信号: {"code", "name", "rule", "reason", "action", "shares_pct"}
    action: "sell_all" | "sell_half"
    """
    from desktop.ai_portfolio import get_state

    state = get_state(mode)
    positions = state.get("positions", [])
    if not positions:
        return []

    repo = get_repo()
    signals = []
    today = date.today()

    for p in positions:
        code = p.get("code", "")
        name = p.get("name", "")
        entry_price = p.get("entry_price", 0)
        stop_loss = p.get("stop_loss", 0)
        shares = p.get("shares", 0)
        entry_date = p.get("entry_date", "")

        if not code or entry_price <= 0:
            continue

        price = _get_price(code, repo)
        if price <= 0:
            continue

        prev_close = _get_prev_close(code, repo)
        pnl_pct = (price - entry_price) / entry_price * 100
        day_pct = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0

        # 持有天数
        try:
            hold_days = (today - date.fromisoformat(entry_date)).days
        except Exception:
            hold_days = 0

        # ── 规则1: 止损触发 ──
        if stop_loss > 0 and price <= stop_loss:
            signals.append({
                "code": code, "name": name, "mode": mode,
                "rule": "止损触发",
                "reason": f"现价{price:.2f} ≤ 止损线{stop_loss:.2f}",
                "action": "sell_all", "shares_pct": 100,
                "price": price, "pnl_pct": pnl_pct,
            })
            continue

        # ── 规则2: ATR 跟踪止损 ──
        atr = _calc_atr(code, repo)
        if atr > 0 and hold_days >= 3:
            # 计算最高价以来的 ATR 止损线
            high_since = repo.fetchone(
                "SELECT MAX(high) FROM daily_kline WHERE code=? AND date>=?",
                (code, entry_date),
            )
            highest = float(high_since[0]) if high_since and high_since[0] else entry_price
            atr_stop = highest - 2 * atr
            atr_stop = max(atr_stop, entry_price * 0.85)

            if price <= atr_stop and atr_stop > stop_loss:
                signals.append({
                    "code": code, "name": name, "mode": mode,
                    "rule": "ATR跟踪止损",
                    "reason": f"现价{price:.2f} ≤ ATR止损{atr_stop:.2f}(最高{highest:.2f}-2×ATR{atr:.2f})",
                    "action": "sell_all", "shares_pct": 100,
                    "price": price, "pnl_pct": pnl_pct,
                })
                continue

        # ── 规则3: 时间止损 ──
        if hold_days > 25 and pnl_pct < -2:
            signals.append({
                "code": code, "name": name, "mode": mode,
                "rule": "时间止损",
                "reason": f"持有{hold_days}天且亏损{pnl_pct:.1f}%",
                "action": "sell_all", "shares_pct": 100,
                "price": price, "pnl_pct": pnl_pct,
            })
            continue

        # ── 规则4: 止盈保护 ──
        if pnl_pct >= 20 and day_pct <= -3:
            signals.append({
                "code": code, "name": name, "mode": mode,
                "rule": "止盈保护",
                "reason": f"盈利{pnl_pct:.1f}%但当日跌{day_pct:.1f}%，卖出半仓保护利润",
                "action": "sell_half", "shares_pct": 50,
                "price": price, "pnl_pct": pnl_pct,
            })
            continue

        # ── 规则5: VCP 失败（给突破后更多波动空间） ──
        if hold_days <= 3 and pnl_pct < -7:
            signals.append({
                "code": code, "name": name, "mode": mode,
                "rule": "VCP失败",
                "reason": f"买入{hold_days}天即跌{pnl_pct:.1f}%，突破失败",
                "action": "sell_all", "shares_pct": 100,
                "price": price, "pnl_pct": pnl_pct,
            })
            continue

    return signals


def update_atr_stops() -> list[str]:
    """
    每日更新所有持仓的 ATR 跟踪止损线（只上移不下移）。
    """
    repo = get_repo()
    updates = []

    rows = repo.fetchall(
        "SELECT id, mode, code, name, entry_price, entry_date, stop_loss "
        "FROM ai_positions WHERE status='open'",
        (),
    )

    for pos_id, mode, code, name, entry_price, entry_date, old_stop in rows:
        atr = _calc_atr(code, repo)
        if atr <= 0:
            continue

        high_r = repo.fetchone(
            "SELECT MAX(high) FROM daily_kline WHERE code=? AND date>=?",
            (code, entry_date or "2020-01-01"),
        )
        highest = float(high_r[0]) if high_r and high_r[0] else entry_price

        new_stop = round(highest - 2 * atr, 2)
        new_stop = max(new_stop, entry_price * 0.85)

        if new_stop > (old_stop or 0):
            repo.execute(
                "UPDATE ai_positions SET stop_loss=? WHERE id=?",
                (new_stop, pos_id),
            )
            updates.append(
                f"{mode}/{code}{name}: 止损 {old_stop:.2f}→{new_stop:.2f} "
                f"(最高{highest:.2f} ATR{atr:.2f})"
            )

    return updates


def check_add_position_signals(mode: str = "full_auto") -> list[dict]:
    """
    检查加仓信号：
    - 盈利 ≥5% 且趋势持续（价格 > MA5 > MA20）
    - 当前仓位 < 满仓（允许加仓）
    - 分 3 档：首次买入1/3 → 加仓到2/3 → 满仓
    """
    from desktop.ai_portfolio import get_state

    state = get_state(mode)
    positions = state.get("positions", [])
    cash = state.get("cash", 0)
    if not positions or cash < 10000:
        return []

    repo = get_repo()
    signals = []

    for p in positions:
        code = p.get("code", "")
        entry_price = p.get("entry_price", 0)
        shares = p.get("shares", 0)
        if not code or entry_price <= 0:
            continue

        price = _get_price(code, repo)
        if price <= 0:
            continue

        pnl_pct = (price - entry_price) / entry_price * 100

        # 条件1：盈利 ≥5%
        if pnl_pct < 5:
            continue

        # 条件2：趋势持续（价格 > MA5 > MA20）
        rows = repo.fetchall(
            "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 20",
            (code,),
        )
        if len(rows) < 20:
            continue
        closes = [r[0] for r in reversed(rows)]
        ma5 = float(np.mean(closes[-5:]))
        ma20 = float(np.mean(closes[-20:]))
        if not (price > ma5 > ma20):
            continue

        # 条件3：计算加仓量（目标持仓 = 初始买入的 2 倍）
        target_shares = shares * 2
        add_shares = target_shares - shares
        add_shares = int(add_shares / 100) * 100
        cost = add_shares * price * 1.0003

        if add_shares >= 100 and cost <= cash * 0.5:
            signals.append({
                "code": code, "name": p.get("name", ""), "mode": mode,
                "current_shares": shares, "add_shares": add_shares,
                "price": price, "pnl_pct": pnl_pct,
                "reason": f"盈利{pnl_pct:.1f}%且趋势持续(价格>MA5>MA20)，加仓{add_shares}股",
            })

    return signals


def execute_auto_sell() -> dict:
    """
    执行自动卖出：
    - full_auto/auto/manual/custom/quantum: 交易时间内直接卖出
    - 非交易时间: 生成建议并推送，不执行
    返回: {"executed": [...], "suggested": [...]}
    """
    from desktop.ai_portfolio import sell, check_trading_time

    result = {"executed": [], "suggested": [], "atr_updates": [], "add_positions": []}

    # 1. 更新 ATR 止损线
    atr_updates = update_atr_stops()
    result["atr_updates"] = atr_updates
    if atr_updates:
        _log.info(f"ATR stops updated: {len(atr_updates)}")

    # 2. 检查加仓信号（完全自主仓）
    try:
        add_signals = check_add_position_signals("full_auto")
        reject = check_trading_time()
        if add_signals and not reject:
            from desktop.ai_portfolio import buy
            for sig in add_signals:
                msg = buy(
                    "full_auto", sig["code"], sig["name"],
                    sig["price"], sig["add_shares"],
                    round(sig["price"] * 0.92, 2),
                    f"[自动加仓] {sig['reason']}",
                )
                result["add_positions"].append(msg)
                _log.info(f"add position: {msg}")
    except Exception as e:
        _log.warning(f"add position check error: {e}")

    # 3. 检查各仓卖出信号
    all_signals = []
    for mode in _sell_monitored_modes():
        signals = check_sell_signals(mode)
        all_signals.extend(signals)

    if not all_signals:
        _log.info("no sell signals")
        return result

    _log.info(f"found {len(all_signals)} sell signals")

    # 3. 执行/推送
    reject = check_trading_time()

    for sig in all_signals:
        mode = sig["mode"]
        code = sig["code"]
        name = sig["name"]
        price = sig["price"]
        action = sig["action"]
        reason = f"{sig['rule']}: {sig['reason']}"

        if mode in _SELL_MONITORED_MODES and not reject:
            # 自主仓与策略仓：卖出信号用于降风险，可自动执行。
            if action == "sell_half":
                # 半仓卖出：先查当前股数
                from desktop.ai_portfolio import get_state
                state = get_state(mode)
                pos = next((p for p in state["positions"] if p["code"] == code), None)
                if pos:
                    half = int(pos["shares"] / 2 / 100) * 100
                    if half >= 100:
                        msg = sell(mode, code, price, f"[自动] {reason} (半仓{half}股)")
                        result["executed"].append(msg)
                    else:
                        msg = sell(mode, code, price, f"[自动] {reason}")
                        result["executed"].append(msg)
            else:
                msg = sell(mode, code, price, f"[自动] {reason}")
                result["executed"].append(msg)
        else:
            # 其他仓 / 非交易时间：只推送建议
            _mode_labels = {
                "full_auto": "完全自主", "auto": "AI推荐",
                "manual": "AI推荐", "custom": "自定义", "quantum": "量子",
            }
            result["suggested"].append(
                f"[{_mode_labels.get(mode, mode)}] {code}{name} 建议{action}: {reason}"
            )

    # 4. 推送卖出信号
    if result["executed"] or result["suggested"]:
        try:
            from signal_push import push_signal
            lines = ["🔔 自动卖出引擎报告", ""]
            if result["executed"]:
                lines.append(f"1. ✅ 已执行卖出（{len(result['executed'])}条）")
                for i, msg in enumerate(result["executed"], 1):
                    lines.append(f"　　({i}) {msg}")
                lines.append("")
            if result["suggested"]:
                lines.append(f"{'2' if result['executed'] else '1'}. 📋 卖出建议（{len(result['suggested'])}条）")
                for i, msg in enumerate(result["suggested"], 1):
                    lines.append(f"　　({i}) {msg}")
            push_signal("🔔 卖出信号", "\n".join(lines))
        except Exception as e:
            _log.warning(f"push sell signals error: {e}")

    return result
