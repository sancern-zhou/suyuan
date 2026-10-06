# -*- coding: utf-8 -*-
"""Analyze an agent run JSON: question, tool call sequence, final answer."""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

path = sys.argv[1]
d = json.load(open(path, encoding="utf-8"))

print("run file:", path)
print("top-level keys:", list(d)[:20])

# find question/messages structure robustly
def walk(o, depth=0):
    if isinstance(o, dict):
        return {k: walk(v, depth + 1) for k, v in o.items()}
    if isinstance(o, list):
        return [walk(v, depth + 1) for v in o[:3]]
    s = str(o)
    return s[:80] if depth > 2 else s

meta = {k: v for k, v in d.items() if k not in ("messages", "steps", "tool_calls", "events")}
print("meta:", json.dumps(walk(meta), ensure_ascii=False)[:600])

msgs = d.get("messages") or d.get("events") or d.get("steps") or []
print("entries:", len(msgs) if isinstance(msgs, list) else type(msgs))

tool_calls = []
for i, m in enumerate(msgs if isinstance(msgs, list) else []):
    if not isinstance(m, dict):
        continue
    role = m.get("role", "?")
    if role == "user":
        c = m.get("content")
        print("\n=== USER QUESTION ===")
        print(str(c)[:500])
    if m.get("tool_calls"):
        for tc in m["tool_calls"]:
            fn = (tc.get("function") or {}).get("name", "?")
            args = (tc.get("function") or {}).get("arguments", "")
            tool_calls.append((fn, str(args)[:160]))
    if isinstance(m.get("content"), list):
        for part in m["content"]:
            if isinstance(part, dict) and part.get("type") == "tool_use":
                tool_calls.append((part.get("name", "?"), json.dumps(part.get("input", {}), ensure_ascii=False)[:160]))

print("\n=== TOOL CALLS (%d) ===" % len(tool_calls))
from collections import Counter
for n, c in Counter(n for n, _ in tool_calls).most_common():
    print("  %-40s x%d" % (n, c))
print("\n--- sequence ---")
for i, (n, a) in enumerate(tool_calls, 1):
    print("%2d. %-40s %s" % (i, n, a))
