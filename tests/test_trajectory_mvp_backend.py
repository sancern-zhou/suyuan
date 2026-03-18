"""
HYSPLIT Trajectory Analysis MVP - Backend Test Script

测试脚本用于验证MVP后端功能：
1. 轨迹计算服务能否正常工作
2. 返回数据是否符合UDF v2.0格式
3. 轨迹地图配置是否正确生成

运行方法：
python tests/test_trajectory_mvp_backend.py
"""

import asyncio
from datetime import datetime
import json
import sys
import os

# 添加backend目录到Python路径
backend_path = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, backend_path)

from app.services.trajectory.trajectory_calculator import TrajectoryCalculatorService


async def test_trajectory_calculator_service():
    """测试轨迹计算服务"""

    print("\n" + "="*80)
    print("HYSPLIT轨迹分析MVP - 后端测试")
    print("="*80 + "\n")

    # 初始化服务
    print("[1/4] 初始化轨迹计算服务...")
    service = TrajectoryCalculatorService()
    print("[OK] 轨迹计算服务初始化成功\n")

    # 测试参数
    print("[2/4] 设置测试参数...")
    lat = 23.13  # 广州
    lon = 113.26
    # 使用过去的日期（ERA5是历史数据，不能查询未来）
    start_time = datetime(2024, 10, 1, 12, 0, 0)  # 2024年10月1日
    hours = 72  # 72小时反向轨迹
    height = 100  # 100米起始高度

    print(f"  - 起点坐标: ({lat}, {lon})")
    print(f"  - 起始时间: {start_time.isoformat()}")
    print(f"  - 回溯时长: {hours}小时")
    print(f"  - 起始高度: {height}米\n")

    # 执行轨迹计算
    print("[3/4] 执行轨迹计算...")
    print("  - 获取ERA5气象数据...")
    print("  - 运行HYSPLIT轨迹算法...")
    print("  - 生成轨迹地图配置...\n")

    result = await service.calculate_backward_trajectory(
        lat=lat,
        lon=lon,
        start_time=start_time,
        hours=hours,
        height=height
    )

    # 验证结果
    print("[4/4] 验证结果...\n")

    # 检查基本状态
    assert result.get("success") == True, "计算失败"
    print("[OK] 轨迹计算成功")

    # 检查UDF v2.0格式
    assert result.get("status") == "success", "状态码不正确"
    assert "metadata" in result, "缺少metadata字段"
    assert result["metadata"].get("schema_version") == "v2.0", "不是UDF v2.0格式"
    print("[OK] 返回数据符合UDF v2.0格式")

    # 检查轨迹数据
    assert "data" in result, "缺少data字段"
    trajectory_points = result["data"]
    assert len(trajectory_points) > 0, "轨迹点为空"
    print(f"[OK] 轨迹数据完整：共{len(trajectory_points)}个轨迹点")

    # 检查可视化配置
    assert "visuals" in result, "缺少visuals字段"
    visuals = result["visuals"]
    assert len(visuals) > 0, "可视化配置为空"

    map_visual = visuals[0]
    assert map_visual.get("type") == "map", "不是地图配置"
    assert "payload" in map_visual, "缺少payload字段"

    map_data = map_visual["payload"]["data"]
    assert "map_center" in map_data, "缺少地图中心"
    assert "layers" in map_data, "缺少图层配置"

    print(f"[OK] 轨迹地图配置正确生成")

    # 检查轨迹统计
    stats = result["metadata"]["trajectory_stats"]
    print(f"\n" + "-"*80)
    print("轨迹统计信息:")
    print(f"  - 主导方向: {stats['dominant_direction']}")
    print(f"  - 总距离: {stats['total_distance_km']:.2f} 公里")
    print(f"  - 平均速度: {stats['avg_speed_ms']:.2f} m/s")
    print(f"  - 最大高度: {stats['max_height_m']:.1f} 米")
    print(f"  - 轨迹点数: {stats['trajectory_points']}")
    print("-"*80 + "\n")

    # 打印摘要
    print("="*80)
    print("测试结果摘要")
    print("="*80)
    print(f"[OK] 所有测试通过")
    print(f"[OK] {result.get('summary', 'MVP测试完成')}")
    print("="*80 + "\n")

    # 保存测试结果到文件
    output_file = "tests/trajectory_mvp_test_result.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[FILE] 完整结果已保存到: {output_file}\n")

    return result


if __name__ == "__main__":
    try:
        result = asyncio.run(test_trajectory_calculator_service())
        print("\n[SUCCESS] MVP后端测试全部通过！\n")

        print("下一步：")
        print("  1. 前端：实现轨迹地图组件（TrajectoryMapPanel.vue）")
        print("  2. 前端：集成到VisualizationPanel")
        print("  3. 端到端测试：通过ReAct Agent调用工具\n")

        sys.exit(0)

    except Exception as e:
        print(f"\n[ERROR] 测试失败: {str(e)}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
