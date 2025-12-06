"""
Quixel Bridge Deep Dive - Focus on ASAR and Export Plugins
===========================================================

Since Bridge is an Electron app, we need to:
1. Extract/examine the app.asar file (contains the actual app code)
2. Find export plugin configurations
3. Look for socket export settings
"""

import os
import sys
import json
import subprocess
from pathlib import Path


def print_section(title):
    """Print a fancy section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def explore_asar_contents():
    """Explore the app.asar file structure."""
    print_section("1. EXPLORING APP.ASAR (ELECTRON APP)")

    asar_path = Path(r"C:\Program Files\Bridge\resources\app.asar")

    if not asar_path.exists():
        print("❌ app.asar not found")
        return

    print(f"✅ Found app.asar: {asar_path}")
    print(f"   Size: {asar_path.stat().st_size:,} bytes\n")

    # Check if asar-extract tool is available
    print("Attempting to list asar contents using npx asar...")

    try:
        # Try using npx asar list
        result = subprocess.run(
            ["npx", "asar", "list", str(asar_path)],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            print("✅ ASAR contents:")
            lines = result.stdout.split('\n')

            # Filter for interesting files
            interesting_keywords = ['export', 'plugin', 'socket', 'blender', 'config']

            print("\n🔍 ALL FILES (filtered for interesting ones):")
            for line in lines:
                if any(kw in line.lower() for kw in interesting_keywords):
                    print(f"  🔍 {line}")

            print("\n📋 ALL FILES (first 200):")
            for i, line in enumerate(lines[:200]):
                print(f"  {line}")

            if len(lines) > 200:
                print(f"\n  ... and {len(lines) - 200} more files")
        else:
            print(f"⚠️ asar list failed: {result.stderr}")
            print("\nTrying alternative method...")

    except FileNotFoundError:
        print("❌ npx/asar not found. Trying alternative method...")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Check unpacked directory
    print_section("2. CHECKING UNPACKED RESOURCES")

    unpacked_dir = Path(r"C:\Program Files\Bridge\resources\app.asar.unpacked")

    if unpacked_dir.exists():
        print(f"✅ Found unpacked directory: {unpacked_dir}\n")

        print("Directory structure:")
        for item in unpacked_dir.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(unpacked_dir)

                # Highlight interesting files
                interesting = any(kw in str(item).lower()
                                for kw in ['export', 'plugin', 'socket', 'blender', 'config', 'json'])

                if interesting:
                    print(f"  🔍 {rel_path}")
    else:
        print("❌ Unpacked directory not found")


def check_user_data_locations():
    """Check common Electron app user data locations."""
    print_section("3. ELECTRON USER DATA LOCATIONS")

    possible_locations = [
        Path.home() / "AppData" / "Roaming" / "Bridge",
        Path.home() / "AppData" / "Local" / "Bridge",
        Path.home() / "AppData" / "Roaming" / "bridge",
        Path.home() / "AppData" / "Local" / "bridge",
        Path.home() / ".bridge",
        Path.home() / ".config" / "Bridge",
        Path(r"C:\Users") / os.environ.get('USERNAME', '') / ".bridge",
    ]

    for location in possible_locations:
        if location.exists():
            print(f"✅ Found: {location}")

            try:
                for item in location.rglob("*"):
                    if item.is_file():
                        rel_path = item.relative_to(location)
                        size = item.stat().st_size

                        # Check if it's a config or interesting file
                        interesting = item.suffix in ['.json', '.xml', '.ini', '.config'] or \
                                    any(kw in item.name.lower() for kw in ['export', 'plugin', 'socket', 'blender'])

                        prefix = "  🔍" if interesting else "  📄"
                        print(f"{prefix} {rel_path} ({size:,} bytes)")

                        # Read interesting small files
                        if interesting and size < 100_000:  # Less than 100KB
                            try:
                                content = item.read_text(encoding='utf-8', errors='ignore')

                                # Check for socket/port/export keywords
                                if any(kw in content.lower() for kw in ['socket', 'port', '24981', 'export', 'blender']):
                                    print(f"\n    ⭐ IMPORTANT FILE FOUND!")
                                    print(f"    {'-' * 70}")
                                    print(content)
                                    print(f"    {'-' * 70}\n")
                            except Exception as e:
                                print(f"    ⚠️ Could not read: {e}")
            except Exception as e:
                print(f"  ❌ Error exploring: {e}")
        else:
            print(f"❌ Not found: {location}")


def extract_specific_files_from_asar():
    """Try to extract specific files from asar that might contain export configs."""
    print_section("4. EXTRACTING KEY FILES FROM ASAR")

    asar_path = Path(r"C:\Program Files\Bridge\resources\app.asar")

    # Files we want to extract (common locations for Electron app configs)
    target_files = [
        "package.json",
        "main.js",
        "index.js",
        "src/main.js",
        "app/main.js",
        "exports/socket.json",
        "plugins/blender.json",
        "config/exports.json",
        "config/plugins.json",
        "src/exports/socket.js",
        "src/plugins/blender.js",
    ]

    output_dir = Path("./bridge_extracted")
    output_dir.mkdir(exist_ok=True)

    print(f"Attempting to extract files to: {output_dir.absolute()}\n")

    for file_path in target_files:
        print(f"Trying to extract: {file_path}")

        try:
            result = subprocess.run(
                ["npx", "asar", "extract-file", str(asar_path), file_path, str(output_dir / Path(file_path).name)],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                extracted_file = output_dir / Path(file_path).name
                if extracted_file.exists():
                    print(f"  ✅ Extracted successfully")

                    # Read and display content
                    try:
                        content = extracted_file.read_text(encoding='utf-8', errors='ignore')
                        print(f"  📋 Content preview:")
                        print(f"  {'-' * 70}")
                        print(content[:1500])
                        if len(content) > 1500:
                            print(f"\n  ... (truncated, total: {len(content)} chars)")
                        print(f"  {'-' * 70}\n")
                    except Exception as e:
                        print(f"  ⚠️ Could not read extracted file: {e}")
            else:
                print(f"  ❌ Extraction failed")

        except FileNotFoundError:
            print(f"  ⚠️ asar tool not available (install with: npm install -g asar)")
            break
        except Exception as e:
            print(f"  ❌ Error: {e}")


def check_bridge_exports_folder():
    """Check if Bridge has a separate exports folder."""
    print_section("5. CHECKING FOR BRIDGE EXPORTS CONFIGURATION")

    possible_export_locations = [
        Path(r"C:\Program Files\Bridge\exports"),
        Path(r"C:\Program Files\Bridge\plugins"),
        Path(r"C:\Program Files\Bridge\resources\exports"),
        Path(r"C:\Program Files\Bridge\resources\plugins"),
        Path(r"C:\Program Files\Bridge\assets\exports"),
        Path.home() / "AppData" / "Roaming" / "Bridge" / "exports",
        Path.home() / "AppData" / "Local" / "Bridge" / "exports",
        Path.home() / "Documents" / "Bridge" / "exports",
    ]

    for location in possible_export_locations:
        if location.exists():
            print(f"✅ Found: {location}\n")

            try:
                for item in location.rglob("*"):
                    if item.is_file():
                        rel_path = item.relative_to(location)
                        print(f"  📄 {rel_path}")

                        # Read config files
                        if item.suffix in ['.json', '.xml', '.js', '.cfg']:
                            try:
                                content = item.read_text(encoding='utf-8', errors='ignore')
                                print(f"\n    Content:")
                                print(f"    {'-' * 70}")
                                print(content)
                                print(f"    {'-' * 70}\n")
                            except Exception as e:
                                print(f"    ⚠️ Could not read: {e}")
            except Exception as e:
                print(f"  ❌ Error: {e}")


def inspect_bridge_assets():
    """Check the assets folder that we saw in the first scan."""
    print_section("6. INSPECTING BRIDGE ASSETS FOLDER")

    assets_dir = Path(r"C:\Program Files\Bridge\assets")

    if assets_dir.exists():
        print(f"✅ Found assets directory\n")

        for item in assets_dir.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(assets_dir)
                size = item.stat().st_size

                print(f"  📄 {rel_path} ({size:,} bytes)")

                # Read text files
                if item.suffix in ['.json', '.xml', '.js', '.txt', '.cfg', '.ini']:
                    try:
                        content = item.read_text(encoding='utf-8', errors='ignore')

                        # Always show JSON/XML files
                        if item.suffix in ['.json', '.xml']:
                            print(f"\n    ⭐ Config file content:")
                            print(f"    {'-' * 70}")
                            print(content)
                            print(f"    {'-' * 70}\n")
                        # Show other text files if they contain keywords
                        elif any(kw in content.lower() for kw in ['socket', 'port', '24981', 'export', 'blender']):
                            print(f"\n    🔍 Contains relevant keywords:")
                            print(f"    {'-' * 70}")
                            print(content)
                            print(f"    {'-' * 70}\n")
                    except Exception as e:
                        print(f"    ⚠️ Could not read: {e}")


def search_for_port_24981():
    """Search all files in Bridge directory for the port number 24981."""
    print_section("7. SEARCHING FOR PORT 24981 IN ALL FILES")

    bridge_dir = Path(r"C:\Program Files\Bridge")

    print("Searching all text files for '24981'...\n")

    searched = 0
    found_in = []

    for item in bridge_dir.rglob("*"):
        if item.is_file() and item.suffix in ['.json', '.xml', '.js', '.txt', '.cfg', '.ini', '.config', '.html', '.css']:
            searched += 1

            try:
                content = item.read_text(encoding='utf-8', errors='ignore')

                if '24981' in content:
                    found_in.append(item)
                    print(f"✅ FOUND in: {item.relative_to(bridge_dir)}")
                    print(f"   {'-' * 70}")

                    # Show context around the match
                    lines = content.split('\n')
                    for i, line in enumerate(lines):
                        if '24981' in line:
                            # Show 5 lines before and after
                            start = max(0, i - 5)
                            end = min(len(lines), i + 6)

                            for j in range(start, end):
                                prefix = ">>> " if j == i else "    "
                                print(f"   {prefix}Line {j+1}: {lines[j]}")

                    print(f"   {'-' * 70}\n")
            except Exception as e:
                pass

    print(f"\nSearched {searched} files")
    print(f"Found port 24981 in {len(found_in)} file(s)")


def main():
    """Main deep dive script."""
    print("=" * 80)
    print("  QUIXEL BRIDGE DEEP DIVE - ELECTRON APP ANALYSIS")
    print("=" * 80)

    # Explore ASAR
    explore_asar_contents()

    # Check user data
    check_user_data_locations()

    # Try to extract specific files
    extract_specific_files_from_asar()

    # Check exports folder
    check_bridge_exports_folder()

    # Inspect assets
    inspect_bridge_assets()

    # Search for port 24981
    search_for_port_24981()

    print_section("SUMMARY")
    print("""
We've examined:
✅ Electron app.asar structure
✅ User data locations
✅ Export plugin configurations
✅ Assets folder
✅ All files for port 24981

NEXT STEPS:
1. Review the output above for any export configuration files
2. Look for socket export plugin definitions
3. Check if we found any files mentioning port 24981
4. Determine if we can customize the socket export
""")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

    input("\n\nPress Enter to exit...")
