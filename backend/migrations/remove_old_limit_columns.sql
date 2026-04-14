-- 删除旧限值相关字段（新标准表只保留新限值的综合指数）
-- 执行日期: 2026-04-09
-- 说明: 新标准表(city_168_statistics_new_standard)只保留2套综合指数：新限值+新算法、新限值+旧算法
--       旧限值相关的综合指数移至旧标准表(city_168_statistics_old_standard)

USE XcAiDb;
GO

-- 要删除的字段说明:
-- pm10_index_old: 旧限值PM10单项指数
-- pm2_5_index_old: 旧限值PM2.5单项指数
-- comprehensive_index_old: 旧限值+旧算法综合指数
-- comprehensive_index_rank_old: 旧限值+旧算法综合指数排名
-- comprehensive_index_old_limit_new_algo: 旧限值+新算法综合指数
-- comprehensive_index_rank_old_limit_new_algo: 旧限值+新算法综合指数排名

-- 1. 删除索引
IF EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_city_168_rank_old' AND object_id = OBJECT_ID('city_168_statistics_new_standard'))
BEGIN
    DROP INDEX idx_city_168_rank_old ON city_168_statistics_new_standard;
    PRINT 'Index idx_city_168_rank_old dropped successfully.';
END
GO

IF EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_city_168_rank_old_limit_new_algo' AND object_id = OBJECT_ID('city_168_statistics_new_standard'))
BEGIN
    DROP INDEX idx_city_168_rank_old_limit_new_algo ON city_168_statistics_new_standard;
    PRINT 'Index idx_city_168_rank_old_limit_new_algo dropped successfully.';
END
GO

-- 2. 删除扩展属性（字段注释）
DECLARE @sql NVARCHAR(MAX);

-- 删除 pm10_index_old 注释
IF EXISTS (
    SELECT 1 FROM sys.extended_properties
    WHERE major_id = OBJECT_ID('city_168_statistics_new_standard')
    AND minor_id = (SELECT column_id FROM sys.columns WHERE object_id = OBJECT_ID('city_168_statistics_new_standard') AND name = 'pm10_index_old')
    AND name = 'MS_Description'
)
BEGIN
    EXEC sp_dropextendedproperty
        @name = N'MS_Description',
        @level0type = N'SCHEMA', @level0name = N'dbo',
        @level1type = N'TABLE', @level1name = N'city_168_statistics_new_standard',
        @level2type = N'COLUMN', @level2name = N'pm10_index_old';
    PRINT 'Extended property for pm10_index_old dropped.';
END
GO

-- 删除 pm2_5_index_old 注释
IF EXISTS (
    SELECT 1 FROM sys.extended_properties
    WHERE major_id = OBJECT_ID('city_168_statistics_new_standard')
    AND minor_id = (SELECT column_id FROM sys.columns WHERE object_id = OBJECT_ID('city_168_statistics_new_standard') AND name = 'pm2_5_index_old')
    AND name = 'MS_Description'
)
BEGIN
    EXEC sp_dropextendedproperty
        @name = N'MS_Description',
        @level0type = N'SCHEMA', @level0name = N'dbo',
        @level1type = N'TABLE', @level1name = N'city_168_statistics_new_standard',
        @level2type = N'COLUMN', @level2name = N'pm2_5_index_old';
    PRINT 'Extended property for pm2_5_index_old dropped.';
END
GO

-- 删除 comprehensive_index_old 注释
IF EXISTS (
    SELECT 1 FROM sys.extended_properties
    WHERE major_id = OBJECT_ID('city_168_statistics_new_standard')
    AND minor_id = (SELECT column_id FROM sys.columns WHERE object_id = OBJECT_ID('city_168_statistics_new_standard') AND name = 'comprehensive_index_old')
    AND name = 'MS_Description'
)
BEGIN
    EXEC sp_dropextendedproperty
        @name = N'MS_Description',
        @level0type = N'SCHEMA', @level0name = N'dbo',
        @level1type = N'TABLE', @level1name = N'city_168_statistics_new_standard',
        @level2type = N'COLUMN', @level2name = N'comprehensive_index_old';
    PRINT 'Extended property for comprehensive_index_old dropped.';
END
GO

