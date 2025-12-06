"""
Bridge Configuration Finder
============================

This script helps find where Bridge stores the "Custom Socket Export" configuration.

INSTRUCTIONS:
1. Run this script FIRST (it will take a snapshot of all files)
2. Open Bridge and change the socket port from 24981 to 24999
3. Save/apply the settings in Bridge
4. Run this script AGAIN (it will show what changed)
"""

import os
import json
from pathlib import Path
from datetime import datetime
import hashlib


def get_file_hash(file_path):
    """Get MD5 hash of a file."""
    try:
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except:
        return None


def scan_directory(base_path, snapshot_file):
    """Scan a directory and save file info."""
    files_info = {}

    if not base_path.exists():
        return files_info

    for item in base_path.rglob("*"):
        if not item.is_file():
            continue

        try:
            rel_path = str(item.relative_to(base_path))
            size = item.stat().st_size
            modified = item.stat().st_mtime
            file_hash = get_file_hash(item) if size < 10_000_000 else None  # Hash files < 10MB

            files_info[rel_path] = {
                'size': size,
                'modified': modified,
                'hash': file_hash,
                'full_path': str(item)
            }
        except Exception as e:
            pass

    return files_info


def main():
    print("=" * 80)
    print("  BRIDGE CONFIGURATION FINDER")
    print("=" * 80)

    # Directories to monitor
    scan_dirs = [
        ("AppData\\Roaming\\Bridge", Path.home() / "AppData" / "Roaming" / "Bridge"),
        ("AppData\\Local\\Bridge", Path.home() / "AppData" / "Local" / "Bridge"),
        ("Documents", Path.home() / "Documents"),
    ]

    # Snapshot file
    snapshot_file = Path("bridge_snapshot.json")

    # Check if this is first run or comparison run
    if snapshot_file.exists():
        print("\n✅ Found previous snapshot - COMPARING CHANGES\n")

        # Load previous snapshot
        with open(snapshot_file, 'r') as f:
            old_snapshot = json.load(f)

        # Take new snapshot
        new_snapshot = {}
        for name, path in scan_dirs:
            print(f"Scanning: {name}...")
            new_snapshot[name] = scan_directory(path, snapshot_file)

        # Compare snapshots
        print("\n" + "=" * 80)
        print("  CHANGES DETECTED")
        print("=" * 80)

        found_changes = False

        for dir_name in old_snapshot.keys():
            old_files = old_snapshot.get(dir_name, {})
            new_files = new_snapshot.get(dir_name, {})

            # Find new files
            new_file_paths = set(new_files.keys()) - set(old_files.keys())
            if new_file_paths:
                found_changes = True
                print(f"\n📄 NEW FILES in {dir_name}:")
                for file_path in new_file_paths:
                    full_path = new_files[file_path]['full_path']
                    size = new_files[file_path]['size']
                    print(f"  ✅ {file_path} ({size:,} bytes)")
                    print(f"     Full path: {full_path}")

                    # Try to read if it's a text file
                    if Path(full_path).suffix in ['.json', '.xml', '.txt', '.cfg', '.ini']:
                        try:
                            content = Path(full_path).read_text(encoding='utf-8', errors='ignore')
                            print(f"     Content:")
                            print("     " + "-" * 70)
                            if Path(full_path).suffix == '.json':
                                try:
                                    data = json.loads(content)
                                    print("     " + json.dumps(data, indent=2).replace('\n', '\n     '))
                                except:
                                    print("     " + content.replace('\n', '\n     '))
                            else:
                                print("     " + content.replace('\n', '\n     '))
                            print("     " + "-" * 70)
                        except Exception as e:
                            print(f"     ⚠️ Could not read: {e}")

            # Find modified files
            modified_files = []
            for file_path in set(old_files.keys()) & set(new_files.keys()):
                old_info = old_files[file_path]
                new_info = new_files[file_path]

                # Check if hash changed (content changed)
                if old_info['hash'] != new_info['hash'] and new_info['hash'] is not None:
                    modified_files.append(file_path)

            if modified_files:
                found_changes = True
                print(f"\n📝 MODIFIED FILES in {dir_name}:")
                for file_path in modified_files:
                    full_path = new_files[file_path]['full_path']
                    print(f"  ✏️  {file_path}")
                    print(f"     Full path: {full_path}")

                    # Try to read if it's a text file
                    if Path(full_path).suffix in ['.json', '.xml', '.txt', '.cfg', '.ini']:
                        try:
                            content = Path(full_path).read_text(encoding='utf-8', errors='ignore')
                            print(f"     NEW Content:")
                            print("     " + "-" * 70)
                            if Path(full_path).suffix == '.json':
                                try:
                                    data = json.loads(content)
                                    print("     " + json.dumps(data, indent=2).replace('\n', '\n     '))
                                except:
                                    print("     " + content.replace('\n', '\n     '))
                            else:
                                print("     " + content.replace('\n', '\n     '))
                            print("     " + "-" * 70)
                        except Exception as e:
                            print(f"     ⚠️ Could not read: {e}")

            # Find deleted files
            deleted_files = set(old_files.keys()) - set(new_files.keys())
            if deleted_files:
                found_changes = True
                print(f"\n🗑️  DELETED FILES in {dir_name}:")
                for file_path in deleted_files:
                    print(f"  ❌ {file_path}")

        if not found_changes:
            print("\n❌ No changes detected!")
            print("\nMake sure you:")
            print("  1. Changed the socket port in Bridge (24981 → 24999)")
            print("  2. Saved/applied the settings")
            print("  3. Closed Bridge (some apps save on exit)")

        # Save new snapshot for next comparison
        with open(snapshot_file, 'w') as f:
            json.dump(new_snapshot, f, indent=2)

        print("\n✅ Snapshot updated for next comparison")

    else:
        print("\n📸 Taking INITIAL SNAPSHOT\n")
        print("This is the first run. The script will scan all directories and save")
        print("the current state of files.\n")
        print("NEXT STEPS:")
        print("  1. Open Quixel Bridge")
        print("  2. Go to Export Settings")
        print("  3. Change the socket port from 24981 to 24999")
        print("  4. Save/apply the settings (might need to close Bridge)")
        print("  5. Run this script again to see what changed\n")

        # Take snapshot
        snapshot = {}
        for name, path in scan_dirs:
            print(f"Scanning: {name}...")
            snapshot[name] = scan_directory(path, snapshot_file)

        # Save snapshot
        with open(snapshot_file, 'w') as f:
            json.dump(snapshot, f, indent=2)

        print("\n✅ Initial snapshot saved!")
        print(f"   File: {snapshot_file.absolute()}")
        print("\nNow follow the steps above and run this script again.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

    input("\n\nPress Enter to exit...")
