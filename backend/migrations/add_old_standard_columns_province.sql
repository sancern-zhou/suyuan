-- ============================================================================
-- 省级统计表添加旧标准综合指数字段
-- ============================================================================
-- 功能：为province_statistics表添加旧标准（HJ 663-2013）综合指数字段
-- 数据库：XcAiDb
-- 作者：Claude Code
-- 日期：2026-04-09
-- ============================================================================

-- 添加旧标准单项指数字段
IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('province_statistics')
    AND name = 'pm10_index_old'
)
BEGIN
    ALTER TABLE province_statistics ADD pm10_index_old DECIMAL(10,3);
    PRINT 'Column pm10_index_old added successfully.';
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('province_statistics')
    AND name = 'pm2_5_index_old'
)
BEGIN
    ALTER TABLE province_statistics ADD pm2_5_index_old DECIMAL(10,3);
    PRINT 'Column pm2_5_index_old added successfully.';
END
GO

-- 添加旧标准综合指数和排名字段
IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('province_statistics')
    AND name = 'comprehensive_index_old'
)
BEGIN
    ALTER TABLE province_statistics ADD comprehensive_index_old DECIMAL(10,3);
    PRINT 'Column comprehensive_index_old added successfully.';
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('province_statistics')
    AND name = 'comprehensive_index_rank_old'
)
BEGIN
    ALTER TABLE province_statistics ADD comprehensive_index_rank_old INT;
    PRINT 'Column comprehensive_index_rank_old added successfully.';
END
GO

-- 添加标准版本字段
IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('province_statistics')
    AND name = 'standard_version'
)
BEGIN
    ALTER TABLE province_statistics ADD standard_version NVARCHAR(20) DEFAULT 'HJ663-2026';
    PRINT 'Column standard_version added successfully.';
END
GO

-- 为旧标准排名创建索引
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_province_rank_old' AND object_id = OBJECT_ID('province_statistics'))
BEGIN
    CREATE INDEX idx_province_rank_old ON province_statistics(comprehensive_index_rank_old);
    PRINT 'Index idx_province_rank_old created successfully.';
END
GO

PRINT '========================================';
PRINT '旧标准字段添加完成！';
PRINT '========================================';
