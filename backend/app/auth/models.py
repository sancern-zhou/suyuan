"""Normalized authenticated-user contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from .errors import AuthenticationRejected


class CurrentUser(BaseModel):
    """Immutable identity supplied to Suyuan business code."""

    model_config = ConfigDict(frozen=True)

    id: str
    username: str
    display_name: str
    role_codes: tuple[str, ...] = ()
    is_admin: bool = False
    sys_code: str = "SUYUAN"
    auth_source: Literal["company", "mock"] = "company"

    @classmethod
    def from_company_payload(
        cls,
        payload: dict[str, Any],
        *,
        admin_role_codes: set[str],
        sys_code: str,
    ) -> "CurrentUser":
        user_id = str(payload.get("id") or payload.get("userId") or "").strip()
        if not user_id:
            raise AuthenticationRejected("company authentication rejected: missing user id")

        username = str(
            payload.get("userName")
            or payload.get("username")
            or payload.get("account")
            or user_id
        ).strip()
        display_name = str(
            payload.get("name")
            or payload.get("displayName")
            or payload.get("nickName")
            or username
        ).strip()
        role_codes = _role_codes(payload)
        platform_admin = payload.get("admin") is True
        return cls(
            id=user_id,
            username=username,
            display_name=display_name,
            role_codes=role_codes,
            is_admin=platform_admin
            or bool(set(role_codes).intersection(admin_role_codes)),
            sys_code=sys_code,
            auth_source="company",
        )


def _role_codes(payload: dict[str, Any]) -> tuple[str, ...]:
    raw_roles = payload.get("roleCodes")
    if raw_roles is None:
        raw_roles = payload.get("roles")
    if raw_roles is None:
        raw_roles = payload.get("roleList")
    if raw_roles is None:
        raw_roles = payload.get("roleCodeList")
    if not isinstance(raw_roles, (list, tuple, set)):
        return ()

    values: list[str] = []
    for item in raw_roles:
        if isinstance(item, str):
            code = item
        elif isinstance(item, dict):
            code = item.get("code") or item.get("roleCode") or item.get("value") or ""
        else:
            code = ""
        normalized = str(code).strip()
        if normalized and normalized not in values:
            values.append(normalized)
    return tuple(values)
