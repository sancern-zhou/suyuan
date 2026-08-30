"""IDBase OAuth/OIDC code exchange for the Android App.

The company identity provider authenticates the person.  The configured
``authenticationMore`` endpoint then resolves that IDBase identity to the
local business account used by the existing Web application.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException

from app.social.app_identity import AppIdentity
from config.settings import settings


class CompanyOAuthError(RuntimeError):
    pass


def authorization_config() -> dict[str, Any]:
    return {
        "issuer": settings.company_oidc_issuer,
        "authorization_endpoint": settings.company_oidc_authorization_endpoint,
        "token_endpoint": settings.company_oidc_token_endpoint,
        "client_id": settings.company_oidc_client_id,
        "redirect_uri": settings.company_oidc_redirect_uri,
        "scopes": settings.company_oidc_scopes_list,
        "code_challenge_method": "S256",
    }


async def exchange_code(*, code: str, code_verifier: str, redirect_uri: str | None = None) -> AppIdentity:
    if not settings.company_oidc_client_id or not settings.company_oidc_token_endpoint:
        raise HTTPException(status_code=503, detail="company_oidc_not_configured")
    if not code.strip() or not code_verifier.strip():
        raise HTTPException(status_code=400, detail="invalid_oidc_exchange_request")

    configured_redirect_uri = settings.company_oidc_redirect_uri.strip()
    requested_redirect_uri = (redirect_uri or configured_redirect_uri).strip()
    if not configured_redirect_uri or requested_redirect_uri != configured_redirect_uri:
        raise HTTPException(status_code=400, detail="invalid_oidc_redirect_uri")
    form = {
        "grant_type": "authorization_code",
        "code": code.strip(),
        "client_id": settings.company_oidc_client_id,
        "redirect_uri": requested_redirect_uri,
        "code_verifier": code_verifier.strip(),
    }
    try:
        async with httpx.AsyncClient(timeout=settings.company_oidc_timeout_seconds) as client:
            response = await client.post(settings.company_oidc_token_endpoint, data=form)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="company_oidc_unavailable") from exc
    if response.status_code >= 500:
        raise HTTPException(status_code=503, detail="company_oidc_unavailable")
    try:
        token_body = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="company_oidc_invalid_response") from exc
    if response.status_code >= 400 or token_body.get("error"):
        raise HTTPException(status_code=401, detail="company_oidc_exchange_rejected")

    id_token = str(token_body.get("id_token") or "").strip()
    if not id_token:
        raise HTTPException(status_code=401, detail="company_oidc_missing_id_token")
    return await resolve_business_identity(id_token)


async def resolve_business_identity(id_token: str) -> AppIdentity:
    endpoint = settings.company_authentication_more_url.strip()
    if not endpoint:
        raise HTTPException(status_code=503, detail="company_authentication_more_not_configured")
    try:
        async with httpx.AsyncClient(timeout=settings.company_oidc_timeout_seconds) as client:
            response = await client.post(
                endpoint,
                json={},
                headers={
                    "Authorization": f"Bearer {id_token}",
                    "SysCode": settings.auth_platform_sys_code,
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="company_authentication_more_unavailable") from exc
    if response.status_code >= 500:
        raise HTTPException(status_code=503, detail="company_authentication_more_unavailable")
    try:
        body = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="company_authentication_more_invalid_response") from exc
    if response.status_code >= 400 or body.get("success") is False:
        raise HTTPException(status_code=401, detail="company_authentication_more_rejected")
    rows = body.get("result")
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=401, detail="company_account_not_bound")
    if len(rows) != 1:
        raise HTTPException(status_code=409, detail="company_account_selection_required")
    row = rows[0] if isinstance(rows[0], dict) else {}
    user_id = str(row.get("userId") or row.get("id") or "").strip()
    username = str(row.get("userName") or row.get("username") or user_id).strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="company_account_missing_user_id")
    display_name = str(row.get("name") or row.get("displayName") or username).strip()
    sys_code = str(row.get("sysCode") or settings.auth_sys_code).strip()
    raw_roles = row.get("roleCodes") or row.get("roles") or row.get("roleList") or row.get("roleCodeList")
    role_codes: list[str] = []
    if isinstance(raw_roles, (list, tuple, set)):
        for role in raw_roles:
            code = role if isinstance(role, str) else role.get("code") if isinstance(role, dict) else ""
            code = str(code or "").strip()
            if code and code not in role_codes:
                role_codes.append(code)
    return AppIdentity(
        account_id=user_id,
        display_name=display_name,
        social_user_id=f"company:{user_id}",
        expires_at=0,
        auth_source="company",
        username=username,
        sys_code=sys_code,
        role_codes=tuple(role_codes),
    )
