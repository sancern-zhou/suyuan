"""
168城市统计表迁移执行脚本

用法:
    cd backend
    python migrations/execute_migration.py
"""
import asyncio
import pyodbc
from datetime import datetime
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
PASSWORD = "#Ph981,6J2bOkWYT7p?5slH$I~g_0itR"


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


def execute_sql_file(conn, sql_file_path):
    """执行SQL文件"""
    with open(sql_file_path, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    # 分割SQL语句（按GO分割）
    statements = []
    current_statement = []

    for line in sql_content.split('\n'):
        line = line.strip()

        # 跳过注释和空行
        if not line or line.startswith('--'):
            current_statement.append(line)

        # 遇到GO时执行当前语句
        if line.upper() == 'GO':
            if current_statement:
                statement = '\n'.join(current_statement)
                statements.append(statement)
                current_statement = []

    # 添加最后一个语句
    if current_statement:
        statement = '\n'.join(current_statement)
        statements.append(statement)

    # 执行所有语句
    cursor = conn.cursor()
    for i, statement in enumerate(statements, 1):
        try:
            if statement.strip():
                print(f"执行语句 {i}/{len(statements)}...")
                cursor.execute(statement)
                conn.commit()
                print(f"✅ 语句 {i} 执行成功")
        except Exception as e:
            print(f"❌ 语句 {i} 执行失败: {str(e)}")
            # 继续执行其他语句

    cursor.close()


def main():
    """主函数"""
    logger.info("migration_started", database=DATABASE)

    try:
        # 连接数据库
        print("连接数据库...")
        conn = get_connection()
        print("✅ 数据库连接成功")

        # 执行迁移脚本
        sql_file = "migrations/migrate_168_statistics_to_new_standard.sql"
        print(f"\n执行迁移脚本: {sql_file}")
        execute_sql_file(conn, sql_file)

        # 验证数据
        print("\n验证数据...")
        cursor = conn.cursor()

        # 检查新标准表记录数
        cursor.execute("SELECT COUNT(*) as count FROM city_168_statistics_new_standard")
        new_count = cursor.fetchone()[0]
        print(f"新标准表记录数: {new_count}")

        # 检查旧标准表记录数
        cursor.execute("SELECT COUNT(*) as count FROM city_168_statistics_old_standard")
        old_count = cursor.fetchone()[0]
        print(f"旧标准表记录数: {old_count}")

        # 检查最新数据
        cursor.execute("""
            SELECT TOP 3 stat_date, stat_type, city_name,
                   comprehensive_index, comprehensive_index_rank, standard_version
            FROM city_168_statistics_new_standard
            ORDER BY stat_date DESC
        """)

        print("\n新标准表最新数据（前3条）:")
        print("-" * 100)
        for row in cursor.fetchall():
            print(f"日期: {row[0]}, 类型: {row[1]}, 城市: {row[2]}, "
                  f"综合指数: {row[3]}, 排名: {row[4]}, 标准: {row[5]}")

        cursor.close()
        conn.close()

        print("\n" + "=" * 100)
        print("✅ 迁移准备完成！")
        print("=" * 100)
        print("\n下一步操作:")
        print("1. 验证数据无误后，执行删除旧字段脚本:")
        print("   python migrations/drop_old_fields.py")
        print("\n2. 更新代码中的表名引用")
        print("\n⚠️ 注意: 删除旧字段前请先备份数据库！")

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
