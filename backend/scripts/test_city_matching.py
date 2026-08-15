#!/usr/bin/env python3
"""
单城市站点匹配测试脚本

功能：
1. 测试指定城市的站点匹配情况
2. 显示匹配前后的对比
3. 用于调试和验证匹配逻辑
"""

import json
import pyodbc
from pathlib import Path
from typing import Dict, List, Any, Optional
import structlog

# 配置日志
logger = structlog.get_logger()


def load_db_stations(connection_string: str) -> Dict[str, Dict[str, Any]]:
    """
    从数据库加载BSD_STATION表数据

    Args:
        connection_string: SQL Server连接字符串

    Returns:
        站点数据字典 (唯一编码 -> 站点信息)
    """
    logger.info("从数据库加载BSD_STATION表数据")

    try:
        conn = pyodbc.connect(connection_string, timeout=30)
        cursor = conn.cursor()

        sql = """
            SELECT
                STATIONID,
                CODE,
                NAME,
                REGIONID,
                LONGITUDE,
                LATITUDE,
                ADDRESS,
                UNIQUECODE,
                DDSTATIONTYPE,
                STATUS
            FROM BSD_STATION
            WHERE STATUS = 1
        """

        cursor.execute(sql)

        columns = [column[0] for column in cursor.description]
        results = []

        for row in cursor.fetchall():
            record = dict(zip(columns, row))
            results.append(record)

        cursor.close()
        conn.close()

        # 构建索引
        stations_by_code = {}
        for record in results:
            # 优先使用UNIQUECODE，其次使用CODE
            unique_code = str(record.get("UNIQUECODE", "")).strip()
            code = str(record.get("CODE", "")).strip()
            station_code = unique_code if unique_code else code

            if station_code:
                stations_by_code[station_code] = record

        logger.info("数据库数据加载完成", total_stations=len(stations_by_code))
        return stations_by_code

    except Exception as e:
        logger.error("从数据库加载数据失败", error=str(e))
        raise


def load_local_stations(json_path: str, target_city: str = None) -> List[Dict[str, Any]]:
    """
    加载本地JSON文件中的站点数据

    Args:
        json_path: JSON文件路径
        target_city: 目标城市（如果指定，只返回该城市的站点）

    Returns:
        站点数据列表
    """
    logger.info("加载本地JSON文件", path=json_path, target_city=target_city)

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        results = data.get("data", [])
        stations = []

        for station in results:
            city_name = station.get("城市名称", "").strip()

            if target_city is None or city_name == target_city or city_name == target_city + "市":
                stations.append(station)

        logger.info("本地数据加载完成", total_stations=len(stations))
        return stations

    except Exception as e:
        logger.error("加载本地JSON失败", error=str(e))
        raise


