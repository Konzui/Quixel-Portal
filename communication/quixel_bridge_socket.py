"""Quixel Bridge socket communication module.

This module handles direct socket communication with Quixel Bridge application,
replacing the Electron-based file-watching system.
"""

import json
import socket
import threading
import bpy
from pathlib import Path

# Global variable to store received data (thread-safe access via lock)
_bridge_data_lock = threading.Lock()
_pending_imports = []  # List of import requests waiting to be processed
_socket_listener = None  # Global reference to socket listener thread
_import_in_progress = False  # Flag to prevent concurrent imports


def parse_bridge_json(bridge_data):
    """Parse Quixel Bridge JSON data and convert to addon format.
    
    Args:
        bridge_data: Bytes or string containing JSON data from Quixel Bridge
        
    Returns:
        list: List of import request dictionaries, each containing:
            - asset_path: Path to asset directory
            - asset_name: Name of the asset
            - thumbnail_path: Path to thumbnail (if found)
            - glacier_setup: Whether to show Glacier setup (default: True)
    """
    import_requests = []
    
    try:
        # Decode bytes to string if needed
        if isinstance(bridge_data, bytes):
            json_string = bridge_data.decode('utf-8')
        else:
            json_string = bridge_data
        
        # Parse JSON - Quixel Bridge sends an array of assets
        json_array = json.loads(json_string)

        if not isinstance(json_array, list):
            # If it's a single object, wrap it in a list
            json_array = [json_array]

        # Process each asset in the array
        for asset_data in json_array:
            try:
                # Extract asset path (required)
                asset_path = asset_data.get("path")
                if not asset_path:
                    continue

                # Convert to Path object and verify it exists
                asset_dir = Path(asset_path)
                if not asset_dir.exists():
                    continue

                # Extract asset name
                asset_name = asset_data.get("name")
                if not asset_name:
                    # Fallback to directory name
                    asset_name = asset_dir.name

                # Clean up asset name (replace spaces with underscores)
                asset_name = asset_name.replace(" ", "_")

                # Extract texture resolution from Bridge export
                texture_resolution = asset_data.get("resolution")

                # Find thumbnail in asset directory
                thumbnail_path = None
                if asset_dir.exists():
                    # Look for common thumbnail file patterns
                    thumbnail_patterns = [
                        "*_preview.*",
                        "*preview.*",
                        "*thumbnail.*",
                        "*thumb.*",
                    ]
                    
                    for pattern in thumbnail_patterns:
                        matches = list(asset_dir.glob(pattern))
                        if matches:
                            # Filter to image extensions
                            image_extensions = ['.png', '.jpg', '.jpeg', '.tga', '.bmp']
                            for match in matches:
                                if match.suffix.lower() in image_extensions:
                                    thumbnail_path = str(match)
                                    break
                        
                        if thumbnail_path:
                            break
                
                # Create import request
                import_request = {
                    "asset_path": str(asset_dir),
                    "asset_name": asset_name,
                    "thumbnail_path": thumbnail_path,
                    "glacier_setup": True,  # Default to enabled
                    "texture_resolution": texture_resolution,  # Pass resolution to importer
                }
                
                import_requests.append(import_request)

            except Exception as e:
                import traceback
                traceback.print_exc()
                continue
        
        return import_requests

    except json.JSONDecodeError as e:
        return []
    except Exception as e:
        import traceback
        traceback.print_exc()
        return []


def _importer_callback(received_data):
    """Callback function called when socket receives data.

    This function is called from the socket thread, so we need to
    safely queue the import requests for processing in the main thread.

    Args:
        received_data: Raw bytes data received from socket
    """
    try:
        # Parse the JSON data
        import_requests = parse_bridge_json(received_data)

        if not import_requests:
            return

        # Route through coordinator if available (hub will route to active instance)
        from .bridge_coordinator import get_coordinator

        coordinator = get_coordinator()

        if coordinator and coordinator.mode == 'hub':
            # Hub mode: route to active instance
            coordinator.route_import_data(import_requests)
        else:
            # Fallback: queue directly (backwards compatibility)
            with _bridge_data_lock:
                _pending_imports.extend(import_requests)

    except Exception as e:
        import traceback
        traceback.print_exc()


