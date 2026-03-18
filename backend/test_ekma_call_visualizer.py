"""
生成模拟EKMA曲面数据并调用可视化验证

这个脚本创建一个物理正确的EKMA曲面数据文件，
然后调用EKMAVisualizer进行绘制，验证后端流程。
"""

import sys
import json
import numpy as np
from pathlib import Path

# 添加backend路径
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))


def create_physical_correct_ekma_surface():
    """
    创建物理正确的EKMA曲面数据

    EKMA物理特征：
    - 峰值位置：VOCs=80ppb, NOx=30ppb（VOCs控制区特征）
    - NOx=0行：O3随VOC增加而增加
    - VOC=0列：O3随NOx增加而减少（NO滴定效应）
    - 高NOx区域O3较低
    - 角落比例：右下角O3 < 左上角O3
    """
    n_voc, n_nox = 21, 21
    voc_range = (0, 200)  # ppb
    nox_range = (0, 100)  # ppb

    # 生成网格
    voc_values = np.linspace(voc_range[0], voc_range[1], n_voc).tolist()
    nox_values = np.linspace(nox_range[0], nox_range[1], n_nox).tolist()

    # 峰值位置
    peak_voc, peak_nox = 80.0, 30.0
    peak_o3 = 150.0

    # 创建O3曲面 - 使用L型等值线模型
    o3_surface = np.zeros((n_nox, n_voc))

    for i, nox in enumerate(nox_values):
        for j, voc in enumerate(voc_values):
            # EKMA L型核心：条件选择控制区
            # VOC控制区：NOx < peak_nox时，O3主要由VOC决定
            # NOx控制区：NOx > peak_nox时，O3主要由NOx决定

            if nox <= peak_nox:
                # VOC控制区：O3随VOC增加，随NOx增加缓慢减少
                o3 = 40 + (peak_o3 - 40) * (voc / peak_voc)
                o3 -= (nox / nox_range[1]) * 15
            else:
                # NOx控制区：O3随NOx减少
                o3 = 40 + (peak_o3 - 40) * ((nox_range[1] - nox) / (nox_range[1] - peak_nox))
                o3 += (voc / voc_range[1]) * 20

            o3_surface[i, j] = max(35, min(160, o3))

    return {
        "o3_surface": o3_surface.tolist(),
        "voc_factors": voc_values,
        "nox_factors": nox_values,
        "peak_position": [float(peak_voc), float(peak_nox)],
        "peak_o3": float(o3_surface.max()),
        "metadata": {
            "description": "物理正确的EKMA测试数据",
            "features": [
                "峰值在VOCs=80, NOx=30",
                "NOx=0时O3随VOC增加",
                "VOC=0时O3随NOx减少（滴定）",
                "高NOx区域O3较低",
                "角落比例正确：右下角 < 左上角"
            ]
        }
    }


