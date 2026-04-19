-- 修改统计数据表字段类型
-- 目标：整数字段改为INT，小数字段改为正确的精度
-- 作者：Claude Code
-- 日期：2026-04-18

USE XcAiDb;
GO

PRINT '开始修改字段类型...';
PRINT '===========================================';

-- 修改城市统计表
PRINT '正在修改城市统计表 (city_168_statistics_new_standard)...';

-- 整数字段改为INT
PRINT '  - so2_concentration: decimal(5,2) → INT';
ALTER TABLE city_168_statistics_new_standard
ALTER COLUMN so2_concentration INT;

PRINT '  - no2_concentration: decimal(5,2) → INT';
ALTER TABLE city_168_statistics_new_standard
ALTER COLUMN no2_concentration INT;

PRINT '  - pm10_concentration: decimal(5,2) → INT';
ALTER TABLE city_168_statistics_new_standard
ALTER COLUMN pm10_concentration INT;

PRINT '  - o3_8h_concentration: decimal(5,2) → INT';
ALTER TABLE city_168_statistics_new_standard
ALTER COLUMN o3_8h_concentration INT;

-- 小数字段调整为1位小数
PRINT '  - pm2_5_concentration: decimal(5,2) → decimal(5,1)';
ALTER TABLE city_168_statistics_new_standard
ALTER COLUMN pm2_5_concentration DECIMAL(5,1);

PRINT '  - co_concentration: decimal(6,3) → decimal(5,1)';
ALTER TABLE city_168_statistics_new_standard
ALTER COLUMN co_concentration DECIMAL(5,1);

PRINT '✓ 城市统计表字段类型修改完成';

-- 修改省级统计表
PRINT '';
PRINT '正在修改省级统计表 (province_statistics_new_standard)...';

-- 整数字段改为INT
PRINT '  - so2_concentration: decimal(5,2) → INT';
ALTER TABLE province_statistics_new_standard
ALTER COLUMN so2_concentration INT;

PRINT '  - no2_concentration: decimal(5,2) → INT';
ALTER TABLE province_statistics_new_standard
ALTER COLUMN no2_concentration INT;

PRINT '  - pm10_concentration: decimal(5,2) → INT';
ALTER TABLE province_statistics_new_standard
ALTER COLUMN pm10_concentration INT;

PRINT '  - o3_8h_concentration: decimal(5,2) → INT';
ALTER TABLE province_statistics_new_standard
ALTER COLUMN o3_8h_concentration INT;

-- 小数字段调整为1位小数
PRINT '  - pm2_5_concentration: decimal(5,2) → decimal(5,1)';
ALTER TABLE province_statistics_new_standard
ALTER COLUMN pm2_5_concentration DECIMAL(5,1);

PRINT '  - co_concentration: decimal(6,3) → decimal(5,1)';
ALTER TABLE province_statistics_new_standard
ALTER COLUMN co_concentration DECIMAL(5,1);

PRINT '✓ 省级统计表字段类型修改完成';

PRINT '';
PRINT '===========================================';
PRINT '✓ 所有字段类型修改完成！';
PRINT '';
PRINT '新字段类型：';
PRINT '  - SO2、NO2、PM10、O3-8h: INT';
PRINT '  - PM2.5、CO: DECIMAL(5,1)';
PRINT '';
PRINT '下一步：';
PRINT '  1. 清除所有数据: python clear_all_statistics.py';
PRINT '  2. 重新计算数据: python manual_update_2026_statistics.py';
PRINT '===========================================';

GO
