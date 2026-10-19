BEGIN;
CREATE TABLE IF NOT EXISTS conversation_reads (
    session_id VARCHAR(255) NOT NULL,
    owner_user_id VARCHAR(255) NOT NULL,
    through_sequence INTEGER NOT NULL DEFAULT -1,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, owner_user_id)
);
COMMIT;
