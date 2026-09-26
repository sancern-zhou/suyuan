# -*- coding: utf-8 -*-
"""Validate go2 failover wiring for jiangsu-ops (run from E:\\suyuan\\backend)."""
import io
import os
import py_compile
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BACKEND = r"E:\suyuan\backend"
os.chdir(BACKEND)
sys.path.insert(0, BACKEND)

# 1) syntax check
for f in [r"config\settings.py", r"app\services\llm_service.py"]:
    py_compile.compile(f, doraise=True)
    print(f"COMPILE OK: {f}")

# 2) load env exactly like the deployed service does
with open(r".env.jiangsu-ops", "r", encoding="utf-8-sig") as fh:
    for line in fh:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

from config.settings import settings  # noqa: E402

print("go2_api_key set:", bool(settings.go2_api_key), "->", (settings.go2_api_key or "")[:12] + "...")
print("go2_base_url:", settings.go2_base_url)
print("go2_model:", settings.go2_model)

from app.services.llm_failover import parse_fallback_candidates  # noqa: E402

auto_chain = parse_fallback_candidates(settings.llm_provider.lower(), settings.doubao_model, settings.llm_fallbacks)
print("AUTO chain :", " -> ".join(f"{c.provider}/{c.model}" for c in auto_chain))

flash_chain = parse_fallback_candidates("", "", settings.llm_flash_models)
print("FLASH chain:", " -> ".join(f"{c.provider}/{c.model}" for c in flash_chain))

# 3) simulate the failover switch the service performs per candidate
from app.services.llm_service import LLMService  # noqa: E402

svc = LLMService()
for provider_id in ("go", "go2"):
    svc.provider = provider_id
    svc._load_provider_config()
    print(f"SWITCH {provider_id}: mode={svc.api_mode} model={svc.model} base={svc.base_url} key={svc.api_key[:12]}...")
print("ALL CHECKS PASSED")
