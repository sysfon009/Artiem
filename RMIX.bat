@echo off
TITLE RMIX Desktop Application
COLOR 0A
cd /d "%~dp0"

:: --- 1. CHECK & ACTIVATE VENV ---
if not exist "venv\Scripts\activate.bat" (
    echo [INFO] Virtual Environment not found. Creating...
    python -m venv venv
    echo [INFO] Venv created!
    call venv\Scripts\activate
    echo [INFO] Installing Python dependencies...
    python -m pip install --upgrade pip
    if exist requirements.txt (
        pip install -r requirements.txt
    )
    echo [INFO] Installation complete!
) else (
    call venv\Scripts\activate
)
echo.

:: --- 2. CHECK IF PYWEBVIEW IS INSTALLED ---
python -c "import webview" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Installing pywebview...
    pip install pywebview
)

:: --- 3. CHECK IF NODE.JS IS AVAILABLE ---
where npm >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] npm not found! Please install Node.js first.
    echo [WARNING] Download from: https://nodejs.org/
    pause
    exit /b 1
)

:: --- 4. BUILD REACT FRONTEND (if needed) ---
echo [INFO] Checking for UI updates...
python check_frontend.py
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] UI changes detected or missing build. Building React frontend...
    cd frontend
    
    if not exist "node_modules" (
        echo [INFO] Installing npm dependencies...
        call npm install
    )
    
    call npm run build
    cd ..
    echo [INFO] Frontend build complete!
) else (
    echo [INFO] Frontend is up-to-date. Skipping build.
)
echo.

:: --- 5. LAUNCH DESKTOP APP ---
echo ======================================================
echo                  LAUNCHING RMIX
echo           Desktop Application Mode
echo ======================================================
echo.
echo [INFO] Starting application...
echo [INFO] Close the RMIX window to stop the server.
echo.

python launcher.py

:: --- 6. ERROR HANDLING ---
if %ERRORLEVEL% NEQ 0 (
    COLOR 0C
    echo.
    echo [ERROR] Application crashed. Check errors above.
)

pause