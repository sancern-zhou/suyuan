"""
Phase 2-3: Forward Trajectory Prediction Testing

正向轨迹预测测试
测试场景：
1. 不同预测时长（24h, 48h, 72h）
2. 不同起始高度（100m, 500m, 1000m）
3. 不同位置（广州、北京）
4. 可视化生成验证（地图+剖面图）
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.trajectory.trajectory_calculator import TrajectoryCalculatorService


async def test_forward_trajectory_basic():
    """测试基础正向轨迹预测（72小时）"""
    print("\n" + "=" * 60)
    print("TEST 1: Basic Forward Trajectory (72h)")
    print("=" * 60)

    service = TrajectoryCalculatorService()
    start_time = datetime(2024, 10, 1, 12, 0, 0)

    start = time.time()
    result = await service.calculate_forward_trajectory(
        lat=23.13,
        lon=113.26,
        start_time=start_time,
        hours=72,
        height=100
    )
    elapsed = time.time() - start

    print(f"\nExecution time: {elapsed:.2f}s")
    print(f"Success: {result.get('success')}")

    if result.get("success"):
        print(f"\nTrajectory Points: {len(result['data'])}")
        print(f"Visuals Generated: {len(result['visuals'])}")

        # 验证数据结构
        print(f"\nData Structure Validation:")
        print(f"  Schema version: {result['metadata']['schema_version']}")
        print(f"  Generator: {result['metadata']['generator']}")
        print(f"  Scenario: {result['metadata']['scenario']}")

        # 验证轨迹统计
        stats = result['metadata']['trajectory_stats']
        print(f"\nTrajectory Statistics:")
        print(f"  Total distance: {stats['total_distance_km']} km")
        print(f"  Dominant direction: {stats['dominant_direction']}")
        print(f"  Height range: {stats['min_height_m']}m - {stats['max_height_m']}m")

        # 验证时间标签（正向应该是+号）
        first_point = result['data'][0]
        last_point = result['data'][-1]
        print(f"\nTime Labels Validation:")
        print(f"  First point age: {first_point['age_hours']}h (should be 0)")
        print(f"  Last point age: {last_point['age_hours']}h (should be 71)")

        # 验证可视化类型
        print(f"\nVisuals Validation:")
        for visual in result['visuals']:
            print(f"  Type: {visual['type']}, ID: {visual['id']}")
            if visual['type'] == 'map':
                print(f"    Map center: {visual['payload']['data']['map_center']}")
            elif visual['type'] == 'profile':
                print(f"    Profile title: {visual['payload']['title']}")

        print(f"\nSummary: {result.get('summary')}")
    else:
        print(f"ERROR: {result.get('error')}")

    return result


async def test_different_prediction_hours():
    """测试不同预测时长（24h, 48h, 72h）"""
    print("\n" + "=" * 60)
    print("TEST 2: Different Prediction Hours (24h, 48h, 72h)")
    print("=" * 60)

    service = TrajectoryCalculatorService()
    start_time = datetime(2024, 10, 1, 12, 0, 0)

    results = []
    for hours in [24, 48, 72]:
        print(f"\nTesting {hours}h prediction...")

        start = time.time()
        result = await service.calculate_forward_trajectory(
            lat=23.13,
            lon=113.26,
            start_time=start_time,
            hours=hours,
            height=100
        )
        elapsed = time.time() - start

        if result.get("success"):
            stats = result['metadata']['trajectory_stats']
            print(f"  Success: {len(result['data'])} points in {elapsed:.2f}s")
            print(f"  Distance: {stats['total_distance_km']} km")
            print(f"  Direction: {stats['dominant_direction']}")

            results.append({
                "hours": hours,
                "success": True,
                "points_count": len(result['data']),
                "distance_km": stats['total_distance_km'],
                "direction": stats['dominant_direction'],
                "execution_time": elapsed
            })
        else:
            print(f"  Failed: {result.get('error')}")
            results.append({
                "hours": hours,
                "success": False,
                "error": result.get("error")
            })

    return results


async def test_different_heights():
    """测试不同起始高度（100m, 500m, 1000m）"""
    print("\n" + "=" * 60)
    print("TEST 3: Different Starting Heights (100m, 500m, 1000m)")
    print("=" * 60)

    service = TrajectoryCalculatorService()
    start_time = datetime(2024, 10, 1, 12, 0, 0)

    results = []
    for height in [100, 500, 1000]:
        print(f"\nTesting height {height}m...")

        result = await service.calculate_forward_trajectory(
            lat=23.13,
            lon=113.26,
            start_time=start_time,
            hours=72,
            height=height
        )

        if result.get("success"):
            stats = result['metadata']['trajectory_stats']
            print(f"  Success: Height range {stats['min_height_m']}m - {stats['max_height_m']}m")
            print(f"  Distance: {stats['total_distance_km']} km")

            results.append({
                "height": height,
                "success": True,
                "height_range": f"{stats['min_height_m']}-{stats['max_height_m']}m",
                "distance_km": stats['total_distance_km']
            })
        else:
            print(f"  Failed: {result.get('error')}")
            results.append({
                "height": height,
                "success": False,
                "error": result.get("error")
            })

    return results


async def test_different_locations():
    """测试不同位置（广州、北京）"""
    print("\n" + "=" * 60)
    print("TEST 4: Different Locations (Guangzhou, Beijing)")
    print("=" * 60)

    service = TrajectoryCalculatorService()
    start_time = datetime(2024, 10, 1, 12, 0, 0)

    locations = [
        {"name": "Guangzhou", "lat": 23.13, "lon": 113.26},
        {"name": "Beijing", "lat": 39.90, "lon": 116.41}
    ]

    results = []
    for loc in locations:
        print(f"\nTesting location: {loc['name']} ({loc['lat']}, {loc['lon']})...")

        result = await service.calculate_forward_trajectory(
            lat=loc['lat'],
            lon=loc['lon'],
            start_time=start_time,
            hours=72,
            height=100
        )

        if result.get("success"):
            stats = result['metadata']['trajectory_stats']
            print(f"  Success: {stats['total_distance_km']} km, direction: {stats['dominant_direction']}")

            results.append({
                "location": loc['name'],
                "success": True,
                "distance_km": stats['total_distance_km'],
                "direction": stats['dominant_direction']
            })
        else:
            print(f"  Failed: {result.get('error')}")
            results.append({
                "location": loc['name'],
                "success": False,
                "error": result.get("error")
            })

    return results


async def test_visualization_validation():
    """测试可视化生成验证"""
    print("\n" + "=" * 60)
    print("TEST 5: Visualization Generation Validation")
    print("=" * 60)

    service = TrajectoryCalculatorService()
    start_time = datetime(2024, 10, 1, 12, 0, 0)

    result = await service.calculate_forward_trajectory(
        lat=23.13,
        lon=113.26,
        start_time=start_time,
        hours=72,
        height=100
    )

    if not result.get("success"):
        print(f"ERROR: {result.get('error')}")
        return {"success": False, "error": result.get("error")}

    print(f"\nValidating visuals...")

    validation_results = {
        "visuals_count": len(result['visuals']),
        "map_validation": {},
        "profile_validation": {}
    }

    # 验证地图
    map_visual = next((v for v in result['visuals'] if v['type'] == 'map'), None)
    if map_visual:
        print(f"\nMap Visual Validation:")
        print(f"  ID: {map_visual['id']}")
        print(f"  Type: {map_visual['type']}")
        print(f"  Title: {map_visual['payload']['title']}")

        # 验证轨迹颜色（应该是青色 #4ECDC4）
        trajectory = map_visual['payload']['data']['layers'][0]['trajectories'][0]
        color_correct = trajectory['color'] == "#4ECDC4"
        print(f"  Color: {trajectory['color']} ({'PASS' if color_correct else 'FAIL'})")

        # 验证方向箭头
        arrows_enabled = trajectory['direction_arrows']
        print(f"  Direction arrows: {arrows_enabled} ({'PASS' if arrows_enabled else 'FAIL'})")

        # 验证标记点
        markers = map_visual['payload']['data']['layers'][1]['markers']
        start_marker = markers[0]
        end_marker = markers[1]
        print(f"  Start marker: {start_marker['label']}")
        print(f"  End marker: {end_marker['label']}")

        validation_results['map_validation'] = {
            "exists": True,
            "color_correct": color_correct,
            "arrows_enabled": arrows_enabled,
            "markers_count": len(markers)
        }
    else:
        print(f"\nMap visual NOT FOUND!")
        validation_results['map_validation'] = {"exists": False}

    # 验证剖面图
    profile_visual = next((v for v in result['visuals'] if v['type'] == 'profile'), None)
    if profile_visual:
        print(f"\nProfile Visual Validation:")
        print(f"  ID: {profile_visual['id']}")
        print(f"  Type: {profile_visual['type']}")
        print(f"  Title: {profile_visual['payload']['title']}")

        # 验证时间标签（应该是+号）
        time_labels = profile_visual['payload']['data']['time_labels']
        first_label = time_labels[0]
        last_label = time_labels[-1]
        positive_labels = first_label.startswith('+') and last_label.startswith('+')
        print(f"  Time labels: {first_label} to {last_label} ({'PASS' if positive_labels else 'FAIL'})")

        # 验证元素数量（应该有3个：高度、温度、气压）
        elements_count = len(profile_visual['payload']['data']['elements'])
        print(f"  Elements count: {elements_count} ({'PASS' if elements_count == 3 else 'FAIL'})")

        # 验证X轴标签（应该是"预测时间"）
        x_label = profile_visual['payload']['options']['x_axis_label']
        correct_x_label = x_label == "预测时间"
        print(f"  X-axis label: {x_label} ({'PASS' if correct_x_label else 'FAIL'})")

        validation_results['profile_validation'] = {
            "exists": True,
            "positive_labels": positive_labels,
            "elements_count": elements_count,
            "correct_x_label": correct_x_label
        }
    else:
        print(f"\nProfile visual NOT FOUND!")
        validation_results['profile_validation'] = {"exists": False}

    return validation_results


async def run_all_tests():
    """运行所有正向轨迹预测测试"""
    print("=" * 80)
    print("PHASE 2-3: FORWARD TRAJECTORY PREDICTION TESTS")
    print("=" * 80)

    test_results = {}

    # Test 1: Basic forward trajectory
    try:
        basic_result = await test_forward_trajectory_basic()
        test_results["basic_forward_trajectory"] = {
            "success": basic_result.get("success"),
            "points_count": len(basic_result.get("data", []))
        }
    except Exception as e:
        print(f"\nTest 1 FAILED: {e}")
        test_results["basic_forward_trajectory"] = {"success": False, "error": str(e)}

    # Test 2: Different prediction hours
    try:
        hours_results = await test_different_prediction_hours()
        test_results["different_prediction_hours"] = hours_results
    except Exception as e:
        print(f"\nTest 2 FAILED: {e}")
        test_results["different_prediction_hours"] = {"success": False, "error": str(e)}

    # Test 3: Different heights
    try:
        heights_results = await test_different_heights()
        test_results["different_heights"] = heights_results
    except Exception as e:
        print(f"\nTest 3 FAILED: {e}")
        test_results["different_heights"] = {"success": False, "error": str(e)}

    # Test 4: Different locations
    try:
        locations_results = await test_different_locations()
        test_results["different_locations"] = locations_results
    except Exception as e:
        print(f"\nTest 4 FAILED: {e}")
        test_results["different_locations"] = {"success": False, "error": str(e)}

    # Test 5: Visualization validation
    try:
        viz_results = await test_visualization_validation()
        test_results["visualization_validation"] = viz_results
    except Exception as e:
        print(f"\nTest 5 FAILED: {e}")
        test_results["visualization_validation"] = {"success": False, "error": str(e)}

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    total_tests = 5
    passed_tests = 0

    # Count passed tests
    if test_results.get("basic_forward_trajectory", {}).get("success"):
        passed_tests += 1

    if isinstance(test_results.get("different_prediction_hours"), list):
        if all(r.get("success") for r in test_results["different_prediction_hours"]):
            passed_tests += 1

    if isinstance(test_results.get("different_heights"), list):
        if all(r.get("success") for r in test_results["different_heights"]):
            passed_tests += 1

    if isinstance(test_results.get("different_locations"), list):
        if all(r.get("success") for r in test_results["different_locations"]):
            passed_tests += 1

    if test_results.get("visualization_validation", {}).get("visuals_count", 0) == 2:
        passed_tests += 1

    print(f"\nTotal tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success rate: {(passed_tests / total_tests) * 100:.1f}%")

    # Save results
    output_file = Path(__file__).parent / "phase2_forward_trajectory_test_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "test_date": datetime.now().isoformat(),
            "phase": "2.3",
            "test_results": test_results,
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "success_rate": (passed_tests / total_tests) * 100
        }, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {output_file}")
    print("=" * 80)

    return passed_tests >= 4


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
