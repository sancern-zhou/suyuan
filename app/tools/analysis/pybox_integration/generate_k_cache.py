"""
预计算k值缓存生成脚本

运行方式:
    python generate_k_cache.py

生成缓存文件:
    k_cache/default.json

功能:
    - 预计算RACM2机理在标准大气条件下的所有反应速率常数
    - 生成JSON格式缓存文件，供后续快速加载
"""
import os
import sys
import json
from datetime import datetime

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from mechanism_loader import load_mechanism, FacsimileParser, RACM2ODESystem
from config import PyBoxConfig


def generate_default_k_cache():
    """生成默认条件下的k值缓存"""

    print("=" * 60)
    print("RACM2 速率常数缓存生成工具")
    print("=" * 60)

    # 标准大气条件
    STANDARD_CONDITIONS = {
        'temperature': 298.15,  # 25°C
        'pressure': 101325.0,   # 1 atm
        'solar_zenith_angle': 30.0,  # 30度
        'relative_humidity': 0.5
    }

    print("\n[1/4] 加载RACM2化学机理...")
    mechanism = load_mechanism("RACM2")
    print(f"    - 物种数: {mechanism.num_species}")
    print(f"    - 反应数: {mechanism.num_reactions}")

    print("\n[2/4] 解析FACSIMILE文件...")
    parser = FacsimileParser()
    fac_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "mechanisms",
        "racm2_ekma.fac"
    )
    mechanism = parser.parse(fac_path)
    print(f"    - 速率表达式: {len(parser.rate_expressions)}")

    # 统计生成/损失矩阵条目数
    p_entries = sum(len(v) for v in parser.production.values()) if isinstance(parser.production, dict) else 0
    d_entries = sum(len(v) for v in parser.destruction.values()) if isinstance(parser.destruction, dict) else 0
    print(f"    - 生成矩阵条目: {p_entries}")
    print(f"    - 损失矩阵条目: {d_entries}")

    print("\n[3/4] 构建ODE系统...")
    ode_system = RACM2ODESystem(mechanism, parser)
    print(f"    - 稀疏矩阵: {'启用' if ode_system._use_sparse else '禁用'}")

    print("\n[4/4] 计算k值并保存缓存...")
    print(f"    - 温度: {STANDARD_CONDITIONS['temperature']} K")
    print(f"    - 压力: {STANDARD_CONDITIONS['pressure']} Pa")
    print(f"    - 太阳天顶角: {STANDARD_CONDITIONS['solar_zenith_angle']}°")

    # 计算k值
    k_values = ode_system._precompute_rate_constants(
        temperature=STANDARD_CONDITIONS['temperature'],
        pressure=STANDARD_CONDITIONS['pressure'],
        solar_zenith_angle=STANDARD_CONDITIONS['solar_zenith_angle'],
        relative_humidity=STANDARD_CONDITIONS['relative_humidity']
    )

    # 构建缓存数据
    cache_data = {
        'k_values': k_values.tolist(),
        'params': {
            'temperature': STANDARD_CONDITIONS['temperature'],
            'pressure': STANDARD_CONDITIONS['pressure'],
            'solar_zenith_angle': STANDARD_CONDITIONS['solar_zenith_angle']
        },
        'created_at': datetime.now().isoformat(),
        'mechanism': 'RACM2',
        'num_species': mechanism.num_species,
        'num_reactions': mechanism.num_reactions,
        'description': '预计算的RACM2速率常数，标准大气条件(298.15K, 101325Pa, SZA=30°)'
    }

    # 保存缓存
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "k_cache")
    os.makedirs(cache_dir, exist_ok=True)

    cache_path = os.path.join(cache_dir, "default.json")
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=2)

    print(f"\n[完成] 缓存已保存到: {cache_path}")
    print(f"    - k值数量: {len(k_values)}")
    print(f"    - 文件大小: {os.path.getsize(cache_path) / 1024:.1f} KB")

    # 显示部分k值统计
    print(f"\n[k值统计]")
    print(f"    - 最小值: {np.min(k_values):.2e}")
    print(f"    - 最大值: {np.max(k_values):.2e}")
    print(f"    - 平均值: {np.mean(k_values):.2e}")
    print(f"    - 中位数: {np.median(k_values):.2e}")

    # 显示几个关键反应的k值
    key_reactions = [
        (0, "O3 + NO -> NO2 + O2"),
        (56, "O3 + hv -> O2 + O(1D)"),
        (3, "NO2 + hv -> NO + O"),
    ]
    print(f"\n[关键反应速率常数]")
    for idx, name in key_reactions:
        if idx < len(k_values):
            print(f"    - {name}: {k_values[idx]:.3e}")

    print("\n" + "=" * 60)
    print("缓存生成完成！后续运行将自动加载此缓存。")
    print("=" * 60)

    return cache_path


if __name__ == "__main__":
    generate_default_k_cache()
