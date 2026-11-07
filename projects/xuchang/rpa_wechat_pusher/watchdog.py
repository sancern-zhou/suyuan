"""许昌微信群告警推送 agent 看门狗（pythonw 常驻，无窗口）。

每 10 分钟检查 agent.py 是否在运行（覆盖用户误关窗口、安全软件杀进程、
偶发崩溃等场景），缺失则用 pythonw 无窗口拉起。由登录自启启动。
"""

from __future__ import annotations

import subprocess
import time
from datetime import datetime
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent
LOG_PATH = ROOT / "data" / "watchdog.log"
CHECK_INTERVAL_SECONDS = 600


def log(message: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}"
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def agent_running() -> bool:
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (proc.info["name"] or "").lower()
            cmdline = " ".join(proc.info["cmdline"] or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if (
            name in {"python.exe", "pythonw.exe"}
            and "agent.py" in cmdline
            and "rpa_wechat_pusher" in cmdline
        ):
            return True
    return False


def start_agent() -> None:
    pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    subprocess.Popen(
        [str(pythonw), "agent.py"],
        cwd=str(ROOT),
        creationflags=0x00000008 | 0x08000000,  # DETACHED_PROCESS | CREATE_NO_WINDOW
    )


def main() -> None:
    log("看门狗启动")
    # 启动延迟：避开与应用自身启动的竞争（避免刚拉起又重复拉起）
    time.sleep(30)
    while True:
        if not agent_running():
            try:
                start_agent()
                log("agent 不在运行，已拉起")
            except Exception as exc:
                log(f"拉起失败：{exc}")
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
