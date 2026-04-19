-- 快速溯源分析表初始化脚本
-- Quick Trace Analysis Table Initialization Script
-- Database: weather_db
-- Host: 180.184.30.94:5432

-- 创建快速溯源分析结果表
CREATE TABLE IF NOT EXISTS quick_trace_analysis (
    -- Primary key (auto-increment)
    id SERIAL PRIMARY KEY,

    -- Analysis time information
    analysis_date DATE NOT NULL,
    alert_time TIMESTAMP NOT NULL,

    -- Alert information
    pollutant VARCHAR(20) NOT NULL,
    alert_value FLOAT NOT NULL,
    unit VARCHAR(20),

    -- Analysis results
    summary_text TEXT,
    visuals TEXT,  -- JSON格式存储

    -- Execution metadata
    execution_time_seconds FLOAT,
    has_trajectory BOOLEAN,
    warning_message TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT quick_trace_analysis_unique UNIQUE (analysis_date, pollutant, alert_time)
);

-- 创建索引以提高查询性能
CREATE INDEX IF NOT EXISTS idx_quick_trace_analysis_date ON quick_trace_analysis(analysis_date);
CREATE INDEX IF NOT EXISTS idx_quick_trace_analysis_pollutant ON quick_trace_analysis(pollutant);
CREATE INDEX IF NOT EXISTS idx_quick_trace_analysis_alert_time ON quick_trace_analysis(alert_time);
CREATE INDEX IF NOT EXISTS idx_quick_trace_analysis_date_pollutant ON quick_trace_analysis(analysis_date, pollutant);

-- 添加表注释
COMMENT ON TABLE quick_trace_analysis IS '快速溯源分析结果表';
COMMENT ON COLUMN quick_trace_analysis.id IS '主键ID';
COMMENT ON COLUMN quick_trace_analysis.analysis_date IS '分析日期（当天）';
COMMENT ON COLUMN quick_trace_analysis.alert_time IS '告警时间';
COMMENT ON COLUMN quick_trace_analysis.pollutant IS '污染物类型 (PM2.5, PM10, O3, NO2, SO2, CO)';
COMMENT ON COLUMN quick_trace_analysis.alert_value IS '告警浓度值';
COMMENT ON COLUMN quick_trace_analysis.unit IS '浓度单位 (μg/m³, mg/m³)';
COMMENT ON COLUMN quick_trace_analysis.summary_text IS '分析报告（Markdown格式）';
COMMENT ON COLUMN quick_trace_analysis.visuals IS '可视化图表列表（JSON格式）';
COMMENT ON COLUMN quick_trace_analysis.execution_time_seconds IS '执行耗时（秒）';
COMMENT ON COLUMN quick_trace_analysis.has_trajectory IS '是否包含轨迹分析';
COMMENT ON COLUMN quick_trace_analysis.warning_message IS '警告信息';
COMMENT ON COLUMN quick_trace_analysis.created_at IS '记录创建时间';

-- 授权（根据实际用户调整）
-- GRANT SELECT, INSERT, UPDATE ON quick_trace_analysis TO your_app_user;
-- GRANT USAGE, SELECT ON SEQUENCE quick_trace_analysis_id_seq TO your_app_user;

-- 验证表创建
SELECT
    table_name,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'quick_trace_analysis'
ORDER BY ordinal_position;
