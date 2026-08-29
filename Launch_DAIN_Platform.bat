@echo off
title DAIN PR Platform - Dhaka University
color 0C
echo ======================================================================
echo           DAIN - DUNITE Achievement ^& Impact Network
echo           Official PR Platform for Dhaka University Ecosystem
echo ======================================================================
echo.
echo Launching DAIN Web Application...
echo Zero node_modules footprint. All assets served on D: drive.
echo.
start "" "http://localhost:3000"
python -m http.server 3000 --directory "D:\dain_demo"
pause
