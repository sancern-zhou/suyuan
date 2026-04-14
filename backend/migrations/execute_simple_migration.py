"""
168城市统计表迁移 - 简化方案

方案：
1. 将 city_168_statistics 重命名为 city_168_statistics_new_standard
2. 保留现有的 city_168_statistics_old_standard 表
3. 删除新标准表中的旧标准对比字段（可选）

用法:
    cd backend
    python migrations/execute_simple_migration.py
"""
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

# SQL Server 连接配置
SERVER = "180.184.30.94,1433"
DATABASE = "XcAiDb"
USER = "sa"
PASSWORD = r"#Ph981,6J2bOkWYT7p?5slH$I~g_0itR"


def get_connection():
    """获取数据库连接"""
    connection_string = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        f"UID={USER};"
        f"PWD={PASSWORD};"
        f"TrustServerCertificate=yes;"
    )
    return pyodbc.connect(connection_string)


def main():
    """主函数"""
    logger.info("migration_started", database=DATABASE)

    try:
        # 连接数据库
        print("连接数据库...")
        conn = get_connection()
        cursor = conn.cursor()
        print("✅ 数据库连接成功")

        # 检查表是否已存在
        print("\n检查表是否存在...")
        cursor.execute("""
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = 'city_168_statistics_new_standard'
        """)
        if cursor.fetchone():
            print("⚠️ city_168_statistics_new_standard 表已存在")
            choice = input("是否删除并重建？(y/N): ")
            if choice.lower() == 'y':
                cursor.execute("DROP TABLE city_168_statistics_new_standard")
                conn.commit()
                print("✅ 已删除现有表")
            else:
                print("❌ 迁移取消")
                return 1

        # 检查源表数据
        print("\n检查源表数据...")
        cursor.execute("""
            SELECT COUNT(*) as cnt,
                   MIN(stat_date) as min_date,
                   MAX(stat_date) as max_date
            FROM city_168_statistics
        """)
        row = cursor.fetchone()
        print(f"city_168_statistics 数据量: {row[0]} 条")
        print(f"日期范围: {row[1]} ~ {row[2]}")

        # 检查 standard_version
        cursor.execute("""
            SELECT standard_version, COUNT(*) as cnt
            FROM city_168_statistics
            GROUP BY standard_version
        """)
        print("\nstandard_version 分布:")
        for ver_row in cursor.fetchall():
            print(f"  - {ver_row[0]}: {ver_row[1]} 条")

        # 重命名表
        print("\n执行表重命名...")
        print("  city_168_statistics -> city_168_statistics_new_standard")
        cursor.execute("sp_rename 'city_168_statistics', 'city_168_statistics_new_standard'")
        conn.commit()
        print("✅ 表重命名成功")

        # 验证新表
        print("\n验证新表...")
        cursor.execute("SELECT COUNT(*) FROM city_168_statistics_new_standard")
        new_count = cursor.fetchone()[0]
        print(f"city_168_statistics_new_standard 数据量: {new_count} 条")

        # 检查旧标准表
        cursor.execute("SELECT COUNT(*) FROM city_168_statistics_old_standard")
        old_count = cursor.fetchone()[0]
        print(f"city_168_statistics_old_standard 数据量: {old_count} 条")

        # 显示最新数据
        print("\n新标准表最新数据（前3条）:")
        print("-" * 100)
        cursor.execute("""
            SELECT TOP 3 stat_date, stat_type, city_name,
                   comprehensive_index, comprehensive_index_rank,
                   standard_version
            FROM city_168_statistics_new_standard
            ORDER BY stat_date DESC, city_name
        """)
        for row in cursor.fetchall():
            print(f"日期: {row[0]}, 类型: {row[1]}, 城市: {row[2]}, "
                  f"综合指数: {row[3]}, 排名: {row[4]}, 标准: {row[5]}")

        cursor.close()
        conn.close()

        print("\n" + "=" * 100)
        print("✅ 迁移完成！")
        print("=" * 100)
        print("\n当前表结构:")
        print("  - city_168_statistics_new_standard (新标准 HJ 633-2026)")
        print("  - city_168_statistics_old_standard (旧标准 HJ 633-2013)")
        print("\n下一步: 更新代码中的表名引用")

        logger.info("migration_completed",
                    new_count=new_count,
                    old_count=old_count)

    except Exception as e:
        logger.error("migration_failed", error=str(e), exc_info=True)
        print(f"\n❌ 迁移失败: {str(e)}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
