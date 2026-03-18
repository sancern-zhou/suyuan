-- ============================================
-- 大气污染溯源分析历史记录表
-- 用途：存储完整的分析会话，包括原始数据和分析结果
-- 设计原则：单表存储，使用JSON列存储复杂数据结构
-- ============================================

-- 创建数据库（如果不存在）
IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'AirPollutionAnalysis')
BEGIN
    CREATE DATABASE AirPollutionAnalysis;
END
GO

USE AirPollutionAnalysis;
GO

-- 删除旧表（开发阶段使用，生产环境请注释）
-- DROP TABLE IF EXISTS analysis_history;

-- 创建历史记录表
CREATE TABLE analysis_history (
    -- ========== 主键和标识符 ==========
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL UNIQUE,  -- 会话唯一标识（UUID）

    -- ========== 查询基本信息 ==========
    query_text NVARCHAR(1000) NOT NULL,       -- 用户原始输入
    scale VARCHAR(20) NOT NULL,               -- 'station' 或 'city'

    -- ========== 提取的参数 ==========
    location NVARCHAR(200),                   -- 站点名称或城市名称
    city NVARCHAR(100),                       -- 城市名称（标准化后）
    pollutant VARCHAR(50),                    -- 污染物类型 (O3, PM2.5, PM10, NO2, SO2, CO)
    start_time DATETIME,                      -- 开始时间
    end_time DATETIME,                        -- 结束时间

    -- ========== 原始数据（JSON格式存储） ==========
    -- 气象数据
    meteorological_data NVARCHAR(MAX),        -- 气象数据 {winds: [], temperatures: [], humidity: []}

    -- 监测数据
    monitoring_data NVARCHAR(MAX),            -- 目标站点/城市的监测数据时间序列
    nearby_stations_data NVARCHAR(MAX),       -- 周边站点数据（用于区域对比）

    -- 组分数据
    vocs_data NVARCHAR(MAX),                  -- VOCs组分数据（O3分析使用）
    particulate_data NVARCHAR(MAX),           -- 颗粒物组分数据（PM2.5/PM10分析使用）

    -- 上风向企业数据
    upwind_enterprises NVARCHAR(MAX),         -- 上风向企业列表 [{name, distance, wind_match, ...}]
    upwind_map_url NVARCHAR(500),             -- 上风向地图URL

    -- 站点/区县信息
    station_info NVARCHAR(MAX),               -- 站点详细信息（经纬度、所属区县等）

    -- ========== 分析结果（JSON格式存储） ==========
    -- LLM分析文本
    weather_analysis NVARCHAR(MAX),           -- 气象分析文本
    regional_comparison NVARCHAR(MAX),        -- 区域对比分析文本
    vocs_source_analysis NVARCHAR(MAX),       -- VOCs来源分析文本
    particulate_source_analysis NVARCHAR(MAX),-- 颗粒物来源分析文本
    comprehensive_summary NVARCHAR(MAX),      -- 综合分析文本

    -- KPI指标
    kpi_data NVARCHAR(MAX),                   -- KPI数据 {peak_value, avg_value, exceed_periods, ...}

    -- 可视化配置
    modules_data NVARCHAR(MAX),               -- 前端模块完整配置（地图、图表、文本）

    -- ========== 对话历史 ==========
    chat_messages NVARCHAR(MAX),              -- 对话记录 [{role, content, timestamp}]

    -- ========== 元数据 ==========
    status VARCHAR(20) DEFAULT 'completed',   -- 'completed', 'failed', 'partial'
    error_message NVARCHAR(MAX),              -- 错误信息（如果失败）

    duration_seconds FLOAT,                   -- 分析总耗时（秒）
    api_calls_count INT,                      -- API调用次数
    llm_tokens_used INT,                      -- LLM使用的token数

    -- ========== 用户和权限 ==========
    user_id VARCHAR(100),                     -- 用户标识（可选）
    is_bookmarked BIT DEFAULT 0,              -- 是否收藏
    notes NVARCHAR(500),                      -- 用户备注
    tags NVARCHAR(200),                       -- 标签（逗号分隔）

    -- ========== 时间戳 ==========
    created_at DATETIME DEFAULT GETDATE(),    -- 创建时间
    updated_at DATETIME DEFAULT GETDATE(),    -- 更新时间

    -- ========== 索引优化 ==========
    CONSTRAINT chk_scale CHECK (scale IN ('station', 'city')),
    CONSTRAINT chk_status CHECK (status IN ('completed', 'failed', 'partial'))
);

-- 创建索引以优化查询性能
CREATE INDEX idx_created_at ON analysis_history(created_at DESC);
CREATE INDEX idx_city_pollutant ON analysis_history(city, pollutant);
CREATE INDEX idx_scale_status ON analysis_history(scale, status);
CREATE INDEX idx_user_bookmarked ON analysis_history(user_id, is_bookmarked);
CREATE INDEX idx_session_id ON analysis_history(session_id);

-- 创建全文索引（用于搜索功能）
-- CREATE FULLTEXT CATALOG ft_catalog AS DEFAULT;
-- CREATE FULLTEXT INDEX ON analysis_history(query_text, notes)
--     KEY INDEX PK__analysis__id;

GO

-- ============================================
-- 插入测试数据（可选）
-- ============================================
/*
INSERT INTO analysis_history (
    session_id, query_text, scale, location, city, pollutant,
    start_time, end_time, status
) VALUES (
    'test-session-001',
    '分析广州天河站2025-08-09的O3污染',
    'station',
    '天河站',
    '广州',
    'O3',
    '2025-08-09 00:00:00',
    '2025-08-09 23:59:59',
    'completed'
);
*/

GO

-- ============================================
-- 查询示例
-- ============================================

-- 1. 查询最近的分析记录
-- SELECT TOP 50
--     id, session_id, query_text, city, pollutant, scale,
--     created_at, status
-- FROM analysis_history
-- ORDER BY created_at DESC;

-- 2. 根据城市和污染物筛选
-- SELECT * FROM analysis_history
-- WHERE city = '广州' AND pollutant = 'O3'
-- ORDER BY created_at DESC;

-- 3. 查询收藏的记录
-- SELECT * FROM analysis_history
-- WHERE is_bookmarked = 1
-- ORDER BY created_at DESC;

-- 4. 获取完整的历史记录（用于恢复状态）
-- SELECT * FROM analysis_history
-- WHERE session_id = 'your-session-id';

PRINT '数据库表创建成功！';
PRINT '表名: analysis_history';
PRINT '支持功能: 完整数据存储、快速检索、对话历史恢复';
