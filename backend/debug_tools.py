"""调试 Office 工具摘要生成"""
import sys
sys.path.insert(0, 'D:/溯源/backend')

from app.tools import global_tool_registry
from app.agent.tool_adapter_backup import SIMPLE_TOOLS

print("=== SIMPLE_TOOLS 配置 ===")
for name, info in SIMPLE_TOOLS.items():
    print(f"{name}: {info}")

print("\n=== 全局工具注册表 ===")
all_tools = global_tool_registry.list_tools()
print(f"总工具数: {len(all_tools)}")
print(f"包含 word_processor: {'word_processor' in all_tools}")
print(f"包含 excel_processor: {'excel_processor' in all_tools}")
print(f"包含 ppt_processor: {'ppt_processor' in all_tools}")

print("\n=== 检查工具是否可遍历 ===")
count = 0
processor_count = 0
for tool_data in global_tool_registry.get_all_tools():
    tool = tool_data['tool']
    schema = tool.get_function_schema()
    name = schema.get('name', 'unknown')
    available = tool.is_available()

    count += 1
    if 'processor' in name:
        processor_count += 1
        print(f"✅ 找到 {name}: available={available}")
        print(f"   描述: {schema.get('description', '')[:50]}")

print(f"\n遍历了 {count} 个工具，其中 {processor_count} 个 processor 工具")
