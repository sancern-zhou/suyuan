-- ============================================
-- 大气污染溯源分析系统 - 历史记录数据库初始化脚本
-- Database: AirPollutionAnalysis
-- Server: 180.184.30.94
-- Description: 完整的数据库和表结构创建脚本，可直接执行
-- Version: 1.0
-- Date: 2025-10-23
-- ============================================

SET NOCOUNT ON;
GO

-- ============================================
-- 第一步：创建数据库（如果不存在）
-- ============================================
PRINT '========================================';
PRINT '正在检查数据库是否存在...';
PRINT '========================================';

IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'AirPollutionAnalysis')
BEGIN
    PRINT '数据库不存在，正在创建 AirPollutionAnalysis...';
    CREATE DATABASE AirPollutionAnalysis
        COLLATE Chinese_PRC_CI_AS;  -- 使用中文排序规则
    PRINT '✓ 数据库创建成功';
END
ELSE
BEGIN
    PRINT '✓ 数据库已存在';
END
GO

-- 切换到目标数据库
USE AirPollutionAnalysis;
GO

PRINT '';
PRINT '========================================';
PRINT '当前使用数据库: AirPollutionAnalysis';
PRINT '========================================';
GO

-- ============================================
-- 第二步：删除旧表（可选，生产环境请注释掉）
-- ============================================
/*
PRINT '';
PRINT '警告: 正在删除旧表...';
IF OBJECT_ID('dbo.analysis_history', 'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.analysis_history;
    PRINT '✓ 旧表已删除';
END
*/

-- ============================================
-- 第三步：创建历史记录表
-- ============================================
PRINT '';
PRINT '========================================';
PRINT '正在创建 analysis_history 表...';
PRINT '========================================';

IF OBJECT_ID('dbo.analysis_history', 'U') IS NOT NULL
BEGIN
    PRINT '× 表已存在，跳过创建';
    PRINT '  如需重建表，请手动执行: DROP TABLE dbo.analysis_history;';
