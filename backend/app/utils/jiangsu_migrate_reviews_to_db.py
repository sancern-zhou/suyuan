"""One-shot migration: existing task-review JSON files into the database.

Usage (from backend/):
    python -m app.utils.migrate_reviews_to_db --env-file .env.jiangsu-ops
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
    from app.services.task_review import _db_save_review, reviews_dir
    from app.utils.path_config import get_data_registry

    print(f"env_file={env_file} data_registry={get_data_registry()}")
    if not DATABASE_URL:
        print("DATABASE_URL is not configured; nothing to migrate.")
        return 1

    paths = sorted(reviews_dir().glob("*.json"))
    migrated = 0
    for path in paths:
        try:
            import json

            record = json.loads(path.read_text(encoding="utf-8"))
            run_db(_db_save_review(record))
            migrated += 1
        except Exception as exc:
            print(f"skip {path.name}: {exc}")
    print(f"task reviews migrated: {migrated}/{len(paths)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
