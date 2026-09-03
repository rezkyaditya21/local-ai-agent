@echo off
title Building Agent Rust Core
cd /d "%~dp0"
echo ========================================================
echo   BUILDING AGENT RUST CORE (Release Mode)
echo ========================================================
where cargo >nul 2>&1
if %errorlevel% neq 0 (
    echo [Peringatan] Cargo belum terpasang. Menggunakan native high-speed Python fallback bridge.
    exit /b 0
)

cargo build --release
if %errorlevel% equ 0 (
    echo [Sukses] Biner Rust berhasil di-compile ke target\release\agent-rust-core.exe!
    copy /y "target\release\agent-rust-core.exe" "..\agent\tools\agent-rust-core.exe" >nul
) else (
    echo [Gagal] Kompilasi Rust gagal.
)
