#!/usr/bin/env python3
"""
Build script for Quixel Portal Blender Addon

This script builds the Electron application and packages the addon
into a production-ready zip file for Blender installation.
"""

import os
import sys
import shutil
import subprocess
import zipfile
from pathlib import Path
from datetime import datetime

# Get the root directory (where this script is located)
ROOT_DIR = Path(__file__).parent.resolve()
ELECTRON_APP_DIR = ROOT_DIR / "electron_app"
STAGING_DIR = ROOT_DIR / "_build_staging"
ZIP_NAME = "Quixel_Portal_v1.0.0.zip"


def print_step(message):
    """Print a formatted step message."""
    print(f"\n{'='*60}")
    print(f"  {message}")
    print(f"{'='*60}")


def print_info(message):
    """Print an info message."""
    print(f"  [INFO] {message}")


def print_success(message):
    """Print a success message."""
    print(f"  [OK] {message}")


def print_error(message):
    """Print an error message."""
    print(f"  [ERROR] {message}")


def get_npm_command():
    """Get the appropriate npm command for the current platform.
    
    Returns the npm command that works, or None if npm is not available.
    """
    # Try different npm commands based on platform
    commands_to_try = []
    if sys.platform == "win32":
        commands_to_try = ["npm.cmd", "npm"]
    else:
        commands_to_try = ["npm"]
    
    for cmd in commands_to_try:
        try:
            result = subprocess.run(
                [cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                shell=sys.platform == "win32"
            )
            if result.returncode == 0:
                return cmd
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        except Exception:
            continue
    
    return None


def check_npm_available():
    """Check if npm is available."""
    print_step("Checking for Node.js/npm")
    
    npm_cmd = get_npm_command()
    
    if npm_cmd:
        try:
            result = subprocess.run(
                [npm_cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                shell=sys.platform == "win32"
            )
            if result.returncode == 0:
                print_success(f"npm found (version: {result.stdout.strip()})")
                return True
        except Exception as e:
            print_error(f"Error checking npm version: {e}")
    
    print_error("npm not found. Please install Node.js from https://nodejs.org/")
    print_info("Make sure Node.js is installed and added to your PATH")
    return False


def build_electron_app():
    """Build the Electron application for Windows."""
    print_step("Building Electron Application")
    
    if not ELECTRON_APP_DIR.exists():
        print_error(f"Electron app directory not found: {ELECTRON_APP_DIR}")
        return False
    
    print_info(f"Building in: {ELECTRON_APP_DIR}")
    
    npm_cmd = get_npm_command()
    if not npm_cmd:
        print_error("npm command not found")
        return False
    
    try:
        # First, ensure dependencies are installed
        print_info("Ensuring dependencies are installed...")
        install_result = subprocess.run(
            [npm_cmd, "install"],
            cwd=str(ELECTRON_APP_DIR),
            check=True,
            timeout=300,  # 5 minute timeout
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=sys.platform == "win32"
        )
        print_success("Dependencies installed")
        
        # Run npm build command
        print_info(f"Running: {npm_cmd} run build-win")
        result = subprocess.run(
            [npm_cmd, "run", "build-win"],
            cwd=str(ELECTRON_APP_DIR),
            check=True,
            timeout=600,  # 10 minute timeout
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=sys.platform == "win32"
        )
        
        print_success("Electron build completed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print_error(f"Electron build failed with return code {e.returncode}")
        if e.stdout:
            print(f"\nBuild output:\n{e.stdout}")
        return False
    except subprocess.TimeoutExpired:
        print_error("Electron build timed out (exceeded 10 minutes)")
        return False
    except Exception as e:
        print_error(f"Error building Electron app: {e}")
        return False


def verify_build_output():
    """Verify that the Electron build output exists."""
    print_step("Verifying Build Output")
    
    exe_path = ELECTRON_APP_DIR / "build" / "win-unpacked" / "Quixel Portal.exe"
    
    if not exe_path.exists():
        print_error(f"Built executable not found: {exe_path}")
        print_error("Please ensure the Electron build completed successfully")
        return False
    
    print_success(f"Found built executable: {exe_path}")
    return True


def should_include_file(file_path, root_dir):
    """Determine if a file should be included in the production build."""
    try:
        relative_path = file_path.relative_to(root_dir)
    except ValueError:
        # File is not relative to root_dir, exclude it
        return False
    
    path_str = str(relative_path).replace("\\", "/")
    path_parts = path_str.split("/")
    file_name = file_path.name
    
    # Exclude Python cache files and directories
    if "__pycache__" in path_parts:
        return False
    if file_name.endswith((".pyc", ".pyo", ".pyd")):
        return False
    
    # Exclude development directories
    if any(part in [".claude", ".git", ".vscode", ".idea", "_build_staging"] for part in path_parts):
        return False
    
    # Exclude development files
    if file_name in [".gitignore", "build.py"]:
        return False
    
    # Special handling for electron_app directory
    if "electron_app" in path_parts:
        electron_index = path_parts.index("electron_app")
        
        # Check if this is inside assets directory - include everything
        if "assets" in path_parts:
            return True
        
        # Check if this is inside build/win-unpacked directory - include everything
        if "win-unpacked" in path_parts:
            return True
        
        # Exclude root-level files in electron_app (source files)
        if electron_index + 1 == len(path_parts):
            # This is a file directly in electron_app
            if file_name.endswith((".js", ".html", ".css", ".json")):
                return False
            if file_name in ["package.json", "package-lock.json", "nul"]:
                return False
        
        # Exclude node_modules and dist
        if "node_modules" in path_parts or "dist" in path_parts:
            return False
        
        # Exclude build artifacts (installer exe, yml files) but not win-unpacked contents
        if "build" in path_parts and "win-unpacked" not in path_parts:
            # This is in build/ but not in win-unpacked (e.g., installer exe, config files)
            if file_name.endswith((".exe", ".yml", ".yaml")):
                return False
        
        # Exclude everything else in electron_app that we haven't explicitly included
        return False
    
    # Include all other files (Python addon files, README, etc.)
    return True


def copy_files_to_staging():
    """Copy production files to staging directory."""
    print_step("Copying Files to Staging Directory")
    
    # Create staging directory
    if STAGING_DIR.exists():
        print_info("Cleaning existing staging directory...")
        shutil.rmtree(STAGING_DIR)
    
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    
    # Files and directories to copy
    items_to_copy = [
        # Python addon files
        "__init__.py",
        "main.py",
        "communication",
        "operations",
        "ui",
        "utils",
        # Electron app (selective)
        "electron_app",
        # Documentation
        "README.md",
    ]
    
    copied_count = 0
    
    for item_name in items_to_copy:
        source = ROOT_DIR / item_name
        
        if not source.exists():
            print_info(f"Skipping (not found): {item_name}")
            continue
        
        destination = STAGING_DIR / item_name
        
        if source.is_file():
            # Copy file
            if should_include_file(source, ROOT_DIR):
                shutil.copy2(source, destination)
                copied_count += 1
                print_info(f"Copied: {item_name}")
        elif source.is_dir():
            # Copy directory with filtering
            _copy_directory_filtered(source, destination, ROOT_DIR)
            if destination.exists():
                copied_count += 1
                print_info(f"Copied directory: {item_name}")
    
    print_success(f"Copied {copied_count} items to staging")
    
    # Verify critical files are present
    exe_path = STAGING_DIR / "electron_app" / "build" / "win-unpacked" / "Quixel Portal.exe"
    if exe_path.exists():
        print_success(f"Verified Electron executable in staging: {exe_path.name}")
    else:
        print_error(f"Electron executable not found in staging: {exe_path}")
        return False
    
    return True


def _copy_directory_filtered(source_dir, dest_dir, root_dir):
    """Copy a directory while filtering files."""
    try:
        relative = source_dir.relative_to(root_dir)
        relative_str = str(relative).replace("\\", "/")
    except ValueError:
        return
    
    # Special handling for electron_app root directory
    if relative_str == "electron_app":
        # Create electron_app directory structure
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy assets directory
        assets_source = source_dir / "assets"
        if assets_source.exists():
            assets_dest = dest_dir / "assets"
            print_info(f"Copying Electron assets: {assets_source} -> {assets_dest}")
            shutil.copytree(assets_source, assets_dest, dirs_exist_ok=True)
        
        # Copy build/win-unpacked directory (entire folder with all runtime files)
        build_source = source_dir / "build" / "win-unpacked"
        if build_source.exists():
            build_dest = dest_dir / "build" / "win-unpacked"
            print_info(f"Copying Electron runtime: {build_source} -> {build_dest}")
            shutil.copytree(build_source, build_dest, dirs_exist_ok=True)
            # Count files copied
            file_count = sum(1 for _ in build_dest.rglob('*') if _.is_file())
            print_info(f"  Copied {file_count} runtime files (exe, DLLs, resources, etc.)")
        else:
            print_error(f"Electron build directory not found: {build_source}")
        
        return
    
    # For other directories, check if they should be included
    if not should_include_file(source_dir, root_dir):
        return
    
    # For other directories, copy with filtering
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    for item in source_dir.iterdir():
        if not should_include_file(item, root_dir):
            continue
        
        dest_item = dest_dir / item.name
        
        if item.is_file():
            shutil.copy2(item, dest_item)
        elif item.is_dir():
            _copy_directory_filtered(item, dest_item, root_dir)


def create_zip_file():
    """Create the final zip file from staging directory."""
    print_step("Creating Zip File")
    
    zip_path = ROOT_DIR / ZIP_NAME
    
    # Remove existing zip if it exists
    if zip_path.exists():
        print_info(f"Removing existing zip: {ZIP_NAME}")
        zip_path.unlink()
    
    print_info(f"Creating zip: {ZIP_NAME}")
    
    # Get the addon name from __init__.py
    addon_display_name = "Quixel Portal"
    try:
        init_file = STAGING_DIR / "__init__.py"
        if init_file.exists():
            with open(init_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # Try to extract name from bl_info
                if '"name":' in content:
                    import re
                    match = re.search(r'"name":\s*"([^"]+)"', content)
                    if match:
                        addon_display_name = match.group(1)
    except Exception:
        pass  # Use default name
    
    # Convert display name to Python-friendly directory name (no spaces, valid identifier)
    # Replace spaces with underscores and ensure it's a valid Python identifier
    addon_dir_name = addon_display_name.replace(" ", "_").replace("-", "_")
    # Remove any characters that aren't valid in Python identifiers
    import string
    valid_chars = string.ascii_letters + string.digits + "_"
    addon_dir_name = "".join(c if c in valid_chars else "_" for c in addon_dir_name)
    # Ensure it starts with a letter or underscore
    if addon_dir_name and addon_dir_name[0].isdigit():
        addon_dir_name = "_" + addon_dir_name
    
    print_info(f"Addon display name: {addon_display_name}")
    print_info(f"Addon directory name: {addon_dir_name}")
    
    # Create zip file
    # Note: We don't need to filter here since we already filtered when copying to staging
    file_count = 0
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(STAGING_DIR):
            # Include all files in staging (they're already filtered)
            for file in files:
                file_path = Path(root) / file
                # Create archive path with addon directory name as root (Python-friendly, no spaces)
                relative_path = file_path.relative_to(STAGING_DIR)
                # Use forward slashes for zip archive paths (zip standard)
                arcname = str(Path(addon_dir_name) / relative_path).replace("\\", "/")
                zipf.write(file_path, arcname)
                file_count += 1
    
    zip_size = zip_path.stat().st_size / (1024 * 1024)  # Size in MB
    print_success(f"Created zip file: {ZIP_NAME}")
    print_info(f"  Files: {file_count}")
    print_info(f"  Size: {zip_size:.2f} MB")
    print_info(f"  Location: {zip_path}")
    
    # Verify exe is in zip
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        exe_files = [f for f in zipf.namelist() if f.endswith('.exe') and 'Quixel Portal.exe' in f]
        if exe_files:
            print_success(f"Verified Electron executable in zip: {exe_files[0]}")
        else:
            print_error("WARNING: Electron executable not found in zip file!")
            return False
    
    return True


def cleanup_staging():
    """Clean up the staging directory."""
    print_step("Cleaning Up")
    
    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
        print_success("Staging directory removed")
    
    return True


def main():
    """Main build function."""
    print("\n" + "="*60)
    print("  Quixel Portal - Blender Addon Build Script")
    print("="*60)
    print(f"  Root directory: {ROOT_DIR}")
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Step 1: Check npm
        if not check_npm_available():
            print_error("Build failed: npm not available")
            return 1
        
        # Step 2: Build Electron app
        if not build_electron_app():
            print_error("Build failed: Electron build unsuccessful")
            return 1
        
        # Step 3: Verify build output
        if not verify_build_output():
            print_error("Build failed: Build output verification failed")
            return 1
        
        # Step 4: Copy files to staging
        if not copy_files_to_staging():
            print_error("Build failed: File copying unsuccessful")
            return 1
        
        # Step 5: Create zip file
        if not create_zip_file():
            print_error("Build failed: Zip creation unsuccessful")
            return 1
        
        # Step 6: Cleanup
        cleanup_staging()
        
        # Success!
        print_step("Build Completed Successfully!")
        print_success(f"Production zip created: {ZIP_NAME}")
        print_info("You can now install this zip file in Blender:")
        print_info("  Edit > Preferences > Add-ons > Install...")
        print_info(f"  Select: {ROOT_DIR / ZIP_NAME}")
        
        return 0
        
    except KeyboardInterrupt:
        print_error("\nBuild interrupted by user")
        cleanup_staging()
        return 1
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        cleanup_staging()
        return 1


if __name__ == "__main__":
    sys.exit(main())

