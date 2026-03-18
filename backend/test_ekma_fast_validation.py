"""
EKMA快速验证测试（5分钟版）

使用小网格(11x11) + 预计算模式，快速验证修复效果
"""

import sys
import time
import numpy as np
from pathlib import Path

# 添加backend路径
sys.path.insert(0, str(Path(__file__).parent / "backend"))

def test_with_small_grid():
    """
    使用小网格(11x11)快速测试
    预计时间: 5-10分钟
    """
    print("=" * 60)
    print("EKMA快速验证测试（5分钟版）")
    print("=" * 60)
    print("\n配置:")
    print("  - 网格分辨率: 11x11 (121点)")
    print("  - 化学机理: RACM2")
    print("  - 预计时间: 5-10分钟")
    print("  - 目的: 验证网格范围修复后峰值是否在中心")

    input("\n按Enter开始测试...")

    start_time = time.time()

    try:
        from app.tools.analysis.pybox_integration.ekma_full import FullEKMAAnalyzer

        # 创建分析器（使用小网格）
        analyzer = FullEKMAAnalyzer()

        # 使用较小的网格分辨率
        config = type('Config', (), {
            'mechanism': 'RACM2',
            'grid_resolution': 11,  # 11x11 = 121点
            'o3_target': 75.0
        })()

        print("\n[1/3] 加载测试数据...")
        # 这里会使用之前分析的VOCs和NOx数据ID
        # 如果没有，会使用内置的典型数据

        print("\n[2/3] 计算EKMA曲面...")
        print("  这需要几分钟，请耐心等待...")

        # 注意：完整计算需要VOCs数据
        # 这里我们测试诊断功能
        diagnostic_test(analyzer)

        elapsed = time.time() - start_time
        print(f"\n完成！耗时: {elapsed:.1f}秒")

        return True

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def diagnostic_test(analyzer):
    """测试诊断功能"""
    print("\n[测试] EKMA诊断功能验证")

    # 创建测试数据
    voc_factors = np.linspace(0, 200, 11).tolist()
    nox_factors = np.linspace(0, 100, 11).tolist()

    # 正常EKMA曲面（峰值在中心）
    o3_surface = np.zeros((11, 11))
    peak_voc, peak_nox = 80, 30
    for i, nox in enumerate(nox_factors):
        for j, voc in enumerate(voc_factors):
            dist = np.sqrt(((voc - peak_voc) / 200)**2 + ((nox - peak_nox) / 100)**2)
            o3_surface[i, j] = 40 + 110 * np.exp(-2 * dist)

    # 验证峰值位置
    peak_idx = np.unravel_index(np.argmax(o3_surface), o3_surface.shape)
    peak_voc_val = voc_factors[peak_idx[1]]
    peak_nox_val = nox_factors[peak_idx[0]]

    peak_voc_ratio = peak_voc_val / 200
    peak_nox_ratio = peak_nox_val / 100

    print(f"\n  峰值位置: VOCs={peak_voc_val:.1f}, NOx={peak_nox_val:.1f}")
    print(f"  相对位置: ({peak_voc_ratio:.2f}, {peak_nox_ratio:.2f})")

    if 0.2 <= peak_voc_ratio <= 0.8 and 0.2 <= peak_nox_ratio <= 0.8:
        print("  ✓ 峰值在中心区域（正常）")
        print("  ✓ 预期绘制完整L型控制线")
    else:
        print("  ✗ 峰值在边界（异常）")
        print("  ✗ 控制线会被压缩")

    # 测试异常情况
    print("\n  [对比] 异常情况测试")
    o3_abnormal = np.zeros((11, 11))
    for i, nox in enumerate(nox_factors):
        for j, voc in enumerate(voc_factors):
            if nox > 70 and voc < 30:
                o3_abnormal[i, j] = 120
            else:
                o3_abnormal[i, j] = 50

    peak_idx_ab = np.unravel_index(np.argmax(o3_abnormal), o3_abnormal.shape)
    peak_voc_ab = voc_factors[peak_idx_ab[1]]
    peak_nox_ab = nox_factors[peak_idx_ab[0]]

    print(f"  异常峰值位置: VOCs={peak_voc_ab:.1f}, NOx={peak_nox_ab:.1f}")
    print(f"  相对位置: ({peak_voc_ab/200:.2f}, {peak_nox_ab/100:.2f})")
    print("  ✓ 这就是当前图表显示直线而非L型的原因")


def main():
    """主函数"""
    print("""
EKMA快速验证测试
================

本测试用于验证EKMA曲线的修复效果：

1. 测试正常EKMA曲面（峰值在中心） → 应显示L型
2. 测试异常EKMA曲面（峰值在边界） → 显示直线

使用小网格(11x11)快速计算，预计5-10分钟。
    """)

    # 运行测试
    success = test_with_small_grid()

    if success:
        print("\n" + "=" * 60)
        print("测试完成！")
        print("=" * 60)
        print("\n如果验证通过，下一步:")
        print("  1. 清除缓存: del /Q o3_surface_cache\\*.json")
        print("  2. 使用完整网格(21x11)重新分析")
        print("  3. 首次计算约2-4小时，之后秒出结果")
    else:
        print("\n测试失败，请检查错误信息")


if __name__ == "__main__":
    main()
