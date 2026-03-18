"""
快速验证规范模式EKMA图表
"""
import sys
from pathlib import Path

backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

from app.tools.analysis.pybox_integration.ekma_visualizer import EKMAVisualizer

# 创建可视化器
visualizer = EKMAVisualizer(figure_size=(10, 8), dpi=100)

# 使用规范模式生成EKMA图
result = visualizer.generate_ekma_surface(
    # 模拟数据（即使不规范也没关系）
    o3_surface=[[i*j for j in range(21)] for i in range(21)],
    voc_factors=list(range(0, 201, 10)),
    nox_factors=list(range(0, 101, 5)),
    sensitivity={"type": "VOCs-limited", "vocs_nox_ratio": 2.0, "recommendation": "优先控制VOCs"},
    current_vocs=60,
    current_nox=45,
    peak_position=(80, 30),
    control_zones={"zone_stats": {"vocs_control_ratio": 0.5, "nox_control_ratio": 0.3, "transition_ratio": 0.2}},
    # 关键参数：强制使用标准等值线
    force_standard_contours=True
)

print("=" * 60)
print("规范模式EKMA图表验证")
print("=" * 60)

if "error" in result:
    print(f"错误: {result['error']}")
else:
    print(f"成功!")
    print(f"图片ID: {result['id']}")
    print(f"图片URL: http://localhost:8000/api/image/{result['id']}")
    print(f"\n查看图片验证等值线是否为规范的L型结构")
