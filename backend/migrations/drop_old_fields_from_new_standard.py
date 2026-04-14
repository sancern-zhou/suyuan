"""
从新标准表中删除旧标准对比字段
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
    logger.info("drop_old_fields_started", database=DATABASE)

    try:
        print("连接数据库...")
        conn = get_connection()
        cursor = conn.cursor()
        print("✅ 数据库连接成功")

        # 要删除的字段
        fields_to_drop = [
            'comprehensive_index_old',
            'comprehensive_index_rank_old',
            'pm10_index_old',
            'pm2_5_index_old',
        ]

        print("\n删除旧标准对比字段...")
        for field in fields_to_drop:
            try:
                sql = f"ALTER TABLE city_168_statistics_new_standard DROP COLUMN {field}"
                print(f"  执行: {sql}")
                cursor.execute(sql)
                conn.commit()
                print(f"  ✅ 删除 {field} 成功")
            except Exception as e:
                print(f"  ❌ 删除 {field} 失败: {str(e)}")

        # 验证结果
        print("\n验证结果...")
        cursor.execute("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'city_168_statistics_new_standard'
            AND COLUMN_NAME IN ('comprehensive_index_old', 'comprehensive_index_rank_old',
                               'pm10_index_old', 'pm2_5_index_old')
            ORDER BY COLUMN_NAME
        """)
        remaining = cursor.fetchall()
        if remaining:
            print("⚠️ 仍有字段未删除:")
            for row in remaining:
                print(f"  - {row[0]}")
        else:
            print("✅ 所有旧标准字段已删除")

        # 显示最终表结构
        print("\n最终表结构（关键字段）:")
        cursor.execute("""
            SELECT COLUMN_NAME, DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'city_168_statistics_new_standard'
            AND COLUMN_NAME IN ('comprehensive_index', 'comprehensive_index_rank',
                               'comprehensive_index_new_limit_old_algo')
            ORDER BY COLUMN_NAME
        """)
        for row in cursor.fetchall():
            print(f"  - {row[0]}: {row[1]}")

        cursor.close()
        conn.close()

        print("\n✅ 字段删除完成！")

        logger.info("drop_old_fields_completed")

    except Exception as e:
        logger.error("drop_old_fields_failed", error=str(e), exc_info=True)
        print(f"\n❌ 失败: {str(e)}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
