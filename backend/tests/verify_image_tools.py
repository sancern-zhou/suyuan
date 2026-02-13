"""
简化版图片工具验证脚本

验证新工具是否正确加载
"""
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

def verify_tools():
    """验证工具加载"""
    print("="*60)
    print("图片工具验证")
    print("="*60)

    # 导入工具注册表
    from app.tools import global_tool_registry

    # 获取所有工具
    tools = global_tool_registry.list_tools()
    tool_names = [tool.name for tool in tools]

    print(f"\n总工具数: {len(tools)}")

    # 检查新工具是否加载
    print("\n检查新工具:")
    new_tools = ['read_file', 'analyze_image']

    for tool_name in new_tools:
        if tool_name in tool_names:
            print(f"  [OK] {tool_name} - 已加载")

            # 获取工具详情
            tool = global_tool_registry.get_tool(tool_name)
            print(f"      描述: {tool.description[:100]}...")
            print(f"      优先级: {tool.priority}")
            print(f"      可用: {tool.is_available()}")
        else:
            print(f"  [FAIL] {tool_name} - 未加载")

    # 显示工具 schema
    print("\n工具 Schema:")
    for tool_name in new_tools:
        if tool_name in tool_names:
            tool = global_tool_registry.get_tool(tool_name)
            schema = tool.get_function_schema()
            print(f"\n{tool_name}:")
            print(f"  参数: {list(schema['parameters']['properties'].keys())}")
            print(f"  必需: {schema['parameters']['required']}")

    print("\n" + "="*60)
    print("验证完成")
    print("="*60)

if __name__ == "__main__":
    verify_tools()
