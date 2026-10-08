"""Canonical user-id matching for cross-surface conversation authorization.

Web company users own records by their raw platform ``userId`` while Android
App company logins own them by ``company:{userId}``; both spellings identify
the same person, so read authorization must accept either.  App-only device
accounts (``app:android:{account_id}``) never merge by name and stay isolated.
"""

COMPANY_PREFIX = "company:"
APP_PREFIX = "app:"


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


def owner_matches(record_owner_user_id: str | None, user_id: str) -> bool:
    """Whether a stored owner_user_id belongs to the given user."""
    owner = (record_owner_user_id or "").strip()
    return owner in canonical_user_ids(user_id)
