"""
修复旧标准表的修约格式

将旧标准表的浓度字段修改为符合修约规则的数据类型：
- SO2/NO2/PM10/PM2.5/O3_8h: int (取整)
- CO: decimal(4,1) (保留1位小数)

用法:
    cd backend
    python migrations/execute_fix_old_standard_rounding.py
"""

import sys
import os
from pathlib import Path

# 添加 backend 目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

import pyodbc
import structlog

# 配置日志
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ],
    logger_factory=structlog.PrintLoggerFactory()
)

logger = structlog.get_logger()


def get_connection_string():
    """获取数据库连接字符串"""
    try:
        from config.settings import Settings
        settings = Settings()
        return settings.sqlserver_connection_string
    except Exception as e:
        logger.error("获取数据库配置失败", error=str(e))
        raise


def execute_sql_file(conn, sql_file_path):
    """执行 SQL 文件"""
    with open(sql_file_path, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    # 按 GO 分割 SQL 语句
    sql_batches = []
    current_batch = []

    for line in sql_content.split('\n'):
        stripped_line = line.strip()
        if stripped_line.upper() == 'GO':
            if current_batch:
                sql_batches.append('\n'.join(current_batch))
                current_batch = []
        else:
            current_batch.append(line)

    if current_batch:
        sql_batches.append('\n'.join(current_batch))

    # 执行每个批次
    cursor = conn.cursor()
    for i, batch in enumerate(sql_batches, 1):
        if batch.strip():
            try:
                cursor.execute(batch)
                conn.commit()
            except Exception as e:
                logger.error("sql_batch_failed", batch_index=i, error=str(e))
                raise

    cursor.close()


def verify_fix(conn):
    """验证修复结果"""
    cursor = conn.cursor()

    print("\n" + "=" * 100)
    print("验证修复结果")
    print("=" * 100)

    # 检查城市旧标准表
    print("\n【城市旧标准表】字段类型:")
    print("-" * 100)
    cursor.execute("""
        SELECT
            COLUMN_NAME,
            DATA_TYPE,
            NUMERIC_PRECISION,
            NUMERIC_SCALE,
            IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'city_168_statistics_old_standard'
          AND COLUMN_NAME IN ('so2_concentration', 'no2_concentration', 'pm10_concentration',
                              'pm2_5_concentration', 'co_concentration', 'o3_8h_concentration')
        ORDER BY ORDINAL_POSITION
    """)

    headers = ['字段名', '数据类型', '精度', '小数位数', '可空']
    print(f"{headers[0]:<25} {headers[1]:<15} {headers[2]:<10} {headers[3]:<10} {headers[4]:<10}")
    for row in cursor.fetchall():
        print(f"{row[0]:<25} {row[1]:<15} {str(row[2]):<10} {str(row[3]):<10} {row[4]:<10}")

    # 检查示例数据
    print("\n【城市旧标准表】示例数据（前3条）:")
    print("-" * 100)
    cursor.execute("""
        SELECT TOP 3
            city_name,
            so2_concentration,
            no2_concentration,
            pm10_concentration,
            pm2_5_concentration,
            co_concentration,
            o3_8h_concentration,
            stat_date
        FROM city_168_statistics_old_standard
        WHERE stat_date LIKE '2025%'
        ORDER BY stat_date DESC, city_name
    """)

    for row in cursor.fetchall():
        print(f"城市: {row[0]:<10} SO2: {str(row[1]):<6} NO2: {str(row[2]):<6} "
              f"PM10: {str(row[3]):<6} PM2.5: {str(row[4]):<6} CO: {str(row[5]):<6} "
              f"O3_8h: {str(row[6]):<6} 日期: {row[7]}")

    # 检查省级旧标准表
    print("\n【省级旧标准表】字段类型:")
    print("-" * 100)
    cursor.execute("""
        SELECT
            COLUMN_NAME,
            DATA_TYPE,
            NUMERIC_PRECISION,
            NUMERIC_SCALE,
            IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'province_statistics_old_standard'
          AND COLUMN_NAME IN ('so2_concentration', 'no2_concentration', 'pm10_concentration',
                              'pm2_5_concentration', 'co_concentration', 'o3_8h_concentration')
        ORDER BY ORDINAL_POSITION
    """)

    print(f"{headers[0]:<25} {headers[1]:<15} {headers[2]:<10} {headers[3]:<10} {headers[4]:<10}")
    for row in cursor.fetchall():
        print(f"{row[0]:<25} {row[1]:<15} {str(row[2]):<10} {str(row[3]):<10} {row[4]:<10}")

    print("\n【省级旧标准表】示例数据（前3条）:")
    print("-" * 100)
    cursor.execute("""
        SELECT TOP 3
            province_name,
            so2_concentration,
            no2_concentration,
            pm10_concentration,
            pm2_5_concentration,
            co_concentration,
            o3_8h_concentration,
            stat_date
        FROM province_statistics_old_standard
        WHERE stat_date LIKE '2025%'
        ORDER BY stat_date DESC, province_name
    """)

    for row in cursor.fetchall():
        print(f"省份: {row[0]:<10} SO2: {str(row[1]):<6} NO2: {str(row[2]):<6} "
              f"PM10: {str(row[3]):<6} PM2.5: {str(row[4]):<6} CO: {str(row[5]):<6} "
              f"O3_8h: {str(row[6]):<6} 日期: {row[7]}")

    cursor.close()


def main():
    """主函数"""
    logger.info("migration_started", migration="fix_old_standard_rounding")

    try:
        # 获取 SQL 文件路径
        script_dir = Path(__file__).parent
        sql_file = script_dir / "fix_old_standard_rounding.sql"

        if not sql_file.exists():
            print(f"❌ SQL 文件不存在: {sql_file}")
            return 1

        print("=" * 100)
        print("修复旧标准表的修约格式")
        print("=" * 100)
        print(f"\nSQL 文件: {sql_file}")
        print("\n说明:")
        print("  - 将 SO2/NO2/PM10/PM2.5/O3_8h 字段类型从 decimal(10,1) 改为 int")
        print("  - 将 CO 字段类型从 decimal(10,2) 改为 decimal(4,1)")
        print("  - 修约现有数据")

        # 确认执行
        print("\n" + "=" * 100)
        choice = input("是否继续执行？(y/N): ")
        if choice.lower() != 'y':
            print("❌ 迁移取消")
            return 1

        # 连接数据库
        print("\n连接数据库...")
        conn_str = get_connection_string()
        conn = pyodbc.connect(conn_str, timeout=30)
        print("✅ 数据库连接成功")

        # 执行 SQL 文件
        print("\n执行 SQL 迁移脚本...")
        execute_sql_file(conn, sql_file)
        print("✅ SQL 执行完成")

        # 验证结果
        verify_fix(conn)

        conn.close()

        print("\n" + "=" * 100)
        print("✅ 迁移完成！")
        print("=" * 100)
        print("\n下一步: 更新 fetcher 代码")
        print("  1. app/fetchers/city_statistics/city_statistics_old_standard_fetcher.py")
        print("  2. app/fetchers/city_statistics/province_statistics_old_standard_fetcher.py")

        logger.info("migration_completed", migration="fix_old_standard_rounding")
        return 0

    except Exception as e:
        logger.error("migration_failed", error=str(e), exc_info=True)
        print(f"\n❌ 迁移失败: {str(e)}")
        return 1


if __name__ == "__main__":
    exit(main())
