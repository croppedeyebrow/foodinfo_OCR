@echo off
setlocal
cd /d "%~dp0"

where docker >nul 2>&1
if errorlevel 1 (
  echo [console] Docker not found. Install Docker Desktop.
  echo Or with host Python: python start_console.py --local
  pause
  exit /b 1
)

set "HOST_PROJECT_DIR=%CD%"
set "HOST_PROJECT_DIR=%HOST_PROJECT_DIR:\=/%"
set "CONSOLE_PORT=8787"
if not "%~1"=="" if not "%~1:~0,2%"=="--" set "CONSOLE_PORT=%~1"

REM Prefer Python launcher when available (browser open + same CLI flags).
where python >nul 2>&1
if not errorlevel 1 (
  python start_console.py %*
  set "EXITCODE=%ERRORLEVEL%"
  if not "%EXITCODE%"=="0" (
    echo.
    echo [console] Exited with code %EXITCODE%.
    echo Port busy?  start-console.cmd 8790
    pause
  )
  exit /b %EXITCODE%
)

echo.
echo  Pipeline Console (Docker, no host Python)
echo  http://127.0.0.1:%CONSOLE_PORT%
echo  HOST_PROJECT_DIR=%HOST_PROJECT_DIR%
echo  Stop: Ctrl+C
echo.

start "" cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:%CONSOLE_PORT%/"
docker compose up --build console
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
  echo.
  echo [console] Exited with code %EXITCODE%.
  pause
)
exit /b %EXITCODE%
