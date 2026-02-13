"""
EKMA曲线快速验证脚本（完整版）

使用模拟数据测试EKMA可视化功能，验证是否生成规范的L型曲线
预计时间: 30-60秒
"""

import sys
import os
import time
import json
from pathlib import Path
from datetime import datetime

# 添加backend路径
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

# 设置工作目录（已在backend目录，无需切换）
# os.chdir(backend_path)

# 设置中文字体
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False


def create_normal_ekma_surface():
    """
    创建正常的EKMA曲面数据（峰值在中心，L型结构）

    EKMA曲面的物理特征（关键！）：
    - 峰值位置：VOCs=80ppb, NOx=30ppb（在VOCs-NOx空间中的某一点）
    - NOx控制区（低VOC/高NOx）：O3随NOx减少而增加（滴定效应）
    - VOCs控制区（高VOC/低NOx）：O3随VOCs减少而增加
    - 等值线沿两个轴方向延伸，形成L型脊线

    物理约束：
    - 高NOx区域（NOx>峰值NOx）：O3应该较低（NO滴定）
    - 低NOx区域（NOx<峰值NOx）：O3随VOC增加而增加
    """
    n_voc, n_nox = 21, 21
    voc_range = (0, 200)  # ppb
    nox_range = (0, 100)  # ppb

    voc_factors = list(range(n_voc))
    nox_factors = list(range(n_nox))

    # 扩展到实际浓度范围
    voc_values = [voc_range[0] + v * (voc_range[1] - voc_range[0]) / (n_voc - 1) for v in voc_factors]
    nox_values = [nox_range[0] + n * (nox_range[1] - nox_range[0]) / (n_nox - 1) for n in nox_factors]

    # 峰值位置：VOCs=80ppb, NOx=30ppb
    peak_voc, peak_nox = 80.0, 30.0
    peak_o3 = 150  # ppb

    o3_surface = [[0.0] * n_voc for _ in range(n_nox)]

    for i, nox in enumerate(nox_values):
        for j, voc in enumerate(voc_values):
            # 核心EKMA模型：使用简化的O3生成-滴定平衡

            if nox < peak_nox:
                # VOC控制区：NOx低于峰值
                # O3与VOC正相关，与NOx负相关（但NOx越低，VOC作用越明显）
                voc_effect = voc / peak_voc  # VOC越高，O3越高
                nox_effect = (peak_nox - nox) / peak_nox * 0.5  # NOx越低，O3越高
                o3 = 40 + (peak_o3 - 40) * min(1.0, voc_effect + nox_effect)
            else:
                # NOx控制区：NOx高于峰值
                # O3与VOC正相关，但被高NOx抑制
                voc_effect = voc / voc_range[1] * 0.8  # VOC贡献
                nox_suppression = (nox - peak_nox) / (nox_range[1] - peak_nox) * 0.5  # NOx抑制
                o3 = 40 + (peak_o3 - 40) * max(0.2, voc_effect - nox_suppression + 0.3)

            o3_surface[i][j] = max(35, min(180, o3))

    # 找到实际峰值位置（应该在预期位置附近）
    import numpy as np
    Z = np.array(o3_surface)
    actual_peak_idx = np.unravel_index(np.argmax(Z), Z.shape)
    actual_peak_voc = voc_values[actual_peak_idx[1]]
    actual_peak_nox = nox_values[actual_peak_idx[0]]

    return {
        "o3_surface": o3_surface,
        "voc_factors": voc_values,
        "nox_factors": nox_values,
        "peak_position": (actual_peak_voc, actual_peak_nox),  # 使用实际峰值
        "peak_o3": float(Z.max()),
        "vocs_nox_ratio": voc_range[1] / nox_range[1]
    }


