"""
删除并重建统计表（使用新的年月格式）

功能：
1. 删除现有表
2. 创建新表（stat_date使用VARCHAR(7)）
3. 重新创建索引

新的表结构：
- stat_date: VARCHAR(7)  -- 格式：2026-01（月度），2026（年度）
- stat_type: monthly | current_month | annual_ytd
"""
import sys
import pyodbc

sys.path.insert(0, '/home/xckj/suyuan/backend')

from app.fetchers.city_statistics.province_statistics_fetcher import ProvinceSQLServerClient


def drop_and_recreate_tables():
    """删除并重建统计表"""

    print("="*80)
    print("删除并重建统计表（使用新的年月格式）")
    print("="*80)

    sql_client = ProvinceSQLServerClient()
    conn = pyodbc.connect(sql_client.connection_string, timeout=30)
    cursor = conn.cursor()

    try:
        # ====================================================================
        # 步骤1：删除省级统计表
        # ====================================================================
        print("\n步骤1：删除省级统计表...")

        # 检查表是否存在
        cursor.execute("""
            SELECT COUNT(*) FROM sys.tables
            WHERE name = 'province_statistics_new_standard'
        """)
        if cursor.fetchone()[0] > 0:
            cursor.execute("DROP TABLE province_statistics_new_standard")
            print("  ✓ 已删除表：province_statistics_new_standard")
        else:
            print("  - 表不存在，跳过")

        # ====================================================================
        # 步骤2：删除城市统计表
        # ====================================================================
        print("\n步骤2：删除城市统计表...")

        cursor.execute("""
            SELECT COUNT(*) FROM sys.tables
            WHERE name = 'city_168_statistics_new_standard'
        """)
        if cursor.fetchone()[0] > 0:
            cursor.execute("DROP TABLE city_168_statistics_new_standard")
            print("  ✓ 已删除表：city_168_statistics_new_standard")
        else:
            print("  - 表不存在，跳过")

        # ====================================================================
        # 步骤3：创建省级统计表
        # ====================================================================
        print("\n步骤3：创建省级统计表...")

        create_province_sql = """
        CREATE TABLE province_statistics_new_standard (
            id INT IDENTITY(1,1) PRIMARY KEY,
            stat_date VARCHAR(7) NOT NULL,  -- 格式：2026-01（月度），2026（年度）
            stat_type VARCHAR(20) NOT NULL,  -- monthly | current_month | annual_ytd
            province_name NVARCHAR(50) NOT NULL,

            -- 浓度值（保留2位小数，中间计算精度）
            so2_concentration DECIMAL(5,2),
            no2_concentration DECIMAL(5,2),
            pm10_concentration DECIMAL(5,2),
            pm2_5_concentration DECIMAL(5,2),
            co_concentration DECIMAL(6,3),  -- CO保留3位小数
            o3_8h_concentration DECIMAL(5,2),

            -- 单项指数（保留3位小数）
            so2_index DECIMAL(6,3),
            no2_index DECIMAL(6,3),
            pm10_index DECIMAL(6,3),
            pm2_5_index DECIMAL(6,3),
            co_index DECIMAL(6,3),
            o3_8h_index DECIMAL(6,3),

            -- 综合指数
            comprehensive_index DECIMAL(6,3),
            comprehensive_index_rank INT,

            -- 新限值+旧算法
            comprehensive_index_new_limit_old_algo DECIMAL(6,3),
            comprehensive_index_rank_new_limit_old_algo INT,

            -- 元数据
            standard_version NVARCHAR(20),
            data_days INT,
            sample_coverage DECIMAL(5,2),
            city_count INT,
            city_names NVARCHAR(MAX),

            -- 时间戳
            created_at DATETIME DEFAULT GETDATE(),
            updated_at DATETIME DEFAULT GETDATE()
        )
        """

        cursor.execute(create_province_sql)
        print("  ✓ 已创建表：province_statistics_new_standard")

        # ====================================================================
        # 步骤4：创建城市统计表
        # ====================================================================
        print("\n步骤4：创建城市统计表...")

        create_city_sql = """
        CREATE TABLE city_168_statistics_new_standard (
            id INT IDENTITY(1,1) PRIMARY KEY,
            stat_date VARCHAR(7) NOT NULL,  -- 格式：2026-01（月度），2026（年度）
            stat_type VARCHAR(20) NOT NULL,  -- monthly | current_month | annual_ytd
            city_name NVARCHAR(50) NOT NULL,
            city_code INT,

            -- 浓度值（保留2位小数，中间计算精度）
            so2_concentration DECIMAL(5,2),
            no2_concentration DECIMAL(5,2),
            pm10_concentration DECIMAL(5,2),
            pm2_5_concentration DECIMAL(5,2),
            co_concentration DECIMAL(6,3),  -- CO保留3位小数
            o3_8h_concentration DECIMAL(5,2),

            -- 单项指数（保留3位小数）
            so2_index DECIMAL(6,3),
            no2_index DECIMAL(6,3),
            pm10_index DECIMAL(6,3),
            pm2_5_index DECIMAL(6,3),
            co_index DECIMAL(6,3),
            o3_8h_index DECIMAL(6,3),

            -- 综合指数
            comprehensive_index DECIMAL(6,3),
            comprehensive_index_rank INT,

            -- 新限值+旧算法
            comprehensive_index_new_limit_old_algo DECIMAL(6,3),
            comprehensive_index_rank_new_limit_old_algo INT,

            -- 元数据
            standard_version NVARCHAR(20),
            data_days INT,
            sample_coverage DECIMAL(5,2),
            region NVARCHAR(50),
            province NVARCHAR(50),

            -- 时间戳
            created_at DATETIME DEFAULT GETDATE(),
            updated_at DATETIME DEFAULT GETDATE()
        )
        """

        cursor.execute(create_city_sql)
        print("  ✓ 已创建表：city_168_statistics_new_standard")

        # ====================================================================
        # 步骤5：创建索引
        # ====================================================================
        print("\n步骤5：创建索引...")

        # 省级统计表索引
        province_indexes = [
            ("idx_province_date_type", "province_statistics_new_standard", "stat_date, stat_type"),
            ("idx_province_type", "province_statistics_new_standard", "stat_type"),
            ("idx_province_name", "province_statistics_new_standard", "province_name"),
            ("idx_province_rank", "province_statistics_new_standard", "comprehensive_index_rank"),
            ("idx_province_unique", "province_statistics_new_standard", "stat_date, stat_type, province_name", True)
        ]

        for idx_name, table_name, columns, *unique in province_indexes:
            is_unique = unique[0] if unique else False
            unique_sql = "UNIQUE " if is_unique else ""
            try:
                cursor.execute(f"CREATE {unique_sql}INDEX {idx_name} ON {table_name} ({columns})")
                print(f"  ✓ 已创建索引：{idx_name} ({table_name})")
            except pyodbc.Error as e:
                if "already exists" not in str(e):
                    print(f"  ✗ 创建索引失败：{idx_name} - {str(e)}")

        # 城市统计表索引
        city_indexes = [
            ("idx_city_168_date", "city_168_statistics_new_standard", "stat_date, stat_type"),
            ("idx_city_168_type", "city_168_statistics_new_standard", "stat_type"),
            ("idx_city_168_city", "city_168_statistics_new_standard", "city_name, city_code"),
            ("idx_city_168_rank", "city_168_statistics_new_standard", "comprehensive_index_rank"),
            ("idx_city_168_date_type", "city_168_statistics_new_standard", "stat_date, stat_type, city_name", True),
            ("idx_city_168_province", "city_168_statistics_new_standard", "province")
        ]

        for idx_name, table_name, columns, *unique in city_indexes:
            is_unique = unique[0] if unique else False
            unique_sql = "UNIQUE " if is_unique else ""
            try:
                cursor.execute(f"CREATE {unique_sql}INDEX {idx_name} ON {table_name} ({columns})")
                print(f"  ✓ 已创建索引：{idx_name} ({table_name})")
            except pyodbc.Error as e:
                if "already exists" not in str(e):
                    print(f"  ✗ 创建索引失败：{idx_name} - {str(e)}")

        conn.commit()

        print("\n" + "="*80)
        print("✓ 表重建完成！")
        print("="*80)
        print("\n新表结构：")
        print("  - stat_date: VARCHAR(7)")
        print("  - 日期格式：")
        print("    • monthly: '2026-01'（年-月，表示全月数据）")
        print("    • current_month: '2026-04'（年-月，表示当月累计）")
        print("    • annual_ytd: '2026'（年，表示年初至今）")
        print("\n中间计算精度：")
        print("  • SO2, NO2, PM10, PM2.5, O3-8h: 保留2位小数")
        print("  • CO: 保留3位小数")

    except Exception as e:
        conn.rollback()
        print(f"\n✗ 执行失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    drop_and_recreate_tables()
