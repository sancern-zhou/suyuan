CREATE TABLE IF NOT EXISTS exam_questions (
    id VARCHAR(36) PRIMARY KEY,
    question_type VARCHAR(32) NOT NULL,
    topic VARCHAR(255) NOT NULL DEFAULT '',
    knowledge_point_id VARCHAR(64),
    stem TEXT NOT NULL,
    options JSONB NOT NULL DEFAULT '{}'::jsonb,
    correct_answer JSONB NOT NULL,
    scoring_points JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_snapshot TEXT NOT NULL DEFAULT '',
    source_version VARCHAR(100) NOT NULL DEFAULT '',
    explanation_hint TEXT NOT NULL DEFAULT '',
    difficulty VARCHAR(20) NOT NULL DEFAULT 'medium',
    review_status VARCHAR(20) NOT NULL DEFAULT 'draft',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    generated_by VARCHAR(100) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_exam_questions_question_type ON exam_questions(question_type);
CREATE INDEX IF NOT EXISTS ix_exam_questions_topic ON exam_questions(topic);
CREATE INDEX IF NOT EXISTS ix_exam_questions_knowledge_point_id ON exam_questions(knowledge_point_id);
CREATE INDEX IF NOT EXISTS ix_exam_questions_review_status ON exam_questions(review_status);
CREATE INDEX IF NOT EXISTS ix_exam_questions_enabled ON exam_questions(enabled);
CREATE INDEX IF NOT EXISTS ix_exam_questions_published_pool
    ON exam_questions(review_status, enabled, question_type, topic);

CREATE TABLE IF NOT EXISTS exam_practice_runs (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    practice_mode VARCHAR(32) NOT NULL,
    question_types JSONB NOT NULL DEFAULT '[]'::jsonb,
    topics JSONB NOT NULL DEFAULT '[]'::jsonb,
    question_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    target_count INTEGER NOT NULL,
    current_index INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_exam_practice_runs_user_id ON exam_practice_runs(user_id);
CREATE INDEX IF NOT EXISTS ix_exam_practice_runs_status ON exam_practice_runs(status);
CREATE INDEX IF NOT EXISTS ix_exam_practice_runs_user_status
    ON exam_practice_runs(user_id, status, started_at);

CREATE TABLE IF NOT EXISTS exam_attempts (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL REFERENCES exam_practice_runs(id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL,
    question_id VARCHAR(36) NOT NULL REFERENCES exam_questions(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'delivered',
    delivered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    answered_at TIMESTAMPTZ,
    skipped_at TIMESTAMPTZ,
    duration_seconds DOUBLE PRECISION,
    submitted_answer JSONB,
    is_correct BOOLEAN,
    score DOUBLE PRECISION,
    evaluation JSONB NOT NULL DEFAULT '{}'::jsonb,
    attempt_number INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS ix_exam_attempts_run_id ON exam_attempts(run_id);
CREATE INDEX IF NOT EXISTS ix_exam_attempts_user_id ON exam_attempts(user_id);
CREATE INDEX IF NOT EXISTS ix_exam_attempts_question_id ON exam_attempts(question_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_exam_attempts_run_sequence
    ON exam_attempts(run_id, sequence);
CREATE INDEX IF NOT EXISTS ix_exam_attempts_user_question
    ON exam_attempts(user_id, question_id, answered_at);
