@echo off
setlocal
title Pocket Pikita
cd /d "%~dp0"

REM Prefer the Python installation this project was built with.
set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"

if exist "%PYTHON%" goto launch

where py >nul 2>nul
if not errorlevel 1 (
    py -3.10 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON=py -3.10"
        goto launch
    )
)

where python >nul 2>nul
if not errorlevel 1 (
    set "PYTHON=python"
    goto launch
)

echo Pocket Pikita could not find Python 3.10.
echo Expected: %LOCALAPPDATA%\Programs\Python\Python310\python.exe
echo.
pause
exit /b 1

:launch
%PYTHON% -c "import pygame, OpenGL" >nul 2>nul
if errorlevel 1 (
    echo Pocket Pikita found Python, but a required package is missing.
    echo Run: %PYTHON% -m pip install -r "%~dp0requirements.txt"
    echo.
    pause
    exit /b 1
)

%PYTHON% "%~dp0main.py"
if errorlevel 1 (
    echo.
    echo Pocket Pikita stopped because of the error above.
    pause
)
