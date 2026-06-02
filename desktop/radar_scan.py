"""Multi-strategy radar scan (UI / optional daemon). No single main strategy."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from desktop.data_access import get_repo
from desktop.strategy_engine import build_context, score_candidate

_log = logging.getLogger("radar_scan")

DEFAULT_RS_MIN = 0


def run_multi_strategy_radar_scan(
    strategy_ids: list[str],
    *,
    sample: int = 500,
    rs_min: int = DEFAULT_RS_MIN,
) -> dict[str, Any]:
    """Run one or more strategy profiles and aggregate like the screening UI."""
    strategy_ids = [sid for sid in strategy_ids if sid]
    if not strategy_ids:
        return {
            "candidates": [],
            "strategy_ids": [],
            "multi_strategy": False,
            "overlap_count": 0,
            "per_strategy": {},
        }

    repo = get_repo()
    codes = [
        r[0]
        for r in repo.fetchall(
            "SELECT code, COUNT(*) as cnt FROM daily_kline "
            "GROUP BY code HAVING cnt >= 50 ORDER BY cnt DESC LIMIT ?",
            (sample,),
        )
    ]

    names: dict[str, str] = {}
    try:
        for r in repo.fetchall("SELECT code, name FROM stock_list", ()):
            names[r[0]] = r[1]
    except Exception:
        pass

    board_map: dict[str, str] = {}
    try:
        for r in repo.fetchall("SELECT code, board FROM board_stocks", ()):
            if r[0] not in board_map:
                board_map[r[0]] = r[1]
    except Exception:
        pass

    aggregated: dict[str, dict] = {}
    per_strategy_rows: dict[str, list[dict]] = {}

    for code in codes:
        rows = repo.fetchall(
            "SELECT close, high, low, volume FROM daily_kline "
            "WHERE code=? ORDER BY date DESC LIMIT 260",
            (code,),
        )
        if len(rows) < 50:
            continue
        rows = rows[::-1]
        closes = np.array([r[0] for r in rows])
        highs = np.array([r[1] for r in rows])
        lows = np.array([r[2] for r in rows])
        vols = np.array([r[3] for r in rows])
        price = float(closes[-1])
        if price <= 0:
            continue

        ctx = build_context(code, closes, highs, lows, vols)
        for strategy_id in strategy_ids:
            scored = score_candidate(strategy_id, ctx)
            score = int(scored["score"])
            rs = int(scored["rs"])
            if rs < rs_min:
                continue

            row = {
                "代码": code,
                "名称": names.get(code, ""),
                "板块": board_map.get(code, ""),
                "策略": scored["strategy"],
                "价格": f"{price:.2f}",
                "RS": str(rs),
                "评分": str(score),
                "VCP": "✓" if scored["vcp"] else "",
                "突破": "✓" if scored["breakout"] else "",
                "收缩": f"{scored['contraction']:.2f}" if scored["contraction"] else "",
                "量比": f"{scored['vol_ratio']:.1f}",
                "离高点%": f"{scored['dist_high']:+.1f}%",
                "建议买入": scored["buy_advice"],
                "建议操作": scored["action_advice"],
            }
            hit_label = str(scored["strategy"] or strategy_id)
            row["命中数"] = 1
            row["命中策略"] = hit_label
            row["共振"] = ""
            per_strategy_rows.setdefault(hit_label, []).append(dict(row))

            current = aggregated.get(code)
            breakout = bool(scored["breakout"])
            if current is None:
                row["_score_num"] = score
                row["_rs_num"] = rs
                row["_breakout_num"] = 1 if breakout else 0
                row["_strategy_hits"] = [hit_label]
                aggregated[code] = row
                continue

            if hit_label not in current["_strategy_hits"]:
                current["_strategy_hits"].append(hit_label)

            replace = (
                score > current["_score_num"]
                or (score == current["_score_num"] and (1 if breakout else 0) > current["_breakout_num"])
                or (score == current["_score_num"] and rs > current["_rs_num"])
            )
            current["_breakout_num"] = max(current["_breakout_num"], 1 if breakout else 0)
            current["_score_num"] = max(current["_score_num"], score)
            current["_rs_num"] = max(current["_rs_num"], rs)
            if replace:
                keep_hits = list(current["_strategy_hits"])
                current.update(row)
                current["_strategy_hits"] = keep_hits
                current["_score_num"] = max(current["_score_num"], score)
                current["_rs_num"] = max(current["_rs_num"], rs)
                current["_breakout_num"] = max(current["_breakout_num"], 1 if breakout else 0)

    candidates = list(aggregated.values())
    overlap_codes: set[str] = set()
    for row in candidates:
        hits = row.pop("_strategy_hits", [])
        score_num = row.pop("_score_num", 0)
        rs_num = row.pop("_rs_num", 0)
        breakout_num = row.pop("_breakout_num", 0)
        row["命中数"] = len(hits) if hits else 1
        row["命中策略"] = " / ".join(hits) if hits else row.get("策略", "")
        row["共振"] = "🔥 共振" if row["命中数"] > 1 else ""
        if row["命中数"] > 1:
            overlap_codes.add(str(row.get("代码", "")))
        row["_sort_key"] = (row["命中数"], breakout_num, score_num, rs_num)

    candidates.sort(key=lambda x: x.get("_sort_key", (0, 0, 0, 0)), reverse=True)
    for row in candidates:
        row.pop("_sort_key", None)

    for label, rows in per_strategy_rows.items():
        rows.sort(
            key=lambda x: (
                1 if str(x.get("代码", "")) in overlap_codes else 0,
                int(x.get("评分", "0") or 0),
                int(x.get("RS", "0") or 0),
            ),
            reverse=True,
        )

    overlap_count = sum(1 for row in candidates if int(row.get("命中数", 1) or 1) > 1)
    meta_strategy_id = strategy_ids[0] if len(strategy_ids) == 1 else "multi"

    return {
        "candidates": candidates[:50],
        "strategy_ids": strategy_ids,
        "multi_strategy": len(strategy_ids) > 1,
        "overlap_count": overlap_count,
        "per_strategy": per_strategy_rows,
        "strategy_id": meta_strategy_id,
    }


def candidates_from_scan_rows(rows: list[dict]) -> list[dict]:
    """Convert last_scan_results rows to OpenClaw candidate dicts."""
    out: list[dict] = []
    for row in rows or []:
        code = str(row.get("代码") or row.get("code") or "")
        if not code:
            continue
        try:
            score = int(row.get("评分", row.get("score", 0)) or 0)
        except (TypeError, ValueError):
            score = 0
        try:
            price = float(row.get("价格", row.get("price", 0)) or 0)
        except (TypeError, ValueError):
            price = 0.0
        out.append(
            {
                "code": code,
                "name": row.get("名称") or row.get("name") or code,
                "score": score,
                "price": round(price, 2),
                "board": row.get("板块") or row.get("board") or "",
                "strategy": row.get("策略") or row.get("strategy") or "",
            }
        )
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def candidates_from_arena_snapshot(*, per_strategy_top: int = 3) -> list[dict]:
    """Merge top picks from each arena strategy snapshot (no single winner)."""
    from desktop.arena.participants import list_arena_strategy_ids
    from desktop.arena.snapshot import get_shared_snapshot, get_strategy_candidates

    snapshot = get_shared_snapshot()
    if not snapshot:
        return []

    merged: dict[str, dict] = {}
    for sid in list_arena_strategy_ids():
        for row in get_strategy_candidates(snapshot, sid)[:per_strategy_top]:
            code = str(row.get("代码") or "")
            if not code:
                continue
            try:
                score = int(float(row.get("评分", 0) or 0))
            except (TypeError, ValueError):
                score = 0
            existing = merged.get(code)
            if existing is None or score > existing["score"]:
                merged[code] = candidates_from_scan_rows([row])[0]
    out = list(merged.values())
    out.sort(key=lambda x: x["score"], reverse=True)
    return out
