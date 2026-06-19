@echo off
title AutoDNA Coder
cd /d "%~dp0"

echo ============================================
echo   AutoDNA Coder - Starting...
echo ============================================
echo.

:: Clear Python cache
if exist __pycache__ rmdir /s /q __pycache__

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python tidak ditemukan. Install Python 3.11+ dulu.
    pause
    exit /b 1
)

:: Install dependencies if needed
if not exist ".deps_installed" (
    echo Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Gagal install dependencies.
        pause
        exit /b 1
    )
    echo. > .deps_installed
    echo Dependencies installed.
    echo.
)

:: Create folders
if not exist input mkdir input
if not exist output mkdir output
if not exist autosave mkdir autosave
if not exist exports mkdir exports
if not exist projects mkdir projects

echo Starting Streamlit...
echo.
echo   App: http://localhost:8501
echo   Tekan Ctrl+C untuk stop
echo.
python -m streamlit run app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false
pause
