@echo off
rem Guangdong data-ops daily job (02:30): master/full reload + daily increments
rem   + reconciliation + DQ gate (dq_check.py -> guangdong_sync.dq_results)
rem Keep this file pure ASCII.

setlocal
set RUNTIME_DIR=%~dp0..
set GD_PYTHON=E:\Tools\Python311\python.exe
set DBT_EXE=E:\Tools\suyuan-guangdong\dbt-venv\Scripts\dbt.exe

cd /d %RUNTIME_DIR%\sync

rem ---- daily_full tables: master data / no reliable incremental column ----
for %%t in (base_station base_device v_cityandregionanddepartment v_supcityandregionanddepartment SYS_USER SYS_DEPARTMENT PW_TASKITEM Sup_Mtc_TaskItem MTC_ORDERTASKITEM SEC_QcBlackOut OPA_DataReceiveRate Alm_Home) do (
    "%GD_PYTHON%" sync_table.py %%t --full >> sync_%%t.log 2>&1
)
rem working_order_details has no update column: full reload catches step status changes
"%GD_PYTHON%" sync_table.py working_order_details --full >> sync_working_order_details.log 2>&1

rem ---- daily incremental: forms/reports/plans (create-time watermarks) ----
for %%t in (PW_TASK RF_W_INSPECTION RF_W_INSPECTIONSUMMARY RF_W_GASEOUSCHECK_SO2 RF_W_GASEOUSCHECK_NOX RF_W_GASEOUSCHECK_CO RF_W_GASEOUSCHECK_O3 RF_W_OTHERDEVICECHECK RF_W_PMCHECK SEC_BlackOutReportDetail SEC_BlackOutReportTimespan QUL_QUALITYDATE Sup_DeviceDayCheck OPA_Performance OPA_STATIONPERFORMANCESCORE) do (
    "%GD_PYTHON%" sync_table.py %%t >> sync_%%t.log 2>&1
)

rem ---- dbt build tag:daily ----
echo [%date% %time%] dbt build tag:daily >> sync_mart.log 2>&1
set "PYTHONUTF8=1"
"%DBT_EXE%" build --project-dir %RUNTIME_DIR%\dbt --profiles-dir %RUNTIME_DIR%\dbt --select tag:daily --no-use-colors >> sync_mart.log 2>&1
echo [%date% %time%] dbt build tag:daily exit=%errorlevel% >> sync_mart.log
if not "%errorlevel%"=="0" exit /b %errorlevel%

rem ---- reconciliation + DQ gate ----
for %%t in (working_orders working_order_details wo_commonfile_links base_station base_device) do (
    "%GD_PYTHON%" sync_table.py %%t --check >> sync_check.log 2>&1
)
"%GD_PYTHON%" dq_check.py >> sync_dq.log 2>&1
echo [%date% %time%] dq exit=%errorlevel% >> sync_dq.log

endlocal
