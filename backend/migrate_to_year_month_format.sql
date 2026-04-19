-- ====================================================================
-- 数据库表结构迁移：stat_date 从 DATE 改为 VARCHAR(7)
-- ====================================================================
-- 功能：
--   1. 备份现有数据
--   2. 修改字段类型
--   3. 转换日期格式：2026-01-01 → 2026-01
-- ====================================================================

USE [AirQuality];
GO

PRINT N'开始迁移 stat_date 字段格式...';
PRINT N'============================================================';
GO

-- ====================================================================
-- 步骤1：备份现有数据（可选）
-- ====================================================================
PRINT N'步骤1：创建备份表...';
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'province_statistics_new_standard_backup')
BEGIN
    SELECT * INTO province_statistics_new_standard_backup
    FROM province_statistics_new_standard;

    PRINT N'  ✓ 省级统计表已备份到 province_statistics_new_standard_backup';
END
ELSE
BEGIN
    PRINT N'  - 备份表已存在，跳过';
END
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'city_168_statistics_new_standard_backup')
BEGIN
    SELECT * INTO city_168_statistics_new_standard_backup
    FROM city_168_statistics_new_standard;

    PRINT N'  ✓ 城市统计表已备份到 city_168_statistics_new_standard_backup';
END
ELSE
BEGIN
    PRINT N'  - 备份表已存在，跳过';
END
GO

-- ====================================================================
-- 步骤2：添加新字段 stat_date_new
-- ====================================================================
PRINT N'';
PRINT N'步骤2：添加新字段 stat_date_new (VARCHAR(7))...';
GO

-- 检查字段是否已存在
IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('province_statistics_new_standard')
    AND name = 'stat_date_new'
)
BEGIN
    ALTER TABLE province_statistics_new_standard
    ADD stat_date_new VARCHAR(7);

    PRINT N'  ✓ province_statistics_new_standard: stat_date_new 字段已添加';
END
ELSE
BEGIN
    PRINT N'  - stat_date_new 字段已存在';
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('city_168_statistics_new_standard')
    AND name = 'stat_date_new'
)
BEGIN
    ALTER TABLE city_168_statistics_new_standard
    ADD stat_date_new VARCHAR(7);

    PRINT N'  ✓ city_168_statistics_new_standard: stat_date_new 字段已添加';
END
ELSE
BEGIN
    PRINT N'  - stat_date_new 字段已存在';
END
GO

-- ====================================================================
-- 步骤3：转换日期格式并填充到新字段
-- ====================================================================
PRINT N'';
PRINT N'步骤3：转换日期格式 (2026-01-01 → 2026-01)...';
GO

-- 省级统计表
UPDATE province_statistics_new_standard
SET stat_date_new = FORMAT(CAST(stat_date AS DATE), 'yyyy-MM')
WHERE stat_date_new IS NULL;

DECLARE @province_count INT;
SELECT @province_count = COUNT(*) FROM province_statistics_new_standard;
PRINT N'  ✓ province_statistics_new_standard: 已转换 ' + CAST(@province_count AS VARCHAR(10)) + N' 条记录';
GO

-- 城市统计表
UPDATE city_168_statistics_new_standard
SET stat_date_new = FORMAT(CAST(stat_date AS DATE), 'yyyy-MM')
WHERE stat_date_new IS NULL;

DECLARE @city_count INT;
SELECT @city_count = COUNT(*) FROM city_168_statistics_new_standard;
PRINT N'  ✓ city_168_statistics_new_standard: 已转换 ' + CAST(@city_count AS VARCHAR(10)) + N' 条记录';
GO

-- ====================================================================
-- 步骤4：删除旧字段并重命名新字段
-- ====================================================================
PRINT N'';
PRINT N'步骤4：替换字段 (删除旧 stat_date, 重命名 stat_date_new → stat_date)...';
GO

-- 省级统计表
-- 4.1 删除旧字段的约束（如果存在）
DECLARE @sql NVARCHAR(MAX);
SELECT @sql = 'ALTER TABLE province_statistics_new_standard DROP CONSTRAINT ' + name + ';'
FROM sys.default_constraints
WHERE parent_object_id = OBJECT_ID('province_statistics_new_standard')
AND parent_column_id = (
    SELECT column_id FROM sys.columns
    WHERE object_id = OBJECT_ID('province_statistics_new_standard')
    AND name = 'stat_date'
);

IF @sql IS NOT NULL
BEGIN
    EXEC sp_executesql @sql;
    PRINT N'  ✓ 已删除旧字段的默认约束';
END
GO

-- 4.2 删除旧字段
ALTER TABLE province_statistics_new_standard
DROP COLUMN stat_date;

PRINT N'  ✓ 已删除旧 stat_date 字段';
GO

-- 4.3 重命名新字段
EXEC sp_rename 'province_statistics_new_standard.stat_date_new', 'stat_date', 'COLUMN';

PRINT N'  ✓ stat_date_new 已重命名为 stat_date';
GO

-- 城市统计表
-- 删除旧字段的约束
SELECT @sql = 'ALTER TABLE city_168_statistics_new_standard DROP CONSTRAINT ' + name + ';'
FROM sys.default_constraints
WHERE parent_object_id = OBJECT_ID('city_168_statistics_new_standard')
AND parent_column_id = (
    SELECT column_id FROM sys.columns
    WHERE object_id = OBJECT_ID('city_168_statistics_new_standard')
    AND name = 'stat_date'
);

IF @sql IS NOT NULL
BEGIN
    EXEC sp_executesql @sql;
    PRINT N'  ✓ 已删除旧字段的默认约束';
END
GO

-- 删除旧字段
ALTER TABLE city_168_statistics_new_standard
DROP COLUMN stat_date;

PRINT N'  ✓ 已删除旧 stat_date 字段';
GO

-- 重命名新字段
EXEC sp_rename 'city_168_statistics_new_standard.stat_date_new', 'stat_date', 'COLUMN';

PRINT N'  ✓ stat_date_new 已重命名为 stat_date';
GO

-- ====================================================================
-- 步骤5：验证迁移结果
-- ====================================================================
PRINT N'';
PRINT N'步骤5：验证迁移结果...';
GO

-- 检查省级统计表
SELECT
    stat_date,
    stat_type,
    COUNT(*) as record_count
FROM province_statistics_new_standard
GROUP BY stat_date, stat_type
ORDER BY stat_date DESC, stat_type
;
GO

-- 检查城市统计表
SELECT TOP 5
    stat_date,
    stat_type,
    COUNT(*) as record_count
FROM city_168_statistics_new_standard
GROUP BY stat_date, stat_type
ORDER BY stat_date DESC, stat_type
;
GO

PRINT N'';
PRINT N'============================================================';
PRINT N'✓ 迁移完成！';
PRINT N'  - stat_date 字段类型：VARCHAR(7)';
PRINT N'  - 日期格式：yyyy-MM (如 2026-01)';
PRINT N'============================================================';
GO
