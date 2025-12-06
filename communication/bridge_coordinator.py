"""Bridge Coordinator - Manages hub/client mode for this Blender instance.

This module determines whether the current instance should run as hub or client
and provides a unified interface for both modes.
"""

import bpy
import os
from typing import Optional

from .shared_state import SharedState
from .bridge_hub import QuixelBridgeHub
from .bridge_client import QuixelBridgeClient
from .window_utils import get_blender_window_handle, set_foreground_window


class BridgeCoordinator:
    """Coordinates hub/client mode for this Blender instance."""

    def __init__(self):
        """Initialize the coordinator."""
        self.state = SharedState()
        self.hub: Optional[QuixelBridgeHub] = None
        self.client: Optional[QuixelBridgeClient] = None
        self.mode: Optional[str] = None  # 'hub' or 'client'

        self.instance_pid = os.getpid()

    def initialize(self) -> bool:
        """Initialize as hub or client based on current state.

        Returns:
            bool: True if initialized successfully
        """
        # Check if a hub already exists
        if self.state.is_hub_alive():
            # Another instance is the hub, become a client
            return self._initialize_as_client()
        else:
            # No hub exists, become the hub
            return self._initialize_as_hub()

    def _initialize_as_hub(self) -> bool:
        """Initialize this instance as the hub.

        Returns:
            bool: True if successful
        """
        print(f"🎯 QuixelBridge: Initializing as HUB (PID: {self.instance_pid})")

        self.hub = QuixelBridgeHub()

        if self.hub.start():
            self.mode = 'hub'
            print(f"✅ QuixelBridge: Running as HUB")
            return True
        else:
            print(f"❌ QuixelBridge: Failed to start as hub")
            self.hub = None
            return False

    def _initialize_as_client(self) -> bool:
        """Initialize this instance as a client.

        Returns:
            bool: True if successful
        """
        # Get instance name from current blend file
        instance_name = self._get_instance_name()

        print(f"🎯 QuixelBridge: Initializing as CLIENT (PID: {self.instance_pid}, Name: {instance_name})")

        self.client = QuixelBridgeClient(instance_name)

        if self.client.start():
            self.mode = 'client'
            print(f"✅ QuixelBridge: Running as CLIENT")
            return True
        else:
            print(f"❌ QuixelBridge: Failed to start as client")
            self.client = None
            return False

    def shutdown(self):
        """Shutdown the coordinator."""
        if self.hub:
            self.hub.stop()
            self.hub = None

        if self.client:
            self.client.stop()
            self.client = None

        self.mode = None
        print(f"✅ QuixelBridge: Coordinator shutdown")

    def claim_active(self) -> bool:
        """Claim active status for this instance and bring window to foreground.

        Returns:
            bool: True if successful
        """
        try:
            # Get window handle for this Blender instance
            hwnd = get_blender_window_handle()

            if not hwnd:
                print("⚠️ QuixelBridge: Could not get window handle")
                # Continue anyway, just without window activation

            if self.mode == 'hub':
                # Hub claims active by setting itself as active
                instance_info = {
                    'pid': self.instance_pid,
                    'name': self._get_instance_name(),
                    'hwnd': hwnd
                }

                self.hub.active_instance = instance_info
                self.hub.state.set_active_instance(instance_info)

                # Bring window to foreground
                if hwnd:
                    set_foreground_window(hwnd)

                print(f"✅ QuixelBridge: Hub claimed active status (HWND: {hwnd})")
                return True

            elif self.mode == 'client':
                # Client claims active (includes window activation)
                return self.client.claim_active()

            else:
                print("❌ QuixelBridge: Cannot claim active - not initialized")
                return False

        except Exception as e:
            print(f"❌ QuixelBridge: Error claiming active: {e}")
            import traceback
            traceback.print_exc()
            return False

    def release_active(self) -> bool:
        """Release active status for this instance.

        Returns:
            bool: True if successful
        """
        if self.mode == 'hub':
            # Hub releases active status
            if self.hub.active_instance and self.hub.active_instance.get('pid') == self.instance_pid:
                self.hub.active_instance = None
                self.hub.state.set_active_instance(None)
                print(f"✅ QuixelBridge: Hub released active status")
                return True
            return False

        elif self.mode == 'client':
            # Client sends RELEASE_ACTIVE to hub
            return self.client.release_active()

        else:
            print(f"❌ QuixelBridge: Cannot release active - not initialized")
            return False

    def is_active(self) -> bool:
        """Check if this instance is currently active.

        Returns:
            bool: True if active
        """
        if self.mode == 'hub':
            return (self.hub.active_instance and
                    self.hub.active_instance.get('pid') == self.instance_pid)

        elif self.mode == 'client':
            return self.client.is_active()

        return False

    def route_import_data(self, import_requests: list):
        """Route import data (only for hub mode).

        Args:
            import_requests: List of import request dictionaries
        """
        if self.mode == 'hub':
            self.hub.route_import_data(import_requests)
        else:
            print(f"⚠️ QuixelBridge: Only hub can route import data")

    def _get_instance_name(self) -> str:
        """Get a display name for this Blender instance.

        Returns:
            str: Instance name
        """
        # Get blend file name (handle restricted context during registration)
        try:
            blend_file = bpy.data.filepath

            if blend_file:
                from pathlib import Path
                return f"Blender - {Path(blend_file).name}"
            else:
                return f"Blender - Unsaved (PID: {self.instance_pid})"
        except AttributeError:
            # bpy.data is restricted during registration
            return f"Blender - Initializing (PID: {self.instance_pid})"


# Global coordinator instance
_coordinator: Optional[BridgeCoordinator] = None


def get_coordinator() -> Optional[BridgeCoordinator]:
    """Get the global coordinator instance.

    Returns:
        BridgeCoordinator or None
    """
    return _coordinator


def initialize_coordinator() -> bool:
    """Initialize the global coordinator.

    Returns:
        bool: True if successful
    """
    global _coordinator

    if _coordinator:
        print("ℹ️ QuixelBridge: Coordinator already initialized")
        return True

    _coordinator = BridgeCoordinator()
    return _coordinator.initialize()


def shutdown_coordinator():
    """Shutdown the global coordinator."""
    global _coordinator

    if _coordinator:
        _coordinator.shutdown()
        _coordinator = None
