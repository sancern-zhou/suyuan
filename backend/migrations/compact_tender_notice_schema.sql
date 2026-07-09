IF OBJECT_ID('tender_notice_contents', 'U') IS NULL
BEGIN
    CREATE TABLE tender_notice_contents (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        url NVARCHAR(1000) NOT NULL,
        raw_content NVARCHAR(MAX) NOT NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT DF_tender_notice_contents_created_at DEFAULT SYSDATETIME(),
        updated_at DATETIME2 NOT NULL CONSTRAINT DF_tender_notice_contents_updated_at DEFAULT SYSDATETIME()
    );
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_tender_notice_contents_url')
    CREATE UNIQUE INDEX UX_tender_notice_contents_url ON tender_notice_contents(url);

IF COL_LENGTH('tender_notices', 'project_category') IS NULL
    ALTER TABLE tender_notices ADD project_category NVARCHAR(200) NULL;

IF COL_LENGTH('tender_notices', 'extraction_meta_json') IS NULL
    ALTER TABLE tender_notices
        ADD extraction_meta_json NVARCHAR(MAX) NOT NULL
            CONSTRAINT DF_tender_notices_extraction_meta DEFAULT N'{}';

IF COL_LENGTH('tender_notices', 'industry_category') IS NOT NULL
BEGIN
    EXEC(N'
        UPDATE tender_notices
        SET project_category = COALESCE(project_category, industry_category)
        WHERE project_category IS NULL
    ');
END;

IF COL_LENGTH('tender_notices', 'raw_content') IS NOT NULL
BEGIN
    EXEC(N'
        INSERT INTO tender_notice_contents (url, raw_content, created_at, updated_at)
        SELECT n.url, n.raw_content, n.created_at, n.updated_at
        FROM tender_notices n
        WHERE NOT EXISTS (
            SELECT 1 FROM tender_notice_contents c WHERE c.url = n.url
        )
    ');
END;

IF COL_LENGTH('tender_notices', 'filter_reason') IS NOT NULL
BEGIN
    EXEC(N'
        UPDATE tender_notices
        SET extraction_meta_json = (
            SELECT
                tender_notices.agency AS agency,
                tender_notices.environment_relevance AS environment_relevance,
                tender_notices.filter_reason AS filter_reason,
                tender_notices.filter_confidence AS filter_confidence,
                JSON_QUERY(COALESCE(tender_notices.attachment_urls_json, N''[]'')) AS attachment_urls
            FOR JSON PATH, WITHOUT_ARRAY_WRAPPER
        )
    ');
END;

DECLARE @drop_constraints_sql NVARCHAR(MAX) = N'';

SELECT @drop_constraints_sql = @drop_constraints_sql + N'ALTER TABLE '
    + QUOTENAME(OBJECT_SCHEMA_NAME(parent_object_id)) + N'.' + QUOTENAME(OBJECT_NAME(parent_object_id))
    + N' DROP CONSTRAINT ' + QUOTENAME(name) + N';'
FROM sys.default_constraints
WHERE parent_object_id = OBJECT_ID('tender_notices')
  AND COL_NAME(parent_object_id, parent_column_id) IN (
      'agency',
      'industry_category',
      'environment_relevance',
      'filter_reason',
      'filter_confidence',
      'raw_content',
      'attachment_urls_json',
      'structured_json'
  );

IF LEN(@drop_constraints_sql) > 0
    EXEC sp_executesql @drop_constraints_sql;

DECLARE @drop_columns_sql NVARCHAR(MAX) = N'ALTER TABLE tender_notices DROP COLUMN ';

SELECT @drop_columns_sql = @drop_columns_sql + QUOTENAME(name) + N','
FROM sys.columns
WHERE object_id = OBJECT_ID('tender_notices')
  AND name IN (
      'agency',
      'industry_category',
      'environment_relevance',
      'filter_reason',
      'filter_confidence',
      'raw_content',
      'attachment_urls_json',
      'structured_json'
  );

IF @drop_columns_sql <> N'ALTER TABLE tender_notices DROP COLUMN '
BEGIN
    SET @drop_columns_sql = LEFT(@drop_columns_sql, LEN(@drop_columns_sql) - 1);
    EXEC sp_executesql @drop_columns_sql;
END;