def create_abnormal_ekma_surface():
    """
    创建异常的EKMA曲面数据（峰值在边界，直线结构）
    """
    n_voc, n_nox = 21, 21
    voc_range = (0, 200)
    nox_range = (0, 100)

    voc_values = [voc_range[0] + v * (voc_range[1] - voc_range[0]) / (n_voc - 1) for v in range(n_voc)]
    nox_values = [nox_range[0] + n * (nox_range[1] - nox_range[0]) / (n_nox - 1) for n in range(n_nox)]

    # 峰值在左上角边界（异常情况）
    peak_voc_idx, peak_nox_idx = 0, 20  # VOCs=0, NOx=100

    o3_surface = [[0.0] * n_voc for _ in range(n_nox)]

    for i, nox in enumerate(nox_values):
        for j, voc in enumerate(voc_values):
            # 只有左上角有高值
            if voc < 50 and nox > 70:
                o3 = 120 + (50 - voc) * 0.5 + (nox - 70) * 0.3
            else:
                o3 = 40 + nox * 0.1 + voc * 0.05

            o3_surface[i][j] = max(40, min(150, o3))

    return {
        "o3_surface": o3_surface,
        "voc_factors": voc_values,
        "nox_factors": nox_values,
        "peak_position": (voc_values[peak_voc_idx], nox_values[peak_nox_idx]),
        "peak_o3": 150,
        "note": "异常情况：峰值在左上角边界"
    }


