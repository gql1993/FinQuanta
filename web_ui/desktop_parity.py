"""
Web pages aligned with PyQt6 desktop tabs (方案一远程控制台).
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st


def render_manual_portfolio(api_call, guard_platform_mode) -> None:
    import pandas as pd

    st.title("💼 模拟仓管理")

    try:
        detail = api_call("GET", "/api/portfolio/manual").get("data", {})
    except Exception as e:
        guard_platform_mode("manual portfolio", e)
        from core.application.manual_portfolio_service import get_manual_portfolio_detail

        detail = get_manual_portfolio_detail()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总资产", f"¥{detail.get('equity', 0):,.0f}")
    c2.metric("总收益", f"{detail.get('return_pct', 0):+.2f}%")
    c3.metric("可用现金", f"¥{detail.get('cash', 0):,.0f}")
    c4.metric("浮动盈亏", f"¥{detail.get('unrealized_pnl', 0):+,.0f}")

    tab_pos, tab_buy, tab_sell, tab_hist = st.tabs(["📊 持仓", "🛒 买入", "📤 卖出", "📋 交易记录"])

    with tab_pos:
        positions = detail.get("positions", [])
        if positions:
            df = pd.DataFrame(positions)
            cols = [
                c
                for c in [
                    "code",
                    "name",
                    "entry_price",
                    "current_price",
                    "pnl_pct",
                    "shares",
                    "entry_date",
                    "stop_loss",
                ]
                if c in df.columns
            ]
            rename = {
                "code": "代码",
                "name": "名称",
                "entry_price": "买入价",
                "current_price": "现价",
                "pnl_pct": "盈亏%",
                "shares": "股数",
                "entry_date": "买入日",
                "stop_loss": "止损",
            }
            st.dataframe(df[cols].rename(columns=rename), use_container_width=True, height=400)
        else:
            st.info("暂无持仓")

    with tab_buy:
        code = st.text_input("股票代码", key="manual_buy_code", placeholder="6位代码")
        price = st.number_input("买入价（0=自动）", min_value=0.0, value=0.0, step=0.01, key="manual_buy_price")
        shares = st.number_input("股数", min_value=100, value=100, step=100, key="manual_buy_shares")
        stop_pct = st.number_input("止损%", min_value=1.0, max_value=30.0, value=8.0, key="manual_buy_stop")
        if st.button("确认买入", type="primary"):
            try:
                resp = api_call(
                    "POST",
                    "/api/portfolio/manual/buy",
                    {
                        "code": code.strip(),
                        "price": price,
                        "shares": int(shares),
                        "stop_loss_pct": stop_pct,
                    },
                )
                if resp.get("ok"):
                    st.success(resp.get("message", "买入成功"))
                    st.rerun()
                else:
                    st.error(resp.get("message", "买入失败"))
            except Exception as e:
                st.error(str(e))

    with tab_sell:
        code = st.text_input("股票代码", key="manual_sell_code", placeholder="6位代码")
        price = st.number_input("卖出价（0=自动）", min_value=0.0, value=0.0, step=0.01, key="manual_sell_price")
        shares = st.number_input("股数（0=全部）", min_value=0, value=0, step=100, key="manual_sell_shares")
        if st.button("确认卖出", type="primary"):
            try:
                resp = api_call(
                    "POST",
                    "/api/portfolio/manual/sell",
                    {"code": code.strip(), "price": price, "shares": int(shares)},
                )
                if resp.get("ok"):
                    st.success(resp.get("message", "卖出成功"))
                    st.rerun()
                else:
                    st.error(resp.get("message", "卖出失败"))
            except Exception as e:
                st.error(str(e))

    with tab_hist:
        hist = detail.get("history", [])
        if hist:
            st.dataframe(pd.DataFrame(hist), use_container_width=True, height=320)
        else:
            st.info("暂无交易记录")


def render_arena(api_call, guard_platform_mode) -> None:
    import pandas as pd

    st.title("🏆 策略竞技场 — 19 种策略赛马")
    st.caption(
        "每位操作手独立模拟仓（各 100 万），共享快照公平对比。"
        " 与桌面端「策略竞技场」一致。"
    )

    boards_text = st.text_input("板块（逗号分隔）", value="人工智能,芯片,量子科技")
    c1, c2 = st.columns(2)
    if c1.button("▶ 跑一轮竞技场", type="primary"):
        boards = [b.strip() for b in boards_text.split(",") if b.strip()]
        with st.spinner("竞技场运行中…"):
            try:
                resp = api_call("POST", "/api/arena/run", {"dry_run": False, "boards": boards})
                if resp.get("ok", True):
                    st.success(resp.get("message", "完成"))
                    st.rerun()
                else:
                    st.error(resp.get("message", "运行失败"))
            except Exception as e:
                st.error(str(e))
    if c2.button("🔄 刷新"):
        st.rerun()

    try:
        lb = api_call("GET", "/api/arena/leaderboard").get("data", {})
        pos_data = api_call("GET", "/api/arena/positions").get("data", {})
        last_run = api_call("GET", "/api/arena/run/latest").get("data", {})
    except Exception as e:
        guard_platform_mode("arena", e)
        from core.application.arena_service import (
            get_arena_latest_run,
            get_arena_leaderboard,
            get_arena_positions,
        )

        lb = get_arena_leaderboard()
        pos_data = get_arena_positions()
        last_run = get_arena_latest_run()

    if last_run.get("skipped") and last_run.get("message"):
        st.warning(last_run["message"])
    elif last_run.get("leaderboard_text"):
        st.info(last_run.get("leaderboard_text", "")[:500])

    rows = lb.get("rows", [])
    if rows:
        df = pd.DataFrame(rows)
        show = [
            c
            for c in [
                "rank",
                "display_name",
                "strategy_id",
                "equity",
                "return_pct",
                "win_rate",
                "positions",
                "total_trades",
                "composite_score",
            ]
            if c in df.columns
        ]
        st.subheader("📊 排行榜")
        st.dataframe(
            df[show].rename(
                columns={
                    "rank": "排名",
                    "display_name": "操作手",
                    "strategy_id": "策略",
                    "equity": "总资产",
                    "return_pct": "收益率%",
                    "win_rate": "胜率%",
                    "positions": "持仓数",
                    "total_trades": "交易",
                    "composite_score": "综合分",
                }
            ),
            use_container_width=True,
            height=420,
        )

    positions = pos_data.get("positions", [])
    if positions:
        st.subheader("📋 全部操作手当前持仓")
        pdf = pd.DataFrame(positions)
        st.dataframe(
            pdf.rename(
                columns={
                    "participant": "操作手",
                    "code": "代码",
                    "name": "名称",
                    "entry_price": "买入价",
                    "current_price": "现价",
                    "pnl_pct": "盈亏%",
                    "shares": "股数",
                    "entry_date": "买入日",
                }
            ),
            use_container_width=True,
            height=360,
        )


def render_short_term(api_call, guard_platform_mode) -> None:
    import pandas as pd

    st.title("⚡ 短期选股")
    tab_event, tab_fund = st.tabs(["⚡ 事件选股", "🏦 基金持仓"])

    with tab_event:
        if st.button("🔄 运行短期选股+NLP", type="primary"):
            with st.spinner("执行 daemon 短期任务…"):
                try:
                    api_call(
                        "POST",
                        "/api/task/trigger/short_term",
                        {"dry_run": False, "run_async": False},
                    )
                    st.success("任务已执行，请刷新查看")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        try:
            sentiment = api_call("GET", "/api/short-term/sentiment").get("data", {})
            events = api_call("GET", "/api/short-term/events?limit=50").get("data", {}).get("items", [])
        except Exception as e:
            guard_platform_mode("short term", e)
            from core.application.short_term_service import (
                get_news_sentiment_snapshot,
                list_recent_events,
            )

            sentiment = get_news_sentiment_snapshot()
            events = list_recent_events(50)

        if sentiment:
            c1, c2, c3 = st.columns(3)
            c1.metric("利好", sentiment.get("positive", sentiment.get("利好", 0)))
            c2.metric("利空", sentiment.get("negative", sentiment.get("利空", 0)))
            c3.metric("更新时间", str(sentiment.get("updated_at", ""))[:19])

        if events:
            st.dataframe(pd.DataFrame(events), use_container_width=True, height=400)
        else:
            st.info("暂无事件记录，可点击上方按钮运行短期选股任务")

    with tab_fund:
        try:
            fund = api_call("GET", "/api/short-term/fund-holdings?limit=200").get("data", {})
        except Exception as e:
            guard_platform_mode("fund holdings", e)
            from core.application.short_term_service import list_fund_holdings

            fund = list_fund_holdings(limit=200)

        period = fund.get("report_period", "")
        st.caption(f"报告期: {period or '无'}")
        items = fund.get("items", [])
        if items:
            st.dataframe(pd.DataFrame(items), use_container_width=True, height=500)
        else:
            st.info("暂无基金持仓数据")


def render_ops_center(api_call, guard_platform_mode, get_ops_center_payload_throttled) -> None:
    import pandas as pd

    st.title("🛰 运行中心")
    force_refresh = st.button("刷新运行中心")
    try:
        ops_center = get_ops_center_payload_throttled(force_refresh=force_refresh)
        registry = ops_center.get("registry", {})
        reg_meta = registry.get("meta", {}) if isinstance(registry, dict) else {}
        tasks = ops_center.get("tasks", [])
        events = ops_center.get("events", [])
        st.caption(
            f"Registry token: {reg_meta.get('change_token', '-')} | "
            f"策略 {reg_meta.get('strategy_count', '-')} | "
            f"工作流 {reg_meta.get('workflow_count', '-')}"
        )
        if tasks:
            st.subheader("任务")
            st.dataframe(pd.DataFrame(tasks), use_container_width=True, height=280)
        if events:
            st.subheader("系统事件")
            st.dataframe(pd.DataFrame(events), use_container_width=True, height=320)
    except Exception as e:
        st.warning(f"运行中心加载失败: {e}")
