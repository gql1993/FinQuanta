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
    boards: list[str] = Field(default_factory=list)


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


class PushConfigRequest(BaseModel):
    serverchan_key: str = ""
    wecom_webhook: str = ""


class PushTestRequest(BaseModel):
    title: str = "FinQuanta API测试"
    content: str = "这是来自 API 服务的测试消息"


class AssistantAskRequest(BaseModel):
    prompt: str
    session_id: str = ""
