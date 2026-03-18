#!/usr/bin/env python3
"""
测试Phase 3.1轨迹计算集成

演示如何使用算法选择功能
"""

import asyncio
from datetime import datetime
from pathlib import Path
import sys

# 添加backend路径
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

# 检查HYSPLIT安装
hysplit_exec = Path("data/hysplit/exec/hyts_std.exe")
HAS_HYSPLIT = hysplit_exec.exists()

print("=" * 80)
print("Phase 3.1轨迹计算 - API使用演示")
print("=" * 80)
print(f"HYSPLIT安装状态: {'已安装' if HAS_HYSPLIT else '未安装'}")
print(f"可执行文件: {hysplit_exec}")
print("=" * 80)


async def demo_phase2_simplified():
    """演示Phase 2简化算法"""
    print("\n" + "=" * 80)
    print("演示1: Phase 2 简化算法")
    print("=" * 80)

    from app.services.trajectory.trajectory_calculator_v3 import TrajectoryCalculatorService

    calculator = TrajectoryCalculatorService()

    result = await calculator.calculate_backward_trajectory(
        lat=23.13,  # 广州
        lon=113.26,
        start_time=datetime(2025, 11, 15, 12, 0),
        hours=24,
        algorithm="simplified"  # 使用简化算法
    )

    if result["success"]:
        print("\n[成功] 轨迹计算完成")
        print(f"  轨迹点数: {len(result['data'])}")
        print(f"  算法: {result['metadata']['algorithm']}")
        print(f"  数据源: {result['metadata']['analysis_params']['data_source']}")
        print(f"  相位: {result['metadata']['analysis_params']['phase']}")
        print(f"  图表数: {len(result['visuals'])}")

        # 显示第一个轨迹点
        if result['data']:
            first_point = result['data'][0]
            print(f"\n  起点: {first_point['lat']:.4f}°N, {first_point['lon']:.4f}°E")
            print(f"  时间: {first_point['timestamp']}")
    else:
        print(f"\n[失败] {result.get('error')}")

    return result


async def demo_phase3_hysplit():
    """演示Phase 3.1 HYSPLIT真实模型"""
    print("\n" + "=" * 80)
    print("演示2: Phase 3.1 HYSPLIT真实模型")
    print("=" * 80)

    if not HAS_HYSPLIT:
        print("\n[跳过] HYSPLIT未安装，无法演示真实模型")
        print(f"  请安装HYSPLIT到: {hysplit_exec}")
        print(f"  或查看安装指南: cat GDAS_DOWNLOAD_INSTRUCTIONS.txt")
        return None

    from app.services.trajectory.trajectory_calculator_v3 import TrajectoryCalculatorService

    calculator = TrajectoryCalculatorService()

    # 检查GDAS数据
    from app.external_apis.meteo_data_manager import MeteoDataManager
    manager = MeteoDataManager(cache_dir="data/hysplit/meteo")

    now = datetime(2025, 11, 15, 12, 0)
    past = now - timedelta(hours=24)

    required_files = manager.get_required_files_for_timerange(past, now)
    availability = manager.check_local_availability(required_files)
    available_count = sum(availability.values())

    print(f"\nGDAS数据检查:")
    print(f"  需要文件: {len(required_files)}")
    print(f"  可用文件: {available_count}")

    if available_count < len(required_files):
        print(f"\n[跳过] GDAS数据不完整")
        print(f"  请下载GDAS数据:")
        print(f"    python scripts/download_gdas_data.py --test")
        return None

    print(f"\n[开始] 使用HYSPLIT真实模型计算轨迹...")

    result = await calculator.calculate_backward_trajectory(
        lat=23.13,  # 广州
        lon=113.26,
        start_time=datetime(2025, 11, 15, 12, 0),
        hours=24,
        algorithm="hysplit"  # 使用HYSPLIT真实模型
    )

    if result["success"]:
        print("\n[成功] HYSPLIT轨迹计算完成")
        print(f"  轨迹点数: {len(result['data'])}")
        print(f"  算法: {result['metadata']['algorithm']}")
        print(f"  HYSPLIT版本: {result['metadata']['analysis_params'].get('hysplit_version', 'N/A')}")
        print(f"  数据源: {result['metadata']['analysis_params']['data_source']}")
        print(f"  气象文件: {result['metadata']['analysis_params'].get('meteo_files', [])}")
        print(f"  相位: {result['metadata']['analysis_params']['phase']}")
        print(f"  图表数: {len(result['visuals'])}")

        # 显示第一个轨迹点
        if result['data']:
            first_point = result['data'][0]
            print(f"\n  起点: {first_point['lat']:.4f}°N, {first_point['lon']:.4f}°E")
            print(f"  时间: {first_point['timestamp']}")
            if 'pressure' in first_point:
                print(f"  气压: {first_point['pressure']:.1f} hPa")
            if 'temperature' in first_point:
                print(f"  温度: {first_point['temperature']:.1f} °C")
    else:
        print(f"\n[失败] {result.get('error')}")

    return result


