"""
端到端测试PM2.5数据流
模拟从API响应到最终存储的完整流程
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# 禁用structlog输出到控制台，避免编码问题
import structlog
import logging
import sys
import io

# 完全禁用日志输出
logging.disable(logging.CRITICAL)
structlog.configure(
    processors=[],
    wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(file=io.StringIO()),  # 输出到内存
    cache_logger_on_first_use=False,
)

from app.utils.data_standardizer import get_data_standardizer
from app.schemas.particulate import UnifiedParticulateData


def test_end_to_end():
    """端到端测试"""

    output_file = Path(__file__).parent / "end_to_end_test_result.txt"

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("End-to-End PM2.5 Data Flow Test\n")
        f.write("=" * 80 + "\n\n")

        # 步骤1：模拟API返回的原始数据（Unicode上标格式）
        f.write("Step 1: API Response (Unicode superscript format)\n")
        f.write("-" * 80 + "\n")

        api_response = [
            {
                "Code": "1067b",
                "StationName": "深南中路",
                "TimePoint": "2026-02-01 00:00:00",
                "SO4²⁻": 8.5,
                "NO₃⁻": 12.3,
                "NH₄⁺": 6.7,
                "Cl⁻": 1.2,
                "Ca²⁺": 2.3,
                "Mg²⁺": 0.8,
                "K⁺": 1.5,
                "Na⁺": 1.1,
                "PM2_5": 35.5
            }
        ]

        f.write(f"Record count: {len(api_response)}\n")
        f.write(f"First record fields:\n")
        for key, value in api_response[0].items():
            f.write(f"  {key}: {value}\n")

        # 步骤2：数据标准化
        f.write("\n" + "=" * 80 + "\n")
        f.write("Step 2: Data Standardization\n")
        f.write("-" * 80 + "\n")

        try:
            standardizer = get_data_standardizer()
            standardized_data = standardizer.standardize(api_response)
        except UnicodeEncodeError as e:
            # Windows控制台编码问题，但数据应该已经标准化
            f.write(f"WARNING: UnicodeEncodeError during logging (expected on Windows)\n")
            f.write(f"Attempting to retrieve standardized data...\n")
            # 直接调用内部方法，跳过日志
            standardizer = get_data_standardizer()
            standardized_data = []
            for record in api_response:
                try:
                    std_record = standardizer._standardize_record(record)
                    if std_record:
                        standardized_data.append(std_record)
                except Exception as inner_e:
                    f.write(f"ERROR in _standardize_record: {inner_e}\n")
                    standardized_data = api_response  # 使用原始数据

        f.write(f"Standardized record count: {len(standardized_data)}\n")
        if standardized_data:
            first_std = standardized_data[0]
            f.write(f"\nStandardized fields:\n")
            for key, value in first_std.items():
                if isinstance(value, dict):
                    f.write(f"  {key}: (dict, {len(value)} items)\n")
                    for sub_key, sub_value in value.items():
                        f.write(f"    {sub_key}: {sub_value}\n")
                else:
                    f.write(f"  {key}: {value}\n")

            # 检查components
            if "components" in first_std:
                components = first_std["components"]
                f.write(f"\nComponents field exists: YES\n")
                f.write(f"Components count: {len(components)}\n")
                if not components:
                    f.write("WARNING: Components dict is EMPTY!\n")
            else:
                f.write(f"\nComponents field exists: NO\n")

        # 步骤3：from_raw_data转换
        f.write("\n" + "=" * 80 + "\n")
        f.write("Step 3: UnifiedParticulateData.from_raw_data() Conversion\n")
        f.write("-" * 80 + "\n")

        if standardized_data:
            unified_record = UnifiedParticulateData.from_raw_data(standardized_data[0])
            unified_dict = unified_record.model_dump()

            f.write(f"Unified record fields:\n")
            for key, value in unified_dict.items():
                if isinstance(value, dict):
                    f.write(f"  {key}: (dict, {len(value)} items)\n")
                    if value:
                        for sub_key, sub_value in value.items():
                            f.write(f"    {sub_key}: {sub_value}\n")
                    else:
                        f.write(f"    (EMPTY DICT)\n")
                else:
                    f.write(f"  {key}: {value}\n")

            # 最终检查
            f.write("\n" + "=" * 80 + "\n")
            f.write("Final Check\n")
            f.write("-" * 80 + "\n")

            final_components = unified_dict.get("components", {})
            if final_components:
                f.write(f"SUCCESS: Final components count = {len(final_components)}\n")
                f.write(f"Components: {list(final_components.keys())}\n")
            else:
                f.write(f"FAILURE: Final components is EMPTY!\n")
                f.write(f"\nDiagnostics:\n")
                f.write(f"  - API response had {len([k for k in api_response[0].keys() if k not in ['Code', 'StationName', 'TimePoint', 'PM2_5']])} component fields\n")
                f.write(f"  - After standardization: {len(standardized_data[0].get('components', {}))} components\n")
                f.write(f"  - After from_raw_data: {len(final_components)} components\n")

        f.write("\n" + "=" * 80 + "\n")

    print(f"Results written to: {output_file}")


if __name__ == "__main__":
    test_end_to_end()
