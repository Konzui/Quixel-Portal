"""Shared state management for multi-instance Blender coordination.

This module provides file-based state persistence to track the hub instance
and active instance across multiple Blender processes.
"""

import json
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any
import threading


class SharedState:
    """Manages shared state file for multi-instance coordination."""

    def __init__(self):
        """Initialize shared state manager."""
        # Use Windows temp directory for state file
        self.state_file = Path(os.environ.get('TEMP', '/tmp')) / 'QuixelBridge_Hub.json'
        # Note: No threading lock needed - file system provides atomicity via temp file + rename

    def read(self) -> Optional[Dict[str, Any]]:
        """Read current state from file.

        Returns:
            dict: State dictionary or None if file doesn't exist or is invalid
        """
        try:
            if not self.state_file.exists():
                return None

            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)

            # Validate state has required fields
            if 'hub_pid' not in state:
                return None

            return state

        except (json.JSONDecodeError, IOError, OSError) as e:
            print(f"⚠️ QuixelBridge: Error reading state file: {e}")
            return None

    def write(self, state: Dict[str, Any]) -> bool:
        """Write state to file atomically (no locking needed - file system provides atomicity).

        Args:
            state: State dictionary to write

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Ensure parent directory exists
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            # Write atomically by writing to temp file then renaming
            temp_file = self.state_file.with_suffix('.tmp')

            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)

            # Atomic replace (Windows handles this)
            temp_file.replace(self.state_file)

            return True

        except Exception as e:
            print(f"Error writing state file: {e}")
            return False

    def update(self, updates: Dict[str, Any]) -> bool:
        """Update specific fields in state file atomically.

        Args:
            updates: Dictionary of fields to update

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Read current state
            state = self.read() or {}

            # Apply updates
            state.update(updates)
            state['last_update'] = time.time()

            # Write back
            return self.write(state)

        except Exception as e:
            print(f"Error updating state: {e}")
            return False

    def is_hub_alive(self, timeout: float = 5.0) -> bool:
        """Check if hub process is still alive.

        Args:
            timeout: How old (in seconds) the last update can be

        Returns:
            bool: True if hub appears alive, False otherwise
        """
        state = self.read()

        if not state:
            return False

        # Check if hub PID exists
        hub_pid = state.get('hub_pid')
        if not hub_pid:
            return False

        # Check process exists (Windows-specific)
        try:
            import psutil
            return psutil.pid_exists(hub_pid)
        except ImportError:
            # Fallback: check timestamp
            last_update = state.get('last_update', 0)
            age = time.time() - last_update
            return age < timeout

    def get_active_instance(self) -> Optional[Dict[str, Any]]:
        """Get information about the currently active instance.

        Returns:
            dict: Active instance info (pid, name, etc.) or None
        """
        state = self.read()

        if not state:
            return None

        return state.get('active_instance')

    def set_active_instance(self, instance_info: Optional[Dict[str, Any]]) -> bool:
        """Set the active instance.

        Args:
            instance_info: Dictionary with instance details (pid, name, hwnd, etc.) or None to clear

        Returns:
            bool: True if successful
        """
        return self.update({'active_instance': instance_info})

    def cleanup(self) -> bool:
        """Remove state file (called when hub shuts down).

        Returns:
            bool: True if successful
        """
        try:
            if self.state_file.exists():
                self.state_file.unlink()
                print(f"✅ QuixelBridge: Cleaned up state file")
            return True
        except OSError as e:
            print(f"⚠️ QuixelBridge: Error cleaning up state file: {e}")
            return False

    def register_hub(self, hub_pid: int) -> bool:
        """Register this instance as the hub.

        Args:
            hub_pid: Process ID of hub instance

        Returns:
            bool: True if successful
        """
        state = {
            'hub_pid': hub_pid,
            'last_update': time.time(),
            'active_instance': None,
            'registered_instances': []
        }

        return self.write(state)

    def register_instance(self, instance_pid: int, instance_name: str) -> bool:
        """Register a new Blender instance with the hub.

        Args:
            instance_pid: Process ID of the instance
            instance_name: Display name (e.g., "Blender - scene.blend")

        Returns:
            bool: True if successful
        """
        state = self.read() or {}

        instances = state.get('registered_instances', [])

        # Check if already registered
        for inst in instances:
            if inst['pid'] == instance_pid:
                # Update existing
                inst['name'] = instance_name
                inst['last_seen'] = time.time()
                return self.write(state)

        # Add new instance
        instances.append({
            'pid': instance_pid,
            'name': instance_name,
            'last_seen': time.time()
        })

        state['registered_instances'] = instances
        return self.write(state)

    def unregister_instance(self, instance_pid: int) -> bool:
        """Unregister a Blender instance.

        Args:
            instance_pid: Process ID of the instance to remove

        Returns:
            bool: True if successful
        """
        state = self.read() or {}

        instances = state.get('registered_instances', [])

        # Remove instance with matching PID
        instances = [inst for inst in instances if inst['pid'] != instance_pid]

        state['registered_instances'] = instances

        # If this was the active instance, clear it
        active = state.get('active_instance')
        if active and active.get('pid') == instance_pid:
            state['active_instance'] = None

        return self.write(state)
