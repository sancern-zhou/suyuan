"""推送受众组目录：业务角色（局长/科长/区县/驻场/执法）→ App 接收账号。

背景：系统原有的定时/事件推送只认 target_user_ids（app:android:<账号>），
没有"局长/科长"这类业务角色概念。多个推送场景（月度特征分析、污染原因
分析、企业核查线索周报）都要把结果推给指定角色，这里提供统一的
角色 → App 账号解析层，账号清单用 JSON 文件维护、运行时可改、无需改代码。

覆盖文件查找顺序（与 air_alert_config 同款约定）：
    1. 环境变量 XUCHANG_PUSH_AUDIENCES 指向的 JSON 路径
    2. 数据登记目录下的 push_audiences.json
文件缺失不是错误，直接用代码内默认值。

JSON 结构（按角色深合并，未覆盖的角色保持默认）：
    {
      "局长": {"app_accounts": ["zhangsan"], "description": "..."},
      "科长": {"app_accounts": ["大气科1", "大气科2"]}
    }
app_accounts 里填 App 账号 id（APP_ACCOUNTS_JSON 的键），解析结果
转成 app:android:<账号> 交 EventTaskDelivery / SocialBroadcastService 投递。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import structlog

from app.utils.path_config import get_data_registry

logger = structlog.get_logger()

AUDIENCES_FILE_ENV = "XUCHANG_PUSH_AUDIENCES"
AUDIENCES_FILE_NAME = "push_audiences.json"

# 默认受众组：账号清单以运行时覆盖文件为准（部署后按实际 App 账号填写）。
# 科长默认挂大气科账号是当前部署的合理初值；局长/区县/驻场/执法留空，
# 解析结果为空时调用方应跳过该受众并记日志，不要让推送主流程失败。
DEFAULT_AUDIENCES: dict[str, dict[str, Any]] = {
    "局长": {"app_accounts": [], "description": "局领导（月度特征分析、污染原因分析）"},
    "科长": {
        "app_accounts": ["大气科1", "大气科2", "大气科3", "大气科4"],
        "description": "大气科科长及科员（全部推送场景）",
    },
    "区县": {"app_accounts": [], "description": "区县生态环境部门（告警、企业周报）"},
    "驻场": {"app_accounts": [], "description": "驻场专家团队（告警）"},
    "执法": {"app_accounts": [], "description": "执法队伍（企业核查线索周报）"},
}

SUPPORTED_ROLES = tuple(DEFAULT_AUDIENCES.keys())


def load_push_audiences(registry_root: Path | None = None) -> dict[str, dict[str, Any]]:
    """加载受众组目录：代码默认值 + JSON 覆盖文件按角色深合并。"""
    audiences: dict[str, dict[str, Any]] = {}
    for role, payload in DEFAULT_AUDIENCES.items():
        audiences[role] = {
            "app_accounts": list(payload.get("app_accounts") or []),
            "description": str(payload.get("description") or ""),
        }
    candidates: list[Path] = []
    env_path = os.getenv(AUDIENCES_FILE_ENV)
    if env_path:
        candidates.append(Path(env_path))
    try:
        candidates.append(
            Path(registry_root) / AUDIENCES_FILE_NAME
            if registry_root is not None
            else get_data_registry() / AUDIENCES_FILE_NAME
        )
    except Exception:  # pragma: no cover - registry 未配置时兜底默认值
        pass
    for path in candidates:
        try:
            overrides = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError):
            continue
        if not isinstance(overrides, dict):
            continue
        for role, value in overrides.items():
            if not isinstance(value, dict):
                continue
            entry = audiences.setdefault(
                role, {"app_accounts": [], "description": ""}
            )
            accounts = value.get("app_accounts")
            if isinstance(accounts, list):
                entry["app_accounts"] = [str(item).strip() for item in accounts if str(item).strip()]
            if value.get("description"):
                entry["description"] = str(value["description"])
        break
    return audiences


def resolve_audience_accounts(
    roles: list[str] | tuple[str, ...] | str,
    *,
    registry_root: Path | None = None,
    audiences: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """把角色名列表解析为去重保序的 app:android:<账号> 接收人列表。

    未知角色忽略并记日志；角色下账号为空视为该受众"未配置"，同样忽略
    （返回结果可能为空，由调用方决定是否跳过投递）。
    """
    if isinstance(roles, str):
        roles = [roles]
    catalog = audiences if audiences is not None else load_push_audiences(registry_root)
    resolved: list[str] = []
    for role in roles:
        name = str(role or "").strip()
        if not name:
            continue
        entry = catalog.get(name)
        if not isinstance(entry, dict):
            logger.warning("push_audience_role_unknown", role=name)
            continue
        accounts = entry.get("app_accounts") or []
        if not accounts:
            logger.warning("push_audience_role_empty", role=name)
            continue
        for account in accounts:
            user_id = f"app:android:{account}"
            if user_id not in resolved:
                resolved.append(user_id)
    return resolved


def audience_summary(
    roles: list[str] | tuple[str, ...] | str,
    *,
    registry_root: Path | None = None,
    audiences: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """供通报/报告正文与日志引用的受众概览（角色 → 账号数）。"""
    if isinstance(roles, str):
        roles = [roles]
    catalog = audiences if audiences is not None else load_push_audiences(registry_root)
    summary: dict[str, Any] = {}
    for role in roles:
        name = str(role or "").strip()
        entry = catalog.get(name) if name else None
        summary[name] = {
            "account_count": len((entry or {}).get("app_accounts") or []),
            "configured": bool((entry or {}).get("app_accounts")),
        }
    return summary
