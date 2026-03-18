#!/usr/bin/env python3
"""
工具合规性验证脚本

验证所有注册的工具是否符合：
1. UDF v1.0 统一数据格式规范
2. v3.0 图表数据格式规范
3. 输入适配器规则完整性
4. 返回Schema正确性

使用方法：
    python scripts/validate_tool_compliance.py
    python scripts/validate_tool_compliance.py --tool get_air_quality
    python scripts/validate_tool_compliance.py --fix
"""

import sys
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
import json

# 添加 backend 到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools import global_tool_registry
from app.tools.base.tool_interface import ToolCategory
import structlog

logger = structlog.get_logger()


class ToolComplianceValidator:
    """工具合规性验证器"""

    def __init__(self):
        self.results = {}
        self.errors = []
        self.warnings = []

    def validate_all_tools(self) -> Dict[str, Any]:
        """
        验证所有工具

        Returns:
            验证结果汇总
        """
        tools = global_tool_registry.list_tools()
        total_tools = len(tools)
        passed_tools = 0
        failed_tools = 0

        print(f"\n{'='*60}")
        print(f"开始验证 {total_tools} 个工具的合规性")
        print(f"{'='*60}\n")

        for i, tool_name in enumerate(tools, 1):
            print(f"[{i}/{total_tools}] 验证工具: {tool_name}")

            result = self.validate_tool(tool_name)
            self.results[tool_name] = result

            if result["valid"]:
                passed_tools += 1
                print(f"  [PASS] 通过")
            else:
                failed_tools += 1
                print(f"  [FAIL] 失败 ({len(result['errors'])} 个错误, {len(result['warnings'])} 个警告)")

                # 显示错误详情
                for error in result["errors"]:
                    print(f"    - 错误: {error}")

                for warning in result["warnings"]:
                    print(f"    - 警告: {warning}")

            print()

        # 汇总结果
        summary = {
            "total_tools": total_tools,
            "passed_tools": passed_tools,
            "failed_tools": failed_tools,
            "pass_rate": (passed_tools / total_tools * 100) if total_tools > 0 else 0,
            "results": self.results
        }

        self.print_summary(summary)

        return summary

    def validate_tool(self, tool_name: str) -> Dict[str, Any]:
        """
        验证单个工具

        Args:
            tool_name: 工具名称

        Returns:
            验证结果
        """
        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "checks": {
                "has_metadata": False,
                "has_input_adapter": False,
                "has_return_schema": False,
                "has_test_samples": False,
                "metadata_complete": False,
                "return_schema_valid": False,
                "complies_udf_v1": False,
                "complies_v3_chart": False
            }
        }

        tool_data = global_tool_registry.get_tool_data(tool_name)
        if not tool_data:
            result["valid"] = False
            result["errors"].append("工具未在注册表中找到")
            return result

        tool = tool_data["tool"]

        # 1. 验证基本元数据
        metadata = tool_data.get("metadata", {})
        if metadata:
            result["checks"]["has_metadata"] = True

            # 检查必要字段
            required_meta_fields = ["data_type", "name", "version"]
            missing_fields = [f for f in required_meta_fields if f not in metadata]
            if missing_fields:
                result["errors"].append(f"缺少元数据字段: {missing_fields}")
            else:
                result["checks"]["metadata_complete"] = True
        else:
            result["errors"].append("工具缺少元数据")

        # 2. 验证输入适配器规则
        input_adapter = tool_data.get("input_adapter_rules", {})
        if input_adapter:
            result["checks"]["has_input_adapter"] = True

            # 检查字段规则
            if "fields" in input_adapter:
                for field_name, field_rule in input_adapter["fields"].items():
                    if "aliases" not in field_rule:
                        result["warnings"].append(f"字段 {field_name} 缺少 aliases")
                    if "validators" not in field_rule:
                        result["warnings"].append(f"字段 {field_name} 缺少 validators")
        else:
            result["warnings"].append("建议添加输入适配器规则以支持宽进严出")

        # 3. 验证返回Schema
        return_schema = tool_data.get("return_schema", {})
        if return_schema:
            result["checks"]["has_return_schema"] = True

            # 检查是否符合UDF v1.0
            if self._validate_udf_v1_schema(return_schema, tool_data.get("category")):
                result["checks"]["complies_udf_v1"] = True
            else:
                result["errors"].append("返回Schema不符合UDF v1.0规范")

            # 检查图表工具是否符合v3.0规范
            if tool_data.get("category") == ToolCategory.VISUALIZATION:
                if self._validate_v3_chart_schema(return_schema):
                    result["checks"]["complies_v3_chart"] = True
                else:
                    result["errors"].append("图表工具返回Schema不符合v3.0规范")
        else:
            result["warnings"].append("建议添加返回Schema以确保数据格式一致")

        # 4. 验证测试样例
        test_samples = tool_data.get("test_samples", [])
        if test_samples:
            result["checks"]["has_test_samples"] = True
        else:
            result["warnings"].append("建议添加测试样例")

        # 5. 验证Function Schema
        try:
            function_schema = tool.get_function_schema()
            if "parameters" not in function_schema or "properties" not in function_schema["parameters"]:
                result["errors"].append("Function Schema 缺少参数定义")
        except Exception as e:
            result["errors"].append(f"Function Schema 验证失败: {str(e)}")

        # 6. 验证工具可用性
        if not tool.is_available():
            result["warnings"].append("工具当前不可用")

        # 综合判断
        result["valid"] = len(result["errors"]) == 0

        return result

    def _validate_udf_v1_schema(self, schema: Dict[str, Any], category: ToolCategory) -> bool:
        """
        验证返回Schema是否符合UDF v1.0规范

        Args:
            schema: 返回Schema
            category: 工具类别

        Returns:
            是否符合规范
        """
        if not isinstance(schema, dict):
            return False

        # 检查必要字段
        required_fields = ["type", "properties"]
        if not all(field in schema for field in required_fields):
            return False

        properties = schema.get("properties", {})

        # 所有工具都应包含的字段
        udf_required_fields = ["status", "success", "data", "metadata", "summary"]

        # 可视化工具不严格要求data字段（图表数据在chart字段中）
        if category == ToolCategory.VISUALIZATION:
            udf_required_fields = [f for f in udf_required_fields if f != "data"]

        if not all(field in properties for field in udf_required_fields):
            return False

        # 验证字段类型
        if properties.get("status", {}).get("type") != "string":
            return False

        if properties.get("success", {}).get("type") != "boolean":
            return False

        # data字段类型验证（如果存在）
        if "data" in properties:
            data_type = properties["data"].get("type")
            if data_type not in ["array", "object", "null"]:
                return False

        return True

    def _validate_v3_chart_schema(self, schema: Dict[str, Any]) -> bool:
        """
        验证图表工具返回Schema是否符合v3.0规范

        Args:
            schema: 返回Schema

        Returns:
            是否符合规范
        """
        if not isinstance(schema, dict):
            return False

        properties = schema.get("properties", {})

        # v3.0图表规范：必须包含 chart 字段
        if "chart" not in properties:
            return False

        chart_config = properties["chart"]
        if not isinstance(chart_config, dict):
            return False

        chart_properties = chart_config.get("properties", {})

        # 检查必要字段
        required_chart_fields = ["id", "type", "data"]
        if not all(field in chart_properties for field in required_chart_fields):
            return False

        # 验证图表类型
        chart_type = chart_properties.get("type", {})
        if "enum" in chart_type:
            valid_types = chart_type["enum"]
            if not all(t in ["pie", "bar", "line", "timeseries", "radar"] for t in valid_types):
                return False

        return True

    def print_summary(self, summary: Dict[str, Any]):
        """打印验证结果汇总"""
        print(f"{'='*60}")
        print(f"验证结果汇总")
        print(f"{'='*60}")
        print(f"总工具数: {summary['total_tools']}")
        print(f"通过工具: {summary['passed_tools']}")
        print(f"失败工具: {summary['failed_tools']}")
        print(f"通过率: {summary['pass_rate']:.1f}%")
        print(f"{'='*60}")

        # 按工具类型统计
        categories = {}
        for tool_name, result in summary["results"].items():
            tool_data = global_tool_registry.get_tool_data(tool_name)
            category = tool_data.get("category", "unknown")
            if category not in categories:
                categories[category] = {"total": 0, "passed": 0}

            categories[category]["total"] += 1
            if result["valid"]:
                categories[category]["passed"] += 1

        if categories:
            print("\n[STATS] 按工具类别统计:")
            for category, stats in categories.items():
                pass_rate = (stats["passed"] / stats["total"] * 100) if stats["total"] > 0 else 0
                print(f"  {category}: {stats['passed']}/{stats['total']} ({pass_rate:.1f}%)")

        # 常见问题统计
        error_counts = {}
        warning_counts = {}
        for result in summary["results"].values():
            for error in result["errors"]:
                error_counts[error] = error_counts.get(error, 0) + 1
            for warning in result["warnings"]:
                warning_counts[warning] = warning_counts.get(warning, 0) + 1

        if error_counts:
            print("\n[ERROR] 常见错误:")
            for error, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"  - {error} ({count} 个工具)")

        if warning_counts:
            print("\n[WARN] 常见警告:")
            for warning, count in sorted(warning_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"  - {warning} ({count} 个工具)")

        print(f"{'='*60}\n")

    def export_report(self, output_path: str):
        """
        导出验证报告为JSON

        Args:
            output_path: 输出文件路径
        """
        report = {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "summary": {
                "total_tools": len(self.results),
                "passed_tools": sum(1 for r in self.results.values() if r["valid"]),
                "failed_tools": sum(1 for r in self.results.values() if not r["valid"])
            },
            "results": self.results
        }

        output_file = Path(output_path)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"[OK] 验证报告已导出到: {output_path}")

    def auto_fix(self) -> Dict[str, Any]:
        """
        自动修复常见问题

        Returns:
            修复结果
        """
        fixed_tools = []
        errors = []

        print(f"\n{'='*60}")
        print(f"开始自动修复")
        print(f"{'='*60}\n")

        for tool_name in global_tool_registry.list_tools():
            tool_data = global_tool_registry.get_tool_data(tool_name)

            # 重新注册以生成缺失的元数据
            try:
                global_tool_registry.register(
                    tool=tool_data["tool"],
                    priority=tool_data.get("priority", 100),
                    auto_generate=True
                )
                fixed_tools.append(tool_name)
                print(f"[OK] 已修复: {tool_name}")
            except Exception as e:
                errors.append(f"{tool_name}: {str(e)}")
                print(f"[ERROR] 修复失败: {tool_name} - {str(e)}")

        print(f"\n{'='*60}")
        print(f"修复完成: {len(fixed_tools)} 个工具已修复")
        if errors:
            print(f"修复失败: {len(errors)} 个工具")
        print(f"{'='*60}\n")

        return {
            "fixed_tools": fixed_tools,
            "errors": errors
        }


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="工具合规性验证脚本 - 验证UDF v1.0和v3.0图表规范"
    )

    parser.add_argument(
        "--tool",
        type=str,
        help="验证指定工具"
    )

    parser.add_argument(
        "--fix",
        action="store_true",
        help="自动修复常见问题"
    )

    parser.add_argument(
        "--export",
        type=str,
        metavar="OUTPUT_PATH",
        help="导出验证报告为JSON"
    )

    args = parser.parse_args()

    validator = ToolComplianceValidator()

    # 验证单个工具
    if args.tool:
        print(f"\n验证工具: {args.tool}")
        result = validator.validate_tool(args.tool)

        if result["valid"]:
            print("[OK] 工具符合规范")
        else:
            print("[ERROR] 工具不符合规范:")
            for error in result["errors"]:
                print(f"  - 错误: {error}")
            for warning in result["warnings"]:
                print(f"  - 警告: {warning}")
        return

    # 自动修复
    if args.fix:
        validator.auto_fix()
        return

    # 验证所有工具
    summary = validator.validate_all_tools()

    # 导出报告
    if args.export:
        validator.export_report(args.export)

    # 退出码
    if summary["failed_tools"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
