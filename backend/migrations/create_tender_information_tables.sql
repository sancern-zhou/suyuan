IF OBJECT_ID('tender_candidates', 'U') IS NULL
BEGIN
    CREATE TABLE tender_candidates (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        title NVARCHAR(500) NOT NULL,
        url NVARCHAR(1000) NOT NULL,
        notice_type NVARCHAR(50) NOT NULL,
        keyword NVARCHAR(100) NULL,
        source NVARCHAR(100) NOT NULL CONSTRAINT DF_tender_candidates_source DEFAULT N'qianlima',
        publish_date DATE NULL,
        raw_list_text NVARCHAR(MAX) NULL,
        metadata_json NVARCHAR(MAX) NOT NULL CONSTRAINT DF_tender_candidates_metadata DEFAULT N'{}',
        filter_status NVARCHAR(30) NOT NULL CONSTRAINT DF_tender_candidates_status DEFAULT N'pending',
        filter_reason NVARCHAR(MAX) NULL,
        filter_confidence FLOAT NULL,
        decision_source NVARCHAR(50) NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT DF_tender_candidates_created_at DEFAULT SYSDATETIME(),
        updated_at DATETIME2 NOT NULL CONSTRAINT DF_tender_candidates_updated_at DEFAULT SYSDATETIME()
    );
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_tender_candidates_url')
    CREATE UNIQUE INDEX UX_tender_candidates_url ON tender_candidates(url);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_tender_candidates_status')
    CREATE INDEX IX_tender_candidates_status ON tender_candidates(filter_status);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_tender_candidates_publish_date')
    CREATE INDEX IX_tender_candidates_publish_date ON tender_candidates(publish_date);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_tender_candidates_keyword')
    CREATE INDEX IX_tender_candidates_keyword ON tender_candidates(keyword);

IF OBJECT_ID('tender_notices', 'U') IS NULL
BEGIN
    CREATE TABLE tender_notices (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        title NVARCHAR(500) NOT NULL,
        url NVARCHAR(1000) NOT NULL,
        notice_type NVARCHAR(50) NOT NULL,
        project_name NVARCHAR(500) NULL,
        purchaser NVARCHAR(300) NULL,
        agency NVARCHAR(300) NULL,
        winning_bidder NVARCHAR(300) NULL,
        budget_amount NVARCHAR(100) NULL,
        budget_amount_wan_yuan DECIMAL(18,4) NULL,
        winning_amount NVARCHAR(100) NULL,
        winning_amount_wan_yuan DECIMAL(18,4) NULL,
        province NVARCHAR(100) NULL,
        city NVARCHAR(100) NULL,
        publish_date DATE NULL,
        bid_open_date NVARCHAR(100) NULL,
        deadline NVARCHAR(100) NULL,
        industry_category NVARCHAR(200) NULL,
        environment_relevance BIT NOT NULL CONSTRAINT DF_tender_notices_relevance DEFAULT 0,
        filter_reason NVARCHAR(MAX) NULL,
        filter_confidence FLOAT NULL,
        raw_content NVARCHAR(MAX) NOT NULL,
        summary NVARCHAR(MAX) NULL,
        key_requirements_json NVARCHAR(MAX) NOT NULL CONSTRAINT DF_tender_notices_requirements DEFAULT N'[]',
        attachment_urls_json NVARCHAR(MAX) NOT NULL CONSTRAINT DF_tender_notices_attachments DEFAULT N'[]',
        structured_json NVARCHAR(MAX) NOT NULL CONSTRAINT DF_tender_notices_structured DEFAULT N'{}',
        created_at DATETIME2 NOT NULL CONSTRAINT DF_tender_notices_created_at DEFAULT SYSDATETIME(),
        updated_at DATETIME2 NOT NULL CONSTRAINT DF_tender_notices_updated_at DEFAULT SYSDATETIME()
    );
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_tender_notices_url')
    CREATE UNIQUE INDEX UX_tender_notices_url ON tender_notices(url);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_tender_notices_publish_date')
    CREATE INDEX IX_tender_notices_publish_date ON tender_notices(publish_date);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_tender_notices_purchaser')
    CREATE INDEX IX_tender_notices_purchaser ON tender_notices(purchaser);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_tender_notices_region')
    CREATE INDEX IX_tender_notices_region ON tender_notices(province, city);

IF OBJECT_ID('tender_fetch_runs', 'U') IS NULL
BEGIN
    CREATE TABLE tender_fetch_runs (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        target_date DATE NOT NULL,
        keywords_json NVARCHAR(MAX) NOT NULL,
        notice_types_json NVARCHAR(MAX) NOT NULL,
        total_candidates INT NOT NULL CONSTRAINT DF_tender_fetch_runs_total DEFAULT 0,
        duplicate_candidates INT NOT NULL CONSTRAINT DF_tender_fetch_runs_duplicates DEFAULT 0,
        filtered_out INT NOT NULL CONSTRAINT DF_tender_fetch_runs_filtered DEFAULT 0,
        detail_fetch_failures INT NOT NULL CONSTRAINT DF_tender_fetch_runs_detail_failures DEFAULT 0,
        saved_notices INT NOT NULL CONSTRAINT DF_tender_fetch_runs_saved DEFAULT 0,
        errors_json NVARCHAR(MAX) NOT NULL CONSTRAINT DF_tender_fetch_runs_errors DEFAULT N'[]',
        status NVARCHAR(30) NOT NULL,
        started_at DATETIME2 NOT NULL CONSTRAINT DF_tender_fetch_runs_started_at DEFAULT SYSDATETIME(),
        finished_at DATETIME2 NULL
    );
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_tender_fetch_runs_target_date')
    CREATE INDEX IX_tender_fetch_runs_target_date ON tender_fetch_runs(target_date);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_tender_fetch_runs_status')
    CREATE INDEX IX_tender_fetch_runs_status ON tender_fetch_runs(status);
