-- Preserve the same resource once per category while continuing to collapse
-- repeated reads or writes inside that category.
ALTER TABLE session_resources DROP CONSTRAINT IF EXISTS session_resources_pkey;

ALTER TABLE session_resources
    ADD CONSTRAINT session_resources_pkey
    PRIMARY KEY (session_id, resource_key, role);
