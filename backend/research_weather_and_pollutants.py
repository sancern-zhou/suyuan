"""
调研气象数据来源和污染物代码含义
"""
import pyodbc
from config.settings import settings
import re

def research_pollutant_codes():
    """调研污染物代码含义"""
    try:
        conn_str = settings.sqlserver_connection_string

        conn = pyodbc.connect(conn_str, timeout=30)
        cursor = conn.cursor()

        print("=" * 80)
        print("【调研5：污染物代码含义】")
        print("=" * 80)

        # 查看是否有污染物代码映射表
        print("\n5.1 查找污染物代码映射表:")
        print("-" * 80)

        # 尝试查询一些可能的表
        possible_tables = [
            'bsd_pollutant',
            'pollutant_code',
            'pollutant_info',
            'dat_pollutant'
        ]

        for table in possible_tables:
            try:
                sql = f"SELECT TOP 3 * FROM {table}"
                cursor.execute(sql)
                if cursor.description:
                    col_names = [desc[0] for desc in cursor.description]
                    print(f"\n表 {table}:")
                    print(f"  字段: {', '.join(col_names)}")
                    rows = cursor.fetchall()
                    for row in rows:
                        print(f"  样例: {dict(zip(col_names, row))}")
            except:
                pass

        # 查看CityAQIPublishHistory表中的污染物字段
        print("\n5.2 CityAQIPublishHistory表中的污染物字段:")
        print("-" * 80)
        sql = """
            SELECT TOP 1 *
            FROM CityAQIPublishHistory
        """
        cursor.execute(sql)
        if cursor.description:
            col_names = [desc[0] for desc in cursor.description]
            # 查找可能的污染物字段
            pollutant_fields = [col for col in col_names if 'pollutant' in col.lower() or 'code' in col.lower() or any(x in col.lower() for x in ['pm25', 'pm10', 'o3', 'no2', 'so2', 'co'])]
            print(f"可能的污染物字段: {', '.join(pollutant_fields)}")

            # 显示样例数据
            row = cursor.fetchone()
            if row:
                record = dict(zip(col_names, row))
                print(f"\n样例数据（前15个字段）:")
                for i, (k, v) in enumerate(list(record.items())[:15]):
                    print(f"  {k}: {v}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"调研失败: {str(e)}")
        import traceback
        traceback.print_exc()

def research_weather_data():
    """调研气象数据来源"""
    try:
        conn_str = settings.sqlserver_connection_string

        conn = pyodbc.connect(conn_str, timeout=30)
        cursor = conn.cursor()

        print("\n" + "=" * 80)
        print("【调研6：气象数据来源】")
        print("=" * 80)

        # 查看dat_weather_hour表
        print("\n6.1 dat_weather_hour表结构:")
        print("-" * 80)
        sql = """
            SELECT TOP 3 *
            FROM dat_weather_hour
            WHERE StationCode = '1001A'
            ORDER BY TimePoint DESC
        """
        cursor.execute(sql)
        if cursor.description:
            col_names = [desc[0] for desc in cursor.description]
            print(f"字段: {', '.join(col_names)}")
            rows = cursor.fetchall()
            for row in rows:
                record = dict(zip(col_names, row))
                print(f"\n样例数据:")
                for k, v in list(record.items())[:10]:
                    print(f"  {k}: {v}")

        # 查看HourlyWeather表
        print("\n6.2 HourlyWeather表结构:")
        print("-" * 80)
        sql = """
            SELECT TOP 3 *
            FROM HourlyWeather
            ORDER BY TimePoint DESC
        """
        cursor.execute(sql)
        if cursor.description:
            col_names = [desc[0] for desc in cursor.description]
            print(f"字段: {', '.join(col_names)}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"调研失败: {str(e)}")
        import traceback
        traceback.print_exc()

def research_city_station_mapping():
    """调研城市和站点映射关系"""
    try:
        conn_str = settings.sqlserver_connection_string

        conn = pyodbc.connect(conn_str, timeout=30)
        cursor = conn.cursor()

        print("\n" + "=" * 80)
        print("【调研7：城市和站点映射关系】")
        print("=" * 80)

        # 查看bsd_city表
        print("\n7.1 bsd_city表结构:")
        print("-" * 80)
        sql = """
            SELECT TOP 5 *
            FROM bsd_city
        """
        cursor.execute(sql)
        if cursor.description:
            col_names = [desc[0] for desc in cursor.description]
            print(f"字段: {', '.join(col_names)}")
            rows = cursor.fetchall()
            for row in rows[:3]:
                record = dict(zip(col_names, row))
                print(f"\n样例: {record}")

        # 查询北京的所有站点
        print("\n7.2 查询北京的所有站点:")
        print("-" * 80)
        sql = """
            SELECT s.positionname, s.stationcode, c.cityname
            FROM bsd_station s
            LEFT JOIN bsd_city c ON s.cityareacode = c.cityareacode
            WHERE c.cityname LIKE N'%北京%'
            ORDER BY s.stationcode
        """
        cursor.execute(sql)
        if cursor.description:
            col_names = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            print(f"找到 {len(rows)} 个站点:")
            for row in rows[:10]:
                record = dict(zip(col_names, row))
                print(f"  {record['positionname']}\t{record['stationcode']}\t{record.get('cityname', 'N/A')}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"调研失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    research_pollutant_codes()
    research_weather_data()
    research_city_station_mapping()
