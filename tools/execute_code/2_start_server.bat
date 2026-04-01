@echo off
title Start Gemini Sandbox Server
echo [INFO] Membersihkan container lama (jika ada)...
docker stop python-sandbox >nul 2>&1
docker rm python-sandbox >nul 2>&1

echo [INFO] Menyalakan Server Sandbox baru...
docker run -d -p 5000:5000 --name python-sandbox my-code-interpreter

echo.
echo [SUCCESS] Server berjalan! 
echo [INFO] Endpoint: http://localhost:5000/execute
echo.
echo Container ID:
docker ps -f "name=python-sandbox" --format "{{.ID}}"
echo.
pause