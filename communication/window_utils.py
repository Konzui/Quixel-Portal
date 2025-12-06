"""Window management utilities using ctypes for Windows API.

This module provides functions to manage window handles, focus, and activation
using the Windows API via ctypes.
"""

import ctypes
from ctypes import wintypes
import time
import sys


# Windows API constants
SW_RESTORE = 9
SW_SHOW = 5
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

# Process snapshot constants
TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = -1


# Define Windows API function signatures
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


# EnumWindows callback type
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


# Process snapshot structures
class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.CHAR * 260)
    ]


def get_blender_window_handle():
    """Get the HWND (window handle) of the current Blender window.

    Returns:
        int: Window handle (HWND) or None if not found
    """
    import os
    current_pid = os.getpid()

    found_hwnd = None

    def enum_callback(hwnd, lparam):
        nonlocal found_hwnd

        # Get process ID for this window
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))

        # Check if it matches our process and is visible
        if process_id.value == current_pid:
            if user32.IsWindowVisible(hwnd):
                # Get window title to verify it's a main window
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buffer, length + 1)
                    title = buffer.value

                    # Blender windows contain "Blender" in title
                    if "Blender" in title:
                        found_hwnd = hwnd
                        return False  # Stop enumeration

        return True  # Continue enumeration

    # Enumerate all top-level windows
    callback = EnumWindowsProc(enum_callback)
    user32.EnumWindows(callback, 0)

    return found_hwnd


def set_foreground_window(hwnd):
    """Bring a window to the foreground using Windows API.

    This function uses multiple Windows API calls to ensure the window
    is properly activated and brought to the front.

    Args:
        hwnd: Window handle (HWND) to activate

    Returns:
        bool: True if successful, False otherwise
    """
    if not hwnd:
        print("⚠️ WindowUtils: Invalid window handle")
        return False

    try:
        # First, restore the window if it's minimized
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.1)  # Small delay for window to restore

        # Ensure window is visible
        user32.ShowWindow(hwnd, SW_SHOW)

        # Attempt to set as foreground window
        result = user32.SetForegroundWindow(hwnd)

        if not result:
            # If SetForegroundWindow fails, try alternative method
            # This can happen if another app has foreground lock
            print("⚠️ WindowUtils: SetForegroundWindow failed, trying alternative method")

            # Use keybd_event to simulate Alt key (releases foreground lock)
            VK_MENU = 0x12  # Alt key
            KEYEVENTF_KEYUP = 0x0002

            user32.keybd_event(VK_MENU, 0, 0, 0)  # Press Alt
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)  # Release Alt

            # Try again
            result = user32.SetForegroundWindow(hwnd)

        # Also set focus to ensure keyboard input goes to this window
        if result:
            user32.SetFocus(hwnd)
            print(f"✅ WindowUtils: Window {hwnd} brought to foreground")
            return True
        else:
            print(f"❌ WindowUtils: Failed to set foreground window {hwnd}")
            return False

    except Exception as e:
        print(f"❌ WindowUtils: Error setting foreground window: {e}")
        import traceback
        traceback.print_exc()
        return False


