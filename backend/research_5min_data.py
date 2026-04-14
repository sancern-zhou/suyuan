"""
调研站点5分钟数据查询工具的实现方案
"""
import pyodbc
from config.settings import settings
import re

def research_station_info():
    """调研站点信息查询"""
    try:
        conn_str = settings.sqlserver_connection_string
        conn_str = re.sub(r'DATABASE=\w+', 'DATABASE=air_quality_db', conn_str, flags=re.IGNORECASE)

        conn = pyodbc.connect(conn_str, timeout=30)
        cursor = conn.cursor()

        print("=" * 80)
        print("【调研1：站点代码查询】")
        print("=" * 80)

        # 查询XcAiDb数据库中的站点信息
        conn_str_xcai = settings.sqlserver_connection_string
        conn_xcai = pyodbc.connect(conn_str_xcai, timeout=30)
        cursor_xcai = conn_xcai.cursor()

        # 查看bsd_station表结构
        print("\n1.1 bsd_station表结构（站点信息表）:")
        print("-" * 80)
        sql = """
            SELECT TOP 5 * FROM bsd_station
        """
        cursor_xcai.execute(sql)
        if cursor_xcai.description:
            col_names = [desc[0] for desc in cursor_xcai.description]
            print(f"字段: {', '.join(col_names)}")
            rows = cursor_xcai.fetchall()
            for row in rows[:3]:
                print(f"  样例: {dict(zip(col_names, row))}")

        # 查询特定站点1001A
        print("\n1.2 查询站点1001A的信息:")
        print("-" * 80)
        sql = """
            SELECT * FROM bsd_station WHERE StationCode = '1001A'
        """
        cursor_xcai.execute(sql)
        row = cursor_xcai.fetchone()
        if row and cursor_xcai.description:
            col_names = [desc[0] for desc in cursor_xcai.description]
            print(f"站点信息: {dict(zip(col_names, row))}")

        cursor_xcai.close()
        conn_xcai.close()

        print("\n" + "=" * 80)
        print("【调研2：污染物代码含义】")
        print("=" * 80)

        # 查询污染物代码分布
        print("\n2.1 Air_5m_2026_1001A_Src表中的污染物代码:")
        print("-" * 80)
        sql = """
            SELECT DISTINCT PollutantCode, COUNT(*) as count
            FROM Air_5m_2026_1001A_Src
            GROUP BY PollutantCode
            ORDER BY PollutantCode
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        print(f"污染物代码\t记录数")
        print("-" * 40)
        for row in rows:
            print(f"{row[0]}\t\t{row[1]:,}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"调研失败: {str(e)}")
        import traceback
        traceback.print_exc()

def research_meteorological_data():
    """调研气象数据"""
    try:
        conn_str = settings.sqlserver_connection_string
        conn_str = re.sub(r'DATABASE=\w+', 'DATABASE=air_quality_db', conn_str, flags=re.IGNORECASE)

        conn = pyodbc.connect(conn_str, timeout=30)
        cursor = conn.cursor()

        print("\n" + "=" * 80)
        print("【调研3：气象数据】")
        print("=" * 80)

        # 列出所有5分钟数据表
        print("\n3.1 所有5分钟数据表:")
        print("-" * 80)
        sql = """
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME LIKE 'Air_5m_%'
            ORDER BY TABLE_NAME
        """
        cursor.execute(sql)
        tables = cursor.fetchall()
        for table in tables:
            print(f"  - {table[0]}")

        # 检查是否有气象字段
        print("\n3.2 检查Air_5m_2026_1001A_Src表是否有气象字段:")
        print("-" * 80)
        sql = """
            SELECT TOP 5 *
            FROM Air_5m_2026_1001A_Src
            WHERE PollutantCode IN ('WD', 'WS', 'TEMP', 'RH')
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        if rows:
            print("找到气象数据:")
            if cursor.description:
                col_names = [desc[0] for desc in cursor.description]
                for row in rows[:3]:
                    print(f"  {dict(zip(col_names, row))}")
        else:
            print("未找到气象数据（WD=风向, WS=风速, TEMP=温度, RH=湿度）")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"调研失败: {str(e)}")
        import traceback
        traceback.print_exc()

def research_data_sample():
    """调研数据样例"""
    try:
        conn_str = settings.sqlserver_connection_string
        conn_str = re.sub(r'DATABASE=\w+', 'DATABASE=air_quality_db', conn_str, flags=re.IGNORECASE)

        conn = pyodbc.connect(conn_str, timeout=30)
        cursor = conn.cursor()

        print("\n" + "=" * 80)
        print("【调研4：数据样例】")
        print("=" * 80)

        # 查询同一时刻的多个污染物
        print("\n4.1 同一时刻的多个污染物数据:")
        print("-" * 80)
        sql = """
            SELECT TOP 10 *
            FROM Air_5m_2026_1001A_Src
            WHERE TimePoint >= '2026-01-01 00:00:00'
            ORDER BY TimePoint, PollutantCode
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        if cursor.description:
            col_names = [desc[0] for desc in cursor.description]
            for row in rows:
                record = dict(zip(col_names, row))
                print(f"  {record['TimePoint']} | {record['PollutantCode']} | {record['MonValue']}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"调研失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    research_station_info()
    research_meteorological_data()
    research_data_sample()
