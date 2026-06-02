from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    ok: bool
    token: str = ""
    role: str = "viewer"
    message: str = ""


class ApiResponse(BaseModel):
    ok: bool = True
    message: str = ""
    data: Any = None


class TriggerRequest(BaseModel):
    dry_run: bool = False
    run_async: bool = True
    priority: int | None = None
    max_retries: int | None = None
    boards: list[str] = Field(default_factory=list)


class ManualPortfolioBuyRequest(BaseModel):
    code: str
    price: float = 0
    shares: int = 100
    stop_loss_pct: float = 8.0


class ManualPortfolioSellRequest(BaseModel):
    code: str
    price: float = 0
    shares: int = 0


class ArenaRunRequest(BaseModel):
    dry_run: bool = False
    boards: list[str] = Field(default_factory=lambda: ["人工智能"])


class CoordinatorPolicyRequest(BaseModel):
    observe_blocked_ratio: float | None = None
    sell_only_sentiment_ratio: float | None = None
    limit_buy_sentiment_ratio: float | None = None
    limit_buy_max_count: int | None = None
    learning_min_samples: int | None = None


class UnattendedTradeGuardRequest(BaseModel):
    enabled: bool | None = None
    unattended_buy_enabled: bool | None = None
    allow_sell_when_buy_disabled: bool | None = None
    max_daily_buy_amount: float | None = None
    max_single_buy_amount: float | None = None
    max_daily_buy_count: int | None = None
    max_batch_buy_amount: float | None = None
    max_batch_buy_count: int | None = None
    max_symbol_daily_buy_count: int | None = None
    max_sector_daily_buy_amount: float | None = None
    max_sector_daily_buy_count: int | None = None
    buy_cooldown_minutes: int | None = None
    require_simulation_pass: bool | None = None
    simulation_min_success_runs: int | None = None
    blacklist: list[str] | str | None = None
    whitelist: list[str] | str | None = None


class OpenClawDaemonAlertPolicyRequest(BaseModel):
    enabled: bool | None = None
    suppress_seconds: int | None = None
    escalate_after: int | None = None
    notify_on_success: bool | None = None
    notify_on_warning: bool | None = None
    notify_on_error: bool | None = None
    success_summary_interval_seconds: int | None = None
    min_level: str | None = None
    default_channels: list[str] | str | None = None
    escalation_channels: list[str] | str | None = None


class OpenClawGuardReplayRequest(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    limit: int = 10
    shares: int = 100
    mode: str = "auto"
    use_real_price: bool = False


class OpenClawHistoricalReplayRequest(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    limit: int = 30
    include_guard_replay: bool = True
    replay_limit: int = 10
    shares: int = 100
    mode: str = "auto"
    use_real_price: bool = False


class OpenClawConfigRollbackRequest(BaseModel):
    audit_index: int = 0


class ApprovalTradeRequest(BaseModel):
    mode: str = "auto"
    action: str
    code: str
    name: str = ""
    price: float
    shares: int
    reason: str = ""


class UserUpsertRequest(BaseModel):
    username: str
    password: str
    role: str = "viewer"


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class RevokeTokensRequest(BaseModel):
    username: str


class AiConfigRequest(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = "deepseek-chat"
    provider: str = "DeepSeek"


class PushConfigRequest(BaseModel):
    serverchan_key: str = ""
    wecom_webhook: str = ""


class PushTestRequest(BaseModel):
    title: str = "FinQuanta API测试"
    content: str = "这是来自 API 服务的测试消息"


class AssistantAskRequest(BaseModel):
    prompt: str
    session_id: str = ""


class SyncExportRequest(BaseModel):
    keys: list[str] = Field(default_factory=list)
    file_path: str = ""


class SyncImportRequest(BaseModel):
    file_path: str
    overwrite: bool = True
