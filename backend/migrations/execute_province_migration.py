#!/usr/bin/env python3
"""
执行省级统计表数据库迁移脚本
"""
import pyodbc

# 数据库连接配置
server = "180.184.30.94,1433"
database = "XcAiDb"
username = "sa"
password = "#Ph981,6J2bOkWYT7p?5slH$I~g_0itR"

# 构建连接字符串
connection_string = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={server};"
    f"DATABASE={database};"
    f"UID={username};"
    f"PWD={{{password}}};"
    f"TrustServerCertificate=yes;"
)

def execute_migration():
    """执行迁移脚本"""
    print("连接数据库...")
    conn = pyodbc.connect(connection_string, timeout=30)
    cursor = conn.cursor()

    try:
        print("\n" + "="*60)
        print("开始省级统计表迁移")
        print("="*60)

        # 1. 检查表是否存在
        cursor.execute("SELECT name FROM sys.tables WHERE name IN ('province_statistics', 'province_statistics_new_standard')")
        existing_tables = [row[0] for row in cursor.fetchall()]
        print(f"\n当前存在的表: {existing_tables}")

        # 2. 重命名表（如果需要）
        if 'province_statistics' in existing_tables and 'province_statistics_new_standard' not in existing_tables:
            print("\n重命名表: province_statistics -> province_statistics_new_standard")
            cursor.execute("EXEC sp_rename 'province_statistics', 'province_statistics_new_standard'")
            conn.commit()
            print("✓ 表重命名成功")
        elif 'province_statistics_new_standard' in existing_tables:
            print("\n✓ 表 province_statistics_new_standard 已存在，跳过重命名")
        else:
            print("\n⚠ 警告: 未找到 province_statistics 表")

        # 3. 删除旧标准相关索引（必须先删除索引才能删除字段）
        old_indexes = [
            'idx_province_rank_old',
            'idx_province_rank_old_limit_new_algo',
            'idx_province_rank_new_limit_old_algo'
        ]

        print("\n删除旧标准相关索引...")
        for index in old_indexes:
            cursor.execute(f"""
                SELECT * FROM sys.indexes
                WHERE name = '{index}'
                AND object_id = OBJECT_ID('province_statistics_new_standard')
            """)
            if cursor.fetchone():
                cursor.execute(f"DROP INDEX {index} ON province_statistics_new_standard")
                print(f"  ✓ 已删除索引: {index}")
            else:
                print(f"  - 索引不存在: {index}")
        conn.commit()

        # 4. 删除新标准表中的旧标准字段
        old_standard_columns = [
            'pm10_index_old',
            'pm2_5_index_old',
            'comprehensive_index_old',
            'comprehensive_index_rank_old',
            'comprehensive_index_old_limit_new_algo',
            'comprehensive_index_rank_old_limit_new_algo'
        ]

        print("\n删除新标准表中的旧标准字段...")
        for column in old_standard_columns:
            cursor.execute(f"""
                SELECT * FROM sys.columns
                WHERE object_id = OBJECT_ID('province_statistics_new_standard')
                AND name = '{column}'
            """)
            if cursor.fetchone():
                cursor.execute(f"ALTER TABLE province_statistics_new_standard DROP COLUMN {column}")
                print(f"  ✓ 已删除字段: {column}")
            else:
                print(f"  - 字段不存在: {column}")
        conn.commit()

        # 5. 创建旧标准表
        print("\n创建旧标准表 province_statistics_old_standard...")
        cursor.execute("SELECT * FROM sys.tables WHERE name = 'province_statistics_old_standard'")
        if not cursor.fetchone():
            create_table_sql = """
            CREATE TABLE province_statistics_old_standard (
                id INT IDENTITY(1,1) PRIMARY KEY,
                stat_date DATE NOT NULL,
                stat_type NVARCHAR(20) NOT NULL,
                province_name NVARCHAR(50) NOT NULL,

                -- 污染物浓度（按final_output规则修约）
                so2_concentration DECIMAL(10, 0),
                no2_concentration DECIMAL(10, 0),
                pm10_concentration DECIMAL(10, 0),
                pm2_5_concentration DECIMAL(10, 1),
                co_concentration DECIMAL(10, 1),
                o3_8h_concentration DECIMAL(10, 0),

                -- 单项指数（使用旧限值计算）
                so2_index DECIMAL(10, 3),
                no2_index DECIMAL(10, 3),
                pm10_index DECIMAL(10, 3),
                pm2_5_index DECIMAL(10, 3),
                co_index DECIMAL(10, 3),
                o3_8h_index DECIMAL(10, 3),

                -- 综合指数（旧限值+新算法）
                comprehensive_index_new_algo DECIMAL(10, 3),
                comprehensive_index_rank_new_algo INT,

                -- 综合指数（旧限值+旧算法）
                comprehensive_index_old_algo DECIMAL(10, 3),
                comprehensive_index_rank_old_algo INT,

                -- 元数据
                data_days INT,
                sample_coverage DECIMAL(10, 2),
                city_count INT,
                city_names NVARCHAR(500),

                -- 时间戳
                created_at DATETIME DEFAULT GETDATE(),
                updated_at DATETIME DEFAULT GETDATE(),

                -- 约束
                CONSTRAINT IX_province_statistics_old_standard UNIQUE (stat_date, stat_type, province_name)
            )
            """
            cursor.execute(create_table_sql)
            conn.commit()
            print("✓ 旧标准表创建成功")
        else:
            print("✓ 旧标准表已存在")

        # 6. 创建索引
        print("\n创建旧标准表索引...")

        indexes = [
            ('idx_province_old_standard_rank_new_algo', 'comprehensive_index_rank_new_algo'),
            ('idx_province_old_standard_rank_old_algo', 'comprehensive_index_rank_old_algo'),
            ('idx_province_old_standard_date_type', 'stat_date, stat_type')
        ]

        for index_name, columns in indexes:
            cursor.execute(f"""
                SELECT * FROM sys.indexes
                WHERE name = '{index_name}'
                AND object_id = OBJECT_ID('province_statistics_old_standard')
            """)
            if not cursor.fetchone():
                cursor.execute(f"CREATE INDEX {index_name} ON province_statistics_old_standard({columns})")
                print(f"  ✓ 创建索引: {index_name}")
            else:
                print(f"  - 索引已存在: {index_name}")
        conn.commit()

        # 7. 验证表结构
        print("\n验证表结构...")
        cursor.execute("""
            SELECT
                t.name as table_name,
                COUNT(c.name) as column_count
            FROM sys.tables t
            INNER JOIN sys.columns c ON t.object_id = c.object_id
            WHERE t.name IN ('province_statistics_new_standard', 'province_statistics_old_standard')
            GROUP BY t.name
            ORDER BY t.name
        """)
        print("\n表结构验证:")
        for row in cursor.fetchall():
            print(f"  {row.table_name}: {row.column_count} 个字段")

        print("\n" + "="*60)
        print("✓ 迁移完成！")
        print("="*60)
        print("\n新标准表: province_statistics_new_standard")
        print("旧标准表: province_statistics_old_standard")
        print("="*60)

    except Exception as e:
        print(f"\n✗ 迁移失败: {str(e)}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
        print("\n数据库连接已关闭")

if __name__ == '__main__':
    execute_migration()
