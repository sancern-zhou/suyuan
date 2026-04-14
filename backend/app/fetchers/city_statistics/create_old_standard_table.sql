-- ============================================================================
-- 168城市空气质量统计预计算表（旧标准限值版本）
-- ============================================================================
-- 功能：存储168个重点城市的空气质量评价指标（按HJ663旧标准限值）
-- 数据库：XcAiDb
-- 作者：Claude Code
-- 日期：2026-04-09
-- ============================================================================

-- 与现有表的区别：
-- 1. 污染物浓度修约规则：CO保留1位小数，其他取整（final_output规则）
-- 2. 计算综合指数时使用修约后的浓度值
-- 3. 存储2套综合指数：旧限值+新算法、旧限值+旧算法

-- 创建表
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'city_168_statistics_old_standard')
BEGIN
    CREATE TABLE city_168_statistics_old_standard (
        id INT IDENTITY(1,1) PRIMARY KEY,
        stat_date DATE NOT NULL,
        stat_type NVARCHAR(20) NOT NULL,
        city_name NVARCHAR(50) NOT NULL,
        city_code INT,

        -- 六项污染物浓度（按final_output规则修约：CO保留1位，其他取整）
        so2_concentration INT,                  -- 取整
        no2_concentration INT,                  -- 取整
        pm10_concentration INT,                 -- 取整
        pm2_5_concentration INT,                -- 取整
        co_concentration DECIMAL(4,1),          -- 保留1位（最大值<100，4位足够）
        o3_8h_concentration INT,                -- 取整

        -- 单项指数（使用旧限值计算）
        so2_index DECIMAL(10,3),
        no2_index DECIMAL(10,3),
        pm10_index DECIMAL(10,3),
        pm2_5_index DECIMAL(10,3),
        co_index DECIMAL(10,3),
        o3_8h_index DECIMAL(10,3),

        -- 综合指数（旧限值）
        comprehensive_index_new_algo DECIMAL(10,3),       -- 旧限值+新算法（PM2.5权重3，NO2权重2，O3权重2）
        comprehensive_index_rank_new_algo INT,
        comprehensive_index_old_algo DECIMAL(10,3),       -- 旧限值+旧算法（所有权重均为1）
        comprehensive_index_rank_old_algo INT,

        -- 元数据
        data_days INT,
        sample_coverage DECIMAL(5,2),
        region NVARCHAR(50),
        province NVARCHAR(50),

        -- 时间戳
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE()
    );

    PRINT 'Table city_168_statistics_old_standard created successfully.';
END
ELSE
BEGIN
    PRINT 'Table city_168_statistics_old_standard already exists.';
END
GO

-- 创建索引
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_city_168_old_date' AND object_id = OBJECT_ID('city_168_statistics_old_standard'))
BEGIN
    CREATE INDEX idx_city_168_old_date ON city_168_statistics_old_standard(stat_date);
    PRINT 'Index idx_city_168_old_date created successfully.';
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_city_168_old_type' AND object_id = OBJECT_ID('city_168_statistics_old_standard'))
BEGIN
    CREATE INDEX idx_city_168_old_type ON city_168_statistics_old_standard(stat_type);
    PRINT 'Index idx_city_168_old_type created successfully.';
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_city_168_old_city' AND object_id = OBJECT_ID('city_168_statistics_old_standard'))
BEGIN
    CREATE INDEX idx_city_168_old_city ON city_168_statistics_old_standard(city_name);
    PRINT 'Index idx_city_168_old_city created successfully.';
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_city_168_old_rank_new_algo' AND object_id = OBJECT_ID('city_168_statistics_old_standard'))
BEGIN
    CREATE INDEX idx_city_168_old_rank_new_algo ON city_168_statistics_old_standard(comprehensive_index_rank_new_algo);
    PRINT 'Index idx_city_168_old_rank_new_algo created successfully.';
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_city_168_old_rank_old_algo' AND object_id = OBJECT_ID('city_168_statistics_old_standard'))
BEGIN
    CREATE INDEX idx_city_168_old_rank_old_algo ON city_168_statistics_old_standard(comprehensive_index_rank_old_algo);
    PRINT 'Index idx_city_168_old_rank_old_algo created successfully.';
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_city_168_old_date_type' AND object_id = OBJECT_ID('city_168_statistics_old_standard'))
BEGIN
    CREATE INDEX idx_city_168_old_date_type ON city_168_statistics_old_standard(stat_date, stat_type);
    PRINT 'Index idx_city_168_old_date_type created successfully.';
END
GO

-- ============================================================================
-- stat_type枚举值说明：
-- - monthly: 月度统计（如2024-03）
-- - annual_ytd: 年度累计（如2024年1月至当前月）
-- - current_month: 当月累计（如2024-03-01至2024-03-15）
-- ============================================================================

-- 添加表注释（SQL Server使用扩展属性）
IF NOT EXISTS (SELECT * FROM sys.extended_properties WHERE name = N'MS_Description' AND major_id = OBJECT_ID('city_168_statistics_old_standard'))
BEGIN
    EXEC sp_addextendedproperty
        @name = N'MS_Description',
        @value = N'168城市空气质量统计预计算表（旧标准限值版本），污染物浓度修约规则：CO保留1位小数，其他取整。存储月度统计、年度累计、当月累计三种类型的空气质量评价指标（按HJ663旧标准限值）',
        @level0type = N'SCHEMA', @level0name = N'dbo',
        @level1type = N'TABLE', @level1name = N'city_168_statistics_old_standard';
    PRINT 'Table description added successfully.';
END
GO

PRINT '========================================';
PRINT 'city_168_statistics_old_standard table setup completed!';
PRINT '========================================';
