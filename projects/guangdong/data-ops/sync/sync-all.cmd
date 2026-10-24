@echo off
rem Guangdong data-ops frequent job (hourly): ODS incremental + dbt build tag:frequent
rem Chain: Operation_SC_GD --(sync_table.py)--> guangdong_ods --(dbt)--> guangdong_mart
rem Keep this file pure ASCII (GBK codepage consoles break on UTF-8 comments).

setlocal
set RUNTIME_DIR=%~dp0..
set GD_PYTHON=E:\Tools\Python311\python.exe
set DBT_EXE=E:\Tools\suyuan-guangdong\dbt-venv\Scripts\dbt.exe

cd /d %RUNTIME_DIR%\sync

rem ---- ODS incremental: work-order chain + alarms/lifecycle/task items/form bodies ----
for %%t in (working_orders working_order_details wo_commonfile_links ALM_ALARM LOG_DEVICE Sup_RF_Common) do (
    "%GD_PYTHON%" sync_table.py %%t >> sync_%%t.log 2>&1
)

rem ---- dbt build tag:frequent (atomic rename rebuild, tests, grants) ----
echo [%date% %time%] dbt build tag:frequent >> sync_mart.log 2>&1
set "PYTHONUTF8=1"
"%DBT_EXE%" build --project-dir %RUNTIME_DIR%\dbt --profiles-dir %RUNTIME_DIR%\dbt --select tag:frequent --no-use-colors >> sync_mart.log 2>&1

endlocal
