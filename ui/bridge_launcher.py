"""Bridge Launcher - Operator to launch Quixel Bridge and claim active status.

This module provides the UI operator for the "Bridge" button that launches
Quixel Bridge and makes the current Blender instance the active import target.
"""

import bpy
import subprocess
import os
import time
from pathlib import Path


class QUIXEL_OT_launch_bridge(bpy.types.Operator):
    """Launch Quixel Bridge and make this instance active for imports"""

    bl_idname = "quixel.launch_bridge"
    bl_label = "Bridge"
    bl_description = "Launch Quixel Bridge and receive imports in this Blender instance"
    bl_options = {'REGISTER'}

    def execute(self, context):
        """Execute the operator."""
        try:
            # Claim active status for this Blender instance FIRST
            # This brings the window to foreground and sets it as active
            from ..communication.bridge_coordinator import get_coordinator
            coordinator = get_coordinator()

            if coordinator:
                coordinator.claim_active()
            else:
                from ..communication.bridge_coordinator import initialize_coordinator
                if initialize_coordinator():
                    coordinator = get_coordinator()
                    if coordinator:
                        coordinator.claim_active()

            # Check if Bridge is already running
            from ..communication.window_utils import (
                is_process_running,
                find_window_by_title,
                set_foreground_window,
                get_blender_window_handle
            )

            bridge_already_running = is_process_running("Bridge.exe")

            if bridge_already_running:
                # Bridge is running, bring it to foreground and keep it there
                bridge_hwnd = find_window_by_title("Bridge")
                if bridge_hwnd:
                    # Use more aggressive window activation
                    from ..communication.window_utils import activate_window_forcefully
                    activate_window_forcefully(bridge_hwnd)

                self.report({'INFO'}, "Bridge is now active - this Blender instance will receive imports")
            else:
                # Launch new Bridge instance
                bridge_process = self._launch_bridge()

                if not bridge_process:
                    self.report({'WARNING'}, "Could not find or launch Quixel Bridge")
                    return {'FINISHED'}

                # Wait a moment for Bridge to start
                time.sleep(0.5)

                # Re-activate Blender window after Bridge launches
                # This ensures Blender stays in foreground
                blender_hwnd = get_blender_window_handle()
                if blender_hwnd:
                    set_foreground_window(blender_hwnd)

                self.report({'INFO'}, "Bridge launched - this Blender instance is now active")

            return {'FINISHED'}

        except Exception as e:
            return {'FINISHED'}  # Still return finished, don't block user

    def _launch_bridge(self):
        """Launch Quixel Bridge application.

        Returns:
            subprocess.Popen or None: Process handle if launched successfully, None otherwise
        """
        # Get Bridge path from preferences
        from .preferences import get_bridge_path
        bridge_exe = get_bridge_path()

        if not bridge_exe:
            return None

        try:
            # Launch Bridge and return process handle
            process = subprocess.Popen([str(bridge_exe)],
                                     shell=True,
                                     stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)

            return process

        except Exception as e:
            return None


def register():
    """Register the operator."""
    bpy.utils.register_class(QUIXEL_OT_launch_bridge)


def unregister():
    """Unregister the operator."""
    try:
        bpy.utils.unregister_class(QUIXEL_OT_launch_bridge)
    except:
        pass
