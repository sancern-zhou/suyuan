#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""suyuan L0 存活探针：宿主机外部控制回路，不依赖被监控的后端进程。

定位与边界（见 deploy/monitoring/README.md）：
- 只回答"进程还活着吗"：web/worker/嵌入服务的 /health 是否可达。
- 不做语义分析、不调用 LLM——后端整体挂掉或 LLM 全链失败时，应用内的
  Watchdog 定时任务会静默失效，本探针是那个时刻唯一还能报信的通道。
- 告警走带外 webhook（企业微信/飞书/钉钉/通用），不经过 suyuan 后端，
  因此后端死亡不会带走报信能力。

仅用 Python 标准库（urllib），无任何 pip 依赖；systemd timer 或 cron
每分钟驱动一次。状态文件记录每个目标的上/下线状态：
- up -> down   立即告警
- down -> down 冷却后重报（默认 6 小时，防轰炸）
- down -> up   发送恢复通知（含宕机时长）

用法：
    l0_probe.py --env-file /opt/suyuan-monitor/l0_probe.env   # 常规探测
    l0_probe.py --env-file ... --test                          # 发测试消息
    l0_probe.py --env-file ... --status                        # 只探测打印，不动状态不告警
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 5
DEFAULT_ALERT_REPEAT_MINUTES = 360
DEFAULT_STATE_FILE = "/var/lib/suyuan-l0-probe/state.json"


def log(message: str) -> None:
    """stderr 输出进 systemd journal / cron 邮件，stdout 保持干净。"""
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {message}", file=sys.stderr)


def load_env_file(path: Path) -> dict:
    """极简 KEY=VALUE 解析（无 python-dotenv 依赖），已导出的环境变量优先。"""
    env = {}
    if not path.is_file():
        return env
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        env[key.strip()] = value
    return env


def parse_targets(spec: str) -> list[tuple[str, str]]:
    """解析 "name|url,name|url,..." 列表。"""
    targets = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk or "|" not in chunk:
            continue
        name, _, url = chunk.partition("|")
        targets.append((name.strip(), url.strip()))
    if not targets:
        raise SystemExit("L0_TARGETS 为空或格式错误，示例：main-web|http://127.0.0.1:8000/health")
    return targets


def probe(url: str, timeout: float) -> tuple[bool, str]:
    """GET 探测，2xx 视为存活；返回 (alive, 失败原因)。"""
    try:
        request = urllib.request.Request(url, method="GET", headers={"User-Agent": "suyuan-l0-probe/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if 200 <= response.status < 300:
                return True, ""
            return False, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as exc:
        reason = getattr(exc, "reason", None) or exc
        return False, str(reason)[:120]


def send_webhook(url: str, channel: str, text: str, timeout: float) -> None:
    """按通道预设投递文本消息；发送失败只记日志，绝不中断探测循环。"""
    if channel == "wecom":
        payload = {"msgtype": "text", "text": {"content": text}}
    elif channel == "feishu":
        payload = {"msg_type": "text", "content": {"text": text}}
    elif channel == "dingtalk":
        payload = {"msgtype": "text", "text": {"content": text}}
    else:
        payload = {"title": "suyuan-l0", "text": text}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if not 200 <= response.status < 300:
                log(f"webhook 响应异常 HTTP {response.status}（channel={channel}）")
    except Exception as exc:  # noqa: BLE001 - 告警失败不影响探测
        log(f"webhook 发送失败（channel={channel}）：{exc}")


def human_duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} 分钟"
    hours, rem = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} 小时 {rem} 分"
    return f"{hours // 24} 天 {hours % 24} 小时"


def main() -> int:
    parser = argparse.ArgumentParser(description="suyuan L0 存活探针")
    parser.add_argument("--env-file", default=str(Path(__file__).with_name("l0_probe.env")))
    parser.add_argument("--test", action="store_true", help="只发一条测试消息，不探测")
    parser.add_argument("--status", action="store_true", help="只探测并打印，不更新状态、不告警")
    args = parser.parse_args()

    file_env = load_env_file(Path(args.env_file))
    config = {**file_env, **{k: v for k, v in os.environ.items() if k.startswith("L0_")}}

    webhook_url = config.get("L0_WEBHOOK_URL", "").strip()
    channel = config.get("L0_WEBHOOK_CHANNEL", "generic").strip().lower()
    timeout = float(config.get("L0_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    repeat_seconds = int(float(config.get("L0_ALERT_REPEAT_MINUTES", DEFAULT_ALERT_REPEAT_MINUTES)) * 60)
    hostname = socket.gethostname()
    now = time.time()
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if args.test:
        if not webhook_url:
            raise SystemExit("L0_WEBHOOK_URL 未配置，无法发送测试消息")
        send_webhook(webhook_url, channel, f"[suyuan-L0] 测试消息：探针配置正常（host={hostname}）", timeout)
        log("测试消息已发送")
        return 0

    targets = parse_targets(config.get("L0_TARGETS", ""))
    state_path = Path(config.get("L0_STATE_FILE", DEFAULT_STATE_FILE))

    state = {}
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log(f"状态文件损坏，重建（{exc}）")
            state = {}

    any_down = False
    alert_texts = []
    for name, url in targets:
        alive, reason = probe(url, timeout)
        entry = state.get(name) or {}
        was_down = entry.get("status") == "down"

        if args.status:
            print(f"{'UP  ' if alive else 'DOWN'} {name} {url}" + (f"  ({reason})" if not alive else ""))
            any_down = any_down or not alive
            continue

        if alive and was_down:
            down_since = entry.get("down_since")
            duration = (
                f"，宕机时长 {human_duration(now - float(down_since))}" if down_since else ""
            )
            alert_texts.append(f"[suyuan-L0] {hostname} {name} 已恢复{duration}（{now_text}）")
            entry = {"status": "up", "since": now}
        elif alive:
            # 首次上线或持续在线：静默（首轮部署不产生任何通知）
            entry = {"status": "up", "since": entry.get("since", now)}
        elif was_down:
            entry["status"] = "down"
            if now - float(entry.get("last_alert_at", 0)) >= repeat_seconds:
                alert_texts.append(
                    f"[suyuan-L0] {hostname} {name} 仍宕机：{reason}（{now_text}，持续 "
                    f"{human_duration(now - float(entry.get('down_since', now)))}）"
                )
                entry["last_alert_at"] = now
        else:
            # 由在线转宕机，或首轮部署即宕机：立即告警
            alert_texts.append(
                f"[suyuan-L0] {hostname} {name} 宕机：{reason}（{now_text}）\n"
                f"请登录服务器检查进程（restart_server.sh / PID 文件）。"
            )
            entry = {"status": "down", "down_since": now, "last_alert_at": now}
        state[name] = entry
        any_down = any_down or not alive

    if args.status:
        return 1 if any_down else 0

    if alert_texts and webhook_url:
        send_webhook(webhook_url, channel, "\n\n".join(alert_texts), timeout)
    elif alert_texts:
        # 未配置 webhook：保留告警文本在日志里，探针可先于通道部署。
        log("L0_WEBHOOK_URL 未配置，仅记录：" + " | ".join(alert_texts))

    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp_path.replace(state_path)

    log(f"探测完成：{len(targets)} 目标" + ("，全部存活" if not any_down else "，存在宕机目标"))
    return 1 if any_down else 0


if __name__ == "__main__":
    sys.exit(main())
