-- smart_events 列表性能修复（2026-11-12）：表在每分钟 tick 的频繁 UPDATE 下
-- 膨胀到 1.7GB（671 活行 / 22MB 活数据），事件中心列表查询走顺序扫描拖慢全部
-- 轮询（中位 6.3s，峰值 57.6s）。本次已对生产库执行 VACUUM (FULL, ANALYZE)
-- 收回至 ~25MB，并补上与列表排序/过滤列一致的函数索引。本迁移把索引固化，
-- 供干净 schema 重建时保持同款；已有库为幂等可重复执行。
-- Apply after 026 to DATABASE_URL (not SESSION_DATABASE_URL).
BEGIN;
CREATE INDEX IF NOT EXISTS ix_smart_events_effective_time
    ON smart_events ((coalesce(latest_occurrence_time, event_start_time)) DESC NULLS LAST);
COMMIT;
