"""Roster-based access policy for operation-mode sign-ins.

The ops-platform SQL Server (SYS_USER / SYS_DEPARTMENT / SYS_ROLETYPE) is the
authority on which account belongs to which unit.  This policy keeps a local
snapshot of that roster so every request — including ones carried by the
agent-issued session token that outlives the ops Forms cookie — is decided
against data at most one sync interval stale, without a synchronous
dependency on the ops SQL Server on the request path.

Decision model (whitelist): only bureau-side accounts (configurable
USERTYPE values, default 1=省中心 and 5=市级) plus explicitly whitelisted
usernames and the configured agent admins may sign in; every other account —
including accounts unknown to the roster — is denied once a roster has been
loaded at least once.  Before the first successful roster load the policy
fails open with a warning so a transient ops-DB outage cannot lock out the
whole deployment.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import structlog

from config.settings import Settings


_ROSTER_SQL = """
SELECT u.USERID, u.LOGINID, u.USERNAME, u.USERTYPE, u.STATUS, u.DATASTATE,
       d.DEPARTMENTNAME AS DEPARTMENT, mu.DEPARTMENTNAME AS MAINTENANCE_UNIT,
       STUFF((SELECT ',' + rt.ROLETYPENAME
              FROM SYS_USERROLE ur
              JOIN SYS_ROLE ro ON ur.ROLEID = ro.ROLEID
              JOIN SYS_ROLETYPE rt ON ro.ROLETYPEID = rt.ROLETYPEID
              WHERE ur.USERID = u.USERID
              FOR XML PATH('')), 1, 1, '') AS ROLE_NAMES
