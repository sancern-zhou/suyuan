"""
AQI日历图生成器 - execute_python 调用示例

展示如何通过 execute_python 工具生成 AQI 日历图。

使用方法：
    在 LLM 对话中，使用 execute_python 工具执行以下代码：

    ```python
    from backend.app.tools.visualization.generate_aqi_calendar.calendar_renderer import generate_calendar_from_data_id

    # 生成日历图
    img_base64 = generate_calendar_from_data_id(
        data_id="air_quality_unified:v1:xxx",
        year=2026,
        month=4,
        pollutant="PM10",
        cities=["广州", "深圳", "珠海", "佛山", "东莞"]
    )

    # 输出图表（自动添加到 visuals）
    print("CHART_SAVED:data:image/png;base64," + img_base64)
    ```

返回格式：
    {
        "status": "success",
        "success": true,
        "data": {
            "output": "CHART_SAVED:data:image/png;base64,...",
            "engine": "ipython"
        },
        "visuals": [
            {
                "id": "matplotlib_xxx",
                "type": "image",
                "title": "图表 tmpxxx",
                "data": {
                    "url": "/api/image/matplotlib_xxx",
                    "image_id": "matplotlib_xxx"
                },
                "meta": {
                    "generator": "execute_python",
                    "schema_version": "3.1"
                }
            }
        ],
        "summary": "✅ 工具已执行完成，图表生成成功：![Chart](/api/image/...)"
    }
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))


def example_basic_usage():
    """示例1：基本用法"""
    print("=" * 60)
    print("示例1：生成 AQI 日历图（基本用法）")
    print("=" * 60)

    code = '''
from backend.app.tools.visualization.generate_aqi_calendar.calendar_renderer import generate_calendar_from_data_id

# 生成日历图
img_base64 = generate_calendar_from_data_id(
    data_id="air_quality_unified:v1:xxx",
    year=2026,
    month=4,
    pollutant="PM10"
)

# 输出图表（自动添加到 visuals）
print("CHART_SAVED:data:image/png;base64," + img_base64)
'''

    print(code)
    print()


def example_multi_city():
    """示例2：多城市对比"""
    print("=" * 60)
    print("示例2：多城市对比日历图")
    print("=" * 60)

    code = '''
from backend.app.tools.visualization.generate_aqi_calendar.calendar_renderer import generate_calendar_from_data_id

# 生成珠三角9城市日历图
cities = ["广州", "深圳", "珠海", "佛山", "东莞", "中山", "江门", "惠州", "肇庆"]

img_base64 = generate_calendar_from_data_id(
    data_id="air_quality_unified:v1:xxx",
    year=2026,
    month=4,
    pollutant="AQI",
    cities=cities
)

print("CHART_SAVED:data:image/png;base64," + img_base64)
'''

    print(code)
    print()


def example_pollutants():
    """示例3：不同污染物"""
    print("=" * 60)
    print("示例3：不同污染物日历图")
    print("=" * 60)

    code = '''
from backend.app.tools.visualization.generate_aqi_calendar.calendar_renderer import generate_calendar_from_data_id

# 支持的污染物指标
pollutants = ["AQI", "SO2", "NO2", "CO", "O3_8h", "PM2_5", "PM10"]

for pollutant in pollutants:
    img_base64 = generate_calendar_from_data_id(
        data_id="air_quality_unified:v1:xxx",
        year=2026,
        month=4,
        pollutant=pollutant,
        cities=["广州", "深圳"]
    )

    print(f"CHART_SAVED:data:image/png;base64,{img_base64}")
    print(f"# {pollutant} 日历图生成完成")
'''

    print(code)
    print()


def example_error_handling():
    """示例4：错误处理"""
    print("=" * 60)
    print("示例4：错误处理")
    print("=" * 60)

    code = '''
from backend.app.tools.visualization.generate_aqi_calendar.calendar_renderer import generate_calendar_from_data_id

try:
    # 测试错误的数据 ID
    img_base64 = generate_calendar_from_data_id(
        data_id="invalid_data_id",
        year=2026,
        month=4,
        pollutant="PM10"
    )
except ValueError as e:
    print(f"错误：{e}")
    # 可以继续处理其他数据
'''

    print(code)
    print()


def example_comparison_with_polar():
    """示例5：与极坐标图对比"""
    print("=" * 60)
    print("示例5：与极坐标风玫瑰图对比")
    print("=" * 60)

    code = '''
# 日历图：时间维度展示
from backend.app.tools.visualization.generate_aqi_calendar.calendar_renderer import generate_calendar_from_data_id

calendar_img = generate_calendar_from_data_id(
    data_id="air_quality_unified:v1:xxx",
    year=2026,
    month=4,
    pollutant="PM10"
)

print("CHART_SAVED:data:image/png;base64," + calendar_img)
print("# 日历图：展示整个月每天的 PM10 浓度变化")

# 极坐标图：风向-风速-浓度关系
from backend.app.tools.visualization.polar_contour_generator import generate_pollution_rose_contour

polar_img = generate_pollution_rose_contour(
    data_id="air_quality_5min:v1:xxx",
    pollutant_name="PM10"
)

print("CHART_SAVED:data:image/png;base64," + polar_img)
print("# 极坐标图：展示不同风向和风速下的 PM10 浓度分布")
'''

    print(code)
    print()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("AQI 日历图 - execute_python 调用示例")
    print("=" * 60 + "\n")

    example_basic_usage()
    example_multi_city()
    example_pollutants()
    example_error_handling()
    example_comparison_with_polar()

    print("=" * 60)
    print("使用说明")
    print("=" * 60)
    print("""
1. 在 LLM 对话中，使用 execute_python 工具
2. 将上述代码复制到工具的 code 参数中
3. 替换 data_id 为实际的数据 ID
4. 执行后会自动生成图表并添加到 visuals 字段
5. 前端 VisualizationPanel 会自动渲染图表

关键优势：
- ✅ 统一接口：与 polar_contour_generator 一致的调用方式
- ✅ 灵活性：可通过 execute_python 灵活调用
- ✅ 返回格式：自动添加到 visuals，前端可直接渲染
- ✅ 参数简化：只需要 data_id, year, month, pollutant
""")
