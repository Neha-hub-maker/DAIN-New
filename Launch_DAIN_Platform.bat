@echo off
title DAIN PR Platform - Dhaka University
color 0C
echo ======================================================================
echo           DAIN - DUNITE Achievement ^& Impact Network
echo           Official PR Platform for Dhaka University Ecosystem (Light Mode)
echo ======================================================================
echo.
echo Starting clean local server on Port 3000...
echo All assets served from D: drive with Zero node_modules footprint.
echo.
start "" "http://localhost:3000/index.html?v=%RANDOM%"
python -m http.server 3000 --directory "D:\dain_demo"
pause
