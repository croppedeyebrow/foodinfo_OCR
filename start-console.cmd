@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM Prefer Python launcher (prompt + Docker Desktop wait + compose).
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

where docker >nul 2>&1
if errorlevel 1 (
  echo [console] Docker not found. Install Docker Desktop.
  echo Or install Python and run: python start_console.py
  pause
  exit /b 1
)

set "HOST_PROJECT_DIR=%CD%"
set "HOST_PROJECT_DIR=%HOST_PROJECT_DIR:\=/%"
set "CONSOLE_PORT=8787"
set "ASSUME_YES="
for %%A in (%*) do (
  if /I "%%~A"=="-y" set "ASSUME_YES=1"
  if /I "%%~A"=="--yes" set "ASSUME_YES=1"
  echo %%~A| findstr /R "^[0-9][0-9]*$" >nul && set "CONSOLE_PORT=%%~A"
)

docker info >nul 2>&1
if not errorlevel 1 goto :run_compose

echo [console] Docker Desktop does not appear to be running.
if defined ASSUME_YES goto :start_desktop
set /p ANSWER=Start Docker Desktop now? [y/N]: 
if /I not "%ANSWER%"=="y" if /I not "%ANSWER%"=="yes" (
  echo [console] Cancelled. Start Docker Desktop manually, then retry.
  pause
  exit /b 1
)

:start_desktop
set "DOCKER_EXE="
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" set "DOCKER_EXE=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
if not defined DOCKER_EXE if exist "%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe" set "DOCKER_EXE=%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe"
if not defined DOCKER_EXE if exist "%LOCALAPPDATA%\Docker\Docker Desktop.exe" set "DOCKER_EXE=%LOCALAPPDATA%\Docker\Docker Desktop.exe"
if not defined DOCKER_EXE (
  echo [console] Docker Desktop.exe not found. Install or start it manually.
  pause
  exit /b 1
)

echo [console] Starting Docker Desktop. Waiting up to 120s...
start "" "%DOCKER_EXE%"

set /a REMAIN=120
:wait_loop
docker info >nul 2>&1
if not errorlevel 1 (
  echo [console] Docker engine is ready.
  goto :run_compose
)
if %REMAIN% LEQ 0 (
  echo [console] Timed out waiting for Docker Desktop.
  echo Open Docker Desktop, wait until Running, then retry.
  pause
  exit /b 1
)
echo [console] Waiting for Docker Desktop engine... (%REMAIN%s left)
timeout /t 3 /nobreak >nul
set /a REMAIN-=3
goto :wait_loop

:run_compose
echo.
echo  Pipeline Console (Docker, no host Python)
echo  http://127.0.0.1:%CONSOLE_PORT%
echo  HOST_PROJECT_DIR=%HOST_PROJECT_DIR%
echo  Stop: Ctrl+C
echo.

start "" cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:%CONSOLE_PORT%/"
set "CONSOLE_PORT=%CONSOLE_PORT%"
docker compose up --build console
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
  echo.
  echo [console] Exited with code %EXITCODE%.
  pause
)
exit /b %EXITCODE%
