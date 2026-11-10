@echo off
rem ============================================================================
rem restart-backend.bat -- restart the suyuan backend pair (web 8000 / worker
rem 8011) with a clean-port gate.
rem
rem Why: on Windows, when a uvicorn master started with --workers 3 is stopped
rem forcefully, its worker children can survive as orphans and keep holding the
rem port. Windows allows rebinding the same port, so an old generation and a new
rem generation end up listening together and requests may hit stale code.
rem
rem Flow per service: net stop (with one retry) -> taskkill any leftover
rem LISTENING pid on the port -> require the port to be free -> net start ->
rem wait for LISTENING -> optional HTTP probe. Any failed step aborts with an
rem explicit error; the script never starts a new generation on top of leftovers.
rem
rem Usage: deploy-local\restart-backend.bat [web|worker|all]    default: all
rem Run from an elevated prompt.
rem ============================================================================

setlocal
set TARGET=%~1
if "%TARGET%"=="" set TARGET=all
if /I not "%TARGET%"=="web" if /I not "%TARGET%"=="worker" if /I not "%TARGET%"=="all" goto :usage
set FAILED=0

if /I "%TARGET%"=="web" call :restart_one suyuan-web 8000 docs
if /I "%TARGET%"=="worker" call :restart_one suyuan-worker 8011 ""
if /I "%TARGET%"=="all" call :restart_one suyuan-web 8000 docs
if /I "%TARGET%"=="all" call :restart_one suyuan-worker 8011 ""

echo.
if "%FAILED%"=="1" (
    echo restart-backend: finished with failures, see [ERROR] lines above.
    endlocal
    exit /b 1
)
echo restart-backend: all done, listeners and health probes passed.
endlocal
exit /b 0

:usage
echo Usage: restart-backend.bat [web^|worker^|all]    default: all
exit /b 2

:restart_one
rem %1 = service name, %2 = port, %3 = HTTP probe path (may be empty)
set SVC=%~1
set PORT=%~2
set HEALTH=%~3
echo === %SVC% : port %PORT% ===

rem -- 1) stop service, retry once on nonzero return --
net stop %SVC% >nul 2>&1
if errorlevel 1 (
    echo net stop returned error, retrying in 8s...
    ping -n 9 127.0.0.1 >nul
    net stop %SVC% >nul 2>&1
)
set /a WAITED=0
:wait_stop
sc query %SVC% | findstr "RUNNING" >nul
if errorlevel 1 goto :stopped
set /a WAITED=WAITED+4
if %WAITED% geq 32 (
    echo [ERROR] %SVC% still RUNNING after net stop retries ^(SCM refused the stop, e.g. error 2189^).
    echo         Stop it from an elevated console session on the server, or reboot at a quiet hour.
    set FAILED=1
    exit /b 1
)
ping -n 5 127.0.0.1 >nul
goto :wait_stop

:stopped
rem -- 2) kill leftover listeners (orphan workers) on the port --
set /a KILLED=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R ":%PORT%[^0-9]" ^| findstr "LISTENING"') do (
    echo   killing leftover listener pid %%p
    taskkill /F /PID %%p >nul 2>&1
    set /a KILLED=KILLED+1
)
if %KILLED% gtr 0 ping -n 4 127.0.0.1 >nul

rem -- 3) require the port to be free --
netstat -ano | findstr /R ":%PORT%[^0-9]" | findstr "LISTENING" >nul
if errorlevel 1 goto :port_free
echo [ERROR] port %PORT% still occupied after taskkill sweep ^(target process stuck at OS level^).
echo         End the python.exe by PID in Task Manager details tab, or reboot at a quiet hour.
echo         Trying to start %SVC% again to restore the previous state...
net start %SVC% >nul 2>&1
set FAILED=1
exit /b 1
:port_free
echo   port %PORT% is free.

rem -- 4) start and wait for the listener --
net start %SVC% >nul 2>&1
set /a WAITED=0
:wait_start
netstat -ano | findstr /R ":%PORT%[^0-9]" | findstr "LISTENING" >nul
if not errorlevel 1 goto :listening
set /a WAITED=WAITED+5
if %WAITED% geq 240 (
    echo [ERROR] %SVC% started but port %PORT% not listening after 240s, see backend\logs\%SVC%.wrapper.log
    set FAILED=1
    exit /b 1
)
ping -n 6 127.0.0.1 >nul
goto :wait_start

:listening
echo   port %PORT% is listening ^(%WAITED%s^).

rem -- 5) HTTP probe --
if "%HEALTH%"=="" goto :health_done
set CODE=
for /f %%c in ('curl -s -o nul -w "%%{http_code}" --max-time 5 http://127.0.0.1:%PORT%/%HEALTH% 2^>nul') do set CODE=%%c
if "%CODE%"=="" (
    echo   [WARN] HTTP probe got no answer ^(curl missing or service still warming up^), relying on the listener.
) else (
    echo   HTTP /%HEALTH% returned %CODE% ^(200/302/401 all count as alive^).
)
:health_done
exit /b 0