FROM SYS_USER u
LEFT JOIN SYS_DEPARTMENT d ON u.DEPARTMENTID = d.DEPARTMENTID
LEFT JOIN SYS_DEPARTMENT mu ON u.MAINTENANCEUNITID = mu.DEPARTMENTID
"""

_SNAPSHOT_VERSION = 1


@dataclass(frozen=True)
class RosterEntry:
    login_id: str
    display_name: str
    usertype: str
    status: str
    department: str
    maintenance_unit: str
    roles: str
    decision: str  # "allowed" | "blocked"
    reason: str
    data_state: str = ""


def _key(value: Any) -> str:
    return str(value or "").strip().lower()


class OperationAccessPolicy:
    """Decide per-request whether an ops-platform username may sign in."""

    def __init__(
        self,
        *,
        settings: Settings,
        snapshot_path: Path | None = None,
        fetch_roster: Callable[[], list[dict[str, Any]]] | None = None,
        logger: Any | None = None,
    ) -> None:
        self._settings = settings
        self._snapshot_path = snapshot_path
        self._fetch_roster = fetch_roster
        self._logger = logger or structlog.get_logger(__name__)
        self._static_allowed = {
            _key(name)
            for name in (
                settings.auth_operation_admin_usernames_set
                | settings.auth_operation_allowed_usernames_set
            )
        }
        self._static_blocked = {
            _key(name) for name in settings.auth_operation_blocked_usernames_set
        }
        self._allowed_usertypes = settings.auth_operation_allowed_usertypes_set
        self._entries: dict[str, RosterEntry] = {}
        # A roster has been loaded from the ops DB or a snapshot at least once;
        # unknown usernames are only denied after this flag is set.
        self._roster_loaded = False
        self._synced_at: str | None = None
        self._last_error: str | None = None
        self._load_snapshot()

    # ------------------------------------------------------------------
    # Decision (request path, in-memory only)

    def decide(self, username: str) -> tuple[bool, str]:
        """Return (allowed, reason) for an ops-platform username."""
        key = _key(username)
        if not key:
            return False, "empty_username"
        if key in self._static_blocked:
            return False, "blocked_list"
        if key in self._static_allowed:
            return True, "static_whitelist"
        entry = self._entries.get(key)
        if entry is not None:
            return entry.decision == "allowed", entry.reason
        if self._roster_loaded:
            return False, "unknown_user"
        return True, "roster_unavailable"

    def summary(self) -> dict[str, Any]:
        unique = self._unique_entries()
        counts = {"allowed": 0, "blocked": 0}
        for entry in unique.values():
            counts[entry.decision] = counts.get(entry.decision, 0) + 1
        return {
            "enabled": self._settings.auth_operation_access_control_enabled,
            "roster_loaded": self._roster_loaded,
            "synced_at": self._synced_at,
            "last_error": self._last_error,
            "allowed_usertypes": sorted(self._allowed_usertypes),
            "static_whitelist": sorted(self._static_allowed),
            "blocked_list": sorted(self._static_blocked),
            "counts": {"total": len(unique), **counts},
            "entries": [asdict(entry) for entry in unique.values()],
        }

    # ------------------------------------------------------------------
    # Roster refresh

    def apply_roster(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        allowed_usertypes = self._allowed_usertypes
        entries: dict[str, RosterEntry] = {}
        allowed = blocked = 0

        def _priority(row: dict[str, Any]) -> tuple:
            # Duplicate login ids exist in SYS_USER (superseded/soft-deleted
            # rows share the login with the live record).  The live record —
            # DATASTATE=1, then Enabled — is the one the ops platform
            # authenticates, so it must win; bureau type only breaks ties.
            return (
                0 if str(row.get("DATASTATE") or "").strip() == "1" else 1,
                0 if str(row.get("STATUS") or "").strip() == "Enabled" else 1,
                0
                if str(row.get("USERTYPE") or "").strip() in allowed_usertypes
                else 1,
                str(row.get("USERID") or ""),
            )

        for row in sorted(rows, key=_priority):
            login_id = str(row.get("LOGINID") or "").strip()
            key = _key(login_id)
            if not key or key in entries:
                continue
            usertype = str(row.get("USERTYPE") or "").strip()
            if usertype in allowed_usertypes:
                decision, reason = "allowed", "bureau_usertype"
            else:
                decision, reason = "blocked", "external_usertype"
            entry = RosterEntry(
                login_id=login_id,
                display_name=str(row.get("USERNAME") or "").strip(),
                usertype=usertype,
                status=str(row.get("STATUS") or "").strip(),
                department=str(row.get("DEPARTMENT") or "").strip(),
                maintenance_unit=str(row.get("MAINTENANCE_UNIT") or "").strip(),
                roles=str(row.get("ROLE_NAMES") or "").strip(),
                decision=decision,
                reason=reason,
                data_state=str(row.get("DATASTATE") or "").strip(),
            )
            entries[key] = entry
            if decision == "allowed":
                allowed += 1
            else:
                blocked += 1
        # Display-name aliases are added only after every login id is indexed:
        # a display name that collides with another account's login id (e.g.
        # an ops account named "陈梓杰" vs the bureau login id "陈梓杰") must
        # never shadow that real account.
        for entry in list(entries.values()):
            display_key = _key(entry.display_name)
            if display_key and display_key not in entries:
                entries[display_key] = entry
        self._entries = entries
        self._roster_loaded = True
        self._synced_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._last_error = None
        self._persist_snapshot()
        self._logger.info(
            "operation_access_roster_applied",
            total=allowed + blocked,
            allowed=allowed,
            blocked=blocked,
            allowed_usertypes=sorted(allowed_usertypes),
        )
        return {"total": allowed + blocked, "allowed": allowed, "blocked": blocked}

    async def refresh(self) -> bool:
        """Pull the roster from the ops SQL Server; keep the snapshot on failure."""
        try:
            if self._fetch_roster is None:
                rows = await asyncio.to_thread(self._fetch_roster_from_db)
            else:
                rows = self._fetch_roster()
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._logger.warning(
                "operation_access_roster_refresh_failed",
                error_type=type(exc).__name__,
            )
            return False
        self.apply_roster(rows)
        return True

    def _fetch_roster_from_db(self) -> list[dict[str, Any]]:
        if not self._settings.ops_sqlserver_configured:
            raise RuntimeError("OPS_SQLSERVER_HOST is not configured")
        import pyodbc

        connection = pyodbc.connect(
            self._settings.ops_sqlserver_connection_string, timeout=30
        )
        try:
            cursor = connection.cursor()
            cursor.execute(_ROSTER_SQL)
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            connection.close()

    # ------------------------------------------------------------------
    # Snapshot persistence

    def _snapshot_file(self) -> Path | None:
        if self._snapshot_path is not None:
            return self._snapshot_path
        try:
            from app.utils.path_config import get_data_registry

            return get_data_registry() / "operation_access" / "roster.json"
        except Exception:
            return None

    def _unique_entries(self) -> dict[str, RosterEntry]:
        unique: dict[str, RosterEntry] = {}
        for entry in self._entries.values():
            key = _key(entry.login_id)
            if key:
                unique[key] = entry
        return unique

    def _load_snapshot(self) -> None:
        path = self._snapshot_file()
        if path is None:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            rows = [
                item
                for item in payload.get("entries", [])
                if isinstance(item, dict)
            ]
        except FileNotFoundError:
            return
        except (OSError, ValueError, TypeError) as exc:
            self._logger.warning(
                "operation_access_snapshot_invalid",
                error_type=type(exc).__name__,
            )
            return
        self._entries = {}
        for item in rows:
            try:
                entry = RosterEntry(**item)
            except TypeError:
                continue
            key = _key(entry.login_id)
            if key:
                self._entries[key] = entry
        for entry in list(self._entries.values()):
            display_key = _key(entry.display_name)
            if display_key and display_key not in self._entries:
                self._entries[display_key] = entry
        self._roster_loaded = bool(self._entries)
        self._synced_at = payload.get("synced_at")

    def _persist_snapshot(self) -> None:
        path = self._snapshot_file()
        if path is None:
            return
        payload = {
            "version": _SNAPSHOT_VERSION,
            "synced_at": self._synced_at,
            "entries": [
                asdict(entry) for entry in self._unique_entries().values()
            ],
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
        except OSError as exc:
            self._logger.warning(
                "operation_access_snapshot_write_failed",
                error_type=type(exc).__name__,
            )

    # ------------------------------------------------------------------
    # Background loop

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        interval = self._settings.auth_operation_access_sync_interval_seconds
        while not stop_event.is_set():
            await self.refresh()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except TimeoutError:
                continue
