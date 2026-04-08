"""
统一业务域模型

目的：
1. 为桌面端 / Web端 / OpenClaw / daemon 提供统一的数据结构
2. 避免不同模块对同一业务实体使用不同字段名
3. 便于后续抽离 engine 层和服务层
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CandidateSignal:
    code: str
    name: str = ""
    board: str = ""
    strategy: str = ""
    score: float = 0.0
    price: float = 0.0
    signal_type: str = ""
    buy_advice: str = ""
    action_advice: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


@dataclass
class PortfolioPosition:
    code: str
    name: str = ""
    mode: str = ""
    entry_price: float = 0.0
    shares: int = 0
    entry_date: str = ""
    stop_loss: float = 0.0
    latest_price: float = 0.0
    market_value: float = 0.0
    pnl_pct: float = 0.0
    advice: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TradeDecision:
    action: str
    code: str
    name: str = ""
    mode: str = ""
    price: float = 0.0
    shares: int = 0
    reason: str = ""
    confidence: float = 0.0
    source: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RiskSnapshot:
    timestamp: str
    var95: float = 0.0
    var99: float = 0.0
    max_exposure: float = 0.0
    max_name: str = "-"
    hhi: float = 0.0
    drawdown: float = 0.0
    market_state: str = ""
    risk_level: str = ""
    n_positions: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LearningFeedback:
    module: str
    metric: str
    value: float
    detail: str = ""
    strategy: str = ""
    weight: float = 0.0
    timestamp: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MarketBar:
    """单根 K 线 / 行情条（统一 OHLCV）。"""

    symbol: str
    date: str = ""
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    amount: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TradingOrder:
    """交易主干使用的订单（与券商原始字段解耦）。"""

    order_id: str
    symbol: str
    side: str
    price: float
    volume: int
    status: str
    filled_volume: int = 0
    avg_fill_price: float = 0.0
    account_id: str = ""
    strategy: str = ""
    order_type: str = "MARKET"
    client_order_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    message: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OrderFill:
    """成交回报。"""

    fill_id: str
    order_id: str
    symbol: str
    side: str
    price: float
    volume: int
    timestamp: str = ""
    commission: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AccountSnapshot:
    """账户资金快照（与 Broker PositionSnapshot 并存：此处偏业务汇总）。"""

    account_id: str
    cash: float = 0.0
    available: float = 0.0
    equity: float = 0.0
    initial_capital: float = 0.0
    currency: str = "CNY"
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskRecord:
    """任务运行记录（与 task_run_log 对齐）。"""

    task_name: str
    trigger_source: str
    status: str
    elapsed_ms: float = 0.0
    summary: str = ""
    detail: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SystemEventRecord:
    """系统审计事件（与 system_event_log 对齐）。"""

    source: str
    category: str
    title: str
    detail: str = ""
    level: str = "info"
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_candidate_from_legacy(row: dict[str, Any]) -> CandidateSignal:
    """兼容旧字典字段名。"""
    return CandidateSignal(
        code=row.get("代码", row.get("code", "")),
        name=row.get("名称", row.get("name", "")),
        board=row.get("板块", row.get("board", "")),
        strategy=row.get("策略", row.get("strategy", "")),
        score=float(row.get("评分", row.get("score", 0)) or 0),
        price=float(str(row.get("价格", row.get("price", 0)) or 0).replace(",", "")),
        signal_type=row.get("信号", row.get("signal_type", "")),
        buy_advice=row.get("建议买入", row.get("buy_advice", "")),
        action_advice=row.get("建议操作", row.get("action_advice", "")),
        extra={k: v for k, v in row.items() if k not in {
            "代码", "code", "名称", "name", "板块", "board", "策略", "strategy",
            "评分", "score", "价格", "price", "信号", "signal_type", "建议买入",
            "buy_advice", "建议操作", "action_advice",
        }},
    )
