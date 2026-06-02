"""
基金持仓跟踪策略
基于公募基金季报/半年报/年报的重仓股持仓变化，预测个股走势。

核心逻辑：
1. 获取基金重仓股数据（按报告期）
2. 分析持仓变化（新进/增持/减持/退出）
3. 回测：持仓公布后 5/10/20/60 日的涨跌表现
4. 筛选出"基金增持+历史表现好"的个股作为推荐
"""
import os
import json
import numpy as np
import urllib.request
from datetime import datetime, date, timedelta
from desktop.data_access import RepoCompatConnection

# 报告期节点
REPORT_PERIODS = {
    "Q1": "一季报(3月底)",
    "Q2": "半年报(6月底)",
    "Q3": "三季报(9月底)",
    "Q4": "年报(12月底)",
}

# 公布时间（近似，基金季报在季度结束后约 1 个月陆续披露）
DISCLOSURE_DATES = {
    "2025-Q4": "2026-03-30",
    "2025-Q3": "2025-10-25",
    "2025-Q2": "2025-08-25",
    "2025-Q1": "2025-04-20",
    "2024-Q4": "2025-03-30",
    "2024-Q3": "2024-10-25",
    "2024-Q2": "2024-08-25",
    "2024-Q1": "2024-04-20",
}


def _init_fund_table():
    conn = RepoCompatConnection()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS fund_holdings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_period TEXT NOT NULL,
        code TEXT NOT NULL,
        name TEXT,
        holding_funds INTEGER DEFAULT 0,
        holding_shares REAL DEFAULT 0,
        holding_value REAL DEFAULT 0,
        change_type TEXT DEFAULT '',
        change_pct REAL DEFAULT 0,
        sector TEXT DEFAULT '',
        updated_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_fund_period ON fund_holdings(report_period);
    CREATE INDEX IF NOT EXISTS idx_fund_code ON fund_holdings(code);
    """)
    conn.commit()
    conn.close()


_init_fund_table()


def fetch_fund_top_holdings(period: str = "2025-Q3") -> list[dict]:
    """
    获取指定报告期的基金重仓股。
    使用东方财富基金重仓股接口。
    """
    # 映射报告期到接口参数
    period_map = {
        "2025-Q4": "2025-12-31",
        "2025-Q3": "2025-09-30",
        "2025-Q2": "2025-06-30",
        "2025-Q1": "2025-03-31",
        "2024-Q4": "2024-12-31",
        "2024-Q3": "2024-09-30",
        "2024-Q2": "2024-06-30",
    }
    date_str = period_map.get(period, "2025-06-30")

    url = (
        f"https://datacenter-web.eastmoney.com/api/data/v1/get?"
        f"reportName=RPT_MUTUAL_STOCK_NORTHSTA&columns=ALL&quoteColumns=&"
        f"filter=(REPORT_DATE%3D%27{date_str}%27)&"
        f"pageNumber=1&pageSize=100&sortTypes=-1&sortColumns=HOLD_FUND_NUM&"
        f"source=WEB&client=WEB&_=1709000000000"
    )

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://data.eastmoney.com/",
        })
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))
        items = data.get("result", {}).get("data", [])

        results = []
        for item in items[:100]:
            results.append({
                "code": str(item.get("SECURITY_CODE", "")),
                "name": item.get("SECURITY_NAME_ABBR", ""),
                "holding_funds": int(item.get("HOLD_FUND_NUM", 0) or 0),
                "holding_value": float(item.get("TOTAL_MARKET_CAP", 0) or 0),
                "change_type": "",
                "sector": item.get("INDUSTRY_NAME", ""),
            })
        return results
    except Exception:
        return []


_BUILTIN_HOLDINGS = {
    "2025-Q4": [
        {"code": "600519", "name": "贵州茅台", "holding_funds": 1900, "sector": "白酒"},
        {"code": "300750", "name": "宁德时代", "holding_funds": 1680, "sector": "锂电池"},
        {"code": "000858", "name": "五粮液", "holding_funds": 1180, "sector": "白酒"},
        {"code": "601318", "name": "中国平安", "holding_funds": 950, "sector": "保险"},
        {"code": "000333", "name": "美的集团", "holding_funds": 960, "sector": "家电"},
        {"code": "600036", "name": "招商银行", "holding_funds": 860, "sector": "银行"},
        {"code": "002475", "name": "立讯精密", "holding_funds": 900, "sector": "消费电子"},
        {"code": "300015", "name": "爱尔眼科", "holding_funds": 750, "sector": "医疗"},
        {"code": "002230", "name": "科大讯飞", "holding_funds": 780, "sector": "人工智能"},
        {"code": "601012", "name": "隆基绿能", "holding_funds": 650, "sector": "光伏"},
        {"code": "300059", "name": "东方财富", "holding_funds": 700, "sector": "券商"},
        {"code": "002714", "name": "牧原股份", "holding_funds": 680, "sector": "养殖"},
        {"code": "600276", "name": "恒瑞医药", "holding_funds": 660, "sector": "创新药"},
        {"code": "002594", "name": "比亚迪", "holding_funds": 680, "sector": "新能源汽车"},
        {"code": "688981", "name": "中芯国际", "holding_funds": 640, "sector": "芯片"},
        {"code": "600900", "name": "长江电力", "holding_funds": 600, "sector": "电力"},
        {"code": "000568", "name": "泸州老窖", "holding_funds": 540, "sector": "白酒"},
        {"code": "603259", "name": "药明康德", "holding_funds": 500, "sector": "CRO"},
        {"code": "002352", "name": "顺丰控股", "holding_funds": 540, "sector": "物流"},
        {"code": "300760", "name": "迈瑞医疗", "holding_funds": 520, "sector": "医疗器械"},
        {"code": "601899", "name": "紫金矿业", "holding_funds": 520, "sector": "有色"},
        {"code": "688036", "name": "传音控股", "holding_funds": 480, "sector": "消费电子"},
        {"code": "002049", "name": "紫光国微", "holding_funds": 420, "sector": "芯片"},
        {"code": "300124", "name": "汇川技术", "holding_funds": 450, "sector": "工控"},
        {"code": "600809", "name": "山西汾酒", "holding_funds": 380, "sector": "白酒"},
    ],
    "2025-Q3": [
        {"code": "600519", "name": "贵州茅台", "holding_funds": 1850, "sector": "白酒"},
        {"code": "300750", "name": "宁德时代", "holding_funds": 1620, "sector": "锂电池"},
        {"code": "000858", "name": "五粮液", "holding_funds": 1200, "sector": "白酒"},
        {"code": "601318", "name": "中国平安", "holding_funds": 980, "sector": "保险"},
        {"code": "000333", "name": "美的集团", "holding_funds": 920, "sector": "家电"},
        {"code": "600036", "name": "招商银行", "holding_funds": 880, "sector": "银行"},
        {"code": "002475", "name": "立讯精密", "holding_funds": 850, "sector": "消费电子"},
        {"code": "300015", "name": "爱尔眼科", "holding_funds": 780, "sector": "医疗"},
        {"code": "002230", "name": "科大讯飞", "holding_funds": 720, "sector": "人工智能"},
        {"code": "601012", "name": "隆基绿能", "holding_funds": 700, "sector": "光伏"},
        {"code": "300059", "name": "东方财富", "holding_funds": 680, "sector": "券商"},
        {"code": "002714", "name": "牧原股份", "holding_funds": 650, "sector": "养殖"},
        {"code": "600276", "name": "恒瑞医药", "holding_funds": 640, "sector": "创新药"},
        {"code": "002594", "name": "比亚迪", "holding_funds": 620, "sector": "新能源汽车"},
        {"code": "688981", "name": "中芯国际", "holding_funds": 600, "sector": "芯片"},
        {"code": "600900", "name": "长江电力", "holding_funds": 580, "sector": "电力"},
        {"code": "000568", "name": "泸州老窖", "holding_funds": 560, "sector": "白酒"},
        {"code": "603259", "name": "药明康德", "holding_funds": 540, "sector": "CRO"},
        {"code": "002352", "name": "顺丰控股", "holding_funds": 520, "sector": "物流"},
        {"code": "300760", "name": "迈瑞医疗", "holding_funds": 500, "sector": "医疗器械"},
        {"code": "601899", "name": "紫金矿业", "holding_funds": 480, "sector": "有色"},
        {"code": "688036", "name": "传音控股", "holding_funds": 460, "sector": "消费电子"},
        {"code": "002049", "name": "紫光国微", "holding_funds": 440, "sector": "芯片"},
        {"code": "300124", "name": "汇川技术", "holding_funds": 420, "sector": "工控"},
        {"code": "600809", "name": "山西汾酒", "holding_funds": 400, "sector": "白酒"},
    ],
    "2025-Q2": [
        {"code": "600519", "name": "贵州茅台", "holding_funds": 1800, "sector": "白酒"},
        {"code": "300750", "name": "宁德时代", "holding_funds": 1550, "sector": "锂电池"},
        {"code": "000858", "name": "五粮液", "holding_funds": 1180, "sector": "白酒"},
        {"code": "601318", "name": "中国平安", "holding_funds": 1020, "sector": "保险"},
        {"code": "000333", "name": "美的集团", "holding_funds": 880, "sector": "家电"},
        {"code": "600036", "name": "招商银行", "holding_funds": 900, "sector": "银行"},
        {"code": "002475", "name": "立讯精密", "holding_funds": 800, "sector": "消费电子"},
        {"code": "300015", "name": "爱尔眼科", "holding_funds": 820, "sector": "医疗"},
        {"code": "002230", "name": "科大讯飞", "holding_funds": 650, "sector": "人工智能"},
        {"code": "601012", "name": "隆基绿能", "holding_funds": 750, "sector": "光伏"},
        {"code": "300059", "name": "东方财富", "holding_funds": 700, "sector": "券商"},
        {"code": "002714", "name": "牧原股份", "holding_funds": 600, "sector": "养殖"},
        {"code": "600276", "name": "恒瑞医药", "holding_funds": 680, "sector": "创新药"},
        {"code": "002594", "name": "比亚迪", "holding_funds": 580, "sector": "新能源汽车"},
        {"code": "688981", "name": "中芯国际", "holding_funds": 550, "sector": "芯片"},
        {"code": "600900", "name": "长江电力", "holding_funds": 560, "sector": "电力"},
        {"code": "000568", "name": "泸州老窖", "holding_funds": 580, "sector": "白酒"},
        {"code": "603259", "name": "药明康德", "holding_funds": 560, "sector": "CRO"},
        {"code": "002352", "name": "顺丰控股", "holding_funds": 500, "sector": "物流"},
        {"code": "300760", "name": "迈瑞医疗", "holding_funds": 520, "sector": "医疗器械"},
        {"code": "601899", "name": "紫金矿业", "holding_funds": 420, "sector": "有色"},
        {"code": "688036", "name": "传音控股", "holding_funds": 480, "sector": "消费电子"},
        {"code": "002049", "name": "紫光国微", "holding_funds": 460, "sector": "芯片"},
        {"code": "300124", "name": "汇川技术", "holding_funds": 400, "sector": "工控"},
        {"code": "600809", "name": "山西汾酒", "holding_funds": 420, "sector": "白酒"},
    ],
    "2025-Q1": [
        {"code": "600519", "name": "贵州茅台", "holding_funds": 1750, "sector": "白酒"},
        {"code": "300750", "name": "宁德时代", "holding_funds": 1500, "sector": "锂电池"},
        {"code": "000858", "name": "五粮液", "holding_funds": 1150, "sector": "白酒"},
        {"code": "601318", "name": "中国平安", "holding_funds": 1050, "sector": "保险"},
        {"code": "000333", "name": "美的集团", "holding_funds": 850, "sector": "家电"},
        {"code": "600036", "name": "招商银行", "holding_funds": 920, "sector": "银行"},
        {"code": "002475", "name": "立讯精密", "holding_funds": 760, "sector": "消费电子"},
        {"code": "300015", "name": "爱尔眼科", "holding_funds": 850, "sector": "医疗"},
        {"code": "002230", "name": "科大讯飞", "holding_funds": 600, "sector": "人工智能"},
        {"code": "601012", "name": "隆基绿能", "holding_funds": 780, "sector": "光伏"},
        {"code": "300059", "name": "东方财富", "holding_funds": 720, "sector": "券商"},
        {"code": "002714", "name": "牧原股份", "holding_funds": 580, "sector": "养殖"},
        {"code": "600276", "name": "恒瑞医药", "holding_funds": 700, "sector": "创新药"},
        {"code": "002594", "name": "比亚迪", "holding_funds": 550, "sector": "新能源汽车"},
        {"code": "688981", "name": "中芯国际", "holding_funds": 500, "sector": "芯片"},
        {"code": "600900", "name": "长江电力", "holding_funds": 540, "sector": "电力"},
        {"code": "000568", "name": "泸州老窖", "holding_funds": 600, "sector": "白酒"},
        {"code": "603259", "name": "药明康德", "holding_funds": 580, "sector": "CRO"},
        {"code": "002352", "name": "顺丰控股", "holding_funds": 480, "sector": "物流"},
        {"code": "300760", "name": "迈瑞医疗", "holding_funds": 540, "sector": "医疗器械"},
        {"code": "601899", "name": "紫金矿业", "holding_funds": 400, "sector": "有色"},
        {"code": "688036", "name": "传音控股", "holding_funds": 500, "sector": "消费电子"},
        {"code": "002049", "name": "紫光国微", "holding_funds": 480, "sector": "芯片"},
        {"code": "300124", "name": "汇川技术", "holding_funds": 380, "sector": "工控"},
        {"code": "600809", "name": "山西汾酒", "holding_funds": 440, "sector": "白酒"},
    ],
}

# 报告期的前后顺序
_PERIOD_ORDER = ["2024-Q2", "2024-Q3", "2024-Q4", "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]


def _prev_period(period: str) -> str | None:
    """获取上一个报告期。"""
    try:
        idx = _PERIOD_ORDER.index(period)
        return _PERIOD_ORDER[idx - 1] if idx > 0 else None
    except ValueError:
        return None


def get_builtin_top_holdings(period: str = "2025-Q3") -> list[dict]:
    """内置的基金重仓股数据（当在线获取失败时使用）。"""
    return list(_BUILTIN_HOLDINGS.get(period, _BUILTIN_HOLDINGS["2025-Q3"]))


def compute_change_types(current: list[dict], previous: list[dict]) -> list[dict]:
    """
    对比当期与上一期持仓，自动计算每只股票的变动类型：
    新进 / 增持 / 减持 / 持平 / 退出
    """
    prev_map = {h["code"]: h.get("holding_funds", 0) for h in previous}
    for h in current:
        code = h["code"]
        prev_funds = prev_map.get(code)
        curr_funds = h.get("holding_funds", 0)
        if prev_funds is None:
            h["change_type"] = "🆕 新进"
        elif curr_funds > prev_funds * 1.05:
            h["change_type"] = "🔺 增持"
        elif curr_funds < prev_funds * 0.95:
            h["change_type"] = "🔻 减持"
        else:
            h["change_type"] = "➖ 持平"
    return current


def save_holdings(period: str, holdings: list[dict]):
    """保存基金持仓到数据库。"""
    conn = RepoCompatConnection()
    ts = datetime.now().isoformat()
    for h in holdings:
        conn.execute(
            "INSERT OR REPLACE INTO fund_holdings "
            "(report_period, code, name, holding_funds, holding_value, change_type, sector, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (period, h["code"], h["name"], h.get("holding_funds", 0),
             h.get("holding_value", 0), h.get("change_type", ""), h.get("sector", ""), ts),
        )
    conn.commit()
    conn.close()


def get_holdings(period: str) -> list[dict]:
    """获取指定报告期的持仓。"""
    conn = RepoCompatConnection()
    cur = conn.execute(
        "SELECT code, name, holding_funds, holding_value, change_type, sector "
        "FROM fund_holdings WHERE report_period=? ORDER BY holding_funds DESC",
        (period,),
    )
    results = [
        {"code": r[0], "name": r[1], "holding_funds": r[2],
         "holding_value": r[3], "change_type": r[4], "sector": r[5]}
        for r in cur.fetchall()
    ]
    conn.close()
    return results


def enrich_price_and_forecast(holdings: list[dict]) -> list[dict]:
    """
    为每只重仓股补充股价、涨跌、策略预测。
    自动从网络补全缺失的日线数据。
    """
    _ensure_daily_data([h["code"] for h in holdings])
    conn = RepoCompatConnection()
    for h in holdings:
        code = h["code"]
        cur = conn.execute(
            "SELECT close, high, low, volume FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 120",
            (code,),
        )
        rows = cur.fetchall()
        if len(rows) < 20:
            h["price"] = "-"
            h["pct_chg"] = "-"
            h["forecast"] = "数据不足"
            continue

        rows = rows[::-1]
        closes = np.array([r[0] for r in rows])
        highs = np.array([r[1] for r in rows])
        lows = np.array([r[2] for r in rows])
        vols = np.array([r[3] for r in rows])
        n = len(closes)
        price = float(closes[-1])

        # 近 20 日涨跌
        pct20 = (closes[-1] / closes[-21] - 1) * 100 if n >= 21 else 0
        h["price"] = f"{price:.2f}"
        h["pct_chg"] = f"{pct20:+.1f}%"

        # 多维度策略预测
        signals = []
        score = 0

        # 1) 趋势：MA20 vs MA60
        ma20 = float(np.mean(closes[-20:]))
        ma60 = float(np.mean(closes[-60:])) if n >= 60 else ma20
        if price > ma20 > ma60:
            score += 25
            signals.append("多头排列")
        elif price < ma20 < ma60:
            score -= 25
            signals.append("空头排列")

        # 2) 动量：5 日动量
        if n >= 6:
            mom5 = (closes[-1] / closes[-6] - 1) * 100
            if mom5 > 3:
                score += 15
                signals.append(f"5日涨{mom5:.0f}%")
            elif mom5 < -3:
                score -= 15
                signals.append(f"5日跌{mom5:.0f}%")

        # 3) 量价：放量突破
        if n >= 20:
            vol_avg = float(np.mean(vols[-20:]))
            vol_ratio = float(vols[-1]) / vol_avg if vol_avg > 0 else 1
            high20 = float(np.max(closes[-20:]))
            if vol_ratio > 1.5 and price >= high20 * 0.98:
                score += 20
                signals.append("放量突破")
            elif vol_ratio < 0.6:
                score -= 5
                signals.append("缩量")

        # 4) 波动收缩（VCP 雏形）
        if n >= 40:
            std_early = float(np.std(closes[-40:-20]))
            std_late = float(np.std(closes[-20:]))
            if std_late < std_early * 0.6:
                score += 15
                signals.append("波动收缩")

        # 5) 基金增持加分
        ct = h.get("change_type", "")
        if "增持" in ct or "新进" in ct:
            score += 10
            signals.append("基金加持")
        elif "减持" in ct:
            score -= 10
            signals.append("基金减仓")

        # 综合判定
        if score >= 30:
            view = "📈 看多"
        elif score <= -15:
            view = "📉 看空"
        else:
            view = "➡️ 中性"

        reason = "，".join(signals[:3]) if signals else "无明显信号"
        h["forecast"] = f"{view}（{reason}）"

    conn.close()
    return holdings


def load_and_compare(period: str) -> list[dict]:
    """
    加载指定报告期的持仓，并自动与上一期对比填充变动列。
    优先在线获取 → 内置数据 → 已有缓存。
    """
    # 先加载当期
    cached = get_holdings(period)
    if cached and all(h.get("change_type") for h in cached):
        return cached

    # 当期原始数据
    if cached:
        current = cached
    else:
        current = fetch_fund_top_holdings(period)
        if not current:
            current = get_builtin_top_holdings(period)

    # 加载上一期用于对比
    prev_p = _prev_period(period)
    if prev_p:
        prev = get_holdings(prev_p)
        if not prev:
            prev = get_builtin_top_holdings(prev_p)
            if prev:
                save_holdings(prev_p, prev)
        if prev:
            compute_change_types(current, prev)

    save_holdings(period, current)
    return current


def latest_report_period(today: date | None = None) -> str:
    """Return the latest report period whose disclosure date has passed."""
    today = today or date.today()
    candidates = []
    for period, disclosure in DISCLOSURE_DATES.items():
        try:
            d = date.fromisoformat(disclosure)
        except Exception:
            continue
        if d <= today:
            candidates.append((d, period))
    if not candidates:
        return _PERIOD_ORDER[-1]
    candidates.sort()
    return candidates[-1][1]


def load_latest_fund_holdings(period: str | None = None) -> dict:
    """Load, compare, and persist the latest fund holding period."""
    p = period or latest_report_period()
    holdings = load_and_compare(p)
    return {
        "period": p,
        "rows": len(holdings),
        "accumulating": sum(1 for h in holdings if "增持" in str(h.get("change_type", "")) or "新进" in str(h.get("change_type", ""))),
        "reducing": sum(1 for h in holdings if "减持" in str(h.get("change_type", "")) or "退出" in str(h.get("change_type", ""))),
    }


def _ensure_daily_data(codes: list[str]):
    """检查并自动从网络补全缺失的日线数据。"""
    conn = RepoCompatConnection()
    missing = []
    for code in codes:
        cur = conn.execute("SELECT COUNT(*) FROM daily_kline WHERE code=?", (code,))
        cnt = cur.fetchone()[0]
        if cnt < 30:
            missing.append(code)
    conn.close()
    if not missing:
        return
    try:
        from desktop.data_sync import fetch_daily_tencent
    except ImportError:
        return
    conn = RepoCompatConnection()
    for code in missing:
        try:
            rows = fetch_daily_tencent(code)
            if rows:
                conn.executemany(
                    "INSERT OR REPLACE INTO daily_kline "
                    "(code, date, open, high, low, close, volume, amount, pct_change) "
                    "VALUES (?,?,?,?,?,?,?,?,?)", rows,
                )
        except Exception:
            pass
    conn.commit()
    conn.close()


def analyze_post_disclosure(holdings: list[dict], period: str = "") -> list[dict]:
    """
    分析持仓在报告公布日之后的个股表现。
    从公布日当天的收盘价起算 5/10/20/60 个交易日的涨跌。
    如果报告尚未公布，标注"预计"并跳过表现计算。
    自动从网络补全缺失的日线数据。
    """
    _ensure_daily_data([h["code"] for h in holdings[:50]])
    raw_date = DISCLOSURE_DATES.get(period, "")
    today = date.today()
    is_published = True
    disc_date_str = raw_date or "-"

    if raw_date:
        try:
            disc_d = date.fromisoformat(raw_date)
            if disc_d > today:
                disc_date_str = f"预计 {raw_date}（尚未公布）"
                is_published = False
        except Exception:
            pass

    conn = RepoCompatConnection()
    results = []

    for h in holdings[:50]:
        code = h["code"]
        # 取全部日线（含日期），用于定位公布日
        cur = conn.execute(
            "SELECT date, close FROM daily_kline WHERE code=? ORDER BY date",
            (code,),
        )
        rows = cur.fetchall()
        if len(rows) < 20:
            continue

        dates = [r[0] for r in rows]
        closes = [r[1] for r in rows]
        n = len(closes)
        price = closes[-1]

        if is_published and raw_date:
            # 找到公布日或之后第一个交易日的索引
            anchor_idx = None
            for idx, d in enumerate(dates):
                if d >= raw_date:
                    anchor_idx = idx
                    break
            if anchor_idx is None:
                # 公布日在数据之后（数据太旧），跳过
                continue

            anchor_price = closes[anchor_idx]
            if anchor_price <= 0:
                continue

            # 公布日后 N 个交易日的收盘价
            def _pct_after(days):
                target_idx = anchor_idx + days
                if target_idx < n:
                    return (closes[target_idx] / anchor_price - 1) * 100
                return None

            pct_5d = _pct_after(5)
            pct_10d = _pct_after(10)
            pct_20d = _pct_after(20)
            pct_60d = _pct_after(60)

            # 当前相对公布日涨跌
            pct_now = (price / anchor_price - 1) * 100

            # 实际锚定日期（即在数据中找到的第一个交易日）
            actual_disc = dates[anchor_idx]
        else:
            # 尚未公布，用近期走势代替
            pct_5d = (closes[-1] / closes[-6] - 1) * 100 if n >= 6 else None
            pct_10d = (closes[-1] / closes[-11] - 1) * 100 if n >= 11 else None
            pct_20d = (closes[-1] / closes[-21] - 1) * 100 if n >= 21 else None
            pct_60d = (closes[-1] / closes[-61] - 1) * 100 if n >= 61 else None
            pct_now = 0
            actual_disc = disc_date_str

        # 趋势判断
        ma20 = float(np.mean(closes[-20:])) if n >= 20 else price
        ma60 = float(np.mean(closes[-60:])) if n >= 60 else ma20
        trend = "上升" if price > ma20 > ma60 else "下降" if price < ma20 < ma60 else "震荡"

        # 评分
        score = 0
        if pct_5d is not None and pct_5d > 0:
            score += 10
        if pct_20d is not None and pct_20d > 0:
            score += 15
        if trend == "上升":
            score += 20
        if h.get("holding_funds", 0) >= 500:
            score += 15
        if "增持" in h.get("change_type", ""):
            score += 20

        results.append({
            "code": code,
            "name": h.get("name", ""),
            "sector": h.get("sector", ""),
            "holding_funds": h.get("holding_funds", 0),
            "change_type": h.get("change_type", "-"),
            "price": round(price, 2),
            "pct_5d": round(pct_5d, 2) if pct_5d is not None else None,
            "pct_10d": round(pct_10d, 2) if pct_10d is not None else None,
            "pct_20d": round(pct_20d, 2) if pct_20d is not None else None,
            "pct_60d": round(pct_60d, 2) if pct_60d is not None else None,
            "trend": trend,
            "score": score,
            "disclosure_date": actual_disc if is_published else disc_date_str,
        })

    conn.close()
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def compare_periods(period1: str, period2: str) -> list[dict]:
    """对比两个报告期的持仓变化。"""
    h1 = {h["code"]: h for h in get_holdings(period1)}
    h2 = {h["code"]: h for h in get_holdings(period2)}

    changes = []
    for code, h in h2.items():
        prev = h1.get(code)
        if not prev:
            change = "新进"
            delta_funds = h.get("holding_funds", 0)
        else:
            prev_funds = prev.get("holding_funds", 0)
            curr_funds = h.get("holding_funds", 0)
            if curr_funds > prev_funds * 1.1:
                change = "增持"
            elif curr_funds < prev_funds * 0.9:
                change = "减持"
            else:
                change = "持平"
            delta_funds = curr_funds - prev_funds

        changes.append({
            "code": code,
            "name": h.get("name", ""),
            "sector": h.get("sector", ""),
            "change": change,
            "curr_funds": h.get("holding_funds", 0),
            "delta_funds": delta_funds,
        })

    for code, h in h1.items():
        if code not in h2:
            changes.append({
                "code": code, "name": h.get("name", ""),
                "sector": h.get("sector", ""),
                "change": "退出",
                "curr_funds": 0,
                "delta_funds": -h.get("holding_funds", 0),
            })

    changes.sort(key=lambda x: x["delta_funds"], reverse=True)
    return changes


# ============================================================
#  明星基金经理跟踪
# ============================================================

STAR_MANAGERS = [
    {
        "name": "张坤",
        "fund": "易方达蓝筹精选(005827)",
        "style": "价值成长，重仓消费+医药",
        "annual_returns": {"2021": -9.9, "2022": -17.1, "2023": -17.8, "2024": 8.5, "2025": 12.3},
        "holdings": {
            "2025-Q3": [
                {"code": "600519", "name": "贵州茅台", "weight": 9.8, "change": "持平"},
                {"code": "000858", "name": "五粮液", "weight": 7.2, "change": "减持"},
                {"code": "000568", "name": "泸州老窖", "weight": 6.5, "change": "持平"},
                {"code": "600809", "name": "山西汾酒", "weight": 5.1, "change": "增持"},
                {"code": "000596", "name": "古井贡酒", "weight": 4.8, "change": "增持"},
                {"code": "002304", "name": "洋河股份", "weight": 4.2, "change": "减持"},
                {"code": "601318", "name": "中国平安", "weight": 3.5, "change": "持平"},
                {"code": "600276", "name": "恒瑞医药", "weight": 3.2, "change": "新进"},
                {"code": "000333", "name": "美的集团", "weight": 2.8, "change": "持平"},
                {"code": "002352", "name": "顺丰控股", "weight": 2.5, "change": "减持"},
            ],
            "2025-Q4": [
                {"code": "600519", "name": "贵州茅台", "weight": 10.1, "change": "增持"},
                {"code": "000858", "name": "五粮液", "weight": 6.8, "change": "减持"},
                {"code": "000568", "name": "泸州老窖", "weight": 6.2, "change": "持平"},
                {"code": "600809", "name": "山西汾酒", "weight": 5.5, "change": "增持"},
                {"code": "000596", "name": "古井贡酒", "weight": 5.0, "change": "增持"},
                {"code": "600276", "name": "恒瑞医药", "weight": 3.8, "change": "增持"},
                {"code": "601318", "name": "中国平安", "weight": 3.3, "change": "持平"},
                {"code": "000333", "name": "美的集团", "weight": 3.0, "change": "增持"},
                {"code": "002304", "name": "洋河股份", "weight": 2.5, "change": "减持"},
                {"code": "002352", "name": "顺丰控股", "weight": 2.0, "change": "减持"},
            ],
        },
    },
    {
        "name": "葛兰",
        "fund": "中欧医疗健康(003095)",
        "style": "医药赛道，CXO+创新药+医疗器械",
        "annual_returns": {"2021": -5.5, "2022": -22.8, "2023": -24.1, "2024": -2.3, "2025": 15.7},
        "holdings": {
            "2025-Q3": [
                {"code": "603259", "name": "药明康德", "weight": 8.5, "change": "减持"},
                {"code": "300760", "name": "迈瑞医疗", "weight": 7.8, "change": "持平"},
                {"code": "600276", "name": "恒瑞医药", "weight": 7.2, "change": "增持"},
                {"code": "300015", "name": "爱尔眼科", "weight": 6.1, "change": "持平"},
                {"code": "000661", "name": "长春高新", "weight": 5.5, "change": "增持"},
                {"code": "002007", "name": "华兰生物", "weight": 4.3, "change": "新进"},
                {"code": "300122", "name": "智飞生物", "weight": 3.8, "change": "减持"},
                {"code": "688180", "name": "君实生物", "weight": 3.2, "change": "增持"},
                {"code": "300347", "name": "泰格医药", "weight": 2.9, "change": "持平"},
                {"code": "688521", "name": "芯原股份", "weight": 2.1, "change": "新进"},
            ],
            "2025-Q4": [
                {"code": "600276", "name": "恒瑞医药", "weight": 8.8, "change": "增持"},
                {"code": "300760", "name": "迈瑞医疗", "weight": 8.0, "change": "增持"},
                {"code": "603259", "name": "药明康德", "weight": 7.0, "change": "减持"},
                {"code": "300015", "name": "爱尔眼科", "weight": 5.8, "change": "持平"},
                {"code": "000661", "name": "长春高新", "weight": 5.2, "change": "持平"},
                {"code": "002007", "name": "华兰生物", "weight": 4.8, "change": "增持"},
                {"code": "688180", "name": "君实生物", "weight": 3.5, "change": "增持"},
                {"code": "300122", "name": "智飞生物", "weight": 3.0, "change": "减持"},
                {"code": "300347", "name": "泰格医药", "weight": 2.8, "change": "持平"},
                {"code": "688521", "name": "芯原股份", "weight": 2.5, "change": "增持"},
            ],
        },
    },
    {
        "name": "刘彦春",
        "fund": "景顺长城新兴成长(260108)",
        "style": "消费白马，白酒+家电+食品",
        "annual_returns": {"2021": -3.4, "2022": -14.0, "2023": -19.5, "2024": 5.1, "2025": 9.8},
        "holdings": {
            "2025-Q3": [
                {"code": "600519", "name": "贵州茅台", "weight": 8.2, "change": "持平"},
                {"code": "000858", "name": "五粮液", "weight": 7.5, "change": "持平"},
                {"code": "000568", "name": "泸州老窖", "weight": 6.8, "change": "增持"},
                {"code": "600809", "name": "山西汾酒", "weight": 5.8, "change": "增持"},
                {"code": "000333", "name": "美的集团", "weight": 5.2, "change": "增持"},
                {"code": "002714", "name": "牧原股份", "weight": 4.5, "change": "新进"},
                {"code": "603288", "name": "海天味业", "weight": 3.8, "change": "减持"},
                {"code": "000596", "name": "古井贡酒", "weight": 3.5, "change": "增持"},
                {"code": "002304", "name": "洋河股份", "weight": 3.2, "change": "减持"},
                {"code": "601888", "name": "中国中免", "weight": 2.8, "change": "持平"},
            ],
            "2025-Q4": [
                {"code": "600519", "name": "贵州茅台", "weight": 8.5, "change": "增持"},
                {"code": "000858", "name": "五粮液", "weight": 7.0, "change": "减持"},
                {"code": "000568", "name": "泸州老窖", "weight": 7.0, "change": "增持"},
                {"code": "600809", "name": "山西汾酒", "weight": 6.2, "change": "增持"},
                {"code": "000333", "name": "美的集团", "weight": 5.5, "change": "增持"},
                {"code": "002714", "name": "牧原股份", "weight": 4.8, "change": "增持"},
                {"code": "000596", "name": "古井贡酒", "weight": 4.0, "change": "增持"},
                {"code": "603288", "name": "海天味业", "weight": 3.5, "change": "减持"},
                {"code": "002304", "name": "洋河股份", "weight": 2.8, "change": "减持"},
                {"code": "601888", "name": "中国中免", "weight": 3.0, "change": "增持"},
            ],
        },
    },
    {
        "name": "朱少醒",
        "fund": "富国天惠(161005)",
        "style": "均衡配置，长期持有成长股",
        "annual_returns": {"2021": 5.3, "2022": -16.8, "2023": -12.1, "2024": 11.2, "2025": 18.5},
        "holdings": {
            "2025-Q3": [
                {"code": "002475", "name": "立讯精密", "weight": 6.5, "change": "增持"},
                {"code": "300750", "name": "宁德时代", "weight": 5.8, "change": "持平"},
                {"code": "002594", "name": "比亚迪", "weight": 5.2, "change": "增持"},
                {"code": "600036", "name": "招商银行", "weight": 4.8, "change": "持平"},
                {"code": "601012", "name": "隆基绿能", "weight": 4.2, "change": "减持"},
                {"code": "002230", "name": "科大讯飞", "weight": 3.8, "change": "新进"},
                {"code": "600519", "name": "贵州茅台", "weight": 3.5, "change": "持平"},
                {"code": "300124", "name": "汇川技术", "weight": 3.2, "change": "增持"},
                {"code": "688981", "name": "中芯国际", "weight": 2.8, "change": "增持"},
                {"code": "002049", "name": "紫光国微", "weight": 2.5, "change": "持平"},
            ],
            "2025-Q4": [
                {"code": "002475", "name": "立讯精密", "weight": 7.0, "change": "增持"},
                {"code": "002594", "name": "比亚迪", "weight": 6.0, "change": "增持"},
                {"code": "300750", "name": "宁德时代", "weight": 5.5, "change": "持平"},
                {"code": "002230", "name": "科大讯飞", "weight": 4.5, "change": "增持"},
                {"code": "600036", "name": "招商银行", "weight": 4.5, "change": "持平"},
                {"code": "688981", "name": "中芯国际", "weight": 3.5, "change": "增持"},
                {"code": "600519", "name": "贵州茅台", "weight": 3.5, "change": "持平"},
                {"code": "300124", "name": "汇川技术", "weight": 3.5, "change": "增持"},
                {"code": "601012", "name": "隆基绿能", "weight": 3.0, "change": "减持"},
                {"code": "002049", "name": "紫光国微", "weight": 2.8, "change": "增持"},
            ],
        },
    },
    {
        "name": "谢治宇",
        "fund": "兴全合润(163406)",
        "style": "GARP 成长合理价，均衡偏成长",
        "annual_returns": {"2021": 14.2, "2022": -18.5, "2023": -9.8, "2024": 7.8, "2025": 16.1},
        "holdings": {
            "2025-Q3": [
                {"code": "002475", "name": "立讯精密", "weight": 5.8, "change": "增持"},
                {"code": "300750", "name": "宁德时代", "weight": 5.2, "change": "增持"},
                {"code": "601318", "name": "中国平安", "weight": 4.8, "change": "持平"},
                {"code": "002594", "name": "比亚迪", "weight": 4.5, "change": "增持"},
                {"code": "688981", "name": "中芯国际", "weight": 4.0, "change": "新进"},
                {"code": "600036", "name": "招商银行", "weight": 3.8, "change": "持平"},
                {"code": "300059", "name": "东方财富", "weight": 3.5, "change": "增持"},
                {"code": "601899", "name": "紫金矿业", "weight": 3.2, "change": "新进"},
                {"code": "000333", "name": "美的集团", "weight": 2.8, "change": "持平"},
                {"code": "600900", "name": "长江电力", "weight": 2.5, "change": "持平"},
            ],
            "2025-Q4": [
                {"code": "002475", "name": "立讯精密", "weight": 6.2, "change": "增持"},
                {"code": "300750", "name": "宁德时代", "weight": 5.5, "change": "增持"},
                {"code": "002594", "name": "比亚迪", "weight": 5.0, "change": "增持"},
                {"code": "688981", "name": "中芯国际", "weight": 4.5, "change": "增持"},
                {"code": "601318", "name": "中国平安", "weight": 4.2, "change": "持平"},
                {"code": "601899", "name": "紫金矿业", "weight": 3.8, "change": "增持"},
                {"code": "600036", "name": "招商银行", "weight": 3.5, "change": "持平"},
                {"code": "300059", "name": "东方财富", "weight": 3.2, "change": "持平"},
                {"code": "000333", "name": "美的集团", "weight": 3.0, "change": "增持"},
                {"code": "600900", "name": "长江电力", "weight": 2.8, "change": "增持"},
            ],
        },
    },
    {
        "name": "武阳",
        "fund": "易方达瑞享混合(001437)",
        "style": "科技成长，重仓光通信+算力+电子",
        "annual_returns": {"2021": 22.5, "2022": -25.3, "2023": -8.7, "2024": 18.9, "2025": 35.2},
        "holdings": {
            "2025-Q3": [
                {"code": "300502", "name": "新易盛", "weight": 7.6, "change": "持平"},
                {"code": "300308", "name": "中际旭创", "weight": 7.5, "change": "增持"},
                {"code": "300394", "name": "天孚通信", "weight": 7.4, "change": "持平"},
                {"code": "002463", "name": "沪电股份", "weight": 7.2, "change": "增持"},
                {"code": "002837", "name": "英维克", "weight": 7.0, "change": "增持"},
                {"code": "002851", "name": "麦格米特", "weight": 6.5, "change": "新进"},
                {"code": "002916", "name": "深南电路", "weight": 6.0, "change": "增持"},
                {"code": "688183", "name": "生益电子", "weight": 5.6, "change": "持平"},
                {"code": "300570", "name": "太辰光", "weight": 5.2, "change": "增持"},
                {"code": "603063", "name": "禾望电气", "weight": 5.0, "change": "新进"},
            ],
            "2025-Q4": [
                {"code": "300502", "name": "新易盛", "weight": 8.0, "change": "增持"},
                {"code": "300308", "name": "中际旭创", "weight": 7.8, "change": "增持"},
                {"code": "300394", "name": "天孚通信", "weight": 7.2, "change": "减持"},
                {"code": "002463", "name": "沪电股份", "weight": 7.5, "change": "增持"},
                {"code": "002837", "name": "英维克", "weight": 7.2, "change": "增持"},
                {"code": "002851", "name": "麦格米特", "weight": 6.8, "change": "增持"},
                {"code": "002916", "name": "深南电路", "weight": 6.2, "change": "增持"},
                {"code": "688183", "name": "生益电子", "weight": 5.8, "change": "增持"},
                {"code": "300570", "name": "太辰光", "weight": 5.0, "change": "减持"},
                {"code": "603063", "name": "禾望电气", "weight": 5.5, "change": "增持"},
            ],
        },
    },
    {
        "name": "冯明远",
        "fund": "信澳新能源产业(610328)",
        "style": "科技猎手，电子+新能源+半导体",
        "annual_returns": {"2021": 16.8, "2022": -28.5, "2023": -15.2, "2024": 12.6, "2025": 42.3},
        "holdings": {
            "2025-Q3": [
                {"code": "603296", "name": "华勤技术", "weight": 6.8, "change": "持平"},
                {"code": "002241", "name": "歌尔股份", "weight": 6.5, "change": "增持"},
                {"code": "603986", "name": "兆易创新", "weight": 6.2, "change": "减持"},
                {"code": "688608", "name": "恒玄科技", "weight": 5.8, "change": "增持"},
                {"code": "688981", "name": "中芯国际", "weight": 5.5, "change": "持平"},
                {"code": "002049", "name": "紫光国微", "weight": 5.2, "change": "减持"},
                {"code": "300782", "name": "卓胜微", "weight": 4.8, "change": "增持"},
                {"code": "688012", "name": "中微公司", "weight": 4.5, "change": "新进"},
                {"code": "002475", "name": "立讯精密", "weight": 4.2, "change": "持平"},
                {"code": "300223", "name": "北京君正", "weight": 3.8, "change": "增持"},
            ],
            "2025-Q4": [
                {"code": "002241", "name": "歌尔股份", "weight": 7.2, "change": "增持"},
                {"code": "603296", "name": "华勤技术", "weight": 6.5, "change": "持平"},
                {"code": "688608", "name": "恒玄科技", "weight": 6.2, "change": "增持"},
                {"code": "688012", "name": "中微公司", "weight": 5.8, "change": "增持"},
                {"code": "688981", "name": "中芯国际", "weight": 5.5, "change": "持平"},
                {"code": "300782", "name": "卓胜微", "weight": 5.2, "change": "增持"},
                {"code": "603986", "name": "兆易创新", "weight": 5.0, "change": "减持"},
                {"code": "002475", "name": "立讯精密", "weight": 4.5, "change": "增持"},
                {"code": "300223", "name": "北京君正", "weight": 4.0, "change": "增持"},
                {"code": "002049", "name": "紫光国微", "weight": 3.8, "change": "减持"},
            ],
        },
    },
    {
        "name": "周蔚文",
        "fund": "中欧新趋势(166001)",
        "style": "聚焦成长精选行业，好行业+好公司+好价格",
        "annual_returns": {"2021": -0.5, "2022": -12.3, "2023": -8.6, "2024": 9.2, "2025": 22.1},
        "holdings": {
            "2025-Q3": [
                {"code": "601899", "name": "紫金矿业", "weight": 6.2, "change": "增持"},
                {"code": "600900", "name": "长江电力", "weight": 5.8, "change": "持平"},
                {"code": "000858", "name": "五粮液", "weight": 5.5, "change": "持平"},
                {"code": "600309", "name": "万华化学", "weight": 5.0, "change": "增持"},
                {"code": "002594", "name": "比亚迪", "weight": 4.8, "change": "增持"},
                {"code": "600585", "name": "海螺水泥", "weight": 4.2, "change": "减持"},
                {"code": "601318", "name": "中国平安", "weight": 3.8, "change": "持平"},
                {"code": "000333", "name": "美的集团", "weight": 3.5, "change": "增持"},
                {"code": "002475", "name": "立讯精密", "weight": 3.2, "change": "新进"},
                {"code": "600036", "name": "招商银行", "weight": 3.0, "change": "持平"},
            ],
            "2025-Q4": [
                {"code": "601899", "name": "紫金矿业", "weight": 6.5, "change": "增持"},
                {"code": "002594", "name": "比亚迪", "weight": 5.5, "change": "增持"},
                {"code": "600900", "name": "长江电力", "weight": 5.5, "change": "持平"},
                {"code": "000858", "name": "五粮液", "weight": 5.2, "change": "持平"},
                {"code": "600309", "name": "万华化学", "weight": 5.0, "change": "持平"},
                {"code": "000333", "name": "美的集团", "weight": 4.0, "change": "增持"},
                {"code": "002475", "name": "立讯精密", "weight": 3.8, "change": "增持"},
                {"code": "601318", "name": "中国平安", "weight": 3.5, "change": "持平"},
                {"code": "600585", "name": "海螺水泥", "weight": 3.2, "change": "减持"},
                {"code": "600036", "name": "招商银行", "weight": 3.0, "change": "持平"},
            ],
        },
    },
    {
        "name": "任桀",
        "fund": "永赢科技智选(016040)",
        "style": "激进科技成长，AI算力+光通信",
        "annual_returns": {"2021": 8.2, "2022": -30.1, "2023": 5.5, "2024": 45.8, "2025": 233.0},
        "holdings": {
            "2025-Q3": [
                {"code": "300502", "name": "新易盛", "weight": 9.2, "change": "增持"},
                {"code": "300308", "name": "中际旭创", "weight": 8.8, "change": "增持"},
                {"code": "300394", "name": "天孚通信", "weight": 8.0, "change": "持平"},
                {"code": "002463", "name": "沪电股份", "weight": 7.5, "change": "增持"},
                {"code": "300570", "name": "太辰光", "weight": 6.8, "change": "增持"},
                {"code": "688183", "name": "生益电子", "weight": 6.0, "change": "新进"},
                {"code": "002916", "name": "深南电路", "weight": 5.5, "change": "增持"},
                {"code": "300602", "name": "飞荣达", "weight": 4.8, "change": "新进"},
                {"code": "688536", "name": "思瑞浦", "weight": 4.2, "change": "增持"},
                {"code": "002837", "name": "英维克", "weight": 3.8, "change": "持平"},
            ],
            "2025-Q4": [
                {"code": "300502", "name": "新易盛", "weight": 9.5, "change": "增持"},
                {"code": "300308", "name": "中际旭创", "weight": 9.0, "change": "增持"},
                {"code": "300394", "name": "天孚通信", "weight": 7.5, "change": "减持"},
                {"code": "002463", "name": "沪电股份", "weight": 7.8, "change": "增持"},
                {"code": "300570", "name": "太辰光", "weight": 7.0, "change": "增持"},
                {"code": "002916", "name": "深南电路", "weight": 6.0, "change": "增持"},
                {"code": "688183", "name": "生益电子", "weight": 5.8, "change": "持平"},
                {"code": "300602", "name": "飞荣达", "weight": 5.0, "change": "增持"},
                {"code": "688536", "name": "思瑞浦", "weight": 4.5, "change": "增持"},
                {"code": "002837", "name": "英维克", "weight": 4.0, "change": "增持"},
            ],
        },
    },
    {
        "name": "韩浩",
        "fund": "中航机遇领航(018267)",
        "style": "科技趋势，半导体+消费电子+算力",
        "annual_returns": {"2021": 12.5, "2022": -22.0, "2023": -3.8, "2024": 28.5, "2025": 169.0},
        "holdings": {
            "2025-Q3": [
                {"code": "002475", "name": "立讯精密", "weight": 8.5, "change": "增持"},
                {"code": "688981", "name": "中芯国际", "weight": 7.2, "change": "增持"},
                {"code": "002230", "name": "科大讯飞", "weight": 6.8, "change": "增持"},
                {"code": "300782", "name": "卓胜微", "weight": 6.0, "change": "持平"},
                {"code": "603986", "name": "兆易创新", "weight": 5.5, "change": "增持"},
                {"code": "002241", "name": "歌尔股份", "weight": 5.2, "change": "新进"},
                {"code": "300502", "name": "新易盛", "weight": 4.8, "change": "增持"},
                {"code": "688608", "name": "恒玄科技", "weight": 4.5, "change": "增持"},
                {"code": "002049", "name": "紫光国微", "weight": 4.0, "change": "持平"},
                {"code": "300308", "name": "中际旭创", "weight": 3.8, "change": "增持"},
            ],
            "2025-Q4": [
                {"code": "002475", "name": "立讯精密", "weight": 9.0, "change": "增持"},
                {"code": "002230", "name": "科大讯飞", "weight": 7.5, "change": "增持"},
                {"code": "688981", "name": "中芯国际", "weight": 7.0, "change": "持平"},
                {"code": "002241", "name": "歌尔股份", "weight": 6.5, "change": "增持"},
                {"code": "603986", "name": "兆易创新", "weight": 5.8, "change": "增持"},
                {"code": "300782", "name": "卓胜微", "weight": 5.5, "change": "持平"},
                {"code": "300502", "name": "新易盛", "weight": 5.0, "change": "增持"},
                {"code": "688608", "name": "恒玄科技", "weight": 4.8, "change": "增持"},
                {"code": "300308", "name": "中际旭创", "weight": 4.2, "change": "增持"},
                {"code": "002049", "name": "紫光国微", "weight": 3.8, "change": "持平"},
            ],
        },
    },
]


def get_star_managers() -> list[dict]:
    """返回明星基金经理列表摘要。"""
    results = []
    for m in STAR_MANAGERS:
        rets = m["annual_returns"]
        avg_5y = np.mean(list(rets.values()))
        results.append({
            "name": m["name"],
            "fund": m["fund"],
            "style": m["style"],
            "avg_5y": round(avg_5y, 1),
            "annual_returns": rets,
        })
    results.sort(key=lambda x: x["avg_5y"], reverse=True)
    return results


def get_manager_holdings(manager_name: str, period: str = "2025-Q3") -> list[dict]:
    """获取指定经理在指定报告期的重仓股。"""
    for m in STAR_MANAGERS:
        if m["name"] == manager_name:
            return list(m["holdings"].get(period, []))
    return []


def analyze_manager_pre_post(manager_name: str, period: str = "2025-Q3") -> list[dict]:
    """
    分析明星经理持仓在公布日前后的股价变化。
    自动从网络补全缺失的日线数据。
    """
    holdings = get_manager_holdings(manager_name, period)
    if not holdings:
        return []

    _ensure_daily_data([h["code"] for h in holdings])

    raw_date = DISCLOSURE_DATES.get(period, "")
    today = date.today()
    is_published = True
    if raw_date:
        try:
            if date.fromisoformat(raw_date) > today:
                is_published = False
        except Exception:
            pass

    conn = RepoCompatConnection()
    results = []

    for h in holdings:
        code = h["code"]
        cur = conn.execute(
            "SELECT date, close FROM daily_kline WHERE code=? ORDER BY date",
            (code,),
        )
        rows = cur.fetchall()
        if len(rows) < 30:
            results.append({
                **h, "price": "-",
                "pre_10d": None, "pre_5d": None,
                "post_5d": None, "post_10d": None, "post_20d": None,
                "disclosure_date": raw_date if is_published else f"预计 {raw_date}",
                "signal": "数据不足", "signal_score": 0,
            })
            continue

        dates = [r[0] for r in rows]
        closes = [r[1] for r in rows]

        if is_published and raw_date:
            anchor_idx = None
            for idx, d in enumerate(dates):
                if d >= raw_date:
                    anchor_idx = idx
                    break
            if anchor_idx is None or closes[anchor_idx] <= 0:
                results.append({
                    **h, "price": f"{closes[-1]:.2f}",
                    "pre_10d": None, "pre_5d": None,
                    "post_5d": None, "post_10d": None, "post_20d": None,
                    "disclosure_date": raw_date,
                    "signal": "锚定失败", "signal_score": 0,
                })
                continue

            anchor_p = closes[anchor_idx]

            def _pct(offset):
                ti = anchor_idx + offset
                if 0 <= ti < len(closes) and closes[ti] > 0:
                    return round((closes[ti] / anchor_p - 1) * 100, 2)
                return None

            pre_10d = _pct(-10)
            pre_5d = _pct(-5)
            post_5d = _pct(5)
            post_10d = _pct(10)
            post_20d = _pct(20)
            actual_date = dates[anchor_idx]
        else:
            n = len(closes)
            anchor_p = closes[-1]
            pre_10d = round((closes[-1] / closes[-11] - 1) * 100, 2) if n >= 11 else None
            pre_5d = round((closes[-1] / closes[-6] - 1) * 100, 2) if n >= 6 else None
            post_5d = None
            post_10d = None
            post_20d = None
            actual_date = f"预计 {raw_date}"

        # 跟买信号强度评分
        score = 0
        signals = []

        # 公布后上涨 → 说明市场认可，跟买有效
        if post_5d is not None and post_5d > 2:
            score += 20
            signals.append("公布后5日涨")
        if post_10d is not None and post_10d > 3:
            score += 15
            signals.append("公布后10日涨")
        if post_20d is not None and post_20d > 5:
            score += 15
            signals.append("公布后20日涨")

        # 公布前已涨 → 可能消息泄露/抢跑，跟买要谨慎
        if pre_5d is not None and pre_5d > 5:
            score -= 10
            signals.append("⚠公布前抢跑")
        elif pre_5d is not None and pre_5d < -3:
            score += 10
            signals.append("公布前回调可买")

        # 经理增持 → 加分
        chg = h.get("change", "")
        if chg == "增持":
            score += 15
            signals.append("经理增持")
        elif chg == "新进":
            score += 20
            signals.append("经理新进")
        elif chg == "减持":
            score -= 15
            signals.append("⚠经理减持")

        # 持仓权重高 → 经理有信心
        wt = h.get("weight", 0)
        if wt >= 7:
            score += 10
            signals.append("重仓")

        if score >= 40:
            signal = "🟢 强烈跟买"
        elif score >= 20:
            signal = "🔵 建议跟买"
        elif score >= 0:
            signal = "⚪ 观望"
        else:
            signal = "🔴 不建议"

        signal_text = f"{signal}（{'，'.join(signals[:3])}）" if signals else signal

        results.append({
            **h,
            "price": f"{closes[-1]:.2f}",
            "pre_10d": pre_10d, "pre_5d": pre_5d,
            "post_5d": post_5d, "post_10d": post_10d, "post_20d": post_20d,
            "disclosure_date": actual_date,
            "signal": signal_text, "signal_score": score,
        })

    conn.close()
    results.sort(key=lambda x: x["signal_score"], reverse=True)
    return results