def match_station(local_station: Dict[str, Any], db_stations: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    匹配本地站点到数据库站点

    Args:
        local_station: 本地站点数据
        db_stations: 数据库站点数据

    Returns:
        匹配到的数据库站点数据，如果未匹配到返回None
    """
    station_code = local_station.get("唯一编码", "").strip()
    station_name = local_station.get("站点名称", "").strip()
    city_name = local_station.get("城市名称", "").strip()

    # 策略1: 通过唯一编码匹配
    if station_code and station_code in db_stations:
        return db_stations[station_code]

    # 策略2: 通过站点名称精确匹配
    for db_station in db_stations.values():
        db_name = str(db_station.get("NAME", "")).strip()
        if station_name == db_name:
            return db_station

    # 策略3: 通过城市+站点名称组合匹配
    if city_name and station_name:
        for db_station in db_stations.values():
            # BSD_STATION表没有CityName字段，只能通过NAME匹配
            db_name = str(db_station.get("NAME", "")).strip()

            # 城市名称匹配
            city_match = (
                city_name == db_city or
                city_name == db_city.replace("市", "") or
                city_name + "市" == db_city
            )

            # 站点名称匹配
            name_match = (
                station_name == db_name or
                station_name in db_name or
                db_name in station_name
            )

            if city_match and name_match:
                return db_station

    return None


def print_station_comparison(local_station: Dict[str, Any], db_station: Dict[str, Any]) -> None:
    """
    打印站点对比信息

    Args:
        local_station: 本地站点数据
        db_station: 数据库站点数据
    """
    print("\n" + "="*80)
    print(f"站点: {local_station.get('站点名称')} ({local_station.get('唯一编码')})")
    print("="*80)

    # 字段映射
    field_mappings = {
        "NAME": "站点名称",
        "UNIQUECODE": "唯一编码",
        "CODE": "编码",
        "REGIONID": "区域ID",
        "LONGITUDE": "经度",
        "LATITUDE": "纬度",
        "ADDRESS": "详细地址",
        "DDSTATIONTYPE": "站点类型ID",
    }

    print("\n{:<30} {:<20} {:<20}".format("字段", "本地值", "数据库值"))
    print("-"*80)

    for db_field, local_field in field_mappings.items():
        local_value = str(local_station.get(local_field, "")).strip()
        db_value = str(db_station.get(db_field, "")).strip()

        # 检查是否有变化
        if local_value != db_value and local_value == "":
            marker = " ➜"  # 表示将被更新
        elif local_value != db_value:
            marker = " ⚠"  # 表示有差异
        else:
            marker = ""   # 表示相同

        print("{:<30} {:<20} {:<20}{}".format(
            local_field,
            local_value if local_value else "(空)",
            db_value if db_value else "(空)",
            marker
        ))

    print("="*80)


def test_city_matching(city_name: str):
    """
    测试指定城市的站点匹配

    Args:
        city_name: 城市名称
    """
    print(f"\n测试城市: {city_name}")
    print("="*80)

    # 配置路径
    project_root = Path(__file__).parent.parent
    json_path = project_root / "config" / "station_district_results_with_type_id.json"

    # SQL Server连接配置
    connection_string = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=180.184.30.94,1433;"
        "DATABASE=AirPollutionAnalysis;"
        "UID=sa;"
        "PWD=#Ph981,6J2bOkWYT7p?5slH$I~g_0itR;"
        "TrustServerCertificate=yes;"
    )

    # 1. 加载数据库数据
    print("\n[1/3] 加载数据库数据...")
    db_stations = load_db_stations(connection_string)

    # 2. 加载本地数据（指定城市）
    print(f"\n[2/3] 加载本地数据（城市: {city_name}）...")
    local_stations = load_local_stations(str(json_path), city_name)

    if not local_stations:
        print(f"\n未找到城市 '{city_name}' 的站点数据")
        return

    # 3. 逐个匹配并显示对比
    print(f"\n[3/3] 匹配站点并显示对比...")
    print(f"共 {len(local_stations)} 个站点")

    matched_count = 0
    unmatched_count = 0

    for local_station in local_stations:
        db_station = match_station(local_station, db_stations)

        if db_station:
            matched_count += 1
            print_station_comparison(local_station, db_station)
        else:
            unmatched_count += 1
            print("\n" + "="*80)
            print(f"⚠ 未匹配到站点: {local_station.get('站点名称')} ({local_station.get('唯一编码')})")
            print("="*80)

    # 统计
    print("\n" + "="*80)
    print("匹配统计")
    print("="*80)
    print(f"总站点数: {len(local_stations)}")
    print(f"已匹配: {matched_count} ({matched_count/len(local_stations)*100:.1f}%)")
    print(f"未匹配: {unmatched_count} ({unmatched_count/len(local_stations)*100:.1f}%)")
    print("="*80)


def main():
    """主函数"""
    import sys

    if len(sys.argv) < 2:
        print("用法: python test_city_matching.py <城市名称>")
        print("示例: python test_city_matching.py 广州")
        print("\n如果不指定城市，将测试所有城市")
        sys.exit(1)

    city_name = sys.argv[1]
    test_city_matching(city_name)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        # 如果没有指定城市，测试广州
        print("未指定城市，测试广州...")
        test_city_matching("广州")
    else:
        city_name = sys.argv[1]
        test_city_matching(city_name)
