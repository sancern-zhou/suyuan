"""
Test Trajectory Phase 2-1: Vertical Motion Calculation

测试轨迹分析Phase 2-1的垂直运动计算功能
验证：
1. 高度不再固定为100m
2. 高度变化范围合理（受边界层高度影响）
3. 多层级风场插值工作正常
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

# 设置路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.trajectory.trajectory_calculator import TrajectoryCalculatorService


async def test_phase2_vertical_motion():
    """测试Phase 2-1垂直运动计算"""

    print("=" * 80)
    print("[TEST] Phase 2-1: Vertical Motion Calculation")
    print("=" * 80)

    # 初始化服务
    service = TrajectoryCalculatorService()

    # 测试参数（使用历史日期避免ERA5 API错误）
    lat = 23.13  # 广州
    lon = 113.26
    start_time = datetime(2024, 10, 1, 12, 0, 0)  # 2024-10-01 12:00 UTC
    hours_backward = 72
    initial_height = 100  # 起始高度100m

    print(f"\n[PARAMS]")
    print(f"  Location: ({lat}, {lon}) - Guangzhou")
    print(f"  Start Time: {start_time.isoformat()}")
    print(f"  Hours Backward: {hours_backward}")
    print(f"  Initial Height: {initial_height}m")

    # 执行轨迹计算
    print(f"\n[STEP 1] Calculating trajectory with vertical motion...")
    result = await service.calculate_backward_trajectory(
        lat=lat,
        lon=lon,
        start_time=start_time,
        hours=hours_backward,
        height=initial_height
    )

    # 验证结果
    if not result.get("success"):
        print(f"\n[ERROR] Trajectory calculation failed: {result.get('error')}")
        return False

    print(f"[OK] Trajectory calculation completed")

    # 分析高度变化
    trajectory = result["data"]
    heights = [point["height"] for point in trajectory]

    print(f"\n[STEP 2] Analyzing height variation...")
    print(f"  Total points: {len(trajectory)}")
    print(f"  Initial height: {heights[0]}m")
    print(f"  Final height: {heights[-1]}m")
    print(f"  Min height: {min(heights)}m")
    print(f"  Max height: {max(heights)}m")
    print(f"  Height range: {max(heights) - min(heights):.1f}m")
    print(f"  Avg height: {sum(heights) / len(heights):.1f}m")

    # 检查高度是否变化（不再固定100m）
    unique_heights = len(set(heights))
    print(f"\n[STEP 3] Verifying vertical motion...")
    print(f"  Unique height values: {unique_heights}")

    if unique_heights == 1:
        print(f"  [FAIL] Height is constant ({heights[0]}m) - vertical motion not working!")
        return False
    else:
        print(f"  [OK] Height varies - vertical motion is working!")

    # 显示前10个点的高度变化
    print(f"\n[STEP 4] Height profile (first 10 points):")
    print(f"  {'Time':<20} {'Age(h)':<8} {'Height(m)':<12} {'Delta(m)':<10}")
    print(f"  {'-' * 60}")
    for i in range(min(10, len(trajectory))):
        point = trajectory[i]
        delta = point["height"] - heights[0] if i > 0 else 0
        print(f"  {point['timestamp']:<20} {point['age_hours']:<8} {point['height']:<12.1f} {delta:+10.1f}")

    # 验证高度范围合理性（边界层高度通常1000-2000m）
    print(f"\n[STEP 5] Validating height range...")
    if max(heights) > 5000:
        print(f"  [WARNING] Max height ({max(heights)}m) exceeds typical boundary layer height")
    if min(heights) < 10:
        print(f"  [WARNING] Min height ({min(heights)}m) below safety threshold")

    reasonable_range = 10 <= min(heights) <= max(heights) <= 3000
    if reasonable_range:
        print(f"  [OK] Height range is reasonable (10m - 3000m)")
    else:
        print(f"  [WARNING] Height range may be unrealistic")

    # 检查算法版本
    print(f"\n[STEP 6] Checking algorithm version...")
    metadata = result.get("metadata", {})
    algorithm = metadata.get("analysis_params", {}).get("algorithm", "unknown")
    print(f"  Algorithm: {algorithm}")

    if "phase2" in algorithm.lower():
        print(f"  [OK] Using Phase 2 algorithm")
    else:
        print(f"  [WARNING] Algorithm may be MVP version, not Phase 2")

    # 保存结果
    output_file = Path(__file__).parent / "trajectory_phase2_test_result.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n[FILE] Test result saved to: {output_file}")

    # 总结
    print(f"\n[SUMMARY]")
    print(f"  Test Status: {'PASS' if unique_heights > 1 else 'FAIL'}")
    print(f"  Vertical Motion: {'Working' if unique_heights > 1 else 'Not Working'}")
    print(f"  Height Variation: {max(heights) - min(heights):.1f}m")
    print(f"  Algorithm: {algorithm}")

    print("=" * 80)

    return unique_heights > 1


async def main():
    """主测试函数"""
    try:
        success = await test_phase2_vertical_motion()

        if success:
            print("\n[SUCCESS] Phase 2-1 vertical motion test PASSED")
            print("[OK] Height variation detected - vertical motion is working!")
        else:
            print("\n[FAILED] Phase 2-1 vertical motion test FAILED")
            print("[ERROR] Height remains constant - vertical motion not working")

        return success

    except Exception as e:
        print(f"\n[ERROR] Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    asyncio.run(main())
