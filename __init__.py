"""Quixel Portal - Blender Addon

A Blender addon that opens Quixel Megascans in a dedicated Electron-based browser
with persistent login sessions and seamless asset import.

This module serves as the entry point for Blender registration. All actual
functionality has been moved to specialized modules:

Modules:
    communication/: Electron IPC and file watching
        - electron_bridge.py: Instance management, process verification, IPC
        - file_watcher.py: Import request polling and validation
    
    operations/: Asset import and processing
        - portal_launcher.py: Electron app launching
        - fbx_importer.py: FBX file import operations
        - material_creator.py: Material creation from textures
        - asset_processor.py: Object organization and hierarchy
    
    utils/: Helper functions
        - naming.py: Naming conventions and JSON parsing
        - texture_loader.py: Texture loading utilities
        - validation.py: Path and asset validation
    
    ui/: Blender UI components
        - operators.py: Blender operators (UI entry points)
    
    main.py: High-level workflow orchestration

See ARCHITECTURE.md for detailed architecture documentation.
See DEVELOPER_GUIDE.md for extension and modification guide.
"""

bl_info = {
    "name": "Quixel Portal",
    "author": "Your Name",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "Topbar",
    "description": "Open Quixel Megascans Portal in dedicated browser",
    "category": "Import-Export",
}

import bpy
import bpy.utils.previews
from pathlib import Path

# Import operators from UI module
from .ui.operators import (
    QUIXEL_OT_cleanup_requests,
    QUIXEL_OT_open_portal,
    QUIXEL_OT_import_fbx,
)
from .ui.import_modal import QUIXEL_OT_import_confirm

# Import communication functions
from .communication.file_watcher import (
    setup_request_watcher,
    check_import_requests,
)
from .communication.electron_bridge import (
    write_heartbeat,
    cleanup_orphaned_requests,
    get_or_create_instance_id,
)

# Note: scene_manager import is done lazily to avoid issues during registration

# Global variable to store icons
custom_icons = None

# Track if we've registered in this session to prevent duplicates
_draw_function_registered = False


def _draw_quixel_button_impl(self, context):
    """Internal implementation of the draw function"""
    global custom_icons
    layout = self.layout
    
    # Create button with custom icon if available
    if custom_icons:
        try:
            # Check if icon exists and get its ID
            if "quixel_logo" in custom_icons:
                icon_item = custom_icons["quixel_logo"]
                if hasattr(icon_item, 'icon_id') and icon_item.icon_id != 0:
                    layout.operator("quixel.open_portal", text="Quixel Portal", icon_value=icon_item.icon_id, emboss=True)
                    return
        except Exception as e:
            print(f"⚠️ Quixel Portal: Error accessing icon: {e}")
    
    # Fallback button without custom icon
    layout.operator("quixel.open_portal", text="Quixel Portal", icon='WORLD', emboss=True)


# Create a wrapper function with a unique identifier
# This allows us to identify our function even after module reloads
def draw_quixel_button(self, context):
    """Draw function to add Quixel Portal button to topbar"""
    _draw_quixel_button_impl(self, context)


# Mark the wrapper with a unique attribute for identification
draw_quixel_button._quixel_portal_id = "quixel_portal_button_v1"


def _is_already_registered():
    """Check if our draw function is already registered by checking a persistent marker"""
    # Store a marker on the header type itself to track registration
    # This marker persists across module reloads (as long as Blender is running)
    marker_name = '_quixel_portal_button_registered'
    
    try:
        # Check if we've set a marker indicating registration
        if hasattr(bpy.types.TOPBAR_HT_upper_bar, marker_name):
            return getattr(bpy.types.TOPBAR_HT_upper_bar, marker_name) == True
    except:
        pass
    
    return False


def _mark_as_registered(registered=True):
    """Mark the header type to indicate our function is registered"""
    marker_name = '_quixel_portal_button_registered'
    try:
        setattr(bpy.types.TOPBAR_HT_upper_bar, marker_name, registered)
    except:
        pass


