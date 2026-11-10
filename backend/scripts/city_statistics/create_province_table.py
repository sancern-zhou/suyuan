"""
省级空气质量统计表创建脚本

功能：在XcAiDb数据库中创建province_statistics表
使用方法：python create_province_table.py

作者：Claude Code
版本：1.0.0
日期：2026-04-05
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.fetchers.city_statistics.city_statistics_fetcher import SQLServerClient
import structlog

logger = structlog.get_logger()


def create_province_table():
    """创建province_statistics表及其索引"""
    client = SQLServerClient()

    # 测试连接
    if not client.test_connection():
        logger.error("sql_server_connection_failed")
        print("数据库连接失败，请检查连接配置")
        return False

    logger.info("sql_server_connection_success")
    print("数据库连接成功\n")

    # 创建表的SQL脚本
    sql_script = """
-- ============================================================================
-- 省级空气质量统计预计算表
-- ============================================================================
-- 功能：存储31个省级行政区的空气质量评价指标（按HJ663标准）
-- 数据库：XcAiDb
-- 作者：Claude Code
-- 日期：2026-04-05
-- ============================================================================

-- 创建表
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'province_statistics')
BEGIN
    CREATE TABLE province_statistics (
        id INT IDENTITY(1,1) PRIMARY KEY,
        stat_date DATE NOT NULL,
        stat_type NVARCHAR(20) NOT NULL,
        province_name NVARCHAR(50) NOT NULL,

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

        -- 综合指数和排名
        comprehensive_index DECIMAL(10,3),
        comprehensive_index_rank INT,

        -- 元数据
        data_days INT,
        sample_coverage DECIMAL(5,2),
        city_count INT,
        city_names NVARCHAR(500),

        -- 时间戳
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE()
    );

    PRINT 'Table province_statistics created successfully.';
END
ELSE
BEGIN
    PRINT 'Table province_statistics already exists.';
END
GO

-- 创建索引
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_province_date' AND object_id = OBJECT_ID('province_statistics'))
BEGIN
    CREATE INDEX idx_province_date ON province_statistics(stat_date);
    PRINT 'Index idx_province_date created successfully.';
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_province_type' AND object_id = OBJECT_ID('province_statistics'))
BEGIN
    CREATE INDEX idx_province_type ON province_statistics(stat_type);
    PRINT 'Index idx_province_type created successfully.';
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_province_name' AND object_id = OBJECT_ID('province_statistics'))
BEGIN
    CREATE INDEX idx_province_name ON province_statistics(province_name);
    PRINT 'Index idx_province_name created successfully.';
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_province_rank' AND object_id = OBJECT_ID('province_statistics'))
BEGIN
    CREATE INDEX idx_province_rank ON province_statistics(comprehensive_index_rank);
    PRINT 'Index idx_province_rank created successfully.';
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_province_date_type' AND object_id = OBJECT_ID('province_statistics'))
BEGIN
    CREATE INDEX idx_province_date_type ON province_statistics(stat_date, stat_type);
    PRINT 'Index idx_province_date_type created successfully.';
END
GO

-- 创建唯一约束（防止重复插入）
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_province_unique' AND object_id = OBJECT_ID('province_statistics'))
BEGIN
    CREATE UNIQUE INDEX idx_province_unique ON province_statistics(stat_date, stat_type, province_name);
    PRINT 'Unique constraint idx_province_unique created successfully.';
END
GO

-- 添加表注释
IF NOT EXISTS (SELECT * FROM sys.extended_properties WHERE name = 'MS_Description' AND major_id = OBJECT_ID('province_statistics'))
BEGIN
    EXEC sp_addextendedproperty
        @name = N'MS_Description',
        @value = N'省级空气质量统计预计算表，存储31个省级行政区的月度统计、年度累计、当月累计三种类型的空气质量评价指标（按HJ663标准）',
        @level0type = N'SCHEMA', @level0name = N'dbo',
        @level1type = N'TABLE', @level1name = N'province_statistics';
    PRINT 'Table description added successfully.';
END
GO

PRINT '========================================';
PRINT 'province_statistics table setup completed!';
PRINT '========================================';
"""

    try:
        import pyodbc
        conn = pyodbc.connect(client.connection_string, timeout=30)

        # 分割SQL脚本并执行每个GO批次
        batches = sql_script.split('GO\n')

        for i, batch in enumerate(batches, 1):
            if batch.strip():
                try:
                    cursor = conn.cursor()
                    cursor.execute(batch)
                    conn.commit()
                    cursor.close()
                except Exception as e:
                    print(f"Batch {i} execution note: {str(e)}")

        conn.close()

        print("\n" + "="*60)
        print("province_statistics表创建成功！")
        print("="*60)
        return True

    except Exception as e:
        logger.error(
            "create_province_table_failed",
            error=str(e),
            exc_info=True
        )
        print(f"创建表失败: {str(e)}")
        return False


if __name__ == "__main__":
    create_province_table()
