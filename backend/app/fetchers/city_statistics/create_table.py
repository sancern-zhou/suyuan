"""
创建city_168_statistics表的Python脚本

使用pyodbc直接执行SQL创建表和索引
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.fetchers.city_statistics.city_statistics_fetcher import SQLServerClient
import structlog

logger = structlog.get_logger()


def create_table():
    """创建数据库表和索引"""
    print("="*60)
    print("创建city_168_statistics表")
    print("="*60)

    client = SQLServerClient()

    # 测试连接
    print("\n1. 测试数据库连接...")
    if not client.test_connection():
        print("✗ 数据库连接失败")
        return False
    print("✓ 数据库连接成功")

    # 检查表是否已存在
    print("\n2. 检查表是否已存在...")
    try:
        import pyodbc

        conn = pyodbc.connect(client.connection_string, timeout=10)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'city_168_statistics'
        """)
        table_exists = cursor.fetchone()[0] > 0

        if table_exists:
            print("  ⊙ 表 'city_168_statistics' 已存在")

            # 询问是否删除重建
            response = input("  是否删除并重建表？(y/N): ").strip().lower()
            if response == 'y':
                print("  删除旧表...")
                cursor.execute("DROP TABLE city_168_statistics")
                conn.commit()
                print("  ✓ 旧表已删除")
            else:
                print("  保留现有表，退出")
                cursor.close()
                conn.close()
                return True

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"  ✗ 检查表失败: {str(e)}")
        return False

    # 创建表
    print("\n3. 创建表...")
    try:
        conn = pyodbc.connect(client.connection_string, timeout=30)
        cursor = conn.cursor()

        # 创建表
        create_table_sql = """
        CREATE TABLE city_168_statistics (
            id INT IDENTITY(1,1) PRIMARY KEY,
            stat_date DATE NOT NULL,
            stat_type NVARCHAR(20) NOT NULL,
            city_name NVARCHAR(50) NOT NULL,
            city_code INT,

            -- 六项污染物浓度
            so2_concentration DECIMAL(10,1),
            no2_concentration DECIMAL(10,1),
            pm10_concentration DECIMAL(10,1),
            pm2_5_concentration DECIMAL(10,1),
            co_concentration DECIMAL(10,2),
            o3_8h_concentration DECIMAL(10,1),

            -- 单项指数
            so2_index DECIMAL(10,3),
            no2_index DECIMAL(10,3),
            pm10_index DECIMAL(10,3),
            pm2_5_index DECIMAL(10,3),
            co_index DECIMAL(10,3),
            o3_8h_index DECIMAL(10,3),

            -- 综合指数
            comprehensive_index DECIMAL(10,3),
            comprehensive_index_rank INT,

            -- 元数据
            data_days INT,
            sample_coverage DECIMAL(5,2),
            region NVARCHAR(50),
            province NVARCHAR(50),

            -- 时间戳
            created_at DATETIME DEFAULT GETDATE(),
            updated_at DATETIME DEFAULT GETDATE()
        )
        """
        cursor.execute(create_table_sql)
        conn.commit()
        print("  ✓ 表创建成功")

        # 创建索引
        print("\n4. 创建索引...")
        indexes = [
            ("idx_city_168_date", "CREATE INDEX idx_city_168_date ON city_168_statistics(stat_date)"),
            ("idx_city_168_type", "CREATE INDEX idx_city_168_type ON city_168_statistics(stat_type)"),
            ("idx_city_168_city", "CREATE INDEX idx_city_168_city ON city_168_statistics(city_name)"),
            ("idx_city_168_rank", "CREATE INDEX idx_city_168_rank ON city_168_statistics(comprehensive_index_rank)"),
            ("idx_city_168_date_type", "CREATE INDEX idx_city_168_date_type ON city_168_statistics(stat_date, stat_type)"),
        ]

        for idx_name, idx_sql in indexes:
            try:
                cursor.execute(idx_sql)
                conn.commit()
                print(f"  ✓ 索引 '{idx_name}' 创建成功")
            except Exception as e:
                print(f"  ✗ 索引 '{idx_name}' 创建失败: {str(e)}")

        cursor.close()
        conn.close()

        print("\n" + "="*60)
        print("✓ 数据库表创建成功！")
        print("="*60)

        return True

    except Exception as e:
        print(f"\n✗ 创建表失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = create_table()
    sys.exit(0 if success else 1)
