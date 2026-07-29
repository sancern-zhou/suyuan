"""Authenticated identity envelope for trusted internal HTTP hops."""

from __future__ import annotations

import base64
import binascii

from pydantic import ValidationError

from .models import CurrentUser


INTERNAL_USER_HEADER = "x-suyuan-current-user"
_MAX_ENVELOPE_LENGTH = 8192


def encode_internal_user(user: CurrentUser) -> str:
    payload = user.model_dump_json().encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decode_internal_user(envelope: str) -> CurrentUser:
    if not envelope or len(envelope) > _MAX_ENVELOPE_LENGTH:
        raise ValueError("invalid_internal_user_envelope")
    try:
        payload = base64.b64decode(
            envelope.encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
        return CurrentUser.model_validate_json(payload)
    except (UnicodeEncodeError, binascii.Error, ValidationError, ValueError) as exc:
        raise ValueError("invalid_internal_user_envelope") from exc