def register():
    """Register the addon with Blender"""
    global custom_icons, _draw_function_registered

    # Clean up any orphaned import requests from previous sessions
    cleanup_orphaned_requests()

    # Clean up any orphaned preview scenes from previous sessions
    # Import lazily to avoid initialization issues
    try:
        from .utils.scene_manager import cleanup_orphaned_preview_scenes
        cleanup_orphaned_preview_scenes()
    except Exception as e:
        print(f"⚠️ Could not cleanup orphaned preview scenes: {e}")

    # Register custom icons
    custom_icons = bpy.utils.previews.new()

    # Load the Quixel logo icon
    addon_dir = Path(__file__).parent
    icon_path = addon_dir / "electron_app" / "assets" / "icons" / "logo_48.png"

    if icon_path.exists():
        try:
            custom_icons.load("quixel_logo", str(icon_path), 'IMAGE')
            # Verify the icon was loaded successfully
            if "quixel_logo" in custom_icons:
                icon_item = custom_icons["quixel_logo"]
                if hasattr(icon_item, 'icon_id'):
                    print(f"✅ Quixel Portal: Icon loaded successfully from {icon_path} (ID: {icon_item.icon_id})")
                else:
                    print(f"⚠️ Quixel Portal: Icon loaded but icon_id not available")
            else:
                print(f"⚠️ Quixel Portal: Icon load failed - not in collection")
        except Exception as e:
            print(f"⚠️ Quixel Portal: Error loading icon: {e}")
    else:
        print(f"⚠️ Quixel Portal: Icon not found at {icon_path}")

    # Register the operators
    bpy.utils.register_class(QUIXEL_OT_cleanup_requests)
    bpy.utils.register_class(QUIXEL_OT_open_portal)
    bpy.utils.register_class(QUIXEL_OT_import_fbx)
    bpy.utils.register_class(QUIXEL_OT_import_confirm)

    # Register draw function to topbar
    # Use a persistent marker on the header type to track registration across module reloads
    # This marker persists as long as Blender is running, even if the module reloads

    # Check if already registered using the persistent marker
    if not _is_already_registered() and not _draw_function_registered:
        try:
            bpy.types.TOPBAR_HT_upper_bar.append(draw_quixel_button)
            _draw_function_registered = True
            _mark_as_registered(True)
            print("✅ Quixel Portal: Button added to topbar")
        except Exception as e:
            print(f"⚠️ Quixel Portal: Error adding button to topbar: {e}")
    else:
        if _is_already_registered():
            # If marker says registered but our flag doesn't, sync the flag
            _draw_function_registered = True
            print("ℹ️ Quixel Portal: Button already registered (detected from previous session)")
        else:
            print("ℹ️ Quixel Portal: Button already registered in this session (skipping)")

    # Start the background timer to check for import requests
    setup_request_watcher()

    # Start the background timer to write heartbeat
    if not bpy.app.timers.is_registered(write_heartbeat):
        bpy.app.timers.register(write_heartbeat)
        print("✅ Quixel Portal: Heartbeat writer started (writing every 30 seconds)")


def unregister():
    """Unregister the addon from Blender"""
    global custom_icons, _draw_function_registered

    # Get instance ID for cleanup
    instance_id = get_or_create_instance_id()

    # Stop the background timers
    if bpy.app.timers.is_registered(check_import_requests):
        bpy.app.timers.unregister(check_import_requests)
        print("✅ Quixel Portal: Import request monitor stopped")

    if bpy.app.timers.is_registered(write_heartbeat):
        bpy.app.timers.unregister(write_heartbeat)
        print("✅ Quixel Portal: Heartbeat writer stopped")

    # Clean up heartbeat file when Blender closes gracefully
    try:
        from .communication.electron_bridge import get_temp_dir
        if instance_id:
            temp_dir = get_temp_dir()
            heartbeat_file = temp_dir / f"heartbeat_{instance_id}.txt"
            if heartbeat_file.exists():
                heartbeat_file.unlink()
                print("✅ Quixel Portal: Heartbeat file deleted")
    except Exception as e:
        # Failed to delete heartbeat file, not critical
        pass

    # Remove draw function from topbar
    # Check both the session flag and the persistent marker
    if _draw_function_registered or _is_already_registered():
        try:
            bpy.types.TOPBAR_HT_upper_bar.remove(draw_quixel_button)
            _draw_function_registered = False
            _mark_as_registered(False)
        except:
            # If removal fails (e.g., function wasn't actually registered or was already removed),
            # reset both flags anyway
            _draw_function_registered = False
            _mark_as_registered(False)

    # Unregister the operators
    try:
        bpy.utils.unregister_class(QUIXEL_OT_cleanup_requests)
    except:
        pass

    try:
        bpy.utils.unregister_class(QUIXEL_OT_open_portal)
    except:
        pass

    try:
        bpy.utils.unregister_class(QUIXEL_OT_import_fbx)
    except:
        pass

    try:
        bpy.utils.unregister_class(QUIXEL_OT_import_confirm)
    except:
        pass

    # Remove custom icons
    if custom_icons:
        try:
            bpy.utils.previews.remove(custom_icons)
            custom_icons = None
        except:
            pass

    print("✅ Quixel Portal: Addon unregistered")


if __name__ == "__main__":
    register()
