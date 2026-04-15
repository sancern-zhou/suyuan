#!/usr/bin/env python3
"""
站点地理信息更新验证脚本

功能：
1. 验证更新后的JSON文件的数据完整性
2. 对比更新前后的差异
3. 生成详细的验证报告
4. 检查是否有遗漏或错误
"""

import json
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime
import structlog

# 配置日志
logger = structlog.get_logger()


class StationGeoValidator:
    """站点地理信息验证器"""

    def __init__(self, original_json: str, updated_json: str):
        """
        初始化验证器

        Args:
            original_json: 原始JSON文件路径
            updated_json: 更新后的JSON文件路径
        """
        self.original_json = original_json
        self.updated_json = updated_json
        self.original_data = None
        self.updated_data = None

        # 验证结果
        self.validation_results = {
            "total_stations": 0,
            "missing_fields_before": {},
            "missing_fields_after": {},
            "updated_stations": [],
            "unchanged_stations": [],
            "errors": []
        }

    def load_json_files(self) -> None:
        """加载JSON文件"""
        logger.info("加载JSON文件")

        try:
            with open(self.original_json, 'r', encoding='utf-8') as f:
                orig_data = json.load(f)
            self.original_data = orig_data.get("data", [])

            with open(self.updated_json, 'r', encoding='utf-8') as f:
                upd_data = json.load(f)
            self.updated_data = upd_data.get("data", [])

            self.validation_results["total_stations"] = len(self.updated_data)

            logger.info(
                "JSON文件加载完成",
                original_count=len(self.original_data),
                updated_count=len(self.updated_data)
            )

        except Exception as e:
            logger.error("加载JSON文件失败", error=str(e))
            raise

    def check_missing_fields(self, station: Dict[str, Any]) -> List[str]:
        """
        检查站点缺失的字段

        Args:
            station: 站点数据

        Returns:
            缺失字段列表
        """
        required_fields = [
            "站点名称",
            "唯一编码",
            "城市名称",
            "经度",
            "纬度",
            "区县",
            "详细地址",
            "省份",
            "城市",
            "乡镇",
            "行政区划代码",
            "站点类型ID"
        ]

        missing = []
        for field in required_fields:
            value = station.get(field)
            if value is None or value == "":
                missing.append(field)

        return missing

    def validate(self) -> None:
        """执行验证"""
        logger.info("开始验证更新结果")

        # 检查更新前的缺失字段
        for station in self.original_data:
            missing = self.check_missing_fields(station)
            for field in missing:
                if field not in self.validation_results["missing_fields_before"]:
                    self.validation_results["missing_fields_before"][field] = 0
                self.validation_results["missing_fields_before"][field] += 1

        # 检查更新后的缺失字段和变化
        for i, updated_station in enumerate(self.updated_data):
            # 检查缺失字段
            missing_after = self.check_missing_fields(updated_station)
            for field in missing_after:
                if field not in self.validation_results["missing_fields_after"]:
                    self.validation_results["missing_fields_after"][field] = 0
                self.validation_results["missing_fields_after"][field] += 1

            # 对比变化
            if i < len(self.original_data):
                original_station = self.original_data[i]
                changes = self.compare_stations(original_station, updated_station)

                if changes:
                    self.validation_results["updated_stations"].append({
                        "station_name": updated_station.get("站点名称"),
                        "station_code": updated_station.get("唯一编码"),
                        "changes": changes
                    })
                else:
                    self.validation_results["unchanged_stations"].append({
                        "station_name": updated_station.get("站点名称"),
                        "station_code": updated_station.get("唯一编码")
                    })

        logger.info("验证完成")

    def compare_stations(self, original: Dict[str, Any], updated: Dict[str, Any]) -> Dict[str, Any]:
        """
        对比两个站点的差异

        Args:
            original: 原始站点数据
            updated: 更新后的站点数据

        Returns:
            变化字段字典
        """
        changes = {}

        for key in updated.keys():
            orig_value = original.get(key)
            upd_value = updated.get(key)

            if orig_value != upd_value:
                changes[key] = {
                    "before": orig_value,
                    "after": upd_value
                }

        return changes

    def generate_report(self, output_path: str) -> None:
        """
        生成验证报告

        Args:
            output_path: 报告输出路径
        """
        logger.info("生成验证报告", path=output_path)

        report_lines = []
        report_lines.append("="*80)
        report_lines.append("站点地理信息更新验证报告")
        report_lines.append("="*80)
        report_lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("")

        # 总体统计
        report_lines.append("## 总体统计")
        report_lines.append(f"站点总数: {self.validation_results['total_stations']}")
        report_lines.append(f"已更新站点数: {len(self.validation_results['updated_stations'])}")
        report_lines.append(f"未变化站点数: {len(self.validation_results['unchanged_stations'])}")
        report_lines.append("")

        # 缺失字段统计
        report_lines.append("## 缺失字段统计")
        report_lines.append("### 更新前")
        for field, count in sorted(self.validation_results["missing_fields_before"].items()):
            report_lines.append(f"  - {field}: {count} 个站点缺失")

        report_lines.append("\n### 更新后")
        if self.validation_results["missing_fields_after"]:
            for field, count in sorted(self.validation_results["missing_fields_after"].items()):
                report_lines.append(f"  - {field}: {count} 个站点仍缺失")
        else:
            report_lines.append("  ✅ 所有字段都已补充完整！")

        report_lines.append("")

        # 更新详情
        report_lines.append("## 更新详情")
        report_lines.append(f"共 {len(self.validation_results['updated_stations'])} 个站点有更新")
        report_lines.append("")

        # 按城市统计更新
        city_updates = {}
        for update in self.validation_results["updated_stations"]:
            # 从 updated_data 中查找城市
            station_code = update["station_code"]
            city = "未知"
            for station in self.updated_data:
                if station.get("唯一编码") == station_code:
                    city = station.get("城市名称", "未知")
                    break

            if city not in city_updates:
                city_updates[city] = []
            city_updates[city].append(update)

        report_lines.append("### 按城市统计")
        for city in sorted(city_updates.keys()):
            report_lines.append(f"{city}: {len(city_updates[city])} 个站点")

        report_lines.append("")

        # 详细变化（前20个）
        report_lines.append("### 详细变化示例（前20个）")
        for i, update in enumerate(self.validation_results["updated_stations"][:20]):
            report_lines.append(f"\n{i+1}. {update['station_name']} ({update['station_code']})")
            for field, change in update["changes"].items():
                report_lines.append(f"   - {field}: {change['before']} → {change['after']}")

        if len(self.validation_results["updated_stations"]) > 20:
            report_lines.append(f"\n... 还有 {len(self.validation_results['updated_stations']) - 20} 个站点")

        report_lines.append("")
        report_lines.append("="*80)

        # 保存报告
        report_text = "\n".join(report_lines)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_text)

        # 打印到控制台
        print(report_text)

        logger.info("验证报告已生成", path=output_path)


def main():
    """主函数"""
    # 配置路径
    project_root = Path(__file__).parent.parent
    original_json = project_root / "config" / "station_district_results_with_type_id.json"
    updated_json = project_root / "config" / "station_district_results_with_type_id_updated.json"
    report_path = project_root / "config" / "station_geo_update_report.txt"

    print("站点地理信息更新验证工具")
    print("="*80)

    # 创建验证器
    validator = StationGeoValidator(str(original_json), str(updated_json))

    # 1. 加载JSON文件
    print(f"\n[1/3] 加载JSON文件...")
    validator.load_json_files()

    # 2. 执行验证
    print(f"\n[2/3] 执行验证...")
    validator.validate()

    # 3. 生成报告
    print(f"\n[3/3] 生成验证报告...")
    validator.generate_report(str(report_path))

    print(f"\n验证报告已保存到: {report_path}")


if __name__ == "__main__":
    main()
