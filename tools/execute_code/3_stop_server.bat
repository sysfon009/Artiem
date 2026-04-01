@echo off
title Stop Gemini Sandbox
echo [INFO] Mematikan server...
docker stop python-sandbox
docker rm python-sandbox

echo.
echo [INFO] Server mati dan container dihapus.
pause