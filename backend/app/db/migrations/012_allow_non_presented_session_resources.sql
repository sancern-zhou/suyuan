-- Ordinary file resources do not require document or visualization presentation data.
ALTER TABLE IF EXISTS session_resources
    ALTER COLUMN logical_key DROP NOT NULL,
    ALTER COLUMN presentation_type DROP NOT NULL,
    ALTER COLUMN presentation DROP NOT NULL;
