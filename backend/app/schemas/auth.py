from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    code: str = Field(min_length=1, description="wx.login() 拿到的 code（DEV 模式下用 dev_ 开头）")


class UserPublic(BaseModel):
    id: int
    nickname: str
    avatar_url: str | None = None
    is_member: bool = False


class LoginResponse(BaseModel):
    token: str
    user: UserPublic
