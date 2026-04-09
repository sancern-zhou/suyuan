-- 添加旧标准（HJ 663-2013）综合指数字段
-- 执行日期: 2026-04-09
-- 说明: 同时支持新旧两个标准的综合指数计算和存储

USE XcAiDb;
GO

-- 1. 添加旧标准的单项指数字段
ALTER TABLE city_168_statistics
ADD pm10_index_old decimal(10, 3) NULL;
GO

ALTER TABLE city_168_statistics
ADD pm2_5_index_old decimal(10, 3) NULL;
GO

-- 2. 添加旧标准的综合指数和排名字段
ALTER TABLE city_168_statistics
ADD comprehensive_index_old decimal(10, 3) NULL;
GO

ALTER TABLE city_168_statistics
ADD comprehensive_index_rank_old int NULL;
GO

-- 3. 添加标准版本标识字段
ALTER TABLE city_168_statistics
ADD standard_version nvarchar(20) NULL;
GO

-- 4. 添加字段注释（SQL Server使用扩展属性）
EXEC sp_addextendedproperty
    @name = N'MS_Description',
    @value = N'PM10单项指数（按HJ 663-2013旧标准计算，标准限值70μg/m³）',
    @level0type = N'SCHEMA', @level0name = N'dbo',
    @level1type = N'TABLE', @level1name = N'city_168_statistics',
    @level2type = N'COLUMN', @level2name = N'pm10_index_old';
GO

EXEC sp_addextendedproperty
    @name = N'MS_Description',
    @value = N'PM2.5单项指数（按HJ 663-2013旧标准计算，标准限值35μg/m³）',
    @level0type = N'SCHEMA', @level0name = N'dbo',
    @level1type = N'TABLE', @level1name = N'city_168_statistics',
    @level2type = N'COLUMN', @level2name = N'pm2_5_index_old';
GO

EXEC sp_addextendedproperty
    @name = N'MS_Description',
    @value = N'综合指数（按HJ 663-2013旧标准计算）',
    @level0type = N'SCHEMA', @level0name = N'dbo',
    @level1type = N'TABLE', @level1name = N'city_168_statistics',
    @level2type = N'COLUMN', @level2name = N'comprehensive_index_old';
GO

EXEC sp_addextendedproperty
    @name = N'MS_Description',
    @value = N'综合指数排名（按HJ 663-2013旧标准计算）',
    @level0type = N'SCHEMA', @level0name = N'dbo',
    @level1type = N'TABLE', @level1name = N'city_168_statistics',
    @level2type = N'COLUMN', @level2name = N'comprehensive_index_rank_old';
GO

EXEC sp_addextendedproperty
    @name = N'MS_Description',
    @value = N'标准版本标识（HJ663-2013/HJ663-2021）',
    @level0type = N'SCHEMA', @level0name = N'dbo',
    @level1type = N'TABLE', @level1name = N'city_168_statistics',
    @level2type = N'COLUMN', @level2name = N'standard_version';
GO

-- 5. 为现有数据添加标准版本标识
UPDATE city_168_statistics
SET standard_version = 'HJ663-2021'
WHERE standard_version IS NULL;
GO

PRINT '成功添加旧标准字段！';
PRINT '新增字段: pm10_index_old, pm2_5_index_old, comprehensive_index_old, comprehensive_index_rank_old, standard_version';
GO
