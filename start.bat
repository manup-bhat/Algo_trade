@echo off
setlocal EnableDelayedExpansion
title IVBS Trading Bot Launcher
color 0A
cd /d "%~dp0"

:: ---- Configuration (edit if your setup differs) ----
set "REDIS_HOST=127.0.0.1"
set "REDIS_PORT=6379"
set "REDIS_SERVICE=Memurai"
:: API_HOST 127.0.0.1 = localhost only (SAFE default). Change to 0.0.0.0 ONLY on a
:: trusted LAN -- the dashboard has no login and can start/stop trading and place
:: LIVE orders, so exposing it to the network is a real risk.
set "API_HOST=127.0.0.1"
set "API_PORT=8000"

echo.
echo ============================================================
echo  IVBS -- Institutional Volume Breakout Strategy
echo  Launcher v1.6
echo ============================================================
echo.

:: ============================================================
:: STEP 1: REDIS  (auto-detect, then auto-start with fallbacks)
::   reachable? -> Memurai service -> Memurai/redis exe -> Docker -> WSL
:: ============================================================
echo [1/3] Redis ...

call :REDIS_PING_CHECK
if "!REDIS_UP!"=="1" goto REDIS_REACHABLE

echo       Not reachable at %REDIS_HOST%:%REDIS_PORT% -- attempting to start it...

:: Attempt 1: Memurai Windows service (the standard Redis for Windows)
sc query %REDIS_SERVICE% >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo       - net start %REDIS_SERVICE% ...
    net start %REDIS_SERVICE% >nul 2>&1
    call :REDIS_WAIT
    if "!REDIS_UP!"=="1" goto REDIS_REACHABLE
)

:: Attempt 2: Memurai / redis-server executable on PATH
call :REDIS_TRY_EXE memurai-server
if "!REDIS_UP!"=="1" goto REDIS_REACHABLE
call :REDIS_TRY_EXE memurai
if "!REDIS_UP!"=="1" goto REDIS_REACHABLE
call :REDIS_TRY_EXE redis-server
if "!REDIS_UP!"=="1" goto REDIS_REACHABLE

:: Attempt 3: Docker (repo ships docker-compose.yml with a 'redis' service)
where docker >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo       - docker compose up -d redis ...
    docker compose up -d redis >nul 2>&1
    call :REDIS_WAIT
    if "!REDIS_UP!"=="1" goto REDIS_REACHABLE
)

:: Attempt 4: WSL redis-server
where wsl >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo       - wsl redis-server --daemonize yes ...
    wsl -e sh -c "redis-server --daemonize yes" >nul 2>&1
    call :REDIS_WAIT
    if "!REDIS_UP!"=="1" goto REDIS_REACHABLE
)

goto REDIS_UNREACHABLE

:REDIS_REACHABLE
echo       Redis reachable at %REDIS_HOST%:%REDIS_PORT%.
echo.
goto VENV_CHECK

:REDIS_UNREACHABLE
echo.
echo [ERROR] Redis is NOT reachable at %REDIS_HOST%:%REDIS_PORT% and could not be
echo         started automatically. Start it with ONE of:
echo           A. Install + run Memurai   : https://www.memurai.com  (runs as a service)
echo           B. Docker                  : docker compose up -d redis
echo           C. WSL                     : wsl sudo service redis-server start
echo         Some options need this script run as Administrator.
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
python -c "import sys" >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo [ERROR] Python is not runnable inside the venv. Recreate it:
    echo           python -m venv .venv
    echo           .venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
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
echo       Releasing port %API_PORT% ...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R "[ :]%API_PORT% " ^| findstr "LISTENING"') do (
    if "%%P" NEQ "0" (
        taskkill /F /PID %%P >nul 2>&1
        echo       Killed port-8000 holder PID %%P
    )
)

:: --- Layer 3: Kill any remaining python.exe running THIS app (uvicorn app.main:app) ---
::   Match the exact module spec 'app.main:app' so we only kill our own server, not
::   unrelated uvicorn processes. (The old '*trading_bot*' filter never matched this
::   project dir 'Algo_trade-dev', so Layer 3 previously killed nothing.)
powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*app.main:app*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('      Killed app.main PID ' + $_.ProcessId) }"

:: --- Wait for OS to fully release port and file handles ---
echo       Waiting for processes to exit cleanly ...
timeout /t 3 /nobreak >nul

:: --- Clear stale Redis keys via the venv redis client (works even if redis-cli
::     is NOT on PATH, e.g. Redis via Docker/WSL). These stale keys are the root
::     cause of engine_autostart_skipped_lock_held on a fresh launch:
::       engine:runner:heartbeat  -- orphaned heartbeat blocks the autostart check
::       engine:autostart:backend -- 60s startup lock a surviving uvicorn may re-set
::       engine:status            -- stale ONLINE/STARTING blocks a fresh launch
::       engine:control           -- reset to RUN (clear any leftover STOP) ---
python -c "import redis; r=redis.Redis(host='%REDIS_HOST%', port=%REDIS_PORT%, socket_connect_timeout=2); r.delete('engine:runner:heartbeat','engine:autostart:backend','engine:status'); r.set('engine:control','RUN')" >nul 2>&1

echo       All processes killed. Redis state cleared. Ready for fresh start.
echo.

:: --- Confirm port 8000 is free before launching ---
netstat -ano | findstr /R "[ :]%API_PORT% " | findstr "LISTENING" >nul 2>&1
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
python -m uvicorn app.main:app --host %API_HOST% --port %API_PORT%

echo.
echo Backend stopped.
pause
exit /b 0

:: ============================================================
:: SUBROUTINES (Redis detection + readiness)
:: ============================================================
:REDIS_PING_CHECK
:: Sets REDIS_UP=1 if Redis answers PING (or the port is open), else 0.
set "REDIS_UP=0"
where redis-cli >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    for /f "delims=" %%R in ('redis-cli -h %REDIS_HOST% -p %REDIS_PORT% PING 2^>nul') do if /I "%%R"=="PONG" set "REDIS_UP=1"
)
if "!REDIS_UP!"=="1" exit /b 0
powershell -NoProfile -Command "try{$c=New-Object Net.Sockets.TcpClient;$c.Connect('%REDIS_HOST%',[int]'%REDIS_PORT%');$c.Close();exit 0}catch{exit 1}" >nul 2>&1
if !ERRORLEVEL! EQU 0 set "REDIS_UP=1"
exit /b 0

:REDIS_WAIT
:: Poll for readiness up to ~10s (1s between tries). Sets REDIS_UP.
set /a _rtries=0
:REDIS_WAIT_LOOP
call :REDIS_PING_CHECK
if "!REDIS_UP!"=="1" exit /b 0
set /a _rtries+=1
if !_rtries! GEQ 10 exit /b 0
timeout /t 1 /nobreak >nul
goto :REDIS_WAIT_LOOP

:REDIS_TRY_EXE
:: %1 = executable to launch detached, then wait for readiness. No-op if not on PATH.
where %1 >nul 2>&1
if !ERRORLEVEL! NEQ 0 exit /b 0
echo       - launching %1 ...
start "" /b %1 >nul 2>&1
call :REDIS_WAIT
exit /b 0