def activate_window_forcefully(hwnd):
    """Forcefully activate a window using multiple Windows API techniques.

    This uses a more aggressive approach to ensure the window stays in foreground.

    Args:
        hwnd: Window handle (HWND) to activate

    Returns:
        bool: True if successful
    """
    if not hwnd:
        print("⚠️ WindowUtils: Invalid window handle")
        return False

    try:
        print(f"🔍 DEBUG: Forcefully activating window {hwnd}...")

        # Check initial state
        is_minimized = user32.IsIconic(hwnd)
        is_visible = user32.IsWindowVisible(hwnd)
        print(f"🔍 DEBUG: Window state - Minimized: {is_minimized}, Visible: {is_visible}")

        # Step 1: If minimized, restore it properly
        if is_minimized:
            print("🔍 DEBUG: Window is minimized, restoring...")
            # Try multiple restore methods
            user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.2)
            user32.ShowWindow(hwnd, SW_SHOW)
            time.sleep(0.1)

            # Verify restoration
            still_minimized = user32.IsIconic(hwnd)
            print(f"🔍 DEBUG: After restore - Still minimized: {still_minimized}")

        # Step 2: Make absolutely sure window is visible and enabled
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.EnableWindow(hwnd, True)
        time.sleep(0.05)

        # Step 3: Get our thread and target thread
        current_thread = kernel32.GetCurrentThreadId()
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        print(f"🔍 DEBUG: Current thread: {current_thread}, Target thread: {target_thread}")

        # Step 4: Disable foreground lock timeout (requires registry change, but we can try)
        # Get current foreground window and its thread
        current_foreground = user32.GetForegroundWindow()
        foreground_thread = user32.GetWindowThreadProcessId(current_foreground, None) if current_foreground else 0

        print(f"🔍 DEBUG: Current foreground window: {current_foreground}, Thread: {foreground_thread}")

        # Step 5: Attach to both current foreground thread AND target thread
        attached_to_foreground = False
        attached_to_target = False

        if foreground_thread and foreground_thread != current_thread:
            result = user32.AttachThreadInput(current_thread, foreground_thread, True)
            attached_to_foreground = bool(result)
            print(f"🔍 DEBUG: Attached to foreground thread: {attached_to_foreground}")

        if target_thread != current_thread:
            result = user32.AttachThreadInput(current_thread, target_thread, True)
            attached_to_target = bool(result)
            print(f"🔍 DEBUG: Attached to target thread: {attached_to_target}")

        # Small delay for attachment to take effect
        time.sleep(0.05)

        # Step 6: Try multiple activation methods in sequence
        user32.BringWindowToTop(hwnd)
        time.sleep(0.03)

        user32.SetForegroundWindow(hwnd)
        time.sleep(0.03)

        user32.SetActiveWindow(hwnd)
        time.sleep(0.03)

        user32.SetFocus(hwnd)
        time.sleep(0.05)

        # Step 7: Use SwitchToThisWindow as final attempt (undocumented but effective)
        try:
            user32.SwitchToThisWindow(hwnd, True)
            print("🔍 DEBUG: Called SwitchToThisWindow")
        except:
            pass

        # Step 8: Detach threads
        if attached_to_foreground and foreground_thread:
            user32.AttachThreadInput(current_thread, foreground_thread, False)
            print("🔍 DEBUG: Detached from foreground thread")

        if attached_to_target:
            user32.AttachThreadInput(current_thread, target_thread, False)
            print("🔍 DEBUG: Detached from target thread")

        # Step 9: Final verification with multiple checks
        time.sleep(0.1)
        final_foreground = user32.GetForegroundWindow()
        is_still_minimized = user32.IsIconic(hwnd)
        is_now_visible = user32.IsWindowVisible(hwnd)

        print(f"🔍 DEBUG: Final state - Foreground window: {final_foreground}, Minimized: {is_still_minimized}, Visible: {is_now_visible}")

        success = (final_foreground == hwnd and not is_still_minimized and is_now_visible)

        if success:
            print(f"✅ WindowUtils: Window {hwnd} successfully activated and verified")
        else:
            print(f"⚠️ WindowUtils: Activation may have failed - Target: {hwnd}, Actual foreground: {final_foreground}")

        return success

    except Exception as e:
        print(f"❌ WindowUtils: Error forcefully activating window: {e}")
        import traceback
        traceback.print_exc()
        return False


def flash_window(hwnd, count=3):
    """Flash a window's title bar to get user attention.

    Args:
        hwnd: Window handle to flash
        count: Number of times to flash (default: 3)

    Returns:
        bool: True if successful
    """
    if not hwnd:
        return False

    try:
        for _ in range(count):
            user32.FlashWindow(hwnd, True)
            time.sleep(0.1)
        return True
    except Exception as e:
        print(f"⚠️ WindowUtils: Error flashing window: {e}")
        return False