END
ELSE
BEGIN
    CREATE TABLE dbo.analysis_history (
        -- ========== 主键和标识符 ==========
        id BIGINT IDENTITY(1,1) PRIMARY KEY,
        session_id VARCHAR(100) NOT NULL,

        -- ========== 查询基本信息 ==========
        query_text NVARCHAR(1000) NOT NULL,       -- 用户原始查询文本
        scale VARCHAR(20) NOT NULL,               -- 分析维度: 'station' 或 'city'

        -- ========== 提取的参数 ==========
        location NVARCHAR(200),                   -- 站点名称（站点级别）
        city NVARCHAR(100),                       -- 城市名称（标准化后）
        pollutant VARCHAR(50),                    -- 污染物类型 (O3, PM2.5, PM10, NO2, SO2, CO)
        start_time DATETIME,                      -- 分析开始时间
        end_time DATETIME,                        -- 分析结束时间

        -- ========== 原始数据（JSON格式） ==========
        -- 气象数据
        meteorological_data NVARCHAR(MAX),        -- 气象数据（风速、风向、温度、湿度等）

        -- 监测数据
        monitoring_data NVARCHAR(MAX),            -- 目标站点/城市的监测数据时间序列
        nearby_stations_data NVARCHAR(MAX),       -- 周边站点数据（用于区域对比分析）

        -- 组分数据
        vocs_data NVARCHAR(MAX),                  -- VOCs组分数据（O3污染分析使用）
        particulate_data NVARCHAR(MAX),           -- 颗粒物组分数据（PM2.5/PM10分析使用）

        -- 上风向企业数据
        upwind_enterprises NVARCHAR(MAX),         -- 上风向企业列表（包括企业名称、行业、排放量、距离等）
        upwind_map_url NVARCHAR(500),             -- 高德地图静态图URL

        -- 站点/区县信息
        station_info NVARCHAR(MAX),               -- 站点详细信息（经纬度、所属区县、地址等）

        -- ========== 分析结果（文本+JSON） ==========
        -- LLM生成的分析文本
        weather_analysis NVARCHAR(MAX),           -- 气象条件分析
        regional_comparison NVARCHAR(MAX),        -- 区域对比分析（站点间或城市间）
        vocs_source_analysis NVARCHAR(MAX),       -- VOCs来源溯源分析
        particulate_source_analysis NVARCHAR(MAX),-- 颗粒物来源溯源分析
        comprehensive_summary NVARCHAR(MAX),      -- 综合分析总结

        -- KPI指标
        kpi_data NVARCHAR(MAX),                   -- KPI摘要（峰值、均值、超标时段等）

        -- 前端模块数据
        modules_data NVARCHAR(MAX),               -- 前端完整模块配置（图表、地图、文本面板）

        -- ========== 对话历史 ==========
        chat_messages NVARCHAR(MAX),              -- AI对话记录（支持对话恢复）

        -- ========== 执行元数据 ==========
        status VARCHAR(20) DEFAULT 'completed',   -- 执行状态: 'completed', 'failed', 'partial'
        error_message NVARCHAR(MAX),              -- 错误信息（失败时记录）
        duration_seconds FLOAT,                   -- 分析总耗时（秒）
        api_calls_count INT,                      -- 外部API调用次数
        llm_tokens_used INT,                      -- LLM消耗的token数

        -- ========== 用户管理 ==========
        user_id VARCHAR(100),                     -- 用户标识（预留字段）
        is_bookmarked BIT DEFAULT 0,              -- 是否收藏
        notes NVARCHAR(500),                      -- 用户备注
        tags NVARCHAR(200),                       -- 标签（逗号分隔）

        -- ========== 时间戳 ==========
        created_at DATETIME DEFAULT GETDATE(),    -- 创建时间
        updated_at DATETIME DEFAULT GETDATE(),    -- 最后更新时间

        -- ========== 约束 ==========
        CONSTRAINT chk_scale CHECK (scale IN ('station', 'city')),
        CONSTRAINT chk_status CHECK (status IN ('completed', 'failed', 'partial')),
        CONSTRAINT uq_session_id UNIQUE (session_id)
    );

    PRINT '✓ 表创建成功';
END
GO

-- ============================================
-- 第四步：创建索引以优化查询性能
-- ============================================
PRINT '';
PRINT '========================================';
PRINT '正在创建索引...';
PRINT '========================================';

-- 时间排序索引（最常用）
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_created_at' AND object_id = OBJECT_ID('dbo.analysis_history'))
BEGIN
    CREATE INDEX idx_created_at ON dbo.analysis_history(created_at DESC);
    PRINT '✓ 创建索引: idx_created_at';
END

-- 城市+污染物复合索引（筛选查询）
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_city_pollutant' AND object_id = OBJECT_ID('dbo.analysis_history'))
BEGIN
    CREATE INDEX idx_city_pollutant ON dbo.analysis_history(city, pollutant);
    PRINT '✓ 创建索引: idx_city_pollutant';
END

-- 维度+状态索引
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_scale_status' AND object_id = OBJECT_ID('dbo.analysis_history'))
BEGIN
    CREATE INDEX idx_scale_status ON dbo.analysis_history(scale, status);
    PRINT '✓ 创建索引: idx_scale_status';
END

-- 用户+收藏索引
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_user_bookmarked' AND object_id = OBJECT_ID('dbo.analysis_history'))
BEGIN
    CREATE INDEX idx_user_bookmarked ON dbo.analysis_history(user_id, is_bookmarked);
    PRINT '✓ 创建索引: idx_user_bookmarked';
END

-- Session ID索引（虽然有唯一约束，但显式创建索引提升性能）
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_session_id' AND object_id = OBJECT_ID('dbo.analysis_history'))
BEGIN
    CREATE INDEX idx_session_id ON dbo.analysis_history(session_id);
    PRINT '✓ 创建索引: idx_session_id';
