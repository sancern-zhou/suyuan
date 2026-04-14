-- ============================================================================
-- 省级统计表重构：新旧标准分离
-- ============================================================================
-- 功能：
--   1. 将 province_statistics 重命名为 province_statistics_new_standard
--   2. 删除新标准表中的旧标准字段
--   3. 创建 province_statistics_old_standard 表
-- 数据库：XcAiDb
-- 作者：Claude Code
-- 日期：2026-04-09
-- ============================================================================

USE XcAiDb;
GO

PRINT '========================================';
PRINT '省级统计表重构开始';
PRINT '========================================';
GO

-- ============================================================================
-- 1. 重命名现有表为 province_statistics_new_standard
-- ============================================================================

IF EXISTS (SELECT * FROM sys.tables WHERE name = 'province_statistics' AND NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'province_statistics_new_standard'))
BEGIN
    EXEC sp_rename 'province_statistics', 'province_statistics_new_standard';
    PRINT '成功重命名表: province_statistics -> province_statistics_new_standard';
END
ELSE
BEGIN
    PRINT '表 province_statistics_new_standard 已存在，跳过重命名';
END
GO

-- ============================================================================
-- 2. 删除新标准表中的旧标准字段
-- ============================================================================

-- 删除旧标准单项指数
IF EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('province_statistics_new_standard') AND name = 'pm10_index_old')
BEGIN
    ALTER TABLE province_statistics_new_standard DROP COLUMN pm10_index_old;
    PRINT '已删除字段: pm10_index_old';
END
GO

IF EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('province_statistics_new_standard') AND name = 'pm2_5_index_old')
BEGIN
    ALTER TABLE province_statistics_new_standard DROP COLUMN pm2_5_index_old;
    PRINT '已删除字段: pm2_5_index_old';
END
GO

-- 删除旧限值+旧算法综合指数
IF EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('province_statistics_new_standard') AND name = 'comprehensive_index_old')
BEGIN
    ALTER TABLE province_statistics_new_standard DROP COLUMN comprehensive_index_old;
    PRINT '已删除字段: comprehensive_index_old';
END
GO

IF EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('province_statistics_new_standard') AND name = 'comprehensive_index_rank_old')
BEGIN
    ALTER TABLE province_statistics_new_standard DROP COLUMN comprehensive_index_rank_old;
    PRINT '已删除字段: comprehensive_index_rank_old';
END
GO

-- 删除旧限值+新算法综合指数
IF EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('province_statistics_new_standard') AND name = 'comprehensive_index_old_limit_new_algo')
BEGIN
    ALTER TABLE province_statistics_new_standard DROP COLUMN comprehensive_index_old_limit_new_algo;
    PRINT '已删除字段: comprehensive_index_old_limit_new_algo';
END
GO

IF EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('province_statistics_new_standard') AND name = 'comprehensive_index_rank_old_limit_new_algo')
BEGIN
    ALTER TABLE province_statistics_new_standard DROP COLUMN comprehensive_index_rank_old_limit_new_algo;
    PRINT '已删除字段: comprehensive_index_rank_old_limit_new_algo';
END
GO

-- 删除旧标准相关索引
IF EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_province_rank_old' AND object_id = OBJECT_ID('province_statistics_new_standard'))
BEGIN
    DROP INDEX idx_province_rank_old ON province_statistics_new_standard;
    PRINT '已删除索引: idx_province_rank_old';
END
GO

IF EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_province_rank_old_limit_new_algo' AND object_id = OBJECT_ID('province_statistics_new_standard'))
BEGIN
    DROP INDEX idx_province_rank_old_limit_new_algo ON province_statistics_new_standard;
    PRINT '已删除索引: idx_province_rank_old_limit_new_algo';
END
GO

