"""One-time import of the smart-event JSON store into the database.

Rebuilds the document-based smart_events / smart_event_tasks /
smart_event_state tables from the legacy manifest and detail packages, then
switches all reads and writes to the database. Evidence package files stay
on disk and are only referenced by path.

Usage (from backend/):
    python -m app.utils.migrate_smart_events_to_db --env-file .env.jiangsu-ops
"""
from __future__ import annotations

import sys


def main() -> int:
    args = [arg for arg in sys.argv[1:] if not arg.startswith("-")]
    env_file = args[0] if args else ".env"

    from dotenv import load_dotenv

    load_dotenv(env_file, override=True)

    from app.db.database import DATABASE_URL
    from app.db.sync_bridge import run_db
    from app.services.smart_event_db import import_store_from_files_async

    if not DATABASE_URL:
        print("DATABASE_URL is not configured; nothing to migrate.")
        return 1
    result = run_db(import_store_from_files_async(), timeout=900)
    print(f"smart events imported: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
