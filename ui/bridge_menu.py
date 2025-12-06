"""Bridge Menu - Add Bridge launcher to Blender's top header.

This module adds a button to the top header next to Scene/ViewLayer dropdowns.
"""

import bpy

# Track if button is registered (prevents duplicates across reloads)
_button_registered = False


def draw_bridge_button(self, context):
    """Draw Bridge button in the header."""
    layout = self.layout
    layout.separator()

    # Get coordinator to show active status
    try:
        from ..communication.bridge_coordinator import get_coordinator
        coordinator = get_coordinator()

        if coordinator and coordinator.is_active():
            # Active - use different color/icon
            layout.operator("quixel.launch_bridge", text="Bridge (Active)", icon='CHECKMARK')
        else:
            # Not active
            layout.operator("quixel.launch_bridge", text="Bridge", icon='WORLD')
    except:
        # Fallback if coordinator not available
        layout.operator("quixel.launch_bridge", text="Bridge", icon='WORLD')


def register():
    """Register the header button."""
    global _button_registered

    # First, clean up any existing instances
    unregister()

    # Add the button
    try:
        bpy.types.TOPBAR_HT_upper_bar.append(draw_bridge_button)
        _button_registered = True
        print("✅ Quixel Portal: Bridge button added to header")
    except Exception as e:
        print(f"⚠️ Quixel Portal: Failed to add Bridge button: {e}")


def unregister():
    """Unregister the header button."""
    global _button_registered

    # Keep trying to remove until it's no longer in the list (handles duplicates)
    removed_count = 0
    max_attempts = 10  # Prevent infinite loop

    for _ in range(max_attempts):
        try:
            bpy.types.TOPBAR_HT_upper_bar.remove(draw_bridge_button)
            removed_count += 1
        except (ValueError, AttributeError):
            # ValueError: not in list, AttributeError: doesn't exist
            break

    if removed_count > 0:
        _button_registered = False
        print(f"✅ Quixel Portal: Removed {removed_count} Bridge button(s) from header")
