"""
Quixel Bridge Debug Script
===========================

This script investigates Quixel Bridge's capabilities and configuration options:
1. Bridge.exe command-line arguments
2. Bridge configuration files (JSON/XML)
3. Socket export settings and customization
4. Process information and environment
5. Registry entries (Windows)
6. Plugin/export configurations

Run this script with Python to gather all information about Bridge.
"""

import os
import sys
import subprocess
import json
import winreg
from pathlib import Path
import xml.etree.ElementTree as ET


def print_section(title):
    """Print a fancy section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def print_subsection(title):
    """Print a subsection header."""
    print(f"\n--- {title} ---")


def find_bridge_executable():
    """Find Bridge.exe on the system."""
    print_section("1. LOCATING QUIXEL BRIDGE")

    # Common installation paths
    common_paths = [
        r"C:\Program Files\Bridge\Bridge.exe",
        r"C:\Program Files (x86)\Bridge\Bridge.exe",
        r"C:\Program Files\Quixel\Bridge\Bridge.exe",
        r"C:\Program Files (x86)\Quixel\Bridge\Bridge.exe",
        Path.home() / "AppData" / "Local" / "Programs" / "Bridge" / "Bridge.exe",
        Path.home() / "AppData" / "Local" / "Quixel" / "Bridge" / "Bridge.exe",
    ]

    found_paths = []

    print("Checking common installation paths:")
    for path in common_paths:
        path = Path(path)
        exists = path.exists()
        print(f"  {'✅' if exists else '❌'} {path}")
        if exists:
            found_paths.append(path)

    # Check PATH environment variable
    print("\nSearching in PATH environment variable:")
    path_env = os.environ.get('PATH', '').split(os.pathsep)
    for path_dir in path_env:
        bridge_exe = Path(path_dir) / "Bridge.exe"
        if bridge_exe.exists() and bridge_exe not in found_paths:
            print(f"  ✅ Found in PATH: {bridge_exe}")
            found_paths.append(bridge_exe)

    if found_paths:
        print(f"\n✅ Found {len(found_paths)} Bridge installation(s)")
        return found_paths[0]  # Return first found
    else:
        print("\n❌ Bridge.exe not found in common locations")
        return None


def explore_bridge_directory(bridge_exe):
    """Explore Bridge installation directory for config files."""
    print_section("2. BRIDGE INSTALLATION DIRECTORY")

    bridge_dir = bridge_exe.parent
    print(f"Bridge directory: {bridge_dir}\n")

    # List all files in Bridge directory
    print("Files in Bridge directory:")
    try:
        for item in sorted(bridge_dir.iterdir()):
            if item.is_file():
                size = item.stat().st_size
                print(f"  📄 {item.name} ({size:,} bytes)")
            elif item.is_dir():
                file_count = len(list(item.iterdir()))
                print(f"  📁 {item.name}/ ({file_count} items)")
    except Exception as e:
        print(f"  ❌ Error listing directory: {e}")

    # Look for config files
    print_subsection("Configuration Files")
    config_patterns = ['*.json', '*.xml', '*.ini', '*.config', '*.cfg']
    config_files = []

    for pattern in config_patterns:
        for config_file in bridge_dir.rglob(pattern):
            if config_file.is_file():
                config_files.append(config_file)
                print(f"  📋 {config_file.relative_to(bridge_dir)}")

    return config_files


def analyze_config_files(config_files):
    """Analyze configuration files for socket/export settings."""
    print_section("3. CONFIGURATION FILE ANALYSIS")

    for config_file in config_files:
        print_subsection(f"File: {config_file.name}")
        print(f"Path: {config_file}\n")

        try:
            content = config_file.read_text(encoding='utf-8', errors='ignore')

            # Check for keywords related to socket/export
            keywords = [
                'socket', 'port', '24981', 'export', 'plugin',
                'blender', 'localhost', '127.0.0.1', 'tcp',
                'connection', 'server', 'client', 'address'
            ]

            found_keywords = []
            for keyword in keywords:
                if keyword.lower() in content.lower():
                    found_keywords.append(keyword)

            if found_keywords:
                print(f"🔍 Found keywords: {', '.join(found_keywords)}\n")

                # Try to parse as JSON
                if config_file.suffix == '.json':
                    try:
                        data = json.loads(content)
                        print("📋 JSON Structure:")
                        print(json.dumps(data, indent=2)[:2000])  # First 2000 chars
                        if len(json.dumps(data)) > 2000:
                            print(f"\n... (truncated, total size: {len(json.dumps(data))} chars)")
                    except json.JSONDecodeError as e:
                        print(f"⚠️ Invalid JSON: {e}")
                        print(f"First 500 chars:\n{content[:500]}")

                # Try to parse as XML
                elif config_file.suffix == '.xml':
                    try:
                        tree = ET.parse(config_file)
                        root = tree.getroot()
                        print(f"📋 XML Root: {root.tag}")
                        print(f"XML Structure (first 2000 chars):")
                        xml_str = ET.tostring(root, encoding='unicode')
                        print(xml_str[:2000])
                        if len(xml_str) > 2000:
                            print(f"\n... (truncated, total size: {len(xml_str)} chars)")
                    except ET.ParseError as e:
                        print(f"⚠️ Invalid XML: {e}")
                        print(f"First 500 chars:\n{content[:500]}")

                # For other files, show relevant lines
                else:
                    print("📋 Relevant lines:")
                    lines = content.split('\n')
                    for i, line in enumerate(lines[:500], 1):  # First 500 lines
                        for keyword in found_keywords:
                            if keyword.lower() in line.lower():
                                print(f"  Line {i}: {line.strip()}")
                                break
            else:
                print("❌ No relevant keywords found")

        except Exception as e:
            print(f"❌ Error reading file: {e}")

        print()


def check_appdata_configs():
    """Check AppData directories for Bridge configurations."""
    print_section("4. APPDATA CONFIGURATION FILES")

    appdata_paths = [
        Path.home() / "AppData" / "Local" / "Quixel",
        Path.home() / "AppData" / "Roaming" / "Quixel",
        Path.home() / "AppData" / "LocalLow" / "Quixel",
        Path.home() / "Documents" / "Quixel",
    ]

    config_files = []

    for appdata_path in appdata_paths:
        if appdata_path.exists():
            print(f"📁 Found: {appdata_path}")

            # List directory structure
            try:
                for item in appdata_path.rglob("*"):
                    if item.is_file():
                        rel_path = item.relative_to(appdata_path)
                        print(f"  📄 {rel_path}")

                        # Check if it's a config file
                        if item.suffix in ['.json', '.xml', '.ini', '.config', '.cfg']:
                            config_files.append(item)
            except Exception as e:
                print(f"  ❌ Error exploring directory: {e}")
        else:
            print(f"❌ Not found: {appdata_path}")

    if config_files:
        print(f"\n✅ Found {len(config_files)} config files in AppData")
        analyze_config_files(config_files)
    else:
        print("\n❌ No config files found in AppData")


def check_registry_entries():
    """Check Windows Registry for Bridge settings."""
    print_section("5. WINDOWS REGISTRY ENTRIES")

    registry_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Quixel"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Quixel"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Quixel"),
        (winreg.HKEY_CURRENT_USER, r"Software\Classes\quixel"),
    ]

    for root_key, subkey_path in registry_paths:
        root_name = {
            winreg.HKEY_LOCAL_MACHINE: "HKEY_LOCAL_MACHINE",
            winreg.HKEY_CURRENT_USER: "HKEY_CURRENT_USER"
        }.get(root_key, "UNKNOWN")

        full_path = f"{root_name}\\{subkey_path}"
        print(f"\nChecking: {full_path}")

        try:
            key = winreg.OpenKey(root_key, subkey_path, 0, winreg.KEY_READ)

            # Enumerate values
            i = 0
            while True:
                try:
                    name, value, value_type = winreg.EnumValue(key, i)
                    type_name = {
                        winreg.REG_SZ: "REG_SZ",
                        winreg.REG_DWORD: "REG_DWORD",
                        winreg.REG_BINARY: "REG_BINARY",
                    }.get(value_type, f"Type {value_type}")

                    print(f"  ✅ {name} = {value} ({type_name})")
                    i += 1
                except OSError:
                    break

            # Enumerate subkeys
            i = 0
            subkeys = []
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    subkeys.append(subkey_name)
                    i += 1
                except OSError:
                    break

            if subkeys:
                print(f"  📁 Subkeys: {', '.join(subkeys)}")

            winreg.CloseKey(key)

        except FileNotFoundError:
            print(f"  ❌ Key not found")
        except Exception as e:
            print(f"  ❌ Error: {e}")


def test_bridge_cli(bridge_exe):
    """Test Bridge.exe command-line arguments."""
    print_section("6. BRIDGE.EXE COMMAND-LINE INTERFACE")

    test_commands = [
        ["--help"],
        ["-h"],
        ["-?"],
        ["/help"],
        ["/?"],
        ["--version"],
        ["-v"],
        ["--port", "24982"],
        ["--socket", "24982"],
        ["--config"],
        ["--list-plugins"],
    ]

    for args in test_commands:
        cmd = [str(bridge_exe)] + args
        cmd_str = " ".join(args)
        print(f"\nTesting: Bridge.exe {cmd_str}")

        try:
            # Run with timeout to avoid hanging
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            if result.stdout:
                print(f"  STDOUT:\n{result.stdout[:500]}")
            if result.stderr:
                print(f"  STDERR:\n{result.stderr[:500]}")
            if result.returncode != 0:
                print(f"  Return code: {result.returncode}")

        except subprocess.TimeoutExpired:
            print(f"  ⏱️ Command timed out (might have launched GUI)")
        except Exception as e:
            print(f"  ❌ Error: {e}")


def check_bridge_plugins(bridge_exe):
    """Check Bridge plugins directory for export plugins."""
    print_section("7. BRIDGE PLUGINS & EXPORT CONFIGURATIONS")

    bridge_dir = bridge_exe.parent

    # Common plugin directory names
    plugin_dirs = [
        bridge_dir / "plugins",
        bridge_dir / "exports",
        bridge_dir / "exporters",
        bridge_dir / "resources" / "plugins",
        bridge_dir / "resources" / "exports",
    ]

    for plugin_dir in plugin_dirs:
        if plugin_dir.exists():
            print(f"\n✅ Found plugin directory: {plugin_dir}")

            try:
                for item in plugin_dir.rglob("*"):
                    if item.is_file():
                        rel_path = item.relative_to(plugin_dir)

                        # Highlight interesting files
                        interesting = any(keyword in str(item).lower()
                                        for keyword in ['socket', 'blender', 'export', 'plugin'])

                        prefix = "  🔍" if interesting else "  📄"
                        print(f"{prefix} {rel_path}")

                        # Read interesting files
                        if interesting and item.suffix in ['.json', '.xml', '.js', '.py']:
                            try:
                                content = item.read_text(encoding='utf-8', errors='ignore')
                                print(f"\n    Content preview:")
                                print(f"    {'-' * 60}")
                                print(content[:1000])
                                if len(content) > 1000:
                                    print(f"    ... (truncated, total: {len(content)} chars)")
                                print(f"    {'-' * 60}\n")
                            except Exception as e:
                                print(f"    ⚠️ Could not read file: {e}")
            except Exception as e:
                print(f"  ❌ Error exploring plugin directory: {e}")
        else:
            print(f"❌ Not found: {plugin_dir}")

    # Also check AppData for plugin configs
    print_subsection("AppData Plugin Configurations")

    appdata_plugin_paths = [
        Path.home() / "AppData" / "Local" / "Quixel" / "Bridge" / "plugins",
        Path.home() / "AppData" / "Local" / "Quixel" / "Bridge" / "exports",
        Path.home() / "AppData" / "Roaming" / "Quixel" / "Bridge" / "plugins",
        Path.home() / "AppData" / "Roaming" / "Quixel" / "Bridge" / "exports",
    ]

    for plugin_path in appdata_plugin_paths:
        if plugin_path.exists():
            print(f"\n✅ Found: {plugin_path}")
            try:
                for item in plugin_path.rglob("*"):
                    if item.is_file():
                        print(f"  📄 {item.relative_to(plugin_path)}")

                        # Read config files
                        if item.suffix in ['.json', '.xml']:
                            try:
                                content = item.read_text(encoding='utf-8', errors='ignore')

                                # Check for socket/port references
                                if any(kw in content.lower() for kw in ['socket', 'port', '24981']):
                                    print(f"\n    🔍 FOUND SOCKET REFERENCE:")
                                    print(f"    {'-' * 60}")
                                    print(content)
                                    print(f"    {'-' * 60}\n")
                            except Exception as e:
                                print(f"    ⚠️ Could not read: {e}")
            except Exception as e:
                print(f"  ❌ Error: {e}")


def check_environment_variables():
    """Check environment variables that might affect Bridge."""
    print_section("8. ENVIRONMENT VARIABLES")

    interesting_vars = [
        'QUIXEL_', 'BRIDGE_', 'MEGASCANS_',
        'APPDATA', 'LOCALAPPDATA', 'PROGRAMFILES',
        'PATH'
    ]

    for key, value in os.environ.items():
        for prefix in interesting_vars:
            if key.upper().startswith(prefix.upper()):
                print(f"  ✅ {key} = {value}")
                break

    print("\n(Showing only Quixel/Bridge-related and common system variables)")


def main():
    """Main debug script."""
    print("=" * 80)
    print("  QUIXEL BRIDGE DEBUG SCRIPT")
    print("  Investigating Bridge capabilities for multi-instance Blender support")
    print("=" * 80)

    # Find Bridge executable
    bridge_exe = find_bridge_executable()

    if not bridge_exe:
        print("\n❌ Cannot proceed without Bridge.exe")
        print("Please install Quixel Bridge or specify the installation path manually.")
        return

    # Explore Bridge installation
    config_files = explore_bridge_directory(bridge_exe)

    # Analyze config files
    if config_files:
        analyze_config_files(config_files)

    # Check AppData configs
    check_appdata_configs()

    # Check registry
    check_registry_entries()

    # Test CLI
    test_bridge_cli(bridge_exe)

    # Check plugins
    check_bridge_plugins(bridge_exe)

    # Check environment
    check_environment_variables()

    # Final summary
    print_section("9. SUMMARY & NEXT STEPS")
    print("""
This debug script has collected information about:
✅ Bridge installation location
✅ Configuration files (JSON/XML/INI)
✅ AppData configurations
✅ Windows Registry entries
✅ Command-line interface options
✅ Plugin/export configurations
✅ Environment variables

KEY THINGS TO LOOK FOR IN THE OUTPUT ABOVE:
1. Socket export plugin config with port numbers (likely in plugins/exports)
2. Command-line arguments that Bridge.exe accepts
3. Config files mentioning 'socket', 'port', or '24981'
4. Any way to pass custom parameters to export plugins

RECOMMENDED ACTIONS:
- Review the plugin configuration files for socket export settings
- Look for any JSON/XML files that configure the Blender export
- Check if Bridge CLI accepts --port or similar arguments
- Investigate custom socket export configurations
""")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

    input("\n\nPress Enter to exit...")
