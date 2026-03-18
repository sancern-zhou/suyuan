-- Simple table creation script (no validation, direct creation)
-- Database: AirPollutionAnalysis
-- Table: analysis_history

USE AirPollutionAnalysis;
GO

-- Drop table if exists (for clean reinstall)
IF OBJECT_ID('dbo.analysis_history', 'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.analysis_history;
    PRINT 'Old table dropped';
END
GO

-- Create table
CREATE TABLE dbo.analysis_history (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL UNIQUE,

    query_text NVARCHAR(1000) NOT NULL,
    scale VARCHAR(20) NOT NULL,

    location NVARCHAR(200),
    city NVARCHAR(100),
    pollutant VARCHAR(50),
    start_time DATETIME,
    end_time DATETIME,

    meteorological_data NVARCHAR(MAX),
    monitoring_data NVARCHAR(MAX),
    nearby_stations_data NVARCHAR(MAX),
    vocs_data NVARCHAR(MAX),
    particulate_data NVARCHAR(MAX),
    upwind_enterprises NVARCHAR(MAX),
    upwind_map_url NVARCHAR(500),
    station_info NVARCHAR(MAX),

    weather_analysis NVARCHAR(MAX),
    regional_comparison NVARCHAR(MAX),
    vocs_source_analysis NVARCHAR(MAX),
    particulate_source_analysis NVARCHAR(MAX),
    comprehensive_summary NVARCHAR(MAX),
    kpi_data NVARCHAR(MAX),
    modules_data NVARCHAR(MAX),

    chat_messages NVARCHAR(MAX),

    status VARCHAR(20) DEFAULT 'completed',
    error_message NVARCHAR(MAX),
    duration_seconds FLOAT,
    api_calls_count INT,
    llm_tokens_used INT,

    user_id VARCHAR(100),
    is_bookmarked BIT DEFAULT 0,
    notes NVARCHAR(500),
    tags NVARCHAR(200),

    created_at DATETIME DEFAULT GETDATE(),
    updated_at DATETIME DEFAULT GETDATE(),

    CONSTRAINT chk_scale CHECK (scale IN ('station', 'city')),
    CONSTRAINT chk_status CHECK (status IN ('completed', 'failed', 'partial'))
);

PRINT 'Table created successfully';
GO

-- Create indexes
CREATE INDEX idx_created_at ON dbo.analysis_history(created_at DESC);
CREATE INDEX idx_city_pollutant ON dbo.analysis_history(city, pollutant);
CREATE INDEX idx_scale_status ON dbo.analysis_history(scale, status);
CREATE INDEX idx_user_bookmarked ON dbo.analysis_history(user_id, is_bookmarked);
CREATE INDEX idx_session_id ON dbo.analysis_history(session_id);

PRINT 'Indexes created successfully';
GO

PRINT 'All done!';
