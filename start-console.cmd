@echo off
setlocal
cd /d "%~dp0"

where docker >nul 2>&1
if errorlevel 1 (
  echo [console] Docker not found. Install Docker Desktop, or run:
  echo   python start_console.py --local
  pause
  exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
  echo [console] python not found. Falling back to docker compose up console...
  docker compose up --build console
  exit /b %ERRORLEVEL%
)

python start_console.py %*
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
  echo.
  echo [console] Exited with code %EXITCODE%.
  echo Port busy?  start-console.cmd 8790
  echo Local only?  start-console.cmd --local
  pause
)
exit /b %EXITCODE%
