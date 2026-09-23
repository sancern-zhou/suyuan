"""
快速测试脚本：验证极坐标等值线图生成器

运行方式：
    cd /home/xckj/suyuan/backend
    python app/tools/visualization/examples/test_polar_contour.py
"""

import sys
sys.path.insert(0, '/home/xckj/suyuan/backend')

from app.tools.visualization.examples.polar_contour_example import (
    generate_smooth_polar_contour,
    generate_wind_rose_contour
)


def test_basic_contour():
    """测试基本等值线图生成"""
    print("=" * 60)
    print("测试1：基本极坐标等值线图")
    print("=" * 60)

    wind_dirs = [0, 45, 90, 135, 180, 225, 270, 315]
    wind_spds = [2.5, 3.0, 2.8, 3.2, 2.6, 2.9, 3.1, 2.7]
    concs = [35.2, 42.1, 38.5, 45.3, 32.8, 40.2, 43.6, 37.9]

    try:
        img_b64 = generate_smooth_polar_contour(
            wind_directions=wind_dirs,
            wind_speeds=wind_spds,
            concentrations=concs,
            title="PM10浓度极坐标等值线图（广雅中学，2026-03-01）",
            pollutant_name="PM10",
            unit="μg/m³",
            grid_resolution=100,
            interpolation_method="cubic",
            contour_levels=20
        )

        print(f"✅ 成功生成等值线图")
        print(f"   - Base64长度: {len(img_b64)}")
        print(f"   - 前100字符: {img_b64[:100]}...")

        # 验证是否是有效的base64
        import base64
        try:
            decoded = base64.b64decode(img_b64)
            print(f"   - 解码后大小: {len(decoded)} bytes")
            print(f"   - PNG头部验证: {decoded[:8] == b'\\x89PNG\\r\\n\\x1a\\n'}")
        except Exception as e:
            print(f"   ❌ Base64解码失败: {e}")

        return True
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_interpolation_methods():
    """对比不同插值方法"""
    print("\n" + "=" * 60)
    print("测试2：对比不同插值方法")
    print("=" * 60)

    wind_dirs = [0, 90, 180, 270]
    wind_spds = [2.0, 3.0, 2.5, 2.8]
    concs = [30.0, 45.0, 35.0, 40.0]

    methods = ['linear', 'cubic', 'nearest']
    results = {}

    for method in methods:
        print(f"\n测试 {method} 插值...")
        try:
            img_b64 = generate_smooth_polar_contour(
                wind_directions=wind_dirs,
                wind_speeds=wind_spds,
                concentrations=concs,
                interpolation_method=method,
                title=f"测试图（{method}插值）",
                grid_resolution=50  # 降低分辨率加快测试
            )
            results[method] = {
                'success': True,
                'size': len(img_b64)
            }
            print(f"  ✅ {method} 插值成功 (Base64长度: {len(img_b64)})")
        except Exception as e:
            results[method] = {
                'success': False,
                'error': str(e)
            }
            print(f"  ❌ {method} 插值失败: {e}")

    return results


def test_wind_rose_alias():
    """测试污染玫瑰图别名函数"""
    print("\n" + "=" * 60)
    print("测试3：污染玫瑰图别名函数")
    print("=" * 60)

    wind_dirs = [0, 45, 90, 135, 180, 225, 270, 315]
    wind_spds = [2.5, 3.0, 2.8, 3.2, 2.6, 2.9, 3.1, 2.7]
    concs = [35.2, 42.1, 38.5, 45.3, 32.8, 40.2, 43.6, 37.9]

    try:
        img_b64 = generate_wind_rose_contour(
            wind_directions=wind_dirs,
            wind_speeds=wind_spds,
            concentrations=concs,
            title="污染玫瑰图（等值线版）"
        )

        print(f"✅ 成功生成污染玫瑰图")
        print(f"   - Base64长度: {len(img_b64)}")

        return True
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def test_edge_cases():
    """测试边界情况"""
    print("\n" + "=" * 60)
    print("测试4：边界情况")
    print("=" * 60)

    # 测试1：最少数据点
    print("\n测试4.1：最少数据点（3个）")
    try:
        img = generate_smooth_polar_contour(
            wind_directions=[0, 120, 240],
            wind_speeds=[2.0, 2.5, 3.0],
            concentrations=[30, 40, 35],
            grid_resolution=30
        )
        print("  ✅ 3个数据点测试通过")
    except Exception as e:
        print(f"  ❌ 3个数据点测试失败: {e}")

    # 测试2：大量数据点
    print("\n测试4.2：大量数据点（100个）")
    try:
        import numpy as np
        n = 100
        wind_dirs = np.random.uniform(0, 360, n).tolist()
        wind_spds = np.random.uniform(1, 5, n).tolist()
        concs = np.random.uniform(20, 60, n).tolist()

        img = generate_smooth_polar_contour(
            wind_directions=wind_dirs,
            wind_speeds=wind_spds,
            concentrations=concs,
            grid_resolution=50,
            interpolation_method="linear"  # 使用线性插值加快速度
        )
        print(f"  ✅ 100个数据点测试通过 (Base64长度: {len(img)})")
    except Exception as e:
        print(f"  ❌ 100个数据点测试失败: {e}")

    # 测试3：验证输入验证
    print("\n测试4.3：输入验证（长度不一致）")
    try:
        img = generate_smooth_polar_contour(
            wind_directions=[0, 90, 180],
            wind_speeds=[2.0, 2.5],  # 长度不一致
            concentrations=[30, 40, 35]
        )
        print("  ❌ 应该抛出ValueError")
    except ValueError as e:
        print(f"  ✅ 正确抛出ValueError: {e}")
    except Exception as e:
        print(f"  ❌ 抛出了错误的异常类型: {e}")


def main():
    """运行所有测试"""
    print("\n" + "🚀" * 30)
    print("极坐标等值线图生成器测试套件")
    print("🚀" * 30 + "\n")

    results = []

    # 运行测试
    results.append(("基本等值线图", test_basic_contour()))
    results.append(("插值方法对比", test_interpolation_methods()))
    results.append(("污染玫瑰图别名", test_wind_rose_alias()))
    results.append(("边界情况", test_edge_cases()))

    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    for name, result in results:
        if isinstance(result, bool):
            status = "✅ 通过" if result else "❌ 失败"
            print(f"{name}: {status}")
        elif isinstance(result, dict):
            success_count = sum(1 for v in result.values() if v.get('success', False))
            total_count = len(result)
            print(f"{name}: {success_count}/{total_count} 通过")

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
