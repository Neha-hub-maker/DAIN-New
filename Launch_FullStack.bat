@echo off
title DAIN Full-Stack (Backend + Frontend) - Dhaka University
color 0A
echo ======================================================================
echo           DAIN - DUNITE Achievement & Impact Network
echo           Full-Stack Platform (FastAPI Backend + Light Mode UI)
echo ======================================================================
echo.
echo [1/2] Starting FastAPI Backend on Port 8000 (SQLite zero-config)...
start "DAIN Backend API" cmd /k "cd /d D:\dain_demo\backend && set PYTHONPATH=D:\dain_demo\backend && uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

echo [2/2] Starting Frontend Web Server on Port 3000...
timeout /t 2 /nobreak >nul
start "" "http://localhost:3000/index.html?v=%RANDOM%"
python -m http.server 3000 --directory "D:\dain_demo"
pause