-- ============================================================================
-- 3. 创建旧标准表 province_statistics_old_standard
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'province_statistics_old_standard')
BEGIN
    CREATE TABLE province_statistics_old_standard (
        id INT IDENTITY(1,1) PRIMARY KEY,
        stat_date DATE NOT NULL,
        stat_type NVARCHAR(20) NOT NULL,  -- monthly, annual_ytd, current_month
        province_name NVARCHAR(50) NOT NULL,

        -- 污染物浓度（按final_output规则修约：CO保留1位，其他取整）
        so2_concentration INT,                   -- 取整
        no2_concentration INT,                   -- 取整
        pm10_concentration INT,                  -- 取整
        pm2_5_concentration INT,                 -- 取整
        co_concentration DECIMAL(4, 1),          -- 保留1位小数（最大值<100，4位足够）
        o3_8h_concentration INT,                 -- 取整

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

        -- 索引
        CONSTRAINT IX_province_statistics_old_standard UNIQUE (stat_date, stat_type, province_name)
    );

    PRINT '成功创建表: province_statistics_old_standard';
END
ELSE
BEGIN
    PRINT '表 province_statistics_old_standard 已存在';
END
GO

-- ============================================================================
-- 4. 创建索引
-- ============================================================================

-- 旧限值+新算法排名索引
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_province_old_standard_rank_new_algo' AND object_id = OBJECT_ID('province_statistics_old_standard'))
BEGIN
    CREATE INDEX idx_province_old_standard_rank_new_algo
    ON province_statistics_old_standard(comprehensive_index_rank_new_algo);
    PRINT '成功创建索引: idx_province_old_standard_rank_new_algo';
END
GO

-- 旧限值+旧算法排名索引
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_province_old_standard_rank_old_algo' AND object_id = OBJECT_ID('province_statistics_old_standard'))
BEGIN
    CREATE INDEX idx_province_old_standard_rank_old_algo
    ON province_statistics_old_standard(comprehensive_index_rank_old_algo);
    PRINT '成功创建索引: idx_province_old_standard_rank_old_algo';
END
GO

-- 日期和类型索引
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_province_old_standard_date_type' AND object_id = OBJECT_ID('province_statistics_old_standard'))
BEGIN
    CREATE INDEX idx_province_old_standard_date_type
    ON province_statistics_old_standard(stat_date, stat_type);
    PRINT '成功创建索引: idx_province_old_standard_date_type';
END
GO

-- ============================================================================
-- 5. 添加字段注释
-- ============================================================================

EXEC sp_addextendedproperty
    @name = N'MS_Description',
    @value = N'省级空气质量统计数据表（旧标准限值版本）',
    @level0type = N'SCHEMA', @level0name = N'dbo',
    @level1type = N'TABLE', @level1name = N'province_statistics_old_standard';
GO

EXEC sp_addextendedproperty
    @name = N'MS_Description',
    @value = N'综合指数（旧限值+新算法）- 使用HJ 663-2013限值（PM10=70, PM2.5=35），新权重（PM2.5=3, NO2=2, O3=2）',
    @level0type = N'SCHEMA', @level0name = N'dbo',
    @level1type = N'TABLE', @level1name = N'province_statistics_old_standard',
    @level2type = N'COLUMN', @level2name = N'comprehensive_index_new_algo';
GO

EXEC sp_addextendedproperty
    @name = N'MS_Description',
    @value = N'综合指数（旧限值+旧算法）- 使用HJ 663-2013限值（PM10=70, PM2.5=35），旧权重（所有权重均为1）',
    @level0type = N'SCHEMA', @level0name = N'dbo',
    @level1type = N'TABLE', @level1name = N'province_statistics_old_standard',
    @level2type = N'COLUMN', @level2name = N'comprehensive_index_old_algo';
GO

PRINT '========================================';
PRINT '省级统计表重构完成！';
PRINT '========================================';
PRINT '新标准表: province_statistics_new_standard';
PRINT '旧标准表: province_statistics_old_standard';
PRINT '========================================';
GO