END

GO

-- ============================================
-- 第五步：验证表结构
-- ============================================
PRINT '';
PRINT '========================================';
PRINT '验证表结构...';
PRINT '========================================';

-- 统计列数
DECLARE @column_count INT;
SELECT @column_count = COUNT(*)
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'analysis_history';

PRINT '✓ 表列数: ' + CAST(@column_count AS VARCHAR(10));

-- 统计索引数
DECLARE @index_count INT;
SELECT @index_count = COUNT(*)
FROM sys.indexes
WHERE object_id = OBJECT_ID('dbo.analysis_history')
  AND name IS NOT NULL;

PRINT '✓ 索引数: ' + CAST(@index_count AS VARCHAR(10));

-- 检查约束
DECLARE @constraint_count INT;
SELECT @constraint_count = COUNT(*)
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
WHERE TABLE_NAME = 'analysis_history';

PRINT '✓ 约束数: ' + CAST(@constraint_count AS VARCHAR(10));

GO

-- ============================================
-- 第六步：插入测试数据（可选）
-- ============================================
PRINT '';
PRINT '========================================';
PRINT '插入测试数据（可选）...';
PRINT '========================================';

-- 取消下面的注释以插入测试数据
/*
IF NOT EXISTS (SELECT * FROM dbo.analysis_history WHERE session_id = 'test-session-001')
BEGIN
    INSERT INTO dbo.analysis_history (
        session_id, query_text, scale, location, city, pollutant,
        start_time, end_time, status, duration_seconds
    ) VALUES (
        'test-session-001',
        '分析广州天河站2025-08-09的O3污染',
        'station',
        '天河站',
        '广州',
        'O3',
        '2025-08-09 00:00:00',
        '2025-08-09 23:59:59',
        'completed',
        45.2
    );
    PRINT '✓ 测试数据插入成功';
END
ELSE
BEGIN
    PRINT '○ 测试数据已存在，跳过插入';
END
*/

GO

-- ============================================
-- 第七步：查询表信息（最终确认）
-- ============================================
PRINT '';
PRINT '========================================';
PRINT '数据库初始化完成！';
PRINT '========================================';
PRINT '';
PRINT '表名: dbo.analysis_history';
PRINT '数据库: AirPollutionAnalysis';
PRINT '服务器: 180.184.30.94';
PRINT '';
PRINT '支持功能:';
PRINT '  - 完整数据存储（原始数据 + 分析结果）';
PRINT '  - 快速检索（时间、城市、污染物、维度）';
PRINT '  - 对话历史恢复';
PRINT '  - 收藏和备注管理';
PRINT '';
PRINT '下一步操作:';
PRINT '  1. 配置后端 .env 文件的数据库连接';
PRINT '  2. 安装 Python 依赖: pip install pyodbc aioodbc';
PRINT '  3. 运行测试: python backend/test_history_db.py';
PRINT '';

-- 显示表结构概览
PRINT '表结构概览:';
PRINT '----------------------------------------';

SELECT
    COLUMN_NAME AS '列名',
    DATA_TYPE AS '数据类型',
    CASE
        WHEN CHARACTER_MAXIMUM_LENGTH = -1 THEN 'MAX'
        WHEN CHARACTER_MAXIMUM_LENGTH IS NOT NULL THEN CAST(CHARACTER_MAXIMUM_LENGTH AS VARCHAR(10))
        ELSE '-'
    END AS '长度',
    CASE WHEN IS_NULLABLE = 'YES' THEN '是' ELSE '否' END AS '可为空'
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'analysis_history'
ORDER BY ORDINAL_POSITION;

GO

PRINT '';
PRINT '========================================';
PRINT '脚本执行完成！';
PRINT '========================================';

SET NOCOUNT OFF;
GO
