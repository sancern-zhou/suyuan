-- ============================================================================
-- 168城市空气质量统计预计算表
-- ============================================================================
-- 功能：存储168个重点城市的空气质量评价指标（按HJ663标准）
-- 数据库：XcAiDb
-- 作者：Claude Code
-- 日期：2026-04-05
-- ============================================================================

-- 创建表
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'city_168_statistics')
BEGIN
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
    );

    PRINT 'Table city_168_statistics created successfully.';
END
ELSE
BEGIN
    PRINT 'Table city_168_statistics already exists.';
END
GO

-- 创建索引
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_city_168_date' AND object_id = OBJECT_ID('city_168_statistics'))
BEGIN
    CREATE INDEX idx_city_168_date ON city_168_statistics(stat_date);
    PRINT 'Index idx_city_168_date created successfully.';
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_city_168_type' AND object_id = OBJECT_ID('city_168_statistics'))
BEGIN
    CREATE INDEX idx_city_168_type ON city_168_statistics(stat_type);
    PRINT 'Index idx_city_168_type created successfully.';
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_city_168_city' AND object_id = OBJECT_ID('city_168_statistics'))
BEGIN
    CREATE INDEX idx_city_168_city ON city_168_statistics(city_name);
    PRINT 'Index idx_city_168_city created successfully.';
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_city_168_rank' AND object_id = OBJECT_ID('city_168_statistics'))
BEGIN
    CREATE INDEX idx_city_168_rank ON city_168_statistics(comprehensive_index_rank);
    PRINT 'Index idx_city_168_rank created successfully.';
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_city_168_date_type' AND object_id = OBJECT_ID('city_168_statistics'))
BEGIN
    CREATE INDEX idx_city_168_date_type ON city_168_statistics(stat_date, stat_type);
    PRINT 'Index idx_city_168_date_type created successfully.';
END
GO

-- ============================================================================
-- stat_type枚举值说明：
-- - monthly: 月度统计（如2024-03）
-- - annual_ytd: 年度累计（如2024年1月至当前月）
-- - current_month: 当月累计（如2024-03-01至2024-03-15）
-- ============================================================================

-- 添加表注释（SQL Server使用扩展属性）
IF NOT EXISTS (SELECT * FROM sys.extended_properties WHERE name = 'MS_Description' AND major_id = OBJECT_ID('city_168_statistics'))
BEGIN
    EXEC sp_addextendedproperty
        @name = N'MS_Description',
        @value = N'168城市空气质量统计预计算表，存储月度统计、年度累计、当月累计三种类型的空气质量评价指标（按HJ663标准）',
        @level0type = N'SCHEMA', @level0name = N'dbo',
        @level1type = N'TABLE', @level1name = N'city_168_statistics';
    PRINT 'Table description added successfully.';
END
GO

PRINT '========================================';
PRINT 'city_168_statistics table setup completed!';
PRINT '========================================';
