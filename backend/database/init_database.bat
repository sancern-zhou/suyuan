@echo off
REM ========================================
REM Database Initialization Script
REM For: Air Pollution Analysis System
REM ========================================

set SERVER=180.184.30.94
set USERNAME=sa
set PASSWORD=#Ph981,6J2bOkWYT7p?5slH$I~g_0itR
set DATABASE=AirPollutionAnalysis
set SCRIPT_FILE=init_history_table_complete.sql

echo ========================================
echo Database Initialization Script
echo Air Pollution Analysis System
echo ========================================
echo.

echo Server: %SERVER%
echo Database: %DATABASE%
echo SQL Script: %SCRIPT_FILE%
echo.

echo Checking sqlcmd tool...
where sqlcmd >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] sqlcmd not found!
    echo.
    echo Please install SQL Server Command Line Tools:
    echo https://docs.microsoft.com/en-us/sql/tools/sqlcmd-utility
    echo.
    pause
    exit /b 1
)
echo [OK] sqlcmd is installed
echo.

echo Checking script file...
if not exist "%SCRIPT_FILE%" (
    echo [ERROR] Script file not found: %SCRIPT_FILE%
    echo Please ensure the script file is in the current directory
    pause
    exit /b 1
)
echo [OK] Script file exists
echo.

echo ========================================
echo Starting database initialization...
echo ========================================
echo.

sqlcmd -S %SERVER% -U %USERNAME% -P "%PASSWORD%" -i "%SCRIPT_FILE%" -o init_output.log

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo [SUCCESS] Database initialization completed!
    echo ========================================
    echo.
    echo Log file: init_output.log
    echo.
    echo Next steps:
    echo 1. Check log file for any errors
    echo 2. Configure backend/.env file
    echo 3. Install Python dependencies: pip install pyodbc aioodbc
    echo 4. Run test: python test_database_connection.py
    echo.
    echo ========================================
    echo Log Output:
    echo ========================================
    type init_output.log
) else (
    echo.
    echo ========================================
    echo [FAILED] Database initialization failed!
    echo ========================================
    echo.
    echo Error code: %ERRORLEVEL%
    echo Please check log file: init_output.log
    echo.
    if exist init_output.log (
        echo ========================================
        echo Error Log:
        echo ========================================
        type init_output.log
    )
)

echo.
pause
