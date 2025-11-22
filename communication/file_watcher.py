"""File watcher module for monitoring import requests from Electron.

This module handles polling for import requests, validation, and cleanup.
"""

import time
from pathlib import Path
import bpy

from .electron_bridge import (
    get_or_create_instance_id,
    read_import_request,
    get_temp_dir,
)


def validate_request(request_data, instance_id):
    """Validate an import request.
    
    Args:
        request_data: Dictionary containing request data
        instance_id: Current Blender instance ID
        
    Returns:
        tuple: (is_valid: bool, reason: str or None)
    """
    if not request_data:
        return False, "No request data"
    
    # Check if request has timestamp and if it's too old (>30 seconds), delete it
    request_timestamp = request_data.get('timestamp', 0)
    current_time = time.time()
    age_seconds = current_time - (request_timestamp / 1000.0 if request_timestamp > 1e10 else request_timestamp)
    
    if age_seconds > 30:
        return False, f"Request is stale ({age_seconds:.1f}s old)"
    
    # If this Blender instance has NO instance ID, it means the user
    # never opened Quixel Portal from this instance
    if not instance_id:
        # If request is old enough (stale), delete it
        # If it's recent, another instance might still need it
        if age_seconds > 5:
            return False, f"No portal opened in this instance, request is {age_seconds:.1f}s old"
        else:
            return False, "No portal opened in this instance (ignoring recent request)"
    
    # If the request has NO instance ID (old format), delete it immediately
    request_instance_id = request_data.get('blender_instance_id')
    if not request_instance_id:
        return False, "Malformed request (no instance ID)"
    
    # Check if this request is for THIS specific Blender instance
    if request_instance_id != instance_id:
        return False, f"Request is for different instance (my: {instance_id}, request: {request_instance_id})"
    
    # Request is valid
    return True, None


def cleanup_stale_requests():
    """Clean up stale import request files."""
    temp_dir = get_temp_dir()
    request_file = temp_dir / "import_request.json"
    
    if not request_file.exists():
        return
    
    try:
        request_data = read_import_request()
        if not request_data:
            # File exists but couldn't be read, delete it
            request_file.unlink()
            return
        
        # Check if request is stale
        request_timestamp = request_data.get('timestamp', 0)
        current_time = time.time()
        age_seconds = current_time - (request_timestamp / 1000.0 if request_timestamp > 1e10 else request_timestamp)
        
        if age_seconds > 30:
            print(f"🗑️ Quixel Portal: Deleting stale import request ({age_seconds:.1f}s old)")
            request_file.unlink()
    except Exception as e:
        print(f"⚠️ Quixel Portal: Error during import request cleanup: {e}")


def check_import_requests():
    """Background timer function to check for import requests from Electron.
    
    This function is registered as a Blender timer and called periodically.
    
    Returns:
        float: Time interval in seconds until next check (1.0)
    """
    instance_id = get_or_create_instance_id()
    temp_dir = get_temp_dir()
    request_file = temp_dir / "import_request.json"
    
    if not request_file.exists():
        return 1.0  # Continue checking
    
    try:
        # Read the import request
        request_data = read_import_request()
        
        if not request_data:
            # File exists but couldn't be read, delete it
            request_file.unlink()
            return 1.0
        
        asset_path = request_data.get('asset_path')
        thumbnail_path = request_data.get('thumbnail')
        asset_name = request_data.get('asset_name')
        
        # Validate the request
        is_valid, reason = validate_request(request_data, instance_id)
        
        if not is_valid:
            if reason and "stale" in reason.lower():
                # Delete stale requests
                try:
                    request_file.unlink()
                    print(f"🗑️ Quixel Portal: {reason}")
                except Exception:
                    pass
            elif reason and "different instance" in reason.lower():
                # Don't delete - let the correct instance handle it
                print(f"🔒 Quixel Portal: {reason}")
            else:
                # Delete malformed requests
                try:
                    request_file.unlink()
                    print(f"⚠️ Quixel Portal: {reason}")
                except Exception:
                    pass
            return 1.0  # Continue checking
        
        # Request is valid for this instance
        print(f"📥 Quixel Portal: Import request received for THIS instance:")
        print(f"   Asset path: {asset_path}")
        print(f"   Thumbnail: {thumbnail_path}")
        print(f"   Asset name: {asset_name}")
        print(f"   Instance ID: {instance_id}")
        
        # CRITICAL: Delete request file FIRST to prevent infinite loops
        # Even if import fails, we don't want to keep retrying
        try:
            request_file.unlink()
            print(f"🗑️ Quixel Portal: Deleted import request file")
        except Exception as del_error:
            print(f"⚠️ Quixel Portal: Failed to delete request file: {del_error}")
        
        # Now process the import
        if asset_path and Path(asset_path).exists():
            try:
                # Import the asset using the main import function
                # Use relative import to avoid conflicts with other addons
                from ..main import import_asset
                result = import_asset(
                    asset_path=asset_path,
                    thumbnail_path=thumbnail_path or '',
                    asset_name=asset_name or ''
                )
                
                if result == {'FINISHED'}:
                    print(f"✅ Quixel Portal: Successfully imported asset from {asset_path}")
                else:
                    print(f"⚠️ Quixel Portal: Import returned: {result}")
            except Exception as import_error:
                print(f"❌ Quixel Portal: Import failed: {import_error}")
                import traceback
                traceback.print_exc()
        else:
            print(f"⚠️ Quixel Portal: Asset path doesn't exist: {asset_path}")
    
    except Exception as e:
        print(f"❌ Quixel Portal: Error processing import request: {e}")
        import traceback
        traceback.print_exc()
        # Try to delete the file anyway to prevent repeated errors
        try:
            if request_file.exists():
                request_file.unlink()
                print(f"🗑️ Quixel Portal: Deleted request file after error")
        except Exception as cleanup_error:
            print(f"⚠️ Quixel Portal: Could not delete request file: {cleanup_error}")
    
    # Continue the timer
    return 1.0  # Check every 1 second


def setup_request_watcher():
    """Set up the request watcher timer.
    
    Returns:
        bool: True if timer was registered, False if already registered
    """
    if not bpy.app.timers.is_registered(check_import_requests):
        bpy.app.timers.register(check_import_requests)
        print("✅ Quixel Portal: Import request monitor started")
        return True
    return False

