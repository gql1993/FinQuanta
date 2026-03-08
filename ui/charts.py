"""
Plotly 金融图表构建器
提供 K 线图、资金曲线、回撤图、热力图、VCP 标注、持仓分布等交互式图表。
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def plot_candlestick(df: pd.DataFrame, mas: list[int] | None = None,
                     title: str = "", height: int = 600,
                     prediction: dict | None = None,
                     predictions: list[dict] | None = None,
                     strategy_line_width: float = 2.2,
                     strategy_line_opacity: float = 0.85) -> go.Figure:
    """交互式 K 线图 + 均线 + 成交量 + 预测线"""
    if mas is None:
        mas = [50, 150, 200]

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25], vertical_spacing=0.03,
    )

    fig.add_trace(go.Candlestick(
        x=df["date"], open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name="K线",
        increasing_line_color="#ef5350", decreasing_line_color="#26a69a",
        increasing_fillcolor="#ef5350", decreasing_fillcolor="#26a69a",
    ), row=1, col=1)

    ma_colors = ["#FF9800", "#2196F3", "#9C27B0", "#4CAF50"]
    for i, ma in enumerate(mas):
        if len(df) >= ma:
            ma_val = df["close"].rolling(ma).mean()
            fig.add_trace(go.Scatter(
                x=df["date"], y=ma_val, name=f"MA{ma}",
                line=dict(width=1.2, color=ma_colors[i % len(ma_colors)]),
            ), row=1, col=1)

    # Prediction overlay (single model)
    if prediction and not predictions:
        # Historical backtest prediction line
        bt_dates = prediction.get("backtest_dates", [])
        bt_pred = prediction.get("backtest_pred", [])
        if bt_dates and bt_pred:
            fig.add_trace(go.Scatter(
                x=bt_dates, y=bt_pred, name="回测预测线",
                line=dict(width=2, color="#E91E63", dash="dot"),
                opacity=0.8,
            ), row=1, col=1)

        # Future forecast with confidence band
        fc_dates = prediction.get("forecast_dates", [])
        fc_mid = prediction.get("forecast_mid", [])
        fc_upper = prediction.get("forecast_upper", [])
        fc_lower = prediction.get("forecast_lower", [])
        if fc_dates and fc_mid:
            fig.add_trace(go.Scatter(
                x=fc_dates, y=fc_upper, name="预测上界",
                line=dict(width=0), showlegend=False, mode="lines",
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=fc_dates, y=fc_lower, name="预测区间",
                line=dict(width=0), fill="tonexty",
                fillcolor="rgba(233,30,99,0.1)", showlegend=True,
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=fc_dates, y=fc_mid, name="预测中线",
                line=dict(width=2.5, color="#E91E63"),
            ), row=1, col=1)

        # Divergence markers
        divs = prediction.get("divergences", [])
        if divs:
            div_dates = [d["date"] for d in divs]
            div_prices = [d["actual"] for d in divs]
            div_text = [f"{d['direction']}{abs(d['diff_pct']):.1f}%" for d in divs]
            fig.add_trace(go.Scatter(
                x=div_dates, y=div_prices, mode="markers+text",
                name="背离点",
                marker=dict(size=8, color="#FF5722", symbol="diamond"),
                text=div_text, textposition="top center",
                textfont=dict(size=9, color="#FF5722"),
            ), row=1, col=1)

    # Multi-strategy prediction overlay
    if predictions:
        palette = [
            "#E91E63", "#3F51B5", "#009688", "#FF9800",
            "#9C27B0", "#00ACC1", "#8BC34A", "#795548",
        ]
        for i, pred in enumerate(predictions):
            name = pred.get("strategy_name", pred.get("strategy_id", f"策略{i+1}"))
            color = palette[i % len(palette)]
            bt_dates = pred.get("backtest_dates", [])
            bt_pred = pred.get("backtest_pred", [])
            fc_dates = pred.get("forecast_dates", [])
            fc_mid = pred.get("forecast_mid", [])
            fc_upper = pred.get("forecast_upper", [])
            fc_lower = pred.get("forecast_lower", [])
            show_band = bool(pred.get("_show_band", False))
            show_div = bool(pred.get("_show_divergence", False))

            if bt_dates and bt_pred:
                fig.add_trace(go.Scatter(
                    x=bt_dates, y=bt_pred, name=f"{name}回测线",
                    line=dict(width=max(1.0, strategy_line_width * 0.7), color=color, dash="dot"),
                    opacity=max(0.2, strategy_line_opacity * 0.55), visible="legendonly",
                ), row=1, col=1)

            if show_band and fc_dates and fc_upper and fc_lower:
                fig.add_trace(go.Scatter(
                    x=fc_dates, y=fc_upper, name=f"{name}上界",
                    line=dict(width=0), showlegend=False, mode="lines",
                ), row=1, col=1)
                fig.add_trace(go.Scatter(
                    x=fc_dates, y=fc_lower, name=f"{name}预测区间",
                    line=dict(width=0), fill="tonexty",
                    fillcolor="rgba(33,150,243,0.08)", showlegend=True,
                ), row=1, col=1)

            if fc_dates and fc_mid:
                fig.add_trace(go.Scatter(
                    x=fc_dates, y=fc_mid, name=f"{name}预测中线",
                    line=dict(width=strategy_line_width, color=color),
                    opacity=strategy_line_opacity,
                ), row=1, col=1)

            if show_div:
                divs = pred.get("divergences", [])
                if divs:
                    div_dates = [d["date"] for d in divs]
                    div_prices = [d["actual"] for d in divs]
                    fig.add_trace(go.Scatter(
                        x=div_dates, y=div_prices, mode="markers",
                        name=f"{name}背离点",
                        marker=dict(size=max(5, int(strategy_line_width * 3.2)), color=color, symbol="diamond"),
                        opacity=max(0.3, strategy_line_opacity * 0.9),
                    ), row=1, col=1)

    colors = ["#ef5350" if c >= o else "#26a69a"
              for c, o in zip(df["close"], df["open"])]
    fig.add_trace(go.Bar(
        x=df["date"], y=df["volume"], name="成交量",
        marker_color=colors, opacity=0.5,
    ), row=2, col=1)

    fig.update_layout(
        title=dict(text=title, x=0.0, xanchor="left", y=0.98),
        height=height,
        xaxis_rangeslider_visible=False,
        template="plotly_white",
        # Put legend below plot to avoid colliding with long chart titles in narrow layouts.
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.16,
            xanchor="left",
            x=0,
            font=dict(size=12),
        ),
        margin=dict(l=50, r=20, t=70, b=95),
    )
    fig.update_yaxes(title_text="价格", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1)

    return fig


def plot_equity_curve(equity_df: pd.DataFrame, initial_capital: float,
                      benchmark_df: pd.DataFrame | None = None,
                      height: int = 500) -> go.Figure:
    """资金曲线 vs 基准"""
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.7, 0.3], vertical_spacing=0.05,
    )

    equity_norm = equity_df["total_equity"] / initial_capital
    fig.add_trace(go.Scatter(
        x=equity_df["date"], y=equity_norm,
        name="SEPA策略", line=dict(width=2, color="#1976D2"),
        fill="tozeroy", fillcolor="rgba(25,118,210,0.1)",
    ), row=1, col=1)

    if benchmark_df is not None and not benchmark_df.empty:
        bench = benchmark_df.copy()
        bench["date"] = pd.to_datetime(bench["date"])
        bench = bench[(bench["date"] >= equity_df["date"].iloc[0])
                      & (bench["date"] <= equity_df["date"].iloc[-1])]
        if not bench.empty:
            bench_norm = bench["close"] / bench["close"].iloc[0]
            fig.add_trace(go.Scatter(
                x=bench["date"], y=bench_norm,
                name="沪深300", line=dict(width=1.5, color="#FF9800", dash="dot"),
            ), row=1, col=1)

    fig.add_trace(go.Bar(
        x=equity_df["date"], y=equity_df["num_positions"],
        name="持仓数", marker_color="rgba(25,118,210,0.3)",
    ), row=2, col=1)

    fig.update_layout(
        title="资金曲线（归一化净值）", height=height,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=20, t=60, b=30),
    )
    fig.update_yaxes(title_text="净值", row=1, col=1)
    fig.update_yaxes(title_text="持仓数", row=2, col=1)

    return fig


def plot_drawdown(equity_df: pd.DataFrame, height: int = 300) -> go.Figure:
    """回撤面积图"""
    equity = equity_df["total_equity"].values
    peak = np.maximum.accumulate(equity)
    dd = (peak - equity) / peak * 100

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=equity_df["date"], y=-dd, fill="tozeroy",
        line=dict(color="#ef5350", width=1),
        fillcolor="rgba(239,83,80,0.3)", name="回撤",
    ))

    fig.update_layout(
        title="回撤分析", height=height, template="plotly_white",
        yaxis_title="回撤 (%)",
        margin=dict(l=50, r=20, t=50, b=30),
    )
    return fig


def plot_monthly_heatmap(equity_df: pd.DataFrame, height: int = 350) -> go.Figure:
    """月度收益热力图"""
    df = equity_df[["date", "total_equity"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")

    monthly = df["total_equity"].resample("ME").last()
    monthly_ret = monthly.pct_change().dropna() * 100

    if monthly_ret.empty:
        return go.Figure()

    years = sorted(monthly_ret.index.year.unique())
    months = list(range(1, 13))
    z = []
    text = []
    for y in years:
        row_z = []
        row_t = []
        for m in months:
            mask = (monthly_ret.index.year == y) & (monthly_ret.index.month == m)
            vals = monthly_ret[mask]
            if len(vals) > 0:
                v = vals.iloc[0]
                row_z.append(v)
                row_t.append(f"{v:.1f}%")
            else:
                row_z.append(None)
                row_t.append("")
        z.append(row_z)
        text.append(row_t)

    fig = go.Figure(data=go.Heatmap(
        z=z, x=[f"{m}月" for m in months], y=[str(y) for y in years],
        text=text, texttemplate="%{text}", textfont={"size": 11},
        colorscale="RdYlGn", zmid=0, zmin=-10, zmax=10,
        colorbar=dict(title="%"),
    ))

    fig.update_layout(
        title="月度收益率 (%)", height=height, template="plotly_white",
        margin=dict(l=50, r=20, t=50, b=30),
    )
    return fig


def plot_exit_reasons(trades: list, height: int = 400) -> go.Figure:
    """卖出原因饼图"""
    from collections import Counter
    reasons = Counter()
    for t in trades:
        reason = t.exit_reason if hasattr(t, "exit_reason") else t.get("exit_reason", t.get("reason", ""))
        key = reason.split(":")[0] if ":" in reason else reason
        if key:
            reasons[key] += 1

    if not reasons:
        return go.Figure()

    fig = go.Figure(data=[go.Pie(
        labels=list(reasons.keys()),
        values=list(reasons.values()),
        textinfo="label+percent", hole=0.4,
    )])
    fig.update_layout(
        title="卖出原因分布", height=height, template="plotly_white",
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig


def plot_pnl_distribution(trades: list, height: int = 350) -> go.Figure:
    """单笔盈亏分布"""
    pnls = []
    for t in trades:
        pct = t.pnl_pct if hasattr(t, "pnl_pct") else t.get("pnl_pct", 0)
        pnls.append(pct * 100 if abs(pct) < 1 else pct)

    if not pnls:
        return go.Figure()

    colors = ["#4CAF50" if p > 0 else "#ef5350" for p in pnls]

    fig = go.Figure(data=[go.Bar(
        x=list(range(1, len(pnls) + 1)), y=pnls,
        marker_color=colors,
    )])
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(
        title="单笔交易盈亏 (%)", height=height, template="plotly_white",
        xaxis_title="交易序号", yaxis_title="盈亏 (%)",
        margin=dict(l=50, r=20, t=50, b=30),
    )
    return fig


def plot_vcp_overlay(df: pd.DataFrame, vcp_result: dict,
                     title: str = "", height: int = 500) -> go.Figure:
    """K 线 + VCP 形态标注"""
    lookback = min(120, len(df))
    recent = df.iloc[-lookback:].copy()

    fig = plot_candlestick(recent, mas=[50], title=title or "VCP 形态分析", height=height)

    pivot = vcp_result.get("pivot_price", 0)
    if pivot > 0:
        fig.add_hline(
            y=pivot, line_dash="dash", line_color="#FF9800",
            annotation_text=f"枢纽 {pivot:.2f}",
            annotation_position="bottom right", row=1, col=1,
        )

    if vcp_result.get("breakout_today"):
        last_date = recent["date"].iloc[-1]
        last_close = recent["close"].iloc[-1]
        fig.add_trace(go.Scatter(
            x=[last_date], y=[last_close],
            mode="markers", marker=dict(size=15, color="#FF9800", symbol="triangle-up"),
            name="突破!", showlegend=True,
        ), row=1, col=1)

    return fig


def plot_portfolio_pie(positions: list, live_prices: dict | None = None,
                       cash: float = 0, height: int = 400) -> go.Figure:
    """持仓分布饼图"""
    labels = []
    values = []

    for p in positions:
        code = p.get("code", p.get("code", ""))
        name = p.get("name", code)
        price = live_prices.get(code, p.get("entry_price", 0)) if live_prices else p.get("entry_price", 0)
        mv = price * p.get("shares", 0)
        labels.append(f"{name}")
        values.append(mv)

    if cash > 0:
        labels.append("现金")
        values.append(cash)

    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values,
        # Avoid clipped outer labels on narrow windows; rely on legend + hover for details.
        textinfo="percent",
        textposition="inside",
        insidetextorientation="auto",
        hovertemplate="%{label}: %{value:,.0f} (%{percent})<extra></extra>",
        hole=0.4,
    )])
    fig.update_layout(
        title="资产配置", height=height, template="plotly_white",
        legend=dict(orientation="v", xanchor="left", x=1.02, yanchor="middle", y=0.5),
        margin=dict(l=20, r=150, t=55, b=20),
    )
    return fig


def plot_rs_gauge(rs_rating: float, height: int = 250) -> go.Figure:
    """RS 评级仪表盘"""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=rs_rating,
        title={"text": "相对强度 (RS)"},
        gauge={
            "axis": {"range": [0, 99]},
            "bar": {"color": "#1976D2"},
            "steps": [
                {"range": [0, 40], "color": "#ffcdd2"},
                {"range": [40, 70], "color": "#fff9c4"},
                {"range": [70, 90], "color": "#c8e6c9"},
                {"range": [90, 99], "color": "#4CAF50"},
            ],
            "threshold": {"line": {"color": "red", "width": 2}, "thickness": 0.75, "value": 70},
        },
    ))
    fig.update_layout(height=height, margin=dict(l=30, r=30, t=60, b=20))
    return fig


def plot_sector_treemap(sector_df: pd.DataFrame, height: int = 500) -> go.Figure:
    """板块涨跌幅矩形树图（类同花顺板块热力图）"""
    if sector_df.empty or "板块" not in sector_df.columns:
        return go.Figure()

    df = sector_df.copy()
    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce").fillna(0)
    if "总市值" in df.columns:
        df["总市值"] = pd.to_numeric(df["总市值"], errors="coerce").fillna(1e8)
    else:
        df["总市值"] = 1e8

    df["abs_chg"] = df["涨跌幅"].abs() + 0.01
    df["label"] = df.apply(
        lambda r: f"{r['板块']}<br>{r['涨跌幅']:+.2f}%", axis=1)

    fig = go.Figure(go.Treemap(
        labels=df["label"],
        parents=[""] * len(df),
        values=df["abs_chg"],
        marker=dict(
            colors=df["涨跌幅"],
            colorscale=[
                [0, "#26a69a"],
                [0.45, "#b2dfdb"],
                [0.5, "#eeeeee"],
                [0.55, "#ffcdd2"],
                [1, "#ef5350"],
            ],
            cmid=0,
            colorbar=dict(title="涨跌幅%", ticksuffix="%"),
        ),
        textinfo="label",
        hovertemplate="<b>%{label}</b><extra></extra>",
    ))

    fig.update_layout(
        title="板块涨跌热力图", height=height,
        margin=dict(l=5, r=5, t=40, b=5),
    )
    return fig


def plot_multi_period_bar(periods_data: dict, stock_name: str = "",
                          height: int = 300) -> go.Figure:
    """多周期盈亏柱状图"""
    period_keys = ["当日", "7日", "30日", "一季度", "半年", "一年"]
    labels = []
    values = []
    for k in period_keys:
        v = periods_data.get(k)
        if v is not None:
            labels.append(k)
            values.append(v)

    if not values:
        return go.Figure()

    colors = ["#4CAF50" if v >= 0 else "#ef5350" for v in values]

    max_abs = max(abs(v) for v in values) if values else 1.0
    y_top = max(v for v in values) if values else 0.0
    y_bottom = min(v for v in values) if values else 0.0
    top_pad = max(0.8, max_abs * 0.25)
    bottom_pad = max(0.6, max_abs * 0.12)

    fig = go.Figure(data=[go.Bar(
        x=labels, y=values, marker_color=colors,
        text=[f"{v:+.2f}%" for v in values],
        textposition="outside",
        cliponaxis=False,
    )])
    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=0.5)
    fig.update_layout(
        title=f"{stock_name} 多周期涨跌幅",
        yaxis_title="涨跌幅 (%)",
        height=height, template="plotly_white",
        margin=dict(l=40, r=20, t=72, b=30),
    )
    fig.update_yaxes(range=[y_bottom - bottom_pad, y_top + top_pad])
    return fig


def plot_strategy_correlation(bt_results: dict, height: int = 500) -> go.Figure:
    """
    多策略收益相关性热力图。
    bt_results: {strategy_id: BacktestResult} — 每个结果需有 equity_curve (含 date, total_equity)。
    """
    daily_returns = {}
    for sid, r in bt_results.items():
        eq = getattr(r, "equity_curve", None)
        if eq is None or not hasattr(eq, "empty") or eq.empty:
            continue
        if "total_equity" not in eq.columns:
            continue
        ret = eq.set_index("date")["total_equity"].pct_change().dropna()
        name = getattr(r, "strategy_name", sid)
        daily_returns[name] = ret

    if len(daily_returns) < 2:
        fig = go.Figure()
        fig.update_layout(title="需至少 2 个策略回测结果才能生成相关性矩阵", height=300)
        return fig

    ret_df = pd.DataFrame(daily_returns)
    ret_df = ret_df.dropna(how="all")
    corr = ret_df.corr()

    names = list(corr.columns)
    z = corr.values.tolist()
    text = [[f"{corr.iloc[i, j]:.2f}" for j in range(len(names))] for i in range(len(names))]

    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=names,
        y=names,
        text=text,
        texttemplate="%{text}",
        textfont=dict(size=12),
        colorscale="RdBu_r",
        zmid=0,
        zmin=-1,
        zmax=1,
        colorbar=dict(title="相关系数"),
    ))
    fig.update_layout(
        title="多策略日收益率相关性矩阵",
        height=height,
        template="plotly_white",
        margin=dict(l=100, r=20, t=60, b=100),
        xaxis=dict(tickangle=-45),
    )
    return fig
