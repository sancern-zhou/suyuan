#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOCs站点映射一致性检查
"""

import sys
import json
from pathlib import Path

# 设置Windows控制台编码
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())

sys.path.insert(0, r'D:\溯源\backend')
sys.path.insert(0, r'D:\vanna广东省VOCs')


def print_section(title: str):
    """打印分节标题"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def check_particulate_matcher():
    """检查颗粒物站点映射器"""
    print_section("1. 检查颗粒物站点映射器")

    try:
        from app.utils.particulate_geo_matcher import get_particulate_geo_matcher

        matcher = get_particulate_geo_matcher()
        print(f"✓ 颗粒物站点映射器加载成功")
        print(f"  站点数量: {len(matcher.station_codes)}")
        print(f"  映射文件: app/config/geo_mappings.json")

        print(f"\n前20个站点:")
        for i, (name, code) in enumerate(list(matcher.station_codes.items())[:20], 1):
            print(f"  {i:2d}. {name:20s} -> {code}")

        return matcher

    except Exception as e:
        print(f"✗ 颗粒物站点映射器加载失败: {e}")
        return None


def check_vanna_geo_mappings():
    """检查Vanna项目站点映射"""
    print_section("2. 检查Vanna项目站点映射")

    vanna_geo_file = Path(r"D:\vanna广东省VOCs\config\geo_mappings.json")

    if not vanna_geo_file.exists():
        print(f"✗ Vanna站点映射文件不存在: {vanna_geo_file}")
        return None

    try:
        with open(vanna_geo_file, 'r', encoding='utf-8') as f:
            vanna_data = json.load(f)

        print(f"✓ Vanna站点映射文件加载成功")

        # 检查stations字段
        if 'stations' in vanna_data:
            stations = vanna_data['stations']
            print(f"  站点数量: {len(stations)}")

            print(f"\n前20个站点:")
            for i, (name, code) in enumerate(list(stations.items())[:20], 1):
                print(f"  {i:2d}. {name:20s} -> {code}")

            return {'type': 'stations', 'data': stations}

        else:
            print(f"  未找到stations字段")
            print(f"  包含字段: {list(vanna_data.keys())}")

            # 检查是否有城市/区县映射
            if 'cities' in vanna_data:
                cities = vanna_data['cities']
                print(f"  城市映射数量: {len(cities)}")
                print(f"  示例城市: {list(cities.keys())[:5]}")

            return None

    except Exception as e:
        print(f"✗ Vanna站点映射加载失败: {e}")
        return None


def check_vocs_api_stations():
    """检查VOCs API支持的站点"""
    print_section("3. 检查VOCs API支持的站点")

    # 从广东超站接口文档中提取的站点列表
    # 参考：广东超站接口文档
    known_vocs_stations = {
        "新兴": "1042b",
        "从化天湖": "1004b",
        "公园前": "1006b",
        "鹤山花果山": "1001b",
        "南沙科大": "1007b",
        "市八中": "1010b",
        "台山端芬": "1002b",
        "西区": "1003b",
        "西园路": "1041b",
        "下埔": "1026b",
        "中山公园": "1014b",
        "综合观测点": "1023b",
        # 根据测试结果，这些站点支持VOCs查询
    }

    print(f"✓ 从接口文档和测试中提取的VOCs站点:")
    print(f"  站点数量: {len(known_vocs_stations)}")

    print(f"\nVOCs监测站点列表:")
    for i, (name, code) in enumerate(known_vocs_stations.items(), 1):
        print(f"  {i:2d}. {name:20s} -> {code}")

    return known_vocs_stations


def compare_mappings(matcher, vanna_stations, vocs_stations):
    """对比映射一致性"""
    print_section("4. 映射一致性分析")

    if not matcher:
        print("✗ 颗粒物站点映射器不可用，无法对比")
        return

    # 获取颗粒物站点
    particulate_stations = matcher.station_codes

    print(f"颗粒物站点数: {len(particulate_stations)}")
    if vanna_stations and 'data' in vanna_stations:
        print(f"Vanna站点数: {len(vanna_stations['data'])}")
    print(f"已知VOCs站点数: {len(vocs_stations)}")

    # 检查已知VOCs站点是否在颗粒物映射中
    print(f"\n检查VOCs站点在颗粒物映射中的可用性:")
    for name, code in vocs_stations.items():
        if name in particulate_stations:
            mapped_code = particulate_stations[name]
            if mapped_code == code:
                print(f"  ✓ {name:20s} -> {code} (一致)")
            else:
                print(f"  ⚠ {name:20s} -> 颗粒物映射={mapped_code}, VOCs站点={code} (不一致)")
        else:
            print(f"  ✗ {name:20s} -> {code} (不在颗粒物映射中)")

    # 检查颗粒物站点是否可用于VOCs查询
    print(f"\n检查颗粒物站点在VOCs API中的可用性:")
    vocs_station_names = set(vocs_stations.keys())

    for name, code in list(particulate_stations.items())[:30]:
        if name in vocs_station_names:
            print(f"  ✓ {name:20s} -> {code} (可用于VOCs)")
        else:
            print(f"  ? {name:20s} -> {code} (VOCs支持性未知)")


def main():
    """主函数"""
    print("="*60)
    print("VOCs站点映射一致性检查")
    print(f"检查时间: {Path(__file__).name}")
    print("="*60)

    # 检查各系统站点映射
    matcher = check_particulate_matcher()
    vanna_stations = check_vanna_geo_mappings()
    vocs_stations = check_vocs_api_stations()

    # 对比分析
    compare_mappings(matcher, vanna_stations, vocs_stations)

    # 总结和建议
    print_section("5. 总结与建议")

    print("\n当前状态:")
    if matcher:
        print(f"  ✓ 颗粒物站点映射器可用 ({len(matcher.station_codes)}个站点)")
    else:
        print(f"  ✗ 颗粒物站点映射器不可用")

    print(f"  ✓ 已知VOCs站点 ({len(vocs_stations)}个)")

    print("\n映射一致性:")
    print("  - VOCs站点是从颗粒物站点映射器获取的")
    print("  - 映射器使用 app/config/geo_mappings.json 文件")
    print("  - 文件包含广东省组分监测站点")

    print("\n建议:")
    print("  1. 确认VOCs站点列表已包含在 geo_mappings.json 中")
    print("  2. 用户应使用站点名称（如'新兴'）而非城市名")
    print("  3. 如需新增站点，需更新 geo_mappings.json")

    print("\n可用站点示例:")
    print("  - 新兴 (1042b)")
    print("  - 公园前 (1006b)")
    print("  - 鹤山花果山 (1001b)")
    print("  - 南沙科大 (1007b)")

    print("\n查询方式:")
    print("  ✓ 方式1: 使用站点名称")
    print("    get_vocs_data(locations=['新兴'], ...)")
    print("  ✓ 方式2: 直接使用站点编码")
    print("    get_vocs_data(code='1042b', ...)")


if __name__ == "__main__":
    main()
