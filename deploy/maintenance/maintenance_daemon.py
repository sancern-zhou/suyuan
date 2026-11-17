#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""suyuan 维护守护进程（宿主机侧）：受控的服务重启 / git 快照 / 回滚。

定位（分级自治的外部执行臂）：
- 后端容器内的修复 Agent 无 docker.sock、无进程管理器，既不能重启 web/worker，
  更不能重启自己；本守护进程跑在宿主机上，故障域与被控对象隔离——后端整体
  挂掉时它仍能拉起服务。
- 它只做确定性动作（restart/snapshot/rollback），不做任何判断；"是否该重启"
  的 P0 判级在应用侧由 severity 规则决定，本进程只校验 token 与自身缰绳。

安全模型：
- 仅监听 127.0.0.1；请求必须携带共享 token（x-maintenance-token）；
- 重启缰绳（本进程侧再兜底一道，与应用侧独立）：同一 service 10 分钟冷却、
  每日最多 5 次；超限拒绝并返回原因；
- /restart 携带 snapshot_id 时：重启 → 等待健康 → 不健康则自动回滚该快照
  并再重启一次（自动回滚失败才需要人工介入）；
- git 快照用 `git stash create`（不污染工作区）+ 保存基线；回滚用 checkout。

用法（本机 Windows / 服务器 Linux 通用，仅标准库）：
    python maintenance_daemon.py --env-file maintenance.env
    python maintenance_daemon.py --env-file maintenance.env --test-restart web
