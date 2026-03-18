import sys
sys.path.insert(0, r"D:\溯源\backend")

from app.tools import global_tool_registry

tools = global_tool_registry.list_tools()
print(f"Total tools: {len(tools)}")
print(f"Has unpack_office: {'unpack_office' in tools}")
print(f"Has pack_office: {'pack_office' in tools}")

office_tools = [t for t in tools if 'office' in t.lower() or 'word' in t.lower() or 'excel' in t.lower() or 'ppt' in t.lower()]
print(f"\nOffice-related tools ({len(office_tools)}):")
for tool in sorted(office_tools):
    print(f"  - {tool}")
