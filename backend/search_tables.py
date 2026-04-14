"""
搜索SQL Server数据库中包含特定关键词的表
"""
import pyodbc
from config.settings import settings
import re

def search_tables(keyword: str, database: str = "XcAiDb"):
    """
    搜索包含关键词的表

    Args:
        keyword: 搜索关键词
        database: 数据库名称
    """
    try:
        conn_str = settings.sqlserver_connection_string
        conn_str = re.sub(r'DATABASE=\w+', f'DATABASE={database}', conn_str, flags=re.IGNORECASE)

        print(f"搜索数据库: {database}")
        print(f"关键词: {keyword}")
        print("-" * 60)

        conn = pyodbc.connect(conn_str, timeout=30)
        cursor = conn.cursor()

        # 查询所有表
        sql = """
            SELECT TABLE_SCHEMA, TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
        """
        cursor.execute(sql)
        all_tables = cursor.fetchall()

        cursor.close()
        conn.close()

        # 搜索包含关键词的表
        keyword_lower = keyword.lower()
        matching = []
        for schema, name in all_tables:
            if keyword_lower in name.lower():
                matching.append((schema, name))

        if matching:
            print(f"找到 {len(matching)} 个包含 '{keyword}' 的表:\n")
            for schema, name in matching:
                print(f"  - {schema}.{name}")
        else:
            print(f"未找到包含 '{keyword}' 的表")

        print()

    except Exception as e:
        print(f"搜索失败: {str(e)}\n")

if __name__ == "__main__":
    keywords = ["Air", "5m", "Src", "2026"]

    for db in ["XcAiDb", "AirPollutionAnalysis"]:
        print("=" * 60)
        print(f"数据库: {db}")
        print("=" * 60)
        for keyword in keywords:
            search_tables(keyword, db)
