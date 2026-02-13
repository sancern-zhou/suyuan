"""
场景预计算脚本

预计算EKMA典型场景的O3响应曲面:
- urban: 城市场景 (VOCs/NOx ~ 5)
- industrial: 工业区场景 (VOCs/NOx ~ 3)
- rural: 农村场景 (VOCs/NOx ~ 10)

使用:
    python precompute_scenes.py

首次运行约10-15分钟（3场景×441点），后续查询毫秒级。
"""

import sys
import os

# 添加backend路径
backend_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.tools.analysis.pybox_integration.cache_utils import (
    EKMA_Scenes,
    precompute_all_scenes,
    get_cache_statistics,
    CACHE_DIR
)
from app.tools.analysis.pybox_integration.pybox_adapter import PyBoxAdapter

# 配置
DEFAULT_GRID_SIZE = 21
DEFAULT_SIMULATION_TIME = 25200.0  # 7小时


def print_scenes_info():
    """打印预计算场景信息"""
    print("\n" + "=" * 60)
    print("EKMA 场景预计算")
    print("=" * 60)

    for key, scene in EKMA_Scenes.SCENES.items():
        voc_total = scene.get("voc_total", 0)
        nox = scene.get("nox", 0)
        ratio = voc_total / nox if nox > 0 else 0

        print("\n场景: {} ({})".format(scene['name'], key))
        print("  VOC总量: {} ppb".format(voc_total))
        print("  NOx浓度: {} ppb".format(nox))
        print("  VOCs/NOx比值: {:.1f}".format(ratio))
        print("  芳香烃占比: {:.0%}".format(scene.get('aromatics_ratio', 0)))
        print("  物种数: {}".format(len(scene['voc_profile'])))

    print("\n" + "-" * 60)
    print("预计算策略:")
    print("  - 每个场景计算21x21 ODE网格 (441点)")
    print("  - 首次约3-5分钟/场景")
    print("  - 后续查询毫秒级（缓存命中）")
    print("=" * 60 + "\n")


def progress_callback(completed: int, total: int, message: str):
    """进度回调"""
    bar_len = 30
    filled = int(bar_len * completed / total)
    bar = "#" * filled + "-" * (bar_len - filled)

    sys.stdout.write("\r  [{}] {}/{} {}   ".format(bar, completed, total, message))
    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(
        description="预计算EKMA典型场景的O3响应曲面"
    )
    parser.add_argument(
        "--scenes",
        nargs="+",
        choices=EKMA_Scenes.get_all_scene_keys(),
        default=EKMA_Scenes.get_all_scene_keys(),
        help="要预计算的场景列表"
    )
    parser.add_argument(
        "--grid-size",
        type=int,
        default=DEFAULT_GRID_SIZE,
        help=f"网格大小 (默认 {DEFAULT_GRID_SIZE})"
    )
    parser.add_argument(
        "--show-stats",
        action="store_true",
        help="显示缓存统计信息"
    )
    parser.add_argument(
        "--list-scenes",
        action="store_true",
        help="列出所有可用场景"
    )

    args = parser.parse_args()

    if args.list_scenes:
        print_scenes_info()
        return 0

    if args.show_stats:
        from app.tools.analysis.pybox_integration.cache_utils import CACHE_DIR
        stats = get_cache_statistics(CACHE_DIR)
        print("\n缓存统计:")
        print(f"  总文件数: {stats['total_files']}")
        print(f"  总大小: {stats['total_size_mb']} MB")
        print(f"  最旧文件: {stats['oldest_file'] or 'N/A'}")
        print(f"  最新文件: {stats['newest_file'] or 'N/A'}")
        print(f"  平均文件大小: {stats['avg_file_size_kb']} KB")
        return 0

    # 打印场景信息
    print_scenes_info()

    # 初始化PyBox适配器
    print("初始化PyBox适配器...")
    try:
        pybox = PyBoxAdapter(mechanism="RACM2")
        print("  PyBox初始化成功\n")
    except Exception as e:
        print(f"  PyBox初始化失败: {e}")
        print("  请确保Cantera和PyBox已正确安装")
        return 1

    # 预计算所有场景
    print(f"开始预计算场景: {', '.join(args.scenes)}")
    print(f"网格大小: {args.grid_size}×{args.grid_size}")
    print()

    results = precompute_all_scenes(
        pybox_adapter=pybox,
        scenes=args.scenes,
        grid_size=args.grid_size,
        simulation_time=DEFAULT_SIMULATION_TIME,
        temperature=298.15,
        pressure=101325.0,
        solar_zenith_angle=30.0,
        progress_callback=progress_callback
    )

    # 打印结果摘要
    print("\n\n预计算完成！")
    print("-" * 40)

    for scene_key, result in results.items():
        scene_name = EKMA_Scenes.SCENES.get(scene_key, {}).get("name", scene_key)
        status = result.get("status", "unknown")

        if status == "cached":
            print(f"  {scene_name}: 已缓存")
        elif status == "computed":
            max_o3 = result.get("max_o3", 0)
            print(f"  {scene_name}: 完成 (峰值O3: {max_o3:.1f} ppb)")
        else:
            print(f"  {scene_name}: {status}")

    # 显示缓存统计
    print("\n" + "-" * 40)
    stats = get_cache_statistics(CACHE_DIR)
    print(f"缓存统计: {stats['total_files']} 文件, {stats['total_size_mb']} MB")

    return 0


if __name__ == "__main__":
    sys.exit(main())
