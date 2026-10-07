@echo off
rem Incremental sync + mart refresh (runs every 5 min)
rem 顺序: ODS 增量 -> dbt build tag:frequent
rem   mart 层已 dbt 化(2026-10-02): dim_station + 工单/告警/站点健康/质控执行/巡检宽表
rem   dbt 负责依赖排序/原子换名重建(无空窗)/数据测试/自动 GRANT agent_reader
rem   原 psql 脚本已归档至 legacy-sql\; 抽数(SQL Server->ODS)仍由 sync_table.py 负责
rem   rf_common: 非故障工单表单体(rFCommon 矩阵), 供 ops_audit DB 取数
cd /d E:\Tools\suyuan-jiangsu\sync
for %%t in (mtc_working_order mtc_working_order_detail alm_summary opa_kq_attendance bsd_station mot_alarm qc_historyresult pw_taskitem mtc_taskitem rf_common) do (
    E:\Tools\Python311\python.exe sync_table.py %%t >> sync_%%t.log 2>&1
)
echo [%date% %time%] dbt build tag:frequent >> sync_mart.log 2>&1
rem PYTHONUTF8=1: dbt 按 UTF-8 读含中文注释的模型文件(计划任务默认 GBK 会 UnicodeDecodeError)
set "PYTHONUTF8=1"
E:\Tools\suyuan-jiangsu\dbt-venv\Scripts\dbt.exe build --project-dir E:\Tools\suyuan-jiangsu\dbt --profiles-dir E:\Tools\suyuan-jiangsu\dbt --select tag:frequent --no-use-colors >> sync_mart.log 2>&1
