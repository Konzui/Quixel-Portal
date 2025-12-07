"""QuixelBridge Hub - Primary instance coordinator.

The hub runs in the first Blender instance and coordinates import routing
between Quixel Bridge and multiple Blender instances using file-based state.
"""

import os
import threading
import time
from typing import Optional, List, Dict, Any

from .shared_state import SharedState


class QuixelBridgeHub:
    """Hub instance that coordinates multi-instance Blender setup via file-based state."""

    def __init__(self):
        """Initialize the hub."""
        self.running = False
        self.heartbeat_thread: Optional[threading.Thread] = None

        self.state = SharedState()
        self.registered_instances: List[Dict[str, Any]] = []
        self.active_instance: Optional[Dict[str, Any]] = None

        # Get current process ID
        self.hub_pid = os.getpid()

    def start(self) -> bool:
        """Start the hub with file-based coordination.

        Returns:
            bool: True if started successfully
        """
        if self.running:
            return True

        # Register as hub in shared state (no pipe name needed)
        if not self.state.register_hub(self.hub_pid):
            print("❌ QuixelBridge Hub: Failed to register in shared state")
            return False

        # Start heartbeat thread for state management
        self.running = True
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()

        return True

    def stop(self):
        """Stop the hub."""
        if not self.running:
            return

        self.running = False

        # Wait for heartbeat thread to finish
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=2.0)

        # Cleanup shared state
        self.state.cleanup()

    def route_import_data(self, import_requests: list):
        """Route import data from Bridge to the active instance.

        Args:
            import_requests: List of import request dictionaries
        """
        if not self.active_instance:
            print("⚠️ QuixelBridge Hub: No active instance to route import to")
            # Hub itself will handle the import
            self._handle_import_locally(import_requests)
            return

        active_pid = self.active_instance.get('pid')
        active_name = self.active_instance.get('name', 'Unknown')


        # If active instance is the hub itself, handle locally
        if active_pid == self.hub_pid:
            self._handle_import_locally(import_requests)
            return

        # Send to secondary instance via file-based state
        self._send_import_to_instance(active_pid, import_requests)

    def _handle_import_locally(self, import_requests: list):
        """Handle import in the hub instance itself.

        Args:
            import_requests: List of import requests to process
        """

        # Queue imports using the existing mechanism
        from .quixel_bridge_socket import _bridge_data_lock, _pending_imports

        with _bridge_data_lock:
            _pending_imports.extend(import_requests)

    def _send_import_to_instance(self, target_pid: int, import_requests: list):
        """Send import data to a secondary instance via shared state.

        Args:
            target_pid: Process ID of target instance
            import_requests: Import requests to send
        """
        # Store the import data in shared state for the target instance to poll
        self.state.update({
            f'pending_import_{target_pid}': {
                'import_requests': import_requests,
                'timestamp': time.time()
            }
        })

    def _sync_state_from_file(self):
        """Synchronize local state from shared state file."""
        state = self.state.read()
        if not state:
            return

        # Sync active instance
        active_instance = state.get('active_instance')
        if active_instance != self.active_instance:
            self.active_instance = active_instance

        # Sync registered instances
        self.registered_instances = state.get('registered_instances', [])

    def _heartbeat_loop(self):
        """Heartbeat loop to update shared state and cleanup dead instances."""
        while self.running:
            try:
                # Sync state from file (to pick up changes from clients)
                self._sync_state_from_file()

                # Update shared state timestamp
                self.state.update({'last_update': time.time()})

                # Cleanup dead instances (check process existence)
                self._cleanup_dead_instances()

                # Sleep for heartbeat interval
                time.sleep(1.0)

            except Exception as e:
                if self.running:
                    print(f"⚠️ QuixelBridge Hub: Error in heartbeat: {e}")

    def _cleanup_dead_instances(self):
        """Remove instances whose processes no longer exist."""
        try:
            import psutil

            alive_instances = []

            for inst in self.registered_instances:
                pid = inst['pid']

                if psutil.pid_exists(pid):
                    alive_instances.append(inst)
                else:
                    print(f"🧹 QuixelBridge Hub: Removed dead instance PID {pid}")

                    # If dead instance was active, clear it
                    if self.active_instance and self.active_instance.get('pid') == pid:
                        self.active_instance = None
                        self.state.set_active_instance(None)

            self.registered_instances = alive_instances

        except ImportError:
            # psutil not available, skip cleanup
            pass
