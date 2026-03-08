"""
事件驱动短期选股策略
事件录入 → 关键词匹配板块 → 历史回测验证 → 短期推荐
"""
import os
import json
import sqlite3
import re
import numpy as np
import urllib.request
from datetime import datetime, date, timedelta

DB_PATH = os.path.join("data_cache", "quant.db")

# 关键词 → 板块映射（可扩展）
KEYWORD_BOARD_MAP = {
    "特高压": ["充电桩", "风电", "光伏", "储能"],
    "人工智能": ["人工智能", "AI应用", "算力"],
    "AI": ["人工智能", "AI应用", "算力"],
    "芯片": ["芯片", "半导体", "存储芯片"],
    "半导体": ["半导体", "芯片", "光刻机"],
    "量子": ["量子科技"],
    "机器人": ["机器人", "自动驾驶"],
    "军工": ["军工", "商业航天"],
    "航天": ["商业航天", "军工"],
    "无人机": ["无人机", "低空经济"],
    "低空": ["低空经济", "无人机"],
    "新能源": ["新能源汽车", "锂电池", "充电桩"],
    "锂电": ["锂电池", "储能"],
    "光伏": ["光伏", "储能"],
    "储能": ["储能", "光伏"],
    "充电桩": ["充电桩", "新能源汽车"],
    "风电": ["风电", "储能"],
    "氢能": ["氢能源"],
    "医药": ["创新药", "医疗器械", "CRO"],
    "创新药": ["创新药", "CRO"],
    "中药": ["中药"],
    "5G": ["5G", "物联网"],
    "云计算": ["云计算", "大数据"],
    "大数据": ["大数据", "云计算", "数据要素"],
    "数据要素": ["数据要素", "大数据"],
    "自动驾驶": ["自动驾驶", "新能源汽车"],
    "脑机": ["脑机接口"],
    "工业母机": ["工业母机"],
    "政策": [],
    "利好": [],
    "利空": [],
}


def match_boards(text: str) -> list[str]:
    """从事件文本中提取匹配的板块。"""
    matched = set()
    for keyword, boards in KEYWORD_BOARD_MAP.items():
        if keyword in text:
            matched.update(boards)
    return sorted(matched) if matched else ["人工智能"]


