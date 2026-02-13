"""
EKMA诊断报告测试脚本

用于验证新增的诊断信息输出是否完整准确
"""

import json
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def print_diagnostic_report(diagnostic_data):
    """格式化打印诊断报告"""

    print("\n" + "="*80)
    print("EKMA诊断报告")
    print("="*80)

    # 1. 综合摘要
    summary = diagnostic_data.get("summary", {})
    print("\n【综合诊断】")
    print(f"  状态: {summary.get('overall_status', 'unknown')}")
    print(f"  严重问题数: {summary.get('issue_count', 0)}")
    print(f"  警告数: {summary.get('warning_count', 0)}")

    if summary.get("critical_issues"):
        print("\n  关键问题:")
        for issue in summary["critical_issues"]:
            print(f"    ❌ {issue}")

    if summary.get("warnings"):
        print("\n  警告:")
        for warning in summary["warnings"]:
            print(f"    ⚠️  {warning}")

    # 2. 详细诊断
    diagnostics = diagnostic_data.get("diagnostics", {})

    # 2.1 输入数据
    print("\n【1. 输入数据完整性】")
    input_diag = diagnostics.get("1_input_data", {})
    print(f"  VOCs总浓度(输入): {input_diag.get('total_vocs_input_ppb', 0):.2f} ppb")
    print(f"  VOCs总浓度(映射): {input_diag.get('total_vocs_mapped_ppb', 0):.2f} ppb")
    print(f"  映射成功率: {input_diag.get('mapping_success_ratio', 0)*100:.1f}%")
    print(f"  物种数(输入/映射): {input_diag.get('species_count_input', 0)}/{input_diag.get('species_count_mapped', 0)}")
    print(f"  完整性状态: {input_diag.get('completeness_status', 'unknown')}")

    missing = input_diag.get("missing_key_precursors", {})
    if missing:
        print("\n  缺失关键前体物:")
        for category, species in missing.items():
            print(f"    - {category}: {', '.join(species)}")

    # 2.2 网格设置
    print("\n【2. 网格范围设置】")
    grid_diag = diagnostics.get("2_grid_setup", {})
    print(f"  VOCs范围: {grid_diag.get('voc_range_ppb', (0, 0))[0]:.0f} - {grid_diag.get('voc_range_ppb', (0, 0))[1]:.0f} ppb")
    print(f"  NOx范围: {grid_diag.get('nox_range_ppb', (0, 0))[0]:.0f} - {grid_diag.get('nox_range_ppb', (0, 0))[1]:.0f} ppb")
    print(f"  VOCs/NOx比例: {grid_diag.get('vocs_nox_span_ratio', 0):.2f}:1")
    print(f"  建议范围: {grid_diag.get('recommended_ratio_range', 'N/A')}")
    print(f"  状态: {grid_diag.get('ratio_status', 'unknown')}")

    current_state = grid_diag.get("current_state_in_grid", {})
    print(f"\n  当前状态点位置:")
    print(f"    VOCs: {current_state.get('vocs_ppb', 0):.2f} ppb (相对位置: {current_state.get('voc_position_ratio', 0):.2f})")
    print(f"    NOx: {current_state.get('nox_ppb', 0):.2f} ppb (相对位置: {current_state.get('nox_position_ratio', 0):.2f})")
    print(f"    是否居中: {current_state.get('is_centered', False)}")

    # 2.3 O3曲面
    print("\n【3. O3响应曲面】")
    surface_diag = diagnostics.get("3_o3_surface", {})
    o3_stats = surface_diag.get("o3_statistics", {})
    print(f"  O3范围: {o3_stats.get('min_ppb', 0):.2f} - {o3_stats.get('max_ppb', 0):.2f} ppb")
    print(f"  O3均值: {o3_stats.get('mean_ppb', 0):.2f} ppb")
    print(f"  O3标准差: {o3_stats.get('std_ppb', 0):.2f} ppb")

    peak_analysis = surface_diag.get("peak_analysis", {})
    print(f"\n  峰值分析:")
    print(f"    位置: VOCs={peak_analysis.get('position_vocs_ppb', 0):.2f}, NOx={peak_analysis.get('position_nox_ppb', 0):.2f}")
    print(f"    相对位置: ({peak_analysis.get('position_voc_ratio', 0):.2f}, {peak_analysis.get('position_nox_ratio', 0):.2f})")
    print(f"    峰值O3: {peak_analysis.get('peak_o3_ppb', 0):.2f} ppb")
    print(f"    在边界: {peak_analysis.get('is_at_boundary', False)}")
    print(f"    位置合理: {peak_analysis.get('is_reasonable_position', False)}")

    boundary = surface_diag.get("boundary_analysis", {})
    print(f"\n  边界分析:")
    edge_means = boundary.get("edge_means_ppb", {})
    for edge_name, value in edge_means.items():
        print(f"    {edge_name}: {value:.2f} ppb")
    print(f"    NOx滴定效应正常: {boundary.get('nox_titration_effect_ok', False)}")

    validity = surface_diag.get("physical_validity", {})
    print(f"\n  物理合理性: {validity.get('overall_status', 'unknown')}")

    # 2.4 控制区
    print("\n【4. 控制区划分】")
    zones_diag = diagnostics.get("4_control_zones", {})
    if zones_diag.get("status") != "not_available":
        print(f"  VOCs控制区: {zones_diag.get('vocs_control_ratio', 0)*100:.1f}%")
        print(f"  NOx控制区: {zones_diag.get('nox_control_ratio', 0)*100:.1f}%")
        print(f"  协同控制区: {zones_diag.get('transition_ratio', 0)*100:.1f}%")
        print(f"  是否均衡: {zones_diag.get('is_balanced', False)}")
        print(f"  状态: {zones_diag.get('balance_status', 'unknown')}")
    else:
        print("  控制区数据不可用")

    # 2.5 敏感性
    print("\n【5. 敏感性诊断】")
    sens_diag = diagnostics.get("5_sensitivity", {})
    print(f"  EKMA结果: {sens_diag.get('ekma_result', 'unknown')}")
    print(f"  判断方法: {sens_diag.get('ekma_method', 'unknown')}")
    print(f"  预期结果: {sens_diag.get('expected_from_zones', 'unknown')}")
    print(f"  结果一致: {sens_diag.get('is_consistent', False)}")
    print(f"  置信度: {sens_diag.get('confidence', 0):.2f}")

    # 3. 修复建议
    recommendations = diagnostic_data.get("recommendations", [])
    if recommendations:
        print("\n【修复建议】")
        for i, rec in enumerate(recommendations, 1):
            print(f"\n  {i}. {rec.get('issue', 'N/A')}")
            print(f"     优先级: {rec.get('priority', 'N/A')}")
            print(f"     建议: {rec.get('suggestion', 'N/A')}")

    # 4. 人类可读解释
    print("\n【诊断解释】")
    interpretation = diagnostic_data.get("interpretation", "无解释")
    print(interpretation)

    print("\n" + "="*80 + "\n")


def main():
    """
    模拟诊断报告输出

    在实际使用中，这些数据来自OBM分析结果的diagnostic字段
    """
    print("EKMA诊断报告测试")
    print("\n此脚本展示了新增的诊断信息输出格式。")
    print("在实际分析中，诊断报告会自动添加到result['diagnostic']字段。")

    print("\n使用方法:")
    print("1. 运行OBM全化学分析: calculate_obm_full_chemistry")
    print("2. 在返回结果中查找'diagnostic'字段")
    print("3. 使用print_diagnostic_report()函数格式化输出")

    print("\n诊断报告包含以下内容:")
    print("  - 输入数据完整性检查（VOCs物种覆盖率）")
    print("  - 网格范围合理性检查（VOCs/NOx比例）")
    print("  - O3曲面物理合理性检查（峰值位置、边界效应）")
    print("  - 控制区划分均衡性检查")
    print("  - 敏感性判断一致性检查")
    print("  - 具体修复建议")

    print("\n示例输出格式见上方print_diagnostic_report()函数。")


if __name__ == "__main__":
    main()
