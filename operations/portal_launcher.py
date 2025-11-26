"""Portal launcher module for opening the Electron application.

This module handles launching the Electron app and managing the window.
"""

import bpy
from ..communication.electron_bridge import (
    get_or_create_instance_id,
    check_electron_running,
    send_show_window_signal,
    launch_electron_app,
    check_debounce,
    write_heartbeat,
)


def open_quixel_portal(context):
    """Open Quixel Portal in dedicated browser.
    
    This is the main entry point for opening the Electron application.
    It handles debouncing, instance management, and launching.
    
    Args:
        context: Blender context
        
    Returns:
        dict: Blender operator result {'FINISHED'} or {'CANCELLED'}
    """
    # Check debouncing
    can_proceed, time_since_last = check_debounce()
    if not can_proceed:
        return {'CANCELLED'}
    
    # Get or create instance ID
    instance_id = get_or_create_instance_id()
    
    # Check if Electron is already running
    is_running, pid, lock_file = check_electron_running(instance_id)
    
    if is_running:
        print(f"🔒 Quixel Portal: Electron already running for this instance")
        
        # Send show window signal
        if send_show_window_signal(instance_id):
            return {'FINISHED'}
        else:
            # Timeout - remove lock file and launch new instance
            print(f"🧹 Quixel Portal: Removing unresponsive lock file")
            if lock_file:
                try:
                    lock_file.unlink()
                except Exception:
                    pass
    
    # Launch new Electron instance
    print(f"🚀 Quixel Portal: Launching new Electron instance...")
    success, error_msg = launch_electron_app(instance_id)

    if success:
        # Start the heartbeat timer now that the portal is open
        if not bpy.app.timers.is_registered(write_heartbeat):
            bpy.app.timers.register(write_heartbeat)
            print("✅ Quixel Portal: Heartbeat writer started (writing every 30 seconds)")

        return {'FINISHED'}
    else:
        # Report error to user
        if hasattr(context, 'report'):
            context.report({'ERROR'}, error_msg or "Failed to launch Quixel Portal")
        return {'CANCELLED'}

