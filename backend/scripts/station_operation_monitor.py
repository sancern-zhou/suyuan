"""CLI for deterministic collectors; relative arguments always use PROJECT_ROOT."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.utils.path_config import resolve_agent_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', default='backend/.env')
    parser.add_argument('--config')
    parser.add_argument('--date')
    parser.add_argument('action', choices=['collect','report'])
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(resolve_agent_path(args.env_file), override=True)
    from app.services.station_operation_monitor.runtime import collect, generate_report, load_config
    config = load_config(args.config)
    try:
        result = collect(config) if args.action == 'collect' else generate_report(config, date=args.date)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get('success') and not result.get('failed_slices') else 1
    except Exception as exc:
        print(json.dumps({'success':False,'error_type':type(exc).__name__},ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