-- 删除 comprehensive_index_rank_old 注释
IF EXISTS (
    SELECT 1 FROM sys.extended_properties
    WHERE major_id = OBJECT_ID('city_168_statistics_new_standard')
    AND minor_id = (SELECT column_id FROM sys.columns WHERE object_id = OBJECT_ID('city_168_statistics_new_standard') AND name = 'comprehensive_index_rank_old')
    AND name = 'MS_Description'
)
BEGIN
    EXEC sp_dropextendedproperty
        @name = N'MS_Description',
        @level0type = N'SCHEMA', @level0name = N'dbo',
        @level1type = N'TABLE', @level1name = N'city_168_statistics_new_standard',
        @level2type = N'COLUMN', @level2name = N'comprehensive_index_rank_old';
    PRINT 'Extended property for comprehensive_index_rank_old dropped.';
END
GO

-- 删除 comprehensive_index_old_limit_new_algo 注释
IF EXISTS (
    SELECT 1 FROM sys.extended_properties
    WHERE major_id = OBJECT_ID('city_168_statistics_new_standard')
    AND minor_id = (SELECT column_id FROM sys.columns WHERE object_id = OBJECT_ID('city_168_statistics_new_standard') AND name = 'comprehensive_index_old_limit_new_algo')
    AND name = 'MS_Description'
)
BEGIN
    EXEC sp_dropextendedproperty
        @name = N'MS_Description',
        @level0type = N'SCHEMA', @level0name = N'dbo',
        @level1type = N'TABLE', @level1name = N'city_168_statistics_new_standard',
        @level2type = N'COLUMN', @level2name = N'comprehensive_index_old_limit_new_algo';
    PRINT 'Extended property for comprehensive_index_old_limit_new_algo dropped.';
END
GO

-- 删除 comprehensive_index_rank_old_limit_new_algo 注释
IF EXISTS (
    SELECT 1 FROM sys.extended_properties
    WHERE major_id = OBJECT_ID('city_168_statistics_new_standard')
    AND minor_id = (SELECT column_id FROM sys.columns WHERE object_id = OBJECT_ID('city_168_statistics_new_standard') AND name = 'comprehensive_index_rank_old_limit_new_algo')
    AND name = 'MS_Description'
)
BEGIN
    EXEC sp_dropextendedproperty
        @name = N'MS_Description',
        @level0type = N'SCHEMA', @level0name = N'dbo',
        @level1type = N'TABLE', @level1name = N'city_168_statistics_new_standard',
        @level2type = N'COLUMN', @level2name = N'comprehensive_index_rank_old_limit_new_algo';
    PRINT 'Extended property for comprehensive_index_rank_old_limit_new_algo dropped.';
END
GO

-- 3. 删除字段
ALTER TABLE city_168_statistics_new_standard
DROP COLUMN IF EXISTS pm10_index_old;
PRINT 'Column pm10_index_old dropped.';
GO

ALTER TABLE city_168_statistics_new_standard
DROP COLUMN IF EXISTS pm2_5_index_old;
PRINT 'Column pm2_5_index_old dropped.';
GO

ALTER TABLE city_168_statistics_new_standard
DROP COLUMN IF EXISTS comprehensive_index_old;
PRINT 'Column comprehensive_index_old dropped.';
GO

ALTER TABLE city_168_statistics_new_standard
DROP COLUMN IF EXISTS comprehensive_index_rank_old;
PRINT 'Column comprehensive_index_rank_old dropped.';
GO

ALTER TABLE city_168_statistics_new_standard
DROP COLUMN IF EXISTS comprehensive_index_old_limit_new_algo;
PRINT 'Column comprehensive_index_old_limit_new_algo dropped.';
GO

ALTER TABLE city_168_statistics_new_standard
DROP COLUMN IF EXISTS comprehensive_index_rank_old_limit_new_algo;
PRINT 'Column comprehensive_index_rank_old_limit_new_algo dropped.';
GO

PRINT '========================================';
PRINT '成功删除旧限值相关字段！';
PRINT '新标准表现在只保留:';
PRINT '  - comprehensive_index (新限值+新算法)';
PRINT '  - comprehensive_index_rank';
PRINT '  - comprehensive_index_new_limit_old_algo (新限值+旧算法)';
PRINT '  - comprehensive_index_rank_new_limit_old_algo';
PRINT '';
PRINT '旧限值相关数据请使用 city_168_statistics_old_standard 表';
PRINT '========================================';
GO