def wait_for_process_window(pid, timeout=5.0, window_title_contains=None):
    """Wait for a process to create its main window.

    Args:
        pid: Process ID to wait for
        timeout: Maximum time to wait in seconds (default: 5.0)
        window_title_contains: Optional string that window title should contain

    Returns:
        int: Window handle (HWND) or None if timeout
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        found_hwnd = None

        def enum_callback(hwnd, lparam):
            nonlocal found_hwnd

            # Get process ID for this window
            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))

            # Check if it matches the target process
            if process_id.value == pid:
                if user32.IsWindowVisible(hwnd):
                    # Get window title
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buffer = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buffer, length + 1)
                        title = buffer.value

                        # Check title filter if provided
                        if window_title_contains is None or window_title_contains in title:
                            found_hwnd = hwnd
                            return False  # Stop enumeration

            return True  # Continue enumeration

        # Enumerate windows
        callback = EnumWindowsProc(enum_callback)
        user32.EnumWindows(callback, 0)

        if found_hwnd:
            print(f"✅ WindowUtils: Found window {found_hwnd} for PID {pid}")
            return found_hwnd

        # Sleep a bit before next check
        time.sleep(0.1)

    print(f"⚠️ WindowUtils: Timeout waiting for window (PID: {pid})")
    return None


def get_foreground_window():
    """Get the currently active foreground window.

    Returns:
        int: HWND of foreground window or None
    """
    try:
        hwnd = user32.GetForegroundWindow()
        return hwnd if hwnd else None
    except Exception as e:
        print(f"⚠️ WindowUtils: Error getting foreground window: {e}")
        return None


def get_window_title(hwnd):
    """Get the title text of a window.

    Args:
        hwnd: Window handle

    Returns:
        str: Window title or empty string
    """
    if not hwnd:
        return ""

    try:
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            return buffer.value
    except Exception as e:
        print(f"⚠️ WindowUtils: Error getting window title: {e}")

    return ""


def is_window_visible(hwnd):
    """Check if a window is visible.

    Args:
        hwnd: Window handle

    Returns:
        bool: True if window is visible
    """
    if not hwnd:
        return False

    try:
        return bool(user32.IsWindowVisible(hwnd))
    except Exception:
        return False


def find_window_by_title(title_contains):
    """Find a window by partial title match.

    Args:
        title_contains: String that should be in the window title

    Returns:
        int: Window handle (HWND) or None if not found
    """
    print(f"🔍 DEBUG: Searching for window with title containing '{title_contains}'...")

    found_hwnd = None
    found_titles = []

    def enum_callback(hwnd, lparam):
        nonlocal found_hwnd

        if user32.IsWindowVisible(hwnd):
            # Get window title
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                title = buffer.value

                # Track all window titles for debugging
                found_titles.append(title)

                # Check if title contains the search string
                if title_contains.lower() in title.lower():
                    found_hwnd = hwnd
                    print(f"✅ DEBUG: Found matching window: '{title}' (HWND: {hwnd})")
                    return False  # Stop enumeration

        return True  # Continue enumeration

    # Enumerate all top-level windows
    callback = EnumWindowsProc(enum_callback)
    user32.EnumWindows(callback, 0)

    if not found_hwnd:
        print(f"❌ DEBUG: No window found with title containing '{title_contains}'")
        print(f"🔍 DEBUG: First 10 visible window titles:")
        for i, title in enumerate(found_titles[:10]):
            print(f"  {i+1}. {title}")

    return found_hwnd


def is_process_running(process_name):
    """Check if a process is running by name using ctypes + Windows API.

    Args:
        process_name: Name of the executable (e.g., "Bridge.exe")

    Returns:
        bool: True if process is running
    """
    print(f"🔍 DEBUG: Checking if process '{process_name}' is running (using ctypes)...")

    # Normalize process name (ensure .exe extension)
    if not process_name.lower().endswith('.exe'):
        process_name = process_name + '.exe'

    try:
        # Create snapshot of all processes
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)

        if snapshot == INVALID_HANDLE_VALUE:
            print(f"❌ DEBUG: Failed to create process snapshot")
            return False

        # Initialize process entry structure
        pe32 = PROCESSENTRY32()
        pe32.dwSize = ctypes.sizeof(PROCESSENTRY32)

        # Get first process
        if not kernel32.Process32First(snapshot, ctypes.byref(pe32)):
            kernel32.CloseHandle(snapshot)
            print(f"❌ DEBUG: Failed to get first process")
            return False

        # Enumerate all processes
        found_count = 0
        process_list = []

        while True:
            # Get process name (decode from bytes)
            current_process = pe32.szExeFile.decode('utf-8', errors='ignore')
            process_list.append(current_process)

            # Check if matches target process
            if current_process.lower() == process_name.lower():
                found_count += 1
                print(f"✅ DEBUG: Found '{current_process}' (PID: {pe32.th32ProcessID})")

            # Get next process
            if not kernel32.Process32Next(snapshot, ctypes.byref(pe32)):
                break

        # Close snapshot handle
        kernel32.CloseHandle(snapshot)

        print(f"🔍 DEBUG: Found {found_count} instance(s) of '{process_name}'")
        print(f"🔍 DEBUG: Total processes scanned: {len(process_list)}")

        if found_count == 0:
            # Show similar process names for debugging
            similar = [p for p in process_list if 'bridge' in p.lower()]
            if similar:
                print(f"🔍 DEBUG: Processes with 'bridge' in name: {similar}")

        return found_count > 0

    except Exception as e:
        print(f"❌ DEBUG: Error checking process: {e}")
        import traceback
        traceback.print_exc()
        return False
