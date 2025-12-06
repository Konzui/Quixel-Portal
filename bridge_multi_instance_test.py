"""
Bridge Multi-Instance Configuration Test
=========================================

This script helps us understand:
1. How to launch multiple Bridge instances with different socket ports
2. Where Bridge stores per-instance configuration
3. How to programmatically set the socket port before launching Bridge
"""

import os
import json
import subprocess
import time
from pathlib import Path
import shutil


def print_section(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def find_bridge_config_file():
    """Find where Bridge stores its configuration."""
    print_section("1. FINDING BRIDGE CONFIGURATION FILE")

    possible_config_locations = [
        Path.home() / "AppData" / "Roaming" / "Bridge" / "config.json",
        Path.home() / "AppData" / "Roaming" / "Bridge" / "settings.json",
        Path.home() / "AppData" / "Roaming" / "Bridge" / "preferences.json",
        Path.home() / "AppData" / "Local" / "Bridge" / "config.json",
        Path.home() / "AppData" / "Local" / "Bridge" / "settings.json",
        Path.home() / "AppData" / "Local" / "Bridge" / "preferences.json",
        Path.home() / "AppData" / "Roaming" / "Bridge" / "Local Storage",
        Path.home() / "AppData" / "Local" / "Bridge" / "Local Storage",
    ]

    found_configs = []

    for config_path in possible_config_locations:
        if config_path.exists():
            print(f"✅ Found: {config_path}")
            found_configs.append(config_path)

            # If it's a file, read it
            if config_path.is_file():
                try:
                    content = config_path.read_text(encoding='utf-8', errors='ignore')

                    # Check if it contains socket port info
                    if '24981' in content or 'socket' in content.lower():
                        print(f"   🔍 Contains socket configuration!\n")

                        # Try to parse as JSON
                        if config_path.suffix == '.json':
                            try:
                                data = json.loads(content)
                                print("   Content:")
                                print("   " + "-" * 76)
                                print("   " + json.dumps(data, indent=2).replace('\n', '\n   '))
                                print("   " + "-" * 76)
                            except:
                                print(f"   Raw content (first 1000 chars):")
                                print("   " + content[:1000].replace('\n', '\n   '))
                        else:
                            print(f"   Raw content (first 1000 chars):")
                            print("   " + content[:1000].replace('\n', '\n   '))
                    else:
                        print(f"   (No socket configuration found)\n")
                except Exception as e:
                    print(f"   ⚠️ Could not read: {e}\n")

            # If it's a directory, explore it
            elif config_path.is_dir():
                print(f"   📁 Directory contents:")
                try:
                    for item in config_path.rglob("*"):
                        if item.is_file():
                            rel_path = item.relative_to(config_path)
                            size = item.stat().st_size
                            print(f"      📄 {rel_path} ({size:,} bytes)")

                            # Check if it contains socket info
                            if size < 1_000_000:  # Only read files < 1MB
                                try:
                                    content = item.read_text(encoding='utf-8', errors='ignore')
                                    if '24981' in content or ('socket' in content.lower() and 'port' in content.lower()):
                                        print(f"         🔍 CONTAINS SOCKET PORT INFO!")
                                        print("         " + "-" * 70)
                                        print("         " + content[:500].replace('\n', '\n         '))
                                        if len(content) > 500:
                                            print(f"\n         ... (truncated, {len(content)} chars total)")
                                        print("         " + "-" * 70)
                                except:
                                    pass
                except Exception as e:
                    print(f"      ⚠️ Error exploring directory: {e}")
                print()
        else:
            print(f"❌ Not found: {config_path}")

    return found_configs


def test_bridge_launch_methods():
    """Test different ways to launch Bridge."""
    print_section("2. TESTING BRIDGE LAUNCH METHODS")

    bridge_exe = Path(r"C:\Program Files\Bridge\Bridge.exe")

    if not bridge_exe.exists():
        print("❌ Bridge.exe not found")
        return

    print(f"✅ Bridge executable: {bridge_exe}\n")

    # Test 1: Launch with different command-line arguments
    test_commands = [
        # Standard launch
        {
            "name": "Standard launch",
            "args": [],
            "description": "Launch Bridge normally"
        },
        # Try to set user data directory (common Electron pattern)
        {
            "name": "Custom user data directory",
            "args": ["--user-data-dir", str(Path.home() / "AppData" / "Local" / "Bridge_Instance2")],
            "description": "Launch with custom user data directory (may create separate config)"
        },
        # Try to set port via command line
        {
            "name": "Port argument (--port)",
            "args": ["--port", "24982"],
            "description": "Try to set port via --port argument"
        },
        {
            "name": "Port argument (--socket-port)",
            "args": ["--socket-port", "24982"],
            "description": "Try to set port via --socket-port argument"
        },
        # Try profile/config arguments
        {
            "name": "Custom profile",
            "args": ["--profile", "instance2"],
            "description": "Try to use a different profile"
        },
    ]

    print("NOTE: This will attempt to launch Bridge multiple times.")
    print("We won't actually launch them (to avoid conflicts), but we'll show the commands.\n")

    for test in test_commands:
        print(f"🧪 Test: {test['name']}")
        print(f"   Description: {test['description']}")

        cmd = [str(bridge_exe)] + test['args']
        print(f"   Command: {' '.join(cmd)}")
        print()

    print("\nTo manually test:")
    print("1. Open cmd.exe")
    print("2. Try each command above")
    print("3. See if Bridge launches with different configurations")


def test_user_data_directory_isolation():
    """Test if we can create isolated Bridge instances with separate configs."""
    print_section("3. USER DATA DIRECTORY ISOLATION TEST")

    bridge_exe = Path(r"C:\Program Files\Bridge\Bridge.exe")

    if not bridge_exe.exists():
        print("❌ Bridge.exe not found")
        return

    # Create test user data directories
    base_dir = Path.home() / "AppData" / "Local"
    test_instances = [
        base_dir / "Bridge_Test_Instance1",
        base_dir / "Bridge_Test_Instance2",
    ]

    print("Creating test instance directories:\n")
    for instance_dir in test_instances:
        instance_dir.mkdir(exist_ok=True, parents=True)
        print(f"✅ Created: {instance_dir}")

    print("\n" + "=" * 80)
    print("MANUAL TEST INSTRUCTIONS")
    print("=" * 80)
    print("""
To test if Bridge supports multiple instances with separate configs:

1. Open TWO command prompt windows (cmd.exe)

2. In the FIRST window, run:
   cd "C:\\Program Files\\Bridge"
   Bridge.exe --user-data-dir "%LOCALAPPDATA%\\Bridge_Test_Instance1"

3. In the SECOND window, run:
   cd "C:\\Program Files\\Bridge"
   Bridge.exe --user-data-dir "%LOCALAPPDATA%\\Bridge_Test_Instance2"

4. If both Bridge instances open successfully:
   - In Instance 1: Set socket port to 24981
   - In Instance 2: Set socket port to 24982
   - Check if both stay open with different ports

5. Check these directories for config files:
   - %LOCALAPPDATA%\\Bridge_Test_Instance1
   - %LOCALAPPDATA%\\Bridge_Test_Instance2

6. Run this script again to see what config files were created!
""")


def find_electron_cache_and_config():
    """Find all Electron app data locations for Bridge."""
    print_section("4. ELECTRON APP DATA LOCATIONS")

    electron_locations = [
        Path.home() / "AppData" / "Roaming" / "Bridge",
        Path.home() / "AppData" / "Local" / "Bridge",
        Path.home() / "AppData" / "Local" / "Programs" / "Bridge",
    ]

    print("Searching for Bridge Electron app data:\n")

    for location in electron_locations:
        if location.exists():
            print(f"✅ Found: {location}")

            # List important subdirectories
            important_dirs = ['Local Storage', 'Session Storage', 'IndexedDB', 'Cache']

            for subdir_name in important_dirs:
                subdir = location / subdir_name
                if subdir.exists():
                    print(f"   📁 {subdir_name}/")

                    # List files in this subdirectory
                    try:
                        for item in subdir.rglob("*"):
                            if item.is_file():
                                rel_path = item.relative_to(subdir)
                                size = item.stat().st_size
                                print(f"      📄 {rel_path} ({size:,} bytes)")

                                # Try to read small files
                                if size < 100_000 and item.suffix in ['.json', '.txt', '.log']:
                                    try:
                                        content = item.read_text(encoding='utf-8', errors='ignore')
                                        if '24981' in content or ('socket' in content.lower() and 'port' in content.lower()):
                                            print(f"         🔍 CONTAINS SOCKET CONFIGURATION!")
                                            print("         " + "-" * 66)
                                            print("         " + content[:500].replace('\n', '\n         '))
                                            if len(content) > 500:
                                                print(f"\n         ... ({len(content)} chars total)")
                                            print("         " + "-" * 66)
                                    except:
                                        pass
                    except Exception as e:
                        print(f"      ⚠️ Error: {e}")

            print()
        else:
            print(f"❌ Not found: {location}")


def analyze_bridge_process():
    """Analyze running Bridge processes to understand their configuration."""
    print_section("5. ANALYZING RUNNING BRIDGE PROCESSES")

    try:
        import psutil

        print("Looking for running Bridge processes:\n")

        bridge_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
            try:
                if proc.info['name'] and 'bridge' in proc.info['name'].lower():
                    bridge_processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if bridge_processes:
            print(f"✅ Found {len(bridge_processes)} Bridge process(es):\n")

            for proc in bridge_processes:
                print(f"Process: {proc.info['name']} (PID: {proc.info['pid']})")
                print(f"  Executable: {proc.info['exe']}")

                if proc.info['cmdline']:
                    print(f"  Command line:")
                    for arg in proc.info['cmdline']:
                        print(f"    - {arg}")

                print()
        else:
            print("❌ No Bridge processes currently running")
            print("   Start Bridge and run this script again to see process details")

    except ImportError:
        print("⚠️ psutil not installed")
        print("   Install with: pip install psutil")
        print("   This would let us analyze running Bridge processes")


def create_launch_script():
    """Create a test script to launch Bridge with custom port."""
    print_section("6. CREATING BRIDGE LAUNCH TEST SCRIPT")

    script_content = '''@echo off
REM Bridge Multi-Instance Launch Script
REM This script launches Bridge with custom configuration

echo Bridge Multi-Instance Launcher
echo ================================
echo.

set BRIDGE_EXE=C:\\Program Files\\Bridge\\Bridge.exe

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
    set USER_DATA_DIR=%LOCALAPPDATA%\\Bridge_Instance1
    set PORT=24981
)

if "%choice%"=="2" (
    set INSTANCE_NAME=Instance2
    set USER_DATA_DIR=%LOCALAPPDATA%\\Bridge_Instance2
    set PORT=24982
)

if "%choice%"=="3" (
    set INSTANCE_NAME=Instance3
    set USER_DATA_DIR=%LOCALAPPDATA%\\Bridge_Instance3
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
'''

    script_path = Path("launch_bridge_instance.bat")
    script_path.write_text(script_content, encoding='utf-8')

    print(f"✅ Created launch script: {script_path.absolute()}\n")
    print("This script lets you launch multiple Bridge instances.")
    print("Each instance will use a separate user data directory.\n")
    print("Usage:")
    print("  1. Double-click launch_bridge_instance.bat")
    print("  2. Choose which instance to launch (1, 2, or 3)")
    print("  3. Configure the socket port in Bridge UI for that instance")
    print("  4. Test if multiple instances can run simultaneously")


def main():
    print("=" * 80)
    print("  BRIDGE MULTI-INSTANCE CONFIGURATION TEST")
    print("=" * 80)
    print("\nThis script will help us understand how to launch multiple Bridge")
    print("instances with different socket ports for multi-Blender support.\n")

    # Find config files
    find_bridge_config_file()

    # Test launch methods
    test_bridge_launch_methods()

    # Test user data directory isolation
    test_user_data_directory_isolation()

    # Find Electron data
    find_electron_cache_and_config()

    # Analyze processes
    analyze_bridge_process()

    # Create launch script
    create_launch_script()

    print_section("SUMMARY & NEXT STEPS")
    print("""
We've explored Bridge's configuration and created test tools.

KEY FINDINGS:
- Bridge is an Electron app (supports --user-data-dir for isolation)
- Each Bridge instance can have its own socket port configuration
- We need to find where Bridge stores the socket port setting

NEXT STEPS:

1. FIND THE CONFIG FILE:
   - Look at the output above for config files containing '24981'
   - This is where Bridge stores the socket port setting

2. TEST MULTI-INSTANCE:
   - Run launch_bridge_instance.bat
   - Launch Instance 1, set port to 24981
   - Launch Instance 2, set port to 24982
   - Verify both stay open with different ports

3. IMPLEMENT IN BLENDER:
   Once we know how to launch Bridge with custom configs, we can:
   - Add "Launch Bridge" button in Blender
   - Each Blender instance launches Bridge with its unique port
   - Bridge connects to that specific Blender instance

CRITICAL QUESTION:
Did the script find any config files containing the socket port (24981)?
If YES: We can modify that file before launching Bridge!
If NO: We need to test if --user-data-dir creates separate configs.
""")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

    input("\n\nPress Enter to exit...")
