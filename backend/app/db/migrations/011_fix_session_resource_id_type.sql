ALTER TABLE IF EXISTS session_resources
    ALTER COLUMN resource_id TYPE VARCHAR(64)
    USING resource_id::text;
