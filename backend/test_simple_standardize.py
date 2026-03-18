"""
简化测试：直接调用standardize方法
"""

import sys
from pathlib import Path
import io

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# 重定向stderr到文件，捕获所有输出
sys.stderr = io.StringIO()
sys.stdout = io.StringIO()

from app.utils.data_standardizer import get_data_standardizer

# 模拟API返回的数据
api_records = [
    {
        "Code": "1067b",
        "StationName": "深南中路",
        "TimePoint": "2026-02-01 00:00:00",
        "SO4²⁻": 8.5,
        "NO₃⁻": 12.3,
        "NH₄⁺": 6.7,
        "PM2_5": 35.5
    }
]

output_file = Path(__file__).parent / "simple_test_result.txt"

with open(output_file, 'w', encoding='utf-8') as f:
    f.write("Simple Standardization Test\n")
    f.write("=" * 80 + "\n\n")

    try:
        standardizer = get_data_standardizer()
        f.write("Standardizer created\n")

        result = standardizer.standardize(api_records)
        f.write(f"Standardization completed\n")
        f.write(f"Result count: {len(result)}\n\n")

        if result:
            first = result[0]
            f.write("First record fields:\n")
            for key, value in first.items():
                if isinstance(value, dict):
                    f.write(f"  {key}: (dict, {len(value)} items)\n")
                    for k, v in value.items():
                        f.write(f"    {k}: {v}\n")
                else:
                    f.write(f"  {key}: {value}\n")

            if "components" in first and first["components"]:
                f.write(f"\nSUCCESS: Components has {len(first['components'])} items\n")
            else:
                f.write(f"\nFAILURE: Components is empty or missing\n")

    except Exception as e:
        f.write(f"ERROR: {e}\n")
        f.write(f"Error type: {type(e).__name__}\n")
        import traceback
        f.write(traceback.format_exc())

print(f"Results written to: {output_file}")
