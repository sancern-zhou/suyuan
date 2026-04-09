-- 添加4套标准组合的综合指数字段（省份数据表）
-- 执行日期: 2026-04-09
-- 说明: 支持新旧污染物浓度限值与新旧综合指数算法的4种组合

USE XcAiDb;
GO

-- 标准组合说明:
-- 1. 新限值+新算法 (已有): comprehensive_index
-- 2. 新限值+旧算法 (新增): comprehensive_index_new_limit_old_algo
-- 3. 旧限值+新算法 (新增): comprehensive_index_old_limit_new_algo
-- 4. 旧限值+旧算法 (已有): comprehensive_index_old

-- 污染物浓度限值差异:
-- PM10: 新标准60, 旧标准70
-- PM2.5: 新标准30, 旧标准35

-- 综合指数算法差异:
-- 新算法权重: PM2.5=3, NO2=2, O3=2, 其他=1
-- 旧算法权重: 所有污染物权重均为1

-- 1. 添加新限值+旧算法字段
ALTER TABLE province_statistics
ADD comprehensive_index_new_limit_old_algo decimal(10, 3) NULL;
GO

ALTER TABLE province_statistics
ADD comprehensive_index_rank_new_limit_old_algo int NULL;
GO

-- 2. 添加旧限值+新算法字段
ALTER TABLE province_statistics
ADD comprehensive_index_old_limit_new_algo decimal(10, 3) NULL;
GO

ALTER TABLE province_statistics
ADD comprehensive_index_rank_old_limit_new_algo int NULL;
GO

-- 3. 添加字段注释
EXEC sp_addextendedproperty
    @name = N'MS_Description',
    @value = N'综合指数（新污染物浓度限值+旧综合指数算法）- PM10/PM2.5使用新限值(60/30)，所有污染物权重均为1',
    @level0type = N'SCHEMA', @level0name = N'dbo',
    @level1type = N'TABLE', @level1name = N'province_statistics',
    @level2type = N'COLUMN', @level2name = N'comprehensive_index_new_limit_old_algo';
GO

EXEC sp_addextendedproperty
    @name = N'MS_Description',
    @value = N'综合指数排名（新污染物浓度限值+旧综合指数算法）',
    @level0type = N'SCHEMA', @level0name = N'dbo',
    @level1type = N'TABLE', @level1name = N'province_statistics',
    @level2type = N'COLUMN', @level2name = N'comprehensive_index_rank_new_limit_old_algo';
GO

EXEC sp_addextendedproperty
    @name = N'MS_Description',
    @value = N'综合指数（旧污染物浓度限值+新综合指数算法）- PM10/PM2.5使用旧限值(70/35)，PM2.5/NO2/O3权重为3/2/2',
    @level0type = N'SCHEMA', @level0name = N'dbo',
    @level1type = N'TABLE', @level1name = N'province_statistics',
    @level2type = N'COLUMN', @level2name = N'comprehensive_index_old_limit_new_algo';
GO

EXEC sp_addextendedproperty
    @name = N'MS_Description',
    @value = N'综合指数排名（旧污染物浓度限值+新综合指数算法）',
    @level0type = N'SCHEMA', @level0name = N'dbo',
    @level1type = N'TABLE', @level1name = N'province_statistics',
    @level2type = N'COLUMN', @level2name = N'comprehensive_index_rank_old_limit_new_algo';
GO

-- 4. 为新字段创建索引
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_province_rank_new_limit_old_algo' AND object_id = OBJECT_ID('province_statistics'))
BEGIN
    CREATE INDEX idx_province_rank_new_limit_old_algo ON province_statistics(comprehensive_index_rank_new_limit_old_algo);
    PRINT 'Index idx_province_rank_new_limit_old_algo created successfully.';
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_province_rank_old_limit_new_algo' AND object_id = OBJECT_ID('province_statistics'))
BEGIN
    CREATE INDEX idx_province_rank_old_limit_new_algo ON province_statistics(comprehensive_index_rank_old_limit_new_algo);
    PRINT 'Index idx_province_rank_old_limit_new_algo created successfully.';
END
GO

PRINT '成功添加4套标准组合字段（省份数据表）！';
PRINT '新增字段: comprehensive_index_new_limit_old_algo, comprehensive_index_rank_new_limit_old_algo';
PRINT '         comprehensive_index_old_limit_new_algo, comprehensive_index_rank_old_limit_new_algo';
GO
