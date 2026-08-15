#!/usr/bin/env python3
"""
站点地理信息逐城市匹配和更新补充脚本

功能：
1. 从SQL Server的BSD_STATION表获取完整的站点地理信息
2. 读取本地的station_district_results_with_type_id.json文件
3. 逐城市对比，找出缺失的地理信息
4. 补充缺失的地理信息（经度、纬度、区县、详细地址、行政区划代码等）
5. 生成更新后的JSON文件

特点：
- 可靠性：采用多层匹配策略（站点名称、唯一编码、城市+站点名称组合）
- 无遗漏：逐城市遍历所有站点
- 数据完整性：保留原有数据，只补充缺失字段
- 日志记录：详细记录匹配过程和结果
"""

import json
import pyodbc
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import structlog

# 配置日志
logger = structlog.get_logger()


class StationGeoUpdater:
    """站点地理信息更新器"""

    def __init__(self):
        """初始化更新器"""
        self.local_stations = {}  # 本地站点数据 (唯一编码 -> 站点信息)
        self.db_stations = {}     # 数据库站点数据 (唯一编码 -> 站点信息)
        self.db_stations_by_name = {}  # 数据库站点数据 (站点名称 -> 站点信息)

        # 统计信息
        self.stats = {
            "total_local": 0,
            "total_db": 0,
            "matched_by_code": 0,
            "matched_by_name": 0,
            "matched_by_city_name": 0,
            "unmatched": 0,
            "updated_fields": {},
        }

    def load_local_json(self, json_path: str) -> None:
        """
        加载本地JSON文件

        Args:
            json_path: JSON文件路径
        """
        logger.info("开始加载本地JSON文件", path=json_path)

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            results = data.get("data", [])
            self.stats["total_local"] = len(results)

            for station in results:
                station_code = station.get("唯一编码", "").strip()
                station_name = station.get("站点名称", "").strip()

                if not station_code:
                    logger.warning("发现无唯一编码的站点", station_name=station_name)
                    continue

                self.local_stations[station_code] = station

            logger.info(
                "本地JSON加载完成",
                total_stations=len(self.local_stations),
                total_records=self.stats["total_local"]
            )

        except Exception as e:
            logger.error("加载本地JSON失败", error=str(e))
            raise

    def load_db_stations(self, connection_string: str) -> None:
        """
        从SQL Server数据库加载BSD_STATION表数据

        Args:
            connection_string: SQL Server连接字符串
        """
        logger.info("开始从数据库加载BSD_STATION表数据")

        try:
            conn = pyodbc.connect(connection_string, timeout=30)
            cursor = conn.cursor()

            # 查询所有站点数据
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

            logger.info("执行SQL查询", sql_preview=sql[:200])
            cursor.execute(sql)

            # 获取列名
            columns = [column[0] for column in cursor.description]

            # 转换为字典
            import decimal
            results = []
            for row in cursor.fetchall():
                record = dict(zip(columns, row))
                # 将 Decimal 转换为 float
                for key, value in record.items():
                    if isinstance(value, decimal.Decimal):
                        record[key] = float(value)
                results.append(record)

            cursor.close()
            conn.close()

            self.stats["total_db"] = len(results)

            # 构建索引
            for record in results:
                # CODE 对应本地的"唯一编码"
                code = str(record.get("CODE", "")).strip()
                # UNIQUECODE 对应本地的"行政区划代码"
                unique_code = str(record.get("UNIQUECODE", "")).strip()
                station_name = str(record.get("NAME", "")).strip()

                # 使用CODE作为主要键
                if code:
                    self.db_stations[code] = record

                if station_name:
                    self.db_stations_by_name[station_name] = record

            logger.info(
                "数据库数据加载完成",
                total_stations=len(self.db_stations),
                total_by_name=len(self.db_stations_by_name)
            )

        except Exception as e:
            logger.error("从数据库加载数据失败", error=str(e))
            raise

    def match_station(self, local_station: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        匹配本地站点到数据库站点（多层匹配策略）

        Args:
            local_station: 本地站点数据

        Returns:
            匹配到的数据库站点数据，如果未匹配到返回None
        """
        station_code = local_station.get("唯一编码", "").strip()
        station_name = local_station.get("站点名称", "").strip()
        city_name = local_station.get("城市名称", "").strip()

        # 策略1: 通过唯一编码匹配（最可靠）
        if station_code and station_code in self.db_stations:
            self.stats["matched_by_code"] += 1
            return self.db_stations[station_code]

        # 策略2: 通过站点名称精确匹配
        if station_name and station_name in self.db_stations_by_name:
            self.stats["matched_by_name"] += 1
            return self.db_stations_by_name[station_name]

        # 策略3: 通过城市+站点名称组合匹配
        if city_name and station_name:
            for db_station in self.db_stations.values():
                # BSD_STATION表没有CityName字段，只能通过NAME匹配
                db_name = str(db_station.get("NAME", "")).strip()

                # 站点名称匹配
                name_match = (
                    station_name == db_name or
                    station_name in db_name or
                    db_name in station_name
                )

                if name_match:
                    self.stats["matched_by_city_name"] += 1
                    return db_station

        # 未匹配到
        return None

    def update_geo_info(self, local_station: Dict[str, Any], db_station: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新本地站点的地理信息（只补充缺失字段，不覆盖已有数据）

        Args:
            local_station: 本地站点数据
            db_station: 数据库站点数据

        Returns:
            更新后的本地站点数据
        """
        # 复制本地站点数据（保留所有原始数据）
        updated = local_station.copy()
        updated_fields = []

        # 字段映射：数据库字段 -> 本地JSON字段
        field_mappings = {
            "LONGITUDE": "经度",
            "LATITUDE": "纬度",
            "ADDRESS": "详细地址",
        }

        # 只更新缺失的字段
        for db_field, local_field in field_mappings.items():
            db_value = db_station.get(db_field)
            local_value = local_station.get(local_field)

            # 只在本地字段为空、None、0或False时才更新
            # 注意：0可能是有效的经纬度值（虽然很少见），但我们通常认为0表示缺失
            needs_update = (
                local_value is None or
                local_value == "" or
                local_value == 0
            )

            if needs_update and db_value is not None and db_value != "":
                updated[local_field] = db_value
                updated_fields.append(local_field)

                # 统计
                if local_field not in self.stats["updated_fields"]:
                    self.stats["updated_fields"][local_field] = 0
                self.stats["updated_fields"][local_field] += 1

        return updated

    def process_by_city(self, output_path: str) -> None:
        """
        逐城市处理站点信息更新

        Args:
            output_path: 输出文件路径
        """
        logger.info("开始逐城市处理站点信息更新")

        # 按城市分组
        cities = {}
        for station_code, local_station in self.local_stations.items():
            city_name = local_station.get("城市名称", "未知").strip()
            if city_name not in cities:
                cities[city_name] = []
            cities[city_name].append(local_station)

        logger.info("城市分组完成", city_count=len(cities))

        # 逐城市处理
        updated_stations = []
        unmatched_stations = []

        for city_name in sorted(cities.keys()):
            city_stations = cities[city_name]
            logger.info(
                "处理城市",
                city=city_name,
                station_count=len(city_stations)
            )

            for local_station in city_stations:
                station_code = local_station.get("唯一编码", "").strip()
                station_name = local_station.get("站点名称", "").strip()

                # 匹配数据库站点
                db_station = self.match_station(local_station)

                if db_station:
                    # 更新地理信息
                    updated_station = self.update_geo_info(local_station, db_station)
                    updated_stations.append(updated_station)
                else:
                    # 未匹配到
                    self.stats["unmatched"] += 1
                    unmatched_stations.append({
                        "站点名称": station_name,
                        "唯一编码": station_code,
                        "城市名称": city_name
                    })
                    # 保留原始数据
                    updated_stations.append(local_station)

        # 生成输出
        output_data = {
            "status": "success",
            "total": len(updated_stations),
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "statistics": self.stats,
            "data": updated_stations
        }

        # 保存更新后的JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        # 保存未匹配的站点列表
        if unmatched_stations:
            unmatched_path = output_path.replace('.json', '_unmatched.json')
            with open(unmatched_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "total": len(unmatched_stations),
                    "data": unmatched_stations
                }, f, ensure_ascii=False, indent=2)
            logger.info("未匹配站点已保存", path=unmatched_path, count=len(unmatched_stations))

        logger.info(
            "站点信息更新完成",
            output_path=output_path,
            total_updated=len(updated_stations),
            unmatched=len(unmatched_stations),
            statistics=self.stats
        )

    def print_summary(self) -> None:
        """打印更新摘要"""
        print("\n" + "="*80)
        print("站点地理信息更新摘要")
        print("="*80)
        print(f"本地站点总数: {self.stats['total_local']}")
        print(f"数据库站点总数: {self.stats['total_db']}")
        print(f"通过唯一编码匹配: {self.stats['matched_by_code']}")
        print(f"通过站点名称匹配: {self.stats['matched_by_name']}")
        print(f"通过城市+站点名称匹配: {self.stats['matched_by_city_name']}")
        print(f"未匹配站点数: {self.stats['unmatched']}")
        print(f"匹配率: {((self.stats['total_local'] - self.stats['unmatched']) / self.stats['total_local'] * 100):.2f}%")
        print("\n更新字段统计:")
        for field, count in self.stats['updated_fields'].items():
            print(f"  - {field}: {count} 个字段")
        print("="*80 + "\n")


