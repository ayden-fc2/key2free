@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "ROOT_DIR=%ROOT_DIR:~0,-1%"

if "%HOST%"=="" set "HOST=127.0.0.1"
if "%BACKEND_PORT%"=="" set "BACKEND_PORT=8000"
if "%FRONTEND_PORT%"=="" set "FRONTEND_PORT=3000"

set "PYTHON_EXE=%ROOT_DIR%\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
  echo Creating Python virtual environment...
  python -m venv "%ROOT_DIR%\.venv"
  if errorlevel 1 (
    echo Failed to create Python virtual environment.
    pause
    exit /b 1
  )
)

echo Installing backend dependencies...
"%PYTHON_EXE%" -m pip install -r "%ROOT_DIR%\backend\requirements.txt"
if errorlevel 1 (
  echo Failed to install backend dependencies.
  pause
  exit /b 1
)

if not exist "%ROOT_DIR%\frontend\node_modules" (
  echo Installing frontend dependencies...
  pushd "%ROOT_DIR%\frontend"
  call npm install
  if errorlevel 1 (
    popd
    echo Failed to install frontend dependencies.
    pause
    exit /b 1
  )
  popd
)

echo.
echo Backend:  http://%HOST%:%BACKEND_PORT%
echo Frontend: http://%HOST%:%FRONTEND_PORT%
echo.
echo Starting backend and frontend with auto reload...

start "A Trading Backend" cmd /k "cd /d "%ROOT_DIR%\backend" && "%PYTHON_EXE%" -m uvicorn app.main:app --host %HOST% --port %BACKEND_PORT% --reload"
start "A Trading Frontend" cmd /k "cd /d "%ROOT_DIR%\frontend" && set "NEXT_PUBLIC_API_BASE_URL=http://%HOST%:%BACKEND_PORT%" && npm run dev -- -H %HOST% -p %FRONTEND_PORT%"

timeout /t 2 /nobreak >nul
start "" "http://%HOST%:%FRONTEND_PORT%"

echo Started. Close the two command windows to stop the services.
pause
