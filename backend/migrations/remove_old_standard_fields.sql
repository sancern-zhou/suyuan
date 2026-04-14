-- ========================================
-- 步骤5：删除 city_168_statistics 表中的旧标准字段
-- ⚠️ 执行前请先备份数据库！
-- ========================================

USE XcAiDb;
GO

PRINT '========================================';
PRINT '⚠️ 警告：即将删除 city_168_statistics 表中的旧标准字段';
PRINT '⚠️ 执行前请先备份数据库！';
PRINT '========================================';
PRINT '';

-- ========================================
-- 删除旧标准相关字段
-- ========================================

-- 删除旧标准综合指数和排名字段
ALTER TABLE dbo.city_168_statistics
DROP COLUMN IF EXISTS comprehensive_index_old;
GO

ALTER TABLE dbo.city_168_statistics
DROP COLUMN IF EXISTS comprehensive_index_rank_old;
GO

-- 删除旧限值+新算法字段（如果不需要保留用于对比）
-- 注意：如果需要保留新限值+旧算法的对比数据，请注释掉以下两行
ALTER TABLE dbo.city_168_statistics
DROP COLUMN IF EXISTS comprehensive_index_new_limit_old_algo;
GO

ALTER TABLE dbo.city_168_statistics
DROP COLUMN IF EXISTS comprehensive_index_rank_new_limit_old_algo;
GO

-- 删除旧限值+旧算法字段（如果不需要保留用于对比）
ALTER TABLE dbo.city_168_statistics
DROP COLUMN IF EXISTS comprehensive_index_old_limit_new_algo;
GO

ALTER TABLE dbo.city_168_statistics
DROP COLUMN IF EXISTS comprehensive_index_rank_old_limit_new_algo;
GO

-- 删除旧的PM10和PM2.5指数字段（如果存在）
ALTER TABLE dbo.city_168_statistics
DROP COLUMN IF EXISTS pm10_index_old;
GO

ALTER TABLE dbo.city_168_statistics
DROP COLUMN IF EXISTS pm2_5_index_old;
GO

PRINT '✅ 旧标准字段删除完成';
PRINT '';

-- ========================================
-- 验证表结构
-- ========================================

PRINT '========================================';
PRINT '验证表结构';
PRINT '========================================';

-- 显示当前表的字段列表
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'city_168_statistics'
    AND TABLE_SCHEMA = 'dbo'
ORDER BY ORDINAL_POSITION;
GO

PRINT '';
PRINT '========================================';
PRINT '✅ 迁移完成！';
PRINT '========================================';
PRINT '';
PRINT '当前表结构：';
PRINT '  - city_168_statistics_old_standard (旧标准 HJ 633-2013)';
PRINT '  - city_168_statistics_new_standard (新标准 HJ 633-2026)';
PRINT '  - city_168_statistics (待删除或重命名)';
