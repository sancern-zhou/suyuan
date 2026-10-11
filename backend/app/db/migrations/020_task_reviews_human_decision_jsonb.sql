-- 020: task_reviews.human_decision varchar(64) -> jsonb
--
-- task_review.decide_review() writes a structured decision payload
-- ({version, action, decision, comment, data_impact, intervals_confirmed,
--   actor, occurred_at, ...}) into human_decision, and every consumer reads it
-- as a dict (jiangsu_data_audit_routes.py, jiangsu_fault_work_order_review_rerun.py,
-- jiangsu_smart_event.py). The column was mis-declared varchar(64) in the
-- reconstructed model, so every human decision failed with
-- asyncpg DataError "expected str, got dict" -> POST /decision returned 500
-- and no review could ever be archived in DB mode (72 rows, 0 archived).
--
-- Safe data migration: human_decision IS NULL on every existing row
-- (verified 2026-10-07), because any non-null write would have failed.
ALTER TABLE task_reviews
    ALTER COLUMN human_decision TYPE jsonb USING NULL::jsonb;