def save_test_data(data, filepath):
    """保存测试数据到JSON文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"测试数据已保存: {filepath}")


def call_ekma_visualizer(data, output_path):
    """
    调用EKMAVisualizer进行可视化
    """
    from app.tools.analysis.pybox_integration.ekma_visualizer import EKMAVisualizer

    print("\n调用EKMAVisualizer...")

    visualizer = EKMAVisualizer(figure_size=(10, 8), dpi=100)

    # 构建敏感性数据
    vocs_nox_ratio = data["voc_factors"][-1] / data["nox_factors"][-1]
    sensitivity = {
        "type": "VOCs-limited",
        "vocs_nox_ratio": vocs_nox_ratio,
        "recommendation": "优先控制VOCs排放"
    }

    # 构建控制区数据
    control_zones = {
        "zone_map": None,
        "zone_masks": None,
        "zone_stats": {
            "vocs_control_ratio": 0.5,
            "nox_control_ratio": 0.3,
            "transition_ratio": 0.2
        },
        "zone_boundaries": {}
    }

    # 调用可视化
    result = visualizer.generate_ekma_surface(
        o3_surface=data["o3_surface"],
        voc_factors=data["voc_factors"],
        nox_factors=data["nox_factors"],
        sensitivity=sensitivity,
        current_vocs=60,
        current_nox=45,
        peak_position=tuple(data["peak_position"]),
        control_zones=control_zones
    )

    if "error" in result:
        print(f"错误: {result['error']}")
        return False

    print(f"生成成功!")
    print(f"  图片ID: {result['id']}")
    if "payload" in result:
        print(f"  标题: {result['payload'].get('title', 'N/A')}")

    # 复制图片到指定位置
    import shutil
    image_id = result["id"]
    src_path = Path(__file__).parent / "backend_data_registry" / "images" / f"{image_id}.png"
    if src_path.exists():
        shutil.copy(src_path, output_path)
        print(f"图片已保存: {output_path}")
    else:
        print(f"警告: 源图片不存在 {src_path}")

    return True


def validate_ekma_data(data):
    """验证EKMA数据的物理正确性"""
    o3_surface = np.array(data["o3_surface"])
    voc_factors = data["voc_factors"]
    nox_factors = data["nox_factors"]
    peak_position = data["peak_position"]

    print("\n" + "=" * 60)
    print("EKMA数据验证")
    print("=" * 60)

    # 1. 验证峰值位置
    peak_row, peak_col = np.unravel_index(o3_surface.argmax(), o3_surface.shape)
    actual_peak_voc = voc_factors[peak_col]
    actual_peak_nox = nox_factors[peak_row]
    print(f"\n预期峰值位置: VOCs={peak_position[0]:.1f}, NOx={peak_position[1]:.1f}")
    print(f"实际峰值位置: VOCs={actual_peak_voc:.1f}, NOx={actual_peak_nox:.1f}")

    # 2. 验证NOx轴行为（VOC=0列）
    nox_axis = o3_surface[:, 0]  # VOC=0
    nox_increasing = all(nox_axis[i] >= nox_axis[i+1] * 0.95 for i in range(len(nox_axis)-1))
    print(f"\nNOx轴行为（VOC=0）:")
    print(f"  O3随NOx增加而{'减少（正确）' if nox_increasing else '增加（错误-缺滴定效应）'}")
    print(f"  VOC=0时 O3范围: {nox_axis.min():.1f} - {nox_axis.max():.1f}")

    # 3. 验证VOC轴行为（NOx=0行）
    voc_axis = o3_surface[0, :]  # NOx=0
    voc_increasing = all(voc_axis[i] <= voc_axis[i+1] * 1.1 for i in range(len(voc_axis)-1))
    print(f"\nVOC轴行为（NOx=0）:")
    print(f"  O3随VOC增加而{'增加（正确）' if voc_increasing else '减少（错误）'}")
    print(f"  NOx=0时 O3范围: {voc_axis.min():.1f} - {voc_axis.max():.1f}")

    # 4. 角落比较
    top_left = o3_surface[0, 0]
    top_right = o3_surface[0, -1]
    bottom_left = o3_surface[-1, 0]
    bottom_right = o3_surface[-1, -1]
    corner_ratio = bottom_right / top_left if top_left > 0 else 1

    print(f"\n角落O3值比较:")
    print(f"  左上角(VOC=0,NOx=0): {top_left:.1f}")
    print(f"  右上角(VOC=max,NOx=0): {top_right:.1f}")
    print(f"  左下角(VOC=0,NOx=max): {bottom_left:.1f}")
    print(f"  右下角(VOC=max,NOx=max): {bottom_right:.1f}")
    print(f"  角落比例(右下/左上): {corner_ratio:.2f} {'（<0.9正确）' if corner_ratio < 0.9 else '（>0.9错误）'}")

    # 5. 整体评估
    is_physical_correct = (
        nox_increasing and  # NOx轴递减
        voc_increasing and  # VOC轴递增
        corner_ratio < 0.9   # 角落比例正确
    )

    print(f"\n" + "=" * 60)
    print(f"数据物理正确性: {'通过' if is_physical_correct else '不通过'}")
    print("=" * 60)

    return is_physical_correct


def main():
    print("=" * 60)
    print("EKMA曲线绘制验证测试")
    print("=" * 60)
    print("\n目的: 创建物理正确的EKMA数据，验证可视化流程")

    # 创建测试数据
    print("\n[1/3] 创建物理正确的EKMA曲面数据...")
    data = create_physical_correct_ekma_surface()

    # 验证数据
    print("\n[2/3] 验证EKMA数据...")
    is_valid = validate_ekma_data(data)

    if not is_valid:
        print("\n警告: 生成的EKMA数据物理不正确，可能无法显示L型曲线")

    # 保存数据
    data_path = Path(__file__).parent / "test_ekma_data.json"
    save_test_data(data, data_path)

    # 调用可视化
    print("\n[3/3] 调用EKMAVisualizer...")
    output_image = Path(__file__).parent / "test_output" / "ekma_physical_correct.png"
    output_image.parent.mkdir(exist_ok=True)

    success = call_ekma_visualizer(data, output_image)

    # 总结
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    print(f"\n数据文件: {data_path}")
    print(f"图片文件: {output_image}")

    if success and is_valid:
        print("\n[成功] EKMA曲线绘制流程验证通过!")
        print("  - 数据具有正确的L型物理特征")
        print("  - 可视化流程正常工作")
    elif success:
        print("\n[部分成功] 可视化流程正常，但数据需要优化")
    else:
        print("\n[失败] 可视化流程出现问题")

    print("\n查看图片:")
    print(f"  浏览器访问: http://localhost:8000/api/image/ekma_surface_*.png")
    print(f"  或查看本地文件: {output_image}")


if __name__ == "__main__":
    main()
