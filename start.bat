@echo off
setlocal EnableDelayedExpansion
title IVBS Trading Bot Launcher
color 0A
cd /d "%~dp0"

echo.
echo ============================================================
echo  IVBS -- Institutional Volume Breakout Strategy
echo  Launcher v1.6
echo ============================================================
echo.

:: ============================================================
:: STEP 1: REDIS / MEMURAI
:: ============================================================
echo [1/3] Redis (Memurai) ...

sc query Memurai 2>nul | findstr "RUNNING" >nul 2>&1
if %ERRORLEVEL% EQU 0 goto REDIS_OK_ALREADY

net start Memurai >nul 2>&1
if %ERRORLEVEL% NEQ 0 goto REDIS_START_WARN

timeout /t 2 /nobreak >nul
echo       Memurai service started successfully.
goto REDIS_PING

:REDIS_OK_ALREADY
echo       Already running as Windows service.
goto REDIS_PING

:REDIS_START_WARN
echo.
echo       [INFO] Could not auto-start Memurai service.
echo              This is OK if Memurai is already running.
echo.
echo              If Redis is NOT running, please do one of:
echo                A. Open the Memurai app from the Start menu
echo                B. Run this script as Administrator
echo                C. Run: net start Memurai  (as Administrator)
echo.
echo       Checking if Redis is already reachable anyway...

:REDIS_PING
where redis-cli >nul 2>&1
if %ERRORLEVEL% NEQ 0 goto REDIS_PING_PS

redis-cli -h 127.0.0.1 -p 6379 PING >"%TEMP%\ivbs_redis_ping.txt" 2>&1
findstr /C:"PONG" "%TEMP%\ivbs_redis_ping.txt" >nul 2>&1
if %ERRORLEVEL% EQU 0 goto REDIS_REACHABLE
goto REDIS_PING_PS

:REDIS_PING_PS
powershell -NoProfile -Command "try{$t=New-Object Net.Sockets.TcpClient('127.0.0.1',6379);$t.Close();exit 0}catch{exit 1}" >nul 2>&1
if %ERRORLEVEL% EQU 0 goto REDIS_REACHABLE
goto REDIS_UNREACHABLE

:REDIS_REACHABLE
echo       Redis is reachable at localhost:6379.
echo.
goto VENV_CHECK

:REDIS_UNREACHABLE
echo.
echo [ERROR] Redis is NOT reachable at localhost:6379.
echo.
echo         Redis is required. Please start it:
echo           A. Open the Memurai app from Start menu
echo           B. Run as Administrator: net start Memurai
echo           C. Docker: docker compose up -d redis
echo.
echo         Then run start.bat again.
echo.
pause
exit /b 1

:: ============================================================
:: STEP 2: VIRTUAL ENVIRONMENT
:: ============================================================
:VENV_CHECK
echo [2/3] Virtual environment ...
if not exist ".venv\Scripts\activate.bat" goto VENV_MISSING

call ".venv\Scripts\activate.bat"
echo       Activated: %VIRTUAL_ENV%
echo.
goto STOP_OLD_ENGINE

:VENV_MISSING
echo.
echo [ERROR] Virtual environment not found at .venv\
echo         Create it:  python -m venv .venv
echo         Install:    .venv\Scripts\pip install -r requirements.txt
echo.
pause
exit /b 1

:: ============================================================
:: STEP 2b: STOP ANY ORPHANED PROCESSES FROM PREVIOUS SESSION
::
:: ROOT CAUSE OF engine_autostart_skipped_lock_held:
::   The old bat only killed engine.runner, NOT uvicorn/app.main.
::   The orphaned uvicorn process was still alive, still owned
::   port 8000, and re-set engine:autostart:backend in Redis
::   between our DEL and the new uvicorn starting -- so the new
::   app found the lock already held on its very first startup.
::
:: Fix: kill ALL three layers in order:
::   1. engine.runner  (child worker)
::   2. uvicorn / app.main  (by port 8000 and by cmdline)
::   3. Any stale python.exe with our project path
:: Then clear Redis, then start fresh.
:: ============================================================
:STOP_OLD_ENGINE
echo [2b] Stopping any previous session ...

