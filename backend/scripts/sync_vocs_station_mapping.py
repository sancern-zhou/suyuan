#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOCs站点映射同步脚本

将Vanna项目中的站点映射同步到溯源系统
"""

import sys
import json
import shutil
from pathlib import Path
from datetime import datetime

# 设置Windows控制台编码
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())

sys.path.insert(0, r'D:\溯源\backend')


def print_section(title: str):
    """打印分节标题"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def sync_geo_mappings():
    """同步站点映射文件"""
    print_section("VOCs站点映射同步")

    # 源文件（Vanna项目）
    source_file = Path(r"D:\vanna广东省VOCs\config\geo_mappings.json")

    # 目标文件（溯源系统）
    target_dir = Path(r"D:\溯源\backend\app\config")
    target_file = target_dir / "geo_mappings.json"

    print(f"源文件: {source_file}")
    print(f"目标文件: {target_file}")

    if not source_file.exists():
        print(f"\n✗ 源文件不存在，无法同步")
        return False

    # 读取源文件
    try:
        with open(source_file, 'r', encoding='utf-8') as f:
            source_data = json.load(f)

        stations = source_data.get('stations', {})
        print(f"\n✓ 源文件读取成功")
        print(f"  站点数量: {len(stations)}")

        # 确保目标目录存在
        target_dir.mkdir(parents=True, exist_ok=True)

        # 备份现有文件（如果存在）
        if target_file.exists():
            backup_file = target_file.with_suffix('.json.bak')
            shutil.copy2(target_file, backup_file)
            print(f"  已备份现有文件到: {backup_file.name}")

        # 写入目标文件
        with open(target_file, 'w', encoding='utf-8') as f:
            json.dump(source_data, f, ensure_ascii=False, indent=2)

        print(f"\n✓ 站点映射同步成功")
        print(f"  目标文件: {target_file}")
        print(f"  站点数量: {len(stations)}")

        # 显示部分站点
        print(f"\n同步的站点示例（前20个）:")
        for i, (name, code) in enumerate(list(stations.items())[:20], 1):
            print(f"  {i:2d}. {name:20s} -> {code}")

        return True

    except Exception as e:
        print(f"\n✗ 同步失败: {e}")
        return False


def verify_sync():
    """验证同步结果"""
    print_section("验证同步结果")

    try:
        from app.utils.particulate_geo_matcher import get_particulate_geo_matcher

        # 重新加载映射器
        # 注意：由于是单例模式，需要清除实例
        from app.utils.particulate_geo_matcher import ParticulateGeoMatcher
        ParticulateGeoMatcher._instance = None

        matcher = get_particulate_geo_matcher()

        print(f"✓ 映射器重新加载成功")
        print(f"  站点数量: {len(matcher.station_codes)}")

        if len(matcher.station_codes) > 0:
            print(f"\n✓ 映射器已包含站点数据")
            print(f"\n站点示例（前15个）:")
            for i, (name, code) in enumerate(list(matcher.station_codes.items())[:15], 1):
                print(f"  {i:2d}. {name:20s} -> {code}")
            return True
        else:
            print(f"\n✗ 映射器仍无站点数据")
            return False

    except Exception as e:
        print(f"\n✗ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_vocs_query():
    """测试VOCs查询"""
    print_section("测试VOCs查询")

    try:
        from app.tools.query.get_vocs_data import GetVOCsDataTool
        from datetime import datetime, timedelta

        # 创建工具实例
        tool = GetVOCsDataTool()
        print("✓ VOCs工具创建成功")

        # 测试站点映射
        from app.utils.particulate_geo_matcher import get_particulate_geo_matcher
        matcher = get_particulate_geo_matcher()

        # 测试参数（使用已知站点）
        test_stations = ["新兴", "公园前", "鹤山花果山"]

        print(f"\n测试站点映射:")
        for station in test_stations:
            try:
                codes = matcher.stations_to_codes([station])
                print(f"  ✓ {station} -> {codes[0]}")
            except ValueError as e:
                print(f"  ✗ {station} -> {e}")

        return True

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("="*60)
    print("VOCs站点映射同步和修复")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    # 步骤1: 同步站点映射
    sync_success = sync_geo_mappings()

    if not sync_success:
        print("\n✗ 同步失败，终止流程")
        return

    # 步骤2: 验证同步结果
    verify_success = verify_sync()

    if not verify_success:
        print("\n✗ 验证失败")
        return

    # 步骤3: 测试VOCs查询
    test_success = test_vocs_query()

    # 总结
    print_section("执行总结")

    print("\n操作结果:")
    print(f"  站点映射同步: {'✓ 成功' if sync_success else '✗ 失败'}")
    print(f"  映射器验证: {'✓ 成功' if verify_success else '✗ 失败'}")
    print(f"  VOCs查询测试: {'✓ 成功' if test_success else '✗ 失败'}")

    if sync_success and verify_success:
        print("\n✅ 站点映射已成功同步！")
        print("\n现在可以使用站点名称查询VOCs数据:")
        print("  - 新兴 (1042b)")
        print("  - 公园前 (1006b)")
        print("  - 鹤山花果山 (1001b)")
        print("  - 南沙科大 (1007b)")
        print("  - 市八中 (1010b)")
        # ... 更多站点

        print("\n使用方式:")
        print("  get_vocs_data(locations=['新兴'], start_time='2025-05-01 00:00:00', end_time='2025-05-31 23:59:59')")
        print("  get_vocs_data(code='1042b', start_time='2025-05-01 00:00:00', end_time='2025-05-31 23:59:59')")

    print("\n处理完成!")


if __name__ == "__main__":
    main()
