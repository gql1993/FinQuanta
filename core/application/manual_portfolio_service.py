"""Manual portfolio read/write for API / Web (mirrors desktop main_window logic)."""

from __future__ import annotations

import json
from datetime import date, datetime

from desktop.data_access import get_kv_json, set_kv_json
from core.application.ops_service import log_system_event


def _default_portfolio() -> dict:
    return {
        "positions": [],
        "cash": 1_000_000,
        "initial_capital": 1_000_000,
        "history": [],
    }


def load_manual_portfolio() -> dict:
    pf = get_kv_json("manual_portfolio", None)
    if isinstance(pf, dict) and pf:
        pf.setdefault("positions", [])
        pf.setdefault("cash", 1_000_000)
        pf.setdefault("initial_capital", 1_000_000)
        pf.setdefault("history", [])
        return pf
    return _default_portfolio()


def save_manual_portfolio(pf: dict) -> None:
    set_kv_json("manual_portfolio", pf)
    try:
        from desktop.snapshot_service import save_system_snapshot

        save_system_snapshot()
    except Exception:
        pass


def _resolve_name(code: str) -> str:
    from api_server.storage import repo

    row = repo.fetchone("SELECT name FROM stock_list WHERE code=?", (code,))
    return row[0] if row else code


def _resolve_price(code: str, price: float) -> float:
    if price > 0:
        return price
    try:
        from desktop.ai_trader import _get_real_price

        return float(_get_real_price(code) or 0)
    except Exception:
        return 0.0


def get_manual_portfolio_detail() -> dict:
    pf = load_manual_portfolio()
    prices: dict[str, float] = {}
    try:
        from desktop.ai_trader import _get_real_price

        for pos in pf.get("positions", []):
            code = pos.get("code", "")
            if code:
                prices[code] = float(_get_real_price(code) or pos.get("entry_price", 0) or 0)
    except Exception:
        pass

    position_value = 0.0
    unrealized = 0.0
    enriched = []
    for pos in pf.get("positions", []):
        code = pos.get("code", "")
        entry = float(pos.get("entry_price", 0) or 0)
        shares = int(pos.get("shares", 0) or 0)
        px = float(prices.get(code, entry) or entry)
        mv = px * shares
        cost = entry * shares
        pnl = mv - cost
        pnl_pct = (px / entry - 1) * 100 if entry > 0 else 0
        position_value += mv
        unrealized += pnl
        enriched.append(
            {
                **pos,
                "current_price": round(px, 2),
                "market_value": round(mv, 2),
                "unrealized_pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
            }
        )

    cash = float(pf.get("cash", 0) or 0)
    initial = float(pf.get("initial_capital", 1_000_000) or 1_000_000)
    equity = cash + position_value
    return_pct = (equity - initial) / initial * 100 if initial > 0 else 0

    return {
        "cash": round(cash, 2),
        "initial_capital": initial,
        "equity": round(equity, 2),
        "position_value": round(position_value, 2),
        "unrealized_pnl": round(unrealized, 2),
        "return_pct": round(return_pct, 2),
        "positions": enriched,
        "history": (pf.get("history") or [])[-50:],
    }


def manual_buy(
    code: str,
    *,
    price: float = 0,
    shares: int = 100,
    stop_loss_pct: float = 8.0,
) -> dict:
    code = str(code or "").strip()
    if len(code) != 6 or not code.isdigit():
        return {"ok": False, "message": "请输入有效的6位股票代码"}

    price = _resolve_price(code, price)
    if price <= 0:
        return {"ok": False, "message": "无法获取价格，请手动输入"}

    shares = max(100, int(shares // 100) * 100)
    cost = price * shares * 1.0003
    pf = load_manual_portfolio()
    if cost > pf["cash"]:
        max_shares = int(pf["cash"] / (price * 1.0003) / 100) * 100
        return {
            "ok": False,
            "message": f"资金不足: 需要 ¥{cost:,.0f}，可用 ¥{pf['cash']:,.0f}（最多 {max_shares} 股）",
        }

    name = _resolve_name(code)
    today = date.today().isoformat()
    pf["positions"].append(
        {
            "code": code,
            "name": name,
            "entry_price": round(price, 2),
            "shares": shares,
            "entry_date": today,
            "stop_loss": round(price * (1 - stop_loss_pct / 100), 2),
        }
    )
    pf["cash"] = round(float(pf["cash"]) - cost, 2)
    pf.setdefault("history", []).append(
        {
            "time": datetime.now().isoformat(),
            "action": "BUY",
            "code": code,
            "name": name,
            "price": price,
            "shares": shares,
        }
    )
    save_manual_portfolio(pf)
    log_system_event(
        "api",
        "manual_portfolio",
        "手动仓买入",
        detail=f"code={code}, price={price:.2f}, shares={shares}",
    )
    return {"ok": True, "message": f"买入 {code} {name} {shares}股 @ ¥{price:.2f}"}


def manual_sell(
    code: str,
    *,
    price: float = 0,
    shares: int = 0,
) -> dict:
    code = str(code or "").strip()
    if len(code) != 6 or not code.isdigit():
        return {"ok": False, "message": "请输入有效的股票代码"}

    pf = load_manual_portfolio()
    pos_idx = -1
    pos = None
    for i, p in enumerate(pf.get("positions", [])):
        if p.get("code") == code:
            pos = p
            pos_idx = i
            break
    if pos is None:
        return {"ok": False, "message": f"未持有 {code}"}

    sell_price = _resolve_price(code, price)
    if sell_price <= 0:
        return {"ok": False, "message": "无法获取价格，请手动输入"}

    sell_shares = int(shares or 0) or int(pos.get("shares", 0) or 0)
    if sell_shares > int(pos.get("shares", 0) or 0):
        return {"ok": False, "message": f"持有 {pos['shares']} 股，不能卖 {sell_shares}"}

    revenue = sell_price * sell_shares * (1 - 0.0013)
    pnl = revenue - float(pos.get("entry_price", 0) or 0) * sell_shares
    pf["cash"] = round(float(pf["cash"]) + revenue, 2)
    if sell_shares >= int(pos.get("shares", 0) or 0):
        pf["positions"].pop(pos_idx)
    else:
        pf["positions"][pos_idx]["shares"] = int(pos["shares"]) - sell_shares

    pf.setdefault("history", []).append(
        {
            "time": datetime.now().isoformat(),
            "action": "SELL",
            "code": code,
            "name": pos.get("name", ""),
            "price": sell_price,
            "shares": sell_shares,
            "pnl": round(pnl, 2),
        }
    )
    save_manual_portfolio(pf)
    log_system_event(
        "api",
        "manual_portfolio",
        "手动仓卖出",
        detail=f"code={code}, price={sell_price:.2f}, shares={sell_shares}, pnl={pnl:.2f}",
    )
    return {
        "ok": True,
        "message": f"卖出 {code} {sell_shares}股 @ ¥{sell_price:.2f}，盈亏 ¥{pnl:+,.2f}",
        "pnl": round(pnl, 2),
    }
