"""Backfill Scenario-1 episode state into PostgreSQL.

This command only copies the already-aggregated episode state. It never
recomputes alerts and never modifies evidence packages or the JSON state.
"""

from __future__ import annotations

import argparse
import json

from app.scenarios.xuchang_station_deviation.episode_storage_db import upsert_episode
from app.utils.path_config import get_data_registry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    state_path = get_data_registry() / "xuchang_station_deviation_alerts" / "episode_state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"episode state unavailable: {state_path}: {exc}") from exc

    episodes = []
    for bucket in ("active", "history"):
        items = state.get(bucket) or []
        episodes.extend(items.values() if isinstance(items, dict) else items)

    if args.dry_run:
        print(f"would backfill {len(episodes)} episodes from {state_path}")
        return 0

    for episode in episodes:
        upsert_episode(episode)
    print(f"backfilled {len(episodes)} episodes from {state_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
