@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo [console] python not found. Install Python 3 and retry.
  pause
  exit /b 1
)

python start_console.py %*
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
  echo.
  echo [console] Exited with code %EXITCODE%.
  echo Port busy?  start-console.cmd 8790
  echo Or:         python start_console.py 8790
  pause
)
exit /b %EXITCODE%
