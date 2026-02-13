"""
场景预计算脚本 - CMD友好版

预计算EKMA典型场景的O3响应曲面
"""
import sys
import os

backend_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.tools.analysis.pybox_integration.cache_utils import (
    EKMA_Scenes,
    precompute_all_scenes,
    get_cache_statistics
)
from app.tools.analysis.pybox_integration.pybox_adapter import PyBoxAdapter


def main():
    print("=" * 60)
    print("EKMA 场景预计算")
    print("=" * 60)

    # 打印场景信息
    print("\n预计算场景:")
    for key in EKMA_Scenes.get_all_scene_keys():
        scene = EKMA_Scenes.SCENES[key]
        voc = scene['voc_total']
        nox = scene['nox']
        ratio = voc / nox
        print("  [{}] {} - VOC={}ppb, NOx={}ppb, 比值={:.1f}".format(
            key, scene['name'], voc, nox, ratio
        ))

    print("\n预计时间: 10-15分钟 (3场景 x 441点)")
    print("=" * 60)

    # 初始化PyBox
    print("\n初始化PyBox适配器...")
    try:
        pybox = PyBoxAdapter(mechanism='RACM2')
        print("  PyBox初始化成功!")
    except Exception as e:
        print("  PyBox初始化失败: {}".format(e))
        print("  请确保Cantera和assimulo已安装")
        return

    # 开始预计算
    print("\n开始预计算...")
    scenes = EKMA_Scenes.get_all_scene_keys()
    total = len(scenes)

    def callback(completed, total, msg):
        bar_len = 30
        filled = int(bar_len * completed / total)
        bar = "#" * filled + "-" * (bar_len - filled)
        sys.stdout.write("\r  [{}] {}/{} {}   ".format(bar, completed, total, msg))
        sys.stdout.flush()

    results = precompute_all_scenes(
        pybox,
        scenes=scenes,
        grid_size=21,
        simulation_time=25200.0,
        progress_callback=callback
    )

    # 打印结果
    print("\n")
    print("=" * 60)
    print("预计算完成!")
    print("=" * 60)

    for key in scenes:
        scene = EKMA_Scenes.SCENES[key]
        status = results.get(key, {}).get('status', 'unknown')
        if status == 'cached':
            print("  [{}] {} - 已缓存".format(key, scene['name']))
        elif status == 'computed':
            max_o3 = results.get(key, {}).get('max_o3', 0)
            print("  [{}] {} - 完成 (峰值O3: {:.0f} ppb)".format(key, scene['name'], max_o3))
        else:
            print("  [{}] {} - {}".format(key, scene['name'], status))

    # 缓存统计
    from app.tools.analysis.pybox_integration.cache_utils import CACHE_DIR
    stats = get_cache_statistics(CACHE_DIR)
    print("\n缓存统计: {} 文件, {} MB".format(
        stats['total_files'], stats['total_size_mb']
    ))


if __name__ == '__main__':
    main()