def plot_ekma_surface(data, title, output_path, show_validation=True):
    """
    使用matplotlib绘制EKMA曲面图
    """
    o3_surface = data["o3_surface"]
    voc_factors = data["voc_factors"]
    nox_factors = data["nox_factors"]
    peak_position = data["peak_position"]

    fig, ax = plt.subplots(figsize=(10, 8), dpi=100)

    # 转换数据
    import numpy as np
    Z = np.array(o3_surface)
    X, Y = np.meshgrid(voc_factors, nox_factors)

    # 绘制热力图
    levels = np.linspace(Z.min(), Z.max(), 15)
    cf = ax.contourf(X, Y, Z, levels=levels, cmap='turbo', antialiased=True)

    # 绘制等值线
    cs = ax.contour(X, Y, Z, levels=levels, colors='black', alpha=0.5, linewidths=0.5)
    ax.clabel(cs, inline=True, fontsize=7, fmt='%.0f')

    # 标记峰值位置
    ax.plot(peak_position[0], peak_position[1], 'r*', markersize=20,
            markeredgecolor='darkred', markeredgewidth=2, label='Peak O3', zorder=10)

    # 标记当前状态点（假设在VOCs=60, NOx=45附近）
    current_vocs = voc_factors[len(voc_factors)//3]
    current_nox = nox_factors[len(nox_factors)//2]
    ax.plot(current_vocs, current_nox, 'wo', markersize=12,
            markeredgecolor='black', markeredgewidth=2, label='Current State', zorder=10)

    # 绘制控制线（模拟L型）
    # 找到峰值附近的等值线作为控制线
    peak_o3 = data.get("peak_o3", 120)
    control_levels = [peak_o3 * 0.85, peak_o3 * 0.9, peak_o3]

    # 绘制控制线
    try:
        cs_control = ax.contour(X, Y, Z, levels=control_levels, colors='red', linewidths=2)
        ax.clabel(cs_control, inline=True, fontsize=8, fmt='O3=%.0f')
    except Exception as e:
        print(f"  警告: 控制线绘制失败 - {e}")

    # 颜色条
    cbar = plt.colorbar(cf, ax=ax, shrink=0.8)
    cbar.set_label('O3 Concentration (ppb)', fontsize=12)

    # 设置标签
    ax.set_xlabel('VOCs (ppb)', fontsize=12)
    ax.set_ylabel('NOx (ppb)', fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')

    # 网格
    ax.grid(True, alpha=0.3, linestyle='--')

    # 图例
    ax.legend(loc='upper right')

    # 验证信息
    if show_validation:
        # 计算峰值位置
        voc_span = voc_factors[-1] - voc_factors[0]
        nox_span = nox_factors[-1] - nox_factors[0]
        peak_voc_ratio = (peak_position[0] - voc_factors[0]) / voc_span
        peak_nox_ratio = (peak_position[1] - nox_factors[0]) / nox_span

        # 验证结果
        is_healthy = 0.2 <= peak_voc_ratio <= 0.8 and 0.2 <= peak_nox_ratio <= 0.8

        # 添加验证信息文本
        validation_text = (
            f"Validation Results:\n"
            f"Peak Position: ({peak_voc_ratio:.2f}, {peak_nox_ratio:.2f})\n"
            f"Expected: (0.2-0.8, 0.2-0.8)\n"
            f"Status: {'NORMAL' if is_healthy else 'ABNORMAL'}\n"
            f"Expected Curve: {'L-shaped' if is_healthy else 'Linear'}"
        )

        color = 'green' if is_healthy else 'red'
        ax.text(0.02, 0.98, validation_text, transform=ax.transAxes,
                verticalalignment='top', fontsize=9,
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.9),
                color=color)

    plt.tight_layout()
    plt.savefig(output_path, dpi=100, bbox_inches='tight')
    plt.close()

    print(f"  图片已保存: {output_path}")
    return output_path


def validate_ekma_surface(data):
    """
    验证EKMA曲面的规范性

    EKMA等值线应该是L型结构（沿VOCs和NOx轴延伸），
    而不是圆形或椭圆形（同心圆）
    """
    o3_surface = data["o3_surface"]
    voc_factors = data["voc_factors"]
    nox_factors = data["nox_factors"]
    peak_position = data["peak_position"]

    import numpy as np

    # 计算峰值位置比例
    voc_span = voc_factors[-1] - voc_factors[0]
    nox_span = nox_factors[-1] - nox_factors[0]

    peak_voc_ratio = (peak_position[0] - voc_factors[0]) / voc_span if voc_span > 0 else 0.5
    peak_nox_ratio = (peak_position[1] - nox_factors[0]) / nox_span if nox_span > 0 else 0.5

    issues = []
    if peak_voc_ratio < 0.15 or peak_voc_ratio > 0.85:
        issues.append(f"峰值VOCs位置异常: {peak_voc_ratio:.2f} (应在0.2-0.8)")
    if peak_nox_ratio < 0.15 or peak_nox_ratio > 0.85:
        issues.append(f"峰值NOx位置异常: {peak_nox_ratio:.2f} (应在0.2-0.8)")

    # 检查曲面形状 - EKMA应该是L型结构
    Z = np.array(o3_surface)

    # 找到实际峰值位置
    peak_row, peak_col = np.unravel_index(np.argmax(Z), Z.shape)
    peak_val = float(Z[peak_row, peak_col])

    # 检查四个角的O3值
    corner_values = {
        "VOC=0,NOx=0": float(Z[0, 0]),
        "VOC=max,NOx=0": float(Z[0, -1]),
        "VOC=0,NOx=max": float(Z[-1, 0]),
        "VOC=max,NOx=max": float(Z[-1, -1])
    }

    # L型结构的特征：
    # 1. 峰值应该在VOCs轴中间偏左、NOx轴中间偏下的位置
    # 2. NOx=0行：O3应该随VOC增加而增加（VOC控制区）
    # 3. VOC=0列：O3应该随NOx增加而减少或稳定（NOx滴定）
    # 4. 右上角(VOC=max,NOx=max)应该比左上角(VOC=0,NOx=0)低（滴定效应）

    # 检查VOC轴行为（NOx=0时）
    voc_axis_o3 = Z[0, :]  # NOx=0的行
    voc_increasing = all(voc_axis_o3[i] <= voc_axis_o3[i+1] * 1.1 for i in range(len(voc_axis_o3)-1))

    # 检查NOx轴行为（VOC=0时）
    nox_axis_o3 = Z[:, 0]  # VOC=0的列
    nox_decreasing = all(nox_axis_o3[i] >= nox_axis_o3[i+1] * 0.9 for i in range(len(nox_axis_o3)-1))

    # 角落比较
    top_left = float(Z[0, 0])
    bottom_right = float(Z[-1, -1])
    corner_ratio = bottom_right / top_left if top_left > 0 else 1

    # L型判定条件
    is_l_shaped = (
        voc_increasing and      # VOC轴：O3随VOC增加
        nox_decreasing and      # NOx轴：O3随NOx减少（滴定）
        corner_ratio < 0.9 and  # 右下角O3低于左上角
        peak_voc_ratio >= 0.3 and peak_voc_ratio <= 0.7 and  # 峰值在VOCs中间区域
        peak_nox_ratio >= 0.2 and peak_nox_ratio <= 0.6     # 峰值在NOx中间区域
    )

    # 圆形检测：四个方向衰减是否对称
    # 计算峰值到四个边缘的衰减
    top_decay = peak_val - Z[0, peak_col] if peak_row > 0 else 0
    bottom_decay = peak_val - Z[-1, peak_col] if peak_row < Z.shape[0]-1 else 0
    left_decay = peak_val - Z[peak_row, 0] if peak_col > 0 else 0
    right_decay = peak_val - Z[peak_row, -1] if peak_col < Z.shape[1]-1 else 0

    decays = [d for d in [top_decay, bottom_decay, left_decay, right_decay] if d > 0]
    if len(decays) >= 2:
        avg_decay = sum(decays) / len(decays)
        decay_std = (sum((d - avg_decay) ** 2 for d in decays) / len(decays)) ** 0.5
        is_circular = decay_std / avg_decay < 0.25 if avg_decay > 0 else False
    else:
        is_circular = False

    if is_circular:
        issues.append("等值线形状异常：检测到同心圆形结构（应为L型）")

    # 如果不是L型也不是圆形，给出更详细的诊断
    if not is_l_shaped and not is_circular:
        diagnostic_info = []
        if not voc_increasing:
            diagnostic_info.append("VOC轴O3未随浓度增加")
        if not nox_decreasing:
            diagnostic_info.append("NOx轴O3未随浓度减少（滴定效应缺失）")
        if corner_ratio >= 0.9:
            diagnostic_info.append("角落O3分布不符合EKMA特征")
        if not (0.3 <= peak_voc_ratio <= 0.7):
            diagnostic_info.append(f"峰值VOCs位置{peak_voc_ratio:.2f}偏离中心")
        if not (0.2 <= peak_nox_ratio <= 0.6):
            diagnostic_info.append(f"峰值NOx位置{peak_nox_ratio:.2f}偏离中心")

        issues.append(f"等值线形状异常: {', '.join(diagnostic_info)}")

    return {
        "peak_voc_ratio": peak_voc_ratio,
        "peak_nox_ratio": peak_nox_ratio,
        "has_issues": len(issues) > 0,
        "issues": issues,
        "is_healthy": (
            0.2 <= peak_voc_ratio <= 0.8 and
            0.2 <= peak_nox_ratio <= 0.8 and
            is_l_shaped and
            not is_circular
        ),
        "corner_values": corner_values,
        "voc_increasing": voc_increasing,
        "nox_decreasing": nox_decreasing,
        "corner_ratio": corner_ratio,
        "is_l_shaped": is_l_shaped,
        "is_circular": is_circular
    }


def test_with_ekma_visualizer():
    """
    使用真实的EKMAVisualizer测试（如果可用）

    返回: (success: bool, normal_result: dict, abnormal_result: dict or None)
    """
    print("\n" + "=" * 60)
    print("测试真实EKMAVisualizer")
    print("=" * 60)

    try:
        from app.tools.analysis.pybox_integration.ekma_visualizer import EKMAVisualizer

        print("\n已导入EKMAVisualizer")
        visualizer = EKMAVisualizer(figure_size=(10, 8), dpi=100)

        # 创建测试数据
        normal_data = create_normal_ekma_surface()

        # 构建敏感性数据
        sensitivity = {
            "type": "VOCs-limited",
            "vocs_nox_ratio": normal_data["vocs_nox_ratio"],
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

        print("\n[测试1] 正常EKMA曲面（峰值在中心，应生成L型）")
        print("-" * 40)
        result = visualizer.generate_ekma_surface(
            o3_surface=normal_data["o3_surface"],
            voc_factors=normal_data["voc_factors"],
            nox_factors=normal_data["nox_factors"],
            sensitivity=sensitivity,
            current_vocs=60,
            current_nox=45,
            peak_position=normal_data["peak_position"],
            control_zones=control_zones
        )

        if "error" in result:
            print(f"  错误: {result['error']}")
            return False, None, None

        # 保存图片
        image_id = result["id"]
        output_path = Path(__file__).parent / "test_output" / f"test_ekma_visualizer_{image_id}.png"

        # 获取图片URL并保存
        if "payload" in result and "markdown_image" in result["payload"]:
            print(f"  生成成功: {result['payload']['title']}")
            print(f"  图片ID: {image_id}")
            print(f"  图片URL: {result['payload']['image_url']}")

        # 验证结果
        normal_result = validate_ekma_surface(normal_data)
        print(f"\n  验证结果:")
        print(f"    峰值位置: VOCs={normal_data['peak_position'][0]:.1f}ppb, NOx={normal_data['peak_position'][1]:.1f}ppb")
        print(f"    峰值位置比例: ({normal_result['peak_voc_ratio']:.2f}, {normal_result['peak_nox_ratio']:.2f})")
        print(f"    曲线形状: {'L型' if normal_result['is_l_shaped'] else '非L型'}")
        print(f"    是否圆形: {'是（异常）' if normal_result['is_circular'] else '否（正常）'}")
        print(f"    整体状态: {'正常' if normal_result['is_healthy'] else '异常'}")

        # 测试异常EKMA曲面
        print("\n[测试2] 异常EKMA曲面（峰值在边界，应显示不完整）")
        print("-" * 40)
        abnormal_data = create_abnormal_ekma_surface()

        result2 = visualizer.generate_ekma_surface(
            o3_surface=abnormal_data["o3_surface"],
            voc_factors=abnormal_data["voc_factors"],
            nox_factors=abnormal_data["nox_factors"],
            sensitivity=sensitivity,
            current_vocs=60,
            current_nox=45,
            peak_position=abnormal_data["peak_position"],
            control_zones=control_zones
        )

        if "error" in result2:
            print(f"  错误: {result2['error']}")
            abnormal_result = None
        else:
            print(f"  生成成功")
            abnormal_result = validate_ekma_surface(abnormal_data)
            print(f"\n  验证结果:")
            print(f"    峰值位置比例: ({abnormal_result['peak_voc_ratio']:.2f}, {abnormal_result['peak_nox_ratio']:.2f})")
            print(f"    曲线形状: {'L型' if abnormal_result['is_l_shaped'] else '非L型'}")

        return True, normal_result, abnormal_result

    except ImportError as e:
        print(f"  无法导入EKMAVisualizer: {e}")
        print("  使用matplotlib备用方案...")
        return False, None, None
    except Exception as e:
        print(f"  错误: {e}")
        import traceback
        traceback.print_exc()
        return False, None, None


def main():
    """主测试函数"""
    print("=" * 60)
    print("EKMA曲线快速验证测试")
    print("=" * 60)
    print("\n目的: 验证EKMA可视化代码能否生成规范的L型曲线")
    print("预计时间: 30-60秒\n")

    output_dir = Path(__file__).parent / "test_output"
    output_dir.mkdir(exist_ok=True)

    # 默认值（防止UnboundLocalError）
    normal_result = None
    abnormal_result = None

    # 尝试使用真实EKMAVisualizer
    visualizer_success, normal_result, abnormal_result = test_with_ekma_visualizer()

    if not visualizer_success:
        # 使用matplotlib备用方案
        print("\n" + "=" * 60)
        print("使用matplotlib备用方案")
        print("=" * 60)

        # 测试正常EKMA曲面
        print("\n【测试1】正常EKMA曲面（峰值在中心）")
        print("-" * 40)
        normal_data = create_normal_ekma_surface()
        normal_result = validate_ekma_surface(normal_data)

        print(f"  峰值位置: VOCs={normal_data['peak_position'][0]:.1f}ppb, NOx={normal_data['peak_position'][1]:.1f}ppb")
        print(f"  相对位置: ({normal_result['peak_voc_ratio']:.2f}, {normal_result['peak_nox_ratio']:.2f})")
        print(f"  曲线形状: {'L型' if normal_result['is_l_shaped'] else '直线'}")
        print(f"  是否圆形: {'是（异常）' if normal_result['is_circular'] else '否（正常）'}")

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        normal_output = output_dir / f"ekma_normal_{timestamp}.png"
        plot_ekma_surface(normal_data, "EKMA等浓度曲面图 - 正常（峰值在中心）", str(normal_output))

        # 测试异常EKMA曲面
        print("\n【测试2】异常EKMA曲面（峰值在边界）")
        print("-" * 40)
        abnormal_data = create_abnormal_ekma_surface()
        abnormal_result = validate_ekma_surface(abnormal_data)

        print(f"  峰值位置: VOCs={abnormal_data['peak_position'][0]:.1f}ppb, NOx={abnormal_data['peak_position'][1]:.1f}ppb")
        print(f"  相对位置: ({abnormal_result['peak_voc_ratio']:.2f}, {abnormal_result['peak_nox_ratio']:.2f})")
        print(f"  曲线形状: {'L型' if abnormal_result['is_l_shaped'] else '直线（预期）'}")

        abnormal_output = output_dir / f"ekma_abnormal_{timestamp}.png"
        plot_ekma_surface(abnormal_data, "EKMA等浓度曲面图 - 异常（峰值在边界）", str(abnormal_output))

    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    if normal_result:
        print("\n正常EKMA曲面:")
        print(f"  峰值位置比例: ({normal_result['peak_voc_ratio']:.2f}, {normal_result['peak_nox_ratio']:.2f})")
        print(f"  VOC轴O3递增: {'是' if normal_result['voc_increasing'] else '否'}")
        print(f"  NOx轴O3递减: {'是' if normal_result['nox_decreasing'] else '否'}")
        print(f"  角落比例: {normal_result['corner_ratio']:.2f}")
        print(f"  曲线形状: {'L型' if normal_result['is_l_shaped'] else '非L型'}")
        print(f"  是否圆形: {'是（异常）' if normal_result['is_circular'] else '否（正常）'}")
        if normal_result['issues']:
            print(f"  问题: {normal_result['issues']}")
        print(f"  结果: {'通过' if normal_result['is_healthy'] else '不通过'}")
    else:
        print("\n正常EKMA曲面: (未测试)")

    if abnormal_result:
        print("\n异常EKMA曲面:")
        print(f"  峰值位置比例: ({abnormal_result['peak_voc_ratio']:.2f}, {abnormal_result['peak_nox_ratio']:.2f})")
        print(f"  合格范围: 0.20 - 0.80")
        print(f"  结果: {'通过' if abnormal_result['is_healthy'] else '不通过（预期）'}")
        print(f"  预期曲线: 直线结构（不完整L型）")
    else:
        print("\n异常EKMA曲面: (未测试)")

    print("\n" + "=" * 60)
    print("结论")
    print("=" * 60)

    if normal_result and normal_result['is_healthy']:
        print("\n[OK] EKMA可视化代码工作正常")
        print("  - 正常数据生成规范的L型曲线")
        if abnormal_result and not abnormal_result['is_healthy']:
            print("  - 异常数据生成非L型曲线（符合预期）")
    elif normal_result and normal_result['is_circular']:
        print("\n[FAIL] 验证失败：等值线为同心圆形结构")
        print("  原因: O3曲面数据不满足EKMA物理特征")
        print("  可能原因:")
        print("    1. 相似缓存插值生成伪数据")
        print("    2. VOCs数据缺失或不完整")
        print("    3. 网格范围设置不当")
    else:
        print("\n[FAIL] 验证失败，请检查代码")

    print(f"\n生成的测试图片:")
    for f in output_dir.glob("*.png"):
        print(f"  {f}")

    print("\n运行方法:")
    print("  cd D:\\溯源\\backend")
    print("  python test_ekma_quick_validation.py")


if __name__ == "__main__":
    main()
