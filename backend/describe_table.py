"""
查看air_quality_db数据库中Air_5m_2026_1001A_Src表的结构和数据
"""
import pyodbc
from config.settings import settings
import re

def describe_table(table_name: str, database: str = "air_quality_db"):
    """
    查看表结构和样例数据

    Args:
        table_name: 表名
        database: 数据库名称
    """
    try:
        conn_str = settings.sqlserver_connection_string
        conn_str = re.sub(r'DATABASE=\w+', f'DATABASE={database}', conn_str, flags=re.IGNORECASE)

        print(f"\n{'=' * 80}")
        print(f"表名: {table_name}")
        print(f"数据库: {database}")
        print(f"服务器: {settings.sqlserver_host}")
        print(f"{'=' * 80}\n")

        conn = pyodbc.connect(conn_str, timeout=30)
        cursor = conn.cursor()

        # 1. 查看表结构
        print("【表结构】")
        print("-" * 80)
        sql_columns = """
            SELECT
                COLUMN_NAME,
                DATA_TYPE,
                CHARACTER_MAXIMUM_LENGTH,
                IS_NULLABLE,
                COLUMN_DEFAULT
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION
        """
        cursor.execute(sql_columns, (table_name,))
        columns = cursor.fetchall()

        for col in columns:
            col_name = col[0]
            data_type = col[1]
            max_len = col[2]
            nullable = col[3]
            default = col[4]

            len_str = f"({max_len})" if max_len else ""
            null_str = "NULL" if nullable == "YES" else "NOT NULL"
            default_str = f" DEFAULT {default}" if default else ""

            print(f"  {col_name:<30} {data_type}{len_str:<15} {null_str:<10}{default_str}")

        print(f"\n总字段数: {len(columns)}\n")

        # 2. 查看记录数
        print("【数据统计】")
        print("-" * 80)
        sql_count = f"SELECT COUNT(*) FROM {table_name}"
        cursor.execute(sql_count)
        count = cursor.fetchone()[0]
        print(f"  总记录数: {count:,}\n")

        # 3. 查看样例数据（前5条）
        print("【样例数据（前5条）】")
        print("-" * 80)
        sql_sample = f"SELECT TOP 5 * FROM {table_name}"
        cursor.execute(sql_sample)
        rows = cursor.fetchall()

        if rows:
            # 获取列名
            col_names = [desc[0] for desc in cursor.description]
            print(f"  字段: {', '.join(col_names[:10])}{'...' if len(col_names) > 10 else ''}\n")

            for i, row in enumerate(rows, 1):
                print(f"  记录 {i}:")
                for j, (col_name, value) in enumerate(zip(col_names, row)):
                    if j < 10:  # 只显示前10个字段
                        # 格式化值
                        if value is None:
                            value_str = "NULL"
                        elif hasattr(value, 'strftime'):
                            value_str = value.strftime('%Y-%m-%d %H:%M:%S')
                        elif isinstance(value, str) and len(value) > 50:
                            value_str = value[:50] + "..."
                        else:
                            value_str = str(value)

                        print(f"    {col_name:<30} {value_str}")
                if len(col_names) > 10:
                    print(f"    ... (还有 {len(col_names) - 10} 个字段)")
                print()
        else:
            print("  表中暂无数据\n")

        # 4. 查看数据范围（如果有时间字段）
        print("【数据范围】")
        print("-" * 80)

        # 尝试查找时间字段
        date_columns = []
        for col in columns:
            col_name = col[0]
            data_type = col[1]
            if data_type in ('datetime', 'datetime2', 'date', 'timestamp'):
                date_columns.append(col_name)

        if date_columns:
            for date_col in date_columns[:3]:  # 只检查前3个时间字段
                sql_min_max = f"SELECT MIN({date_col}), MAX({date_col}) FROM {table_name} WHERE {date_col} IS NOT NULL"
                cursor.execute(sql_min_max)
                min_val, max_val = cursor.fetchone()

                if min_val and max_val:
                    if hasattr(min_val, 'strftime'):
                        min_str = min_val.strftime('%Y-%m-%d %H:%M:%S')
                        max_str = max_val.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        min_str = str(min_val)
                        max_str = str(max_val)
                    print(f"  {date_col}: {min_str} ~ {max_str}")
        else:
            print("  未找到时间字段")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"查询失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    describe_table("Air_5m_2026_1001A_Src", "air_quality_db")
