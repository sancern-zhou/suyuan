-- Separate a knowledge base's visibility from where its rebuildable vector
-- projection lives. Existing indexes were historically hosted in QDRANT_*,
-- which is now the shared store, so the migration is backward compatible.
ALTER TABLE knowledge_bases
    ADD COLUMN IF NOT EXISTS vector_store_scope VARCHAR(16) NOT NULL DEFAULT 'shared';

ALTER TABLE knowledge_bases
    DROP CONSTRAINT IF EXISTS ck_knowledge_bases_vector_store_scope;

ALTER TABLE knowledge_bases
    ADD CONSTRAINT ck_knowledge_bases_vector_store_scope
    CHECK (vector_store_scope IN ('shared', 'local'));

CREATE INDEX IF NOT EXISTS ix_knowledge_bases_vector_store_scope
    ON knowledge_bases(vector_store_scope);
