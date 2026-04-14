-- 重命名新标准表，使其与旧标准表命名风格一致
-- 执行日期: 2026-04-09
-- 说明:
--   city_168_statistics -> city_168_statistics_new_standard（新标准表）
--   city_168_statistics_old_standard（旧标准表，保持不变）

USE XcAiDb;
GO

-- 检查新标准表是否存在
IF EXISTS (SELECT * FROM sys.tables WHERE name = 'city_168_statistics')
BEGIN
    -- 重命名表
    EXEC sp_rename 'city_168_statistics', 'city_168_statistics_new_standard';
    PRINT 'Table city_168_statistics renamed to city_168_statistics_new_standard successfully.';
END
ELSE
BEGIN
    PRINT 'Table city_168_statistics does not exist.';
END
GO

-- 更新表的扩展属性描述
IF EXISTS (SELECT * FROM sys.extended_properties WHERE name = N'MS_Description' AND major_id = OBJECT_ID('city_168_statistics_new_standard'))
BEGIN
    EXEC sp_dropextendedproperty
        @name = N'MS_Description',
        @level0type = N'SCHEMA', @level0name = N'dbo',
        @level1type = N'TABLE', @level1name = N'city_168_statistics_new_standard';
END
GO

EXEC sp_addextendedproperty
    @name = N'MS_Description',
    @value = N'168城市空气质量统计预计算表（新标准限值版本），按HJ 663-2026新标准计算综合指数。存储2套综合指数：新限值+新算法、新限值+旧算法。',
    @level0type = N'SCHEMA', @level0name = N'dbo',
    @level1type = N'TABLE', @level1name = N'city_168_statistics_new_standard';
GO

-- 更新旧标准表的描述
IF EXISTS (SELECT * FROM sys.extended_properties WHERE name = N'MS_Description' AND major_id = OBJECT_ID('city_168_statistics_old_standard'))
BEGIN
    EXEC sp_dropextendedproperty
        @name = N'MS_Description',
        @level0type = N'SCHEMA', @level0name = N'dbo',
        @level1type = N'TABLE', @level1name = N'city_168_statistics_old_standard';
END
GO

EXEC sp_addextendedproperty
    @name = N'MS_Description',
    @value = N'168城市空气质量统计预计算表（旧标准限值版本），按HJ 663-2013旧标准计算综合指数。存储2套综合指数：旧限值+新算法、旧限值+旧算法。',
    @level0type = N'SCHEMA', @level0name = N'dbo',
    @level1type = N'TABLE', @level1name = N'city_168_statistics_old_standard';
GO

PRINT '========================================';
PRINT '表重命名完成！';
PRINT '';
PRINT '两张表命名风格一致:';
PRINT '  - city_168_statistics_new_standard（新标准表）';
PRINT '  - city_168_statistics_old_standard（旧标准表）';
PRINT '========================================';
GO
