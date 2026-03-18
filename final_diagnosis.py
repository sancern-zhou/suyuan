"""
最终诊断脚本 - 确认 unpack_office 工具问题的根本原因
"""
import subprocess
import sys
from pathlib import Path

print("=" * 80)
print("FINAL DIAGNOSIS - unpack_office Tool Issue")
print("=" * 80)

# 1. 检查代码修改是否存在
print("\n[Check 1] Verifying code modifications...")

files_to_check = {
    "app/main.py": ["refresh_tools", "refreshing_global_agent_tools"],
    "app/agent/core/executor.py": ["def refresh_tools"],
    "app/agent/react_agent.py": ["def refresh_tools"],
    "app/agent/core/planner.py": ["global_tool_registry"]
}

all_ok = True
for file_path, keywords in files_to_check.items():
    full_path = Path("D:/溯源/backend") / file_path
    if not full_path.exists():
        print(f"  [ERROR] File not found: {file_path}")
        all_ok = False
        continue

    content = full_path.read_text(encoding='utf-8')
    file_ok = True
    for keyword in keywords:
        if keyword not in content:
            print(f"  [ERROR] Missing '{keyword}' in {file_path}")
            file_ok = False
            all_ok = False

    if file_ok:
        print(f"  [OK] {file_path}")

if all_ok:
    print("  [SUMMARY] All code modifications are present")
else:
    print("  [SUMMARY] Some modifications are missing!")

# 2. 检查 Python 缓存
print("\n[Check 2] Checking for Python cache files...")
backend_dir = Path("D:/溯源/backend")
pycache_dirs = list(backend_dir.rglob("__pycache__"))
pyc_files = list(backend_dir.rglob("*.pyc"))

print(f"  __pycache__ directories: {len(pycache_dirs)}")
print(f"  .pyc files: {len(pyc_files)}")

if pycache_dirs or pyc_files:
    print("  [WARNING] Cache files exist - may cause old code to be used")
    print("  [ACTION] Run clean_restart.bat to clear cache and restart")
else:
    print("  [OK] No cache files found")

# 3. 检查 global_tool_registry
print("\n[Check 3] Verifying global_tool_registry...")
sys.path.insert(0, str(backend_dir))

try:
    from app.tools import global_tool_registry
    tools = global_tool_registry.list_tools()
    print(f"  Total tools: {len(tools)}")
    print(f"  Has 'unpack_office': {'unpack_office' in tools}")
    print(f"  Has 'pack_office': {'pack_office' in tools}")

    if 'unpack_office' in tools:
        print("  [OK] unpack_office is registered in global_tool_registry")
    else:
        print("  [ERROR] unpack_office is NOT in global_tool_registry!")

except Exception as e:
    print(f"  [ERROR] Could not load global_tool_registry: {e}")

# 4. 检查后端进程
print("\n[Check 4] Checking for running backend processes...")
try:
    result = subprocess.run(
        ["powershell", "-Command",
         "Get-Process python | Where-Object {$_.Path -like '*溯源*'} | Select-Object Id, Path"],
        capture_output=True,
        text=True,
        timeout=5
    )
    if result.stdout.strip():
        print("  [WARNING] Found running Python processes:")
        print(result.stdout)
        print("  [ACTION] Stop these processes before restarting")
    else:
        print("  [INFO] No Python processes found")
except Exception as e:
    print(f"  [INFO] Could not check processes: {e}")

# 5. 最终建议
print("\n" + "=" * 80)
print("RECOMMENDATIONS")
print("=" * 80)

if pycache_dirs or pyc_files:
    print("\n1. CRITICAL: Clear Python cache and restart backend")
    print("   Command: D:\\溯源\\backend\\clean_restart.bat")
    print("")
    print("2. After restart, verify tools are loaded")
    print("   Command: python D:\\溯源\\verify_backend.py")
else:
    print("\n1. Restart backend server")
    print("   - Stop current server (Ctrl+C)")
    print("   - Run: cd D:\\溯源\\backend && start.bat")
    print("")
    print("2. Check startup logs for:")
    print("   - [info] llm_tools_initialized")
    print("   - [info] refreshing_global_agent_tools")
    print("   - [info] global_agents_refreshed")
    print("")
    print("3. Verify with: python D:\\溯源\\verify_backend.py")

print("\n" + "=" * 80)
