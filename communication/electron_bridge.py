"""Electron bridge module for IPC communication.

This module handles all direct communication with the Electron application,
including instance management, process verification, and file-based IPC.
"""

import os
import sys
import json
import time
import uuid
import subprocess
import tempfile
from pathlib import Path

# Try to import psutil for process verification
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("⚠️ Quixel Portal: psutil not available, using fallback process verification")

# Global instance ID storage (per Blender process)
_instance_id = None

# Track last portal open time for debouncing
_last_portal_open_time = 0


def get_or_create_instance_id():
    """Get or create a Blender instance ID.
    
    Returns:
        str: UUID string representing this Blender instance
    """
    global _instance_id
    
    if not _instance_id:
        _instance_id = str(uuid.uuid4())
        print(f"🔑 Quixel Portal: Generated new instance ID: {_instance_id}")
    
    return _instance_id


def get_temp_dir():
    """Get the temporary directory for IPC communication.
    
    Returns:
        Path: Path to the quixel_portal temp directory
    """
    return Path(tempfile.gettempdir()) / "quixel_portal"


def check_electron_running(instance_id):
    """Check if Electron is already running for this instance.
    
    Args:
        instance_id: The Blender instance ID
        
    Returns:
        tuple: (is_running: bool, pid: int or None, lock_file: Path or None)
    """
    temp_dir = get_temp_dir()
    lock_file = temp_dir / f"electron_lock_{instance_id}.txt"
    
    if not lock_file.exists():
        return False, None, None
    
    # Check if lock file is stale (older than 2 minutes)
    try:
        file_mtime = lock_file.stat().st_mtime
        file_age = time.time() - file_mtime
        
        if file_age > 120:  # 2 minutes
            print(f"⚠️ Quixel Portal: Stale lock file detected (age: {file_age:.0f}s), removing...")
            lock_file.unlink()
            return False, None, None
    except Exception as e:
        print(f"⚠️ Quixel Portal: Error checking lock file age: {e}")
        return False, None, None
    
    # Read lock file to get PID
    try:
        with open(lock_file, 'r') as f:
            lock_data = json.load(f)
        
        electron_pid = lock_data.get('pid')
        
        if not electron_pid:
            print(f"⚠️ Quixel Portal: Lock file has no PID, assuming stale")
            lock_file.unlink()
            return False, None, None
        
        # Verify process is actually running
        process_alive = _verify_process_running(electron_pid)
        
        if not process_alive:
            print(f"🧹 Quixel Portal: Removing stale lock file (process is dead)")
            lock_file.unlink()
            return False, None, None
        
        return True, electron_pid, lock_file
        
    except (json.JSONDecodeError, KeyError) as e:
        print(f"⚠️ Quixel Portal: Failed to read lock file: {e}")
        lock_file.unlink()
        return False, None, None
    except Exception as e:
        print(f"⚠️ Quixel Portal: Error checking lock file: {e}")
        return False, None, None


