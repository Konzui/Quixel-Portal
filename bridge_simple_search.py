"""
Simple Bridge Search - Find Port Configuration
==============================================

Just search for port 24981 and export configurations.
"""

import os
from pathlib import Path
import json


def print_section(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def search_for_port_in_directory(directory, extensions=None):
    """Search for port 24981 in text files."""
    if extensions is None:
        extensions = ['.json', '.xml', '.js', '.txt', '.cfg', '.ini', '.config', '.html']

    found_files = []

    for item in Path(directory).rglob("*"):
        if not item.is_file():
            continue

        if item.suffix.lower() not in extensions:
            continue

        # Skip very large files
        if item.stat().st_size > 5_000_000:  # Skip files > 5MB
            continue

        try:
            content = item.read_text(encoding='utf-8', errors='ignore')

            if '24981' in content or 'socket' in content.lower() and 'export' in content.lower():
                found_files.append((item, content))

        except Exception:
            pass

    return found_files


def check_user_bridge_data():
    """Check user's AppData for Bridge configurations."""
    print_section("1. CHECKING USER APPDATA FOR BRIDGE")

    # Try to find Bridge's user data
    base_paths = [
        Path.home() / "AppData" / "Roaming" / "Bridge",
        Path.home() / "AppData" / "Local" / "Bridge",
    ]

    for base_path in base_paths:
        if not base_path.exists():
            print(f"❌ Not found: {base_path}")
            continue

        print(f"✅ Found: {base_path}\n")

        # List all files
        for item in base_path.rglob("*"):
            if item.is_file():
                print(f"  📄 {item.relative_to(base_path)} ({item.stat().st_size:,} bytes)")

        # Search for config files
        print("\n🔍 Searching for configurations...\n")
        found = search_for_port_in_directory(base_path)

        for file_path, content in found:
            print(f"✅ FOUND: {file_path.relative_to(base_path)}")
            print("-" * 80)

            # If it's JSON, pretty print it
            if file_path.suffix == '.json':
                try:
                    data = json.loads(content)
                    print(json.dumps(data, indent=2))
                except:
                    print(content)
            else:
                print(content)

            print("-" * 80)
            print()


def check_bridge_installation():
    """Check Bridge installation for export configs."""
    print_section("2. CHECKING BRIDGE INSTALLATION")

    bridge_path = Path(r"C:\Program Files\Bridge")

    if not bridge_path.exists():
        print("❌ Bridge not found")
        return

    print(f"✅ Bridge found: {bridge_path}\n")

    # Only search in likely config locations
    search_dirs = [
        bridge_path / "assets",
        bridge_path / "resources",
    ]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue

        print(f"\n🔍 Searching in: {search_dir.name}/")
        found = search_for_port_in_directory(search_dir)

        for file_path, content in found:
            rel_path = file_path.relative_to(bridge_path)
            print(f"\n✅ FOUND: {rel_path}")
            print("-" * 80)

            # If it's JSON, pretty print it
            if file_path.suffix == '.json':
                try:
                    data = json.loads(content)
                    print(json.dumps(data, indent=2))
                except:
                    print(content[:2000])
                    if len(content) > 2000:
                        print(f"\n... (truncated, {len(content)} total chars)")
            else:
                print(content[:2000])
                if len(content) > 2000:
                    print(f"\n... (truncated, {len(content)} total chars)")

            print("-" * 80)


def check_documents_folder():
    """Check Documents folder for Bridge export configs."""
    print_section("3. CHECKING DOCUMENTS FOLDER")

    docs_path = Path.home() / "Documents"

    # Look for Bridge-related folders
    bridge_folders = []
    for item in docs_path.iterdir():
        if 'bridge' in item.name.lower() or 'quixel' in item.name.lower():
            bridge_folders.append(item)

    if not bridge_folders:
        print("❌ No Bridge/Quixel folders found in Documents")
        return

    for folder in bridge_folders:
        print(f"\n✅ Found: {folder}")

        # List contents
        try:
            for item in folder.rglob("*"):
                if item.is_file():
                    print(f"  📄 {item.relative_to(folder)}")

                    # Read config files
                    if item.suffix in ['.json', '.xml', '.txt', '.cfg']:
                        try:
                            content = item.read_text(encoding='utf-8', errors='ignore')
                            print(f"\n    Content:")
                            print("    " + "-" * 76)

                            if item.suffix == '.json':
                                try:
                                    data = json.loads(content)
                                    print("    " + json.dumps(data, indent=2).replace('\n', '\n    '))
                                except:
                                    print("    " + content.replace('\n', '\n    '))
                            else:
                                print("    " + content.replace('\n', '\n    '))

                            print("    " + "-" * 76)
                            print()
                        except Exception as e:
                            print(f"    ⚠️ Could not read: {e}")
        except Exception as e:
            print(f"  ❌ Error: {e}")


def main():
    print("=" * 80)
    print("  SIMPLE BRIDGE SEARCH - FIND PORT 24981 CONFIGURATION")
    print("=" * 80)

    check_user_bridge_data()
    check_bridge_installation()
    check_documents_folder()

    print_section("INSTRUCTIONS FOR FINDING EXPORT SETTINGS")
    print("""
If no configuration files were found above, try this:

1. Open Quixel Bridge application
2. Go to Settings or Preferences
3. Look for "Export Settings" or "Integration Settings"
4. Look for any mention of:
   - Socket export
   - Blender integration
   - Custom exports
   - Port numbers
5. Check if there's a way to create/edit export presets
6. Look for any "Advanced" or "Developer" settings

SPECIFIC THINGS TO LOOK FOR IN BRIDGE UI:
- Export Presets/Templates
- Custom Socket Export configuration
- Integration settings for Blender
- Any way to specify a port number

If you find export configuration UI:
- Take screenshots
- Try to export/save a custom configuration
- Check if new files appear in AppData or Documents folders
""")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

    input("\n\nPress Enter to exit...")
