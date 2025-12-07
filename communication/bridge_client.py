"""QuixelBridge Client - Secondary instance connector.

The client runs in secondary Blender instances and communicates with the hub
via file-based state to register, claim active status, and receive import data.
"""

import os
import threading
import time
from typing import Optional

from .shared_state import SharedState
from .window_utils import get_blender_window_handle, set_foreground_window


class QuixelBridgeClient:
    """Client for secondary Blender instances using file-based coordination."""

    def __init__(self, instance_name: str):
        """Initialize the client.

        Args:
            instance_name: Display name for this instance (e.g., "Blender - scene.blend")
        """
        self.instance_name = instance_name
        self.instance_pid = os.getpid()

        self.state = SharedState()
        self.running = False
        self.poll_thread: Optional[threading.Thread] = None

        self._is_active = False

    def start(self) -> bool:
        """Start the client and register with hub via shared state.

        Returns:
            bool: True if started successfully
        """
        if self.running:
            return True

        # Check if hub exists
        if not self.state.is_hub_alive():
            print("❌ QuixelBridge Client: No hub found")
            return False

        # Register with hub via shared state
        if not self.state.register_instance(self.instance_pid, self.instance_name):
            print("❌ QuixelBridge Client: Failed to register with hub")
            return False

        print(f"✅ QuixelBridge Client: Registered as {self.instance_name} (PID: {self.instance_pid})")

        # Start polling thread for state changes and import data
        self.running = True
        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()

        return True

    def stop(self):
        """Stop the client and unregister from hub."""
        if not self.running:
            return

        self.running = False

        # Unregister from hub via shared state
        self.state.unregister_instance(self.instance_pid)

        # Wait for polling thread
        if self.poll_thread:
            self.poll_thread.join(timeout=2.0)

        print("✅ QuixelBridge Client: Stopped")

    def claim_active(self) -> bool:
        """Claim active status and bring window to foreground.

        Returns:
            bool: True if successful
        """
        # Get window handle for this Blender instance
        hwnd = get_blender_window_handle()

        if not hwnd:
            print("⚠️ QuixelBridge Client: Could not get window handle")

        instance_info = {
            'pid': self.instance_pid,
            'name': self.instance_name,
            'hwnd': hwnd
        }

        if self.state.set_active_instance(instance_info):
            self._is_active = True

            # Bring window to foreground
            if hwnd:
                set_foreground_window(hwnd)

            print(f"✅ QuixelBridge Client: Claimed active status (HWND: {hwnd})")
            return True
        else:
            print(f"❌ QuixelBridge Client: Failed to claim active status")
            return False

    def release_active(self) -> bool:
        """Release active status.

        Returns:
            bool: True if successful
        """
        # Only release if we are currently active
        active = self.state.get_active_instance()
        if active and active.get('pid') == self.instance_pid:
            if self.state.set_active_instance(None):
                self._is_active = False
                print(f"✅ QuixelBridge Client: Released active status")
                return True

        self._is_active = False
        return False

    def is_active(self) -> bool:
        """Check if this instance is currently active.

        Returns:
            bool: True if active
        """
        return self._is_active

    def _poll_loop(self):
        """Poll shared state for active status changes and pending imports."""
        while self.running:
            try:
                # Read shared state
                state = self.state.read()
                if not state:
                    time.sleep(0.5)
                    continue

                # Check if we're the active instance
                active_instance = state.get('active_instance')
                if active_instance and active_instance.get('pid') == self.instance_pid:
                    if not self._is_active:
                        self._is_active = True

                    # Check for pending imports
                    import_key = f'pending_import_{self.instance_pid}'
                    pending_import = state.get(import_key)

                    if pending_import:
                        import_requests = pending_import.get('import_requests', [])

                        if import_requests:

                            # Process imports
                            self._process_imports(import_requests)

                            # Clear pending import from state
                            state.pop(import_key, None)
                            self.state.write(state)
                else:
                    if self._is_active:
                        self._is_active = False

                # Poll interval
                time.sleep(0.5)

            except Exception as e:
                if self.running:
                    print(f"⚠️ QuixelBridge Client: Error in polling loop: {e}")
                    import traceback
                    traceback.print_exc()

    def _process_imports(self, import_requests: list):
        """Process import requests received from hub.

        Args:
            import_requests: List of import request dictionaries
        """
        # Queue imports using the existing mechanism
        from .quixel_bridge_socket import _bridge_data_lock, _pending_imports

        with _bridge_data_lock:
            _pending_imports.extend(import_requests)

        print(f"✅ QuixelBridge Client: Queued {len(import_requests)} import(s) for processing")
