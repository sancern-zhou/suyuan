-- ========================================
-- 168城市统计表迁移：拆分为新旧标准两个表
-- 执行日期：2026-04-09
-- ========================================

USE XcAiDb;
GO

-- ========================================
-- 步骤1：创建新标准表 city_168_statistics_new_standard
-- ========================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'city_168_statistics_new_standard')
BEGIN
    CREATE TABLE dbo.city_168_statistics_new_standard (
        id INT IDENTITY(1,1) PRIMARY KEY,
        stat_date DATE NOT NULL,
        stat_type NVARCHAR(20) NOT NULL,  -- monthly/annual_ytd/current_month
        city_name NVARCHAR(50) NOT NULL,
        city_code INT NULL,

        -- 污染物浓度
        so2_concentration DECIMAL(10,1) NULL,
        no2_concentration DECIMAL(10,1) NULL,
        pm10_concentration DECIMAL(10,1) NULL,
        pm2_5_concentration DECIMAL(10,1) NULL,
        co_concentration DECIMAL(10,2) NULL,
        o3_8h_concentration DECIMAL(10,1) NULL,

        -- 单项质量指数（新标准 HJ 633-2026）
        so2_index DECIMAL(10,3) NULL,
        no2_index DECIMAL(10,3) NULL,
        pm10_index DECIMAL(10,3) NULL,
        pm2_5_index DECIMAL(10,3) NULL,
        co_index DECIMAL(10,3) NULL,
        o3_8h_index DECIMAL(10,3) NULL,

        -- 综合指数（新标准 HJ 633-2026）
        comprehensive_index DECIMAL(10,3) NULL,
        comprehensive_index_rank INT NULL,

        -- 新限值+旧算法（用于对比）
        comprehensive_index_new_limit_old_algo DECIMAL(10,3) NULL,
        comprehensive_index_rank_new_limit_old_algo INT NULL,

        -- 数据质量
        data_days INT NULL,
        sample_coverage DECIMAL(10,2) NULL,

        -- 地理信息
        region NVARCHAR(50) NULL,
        province NVARCHAR(50) NULL,

        -- 标准版本标识
        standard_version NVARCHAR(20) NULL,  -- 'HJ663-2026'

        -- 时间戳
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE()
    );

    PRINT '✅ 创建表 city_168_statistics_new_standard 成功';
END
ELSE
BEGIN
    PRINT '⚠️ 表 city_168_statistics_new_standard 已存在，跳过创建';
END
GO

-- ========================================
-- 步骤2：创建索引
-- ========================================

-- 查询索引（用于快速查询特定城市和类型的数据）
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_city_168_statistics_new_standard_lookup' AND object_id = OBJECT_ID('city_168_statistics_new_standard'))
BEGIN
    CREATE INDEX IX_city_168_statistics_new_standard_lookup
    ON dbo.city_168_statistics_new_standard(stat_type, stat_date, city_name);
    PRINT '✅ 创建索引 IX_city_168_statistics_new_standard_lookup 成功';
END
GO

-- ========================================
-- 步骤3：迁移数据
-- ========================================

-- 迁移数据到新标准表
INSERT INTO dbo.city_168_statistics_new_standard (
    stat_date, stat_type, city_name, city_code,
    so2_concentration, no2_concentration, pm10_concentration, pm2_5_concentration,
    co_concentration, o3_8h_concentration,
    so2_index, no2_index, pm10_index, pm2_5_index, co_index, o3_8h_index,
    comprehensive_index, comprehensive_index_rank,
    comprehensive_index_new_limit_old_algo, comprehensive_index_rank_new_limit_old_algo,
    data_days, sample_coverage, region, province,
    standard_version, created_at, updated_at
)
SELECT
    stat_date, stat_type, city_name, city_code,
    so2_concentration, no2_concentration, pm10_concentration, pm2_5_concentration,
    co_concentration, o3_8h_concentration,
    so2_index, no2_index, pm10_index, pm2_5_index, co_index, o3_8h_index,
    comprehensive_index, comprehensive_index_rank,
    comprehensive_index_new_limit_old_algo, comprehensive_index_rank_new_limit_old_algo,
    data_days, sample_coverage, region, province,
    'HJ663-2026' AS standard_version,  -- 标识为新标准
    created_at, updated_at
FROM dbo.city_168_statistics
WHERE standard_version = 'HJ663-2026';  -- 只迁移新标准数据

PRINT '✅ 数据迁移完成，迁移行数：' + CAST(@@ROWCOUNT AS NVARCHAR(10));
GO

-- ========================================
-- 步骤4：验证数据
-- ========================================

-- 检查新标准表数据量
DECLARE @new_standard_count INT;
DECLARE @old_standard_count INT;

SELECT @new_standard_count = COUNT(*) FROM dbo.city_168_statistics_new_standard;
SELECT @old_standard_count = COUNT(*) FROM dbo.city_168_statistics_old_standard;

PRINT '========================================';
PRINT '数据验证';
PRINT '========================================';
PRINT '新标准表记录数：' + CAST(@new_standard_count AS NVARCHAR(10));
PRINT '旧标准表记录数：' + CAST(@old_standard_count AS NVARCHAR(10));
PRINT '';

-- 检查最新数据
PRINT '新标准表最新数据（前3条）：';
PRINT '========================================';
SELECT TOP 3
    stat_date, stat_type, city_name,
    comprehensive_index, comprehensive_index_rank,
    standard_version
FROM dbo.city_168_statistics_new_standard
ORDER BY stat_date DESC, city_name;
GO

PRINT '';
PRINT '迁移准备完成！请确认数据无误后执行步骤5（删除旧字段）。';
PRINT '执行步骤5前请先备份数据库！';