def _verify_process_running(pid):
    """Verify if a process with the given PID is actually running.
    
    Args:
        pid: Process ID to check
        
    Returns:
        bool: True if process is running, False otherwise
    """
    if PSUTIL_AVAILABLE:
        try:
            process = psutil.Process(pid)
            process_name = process.name().lower()
            
            # Check for both development (electron) and production (quixel portal.exe) names
            if 'electron' in process_name or 'quixel' in process_name or 'portal' in process_name:
                print(f"✅ Quixel Portal: Verified Electron process is alive (PID: {pid}, name: {process.name()})")
                return True
        except psutil.NoSuchProcess:
            print(f"⚠️ Quixel Portal: Process {pid} no longer exists")
            return False
        except psutil.AccessDenied:
            print(f"⚠️ Quixel Portal: Cannot verify process {pid} (access denied), assuming alive")
            return True
    else:
        # Fallback: Use OS-specific process check
        if sys.platform == "win32":
            try:
                result = subprocess.run(
                    f'tasklist /FI "PID eq {pid}" /NH',
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding='cp850',
                    errors='ignore',
                    timeout=3,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                output = result.stdout.strip() if result.stdout else ""
                
                if str(pid) in output and result.returncode == 0:
                    print(f"✅ Quixel Portal: Process {pid} is running (tasklist check)")
                    return True
            except (subprocess.TimeoutExpired, UnicodeDecodeError, Exception):
                # If check fails, assume process is alive to be safe
                return True
        else:
            # Linux/Mac: Use kill -0 signal
            try:
                os.kill(pid, 0)  # Signal 0 doesn't kill, just checks if process exists
                print(f"✅ Quixel Portal: Process {pid} is running (kill -0 check)")
                return True
            except OSError:
                return False
            except Exception:
                return True
    
    return False


def send_show_window_signal(instance_id):
    """Send a signal to Electron to show its window.
    
    Args:
        instance_id: The Blender instance ID
        
    Returns:
        bool: True if signal was acknowledged, False if timeout
    """
    temp_dir = get_temp_dir()
    signal_file = temp_dir / f"show_window_{instance_id}.txt"
    
    # Create temp directory if it doesn't exist
    if not temp_dir.exists():
        temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Write signal file with timestamp
    with open(signal_file, 'w') as f:
        f.write(str(time.time()))
    
    print(f"👁️ Quixel Portal: Sending show window signal...")
    
    # Poll for up to 3 seconds (30 checks * 100ms)
    max_attempts = 30
    for attempt in range(max_attempts):
        time.sleep(0.1)  # Wait 100ms between checks
        
        if not signal_file.exists():
            # Signal was processed by Electron!
            print(f"✅ Quixel Portal: Signal acknowledged by Electron (took {(attempt + 1) * 100}ms)")
            return True
    
    # Timeout - signal was not processed
    print(f"⚠️ Quixel Portal: Timeout waiting for signal acknowledgment")
    
    # Clean up signal file
    if signal_file.exists():
        signal_file.unlink()
    
    return False


def launch_electron_app(instance_id):
    """Launch the Electron application.
    
    Args:
        instance_id: The Blender instance ID to pass to Electron
        
    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    # Get the addon directory
    addon_dir = Path(__file__).parent.parent
    electron_app_dir = addon_dir / "electron_app"
    
    # Path to the built executable
    exe_path = electron_app_dir / "build" / "win-unpacked" / "Quixel Portal.exe"
    
    # Check if executable exists
    if exe_path.exists():
        try:
            subprocess.Popen(
                [str(exe_path), '--blender-instance', instance_id],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print(f"🚀 Quixel Portal: Launched Electron executable")
            return True, None
        except Exception as e:
            error_msg = f"Failed to launch Quixel Portal: {str(e)}"
            print(f"❌ Quixel Portal: {error_msg}")
            return False, error_msg
    else:
        # Fallback to npm start if exe doesn't exist
        if not electron_app_dir.exists():
            error_msg = "Electron app not found. Please ensure the addon is properly installed."
            print(f"❌ Quixel Portal: {error_msg}")
            return False, error_msg
        
        node_modules = electron_app_dir / "node_modules"
        if not node_modules.exists():
            error_msg = "Electron app not built. Please run 'npm install' in the electron_app directory."
            print(f"❌ Quixel Portal: {error_msg}")
            return False, error_msg
        
        try:
            if sys.platform == "win32":
                npm_cmd = "npm.cmd"
            else:
                npm_cmd = "npm"
            
            subprocess.Popen(
                [npm_cmd, "start", "--", "--blender-instance", instance_id],
                cwd=str(electron_app_dir),
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print(f"🚀 Quixel Portal: Launched Electron via npm")
            return True, None
        except Exception as e:
            error_msg = f"Failed to launch Quixel Portal: {str(e)}"
            print(f"❌ Quixel Portal: {error_msg}")
            return False, error_msg


def write_heartbeat(instance_id=None):
    """Write heartbeat file to signal Electron that Blender is still alive.

    This function checks if the Electron portal is still running before writing
    the heartbeat. If the portal is no longer running, it stops the heartbeat timer.

    Args:
        instance_id: Optional Blender instance ID. If not provided, will be retrieved automatically.

    Returns:
        float or None: Time interval in seconds until next heartbeat (30.0), or None to stop the timer
    """
    try:
        # Get instance ID if not provided (for timer callbacks)
        if instance_id is None:
            instance_id = get_or_create_instance_id()

        if not instance_id:
            return 30.0  # Check again in 30 seconds

        # Check if Electron is still running - if not, stop the heartbeat
        is_running, pid, lock_file = check_electron_running(instance_id)
        if not is_running:
            print(f"🛑 Quixel Portal: Electron not running, stopping heartbeat timer")
            # Clean up our heartbeat file
            temp_dir = get_temp_dir()
            heartbeat_file = temp_dir / f"heartbeat_{instance_id}.txt"
            if heartbeat_file.exists():
                try:
                    heartbeat_file.unlink()
                    print(f"🧹 Quixel Portal: Cleaned up heartbeat file")
                except Exception:
                    pass
            # Return None to unregister the timer
            return None

        temp_dir = get_temp_dir()

        # Create directory if it doesn't exist
        if not temp_dir.exists():
            temp_dir.mkdir(parents=True, exist_ok=True)

        # Write heartbeat file with timestamp and PID
        heartbeat_file = temp_dir / f"heartbeat_{instance_id}.txt"
        heartbeat_data = {
            "timestamp": time.time(),
            "blender_pid": os.getpid(),
            "instance_id": instance_id
        }

        with open(heartbeat_file, 'w') as f:
            json.dump(heartbeat_data, f, indent=2)

        print(f"💓 Quixel Portal: Heartbeat written (timestamp: {heartbeat_data['timestamp']:.0f})")

        # Clean up old heartbeat files (>2 hours old)
        try:
            current_time = time.time()
            for old_file in temp_dir.glob("heartbeat_*.txt"):
                # Skip our own file
                if old_file == heartbeat_file:
                    continue

                # Check file age
                try:
                    file_age = current_time - old_file.stat().st_mtime
                    if file_age > 7200:  # 2 hours in seconds
                        old_file.unlink()
                        print(f"🧹 Quixel Portal: Cleaned up old heartbeat file: {old_file.name}")
                except Exception:
                    # Failed to delete old file, not critical
                    pass
        except Exception:
            # Failed to clean up, not critical
            pass

    except Exception as e:
        print(f"⚠️ Quixel Portal: Failed to write heartbeat: {e}")

    # Continue the timer - write heartbeat every 30 seconds
    return 30.0


def read_import_request():
    """Read import request file from Electron.
    
    Returns:
        dict or None: Request data if file exists and is valid, None otherwise
    """
    temp_dir = get_temp_dir()
    request_file = temp_dir / "import_request.json"
    
    if not request_file.exists():
        return None
    
    try:
        with open(request_file, 'r') as f:
            request_data = json.load(f)
        return request_data
    except Exception as e:
        print(f"⚠️ Quixel Portal: Failed to read import request: {e}")
        return None


def write_import_complete(asset_path, asset_name, thumbnail_path=None):
    """Write completion file to notify Electron app.
    
    Args:
        asset_path: Path to the imported asset directory
        asset_name: Name of the imported asset
        thumbnail_path: Optional path to thumbnail image
    """
    try:
        temp_dir = get_temp_dir()
        
        # Ensure directory exists
        if not temp_dir.exists():
            temp_dir.mkdir(parents=True, exist_ok=True)
        
        completion_file = temp_dir / "import_complete.json"
        
        completion_data = {
            "asset_path": str(asset_path),
            "asset_name": asset_name,
            "thumbnail": str(thumbnail_path) if thumbnail_path else None,
            "timestamp": time.time()
        }
        
        with open(completion_file, 'w') as f:
            json.dump(completion_data, f, indent=2)
        
        print(f"✅ Quixel Portal: Notified Electron of import completion for '{asset_name}'")
        
    except Exception as e:
        print(f"⚠️ Quixel Portal: Failed to notify import completion: {e}")


def cleanup_orphaned_requests():
    """Clean up any orphaned import request files on addon reload/registration."""
    try:
        temp_dir = get_temp_dir()
        if not temp_dir.exists():
            return
        
        request_file = temp_dir / "import_request.json"
        
        if request_file.exists():
            try:
                request_file.unlink()
                print(f"🧹 Quixel Portal: Cleaned up import request file on addon reload")
            except Exception as e:
                print(f"⚠️ Quixel Portal: Failed to delete import request: {e}")
    
    except Exception as e:
        print(f"⚠️ Quixel Portal: Error during import request cleanup: {e}")


def check_debounce():
    """Check if enough time has passed since last portal open (debouncing).
    
    Returns:
        tuple: (can_proceed: bool, time_since_last: float)
    """
    global _last_portal_open_time
    
    current_time = time.time()
    time_since_last = current_time - _last_portal_open_time
    
    if time_since_last < 2.0:  # Ignore clicks within 2 seconds
        return False, time_since_last
    
    _last_portal_open_time = current_time
    return True, time_since_last