def save_event(event_text: str, event_date: str = "", source: str = "手动输入"):
    """保存事件到数据库。"""
    if not event_date:
        event_date = date.today().isoformat()
    boards = match_boards(event_text)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT,
            event_text TEXT,
            source TEXT,
            matched_boards TEXT,
            created_at TEXT
        )
    """)
    conn.execute(
        "INSERT INTO events (event_date, event_text, source, matched_boards, created_at) VALUES (?,?,?,?,?)",
        (event_date, event_text, source, json.dumps(boards, ensure_ascii=False), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return boards


def get_events(limit: int = 50) -> list[dict]:
    """获取历史事件。"""
    conn = sqlite3.connect(DB_PATH, timeout=5)
    try:
        cur = conn.execute(
            "SELECT id, event_date, event_text, source, matched_boards, created_at FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        events = []
        for r in cur.fetchall():
            events.append({
                "id": r[0], "date": r[1], "text": r[2], "source": r[3],
                "boards": json.loads(r[4]) if r[4] else [], "created": r[5],
            })
        return events
    except Exception:
        return []
    finally:
        conn.close()


def backtest_event(boards: list[str], lookback_days: int = 5) -> list[dict]:
    """
    回测事件关联板块的历史表现。
    找到板块成分股，计算事件后 3/5/10 日涨跌幅。
    """
    conn = sqlite3.connect(DB_PATH, timeout=5)
    results = []

    for board in boards:
        cur = conn.execute("SELECT code FROM board_stocks WHERE board=?", (board,))
        codes = [r[0] for r in cur.fetchall()]
        if not codes:
            continue

        board_stats = {"board": board, "stocks": len(codes), "avg_3d": 0, "avg_5d": 0, "avg_10d": 0, "top_stocks": []}
        pcts_3d, pcts_5d, pcts_10d = [], [], []
        stock_details = []

        for code in codes[:30]:
            cur2 = conn.execute(
                "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 15",
                (code,),
            )
            rows = cur2.fetchall()
            if len(rows) < 11:
                continue
            rows = rows[::-1]
            closes = [r[0] for r in rows]
            base = closes[-11] if len(closes) >= 11 else closes[0]
            if base <= 0:
                continue

            cur_price = closes[-1]
            p3 = (closes[-8] - base) / base * 100 if len(closes) >= 9 else 0
            p5 = (closes[-6] - base) / base * 100 if len(closes) >= 7 else 0
            p10 = (cur_price - base) / base * 100

            pcts_3d.append(p3)
            pcts_5d.append(p5)
            pcts_10d.append(p10)

            # 名称
            cur_n = conn.execute("SELECT name FROM stock_list WHERE code=?", (code,))
            name_row = cur_n.fetchone()
            name = name_row[0] if name_row else code

            stock_details.append({
                "code": code, "name": name, "price": round(cur_price, 2),
                "3d": round(p3, 2), "5d": round(p5, 2), "10d": round(p10, 2),
            })

        if pcts_3d:
            board_stats["avg_3d"] = round(float(np.mean(pcts_3d)), 2)
            board_stats["avg_5d"] = round(float(np.mean(pcts_5d)), 2)
            board_stats["avg_10d"] = round(float(np.mean(pcts_10d)), 2)
            stock_details.sort(key=lambda x: x["10d"], reverse=True)
            board_stats["top_stocks"] = stock_details[:10]

        results.append(board_stats)

    conn.close()
    results.sort(key=lambda x: x["avg_5d"], reverse=True)
    return results


def recommend_stocks(boards: list[str], top_n: int = 10) -> list[dict]:
    """基于事件匹配的板块，推荐短期强势股。"""
    conn = sqlite3.connect(DB_PATH, timeout=5)
    all_stocks = []

    for board in boards:
        cur = conn.execute("SELECT code FROM board_stocks WHERE board=?", (board,))
        codes = [r[0] for r in cur.fetchall()]

        for code in codes[:30]:
            cur2 = conn.execute(
                "SELECT close, high, low, volume FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 60",
                (code,),
            )
            rows = cur2.fetchall()
            if len(rows) < 20:
                continue
            rows = rows[::-1]
            closes = np.array([r[0] for r in rows])
            volumes = np.array([r[3] for r in rows])
            n = len(closes)
            price = float(closes[-1])

            # 评分
            score = 0
            signals = []

            # 短期动量
            mom5 = (price / float(closes[-6]) - 1) * 100 if n >= 6 and closes[-6] > 0 else 0
            if mom5 > 3:
                score += 20
                signals.append(f"5日涨{mom5:.1f}%")

            # 量比
            vol_ma = float(np.mean(volumes[-20:])) if n >= 20 else 1
            vol_ratio = float(volumes[-1]) / max(vol_ma, 1)
            if vol_ratio > 1.5:
                score += 15
                signals.append(f"放量{vol_ratio:.1f}倍")

            # 突破
            if n >= 20:
                high20 = float(np.max(closes[-21:-1]))
                if price >= high20:
                    score += 25
                    signals.append("突破20日高点")

            # 趋势
            ma20 = float(np.mean(closes[-20:])) if n >= 20 else price
            if price > ma20:
                score += 10

            if score < 15:
                continue

            cur_n = conn.execute("SELECT name FROM stock_list WHERE code=?", (code,))
            name_row = cur_n.fetchone()
            name = name_row[0] if name_row else code

            all_stocks.append({
                "code": code, "name": name, "board": board,
                "price": round(price, 2),
                "mom5": round(mom5, 2),
                "vol_ratio": round(vol_ratio, 2),
                "score": score,
                "signals": " ".join(signals),
            })

    conn.close()
    all_stocks.sort(key=lambda x: x["score"], reverse=True)
    return all_stocks[:top_n]


def fetch_news_eastmoney(limit: int = 20) -> list[dict]:
    """从东方财富抓取最新财经快讯。"""
    url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns?client=web&biz=web_news_col&column=350&order=1&needInteractData=0&page_index=1&page_size=" + str(limit)
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://kuaixun.eastmoney.com/",
        })
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode("utf-8"))
        items = data.get("data", {}).get("list", [])
        news = []
        for item in items:
            news.append({
                "title": item.get("title", ""),
                "digest": item.get("digest", ""),
                "date": item.get("showTime", "")[:10],
                "url": item.get("url", ""),
                "source": "东方财富",
            })
        return news
    except Exception:
        return []


def fetch_broker_china_news(limit: int = 30) -> list[dict]:
    """
    抓取券商中国相关资讯（多源聚合）。
    源1: 东方财富搜索"券商中国"
    源2: 新浪财经搜索"券商中国"
    源3: 东方财富股票频道（含券商相关报道）
    """
    results = []

    # 源1: 东方财富资讯搜索
    try:
        url = (
            "https://search-api-web.eastmoney.com/search/jsonp?"
            "cb=&param=%7B%22uid%22%3A%22%22%2C%22keyword%22%3A%22%E5%88%B8%E5%95%86%E4%B8%AD%E5%9B%BD%22%2C"
            "%22type%22%3A%5B%22cmsArticleWebOld%22%5D%2C%22client%22%3A%22web%22%2C"
            f"%22clientType%22%3A%22web%22%2C%22clientVersion%22%3A%22curr%22%2C%22param%22%3A%7B"
            f"%22cmsArticleWebOld%22%3A%7B%22searchScope%22%3A%22default%22%2C%22sort%22%3A%22default%22%2C"
            f"%22pageIndex%22%3A1%2C%22pageSize%22%3A{limit}%2C%22preTag%22%3A%22%22%2C%22postTag%22%3A%22%22%7D%7D%7D"
        )
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://so.eastmoney.com/",
        })
        text = urllib.request.urlopen(req, timeout=10).read().decode("utf-8")
        if text.startswith("("):
            text = text[1:]
        if text.endswith(")"):
            text = text[:-1]
        data = json.loads(text)
        items = data.get("result", {}).get("cmsArticleWebOld", {}).get("list", [])
        for item in items:
            title = item.get("title", "").replace("<em>", "").replace("</em>", "")
            results.append({
                "title": title,
                "digest": item.get("content", "")[:120].replace("<em>", "").replace("</em>", ""),
                "date": item.get("date", "")[:10],
                "url": item.get("url", ""),
                "source": "券商中国(东财)",
            })
    except Exception:
        pass

    # 源2: 新浪财经滚动新闻（含券商中国转载）
    if len(results) < 10:
        try:
            url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=30&page=1"
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://finance.sina.com.cn/",
            })
            text = urllib.request.urlopen(req, timeout=10).read().decode("utf-8")
            data = json.loads(text)
            items = data.get("result", {}).get("data", [])
            for item in items:
                title = item.get("title", "")
                # 筛选含券商/证券/研报相关的
                if any(kw in title for kw in ["券商", "证券", "研报", "研究", "首席", "策略", "行业"]):
                    import time as _time
                    ts = int(item.get("ctime", 0))
                    d = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts > 0 else ""
                    results.append({
                        "title": title,
                        "digest": item.get("intro", "")[:120],
                        "date": d,
                        "url": item.get("url", ""),
                        "source": "新浪财经",
                    })
        except Exception:
            pass

    # 源3: 东方财富研报频道
    if len(results) < 10:
        try:
            url = "https://reportapi.eastmoney.com/report/list?industryCode=*&pageSize=20&industry=*&rating=&ratingChange=&beginTime=&endTime=&pageNo=1&fields=&qType=0&orgCode=&rcode=&p=1&pageNum=1&_=0"
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://data.eastmoney.com/report/",
            })
            text = urllib.request.urlopen(req, timeout=10).read().decode("utf-8")
            data = json.loads(text)
            items = data.get("data", []) or []
            for item in items[:15]:
                results.append({
                    "title": item.get("title", ""),
                    "digest": f"机构: {item.get('orgSName', '')} | 行业: {item.get('industryName', '')} | 评级: {item.get('emRatingName', '')}",
                    "date": item.get("publishDate", "")[:10],
                    "url": f"https://data.eastmoney.com/report/zw_macresearch.jshtml?encodeUrl={item.get('encodeUrl', '')}",
                    "source": "东财研报",
                })
        except Exception:
            pass

    return results


def auto_analyze_news(news_list: list[dict]) -> list[dict]:
    """
    对新闻列表自动进行事件分析：提取关键词、匹配板块、判定影响方向。
    返回增强后的新闻列表（附带 matched_boards, direction）。
    """
    _POSITIVE_KW = {"利好", "突破", "超预期", "增长", "涨停", "创新高", "加码", "扶持", "政策支持", "翻倍", "放量", "龙头"}
    _NEGATIVE_KW = {"利空", "下跌", "暴跌", "减持", "亏损", "退市", "处罚", "制裁", "暂停", "限制", "风险"}

    for news in news_list:
        text = news.get("title", "") + news.get("digest", "")
        boards = match_boards(text)
        news["matched_boards"] = boards

        pos = sum(1 for kw in _POSITIVE_KW if kw in text)
        neg = sum(1 for kw in _NEGATIVE_KW if kw in text)
        if pos > neg:
            news["direction"] = "📈 利好"
        elif neg > pos:
            news["direction"] = "📉 利空"
        else:
            news["direction"] = "➡️ 中性"

        news["keywords"] = ", ".join([kw for kw in KEYWORD_BOARD_MAP if kw in text][:5])

    return news_list


# ============================================================
#  事件-股价历史关联分析引擎
# ============================================================

def _board_index_series(board: str) -> list[tuple]:
    """
    构造板块等权指数序列（date, close），用板块成分股日线均价模拟。
    """
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cur = conn.execute("SELECT code FROM board_stocks WHERE board=?", (board,))
    codes = [r[0] for r in cur.fetchall()]
    if not codes:
        conn.close()
        return []

    from collections import defaultdict
    date_prices = defaultdict(list)
    for code in codes[:40]:
        cur2 = conn.execute(
            "SELECT date, close FROM daily_kline WHERE code=? ORDER BY date", (code,)
        )
        for r in cur2.fetchall():
            if r[1] and r[1] > 0:
                date_prices[r[0]].append(r[1])
    conn.close()

    # 按日期排序，取每天均价作为板块指数
    index = []
    for d in sorted(date_prices.keys()):
        prices = date_prices[d]
        if len(prices) >= 3:
            index.append((d, float(np.mean(prices))))
    return index


def study_event_history(keyword: str, lookforward_days: list[int] = None) -> dict:
    """
    事件研究：找到历史上该关键词相关板块的所有"异动日"，
    分析异动日后 N 天的板块指数走势，构建统计规律。

    异动日定义：板块指数单日涨幅 ≥ 2%（大涨）或 ≤ -2%（大跌）。

    返回：
    {
        keyword, boards, total_events,
        stats: [{ days, avg_return, median_return, win_rate, max_return, min_return }],
        events: [{ date, day_return, fwd_5d, fwd_10d, fwd_20d }],  # 最近的事件样本
        prediction: { direction, confidence, reason }
    }
    """
    if lookforward_days is None:
        lookforward_days = [3, 5, 10, 20]

    boards = KEYWORD_BOARD_MAP.get(keyword, [])
    if not boards:
        for kw, bds in KEYWORD_BOARD_MAP.items():
            if keyword in kw or kw in keyword:
                boards = bds
                break
    if not boards:
        return {"keyword": keyword, "boards": [], "total_events": 0,
                "stats": [], "events": [], "prediction": {"direction": "无数据", "confidence": 0, "reason": "未匹配到板块"}}

    # 取第一个匹配板块构建指数
    main_board = boards[0]
    index = _board_index_series(main_board)
    if len(index) < 60:
        return {"keyword": keyword, "boards": boards, "total_events": 0,
                "stats": [], "events": [], "prediction": {"direction": "数据不足", "confidence": 0, "reason": f"{main_board} 日线不足60天"}}

    dates = [x[0] for x in index]
    closes = np.array([x[1] for x in index])
    n = len(closes)

    # 计算日涨跌幅
    daily_pcts = np.zeros(n)
    for i in range(1, n):
        daily_pcts[i] = (closes[i] / closes[i - 1] - 1) * 100

    # 找异动日（单日涨幅 ≥ 2% 或 ≤ -2%）
    event_indices = [i for i in range(1, n) if abs(daily_pcts[i]) >= 2.0]

    if not event_indices:
        # 放宽到 1.5%
        event_indices = [i for i in range(1, n) if abs(daily_pcts[i]) >= 1.5]

    if not event_indices:
        return {"keyword": keyword, "boards": boards, "total_events": 0,
                "stats": [], "events": [], "prediction": {"direction": "无异动", "confidence": 0, "reason": "历史未出现显著波动"}}

    # 分析每个异动日后 N 天的表现
    fwd_returns = {d: [] for d in lookforward_days}
    event_samples = []

    for idx in event_indices:
        sample = {"date": dates[idx], "day_return": round(daily_pcts[idx], 2)}
        for days in lookforward_days:
            target = idx + days
            if target < n and closes[idx] > 0:
                ret = (closes[target] / closes[idx] - 1) * 100
                fwd_returns[days].append(ret)
                sample[f"fwd_{days}d"] = round(ret, 2)
            else:
                sample[f"fwd_{days}d"] = None
        event_samples.append(sample)

    # 统计汇总
    stats = []
    for days in lookforward_days:
        rets = fwd_returns[days]
        if not rets:
            continue
        arr = np.array(rets)
        stats.append({
            "days": days,
            "samples": len(rets),
            "avg_return": round(float(np.mean(arr)), 2),
            "median_return": round(float(np.median(arr)), 2),
            "win_rate": round(float(np.sum(arr > 0) / len(arr) * 100), 1),
            "max_return": round(float(np.max(arr)), 2),
            "min_return": round(float(np.min(arr)), 2),
            "std": round(float(np.std(arr)), 2),
        })

    # 基于统计规律生成预测
    prediction = _generate_prediction(keyword, main_board, stats, event_samples, daily_pcts)

    return {
        "keyword": keyword,
        "boards": boards,
        "main_board": main_board,
        "total_events": len(event_indices),
        "stats": stats,
        "events": event_samples[-20:],  # 最近 20 个样本
        "prediction": prediction,
    }


def _generate_prediction(keyword: str, board: str, stats: list, events: list, daily_pcts) -> dict:
    """基于历史统计生成预测。"""
    if not stats:
        return {"direction": "无数据", "confidence": 0, "reason": "历史样本不足"}

    # 取 5 日和 10 日统计
    s5 = next((s for s in stats if s["days"] == 5), None)
    s10 = next((s for s in stats if s["days"] == 10), None)
    s20 = next((s for s in stats if s["days"] == 20), None)

    signals = []
    score = 0

    if s5:
        if s5["win_rate"] >= 60:
            score += 25
            signals.append(f"5日胜率{s5['win_rate']:.0f}%")
        elif s5["win_rate"] <= 40:
            score -= 20
            signals.append(f"5日胜率仅{s5['win_rate']:.0f}%")
        if s5["avg_return"] > 1:
            score += 15
            signals.append(f"5日均涨{s5['avg_return']:+.1f}%")
        elif s5["avg_return"] < -1:
            score -= 15
            signals.append(f"5日均跌{s5['avg_return']:+.1f}%")

    if s10:
        if s10["win_rate"] >= 55:
            score += 20
            signals.append(f"10日胜率{s10['win_rate']:.0f}%")
        if s10["avg_return"] > 2:
            score += 15
            signals.append(f"10日均涨{s10['avg_return']:+.1f}%")

    if s20:
        if s20["avg_return"] > 3:
            score += 10
            signals.append(f"20日均涨{s20['avg_return']:+.1f}%")
        elif s20["avg_return"] < -3:
            score -= 10
            signals.append(f"20日均跌{s20['avg_return']:+.1f}%")

    # 最近一次事件的方向
    if events:
        last = events[-1]
        last_ret = last.get("day_return", 0)
        if last_ret > 2:
            score += 10
            signals.append(f"最近一次大涨{last_ret:+.1f}%")
        elif last_ret < -2:
            score -= 5
            signals.append(f"最近一次大跌{last_ret:+.1f}%")

    total_samples = s5["samples"] if s5 else 0
    if total_samples >= 10:
        confidence = min(85, 40 + total_samples * 2)
    elif total_samples >= 5:
        confidence = 35 + total_samples * 3
    else:
        confidence = max(10, total_samples * 8)

    if score >= 30:
        direction = f"📈 看涨（{board}）"
    elif score <= -15:
        direction = f"📉 看跌（{board}）"
    else:
        direction = f"➡️ 震荡（{board}）"

    reason = "；".join(signals[:4]) if signals else "信号不明确"
    return {"direction": direction, "confidence": confidence, "score": score, "reason": reason}


def analyze_news_with_history(news_list: list[dict]) -> list[dict]:
    """
    对新闻列表做历史关联分析：
    每条新闻提取关键词 → 查找历史同类事件 → 分析后续板块走势 → 给出预测。
    """
    _cache = {}
    for news in news_list:
        text = news.get("title", "") + news.get("digest", "")
        keywords = [kw for kw in KEYWORD_BOARD_MAP if kw in text]
        if not keywords:
            news["history_prediction"] = "无匹配关键词"
            news["history_confidence"] = 0
            news["history_detail"] = ""
            continue

        main_kw = keywords[0]
        if main_kw not in _cache:
            _cache[main_kw] = study_event_history(main_kw)
        result = _cache[main_kw]

        pred = result.get("prediction", {})
        news["history_prediction"] = pred.get("direction", "-")
        news["history_confidence"] = pred.get("confidence", 0)
        news["history_detail"] = pred.get("reason", "")
        news["history_events"] = result.get("total_events", 0)

        # 补充统计摘要
        s5 = next((s for s in result.get("stats", []) if s["days"] == 5), None)
        if s5:
            news["history_5d_avg"] = s5["avg_return"]
            news["history_5d_winrate"] = s5["win_rate"]
        else:
            news["history_5d_avg"] = None
            news["history_5d_winrate"] = None

    return news_list
