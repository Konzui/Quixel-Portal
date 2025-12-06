"""Quixel Portal - Blender Addon

A Blender addon that connects directly to Quixel Bridge via socket communication
for seamless asset import with shader setup and geometry.

This module serves as the entry point for Blender registration. All actual
functionality has been moved to specialized modules:

Modules:
    communication/: Quixel Bridge socket communication
        - quixel_bridge_socket.py: Socket listener and JSON parsing
    
    operations/: Asset import and processing
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
    "location": "File > Import",
    "description": "Import Quixel Megascans assets directly from Quixel Bridge",
    "category": "Import-Export",
}

import bpy
from pathlib import Path

# Import operators from UI module
from .ui.operators import (
    QUIXEL_OT_cleanup_requests,
    QUIXEL_OT_import_fbx,
)
from .ui.import_modal import QUIXEL_OT_import_confirm
from .ui.bridge_launcher import QUIXEL_OT_launch_bridge
from .ui.bridge_panel import QUIXEL_PT_bridge_panel
from .ui import bridge_menu

# Import socket communication functions
from .communication.quixel_bridge_socket import (
    start_socket_listener,
    stop_socket_listener,
    check_pending_imports,
)

# Import coordinator functions
from .communication.bridge_coordinator import (
    initialize_coordinator,
    shutdown_coordinator,
)


def register():
    """Register the addon with Blender"""
    # Clean up any orphaned preview scenes from previous sessions
    # Import lazily to avoid initialization issues
    try:
        from .utils.scene_manager import cleanup_orphaned_preview_scenes
        cleanup_orphaned_preview_scenes()
    except Exception as e:
        print(f"⚠️ Quixel Portal: Could not cleanup orphaned preview scenes: {e}")

    # Register the operators
    bpy.utils.register_class(QUIXEL_OT_cleanup_requests)
    bpy.utils.register_class(QUIXEL_OT_import_fbx)
    bpy.utils.register_class(QUIXEL_OT_import_confirm)
    bpy.utils.register_class(QUIXEL_OT_launch_bridge)

    # Register the UI panel
    bpy.utils.register_class(QUIXEL_PT_bridge_panel)
    print("✅ Quixel Portal: UI panel registered")

    # Register the menu item
    bridge_menu.register()
    print("✅ Quixel Portal: Menu item registered")

    # Initialize the multi-instance coordinator (hub or client mode)
    if initialize_coordinator():
        print("✅ Quixel Portal: Multi-instance coordinator initialized")
    else:
        print("⚠️ Quixel Portal: Failed to initialize coordinator")

    # Start the Quixel Bridge socket listener (only for hub instances)
    if start_socket_listener():
        print("✅ Quixel Portal: Socket listener started on port 24981")
    else:
        print("⚠️ Quixel Portal: Socket listener not started (client mode or error)")

    # Start the background timer to check for pending imports
    if not bpy.app.timers.is_registered(check_pending_imports):
        bpy.app.timers.register(check_pending_imports)
        print("✅ Quixel Portal: Import request monitor started")

    print("✅ Quixel Portal: Addon registered")


def unregister():
    """Unregister the addon from Blender"""
    # Stop the background timer
    if bpy.app.timers.is_registered(check_pending_imports):
        bpy.app.timers.unregister(check_pending_imports)
        print("✅ Quixel Portal: Import request monitor stopped")

    # Shutdown the coordinator
    shutdown_coordinator()

    # Stop the socket listener
    stop_socket_listener()

    # Unregister the menu item
    bridge_menu.unregister()

    # Unregister the UI panel
    try:
        bpy.utils.unregister_class(QUIXEL_PT_bridge_panel)
    except:
        pass

    # Unregister the operators
    try:
        bpy.utils.unregister_class(QUIXEL_OT_cleanup_requests)
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

    try:
        bpy.utils.unregister_class(QUIXEL_OT_launch_bridge)
    except:
        pass

    print("✅ Quixel Portal: Addon unregistered")


if __name__ == "__main__":
    register()
