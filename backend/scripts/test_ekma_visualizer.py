#!/usr/bin/env python3
"""
简单测试脚本：生成模拟 O3 响应面并调用 EKMAVisualizer 以验证可视化（包括轴为降序的情况）
生成两张图片到 backend/scripts/output：ekma_normal.png, ekma_reversed.png
"""
import os
import sys
import base64
import numpy as np

# 将仓库根添加到 sys.path，确保可以导入项目内模块
HERE = os.path.dirname(os.path.abspath(__file__))
# REPO root is two levels up from backend/scripts -> 项目根目录
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
print("DEBUG: REPO_ROOT:", REPO_ROOT)
print("DEBUG: REPO_ROOT exists:", os.path.exists(REPO_ROOT))
print("DEBUG: sys.path[0]:", sys.path[0])
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
print("DEBUG: BACKEND_DIR:", BACKEND_DIR)
print("DEBUG: BACKEND_DIR exists:", os.path.exists(BACKEND_DIR))

try:
    # 项目中的 backend 包以外，主应用包是 `app`，优先尝试直接导入 `app` 下的模块
    from app.tools.analysis.pybox_integration.ekma_visualizer import EKMAVisualizer
except Exception as e:
    print("IMPORT_FAILED", str(e))
    raise

OUT_DIR = os.path.join(HERE, "output")
os.makedirs(OUT_DIR, exist_ok=True)

def make_surface(vocs, nox, peak_voc=90.0, peak_nox=40.0, amp=40.0, baseline=20.0):
    # vocs: 1d voc axis, nox: 1d nox axis
    V, N = np.meshgrid(vocs, nox, indexing='xy')  # shape (len(nox), len(vocs))
    # 使用二维高斯形成一个有明显峰值的响应面（单位：ppb）
    sigma_v = (vocs.max() - vocs.min()) * 0.2
    sigma_n = (nox.max() - nox.min()) * 0.2
    Z = baseline + amp * np.exp(-(((V - peak_voc) ** 2) / (2 * sigma_v ** 2) + ((N - peak_nox) ** 2) / (2 * sigma_n ** 2)))
    return Z

def make_ridge_surface(vocs, nox, amp=40.0, baseline=20.0):
    """
    生成一个具有明显脊状（ridge）响应面的模拟数据：
    脊线沿 VOC 轴随 NOx 逐步偏移，形成非对称等值线，接近真实 EKMA 的形态。
    """
    V, N = np.meshgrid(vocs, nox, indexing='xy')
    # 脊线中心为 VOC = base + k * NOx
    base_peak_v = 30.0
    k = 0.8  # 脊线随 NOx 上升在 VOC 上的偏移量
    peak_v = base_peak_v + k * N
    peak_n = 25.0 + 0.2 * V  # 让脊在 NOx 方向也有小幅依赖，制造扭曲

    sigma_v = (vocs.max() - vocs.min()) * 0.12
    sigma_n = (nox.max() - nox.min()) * 0.18

    Z = baseline + amp * np.exp(-(((V - peak_v) ** 2) / (2 * sigma_v ** 2) + ((N - peak_n) ** 2) / (2 * sigma_n ** 2)))
    # 在脊线的一侧增加一个倾斜的梯度以增强非对称性
    Z += 5.0 * (V / (vocs.max() + 1.0))
    return Z

def save_chart_from_payload(payload, out_path):
    data = payload.get("payload", {}).get("data")
    if not data:
        print("NO_IMAGE_IN_PAYLOAD")
        return False
    # payload data is "data:image/png;base64,...."
    if data.startswith("data:"):
        b64 = data.split(",", 1)[1]
    else:
        b64 = data
    img = base64.b64decode(b64)
    with open(out_path, "wb") as f:
        f.write(img)
    return True

