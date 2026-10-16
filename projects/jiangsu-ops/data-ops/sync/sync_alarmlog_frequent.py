# -*- coding: utf-8 -*-
"""告警分片 + 质控三件套 高频批量同步(sync-all.cmd 每 5 分钟调用)。

对 sync_config.json 中 alarmlog_<年>_<站> 与 qc_his_(task_status|run_log|air_data)_result_<年>
条目做增量同步;子进程池并行(每个表一个 sync_table.py 进程,互不影响水位)。
首次运行会自动全量(受初始窗口约束);qc_his_run_log 初始拉取耗时较长,
建议首跑在后台手工执行完成后再接入 5 分钟调度。
"""
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SYNC_DIR = Path(__file__).resolve().parent
MAX_WORKERS = 6
QC_PAT = re.compile(r"^qc_his_(task_status|run_log|air_data)_result_\d{4}$")


def target_tables() -> list[str]:
    cfg = json.loads((SYNC_DIR / "sync_config.json").read_text(encoding="utf-8"))
    tables = [t for t in cfg["tables"] if t.startswith("alarmlog_")]
    tables += [t for t in cfg["tables"] if QC_PAT.match(t)]
    return sorted(tables)


def run_one(table: str):
    proc = subprocess.run(
        [sys.executable, str(SYNC_DIR / "sync_table.py"), table],
        capture_output=True, text=True, cwd=str(SYNC_DIR))
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
    return table, proc.returncode == 0, tail[-1][:240] if tail else ""


def main() -> int:
    tables = target_tables()
    if not tables:
        print("no alarmlog/qc entries in sync_config.json", flush=True)
        return 1
    failed = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for table, ok, tail in pool.map(run_one, tables):
            if not ok:
                failed.append(table)
                print("[FAIL] %s: %s" % (table, tail), flush=True)
    print("alarmlog/qc frequent sync: %d ok, %d failed" % (len(tables) - len(failed), len(failed)), flush=True)
    return 1 if len(failed) > len(tables) // 2 else (1 if failed else 0)


if __name__ == "__main__":
    sys.exit(main())
