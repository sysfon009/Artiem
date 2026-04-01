@echo off
title Build Gemini Sandbox Image
echo [INFO] Sedang membangun Docker Image 'my-code-interpreter'...
echo -----------------------------------------------------------

docker build -t my-code-interpreter .

echo.
echo -----------------------------------------------------------
echo [INFO] Proses Build Selesai.
pause