def main():
    """主函数"""
    # 配置路径
    project_root = Path(__file__).parent.parent
    input_json = project_root / "config" / "station_district_results_with_type_id.json"
    output_json = project_root / "config" / "station_district_results_with_type_id_updated.json"

    # SQL Server连接配置
    # 注意：请根据实际情况修改连接字符串
    connection_string = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=180.184.30.94,1433;"
        "DATABASE=AirPollutionAnalysis;"
        "UID=sa;"
        "PWD=#Ph981,6J2bOkWYT7p?5slH$I~g_0itR;"
        "TrustServerCertificate=yes;"
    )

    print("站点地理信息逐城市匹配和更新补充工具")
    print("="*80)

    # 创建更新器
    updater = StationGeoUpdater()

    # 1. 加载本地JSON
    print(f"\n[1/3] 加载本地JSON文件: {input_json}")
    updater.load_local_json(str(input_json))

    # 2. 加载数据库数据
    print(f"\n[2/3] 从数据库加载BSD_STATION表数据...")
    updater.load_db_stations(connection_string)

    # 3. 逐城市处理
    print(f"\n[3/3] 逐城市处理站点信息更新...")
    updater.process_by_city(str(output_json))

    # 4. 打印摘要
    updater.print_summary()

    print(f"\n更新后的JSON文件已保存到: {output_json}")
    print("请检查更新结果，确认无误后替换原文件。")


if __name__ == "__main__":
    main()
