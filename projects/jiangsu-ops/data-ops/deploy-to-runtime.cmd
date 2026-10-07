@echo off
rem Sync code from repo (this dir) to server runtime E:\Tools\suyuan-jiangsu.
rem Copy/add only - NEVER deletes runtime files (real credentials, logs, target, node_modules live there).
robocopy "%~dp0dbt"  "E:\Tools\suyuan-jiangsu\dbt"  /E /XD target logs __pycache__ /XF "*.log" ".user.yml" "profiles.yml" /NFL /NDL /NJH /NP
robocopy "%~dp0cube" "E:\Tools\suyuan-jiangsu\cube" /E /XD node_modules /XF "local.json" /NFL /NDL /NJH /NP
robocopy "%~dp0sync" "E:\Tools\suyuan-jiangsu\sync" /E /XD __pycache__ /XF "*.log" "sync_config.json" "sync_config.json.bak_rfcommon" /NFL /NDL /NJH /NP
echo deployed (robocopy exit %ERRORLEVEL%, ^<8 means success). Remember: dbt takes effect next run; cube needs SuyuanJiangsu-Cube restart.
