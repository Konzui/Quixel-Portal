"""Icon Loader - Manages custom addon icons.

This module handles loading and registering custom icons for the addon.
"""

import bpy
import bpy.utils.previews
from pathlib import Path

# Global variable to store icon previews
preview_collections = {}


def get_icon_id(icon_name):
    """Get the icon ID for a custom icon.

    Args:
        icon_name: Name of the icon file (without extension)

    Returns:
        int: Icon ID for use in UI, or 0 if not found
    """
    pcoll = preview_collections.get("main")
    if pcoll and icon_name in pcoll:
        return pcoll[icon_name].icon_id
    return 0


def register():
    """Register icon previews."""
    pcoll = bpy.utils.previews.new()

    # Get addon directory and icons path
    addon_dir = Path(__file__).parent.parent
    icons_dir = addon_dir / "assets" / "icons"

    # Load all PNG icons from the icons directory
    if icons_dir.exists():
        for icon_file in icons_dir.glob("*.png"):
            icon_name = icon_file.stem  # Filename without extension
            pcoll.load(icon_name, str(icon_file), 'IMAGE')

    preview_collections["main"] = pcoll


def unregister():
    """Unregister icon previews."""
    for pcoll in preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()
