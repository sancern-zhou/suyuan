# -*- coding: utf-8 -*-
"""jiangsu_query_metrics 真实环境 e2e（走 /api/agent/analyze 完整链路）。"""
import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8001/api/agent/analyze"

CASES = [
    # (名称, mode, query, 期望工具)
    ("T1 按市工单量与超期率", "ops",
     "各市本月的工单量和超期率排名", "jiangsu_query_metrics"),
    ("T2 近7日工单趋势", "smart_inspection",
     "最近一周每天新增工单是多少，按天列出", "jiangsu_query_metrics"),
    ("T3 质控合格率", "ops",
     "本月各市质控合格率是多少", "jiangsu_query_metrics"),
    ("T4 站点风险(目录外→SQL)", "ops",
     "当前风险等级为高的站点清单有哪些", None),  # health 表不在语义目录, 应走 SQL 工具
]


def stream_analyze(query: str, mode: str, timeout_s: float = 300.0):
    payload = {
        "query": query,
        "skill_ids": [],
        "context_refs": [],
        "session_id": None,
        "mode": mode,
        "user_id": "e2e-metrics-test",
        "enhance_with_history": False,
        "max_iterations": 8,
    }
    tools_used = []
    answer_parts = []
    start = time.monotonic()
    with httpx.Client(timeout=httpx.Timeout(timeout_s)) as client:
        with client.stream("POST", BASE, json=payload) as resp:
            if resp.status_code != 200:
                print(f"    HTTP {resp.status_code}: {resp.read()[:200]}")
                return None, [], ""
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                try:
                    event = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                etype = event.get("type", "")
                data = event.get("data", {}) or {}
                if etype == "action":
                    # 结构: {"type":"action","data":{"thought":...,"action":{...}}}
                    act = data.get("action") or {}
                    if isinstance(act, dict):
                        tool = (act.get("tool") or act.get("tool_name")
                                or act.get("name") or "")
                        if tool and act.get("type") != "PLAIN_TEXT_REPLY":
                            tools_used.append(tool)
                elif etype == "tool_use":
                    tool = data.get("tool_name") or data.get("tool")
                    if tool:
                        tools_used.append(tool)
                elif etype in ("complete", "incomplete"):
                    answer_parts = [data.get("answer", "")]
    return time.monotonic() - start, tools_used, (answer_parts[0] if answer_parts else "")


def main() -> int:
    failures = 0
    for name, mode, query, expect in CASES:
        print(f"[{name}] mode={mode}")
        dur, tools, answer = stream_analyze(query, mode)
        if dur is None:
            failures += 1
            print("    !!! 请求失败")
            continue
        uniq = list(dict.fromkeys(tools))
        hit = [t for t in uniq if "jiangsu" in t]
        print(f"    {dur:.0f}s tools={uniq}")
        if expect:
            ok = expect in uniq
            flag = "OK" if ok else "!!! 未命中预期工具"
            if not ok:
                failures += 1
            print(f"    {flag} (期望 {expect})")
        else:
            print(f"    路由={hit}")
        snippet = (answer or "").replace("\n", " ")[:220]
        print(f"    答: {snippet}")
    print(f"\nRESULT: {'ALL PASS' if failures == 0 else str(failures) + ' FAILURES'}")
    return failures


sys.exit(main())
