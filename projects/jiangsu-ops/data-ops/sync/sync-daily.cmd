@echo off
rem Daily job 02:30: dict/full refresh + 字典表SCD2快照 + daily marts + reconciliation + DQ
rem   dbt 化(2026-10-02): dbt snapshot 对 19 张字典/规则表做整行哈希变更留痕
rem   (alm_rule 无更新时间列的问题自此有解: 变更历史查 jiangsu_snapshot.alm_rule)
rem   dbt build tag:daily: dim_device/日概况/质控安排/月度考核/停电宽表(含数据测试)
cd /d E:\Tools\suyuan-jiangsu\sync
set FULLLIST=opa_user_info bsd_device bsd_devicetype qc_task bsd_city qc_arrangeresult qc_historymonthresultoverview pw_task opa_performance_tworate opa_performance_qaqc opa_qcqa_deduction mtc_blackout mtc_dataentry mtc_dataentry_data mtc_fault wo_commonfile log_device qc_backorderarrangelog bsd_supply bsd_moniter_parameter dev_scrap bsd_region bsd_usergroup bsd_usergroup_user bsd_usergroup_station bsd_usergroup_station_devicetype bsd_maintenanceunit mtc_faultcontent mtc_faultcontentitem alm_rule wfl_workflow wfl_workflowtask rf_ruleitem qa_standardmaterialstorage
for %%t in (%FULLLIST%) do (
    E:\Tools\Python311\python.exe sync_table.py %%t --full >> sync_%%t.log 2>&1
)
echo [%date% %time%] dbt snapshot + build tag:daily >> sync_mart.log 2>&1
rem PYTHONUTF8=1: dbt 按 UTF-8 读含中文注释的模型文件(计划任务默认 GBK 会 UnicodeDecodeError)
set "PYTHONUTF8=1"
E:\Tools\suyuan-jiangsu\dbt-venv\Scripts\dbt.exe snapshot --project-dir E:\Tools\suyuan-jiangsu\dbt --profiles-dir E:\Tools\suyuan-jiangsu\dbt --no-use-colors >> sync_mart.log 2>&1
echo [%date% %time%] dbt snapshot exit=%errorlevel% >> sync_mart.log
E:\Tools\suyuan-jiangsu\dbt-venv\Scripts\dbt.exe build --project-dir E:\Tools\suyuan-jiangsu\dbt --profiles-dir E:\Tools\suyuan-jiangsu\dbt --select tag:daily --no-use-colors >> sync_mart.log 2>&1
echo [%date% %time%] dbt build tag:daily exit=%errorlevel% >> sync_mart.log
rem dbt 失败时让计划任务 LastTaskResult 非 0(dq 的 SLA 告警要隔天才发现, 退出码当场可见)
if not "%errorlevel%"=="0" exit /b %errorlevel%
set CHECKLIST=mtc_working_order mtc_working_order_detail alm_summary opa_kq_attendance bsd_station mot_alarm opa_user_info bsd_device bsd_devicetype qc_task bsd_city qc_historyresult qc_arrangeresult qc_historymonthresultoverview pw_taskitem mtc_taskitem pw_task opa_performance_tworate opa_performance_qaqc opa_qcqa_deduction mtc_blackout mtc_dataentry mtc_dataentry_data mtc_fault wo_commonfile log_device qc_backorderarrangelog bsd_supply bsd_moniter_parameter dev_scrap bsd_region bsd_usergroup bsd_usergroup_user bsd_usergroup_station bsd_usergroup_station_devicetype bsd_maintenanceunit mtc_faultcontent mtc_faultcontentitem alm_rule wfl_workflow qa_standardmaterialstorage
for %%t in (%CHECKLIST%) do (
    E:\Tools\Python311\python.exe sync_table.py %%t --check >> sync_check.log 2>&1
)
rem 数据质量检查(新鲜度/空值/同步心跳/契约漂移), 结果落 jiangsu_sync.dq_results
E:\Tools\Python311\python.exe dq_check.py >> sync_dq.log 2>&1
