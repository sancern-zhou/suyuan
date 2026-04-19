-- 清除所有统计数据（重新计算前执行）
-- 作者：Claude Code
-- 日期：2026-04-18
-- 说明：清除city_168_statistics_new_standard和province_statistics_new_standard表中的所有数据
--
-- 注意：
-- 清除后请运行 manual_update_2026_statistics.py 重新计算数据
-- 新的stat_type命名：
--   - ytd_to_month: 年初到某月累计
--   - month_current: 当月累计（进行中）
--   - year_to_date: 年初至今累计
--   - month_complete: 完整月数据（已结束）

USE XcAiDb;
GO

PRINT '开始清除所有统计数据...';
PRINT '===========================================';

-- 统计删除前的数据量
DECLARE @city_count_before INT;
DECLARE @province_count_before INT;

SELECT @city_count_before = COUNT(*) FROM city_168_statistics_new_standard;
SELECT @province_count_before = COUNT(*) FROM province_statistics_new_standard;

PRINT '删除前数据量：';
PRINT '  城市统计表: ' + CAST(@city_count_before AS VARCHAR) + ' 条';
PRINT '  省级统计表: ' + CAST(@province_count_before AS VARCHAR) + ' 条';
PRINT '===========================================';

-- 删除城市统计数据
PRINT '正在删除城市统计数据...';
DELETE FROM city_168_statistics_new_standard;
PRINT '✓ 城市统计数据已清除';

-- 删除省级统计数据
PRINT '正在删除省级统计数据...';
DELETE FROM province_statistics_new_standard;
PRINT '✓ 省级统计数据已清除';

PRINT '===========================================';

-- 验证删除结果
DECLARE @city_count_after INT;
DECLARE @province_count_after INT;

SELECT @city_count_after = COUNT(*) FROM city_168_statistics_new_standard;
SELECT @province_count_after = COUNT(*) FROM province_statistics_new_standard;

PRINT '删除后数据量：';
PRINT '  城市统计表: ' + CAST(@city_count_after AS VARCHAR) + ' 条';
PRINT '  省级统计表: ' + CAST(@province_count_after AS VARCHAR) + ' 条';

IF @city_count_after = 0 AND @province_count_after = 0
    PRINT '===========================================';
    PRINT '✓ 所有数据已成功清除！';
    PRINT '✓ 现在可以运行 manual_update_2026_statistics.py 重新计算数据';
ELSE
    PRINT '===========================================';
    PRINT '⚠ 警告：数据清除不完全，请检查！';

GO
