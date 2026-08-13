-- Isolate local knowledge-base metadata when project branches share PostgreSQL.
ALTER TABLE knowledge_bases
    ADD COLUMN IF NOT EXISTS local_scope VARCHAR(128);

CREATE INDEX IF NOT EXISTS ix_knowledge_bases_local_scope
    ON knowledge_bases(local_scope);
