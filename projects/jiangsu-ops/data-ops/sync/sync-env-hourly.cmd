@echo off
rem Hourly incremental sync of station env hourly shards (integrated_h_<year>_<station>).
rem 每小时第 10 分钟由计划任务 SuyuanJiangsu-sync-env-hourly 调用(独立于 02:30 的 sync-daily,
rem 使智能事件/工单审核的动环证据 ODS 副本滞后从最多 24h 缩到 1h)。
rem sync_env_hourly.py 自带水位增量: 首次自动全量(窗口 >= 2026-10-01), 之后只拉新 id;
rem 单站失败不影响其余站, 汇总退出码供计划任务告警。
cd /d E:\Tools\suyuan-jiangsu\sync
E:\Tools\Python311\python.exe sync_env_hourly.py >> sync_integrated_env_hourly.log 2>&1
exit /b %errorlevel%
