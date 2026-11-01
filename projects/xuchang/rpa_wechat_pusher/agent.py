"""许昌站点告警 → 个人微信群 RPA 推送 agent（wechatauto-replica 驱动微信 4.x）。

常驻轮询后端待发队列，把告警通报发进指定群。仅发不收；依赖微信 4.x
电脑版已登录且主窗口可用。部署步骤见 README.md。

用法：
    python agent.py                # 常驻轮询（Ctrl+C 退出）
    python agent.py --once         # 只跑一轮
    python agent.py --dry-run      # 轮询但只打印不实发（验证链路）
    python agent.py --test "文本"  # 手动发一条到配置的群（验证微信环境）
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path

import httpx

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.toml"
DATA_DIR = BASE_DIR / "data"
LOG_PATH = DATA_DIR / "agent.log"
SENT_MARKERS_PATH = DATA_DIR / "sent_markers.json"

# 本地已发送标记上限：防止 ack 丢失导致重复发送，同时控制文件体积
SENT_MARKERS_LIMIT = 500

PENDING_PATH = "/api/xuchang-wechat-push/pending"
ACK_PATH = "/api/xuchang-wechat-push/ack"


def log(message: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}"
    print(line, flush=True)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


class ConfigError(RuntimeError):
    pass


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise ConfigError(
            f"缺少配置文件 {CONFIG_PATH}，请复制 config.example.toml 为 config.toml 并填写"
        )
    raw = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    backend = raw.get("backend") or {}
    wechat = raw.get("wechat") or {}
    agent = raw.get("agent") or {}
    cfg = {
        "base_url": str(backend.get("base_url") or "").rstrip("/"),
        "token": str(backend.get("token") or ""),
        "group_name": str(wechat.get("group_name") or "").strip(),
        "message_prefix": str(wechat.get("message_prefix") or ""),
        "poll_interval_seconds": float(agent.get("poll_interval_seconds", 15)),
        "send_retry": int(agent.get("send_retry", 2)),
        "send_retry_delay_seconds": float(agent.get("send_retry_delay_seconds", 3)),
        "http_timeout_seconds": float(agent.get("http_timeout_seconds", 10)),
        "agent_id": socket.gethostname(),
    }
    if not cfg["base_url"] or cfg["base_url"].startswith("http") is False:
        raise ConfigError("config.toml [backend].base_url 未填写（如 https://host）")
    if not cfg["token"] or cfg["token"] == "change-me":
        raise ConfigError("config.toml [backend].token 未填写（与后端 XUCHANG_WECHAT_PUSH_TOKEN 一致）")
    if not cfg["group_name"]:
        raise ConfigError("config.toml [wechat].group_name 未填写（目标微信群名）")
    return cfg


class WeChatSender:
    """wechatauto-replica 驱动（微信 4.x 客户端）。

    微信 3.9.x + wxauto 的老路线已被腾讯强制升级拦截（2025-10 起新设备登录
    提示版本过低），本 agent 直接适配微信 4.x：wechatauto 热激活 Weixin.dll
    的无障碍闸门使 UIA 树物化后发送，UIA 优先、OCR 兜底（OCR 依赖 winsdk，
    缺失时仅少一层兜底，不影响发送）。
    """

    def __init__(self) -> None:
        try:
            from wechatauto.guia import quick_send
        except ImportError as exc:
            raise RuntimeError(
                "未安装 wechatauto-replica，请先运行 install.bat"
            ) from exc
        self._send = quick_send

    def send_text(self, group_name: str, text: str) -> None:
        result = self._send(text, group_name)
        status = str((result or {}).get("status") or "")
        if "成功" not in status and "ok" not in status.lower():
            raise RuntimeError(f"发送未确认：{result}")


def http_headers(cfg: dict) -> dict:
    return {"Authorization": f"Bearer {cfg['token']}"}


def fetch_pending(cfg: dict) -> list[dict] | None:
    try:
        response = httpx.get(
            f"{cfg['base_url']}{PENDING_PATH}",
            params={"limit": 10, "agent_id": cfg["agent_id"]},
            headers=http_headers(cfg),
            timeout=cfg["http_timeout_seconds"],
        )
    except httpx.HTTPError as exc:
        log(f"[warn] 后端不可达：{exc}")
        return None
    if response.status_code == 403:
        log("[error] 后端返回 403：未启用推送接口（检查 XUCHANG_WECHAT_PUSH_TOKEN/API_PREFIX 是否配置）")
        return None
    if response.status_code == 401:
        log("[error] 后端返回 401：token 不正确，检查 config.toml 的 token")
        return None
    if response.status_code != 200:
        log(f"[warn] 拉取待发消息失败：HTTP {response.status_code}")
        return None
    return response.json().get("messages") or []


def ack(cfg: dict, message_id: str, status: str, detail: str | None = None) -> bool:
    try:
        response = httpx.post(
            f"{cfg['base_url']}{ACK_PATH}",
            json={
                "id": message_id,
                "status": status,
                "detail": detail,
                "agent_id": cfg["agent_id"],
            },
            headers=http_headers(cfg),
            timeout=cfg["http_timeout_seconds"],
        )
    except httpx.HTTPError as exc:
        log(f"[warn] 回执失败（{message_id} {status}）：{exc}")
        return False
    if response.status_code != 200:
        log(f"[warn] 回执被拒（{message_id} {status}）：HTTP {response.status_code}")
        return False
    log(f"[info] 回执成功：{message_id} -> {response.json().get('result')}")
    return True


def load_markers() -> dict:
    try:
        data = json.loads(SENT_MARKERS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("markers"), dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"markers": {}}


def save_markers(markers: dict) -> None:
    items = sorted(markers["markers"].items(), key=lambda kv: kv[1], reverse=True)
    markers["markers"] = dict(items[:SENT_MARKERS_LIMIT])
    SENT_MARKERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = SENT_MARKERS_PATH.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(markers, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    temp_path.replace(SENT_MARKERS_PATH)


def send_with_retry(cfg: dict, sender: WeChatSender, text: str) -> str | None:
    """成功返回 None；重试耗尽返回最后一次错误信息。"""
    last_error = "未知错误"
    for attempt in range(1 + cfg["send_retry"]):
        try:
            sender.send_text(cfg["group_name"], text)
            return None
        except Exception as exc:
            last_error = str(exc)
            log(f"[warn] 发送失败（第 {attempt + 1} 次）：{last_error}")
            if attempt < cfg["send_retry"]:
                time.sleep(cfg["send_retry_delay_seconds"])
    return last_error


def run_cycle(cfg: dict, markers: dict, sender: WeChatSender | None, dry_run: bool) -> None:
    messages = fetch_pending(cfg)
    if messages is None:
        return
    for msg in messages:
        message_id = str(msg.get("id") or "")
        text = f"{cfg['message_prefix']}{msg.get('text') or ''}"
        if not message_id or not msg.get("text"):
            log(f"[warn] 跳过异常消息：{msg}")
            continue
        if message_id in markers["markers"]:
            # 上轮已实发但 ack 未达：只补回执，绝不重发
            log(f"[info] {message_id} 本地已发送，补回执")
            ack(cfg, message_id, "sent", detail="本地已发送标记补回执")
            continue
        if dry_run:
            log(f"[dry-run] 将发到「{cfg['group_name']}」：{text[:80]}...")
            continue
        if sender is None:
            return  # 微信不可用：消息留在队列，下轮再试
        error = send_with_retry(cfg, sender, text)
        if error is None:
            log(f"[info] 已发送告警 {message_id} 到「{cfg['group_name']}」")
            markers["markers"][message_id] = datetime.now().isoformat(
                timespec="seconds"
            )
            save_markers(markers)
            ack(cfg, message_id, "sent")
        else:
            ack(cfg, message_id, "failed", detail=error)


def ensure_sender(cfg: dict, sender: WeChatSender | None) -> WeChatSender | None:
    if sender is not None:
        return sender
    try:
        return WeChatSender()
    except RuntimeError as exc:
        log(f"[warn] {exc}")
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="许昌站点告警微信群推送 agent")
    parser.add_argument("--once", action="store_true", help="只跑一轮后退出")
    parser.add_argument("--dry-run", action="store_true", help="只打印不实发、不回执")
    parser.add_argument("--test", metavar="TEXT", help="手动发一条文本到配置的群后退出")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 1

    log(
        f"agent 启动：backend={cfg['base_url']} group=「{cfg['group_name']}」 "
        f"poll={cfg['poll_interval_seconds']}s agent_id={cfg['agent_id']}"
    )

    if args.test:
        try:
            sender = WeChatSender()
            sender.send_text(cfg["group_name"], args.test)
        except RuntimeError as exc:
            print(f"[错误] {exc}", file=sys.stderr)
            return 1
        log(f"测试消息已发送到「{cfg['group_name']}」，请在微信里确认")
        return 0

    markers = load_markers()
    sender: WeChatSender | None = None
    while True:
        if not args.dry_run:
            sender = ensure_sender(cfg, sender)
        try:
            run_cycle(cfg, markers, sender, args.dry_run)
        except Exception:
            log("[warn] 本轮执行异常，继续下一轮")
            log_exception()
        if args.once or args.dry_run:
            return 0
        time.sleep(cfg["poll_interval_seconds"])


def log_exception() -> None:
    import traceback

    for line in traceback.format_exc().splitlines():
        log(f"    {line}")


if __name__ == "__main__":
    raise SystemExit(main())
