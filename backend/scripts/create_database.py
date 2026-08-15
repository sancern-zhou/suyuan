"""
创建 weather_db 数据库

使用 psycopg2 同步客户端创建数据库（因为 asyncpg 不能创建数据库）
"""
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import sys

# 数据库连接信息
DB_HOST = "180.184.30.94"
DB_PORT = 5432
DB_USER = "postgres"
DB_PASSWORD = "Xc13129092470"
DB_NAME = "weather_db"

def create_database():
    """创建 weather_db 数据库"""
    print("=" * 60)
    print("创建 weather_db 数据库")
    print("=" * 60)

    try:
        # 连接到 postgres 默认数据库
        print(f"连接到 PostgreSQL 服务器: {DB_HOST}:{DB_PORT}")
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database="postgres"
        )

        # 设置自动提交模式（创建数据库需要）
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        # 检查数据库是否已存在
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (DB_NAME,)
        )
        exists = cursor.fetchone()

        if exists:
            print(f"[OK] 数据库 '{DB_NAME}' 已存在")
        else:
            # 创建数据库
            print(f"创建数据库 '{DB_NAME}'...")
            cursor.execute(f'CREATE DATABASE {DB_NAME} OWNER {DB_USER}')
            print(f"[OK] 数据库 '{DB_NAME}' 创建成功")

        cursor.close()
        conn.close()

        # 连接到新数据库并安装 TimescaleDB
        print(f"\n连接到数据库 '{DB_NAME}'...")
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        # 检查 TimescaleDB 扩展
        cursor.execute(
            "SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'"
        )
        has_timescaledb = cursor.fetchone()

        if has_timescaledb:
            print("[OK] TimescaleDB 扩展已安装")
            cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'")
            version = cursor.fetchone()[0]
            print(f"   版本: {version}")
        else:
            print("尝试安装 TimescaleDB 扩展...")
            try:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
                print("[OK] TimescaleDB 扩展安装成功")
            except Exception as e:
                print(f"[WARN] TimescaleDB 扩展未安装: {e}")
                print("   数据库仍可正常使用，但没有时序优化")

        cursor.close()
        conn.close()

        print("\n" + "=" * 60)
        print("数据库准备完成！")
        print("=" * 60)
        print(f"\n数据库连接信息:")
        print(f"  主机: {DB_HOST}")
        print(f"  端口: {DB_PORT}")
        print(f"  数据库: {DB_NAME}")
        print(f"  用户: {DB_USER}")
        print(f"\n连接字符串:")
        print(f"  postgresql+asyncpg://{DB_USER}:****@{DB_HOST}:{DB_PORT}/{DB_NAME}")
        print("\n下一步:")
        print("  1. 运行: python scripts/init_database.py")
        print("  2. 运行: python scripts/test_database.py")
        print("=" * 60)

        return True

    except psycopg2.Error as e:
        print(f"\n[ERROR] 数据库操作失败: {e}")
        print(f"\n错误详情: {e.pgerror if hasattr(e, 'pgerror') else str(e)}")
        return False
    except Exception as e:
        print(f"\n[ERROR] 未知错误: {e}")
        return False

if __name__ == "__main__":
    success = create_database()
    sys.exit(0 if success else 1)
