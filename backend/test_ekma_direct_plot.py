"""
直接生成标准EKMA等值线图

使用matplotlib绘制教科书级别的EKMA等值线，
验证后端可视化流程。
"""

import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# 添加backend路径
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))


def create_standard_ekma_contours():
    """
    创建标准的EKMA等值线数据

    EKMA特征（参考图）：
    - 峰值在 (80, 30)
    - 等值线是分段线性的L型
    - 低NOx区域：等值线是水平线（平行于NOx轴）
    - 高VOC区域：等值线是垂直线（平行于VOC轴）
    - 等值线在峰值处"转弯"

    正确的EKMA模型：
    O3 = peak_o3 - 衰减 * max(NOx偏离, VOC偏离)
    """
    n_voc, n_nox = 21, 21
    voc_range = (0, 200)  # ppb
    nox_range = (0, 100)  # ppb

    voc_values = np.linspace(voc_range[0], voc_range[1], n_voc)
    nox_values = np.linspace(nox_range[0], nox_range[1], n_nox)

    # 峰值位置
    peak_voc, peak_nox = 80.0, 30.0
    peak_o3 = 150.0

    # 创建网格
    VOC, NOX = np.meshgrid(voc_values, nox_values)

    # 计算归一化偏离
    voc_dev = (VOC - peak_voc) / voc_range[1]  # VOC偏离峰值（归一化）
    nox_dev = (NOX - peak_nox) / nox_range[1]  # NOx偏离峰值（归一化）

    # 核心：使用max创建L型衰减
    # max(voc_dev, nox_dev) 的等值线是方形/阶梯状
    max_dev = np.maximum(voc_dev, nox_dev)

    # O3 = 峰值 - 衰减 * max偏离
    # 这会产生沿两个轴延伸的等值线
    O3 = peak_o3 - max_dev * (peak_o3 - 40) * 1.2

    # 应用边界约束
    # VOC=0列：滴定效应
    mask_voc_zero = VOC < 10
    O3[mask_voc_zero] = 40 + (peak_o3 - 40) * (1 - NOX[mask_voc_zero] / nox_range[1])

    # 角落约束：右下角 < 左上角
    mask_corner = (VOC > peak_voc) & (NOX > peak_nox)
    O3[mask_corner] = 40 + (peak_o3 - 40) * (1 - voc_dev[mask_corner]) * (1 - nox_dev[mask_corner])

    # 确保范围
    O3 = np.clip(O3, 35, 160)

    return VOC, NOX, O3, voc_values, nox_values


def plot_ekma_with_matplotlib(VOC, NOX, O3, voc_values, nox_values, output_path):
    """使用matplotlib绘制EKMA图"""
    fig, ax = plt.subplots(figsize=(10, 8), dpi=100)

    # 绘制填充等值线
    levels = np.linspace(35, 160, 15)
    cf = ax.contourf(VOC, NOX, O3, levels=levels, cmap='turbo')

    # 绘制等值线
    cs = ax.contour(VOC, NOX, O3, levels=levels, colors='black', alpha=0.5, linewidths=0.5)
    ax.clabel(cs, inline=True, fontsize=7, fmt='%.0f')

    # 标记峰值位置
    peak_voc, peak_nox = 80.0, 30.0
    ax.plot(peak_voc, peak_nox, 'r*', markersize=20, markeredgecolor='darkred',
            markeredgewidth=2, label='Peak O3', zorder=10)

    # 标记当前状态点
    ax.plot(60, 45, 'wo', markersize=12, markeredgecolor='black',
            markeredgewidth=2, label='Current State', zorder=10)

    # 颜色条
    cbar = plt.colorbar(cf, ax=ax, shrink=0.8)
    cbar.set_label('O3 Concentration (ppb)', fontsize=12)

    # 设置标签
    ax.set_xlabel('VOCs (ppb)', fontsize=12)
    ax.set_ylabel('NOx (ppb)', fontsize=12)
    ax.set_title('Standard EKMA Isopleth (Peak: VOCs=80, NOx=30)', fontsize=14, fontweight='bold')

    # 网格
    ax.grid(True, alpha=0.3, linestyle='--')

    # 图例
    ax.legend(loc='upper right')

    plt.tight_layout()
    plt.savefig(output_path, dpi=100, bbox_inches='tight')
    plt.close()

    print(f"图片已保存: {output_path}")
    return output_path


def call_image_cache(image_path):
    """调用后端图片缓存服务"""
    from app.services.image_cache import ImageCache

    cache = ImageCache()

    with open(image_path, 'rb') as f:
        image_data = f.read()

    # 保存图片
    image_id = cache.save(image_data)

    print(f"\n图片缓存服务:")
    print(f"  图片ID: {image_id}")
    print(f"  图片URL: /api/image/{image_id}")

    return image_id


def main():
    print("=" * 60)
    print("标准EKMA曲线生成测试")
    print("=" * 60)

    # 创建标准EKMA数据
    print("\n[1/3] 创建标准EKMA等值线数据...")
    VOC, NOX, O3, voc_values, nox_values = create_standard_ekma_contours()

    # 验证数据
    print("\n[2/3] 验证数据...")
    peak_row, peak_col = np.unravel_index(O3.argmax(), O3.shape)
    peak_voc = voc_values[peak_col]
    peak_nox = nox_values[peak_row]

    print(f"  峰值位置: VOCs={peak_voc:.1f}, NOx={peak_nox:.1f}")
    print(f"  O3范围: {O3.min():.1f} - {O3.max():.1f}")

    # 角落值
    corners = {
        "左上角(VOC=0,NOx=0)": O3[0, 0],
        "右上角(VOC=max,NOx=0)": O3[0, -1],
        "左下角(VOC=0,NOx=max)": O3[-1, 0],
        "右下角(VOC=max,NOx=max)": O3[-1, -1]
    }
    print(f"  角落值:")
    for name, value in corners.items():
        print(f"    {name}: {value:.1f}")

    # 绘制图片
    print("\n[3/3] 绘制EKMA图...")
    output_dir = Path(__file__).parent / "test_output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "ekma_standard_contours.png"

    plot_ekma_with_matplotlib(VOC, NOX, O3, voc_values, nox_values, output_path)

    # 调用图片缓存
    print("\n[4/3] 调用图片缓存服务...")
    try:
        image_id = call_image_cache(output_path)
        print(f"\n完成! 图片URL: http://localhost:8000/api/image/{image_id}")
    except Exception as e:
        print(f"图片缓存调用失败: {e}")
        print(f"本地图片路径: {output_path}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