async def compare_algorithms():
    """对比两种算法"""
    print("\n" + "=" * 80)
    print("演示3: 算法对比")
    print("=" * 80)

    from app.services.trajectory.trajectory_calculator_v3 import TrajectoryCalculatorService

    calculator = TrajectoryCalculatorService()
    lat, lon = 23.13, 113.26
    start_time = datetime(2025, 11, 15, 12, 0)
    hours = 24

    algorithms = [
        ("simplified", "Phase 2简化算法"),
        ("hysplit", "Phase 3.1 HYSPLIT")
    ]

    results = {}

    for algo, desc in algorithms:
        print(f"\n[{desc}]")
        try:
            result = await calculator.calculate_backward_trajectory(
                lat=lat, lon=lon, start_time=start_time,
                hours=hours, algorithm=algo
            )
            results[algo] = result

            if result["success"]:
                print(f"  状态: 成功")
                print(f"  轨迹点数: {len(result['data'])}")
                print(f"  数据源: {result['metadata']['analysis_params']['data_source']}")
            else:
                print(f"  状态: 失败")
                print(f"  错误: {result.get('error', 'N/A')}")
        except Exception as e:
            print(f"  状态: 异常")
            print(f"  错误: {str(e)}")
            results[algo] = None

    # 对比结果
    print(f"\n{'=' * 80}")
    print("对比结果")
    print(f"{'=' * 80}")

    for algo in ["simplified", "hysplit"]:
        if results.get(algo) and results[algo]["success"]:
            r = results[algo]
            print(f"\n{algo}:")
            print(f"  成功: ✓")
            print(f"  轨迹点数: {len(r['data'])}")
            print(f"  算法: {r['metadata']['algorithm']}")
            print(f"  数据源: {r['metadata']['analysis_params']['data_source']}")
        else:
            print(f"\n{algo}:")
            print(f"  成功: ✗")

    return results


async def main():
    """主函数"""
    print("\n选择演示:")
    print("  1. Phase 2简化算法")
    print("  2. Phase 3.1 HYSPLIT (需要HYSPLIT + GDAS数据)")
    print("  3. 算法对比")

    choice = input("\n请选择 (1-3, 回车退出): ").strip()

    if choice == "1":
        await demo_phase2_simplified()
    elif choice == "2":
        await demo_phase3_hysplit()
    elif choice == "3":
        await compare_algorithms()
    else:
        print("\n退出")

    print("\n" + "=" * 80)
    print("演示结束")
    print("=" * 80)
    print("\n更多信息:")
    print("  下载GDAS数据: python scripts/download_gdas_data.py --test")
    print("  验证数据: python scripts/verify_gdas_data.py")
    print("  完整测试: python scripts/test_hysplit_with_real_data.py")
    print("  查看指南: cat GDAS_DOWNLOAD_INSTRUCTIONS.txt")


if __name__ == "__main__":
    asyncio.run(main())
