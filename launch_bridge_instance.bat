@echo off
REM Bridge Multi-Instance Launch Script
REM This script launches Bridge with custom configuration

echo Bridge Multi-Instance Launcher
echo ================================
echo.

set BRIDGE_EXE=C:\Program Files\Bridge\Bridge.exe

if not exist "%BRIDGE_EXE%" (
    echo ERROR: Bridge.exe not found at %BRIDGE_EXE%
    pause
    exit /b 1
)

echo Choose an instance to launch:
echo.
echo 1. Instance 1 (Port 24981)
echo 2. Instance 2 (Port 24982)
echo 3. Instance 3 (Port 24983)
echo.

set /p choice="Enter choice (1-3): "

if "%choice%"=="1" (
    set INSTANCE_NAME=Instance1
    set USER_DATA_DIR=%LOCALAPPDATA%\Bridge_Instance1
    set PORT=24981
)

if "%choice%"=="2" (
    set INSTANCE_NAME=Instance2
    set USER_DATA_DIR=%LOCALAPPDATA%\Bridge_Instance2
    set PORT=24982
)

if "%choice%"=="3" (
    set INSTANCE_NAME=Instance3
    set USER_DATA_DIR=%LOCALAPPDATA%\Bridge_Instance3
    set PORT=24983
)

echo.
echo Launching Bridge %INSTANCE_NAME%
echo User Data Dir: %USER_DATA_DIR%
echo Target Port: %PORT%
echo.

REM Create user data directory if it doesn't exist
if not exist "%USER_DATA_DIR%" mkdir "%USER_DATA_DIR%"

REM Try different launch methods
echo Method 1: Using --user-data-dir
start "Bridge %INSTANCE_NAME%" "%BRIDGE_EXE%" --user-data-dir="%USER_DATA_DIR%"

REM Uncomment to try other methods:
REM echo Method 2: Using --profile
REM start "Bridge %INSTANCE_NAME%" "%BRIDGE_EXE%" --profile=%INSTANCE_NAME%

REM echo Method 3: Using environment variable
REM set BRIDGE_PORT=%PORT%
REM start "Bridge %INSTANCE_NAME%" "%BRIDGE_EXE%"

echo.
echo Bridge launched! Configure the socket port to %PORT% in the Bridge UI.
echo.
pause
