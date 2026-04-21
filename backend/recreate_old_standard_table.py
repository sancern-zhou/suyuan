"""
重建旧标准省级统计表

python backend/recreate_old_standard_table.py
"""

import sys
sys.path.insert(0, '/home/xckj/suyuan/backend')

import pyodbc

# 连接数据库
connection_string = 'DRIVER={ODBC Driver 17 for SQL Server};SERVER=180.184.91.74,9003;DATABASE=XcAiDb;UID=sa;PWD=XcAiDb@2023'

print("="*80)
print("重建旧标准省级统计表")
print("="*80)

try:
    conn = pyodbc.connect(connection_string, timeout=30)
    cursor = conn.cursor()

    # 删除旧表
    print("\n步骤1：删除旧表...")
    cursor.execute('DROP TABLE IF EXISTS province_statistics_old_standard')
    conn.commit()
    print("  ✓ 已删除表")

    # 创建新表
    print("\n步骤2：创建新表...")
    create_sql = """
    CREATE TABLE province_statistics_old_standard (
        id INT IDENTITY(1,1) PRIMARY KEY,
        stat_date VARCHAR(7) NOT NULL,
        stat_type NVARCHAR(20) NOT NULL,
        province_name NVARCHAR(50) NOT NULL,

        -- 污染物浓度
        so2_concentration INT,
        no2_concentration INT,
        pm10_concentration INT,
        pm2_5_concentration INT,
        co_concentration DECIMAL(4, 1),
        o3_8h_concentration INT,

        -- 单项指数
        so2_index DECIMAL(10, 3),
        no2_index DECIMAL(10, 3),
        pm10_index DECIMAL(10, 3),
        pm2_5_index DECIMAL(10, 3),
        co_index DECIMAL(10, 3),
        o3_8h_index DECIMAL(10, 3),

        -- 综合指数
        comprehensive_index_new_algo DECIMAL(10, 3),
        comprehensive_index_rank_new_algo INT,
        comprehensive_index_old_algo DECIMAL(10, 3),
        comprehensive_index_rank_old_algo INT,

        -- 元数据
        data_days INT,
        sample_coverage DECIMAL(10, 2),
        city_count INT,
        city_names NVARCHAR(500),

        -- 达标率字段
        exceed_days INT,
        valid_days INT,
        compliance_rate DECIMAL(5,1),
        exceed_rate DECIMAL(5,1),

        -- 时间戳
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE(),

        -- 约束
        CONSTRAINT IX_province_statistics_old_standard UNIQUE (stat_date, stat_type, province_name)
    )
    """
    cursor.execute(create_sql)
    conn.commit()
    print("  ✓ 已创建表")

    # 创建索引
    print("\n步骤3：创建索引...")
    cursor.execute('CREATE INDEX idx_old_date_type ON province_statistics_old_standard(stat_date, stat_type)')
    cursor.execute('CREATE INDEX idx_old_province_name ON province_statistics_old_standard(province_name)')
    conn.commit()
    print("  ✓ 已创建索引")

    cursor.close()
    conn.close()

    print("\n" + "="*80)
    print("✓ 旧标准表重建完成！")
    print("="*80)

except Exception as e:
    print(f"\n错误: {e}")
    import traceback
    traceback.print_exc()
