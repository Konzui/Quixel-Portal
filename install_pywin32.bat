@echo off
REM Install pywin32 for Blender's Python
REM This enables multi-instance Blender coordination

echo ========================================
echo  Quixel Portal - Install pywin32
echo ========================================
echo.

REM Try Blender 4.4 first
set BLENDER_PYTHON="C:\Program Files\Blender Foundation\Blender 4.4\4.4\python\bin\python.exe"

if exist %BLENDER_PYTHON% (
    echo Found Blender 4.4 Python
    echo Installing pywin32...
    echo.
    %BLENDER_PYTHON% -m pip install pywin32
    goto :success
)

REM Try Blender 4.2
set BLENDER_PYTHON="C:\Program Files\Blender Foundation\Blender 4.2\4.2\python\bin\python.exe"

if exist %BLENDER_PYTHON% (
    echo Found Blender 4.2 Python
    echo Installing pywin32...
    echo.
    %BLENDER_PYTHON% -m pip install pywin32
    goto :success
)

REM Try Blender 4.3
set BLENDER_PYTHON="C:\Program Files\Blender Foundation\Blender 4.3\4.3\python\bin\python.exe"

if exist %BLENDER_PYTHON% (
    echo Found Blender 4.3 Python
    echo Installing pywin32...
    echo.
    %BLENDER_PYTHON% -m pip install pywin32
    goto :success
)

echo ERROR: Could not find Blender Python installation
echo.
echo Please manually run:
echo "C:\Program Files\Blender Foundation\Blender [VERSION]\[VERSION]\python\bin\python.exe" -m pip install pywin32
echo.
pause
exit /b 1

:success
echo.
echo ========================================
echo  Installation Complete!
echo ========================================
echo.
echo pywin32 has been installed successfully.
echo Restart Blender to enable multi-instance coordination.
echo.
pause
