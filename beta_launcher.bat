@echo off
setlocal EnableDelayedExpansion
TITLE RMIX Beta Launcher (Browser Mode)
COLOR 0B
cd /d "%~dp0"

echo ======================================================
echo               RMIX BETA BROWSER LAUNCHER
echo                 (Auto-Reload Active)
echo ======================================================
echo.

:: --- 1. CHECK & ACTIVATE VENV ---
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual Environment tidak ditemukan! Silakan jalankan RMIX.bat aslinya terlebih dahulu.
    pause
    exit /b 1
)
call venv\Scripts\activate

:: --- 2. GET LOCAL IP ADDRESS ---
echo [INFO] Aplikasi dapat diakses melalui browser:
echo.
echo    - Di Laptop ini : http://127.0.0.1:8000
echo    - Di HP (1 WiFi): 
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "ipv4"') do (
    set "IP=%%a"
    set "IP=!IP: =!"
    echo                      http://!IP!:8000
)
echo.
echo ======================================================
echo [INFO] Mode Developer (Backend) AKTIF!
echo    - Setiap kali kodingan Python (misal beta_img.py) di-save,
echo      server akan otomatis restart / reload.
echo    - Tutup jendela terminal ini atau tekan CTRL+C untuk berhenti.
echo ======================================================
echo.

:: --- 3. RUN MAIN.PY SECARA DIRECT ---
python main.py

pause
