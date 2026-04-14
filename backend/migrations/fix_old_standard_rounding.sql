-- 修复旧标准表的修约格式问题
-- 执行日期: 2026-04-10
-- 说明: 将旧标准表的浓度字段修改为符合修约规则的数据类型
--   - SO2/NO2/PM10/PM2.5/O3_8h: int (取整)
--   - CO: decimal(4,1) (保留1位小数)

USE XcAiDb;
GO

PRINT '开始修复旧标准表的修约格式...';
PRINT '';

-- =============================================================================
-- 第一步：修复城市旧标准表
-- =============================================================================

PRINT '【1/4】修复 city_168_statistics_old_standard 表...';

-- 1.1 添加临时字段存储修约后的值
ALTER TABLE city_168_statistics_old_standard
ADD so2_concentration_new int NULL;
GO

ALTER TABLE city_168_statistics_old_standard
ADD no2_concentration_new int NULL;
GO

ALTER TABLE city_168_statistics_old_standard
ADD pm10_concentration_new int NULL;
GO

ALTER TABLE city_168_statistics_old_standard
ADD pm2_5_concentration_new int NULL;
GO

ALTER TABLE city_168_statistics_old_standard
ADD co_concentration_new decimal(4,1) NULL;
GO

ALTER TABLE city_168_statistics_old_standard
ADD o3_8h_concentration_new int NULL;
GO

PRINT '  ✅ 添加临时字段完成';

-- 1.2 修约数据并存储到临时字段
-- SO2: 取整
UPDATE city_168_statistics_old_standard
SET so2_concentration_new = CAST(so2_concentration AS INT)
WHERE so2_concentration IS NOT NULL;
GO

-- NO2: 取整
UPDATE city_168_statistics_old_standard
SET no2_concentration_new = CAST(no2_concentration AS INT)
WHERE no2_concentration IS NOT NULL;
GO

-- PM10: 取整
UPDATE city_168_statistics_old_standard
SET pm10_concentration_new = CAST(pm10_concentration AS INT)
WHERE pm10_concentration IS NOT NULL;
GO

-- PM2.5: 取整
UPDATE city_168_statistics_old_standard
SET pm2_5_concentration_new = CAST(pm2_5_concentration AS INT)
WHERE pm2_5_concentration IS NOT NULL;
GO

-- CO: 保留1位小数
UPDATE city_168_statistics_old_standard
SET co_concentration_new = CAST(co_concentration AS DECIMAL(4,1))
WHERE co_concentration IS NOT NULL;
GO

-- O3_8h: 取整
UPDATE city_168_statistics_old_standard
SET o3_8h_concentration_new = CAST(o3_8h_concentration AS INT)
WHERE o3_8h_concentration IS NOT NULL;
GO

PRINT '  ✅ 数据修约完成';

-- 1.3 删除旧字段
ALTER TABLE city_168_statistics_old_standard
DROP COLUMN so2_concentration;
GO

ALTER TABLE city_168_statistics_old_standard
DROP COLUMN no2_concentration;
GO

ALTER TABLE city_168_statistics_old_standard
DROP COLUMN pm10_concentration;
GO

ALTER TABLE city_168_statistics_old_standard
DROP COLUMN pm2_5_concentration;
GO

ALTER TABLE city_168_statistics_old_standard
DROP COLUMN co_concentration;
GO

ALTER TABLE city_168_statistics_old_standard
DROP COLUMN o3_8h_concentration;
GO

PRINT '  ✅ 删除旧字段完成';

-- 1.4 重命名新字段
EXEC sp_rename 'city_168_statistics_old_standard.so2_concentration_new', 'so2_concentration', 'COLUMN';
GO

EXEC sp_rename 'city_168_statistics_old_standard.no2_concentration_new', 'no2_concentration', 'COLUMN';
GO

EXEC sp_rename 'city_168_statistics_old_standard.pm10_concentration_new', 'pm10_concentration', 'COLUMN';
GO

EXEC sp_rename 'city_168_statistics_old_standard.pm2_5_concentration_new', 'pm2_5_concentration', 'COLUMN';
GO

EXEC sp_rename 'city_168_statistics_old_standard.co_concentration_new', 'co_concentration', 'COLUMN';
GO

EXEC sp_rename 'city_168_statistics_old_standard.o3_8h_concentration_new', 'o3_8h_concentration', 'COLUMN';
GO

PRINT '  ✅ 字段重命名完成';

PRINT '';
PRINT '✅ city_168_statistics_old_standard 表修复完成';
PRINT '';

-- =============================================================================
-- 第二步：修复省级旧标准表
-- =============================================================================

PRINT '【2/4】修复 province_statistics_old_standard 表...';

-- 2.1 添加临时字段
ALTER TABLE province_statistics_old_standard
ADD so2_concentration_new int NULL;
GO

ALTER TABLE province_statistics_old_standard
ADD no2_concentration_new int NULL;
GO

ALTER TABLE province_statistics_old_standard
ADD pm10_concentration_new int NULL;
GO

ALTER TABLE province_statistics_old_standard
ADD pm2_5_concentration_new int NULL;
GO

ALTER TABLE province_statistics_old_standard
ADD co_concentration_new decimal(4,1) NULL;
GO

ALTER TABLE province_statistics_old_standard
ADD o3_8h_concentration_new int NULL;
GO

PRINT '  ✅ 添加临时字段完成';

-- 2.2 修约数据
UPDATE province_statistics_old_standard
SET so2_concentration_new = CAST(so2_concentration AS INT)
WHERE so2_concentration IS NOT NULL;
GO

