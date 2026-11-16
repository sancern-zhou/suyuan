# -*- coding: utf-8 -*-
"""校验组分站表单语义档案（sup_form_profiles.yaml）与 Agent 查询白名单的一致性。

背景：语义档案按 ruleitemtag 建档，但档案本身不声明承载表；如果某个 tag 的数据
只落在未进白名单的表里，就会出现"规则有档案、Agent 查不到数据"。本脚本扫描
guangdong_mart / guangdong_ods 下全部 sup_rf% 表，建立 tag -> 承载表映射，再与
contract.txt（主契约）+ ods_contract.txt（ODS 兜底）两份白名单比对。

输出三档：
  FAIL  tag 的承载表存在但不在 Agent 白名单（数据不可查）
  WARN  tag 在库里没有任何承载表（未同步或无数据，档案暂无法落地）
  INFO  白名单表里出现但未建档的 tag（供后续建档，不影响退出码）

用法:
  PYTHONPATH=backend python projects/guangdong/data-ops/sync/check_sup_profile_coverage.py
  PYTHONPATH=backend python projects/guangdong/data-ops/sync/check_sup_profile_coverage.py --json
退出码: 存在 FAIL 返回 1。
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

SYNC_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SYNC_DIR / "sync_config.json"


def _backend_root() -> Path:
    """后端根目录：运行时配置的 backend_root 优先，其次环境变量，最后按仓库布局回退。"""
    for candidate in (os.getenv("SUYUAN_BACKEND_ROOT"),):
        if candidate and Path(candidate).is_dir():
            return Path(candidate)
    if CONFIG_PATH.is_file():
        try:
            root = str(json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get("backend_root") or "")
            if root and Path(root).is_dir():
                return Path(root)
        except Exception:  # noqa: BLE001
            pass
    return (SYNC_DIR / ".." / ".." / ".." / ".." / "backend").resolve()


BACKEND_ROOT = _backend_root()
PROFILES_PATH = Path(
    os.getenv("SUP_FORM_PROFILES_PATH")
    or (BACKEND_ROOT / "app" / "services" / "ops_audit" / "configs" / "sup_form_profiles.yaml")
).resolve()
TOOL_DIR = BACKEND_ROOT / "app" / "tools" / "query" / "guangdong_ops_sql_query"
CONTRACT_PATH = (TOOL_DIR / "contract.txt").resolve()
ODS_CONTRACT_PATH = (TOOL_DIR / "ods_contract.txt").resolve()

SUP_TABLE_PATTERNS = ("sup_rf%",)


def load_dsn() -> str:
    dsn = os.getenv("OPS_MART_DATABASE_URL", "").replace("+asyncpg", "")
    if dsn:
        return dsn
    if CONFIG_PATH.is_file():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["target"]["dsn"]
        except Exception:  # noqa: BLE001
            pass
    raise SystemExit("OPS_MART_DATABASE_URL / sync_config.json target.dsn 均未配置")


def load_profile_tags() -> set[str]:
    if yaml is None:
        raise SystemExit("需要 PyYAML（backend venv）解析 sup_form_profiles.yaml")
    data = yaml.safe_load(io.open(PROFILES_PATH, encoding="utf-8"))
    profiles = (data or {}).get("form_profiles") or {}
    return {str(k) for k in profiles}


def load_whitelist() -> set[str]:
    tables: set[str] = set()
    for path in (CONTRACT_PATH, ODS_CONTRACT_PATH):
        try:
            for line in io.open(path, encoding="utf-8"):
                if line.startswith("TABLES:"):
                    tables |= {t.strip().lower() for t in line.split(":", 1)[1].split(",") if t.strip()}
        except OSError:
            pass
    return tables


async def scan_tag_carriers(pg) -> dict[str, set[str]]:
    rows = await pg.fetch(
        """SELECT n.nspname AS schema_name, c.relname AS table_name
           FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE c.relkind = 'r'
             AND n.nspname IN ('guangdong_mart', 'guangdong_ods')
             AND c.relname LIKE 'sup_rf%'"""
    )
    # 同名表优先 mart（语义层读它）
    seen: dict[str, str] = {}
    for r in rows:
        name = r["table_name"].lower()
        if name not in seen or r["schema_name"] == "guangdong_mart":
            seen[name] = r["schema_name"]
    carriers: dict[str, set[str]] = {}
    for table, schema in sorted(seen.items()):
        try:
            tags = await pg.fetch(
                f'SELECT DISTINCT ruleitemtag FROM "{schema}"."{table}" '
                "WHERE ruleitemtag IS NOT NULL AND btrim(ruleitemtag) <> ''"
            )
        except Exception:  # noqa: BLE001
            continue
        for t in tags:
            tag = str(t["ruleitemtag"]).strip()
            carriers.setdefault(tag, set()).add(table)
    return carriers


async def main() -> int:
    import asyncpg

    profile_tags = load_profile_tags()
    whitelist = load_whitelist()
    conn = await asyncpg.connect(load_dsn())
    try:
        carriers = await scan_tag_carriers(conn)
    finally:
        await conn.close()

    lower_map = {k.lower(): (k, v) for k, v in carriers.items()}
    unreachable, no_data, detail = [], [], []
    for tag in sorted(profile_tags):
        tables = carriers.get(tag) or (lower_map.get(tag.lower(), ("", set()))[1])
        if not tables:
            no_data.append(tag)
            continue
        bad = sorted(t for t in tables if t not in whitelist)
        if bad:
            unreachable.append((tag, bad))
            detail.append("%s -> %s" % (tag, ",".join(bad)))

    profiled_lower = {t.lower() for t in profile_tags}
    unprofiled = sorted(t for t in carriers if t.lower() not in profiled_lower)

    result = {
        "profiles": len(profile_tags),
        "tags_with_reachable_data": len(profile_tags) - len(no_data) - len(unreachable),
        "unreachable": [{"tag": t, "tables": b} for t, b in unreachable],
        "no_data": no_data,
        "unprofiled_tags": unprofiled,
    }
    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("profiles=%d reachable=%d unreachable=%d no_data=%d unprofiled=%d" % (
            result["profiles"], result["tags_with_reachable_data"],
            len(unreachable), len(no_data), len(unprofiled)))
        for item in detail:
            print("FAIL:", item)
        for tag in no_data:
            print("WARN: no carrier table:", tag)
        if unprofiled:
            print("INFO: whitelisted tags without profile (%d): %s" % (
                len(unprofiled), ", ".join(unprofiled[:20])))
    return 1 if unreachable else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
