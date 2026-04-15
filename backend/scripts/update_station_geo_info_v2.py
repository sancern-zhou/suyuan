#!/usr/bin/env python3
"""
站点地理信息逐城市匹配和更新补充脚本 V2

改进：
- 只通过站点名称匹配（更可靠）
- 只补充缺失的字段，不覆盖已有数据
- 详细记录每个更新操作
"""

import json
import pyodbc
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import structlog

logger = structlog.get_logger()


class StationGeoUpdaterV2:
    """站点地理信息更新器 V2"""

    def __init__(self):
        self.local_stations = []  # 本地站点数据列表（改为列表以支持重复编码）
        self.db_stations_by_name = {}  # 数据库站点数据 (站点名称 -> 站点信息)

        # 统计信息
        self.stats = {
            "total_local": 0,
            "total_db": 0,
            "matched_by_name": 0,
            "updated_lon": 0,
            "updated_lat": 0,
            "updated_addr": 0,
            "update_log": [],
        }

    def load_local_json(self, json_path: str) -> None:
        """加载本地JSON文件"""
        logger.info("开始加载本地JSON文件", path=json_path)

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            results = data.get("data", [])
            self.stats["total_local"] = len(results)

            for station in results:
                # 直接添加到列表（包括没有唯一编码的站点）
                self.local_stations.append(station)

            logger.info(
                "本地JSON加载完成",
                total_stations=len(self.local_stations),
                total_records=self.stats["total_local"]
            )

        except Exception as e:
            logger.error("加载本地JSON失败", error=str(e))
            raise

    def load_db_stations(self, connection_string: str) -> None:
        """从SQL Server数据库加载BSD_STATION表数据"""
        logger.info("开始从数据库加载BSD_STATION表数据")

        try:
            conn = pyodbc.connect(connection_string, timeout=30)
            cursor = conn.cursor()

            sql = """
                SELECT
                    CODE,
                    NAME,
                    LONGITUDE,
                    LATITUDE,
                    ADDRESS
                FROM BSD_STATION
                WHERE STATUS = 1
            """

            cursor.execute(sql)

            import decimal
            results = []
            for row in cursor.fetchall():
                record = {
                    "CODE": row[0],
                    "NAME": row[1],
                    "LONGITUDE": float(row[2]) if row[2] else None,
                    "LATITUDE": float(row[3]) if row[3] else None,
                    "ADDRESS": row[4],
                }
                results.append(record)

            cursor.close()
            conn.close()

            self.stats["total_db"] = len(results)

            # 构建名称索引
            for record in results:
                name = record.get("NAME", "").strip()
                if name:
                    self.db_stations_by_name[name] = record

            logger.info(
                "数据库数据加载完成",
                total_stations=len(self.db_stations_by_name)
            )

        except Exception as e:
            logger.error("从数据库加载数据失败", error=str(e))
            raise

    def needs_update(self, local_station: Dict[str, Any], db_station: Dict[str, Any]) -> Dict[str, Any]:
        """
        检查站点是否需要更新，返回需要更新的字段

        只补充缺失的字段，不覆盖已有数据
        """
        updates = {}

        # 检查经度
        local_lon = local_station.get("经度")
        db_lon = db_station.get("LONGITUDE")
        if local_lon is None or local_lon == "" or local_lon == 0:
            if db_lon is not None and db_lon != 0:
                updates["经度"] = db_lon

        # 检查纬度
        local_lat = local_station.get("纬度")
        db_lat = db_station.get("LATITUDE")
        if local_lat is None or local_lat == "" or local_lat == 0:
            if db_lat is not None and db_lat != 0:
                updates["纬度"] = db_lat

        # 检查详细地址
        local_addr = local_station.get("详细地址")
        db_addr = db_station.get("ADDRESS")
        if local_addr is None or local_addr == "":
            if db_addr is not None and db_addr != "":
                updates["详细地址"] = db_addr

        return updates

    def process_by_city(self, output_path: str) -> None:
        """逐城市处理站点信息更新"""
        logger.info("开始逐城市处理站点信息更新")

        # 按城市分组
        cities = {}
        for local_station in self.local_stations:
            city_name = local_station.get("城市名称", "未知").strip()
            if city_name not in cities:
                cities[city_name] = []
            cities[city_name].append(local_station)

        logger.info("城市分组完成", city_count=len(cities))

        # 逐城市处理
        updated_stations = []

        for city_name in sorted(cities.keys()):
            city_stations = cities[city_name]
            logger.info(
                "处理城市",
                city=city_name,
                station_count=len(city_stations)
            )

            for local_station in city_stations:
                station_name = local_station.get("站点名称", "").strip()
                station_code = local_station.get("唯一编码", "").strip()

                # 通过站点名称匹配
                if station_name in self.db_stations_by_name:
                    db_station = self.db_stations_by_name[station_name]
                    self.stats["matched_by_name"] += 1

                    # 检查是否需要更新
                    updates = self.needs_update(local_station, db_station)

                    if updates:
                        # 创建更新后的站点
                        updated_station = local_station.copy()
                        updated_station.update(updates)

                        # 记录更新日志
                        log_entry = {
                            "station_name": station_name,
                            "station_code": station_code,
                            "city": city_name,
                            "updates": updates
                        }
                        self.stats["update_log"].append(log_entry)

                        # 统计
                        if "经度" in updates:
                            self.stats["updated_lon"] += 1
                        if "纬度" in updates:
                            self.stats["updated_lat"] += 1
                        if "详细地址" in updates:
                            self.stats["updated_addr"] += 1

                        updated_stations.append(updated_station)
                    else:
                        # 不需要更新，保留原数据
                        updated_stations.append(local_station)
                else:
                    # 未匹配到，保留原数据
                    updated_stations.append(local_station)

        # 生成输出
        output_data = {
            "status": "success",
            "total": len(updated_stations),
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "statistics": {
                "total_local": self.stats["total_local"],
                "total_db": self.stats["total_db"],
                "matched_by_name": self.stats["matched_by_name"],
                "updated_lon": self.stats["updated_lon"],
                "updated_lat": self.stats["updated_lat"],
                "updated_addr": self.stats["updated_addr"],
            },
            "data": updated_stations
        }

        # 保存更新后的JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        logger.info(
            "站点信息更新完成",
            output_path=output_path,
            total_updated=len(updated_stations),
            statistics=self.stats
        )

    def print_summary(self) -> None:
        """打印更新摘要"""
        print("\n" + "="*80)
        print("站点地理信息更新摘要")
        print("="*80)
        print(f"本地站点总数: {self.stats['total_local']}")
        print(f"数据库站点总数: {self.stats['total_db']}")
        print(f"通过站点名称匹配: {self.stats['matched_by_name']}")
        print(f"更新经度字段: {self.stats['updated_lon']}")
        print(f"更新纬度字段: {self.stats['updated_lat']}")
        print(f"更新详细地址字段: {self.stats['updated_addr']}")
        print("="*80 + "\n")


def main():
    """主函数"""
    # 配置路径
    project_root = Path(__file__).parent.parent
    input_json = project_root / "config" / "station_district_results_with_type_id.json"
    output_json = project_root / "config" / "station_district_results_with_type_id_updated.json"

    # SQL Server连接配置
    connection_string = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=180.184.30.94,1433;"
        "DATABASE=AirPollutionAnalysis;"
        "UID=sa;"
        "PWD=#Ph981,6J2bOkWYT7p?5slH$I~g_0itR;"
        "TrustServerCertificate=yes;"
    )

    print("站点地理信息逐城市匹配和更新补充工具 V2")
    print("="*80)

    # 创建更新器
    updater = StationGeoUpdaterV2()

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