UPDATE province_statistics_old_standard
SET no2_concentration_new = CAST(no2_concentration AS INT)
WHERE no2_concentration IS NOT NULL;
GO

UPDATE province_statistics_old_standard
SET pm10_concentration_new = CAST(pm10_concentration AS INT)
WHERE pm10_concentration IS NOT NULL;
GO

UPDATE province_statistics_old_standard
SET pm2_5_concentration_new = CAST(pm2_5_concentration AS INT)
WHERE pm2_5_concentration IS NOT NULL;
GO

UPDATE province_statistics_old_standard
SET co_concentration_new = CAST(co_concentration AS DECIMAL(4,1))
WHERE co_concentration IS NOT NULL;
GO

UPDATE province_statistics_old_standard
SET o3_8h_concentration_new = CAST(o3_8h_concentration AS INT)
WHERE o3_8h_concentration IS NOT NULL;
GO

PRINT '  ✅ 数据修约完成';

-- 2.3 删除旧字段
ALTER TABLE province_statistics_old_standard
DROP COLUMN so2_concentration;
GO

ALTER TABLE province_statistics_old_standard
DROP COLUMN no2_concentration;
GO

ALTER TABLE province_statistics_old_standard
DROP COLUMN pm10_concentration;
GO

ALTER TABLE province_statistics_old_standard
DROP COLUMN pm2_5_concentration;
GO

ALTER TABLE province_statistics_old_standard
DROP COLUMN co_concentration;
GO

ALTER TABLE province_statistics_old_standard
DROP COLUMN o3_8h_concentration;
GO

PRINT '  ✅ 删除旧字段完成';

-- 2.4 重命名新字段
EXEC sp_rename 'province_statistics_old_standard.so2_concentration_new', 'so2_concentration', 'COLUMN';
GO

EXEC sp_rename 'province_statistics_old_standard.no2_concentration_new', 'no2_concentration', 'COLUMN';
GO

EXEC sp_rename 'province_statistics_old_standard.pm10_concentration_new', 'pm10_concentration', 'COLUMN';
GO

EXEC sp_rename 'province_statistics_old_standard.pm2_5_concentration_new', 'pm2_5_concentration', 'COLUMN';
GO

EXEC sp_rename 'province_statistics_old_standard.co_concentration_new', 'co_concentration', 'COLUMN';
GO

EXEC sp_rename 'province_statistics_old_standard.o3_8h_concentration_new', 'o3_8h_concentration', 'COLUMN';
GO

PRINT '  ✅ 字段重命名完成';

PRINT '';
PRINT '✅ province_statistics_old_standard 表修复完成';
PRINT '';

-- =============================================================================
-- 第三步：验证修复结果
-- =============================================================================

PRINT '【3/4】验证修复结果...';
PRINT '';

-- 查看城市旧标准表的结构
PRINT 'city_168_statistics_old_standard 表结构:';
PRINT '-----------------------------------------------------------------------------';
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    NUMERIC_PRECISION,
    NUMERIC_SCALE,
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'city_168_statistics_old_standard'
  AND COLUMN_NAME IN ('so2_concentration', 'no2_concentration', 'pm10_concentration',
                      'pm2_5_concentration', 'co_concentration', 'o3_8h_concentration')
ORDER BY ORDINAL_POSITION;
GO

PRINT '';
PRINT '示例数据（城市旧标准表，前3条）:';
PRINT '-----------------------------------------------------------------------------';
SELECT TOP 3
    city_name,
    so2_concentration,
    no2_concentration,
    pm10_concentration,
    pm2_5_concentration,
    co_concentration,
    o3_8h_concentration,
    stat_date
FROM city_168_statistics_old_standard
WHERE stat_date LIKE '2025%'
ORDER BY stat_date DESC, city_name;
GO

PRINT '';
PRINT '示例数据（省级旧标准表，前3条）:';
PRINT '-----------------------------------------------------------------------------';
SELECT TOP 3
    province_name,
    so2_concentration,
    no2_concentration,
    pm10_concentration,
    pm2_5_concentration,
    co_concentration,
    o3_8h_concentration,
    stat_date
FROM province_statistics_old_standard
WHERE stat_date LIKE '2025%'
ORDER BY stat_date DESC, province_name;
GO

PRINT '';
PRINT '✅ 验证完成';
PRINT '';

-- =============================================================================
-- 第四步：总结
-- =============================================================================

PRINT '';
PRINT '================================================================================';
PRINT '✅ 旧标准表修约格式修复完成！';
PRINT '================================================================================';
PRINT '';
PRINT '修改内容:';
PRINT '  1. city_168_statistics_old_standard 表';
PRINT '     - SO2/NO2/PM10/PM2.5/O3_8h: decimal(10,1) -> int (取整)';
PRINT '     - CO: decimal(10,2) -> decimal(4,1) (保留1位小数)';
PRINT '';
PRINT '  2. province_statistics_old_standard 表';
PRINT '     - SO2/NO2/PM10/PM2.5/O3_8h: decimal(10,1) -> int (取整)';
PRINT '     - CO: decimal(10,2) -> decimal(4,1) (保留1位小数)';
PRINT '';
PRINT '下一步: 更新 fetcher 代码中的字段定义';
PRINT '  - app/fetchers/city_statistics/city_statistics_old_standard_fetcher.py';
PRINT '  - app/fetchers/city_statistics/province_statistics_old_standard_fetcher.py';
PRINT '================================================================================';
GO
