"""
Phase 2-5: Integration Testing and Optimization

轨迹分析Phase 2集成测试
测试场景：
1. 不同起始高度（100m, 500m, 1000m）
2. 不同回溯时间（24h, 48h, 72h）
3. 验证visuals数量和类型
4. 性能基准测试
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.trajectory.trajectory_calculator import TrajectoryCalculatorService


async def test_scenario(name: str, lat: float, lon: float, height: int, hours: int):
    """测试单个场景"""
    print(f"\n{'=' * 60}")
    print(f"Scenario: {name}")
    print(f"  Location: ({lat}, {lon})")
    print(f"  Height: {height}m")
    print(f"  Hours: {hours}h")
    print(f"{'=' * 60}")

    service = TrajectoryCalculatorService()
    start_time = datetime(2024, 10, 1, 12, 0, 0)

    start = time.time()
    result = await service.calculate_backward_trajectory(
        lat=lat,
        lon=lon,
        start_time=start_time,
        hours=hours,
        height=height
    )
    elapsed = time.time() - start

    if not result.get("success"):
        print(f"[ERROR] {result.get('error')}")
        return None

    # 分析结果
    heights = [p["height"] for p in result["data"]]
    stats = result["metadata"]["trajectory_stats"]

    print(f"\n[RESULTS]")
    print(f"  Execution time: {elapsed:.2f}s")
    print(f"  Trajectory points: {len(result['data'])}")
    print(f"  Visuals count: {len(result['visuals'])}")
    print(f"  Visuals types: {', '.join([v['payload']['type'] for v in result['visuals']])}")
    print(f"\n  Height variation:")
    print(f"    Initial: {heights[0]}m")
    print(f"    Final: {heights[-1]:.0f}m")
    print(f"    Range: {stats['min_height_m']:.0f}m - {stats['max_height_m']:.0f}m")
    print(f"    Delta: {heights[-1] - heights[0]:.0f}m")
    print(f"\n  Trajectory stats:")
    print(f"    Distance: {stats['total_distance_km']:.1f}km")
    print(f"    Direction: {stats['dominant_direction']}")
    print(f"    Avg speed: {stats['avg_speed_ms']:.1f} m/s")

    # 验证
    checks = []
    checks.append(("Visuals count", len(result['visuals']) == 2, "2 visuals (map + profile)"))
    checks.append(("Height variation", len(set(heights)) > 1, "Height varies"))
    checks.append(("Algorithm version", "phase2" in stats.get("algorithm", "").lower() or \
                   result["metadata"].get("analysis_params", {}).get("algorithm", "") == "simplified_lagrangian_phase2",
                   "Phase 2 algorithm"))
    checks.append(("Performance", elapsed < 30, "< 30s execution time"))

    print(f"\n[VALIDATION]")
    all_passed = True
    for check_name, passed, description in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {check_name}: {description}")
        all_passed = all_passed and passed

    return {
        "name": name,
        "success": result.get("success"),
        "elapsed": elapsed,
        "points": len(result["data"]),
        "visuals": len(result["visuals"]),
        "height_delta": heights[-1] - heights[0],
        "distance_km": stats["total_distance_km"],
        "all_checks_passed": all_passed
    }


async def run_integration_tests():
    """运行所有集成测试"""
    print("=" * 80)
    print("PHASE 2-5: INTEGRATION TESTING")
    print("=" * 80)

    # 测试场景
    scenarios = [
        # 不同起始高度
        ("Low altitude (100m)", 23.13, 113.26, 100, 72),
        ("Medium altitude (500m)", 23.13, 113.26, 500, 72),
        ("High altitude (1000m)", 23.13, 113.26, 1000, 72),

        # 不同回溯时间
        ("Short duration (24h)", 23.13, 113.26, 100, 24),
        ("Medium duration (48h)", 23.13, 113.26, 100, 48),

        # 不同位置
        ("Beijing", 39.9, 116.4, 100, 72),
    ]

    results = []
    for scenario in scenarios:
        result = await test_scenario(*scenario)
        if result:
            results.append(result)
        await asyncio.sleep(1)  # 避免API限流

    # 生成总结报告
    print(f"\n{'=' * 80}")
    print("INTEGRATION TEST SUMMARY")
    print(f"{'=' * 80}")

    print(f"\n{'Scenario':<30} {'Status':<10} {'Time(s)':<10} {'Points':<10} {'Visuals':<10} {'Height Δ':<12}")
    print(f"{'-' * 95}")

    for result in results:
        status = "PASS" if result["all_checks_passed"] else "FAIL"
        print(f"{result['name']:<30} {status:<10} {result['elapsed']:<10.2f} "
              f"{result['points']:<10} {result['visuals']:<10} {result['height_delta']:<12.0f}m")

    # 性能统计
    avg_time = sum(r["elapsed"] for r in results) / len(results)
    max_time = max(r["elapsed"] for r in results)
    min_time = min(r["elapsed"] for r in results)

    print(f"\n[PERFORMANCE METRICS]")
    print(f"  Average execution time: {avg_time:.2f}s")
    print(f"  Min execution time: {min_time:.2f}s")
    print(f"  Max execution time: {max_time:.2f}s")
    print(f"  All under 30s target: {max_time < 30}")

    # 成功率
    success_count = sum(1 for r in results if r["all_checks_passed"])
    success_rate = (success_count / len(results)) * 100

    print(f"\n[TEST RESULTS]")
    print(f"  Total scenarios: {len(results)}")
    print(f"  Passed: {success_count}")
    print(f"  Failed: {len(results) - success_count}")
    print(f"  Success rate: {success_rate:.1f}%")

    # 保存结果
    output_file = Path(__file__).parent / "phase2_integration_test_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "test_date": datetime.now().isoformat(),
            "phase": "2.0",
            "scenarios_count": len(results),
            "success_rate": success_rate,
            "performance": {
                "avg_time": avg_time,
                "min_time": min_time,
                "max_time": max_time
            },
            "scenarios": results
        }, f, indent=2, ensure_ascii=False)

    print(f"\n[FILE] Results saved to: {output_file}")

    print("=" * 80)

    return success_rate >= 80.0  # 80%通过率为合格


if __name__ == "__main__":
    success = asyncio.run(run_integration_tests())
    exit(0 if success else 1)
