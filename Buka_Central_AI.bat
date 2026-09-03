@echo off
title Central AI Hub - Local Autonomous Suite
echo =========================================================
echo    MEMBUKA CENTRAL AI HUB - LOCAL AUTONOMOUS SUITE       
echo =========================================================

:: Cek apakah server sudah berjalan di port 7860
netstat -ano | findstr :7860 >nul
if %errorlevel% neq 0 (
    echo [1/2] Menyalakan server lokal di latar belakang...
    cd /d "C:\Users\rezky\Documents\agent\central_hub"
    start /B python server.py >nul 2>&1
    timeout /t 2 /nobreak >nul
) else (
    echo [1/2] Server lokal sudah berjalan aktif!
)

echo [2/2] Membuka antarmuka visual di browser...
start http://localhost:7860

echo.
echo Selesai! Central AI Hub siap digunakan di browser Anda.
echo Jendela ini dapat ditutup kapan saja.
timeout /t 3 >nul
exit
