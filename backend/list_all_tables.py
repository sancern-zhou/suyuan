"""
列出SQL Server数据库中的所有表
"""
import pyodbc
from config.settings import settings
import re

def list_all_tables(database: str = "XcAiDb"):
    """
    列出数据库中的所有表

    Args:
        database: 数据库名称
    """
    try:
        conn_str = settings.sqlserver_connection_string
        conn_str = re.sub(r'DATABASE=\w+', f'DATABASE={database}', conn_str, flags=re.IGNORECASE)

        print(f"\n数据库: {database}")
        print("=" * 80)

        conn = pyodbc.connect(conn_str, timeout=30)
        cursor = conn.cursor()

        # 查询所有表
        sql = """
            SELECT TABLE_SCHEMA, TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_SCHEMA, TABLE_NAME
        """
        cursor.execute(sql)
        all_tables = cursor.fetchall()

        cursor.close()
        conn.close()

        print(f"总表数: {len(all_tables)}\n")

        # 按schema分组显示
        current_schema = None
        for schema, name in all_tables:
            if schema != current_schema:
                current_schema = schema
                print(f"\n[{schema}]")
            print(f"  {name}")

    except Exception as e:
        print(f"列出表失败: {str(e)}")

if __name__ == "__main__":
    list_all_tables("XcAiDb")
    list_all_tables("AirPollutionAnalysis")
