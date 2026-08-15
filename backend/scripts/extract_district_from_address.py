#!/usr/bin/env python3
"""
从BSD_STATION表的地址字段中提取区县信息并更新到本地JSON文件
"""

import json
import pyodbc
import re
from pathlib import Path
from typing import Dict, Optional
import structlog

logger = structlog.get_logger()


class DistrictExtractor:
    """从地址中提取区县信息的工具"""

    # 各城市的区/镇列表（用于匹配）
    CITY_DISTRICTS = {
        "东莞": [
            '莞城', '南城', '东城', '万江', '石龙', '虎门', '厚街', '常平', '长安',
            '塘厦', '清溪', '黄江', '大朗', '凤岗', '樟木头', '大岭山', '望牛墩',
            '麻涌', '中堂', '高埗', '洪梅', '道滘', '沙田', '寮步', '松山湖',
            '企石', '石排', '茶山', '横沥', '桥头', '谢岗', '东坑', '石碣'
        ],
        "广州": [
            '荔湾', '越秀', '海珠', '天河', '白云', '黄埔', '番禺', '花都', '南沙',
            '从化', '增城', '萝岗', '经济开发区'
        ],
        "深圳": [
            '罗湖', '福田', '南山', '宝安', '龙岗', '盐田', '龙华', '坪山', '光明',
            '大鹏', '光明新区', '坪山新区', '龙华新区', '大鹏新区'
        ],
        "佛山": [
            '禅城', '南海', '顺德', '三水', '高明', '顺德区', '南海区', '三水区', '高明区'
        ],
        "中山": [
            '石岐', '东区', '南区', '西区', '火炬开发区', '港口', '沙溪', '大涌',
            '黄圃', '东凤', '古镇', '横栏', '南头', '民众', '南朗', '三乡', '板芙',
            '神湾', '三角'
        ],
        # 其他城市可以根据需要添加
    }

    def __init__(self):
        self.extraction_stats = {
            "total_processed": 0,
            "district_extracted": 0,
            "district_already_exists": 0,
            "not_found": 0
        }

    def extract_district(self, address: str, city: str = "") -> Optional[str]:
        """
        从地址中提取区县信息

        Args:
            address: 地址字符串
            city: 城市名称（用于选择匹配规则）

        Returns:
            提取的区县名称，如果未提取到返回None
        """
        if not address:
            return None

        # 清理地址字符串
        address = address.strip()

        # 方法1：使用城市特定的区/镇列表匹配
        city_key = None
        for key in self.CITY_DISTRICTS:
            if key in city:
                city_key = key
                break

        if city_key and city_key in self.CITY_DISTRICTS:
            for district in self.CITY_DISTRICTS[city_key]:
                if district in address:
                    return district

        # 方法2：使用正则表达式匹配通用模式
        # 匹配 "XX街道"（排除 "XX市街道"）
        match = re.search(r'(?!.*市街道)([\u4e00-\u9fa5]{2,4}?街道)', address)
        if match:
            district = match.group(1).replace('街道', '')
            # 过滤掉一些明显的非区县词汇
            if district not in ['市区', '城区', '镇区', '社区']:
                if len(district) >= 2:  # 至少2个字符
                    return district

        # 匹配 "XX镇"（排除 "XX市镇"）
        match = re.search(r'(?!.*市镇)([\u4e00-\u9fa5]{2,4}?镇)', address)
        if match:
            district = match.group(1).replace('镇', '')
            # 排除城市名本身
            if district not in ['东莞', '广州', '深圳', '佛山', '中山', '惠州',
                              '江门', '珠海', '汕头', '佛山', '肇庆', '清远', '市区']:
                if len(district) >= 2:
                    return district

        # 方法3：匹配 "XX区"
        match = re.search(r'([\u4e00-\u9fa5]{2,4}?区)', address)
        if match:
            district = match.group(1).replace('区', '')
            # 排除一些明显的非区县词汇
            if district not in ['市区', '城区', '镇区', '社区', '开发']:
                if len(district) >= 2:
                    return district + '区'  # 保留"区"后缀

        return None

    def load_db_stations(self, connection_string: str) -> Dict[str, Dict]:
        """从数据库加载BSD_STATION表数据"""
        logger.info("从数据库加载BSD_STATION表数据")

        try:
            conn = pyodbc.connect(connection_string, timeout=30)
            cursor = conn.cursor()

            sql = """
                SELECT CODE, NAME, ADDRESS, REGIONID
                FROM BSD_STATION
                WHERE STATUS = 1 AND ADDRESS IS NOT NULL AND ADDRESS != ''
            """

            cursor.execute(sql)

            stations = {}
            for row in cursor.fetchall():
                code = str(row[0]).strip()
                name = str(row[1]).strip()
                address = str(row[3] or "").strip()
                region_id = str(row[2] or "").strip()

                if code:
                    stations[code] = {
                        'name': name,
                        'address': address,
                        'region_id': region_id
                    }

            cursor.close()
            conn.close()

            logger.info(f"加载了 {len(stations)} 个站点数据")
            return stations

        except Exception as e:
            logger.error("从数据库加载数据失败", error=str(e))
            raise

    def update_json_file(self, json_path: str, db_stations: Dict[str, Dict]) -> None:
        """更新本地JSON文件中的区县信息"""
        logger.info("更新本地JSON文件", path=json_path)

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            stations = data.get("data", [])

            updated_count = 0
            for station in stations:
                self.extraction_stats["total_processed"] += 1

                # 只处理缺失区县的站点
                if station.get("区县"):
                    self.extraction_stats["district_already_exists"] += 1
                    continue

                code = station.get("唯一编码", "").strip()
                city_name = station.get("城市名称", "").strip()
                address = station.get("详细地址", "").strip()

                # 优先使用数据库中的地址
                db_address = None
                if code in db_stations:
                    db_address = db_stations[code]['address']

                # 使用数据库地址（如果有）或本地地址
                addr_to_extract = db_address if db_address else address

                if addr_to_extract:
                    # 提取区县
                    district = self.extract_district(addr_to_extract, city_name)

                    if district:
                        station["区县"] = district
                        updated_count += 1
                        self.extraction_stats["district_extracted"] += 1
                        logger.info(
                            "提取成功",
                            station=station.get("站点名称"),
                            code=code,
                            district=district,
                            address=addr_to_extract[:50]
                        )
                    else:
                        self.extraction_stats["not_found"] += 1

            # 保存更新后的文件
            output_path = json_path.replace('.json', '_with_district.json')
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(
                "更新完成",
                output_path=output_path,
                updated_count=updated_count
            )

            return output_path, updated_count

        except Exception as e:
            logger.error("更新JSON文件失败", error=str(e))
            raise

    def print_summary(self):
        """打印提取摘要"""
        print("\n" + "="*80)
        print("区县信息提取摘要")
        print("="*80)
        print(f"处理站点总数: {self.extraction_stats['total_processed']}")
        print(f"成功提取区县: {self.extraction_stats['district_extracted']}")
        print(f"已有区县信息: {self.extraction_stats['district_already_exists']}")
        print(f"未提取到: {self.extraction_stats['not_found']}")
        print("="*80 + "\n")


def main():
    """主函数"""
    # 配置路径
    project_root = Path(__file__).parent.parent
    input_json = project_root / "config" / "station_district_results_with_type_id_updated.json"

    # SQL Server连接配置
    connection_string = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=180.184.30.94,1433;"
        "DATABASE=AirPollutionAnalysis;"
        "UID=sa;"
        "PWD=#Ph981,6J2bOkWYT7p?5slH$I~g_0itR;"
        "TrustServerCertificate=yes;"
    )

    print("从BSD_STATION表地址中提取区县信息")
    print("="*80)

    # 创建提取器
    extractor = DistrictExtractor()

    # 1. 加载数据库数据
    print(f"\n[1/2] 从数据库加载BSD_STATION表数据...")
    db_stations = extractor.load_db_stations(connection_string)

    # 2. 更新JSON文件
    print(f"\n[2/2] 更新本地JSON文件...")
    output_path, updated_count = extractor.update_json_file(str(input_json), db_stations)

    # 3. 打印摘要
    extractor.print_summary()

    print(f"\n更新后的JSON文件已保存到: {output_path}")
    print(f"共更新了 {updated_count} 个站点的区县信息")


if __name__ == "__main__":
    main()
