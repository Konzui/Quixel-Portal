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

            print(f"🔍 DEBUG: Coordinator instance: {coordinator}")
            print(f"🔍 DEBUG: Coordinator mode: {coordinator.mode if coordinator else 'N/A'}")

            if coordinator:
                print("🎯 QuixelBridge: Claiming active status...")
                coordinator.claim_active()
            else:
                print("❌ QuixelBridge: No coordinator found - trying to initialize...")
                from ..communication.bridge_coordinator import initialize_coordinator
                if initialize_coordinator():
                    coordinator = get_coordinator()
                    if coordinator:
                        print("✅ QuixelBridge: Coordinator initialized, claiming active...")
                        coordinator.claim_active()
                    else:
                        print("❌ QuixelBridge: Failed to get coordinator after initialization")

            # Check if Bridge is already running
            from ..communication.window_utils import (
                is_process_running,
                find_window_by_title,
                set_foreground_window,
                get_blender_window_handle
            )

            bridge_already_running = is_process_running("Bridge.exe")
            print(f"🔍 DEBUG: Bridge already running: {bridge_already_running}")

            if bridge_already_running:
                # Bridge is running, bring it to foreground and keep it there
                print("ℹ️ QuixelBridge: Bridge already running, bringing to foreground...")

                bridge_hwnd = find_window_by_title("Bridge")
                if bridge_hwnd:
                    print(f"✅ QuixelBridge: Found Bridge window (HWND: {bridge_hwnd})")

                    # Use more aggressive window activation
                    from ..communication.window_utils import activate_window_forcefully
                    activate_window_forcefully(bridge_hwnd)

                    print("✅ QuixelBridge: Bridge window brought to foreground")
                else:
                    print("⚠️ QuixelBridge: Could not find Bridge window")

                self.report({'INFO'}, "Bridge is now active - this Blender instance will receive imports")
            else:
                # Launch new Bridge instance
                print("🚀 QuixelBridge: Launching new Bridge instance...")
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
                    print("🔄 QuixelBridge: Re-activating Blender window after Bridge launch...")
                    set_foreground_window(blender_hwnd)

                self.report({'INFO'}, "Bridge launched - this Blender instance is now active")

            return {'FINISHED'}

        except Exception as e:
            print(f"❌ Bridge launch error: {e}")
            import traceback
            traceback.print_exc()
            return {'FINISHED'}  # Still return finished, don't block user

    def _launch_bridge(self):
        """Launch Quixel Bridge application.

        Returns:
            subprocess.Popen or None: Process handle if launched successfully, None otherwise
        """
        # Common Bridge installation paths
        bridge_paths = [
            Path(r"C:\Program Files\Bridge\Bridge.exe"),
            Path(r"C:\Program Files (x86)\Bridge\Bridge.exe"),
            Path.home() / "AppData" / "Local" / "Programs" / "Bridge" / "Bridge.exe",
        ]

        # Find Bridge executable
        bridge_exe = None
        for path in bridge_paths:
            if path.exists():
                bridge_exe = path
                break

        if not bridge_exe:
            print("❌ QuixelBridge: Bridge.exe not found")
            return None

        try:
            # Launch Bridge and return process handle
            process = subprocess.Popen([str(bridge_exe)],
                                     shell=True,
                                     stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)

            print(f"✅ QuixelBridge: Launched Bridge (PID: {process.pid})")
            return process

        except Exception as e:
            print(f"❌ Failed to launch Bridge: {e}")
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
