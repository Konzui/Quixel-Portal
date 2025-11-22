"""Communication module for Electron-Blender IPC.

This module handles all communication between the Blender addon and the Electron application,
including file-based IPC, instance management, and heartbeat monitoring.
"""

from .electron_bridge import (
    get_or_create_instance_id,
    check_electron_running,
    launch_electron_app,
    send_show_window_signal,
    write_heartbeat,
    read_import_request,
    write_import_complete,
    get_temp_dir,
    cleanup_orphaned_requests,
    check_debounce,
)
from .file_watcher import (
    setup_request_watcher,
    validate_request,
    cleanup_stale_requests,
    check_import_requests,
)

__all__ = [
    'get_or_create_instance_id',
    'check_electron_running',
    'launch_electron_app',
    'send_show_window_signal',
    'write_heartbeat',
    'read_import_request',
    'write_import_complete',
    'get_temp_dir',
    'cleanup_orphaned_requests',
    'check_debounce',
    'setup_request_watcher',
    'validate_request',
    'cleanup_stale_requests',
    'check_import_requests',
]

