"""
修复后的调研脚本
"""
import pyodbc
from config.settings import settings
import re

def research_weather_table_structure():
    """调研气象表结构"""
    try:
        conn_str = settings.sqlserver_connection_string
        conn = pyodbc.connect(conn_str, timeout=30)
        cursor = conn.cursor()

        print("=" * 80)
        print("【调研6：气象数据来源】")
        print("=" * 80)

        # 查看dat_weather_hour表结构
        print("\n6.1 dat_weather_hour表结构:")
        print("-" * 80)
        sql = """
            SELECT TOP 3 *
            FROM dat_weather_hour
        """
        cursor.execute(sql)
        if cursor.description:
            col_names = [desc[0] for desc in cursor.description]
            print(f"字段: {', '.join(col_names)}")
            rows = cursor.fetchall()
            for row in rows[:2]:
                record = dict(zip(col_names, row))
                print(f"\n样例数据:")
                for k, v in list(record.items())[:12]:
                    print(f"  {k}: {v}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"调研失败: {str(e)}")
        import traceback
        traceback.print_exc()

def research_station_city_mapping():
    """调研站点城市映射"""
    try:
        conn_str = settings.sqlserver_connection_string
        conn = pyodbc.connect(conn_str, timeout=30)
        cursor = conn.cursor()

        print("\n" + "=" * 80)
        print("【调研7：站点城市映射】")
        print("=" * 80)

        # 查看bsd_station表完整结构
        print("\n7.1 bsd_station表完整结构:")
        print("-" * 80)
        sql = """
            SELECT TOP 3 *
            FROM bsd_station
        """
        cursor.execute(sql)
        if cursor.description:
            col_names = [desc[0] for desc in cursor.description]
            print(f"字段: {', '.join(col_names)}")
            rows = cursor.fetchall()
            for row in rows:
                record = dict(zip(col_names, row))
                print(f"\n样例: {record}")

        # 查看bsd_city表完整结构
        print("\n7.2 bsd_city表完整结构:")
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

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"调研失败: {str(e)}")
        import traceback
        traceback.print_exc()

def research_pollutant_code_meaning():
    """调研污染物代码含义"""
    try:
        # 从外部API查询污染物代码
        import requests

        print("\n" + "=" * 80)
        print("【调研8：污染物代码含义（从外部API）】")
        print("=" * 80)

        # 尝试从VOCs API查询
        url = "http://180.184.91.74:9092/api/uqp/query"
        params = {
            "stationCode": "1001A",
            "startTime": "2026-01-01 00:00:00",
            "endTime": "2026-01-01 01:00:00"
        }

        try:
            response = requests.post(url, json=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                print(f"\nVOCs API响应结构:")
                print(f"  Keys: {list(data.keys())}")
        except Exception as e:
            print(f"API查询失败: {e}")

        # 尝试从颗粒物API查询
        url = "http://180.184.91.74:9093/api/uqp/query"
        try:
            response = requests.post(url, json=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                print(f"\n颗粒物API响应结构:")
                print(f"  Keys: {list(data.keys())}")
        except Exception as e:
            print(f"API查询失败: {e}")

    except Exception as e:
        print(f"调研失败: {str(e)}")

if __name__ == "__main__":
    research_weather_table_structure()
    research_station_city_mapping()
    research_pollutant_code_meaning()
