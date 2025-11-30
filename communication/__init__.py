"""Communication module for Quixel Bridge socket communication.

This module handles direct socket communication with Quixel Bridge application,
replacing the Electron-based file-watching system.
"""

from .quixel_bridge_socket import (
    start_socket_listener,
    stop_socket_listener,
    check_pending_imports,
    parse_bridge_json,
)

__all__ = [
    'start_socket_listener',
    'stop_socket_listener',
    'check_pending_imports',
    'parse_bridge_json',
]

