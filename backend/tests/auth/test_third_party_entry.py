import base64
import hashlib
import hmac
import json
import time

import pytest

from app.auth.third_party_entry import ThirdPartyJwtError, verify_third_party_jwt

SECRET = "2A3D1678-64D2-4527-B3C3-621BB622C0DD"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def build_jwt(secret: str, payload: dict, header: dict | None = None) -> str:
    head = b64url(json.dumps(header or {"alg": "HS256"}, separators=(",", ":")).encode())
    body = b64url(json.dumps(payload, separators=(",", ":")).encode())
    key = base64.b64encode(secret.encode())
    signature = hmac.new(key, f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{b64url(signature)}"


def payload_with(**overrides):
    payload = {
        "jti": "1",
        "sub": "ScGuanLy",
        "iat": 1793701279,
        "exp": 1793701279 + 120,
        "aud": "120000",
        "custom": {"UserName": "超级管理员"},
    }
    payload.update(overrides)
    return payload


def test_valid_jwt_returns_subject():
    token = build_jwt(SECRET, payload_with())
    assert verify_third_party_jwt(token, SECRET, now=1793701279 + 30) == "ScGuanLy"


def test_signature_bound_to_platform_key_derivation():
    token = build_jwt(SECRET, payload_with())
    wrong_secret = "2A3D1678-64D2-4527-B3C3-621BB622C0D0"
    with pytest.raises(ThirdPartyJwtError, match="invalid signature"):
        verify_third_party_jwt(token, wrong_secret, now=1793701279 + 30)


def test_expired_jwt_is_rejected():
    token = build_jwt(SECRET, payload_with(exp=1793701279 + 30))
    with pytest.raises(ThirdPartyJwtError, match="expired"):
        verify_third_party_jwt(token, SECRET, now=1793701279 + 120)


def test_malformed_and_foreign_alg_are_rejected():
    with pytest.raises(ThirdPartyJwtError, match="malformed"):
        verify_third_party_jwt("not-a-jwt", SECRET)
    with pytest.raises(ThirdPartyJwtError, match="unsupported"):
        verify_third_party_jwt(
            build_jwt(SECRET, payload_with(), header={"alg": "none"}), SECRET
        )
    with pytest.raises(ThirdPartyJwtError, match="missing subject"):
        verify_third_party_jwt(build_jwt(SECRET, payload_with(sub="")), SECRET)


def test_key_matches_platform_base64_of_secret_bytes():
    # 平台 JwtUtils: signWith(HS256, Base64.getEncoder().encode(secret.getBytes()))
    assert base64.b64encode(SECRET.encode()) == b'MkEzRDE2NzgtNjREMi00NTI3LUIzQzMtNjIxQkI2MjJDMERE'
