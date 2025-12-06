"""Addon Preferences - User settings for Quixel Portal.

This module provides the addon preferences panel for configuring settings
like the Quixel Bridge application path.
"""

import bpy
from bpy.types import AddonPreferences
from bpy.props import StringProperty
from pathlib import Path


class QuixelPortalPreferences(AddonPreferences):
    """Preferences for Quixel Portal addon."""

    bl_idname = "Quixel Portal"

    bridge_path: StringProperty(
        name="Bridge Path",
        description="Path to Quixel Bridge executable (Bridge.exe)",
        default="",
        subtype='FILE_PATH',
    )

    def draw(self, context):
        """Draw the preferences panel."""
        layout = self.layout

        box = layout.box()
        box.label(text="Quixel Bridge Configuration", icon='SETTINGS')

        row = box.row()
        row.prop(self, "bridge_path", text="Bridge Executable")

        # Show detected paths if custom path is not set
        if not self.bridge_path:
            box.separator()
            col = box.column(align=True)
            col.label(text="Auto-detected paths will be used:", icon='INFO')

            # List common paths
            common_paths = [
                Path(r"C:\Program Files\Bridge\Bridge.exe"),
                Path(r"C:\Program Files (x86)\Bridge\Bridge.exe"),
                Path.home() / "AppData" / "Local" / "Programs" / "Bridge" / "Bridge.exe",
            ]

            for path in common_paths:
                row = col.row()
                if path.exists():
                    row.label(text=f"  ✓ {path}", icon='CHECKMARK')
                else:
                    row.label(text=f"  ✗ {path}", icon='X')


def get_bridge_path():
    """Get the configured Bridge path from preferences.

    Returns:
        Path or None: Path to Bridge.exe if found, None otherwise
    """
    try:
        prefs = bpy.context.preferences.addons["Quixel Portal"].preferences
        if prefs.bridge_path and Path(prefs.bridge_path).exists():
            return Path(prefs.bridge_path)
    except:
        pass

    # Fall back to default search paths
    bridge_paths = [
        Path(r"C:\Program Files\Bridge\Bridge.exe"),
        Path(r"C:\Program Files (x86)\Bridge\Bridge.exe"),
        Path.home() / "AppData" / "Local" / "Programs" / "Bridge" / "Bridge.exe",
    ]

    for path in bridge_paths:
        if path.exists():
            return path

    return None


def register():
    """Register the preferences class."""
    bpy.utils.register_class(QuixelPortalPreferences)


def unregister():
    """Unregister the preferences class."""
    try:
        bpy.utils.unregister_class(QuixelPortalPreferences)
    except:
        pass
