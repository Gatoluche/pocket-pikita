@echo off
REM Double-click to launch Pocket Pikita.
cd /d "%~dp0"
python main.py
REM Keep the window open only if something went wrong, so the error is readable.
if errorlevel 1 pause
