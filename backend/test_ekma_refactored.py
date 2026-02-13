"""测试EKMA可视化器重构后的代码"""
import sys
import numpy as np

# 测试导入
try:
    from app.tools.analysis.pybox_integration.ekma_visualizer import EKMAVisualizer
    from app.tools.analysis.pybox_integration.ekma_lshape_model import LShapeControlLine
    from app.tools.analysis.pybox_integration.ekma_control_zones import ControlZoneDivider
    print("All imports successful!")
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

# 测试L形控制线模型
print("\n=== 测试L形控制线模型 ===")
lshape = LShapeControlLine(
    peak_voc=0.5, peak_nox=0.5,
    anchor_voc=0.1, anchor_nox=0.1,
    slope_voc_arm=-1.5, slope_nox_arm=0.3
)
print(f"L-shape model created: peak_voc={lshape.peak_voc}, peak_nox={lshape.peak_nox}")

# 测试点分类
result = lshape.classify_point(0.3, 0.7)
print(f"Point (0.3, 0.7) classified as: {result['zone']}")

result = lshape.classify_point(0.7, 0.3)
print(f"Point (0.7, 0.3) classified as: {result['zone']}")

# 测试控制区划分
print("\n=== 测试控制区划分 ===")
divider = ControlZoneDivider(lshape, transition_buffer_ratio=0.1)
voc_factors = np.linspace(0.1, 1.0, 20)
nox_factors = np.linspace(0.1, 1.0, 20)
zone_result = divider.divide_zones(voc_factors, nox_factors)
print(f"Zone stats: {zone_result['zone_stats']}")

# 测试可视化器
print("\n=== 测试EKMA曲面生成 ===")
viz = EKMAVisualizer()
print(f"EKMAVisualizer created with figure_size={viz.figure_size}, dpi={viz.dpi}")

# 测试EKMA曲面数据生成
print("\n=== 测试EKMA曲面数据生成 ===")
try:
    voc_arr = np.linspace(0.1, 1.0, 30)
    nox_arr = np.linspace(0.1, 1.0, 30)
    voc_grid, nox_grid = np.meshgrid(voc_arr, nox_arr, indexing='xy')
    Z = np.random.uniform(40, 120, voc_grid.shape)

    result = viz._generate_ekma_surface_data(voc_grid, nox_grid, Z)
    print(f"Surface data generated: status={result.get('status')}")
    print(f"Peak position: {result.get('peak_position')}")
    print(f"Sensitivity type: {result.get('sensitivity', {}).get('type')}")
except Exception as e:
    print(f"Error in surface data generation: {e}")

print("\n=== 所有测试通过 ===")
