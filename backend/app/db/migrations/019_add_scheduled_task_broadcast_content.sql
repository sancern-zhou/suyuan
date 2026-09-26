ALTER TABLE scheduled_task_results
    ADD COLUMN IF NOT EXISTS broadcast_message TEXT,
    ADD COLUMN IF NOT EXISTS broadcast_image_paths JSONB NOT NULL DEFAULT '[]'::jsonb;
