"""Contracts for authenticated platform-to-WeChat bindings."""

from datetime import datetime

from pydantic import BaseModel


class SocialBindingRecord(BaseModel):
    id: str
    platform_user_id: str
    platform_username: str
    platform_display_name: str
    account_id: str
    ilink_user_id: str
    bot_account: str
    status: str
    bound_at: datetime


class WeixinScanTaskRecord(BaseModel):
    id: str
    account_id: str
    owner_user_id: str
    owner_username: str
    owner_display_name: str
    status: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