:: --- Layer 1: Kill engine.runner workers (CimInstance is more reliable than WmiObject) ---
powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*engine.runner*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('      Killed engine.runner PID ' + $_.ProcessId) }"

:: --- Layer 2: Kill whatever process is holding port 8000 (old uvicorn) ---
echo       Releasing port 8000 ...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R "[ :]8000 " ^| findstr "LISTENING"') do (
    if "%%P" NEQ "0" (
        taskkill /F /PID %%P >nul 2>&1
        echo       Killed port-8000 holder PID %%P
    )
)

:: --- Layer 3: Kill any remaining python.exe running app.main or uvicorn in our project ---
powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and ($_.CommandLine -like '*app.main*' -or $_.CommandLine -like '*uvicorn*') -and $_.CommandLine -like '*trading_bot*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('      Killed app.main/uvicorn PID ' + $_.ProcessId) }"

:: --- Wait for OS to fully release port and file handles ---
echo       Waiting for processes to exit cleanly ...
timeout /t 3 /nobreak >nul

:: --- Graceful Redis signal (belt-and-suspenders for any process that survived) ---
redis-cli -h 127.0.0.1 -p 6379 SET engine:control STOP >nul 2>&1
timeout /t 1 /nobreak >nul

:: --- Clear ALL stale Redis keys ---
:: engine:runner:heartbeat   -- orphaned heartbeat blocks autostart check
:: engine:autostart:backend  -- 60s startup lock; if old uvicorn was alive it
::                              may have re-set this AFTER our earlier DEL,
::                              causing engine_autostart_skipped_lock_held
:: engine:status             -- stale ONLINE/STARTING blocks fresh launch
:: engine:control            -- reset to RUN (clear leftover STOP signal)
redis-cli -h 127.0.0.1 -p 6379 DEL engine:runner:heartbeat >nul 2>&1
redis-cli -h 127.0.0.1 -p 6379 DEL engine:autostart:backend >nul 2>&1
redis-cli -h 127.0.0.1 -p 6379 DEL engine:status >nul 2>&1
redis-cli -h 127.0.0.1 -p 6379 SET engine:control RUN >nul 2>&1

echo       All processes killed. Redis state cleared. Ready for fresh start.
echo.

:: --- Confirm port 8000 is free before launching ---
netstat -ano | findstr /R "[ :]8000 " | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo.
    echo [WARNING] Port 8000 is still in use after kill attempts.
    echo           Another process may be holding it.
    echo           Try running this script as Administrator, or
    echo           manually kill the process:
    echo             netstat -ano ^| findstr ":8000"
    echo             taskkill /F /PID ^<pid^>
    echo.
    echo           Attempting to start anyway ^(uvicorn may fail^) ...
    echo.
)

:: ============================================================
:: STEP 3: START BACKEND (uvicorn)
::
:: app.main auto-starts engine.runner via AUTO_START_ENGINE_WITH_BACKEND.
:: It uses Redis heartbeat detection to avoid duplicate launches.
::
:: Morning workflow:
::   1. Double-click start.bat
::   2. Open http://127.0.0.1:8000 in browser
::   3. Click Login to Kite and complete OAuth
::   4. Engine starts automatically -- done!
:: ============================================================
:START_BACKEND
echo ============================================================
echo  Starting backend + engine ...
echo  Dashboard : http://127.0.0.1:8000
echo  API docs  : http://127.0.0.1:8000/docs
echo.
echo  Morning checklist:
echo    1. Wait for "Application startup complete" below
echo    2. Open http://127.0.0.1:8000 in your browser
echo    3. Click the profile icon then Login to Kite
echo    4. Complete Kite OAuth login
echo    5. Engine initialises automatically (watch status pill)
echo.
echo  Press Ctrl+C to stop everything.
echo ============================================================
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

echo.
echo Backend stopped.
pause
