"""Canonical user-id matching for cross-surface conversation authorization.

Web company users own records by their raw platform ``userId`` while Android
App company logins own them by ``company:{userId}``; both spellings identify
the same person, so read authorization must accept either.  App-only device
accounts (``app:android:{account_id}``) stay isolated unless the account
declares an explicit ``bind_user_id`` in ``APP_ACCOUNTS_JSON`` — binding is
never inferred from a matching name.
"""

from functools import lru_cache
import json

from config.settings import settings

COMPANY_PREFIX = "company:"
APP_PREFIX = "app:"
APP_ANDROID_PREFIX = "app:android:"


def canonical_user_ids(raw_user_id: str) -> tuple[str, ...]:
    """Return every owner spelling that identifies the same person."""
    value = (raw_user_id or "").strip()
    if not value:
        return ()
    if value.startswith(APP_PREFIX):
        return (value,)
    if value.startswith(COMPANY_PREFIX):
        stripped = value[len(COMPANY_PREFIX) :].strip()
        return (value, stripped) if stripped else (value,)
    return (value, f"{COMPANY_PREFIX}{value}")


@lru_cache(maxsize=1)
def _app_accounts() -> dict[str, dict]:
    try:
        parsed = json.loads(settings.app_accounts_json or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): value for key, value in parsed.items() if isinstance(value, dict)}


def _bound_company_user_id(account_id: str) -> str:
    bound = str(_app_accounts().get(account_id, {}).get("bind_user_id") or "").strip()
    return bound


def visible_owner_ids(raw_user_id: str) -> tuple[str, ...]:
    """Owner spellings visible to a user, including explicit account bindings."""
    value = (raw_user_id or "").strip()
    if not value:
        return ()
    ids = list(canonical_user_ids(value))
    if value.startswith(APP_ANDROID_PREFIX):
        account_id = value[len(APP_ANDROID_PREFIX) :].strip()
        bound = _bound_company_user_id(account_id)
        if bound:
            ids.extend(canonical_user_ids(bound))
    else:
        company_ids = set(ids)
        for account_id, config in _app_accounts().items():
            bound = str(config.get("bind_user_id") or "").strip()
            if bound and company_ids.intersection(canonical_user_ids(bound)):
                ids.append(f"{APP_ANDROID_PREFIX}{account_id}")
    return tuple(dict.fromkeys(ids))


def owner_matches(record_owner_user_id: str | None, user_id: str) -> bool:
    """Whether a stored owner_user_id belongs to the given user."""
    owner = (record_owner_user_id or "").strip()
    return owner in visible_owner_ids(user_id)
