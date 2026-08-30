"""Authenticated identity envelope for trusted internal HTTP hops."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac

from pydantic import ValidationError

from .models import CurrentUser


INTERNAL_USER_HEADER = "x-suyuan-current-user"
_MAX_ENVELOPE_LENGTH = 8192


def _sign(encoded: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def encode_internal_user(user: CurrentUser, *, secret: str = "") -> str:
    payload = user.model_dump_json().encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii")
    if not secret:
        return encoded
    return f"{encoded}.{_sign(encoded, secret)}"


def decode_internal_user(envelope: str, *, secret: str = "") -> CurrentUser:
    if not envelope or len(envelope) > _MAX_ENVELOPE_LENGTH:
        raise ValueError("invalid_internal_user_envelope")
    encoded, separator, supplied_mac = envelope.partition(".")
    if separator:
        if not secret:
            raise ValueError("invalid_internal_user_envelope")
        if not hmac.compare_digest(_sign(encoded, secret), supplied_mac):
            raise ValueError("invalid_internal_user_envelope")
    elif secret:
        raise ValueError("invalid_internal_user_envelope")
    try:
        payload = base64.b64decode(
            encoded.encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
        return CurrentUser.model_validate_json(payload)
    except (UnicodeEncodeError, binascii.Error, ValidationError, ValueError) as exc:
        raise ValueError("invalid_internal_user_envelope") from exc