def run_test(voc_vals, nox_vals, out_name, reversed_axes=False):
    vis = EKMAVisualizer(figure_size=(10, 8), dpi=150)
    Z = make_surface(voc_vals, nox_vals)
    # 如果想测试传入为倒序的轴（真实世界常见错误），传入降序轴但不重排 Z，
    # 这样可验证可视化器的自动排序是否生效
    if reversed_axes:
        voc_in = voc_vals[::-1]
        nox_in = nox_vals[::-1]
        Z_in = Z  # 故意不反转 Z，这模拟调用者传入乱序轴导致显示异常的情况
    else:
        voc_in = voc_vals
        nox_in = nox_vals
        Z_in = Z

    # 调用绘图（axis_mode=absolute，传入的是绝对浓度 ppb）
    payload = vis.generate_ekma_surface(
        o3_surface=Z_in,
        voc_factors=list(voc_in),
        nox_factors=list(nox_in),
        sensitivity={
            "type": "VOCs-limited",
            "vocs_nox_ratio": 2.4,
            "recommendation": "优先控制NOx排放..."
        },
        current_o3=None,
        current_vocs=float(voc_vals.mean()),
        current_nox=float(nox_vals.mean()),
        plot_interp_factor=2,
        plot_smoothing_sigma=1.0,
        axis_mode="absolute"
    )

    out_path = os.path.join(OUT_DIR, out_name)
    ok = save_chart_from_payload(payload, out_path)
    print("SAVED:", out_path, "OK:", ok)
    return out_path if ok else None

def main():
    vocs = np.linspace(0, 120, 25)   # ppb
    noxs = np.linspace(0, 60, 25)    # ppb

    print("Running normal-axis test...")
    p1 = run_test(vocs, noxs, "ekma_normal.png", reversed_axes=False)

    print("Running reversed-axis test (simulate caller provided descending axes)...")
    p2 = run_test(vocs, noxs, "ekma_reversed.png", reversed_axes=True)

    # 生成 ridge 型响应面以模拟更真实的 EKMA 曲线（非轴对称）
    print("Running ridge (asymmetric) surface test...")
    vis = EKMAVisualizer(figure_size=(10, 8), dpi=150)
    Z_ridge = make_ridge_surface(vocs, noxs)
    # 正常轴顺序
    payload_ridge = vis.generate_ekma_surface(
        o3_surface=Z_ridge,
        voc_factors=list(vocs),
        nox_factors=list(noxs),
        sensitivity={
            "type": "VOCs-limited",
            "vocs_nox_ratio": 2.4,
            "recommendation": "优先控制VOCs..."
        },
        current_vocs=float(vocs.mean()),
        current_nox=float(noxs.mean()),
        plot_interp_factor=2,
        plot_smoothing_sigma=1.0,
        axis_mode="absolute"
    )
    out_ridge = os.path.join(OUT_DIR, "ekma_ridge.png")
    save_chart_from_payload(payload_ridge, out_ridge)
    print("SAVED ridge normal:", out_ridge)

    # reversed axes for ridge surface
    print("Running ridge reversed-axis test...")
    payload_ridge_rev = vis.generate_ekma_surface(
        o3_surface=Z_ridge,
        voc_factors=list(vocs[::-1]),
        nox_factors=list(noxs[::-1]),
        sensitivity={
            "type": "VOCs-limited",
            "vocs_nox_ratio": 2.4,
            "recommendation": "优先控制VOCs..."
        },
        current_vocs=float(vocs.mean()),
        current_nox=float(noxs.mean()),
        plot_interp_factor=2,
        plot_smoothing_sigma=1.0,
        axis_mode="absolute"
    )
    out_ridge_rev = os.path.join(OUT_DIR, "ekma_ridge_reversed.png")
    save_chart_from_payload(payload_ridge_rev, out_ridge_rev)
    print("SAVED ridge reversed:", out_ridge_rev)

    print("Done. Outputs written to:", OUT_DIR)
    if p1:
        print("Normal chart:", p1)
    if p2:
        print("Reversed-axis chart:", p2)

if __name__ == "__main__":
    main()


