#!/usr/bin/env python3
"""
工具注册CLI - 辅助新工具注册

使用此CLI可以快速注册新工具到 global_tool_registry，自动生成：
- 输入适配器规则
- 返回Schema
- 测试样例
- 验证合规性

使用方法：
    python scripts/register_tool.py --tool-path path/to/tool.py --category query --priority 100
    python scripts/register_tool.py --interactive
"""

import sys
import argparse
import importlib.util
import inspect
from pathlib import Path
from typing import Dict, Any, List, Optional
import json

# 添加 backend 到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools import global_tool_registry
from app.tools.base.tool_interface import LLMTool
import structlog

logger = structlog.get_logger()


class ToolRegistrationCLI:
    """工具注册命令行界面"""

    def __init__(self):
        self.tool_instance: Optional[LLMTool] = None
        self.tool_path: Optional[Path] = None
        self.category: Optional[str] = None
        self.priority: Optional[int] = None
        self.auto_generate: bool = True

    def load_tool(self, tool_path: str) -> bool:
        """
        动态加载工具类

        Args:
            tool_path: 工具文件路径

        Returns:
            是否加载成功
        """
        try:
            tool_file = Path(tool_path)
            if not tool_file.exists():
                logger.error("tool_file_not_found", path=tool_path)
                return False

            # 动态导入模块
            spec = importlib.util.spec_from_file_location("temp_tool_module", tool_file)
            if not spec or not spec.loader:
                logger.error("tool_file_invalid", path=tool_path)
                return False

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 查找LLMTool子类
            tool_classes = []
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, LLMTool) and obj != LLMTool:
                    tool_classes.append(obj)

            if not tool_classes:
                logger.error("no_tool_class_found", path=tool_path)
                return False
            elif len(tool_classes) > 1:
                logger.warning("multiple_tool_classes_found", count=len(tool_classes))
                # 选择第一个
                tool_class = tool_classes[0]
            else:
                tool_class = tool_classes[0]

            # 实例化工具
            self.tool_instance = tool_class()
            logger.info("tool_loaded", tool_name=self.tool_instance.name)

            return True

        except Exception as e:
            logger.error("tool_load_failed", error=str(e), exc_info=True)
            return False

    def validate_tool(self) -> List[str]:
        """
        验证工具是否符合注册要求

        Returns:
            错误列表
        """
        errors = []

        if not self.tool_instance:
            errors.append("工具未加载")
            return errors

        if not hasattr(self.tool_instance, 'name') or not self.tool_instance.name:
            errors.append("工具缺少名称")

        if not hasattr(self.tool_instance, 'execute'):
            errors.append("工具缺少execute方法")

        # 验证Function Schema
        if hasattr(self.tool_instance, 'get_function_schema'):
            schema = self.tool_instance.get_function_schema()
            if 'parameters' not in schema or 'properties' not in schema['parameters']:
                errors.append("Function Schema 缺少参数定义")

        # 验证工具可用性
        if not self.tool_instance.is_available():
            logger.warning("tool_not_available", tool=self.tool_instance.name)

        return errors

    def generate_registration_data(self) -> Dict[str, Any]:
        """
        生成工具注册数据（使用自动生成器）

        Returns:
            注册数据字典
        """
        if not self.tool_instance:
            raise ValueError("工具未加载")

        # 使用 global_tool_registry 的自动生成功能
        return {
            "tool": self.tool_instance,
            "priority": self.priority or 100,
            "input_adapter_rules": None,  # 让注册表自动生成
            "return_schema": None,  # 让注册表自动生成
            "metadata": None,  # 让注册表自动生成
            "auto_generate": True
        }

    def interactive_mode(self):
        """交互式注册模式"""
        print("\n=== 工具注册向导 ===\n")

        # Step 1: 输入工具路径
        while True:
            tool_path = input("请输入工具文件路径: ").strip()
            if not tool_path:
                print("❌ 路径不能为空")
                continue

            if self.load_tool(tool_path):
                self.tool_path = Path(tool_path)
                break
            else:
                print(f"❌ 无法加载工具: {tool_path}")
                retry = input("是否重试? (y/n): ").strip().lower()
                if retry != 'y':
                    return

        # Step 2: 验证工具
        errors = self.validate_tool()
        if errors:
            print("\n❌ 工具验证失败:")
            for error in errors:
                print(f"  - {error}")
            return
        else:
            print(f"\n✅ 工具验证通过: {self.tool_instance.name}")

        # Step 3: 输入优先级
        while True:
            priority_str = input(f"请输入优先级 (默认100, 1-1000): ").strip()
            if not priority_str:
                self.priority = 100
                break

            try:
                priority = int(priority_str)
                if 1 <= priority <= 1000:
                    self.priority = priority
                    break
                else:
                    print("❌ 优先级必须在 1-1000 之间")
            except ValueError:
                print("❌ 请输入有效数字")

        # Step 4: 确认注册
        print("\n=== 注册信息 ===")
        print(f"工具名称: {self.tool_instance.name}")
        print(f"工具路径: {self.tool_path}")
        print(f"优先级: {self.priority}")
        print(f"自动生成元数据: True")

        confirm = input("\n确认注册? (y/n): ").strip().lower()
        if confirm != 'y':
            print("❌ 注册已取消")
            return

        # Step 5: 注册工具
        self.register_tool()

        # Step 6: 显示结果
        self.show_registration_result()

    def register_tool(self):
        """执行工具注册"""
        try:
            registration_data = self.generate_registration_data()

            # 注册到 global_tool_registry
            global_tool_registry.register(**registration_data)

            print(f"\n✅ 工具注册成功!")
            print(f"工具名称: {self.tool_instance.name}")
            print(f"优先级: {self.priority}")

        except Exception as e:
            print(f"\n❌ 注册失败: {str(e)}")
            logger.error("tool_registration_failed", error=str(e), exc_info=True)

    def show_registration_result(self):
        """显示注册结果和详细信息"""
        if not self.tool_instance:
            return

        tool_name = self.tool_instance.name
        tool_data = global_tool_registry.get_tool_data(tool_name)

        if not tool_data:
            print("❌ 无法获取工具数据")
            return

        print("\n=== 工具详情 ===")
        print(f"\n📋 基本信息:")
        print(f"  名称: {tool_name}")
        print(f"  类别: {tool_data.get('category')}")
        print(f"  版本: {tool_data.get('version')}")
        print(f"  优先级: {tool_data.get('priority')}")
        print(f"  需要上下文: {tool_data.get('requires_context')}")

        print(f"\n⚙️  元数据:")
        metadata = tool_data.get('metadata', {})
        for key, value in metadata.items():
            if isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    print(f"    - {k}: {v}")
            else:
                print(f"  {key}: {value}")

        print(f"\n📝 输入适配器规则:")
        adapter_rules = tool_data.get('input_adapter_rules', {})
        if adapter_rules:
            print(f"  字段数: {len(adapter_rules.get('fields', {}))}")
        else:
            print("  未配置")

        print(f"\n✅ 测试样例:")
        test_samples = tool_data.get('test_samples', [])
        for sample in test_samples:
            print(f"  - {sample.get('name')}: {sample.get('description')}")

        print(f"\n📊 验证合规性:")
        compliance = global_tool_registry.validate_tool_compliance(tool_name)
        if compliance["valid"]:
            print("  ✅ 工具符合统一数据格式和v3.0规范")
        else:
            print("  ⚠️ 工具需要改进:")
            for error in compliance["errors"]:
                print(f"    - {error}")
            for warning in compliance["warnings"]:
                print(f"    - {warning}")

    def export_tool_config(self, output_path: str):
        """导出工具配置为JSON"""
        if not self.tool_instance:
            print("❌ 请先加载工具")
            return

        tool_name = self.tool_instance.name
        tool_data = global_tool_registry.get_tool_data(tool_name)

        if not tool_data:
            print("❌ 无法获取工具数据")
            return

        config = {
            "tool_name": tool_name,
            "version": tool_data.get("version"),
            "category": str(tool_data.get("category")),
            "priority": tool_data.get("priority"),
            "requires_context": tool_data.get("requires_context"),
            "metadata": tool_data.get("metadata"),
            "input_adapter_rules": tool_data.get("input_adapter_rules"),
            "return_schema": tool_data.get("return_schema"),
            "test_samples": tool_data.get("test_samples"),
            "registered_at": tool_data.get("registered_at")
        }

        output_file = Path(output_path)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        print(f"✅ 工具配置已导出到: {output_path}")

    def list_registered_tools(self):
        """列出所有已注册的工具"""
        tools = global_tool_registry.list_tools()

        print(f"\n=== 已注册工具列表 (共 {len(tools)} 个) ===\n")

        for i, tool_name in enumerate(tools, 1):
            tool_data = global_tool_registry.get_tool_data(tool_name)
            category = tool_data.get("category")
            priority = tool_data.get("priority")
            requires_context = tool_data.get("requires_context")
            stats = global_tool_registry.get_stats().get(tool_name, {})

            print(f"{i}. {tool_name}")
            print(f"   类别: {category}")
            print(f"   优先级: {priority}")
            print(f"   需要上下文: {requires_context}")
            print(f"   调用统计: {stats.get('total', 0)} 次")
            print()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="工具注册CLI - 辅助新工具注册到 global_tool_registry"
    )

    parser.add_argument(
        "--interactive",
        action="store_true",
        help="交互式注册模式"
    )

    parser.add_argument(
        "--tool-path",
        type=str,
        help="工具文件路径"
    )

    parser.add_argument(
        "--category",
        type=str,
        choices=["query", "analysis", "visualization"],
        help="工具类别"
    )

    parser.add_argument(
        "--priority",
        type=int,
        default=100,
        help="优先级 (1-1000，默认100)"
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有已注册工具"
    )

    parser.add_argument(
        "--export",
        type=str,
        metavar="OUTPUT_PATH",
        help="导出工具配置为JSON"
    )

    parser.add_argument(
        "--validate",
        type=str,
        metavar="TOOL_NAME",
        help="验证指定工具的合规性"
    )

    args = parser.parse_args()

    cli = ToolRegistrationCLI()

    # 列出工具
    if args.list:
        cli.list_registered_tools()
        return

    # 导出工具配置
    if args.export:
        if not cli.tool_instance:
            print("❌ 请先使用 --tool-path 指定工具")
            return
        cli.export_tool_config(args.export)
        return

    # 验证工具合规性
    if args.validate:
        compliance = global_tool_registry.validate_tool_compliance(args.validate)
        print(f"\n=== 工具合规性验证: {args.validate} ===")
        if compliance["valid"]:
            print("✅ 工具符合规范")
        else:
            print("❌ 工具不符合规范:")
            for error in compliance["errors"]:
                print(f"  - 错误: {error}")
            for warning in compliance["warnings"]:
                print(f"  - 警告: {warning}")
        return

    # 交互式模式
    if args.interactive:
        cli.interactive_mode()
        return

    # 命令行模式
    if args.tool_path:
        if not cli.load_tool(args.tool_path):
            sys.exit(1)

        errors = cli.validate_tool()
        if errors:
            print("❌ 工具验证失败:")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)

        cli.priority = args.priority

        if args.category:
            cli.tool_instance.category = args.category

        print(f"\n=== 准备注册工具 ===")
        print(f"工具名称: {cli.tool_instance.name}")
        print(f"优先级: {cli.priority}")

        confirm = input("\n确认注册? (y/n): ").strip().lower()
        if confirm == 'y':
            cli.register_tool()
            cli.show_registration_result()
        else:
            print("❌ 注册已取消")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
