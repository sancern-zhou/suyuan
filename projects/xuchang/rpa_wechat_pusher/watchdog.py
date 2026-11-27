"""许昌微信群告警推送 agent 看门狗（pythonw 常驻，无窗口）。

每 10 分钟检查一次：
- agent 进程缺失 → pythonw 无窗口拉起（覆盖误关窗口、安全软件杀进程、崩溃）。
- agent 进程在但存活心跳（data/agent_liveness 的 mtime）超过阈值未更新 →
  判定冻结在 UIA/网络调用里，杀掉进程树后重新拉起。2026-11-12 事故教训：
  agent 冻结 36h 期间进程与单实例锁都在，只查进程存在性发现不了。

心跳由 agent.py 每轮轮询、每条消息与每张附图处理前 touch。由登录自启启动。
"""

from __future__ import annotations

import subprocess
import time
from datetime import datetime
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent
LOG_PATH = ROOT / "data" / "watchdog.log"
LIVENESS_PATH = ROOT / "data" / "agent_liveness"
CHECK_INTERVAL_SECONDS = 600
# agent 正常单段操作上限远小于此值（单条文本 3 次重试×75s 内部总时限、
# 单张附图下载 2×30s + 3 次发送重试），心跳 10 分钟未更新必然是冻结而非繁忙
LIVENESS_STALE_SECONDS = 600


def log(message: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}"
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def find_agent_procs() -> list[psutil.Process]:
    procs: list[psutil.Process] = []
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
            procs.append(proc)
    return procs


def agent_running() -> bool:
    return bool(find_agent_procs())


def liveness_stale_seconds() -> float | None:
    """存活心跳的陈旧秒数；文件缺失（旧版 agent 从未写过）返回 None 表示无法判定。"""
    try:
        return max(0.0, time.time() - LIVENESS_PATH.stat().st_mtime)
    except OSError:
        return None


def kill_agent_tree(procs: list[psutil.Process]) -> None:
    # venv 的 pythonw.exe 是 launcher，真实解释器是其子进程且两层命令行相同；
    # 先杀子进程再杀父进程，避免子进程变孤儿继续占单实例锁端口
    for proc in procs:
        try:
            children = proc.children(recursive=True)
        except psutil.Error:
            children = []
        for child in children:
            try:
                child.kill()
            except psutil.Error:
                pass
        try:
            proc.kill()
        except psutil.Error:
            pass


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
        procs = find_agent_procs()
        if not procs:
            try:
                start_agent()
                log("agent 不在运行，已拉起")
            except Exception as exc:
                log(f"拉起失败：{exc}")
        else:
            stale = liveness_stale_seconds()
            if stale is not None and stale > LIVENESS_STALE_SECONDS:
                log(f"agent 进程在但心跳已 {int(stale)}s 未更新，判定冻结，杀进程树后拉起新实例")
                kill_agent_tree(procs)
                time.sleep(5)  # 等单实例锁端口随进程死亡释放
                try:
                    start_agent()
                    log("冻结 agent 已替换为新实例")
                except Exception as exc:
                    log(f"拉起新实例失败：{exc}")
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