class QuixelBridgeSocketListener(threading.Thread):
    """Socket listener thread for Quixel Bridge communication.
    
    This thread listens on port 24981 for JSON data from Quixel Bridge
    and queues import requests for processing in the main Blender thread.
    """
    
    def __init__(self):
        threading.Thread.__init__(self)
        self.host = 'localhost'
        self.port = 24981
        self.running = True
        self.daemon = True  # Thread will exit when main program exits
        self.socket_ = None
    
    def run(self):
        """Start the socket listener loop."""
        try:
            # Create socket
            self.socket_ = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # Set socket options for reuse
            self.socket_.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Bind to host and port
            try:
                self.socket_.bind((self.host, self.port))
            except OSError as e:
                self.running = False
                return
            
            # Main listening loop
            while self.running:
                try:
                    # Listen for connections (backlog of 5)
                    self.socket_.listen(5)
                    
                    # Accept connection
                    client, addr = self.socket_.accept()

                    # Receive data
                    buffer_size = 4096 * 2
                    total_data = b""
                    
                    # First receive
                    data = client.recv(buffer_size)
                    
                    # Check for shutdown signal
                    if data == b'Bye Megascans':
                        self.running = False
                        client.close()
                        break
                    
                    if data:
                        total_data += data
                        
                        # Keep receiving until connection closes
                        while self.running:
                            data = client.recv(buffer_size)

                            if data == b'Bye Megascans':
                                self.running = False
                                break
                            
                            if data:
                                total_data += data
                            else:
                                # Connection closed, process received data
                                if total_data:
                                    _importer_callback(total_data)
                                break
                        
                        client.close()
                    
                except socket.error as e:
                    if self.running:
                        pass
                    break
                except Exception as e:
                    if self.running:
                        import traceback
                        traceback.print_exc()
                    break

        except Exception as e:
            import traceback
            traceback.print_exc()
        finally:
            if self.socket_:
                try:
                    self.socket_.close()
                except:
                    pass
    
    def stop(self):
        """Stop the socket listener."""
        self.running = False
        
        # Close socket to break out of accept() call
        if self.socket_:
            try:
                self.socket_.close()
            except:
                pass


def start_socket_listener(force: bool = False):
    """Start the Quixel Bridge socket listener thread.

    Note: In multi-instance mode, only the hub should run the socket listener.
    This function will automatically check the coordinator mode unless force=True.

    Args:
        force: If True, start listener regardless of coordinator mode

    Returns:
        bool: True if listener started successfully, False otherwise
    """
    global _socket_listener

    # Check if listener is already running
    if _socket_listener and _socket_listener.is_alive():
        return True

    # Check if we should start the listener (only hub instances)
    if not force:
        from .bridge_coordinator import get_coordinator

        coordinator = get_coordinator()

        if coordinator and coordinator.mode != 'hub':
            return True  # Not an error - clients don't need socket listener

    try:
        # Create and start listener thread
        _socket_listener = QuixelBridgeSocketListener()
        _socket_listener.start()

        # Give it a moment to start
        import time
        time.sleep(0.1)

        if _socket_listener.is_alive():
            return True
        else:
            return False

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False


def stop_socket_listener():
    """Stop the Quixel Bridge socket listener thread."""
    global _socket_listener
    
    if _socket_listener and _socket_listener.is_alive():
        _socket_listener.stop()
        
        # Wait for thread to finish (with timeout)
        _socket_listener.join(timeout=2.0)

    _socket_listener = None


def check_pending_imports():
    """Check for pending import requests and process them.
    
    This function should be called from a Blender timer to safely
    process imports in the main thread. Processes ONE import per call
    to avoid blocking the main thread.
    
    Returns:
        float: Time interval in seconds until next check
    """
    global _pending_imports, _import_in_progress
    
    # Don't process if an import is already in progress
    if _import_in_progress:
        return 0.1  # Check again soon
    
    # Check if there are pending imports
    with _bridge_data_lock:
        if not _pending_imports:
            return 1.0  # Continue checking every second when idle
        
        # Get only the first import to process (one at a time)
        import_request = _pending_imports.pop(0)
    
    # Mark import as in progress
    _import_in_progress = True
    
    try:
        asset_path = import_request.get("asset_path")
        thumbnail_path = import_request.get("thumbnail_path")
        asset_name = import_request.get("asset_name")
        glacier_setup = import_request.get("glacier_setup", True)
        texture_resolution = import_request.get("texture_resolution")

        # Import the asset using the main import function
        # This is a blocking operation, but we only do one at a time
        from ..main import import_asset
        
        result = import_asset(
            asset_path=asset_path,
            thumbnail_path=thumbnail_path or '',
            asset_name=asset_name or '',
            glacier_setup=glacier_setup,
            texture_resolution=texture_resolution
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        # Mark import as complete
        _import_in_progress = False
    
    # Check again soon if there are more imports, otherwise wait longer
    with _bridge_data_lock:
        if _pending_imports:
            return 0.1  # Process next import soon
        else:
            return 1.0  # Wait longer when idle