"""
from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_PORT = 8013
RESTART_COOLDOWN_SECONDS = 600
RESTART_DAILY_LIMIT = 5
HEALTH_WAIT_SECONDS = 240
HEALTH_INTERVAL_SECONDS = 5

_state: dict = {"restarts": {}, "snapshots": {}}
_state_path: Path | None = None


def _load_state(path: Path) -> None:
    """缰绳状态落盘读取：进程重启不重置冷却/日限（否则重启守护进程即可绕过）。"""
    global _state, _state_path
    _state_path = path
    try:
        if path.is_file():
            _state.update(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        pass


def _save_state() -> None:
    if _state_path is None:
        return
    try:
        tmp = _state_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(_state, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(_state_path)
    except OSError:
        pass


def log(message: str) -> None:
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {message}", file=sys.stderr)


def load_env_file(path: Path) -> dict:
    env = {}
    if not path.is_file():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def run_cmd(args, cwd: Path | None = None, timeout: int = 120):
    proc = subprocess.run(
        args, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed ({' '.join(map(str, args))}): {proc.stderr.strip()[:300]}"
        )
    return proc.stdout.strip()


class Maintenance:
    def __init__(self, env: dict):
        self.token = env.get("MAINTENANCE_TOKEN", "")
        self.repo_root = Path(env.get("MAINTENANCE_REPO_ROOT", ".")).resolve()
        # 本地 Docker 部署：docker compose -p <proj> -f <file> restart <svc>
        self.compose_project = env.get("MAINTENANCE_COMPOSE_PROJECT", "")
        self.compose_file = env.get("MAINTENANCE_COMPOSE_FILE", "")
        # 服务器原生部署（可选）：交给重启脚本，忽略 service 粒度
        self.restart_command = env.get("MAINTENANCE_RESTART_COMMAND", "")
        # 健康探针 URL：service 名 → URL（键名大小写不敏感）
        self.health_urls = {
            k[len("MAINTENANCE_HEALTH_"):].lower(): v
            for k, v in env.items()
            if k.upper().startswith("MAINTENANCE_HEALTH_")
        }
        if not self.token:
            raise SystemExit("MAINTENANCE_TOKEN 未配置，守护进程拒绝启动（不设防=裸授权）")

    # ---- 基础动作 ----
    def restart(self, service: str) -> dict:
        if self.restart_command:
            run_cmd(self.restart_command.split(), cwd=self.repo_root, timeout=300)
            return {"executed": self.restart_command}
        if not (self.compose_project and self.compose_file):
            raise RuntimeError("未配置 MAINTENANCE_RESTART_COMMAND 或 compose 参数")
        args = [
            "docker", "compose", "-p", self.compose_project,
            "-f", str(self.compose_file), "restart", service,
        ]
        run_cmd(args, cwd=self.repo_root, timeout=300)
        return {"executed": " ".join(args)}

    def probe(self, url: str, timeout: int = 8) -> bool:
        try:
            request = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return 200 <= response.status < 300
        except Exception:
            return False

    def wait_healthy(self, service: str) -> bool:
        url = self.health_urls.get(service)
        if not url:
            log(f"service {service} 无健康探针配置，跳过等待")
            return True
        deadline = time.time() + HEALTH_WAIT_SECONDS
        while time.time() < deadline:
            if self.probe(url):
                return True
            time.sleep(HEALTH_INTERVAL_SECONDS)
        return False

    # ---- git 快照 / 回滚 ----
    def snapshot(self, label: str = "") -> dict:
        run_cmd(["git", "rev-parse", "HEAD"], cwd=self.repo_root)
        # stash create 不改工作区，返回一个提交对象；无改动时返回空
        stash = run_cmd(["git", "stash", "create"], cwd=self.repo_root)
        head = run_cmd(["git", "rev-parse", "HEAD"], cwd=self.repo_root)
        snapshot_id = secrets.token_hex(6)
        _state["snapshots"][snapshot_id] = {
            "head": head,
            "stash": stash,
            "label": label,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        _save_state()
        return {"snapshot_id": snapshot_id, "head": head[:12], "stash": stash[:12] or None}

    def rollback(self, snapshot_id: str) -> dict:
        snap = _state["snapshots"].get(snapshot_id)
        if not snap:
            raise RuntimeError(f"快照不存在或已过期: {snapshot_id}")
        # 精确恢复：先回到 head（清掉快照后的所有工作区改动），再重放 stash 基线
        run_cmd(["git", "checkout", "--", "."], cwd=self.repo_root)
        if snap["stash"]:
            run_cmd(["git", "checkout", snap["stash"], "--", "."], cwd=self.repo_root)
        return {"rolled_back_to": snap["head"][:12], "label": snap.get("label", "")}

    # ---- 缰绳 ----
    def check_restart_reins(self, service: str) -> str | None:
        now = time.time()
        day = datetime.now().strftime("%Y%m%d")
        last = _state["restarts"].get(f"{service}:last_at", 0)
        if now - last < RESTART_COOLDOWN_SECONDS:
            wait = int((RESTART_COOLDOWN_SECONDS - (now - last)) / 60) + 1
            return f"{service} 处于重启冷却期（约 {wait} 分钟后可再次执行）"
        day_key = f"{service}:{day}"
        used = _state["restarts"].get(day_key, 0)
        if used >= RESTART_DAILY_LIMIT:
            return f"{service} 今日重启已达上限（{RESTART_DAILY_LIMIT} 次），需人工介入"
        return None

    def record_restart(self, service: str) -> None:
        now = time.time()
        day = datetime.now().strftime("%Y%m%d")
        _state["restarts"][f"{service}:last_at"] = now
        _state["restarts"][f"{service}:{day}"] = (
            _state["restarts"].get(f"{service}:{day}", 0) + 1
        )
        _save_state()

    # ---- 组合动作 ----
    def restart_with_verify(self, service: str, snapshot_id: str | None) -> dict:
        self.restart(service)
        healthy = self.wait_healthy(service)
        result = {"service": service, "healthy": healthy, "rolled_back": False}
        if not healthy and snapshot_id:
            log(f"restart_unhealthy_rolling_back service={service} snapshot={snapshot_id}")
            self.rollback(snapshot_id)
            self.restart(service)
            result["healthy"] = self.wait_healthy(service)
            result["rolled_back"] = True
        return result


class Handler(BaseHTTPRequestHandler):
    daemon: Maintenance | None = None

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        expected = self.daemon.token
        got = self.headers.get("x-maintenance-token", "")
        return bool(expected) and secrets.compare_digest(expected, got)

    def log_message(self, *args) -> None:  # 静默访问日志
        pass

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"status": "ok"})
            return
        if not self._authorized():
            self._send(403, {"error": "forbidden"})
            return
        if self.path == "/status":
            self._send(200, {
                "health": {svc: self.daemon.probe(url) for svc, url in self.daemon.health_urls.items()},
                "restarts": _state["restarts"],
            })
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self._authorized():
            self._send(403, {"error": "forbidden"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(length) or b"{}"
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except UnicodeDecodeError:
                # Windows 客户端 shell 可能按 GBK 发送中文；宽松回退而不是断连。
                payload = json.loads(raw_body.decode("gbk", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(400, {"error": "bad json"})
            return

        try:
            if self.path == "/snapshot":
                result = self.daemon.snapshot(label=str(payload.get("label", "")))
                self._send(200, {"success": True, **result})
                return
            if self.path == "/rollback":
                result = self.daemon.rollback(str(payload.get("snapshot_id", "")))
                log(f"rolled_back {result}")
                self._send(200, {"success": True, **result})
                return
            if self.path == "/restart":
                service = str(payload.get("service", "")).strip().lower()
                if service not in {"web", "worker", "all"}:
                    self._send(400, {"error": "service 必须是 web/worker/all"})
                    return
                reason = self.daemon.check_restart_reins(service)
                if reason:
                    self._send(429, {"success": False, "error": reason})
                    return
                self.daemon.record_restart(service)
                targets = ["web", "worker"] if service == "all" else [service]
                results = []
                for target in targets:
                    results.append(
                        self.daemon.restart_with_verify(
                            target, payload.get("snapshot_id")
                        )
                    )
                log(f"restart_done service={service} results={results}")
                self._send(200, {"success": True, "results": results})
                return
            self._send(404, {"error": "not found"})
        except Exception as exc:  # noqa: BLE001
            log(f"action_failed path={self.path} error={exc}")
            self._send(500, {"success": False, "error": str(exc)[:300]})


def main() -> int:
    parser = argparse.ArgumentParser(description="suyuan 维护守护进程")
    parser.add_argument("--env-file", default=str(Path(__file__).with_name("maintenance.env")))
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument(
        "--test-restart", choices=["web", "worker"],
        help="自检模式：直接执行一次重启并验证健康（绕过 HTTP，用于部署时验证）",
    )
    args = parser.parse_args()

    env = load_env_file(Path(args.env_file))
    daemon = Maintenance(env)
    Handler.daemon = daemon
    state_file = env.get("MAINTENANCE_STATE_FILE") or str(
        Path(args.env_file).with_name("maintenance_state.json")
    )
    _load_state(Path(state_file))

    if args.test_restart:
        reason = daemon.check_restart_reins(args.test_restart)
        if reason:
            print(f"REIN_BLOCKED {reason}")
            return 1
        result = daemon.restart_with_verify(args.test_restart, None)
        print(f"TEST_RESULT {json.dumps(result, ensure_ascii=False)}")
        return 0 if result.get("healthy") else 2

    port = args.port or int(env.get("MAINTENANCE_PORT", DEFAULT_PORT))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    log(f"maintenance_daemon_started port={port} repo={daemon.repo_root}")
    log(
        f"restart_mode={'script' if daemon.restart_command else 'compose'} "
        f"health_probes={list(daemon.health_urls)}"
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
