"""Import confirmation toolbar using draw handlers (no modal operator).

This module provides a simpler approach using draw handlers and mouse
tracking without requiring a modal operator.
"""

import bpy
from .import_toolbar import ImportToolbar


# Global reference to active toolbar
_active_toolbar = None
_draw_handler = None
_mouse_tracker_running = False


def get_active_toolbar():
    """Get the currently active toolbar instance."""
    global _active_toolbar
    return _active_toolbar


def _draw_toolbar():
    """Draw callback for the toolbar."""
    global _active_toolbar
    if _active_toolbar:
        _active_toolbar.draw()


def _track_mouse():
    """Timer callback to track mouse position and handle events."""
    global _active_toolbar, _mouse_tracker_running

    if _active_toolbar is None or not _active_toolbar.visible:
        _mouse_tracker_running = False
        return None  # Stop timer

    # Get mouse position from window
    try:
        for window in bpy.context.window_manager.windows:
            # Check each area for mouse position
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    # Get mouse position relative to area
                    # We need to check if mouse is in this area
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            # Tag for redraw if toolbar is visible
                            area.tag_redraw()
                            break
                    break
    except:
        pass

    return 0.05  # Continue tracking at 20fps


def _handle_mouse_event(scene):
    """Depsgraph update handler to catch mouse events."""
    global _active_toolbar

    if _active_toolbar is None or not _active_toolbar.visible:
        return

    try:
        # Get current mouse position
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            # We can't easily get mouse events here, but we'll handle
                            # them through the wm.event_timer approach instead
                            pass
    except:
        pass


class QUIXEL_OT_import_confirm(bpy.types.Operator):
    """Import confirmation toolbar operator.

    This operator uses draw handlers instead of modal operation
    to avoid context issues when called from timers.
    """
    bl_idname = "quixel.import_confirm"
    bl_label = "Confirm Import"
    bl_options = {'INTERNAL'}

    # Class variables to store state
    _timer = None
    _last_mouse_x = -1
    _last_mouse_y = -1
    _mouse_pressed = False

    def modal(self, context, event):
        """Handle modal events for mouse interaction."""
        global _active_toolbar

        if _active_toolbar is None or not _active_toolbar.visible:
            self.cancel(context)
            return {'CANCELLED'}

        # Check if modifier keys are pressed (ALT, SHIFT, CTRL)
        # If so, always allow viewport navigation
        has_modifiers = event.alt or event.shift or event.ctrl or event.oskey
        
        # Handle mouse movement
        if event.type == 'MOUSEMOVE':
            # If modifiers are pressed, always pass through for viewport navigation
            if has_modifiers:
                return {'PASS_THROUGH'}
            
            # Handle mouse move in toolbar (returns True if dragging)
            is_dragging = _active_toolbar.handle_mouse_move(
                event.mouse_region_x,
                event.mouse_region_y
            )

            # Tag for redraw if context is valid
            if context.area:
                context.area.tag_redraw()

            # Only consume if we're actually dragging the slider
            # Don't consume just because mouse button is pressed (might be viewport drag)
            if is_dragging:
                return {'RUNNING_MODAL'}
            else:
                # Pass through to allow normal Blender interaction
                return {'PASS_THROUGH'}

        # Handle mouse button press
        elif event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                # If modifiers are pressed, always pass through for viewport navigation
                if has_modifiers:
                    return {'PASS_THROUGH'}
                
                self._mouse_pressed = True
                # Only consume the event if we clicked on a widget
                if _active_toolbar.handle_mouse_down(
                    event.mouse_region_x,
                    event.mouse_region_y
                ):
                    if context.area:
                        context.area.tag_redraw()
                    return {'RUNNING_MODAL'}
                else:
                    # Click was outside toolbar, pass through
                    self._mouse_pressed = False  # Reset since we didn't click on toolbar
                    return {'PASS_THROUGH'}

            elif event.value == 'RELEASE':
                # If modifiers are pressed, always pass through
                if has_modifiers:
                    self._mouse_pressed = False
                    return {'PASS_THROUGH'}
                
                # Only handle release if we were tracking a press
                if self._mouse_pressed:
                    self._mouse_pressed = False
                    # Only consume the event if we released on a widget
                    if _active_toolbar.handle_mouse_up(
                        event.mouse_region_x,
                        event.mouse_region_y
                    ):
                        if context.area:
                            context.area.tag_redraw()
                        return {'RUNNING_MODAL'}
                    else:
                        # Release was outside toolbar, pass through
                        return {'PASS_THROUGH'}
                else:
                    # We weren't tracking this press, pass through
                    return {'PASS_THROUGH'}

        # Allow viewport navigation
        elif event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'RIGHTMOUSE'}:
            return {'PASS_THROUGH'}

        # ESC key cancels
        elif event.type == 'ESC' and event.value == 'PRESS':
            if _active_toolbar:
                _active_toolbar._handle_cancel(None)
            return {'CANCELLED'}

        # Pass through all other events to allow normal Blender interaction
        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        """Start the operator."""
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        """Clean up on cancel."""
        if self._timer:
            try:
                wm = context.window_manager
                wm.event_timer_remove(self._timer)
            except:
                pass
            self._timer = None


def show_import_toolbar(context, imported_objects, imported_materials, materials_before_import, original_scene=None, temp_scene=None):
    """Show the import confirmation toolbar.

    This function sets up the toolbar with draw handlers.

    Args:
        context: Blender context
        imported_objects: List of imported objects for cleanup
        imported_materials: List of created materials for cleanup
        materials_before_import: Set of material names before import
        original_scene: Optional reference to original scene (for scene switching)
        temp_scene: Optional reference to temporary preview scene

    Returns:
        dict: {'FINISHED'}
    """
    global _active_toolbar, _draw_handler, _mouse_tracker_running

    # Always use fresh context to avoid stale references
    try:
        context = bpy.context
    except:
        print("⚠️ Could not get valid context")
        return {'CANCELLED'}
    
    # Validate context before proceeding
    try:
        if context.window_manager is None:
            print("⚠️ Context window_manager is invalid")
            return {'CANCELLED'}
        if context.scene is None or context.scene.name not in bpy.data.scenes:
            print("⚠️ Context scene is invalid")
            return {'CANCELLED'}
    except (AttributeError, KeyError, ReferenceError):
        print("⚠️ Context validation failed")
        return {'CANCELLED'}

    # Find a 3D viewport
    area_3d = None
    try:
        for window in context.window_manager.windows:
            if window is None or window.screen is None:
                continue
            for area in window.screen.areas:
                if area is None or area.type != 'VIEW_3D':
                    continue
                area_3d = area
                break
            if area_3d:
                break
    except (AttributeError, ReferenceError):
        pass

    if not area_3d:
        print("⚠️ No 3D Viewport found - cannot show toolbar")
        return {'CANCELLED'}

    # Create fake context for toolbar initialization
    class FakeContext:
        def __init__(self, area):
            self.area = area

    fake_ctx = FakeContext(area_3d)

    # Create toolbar
    _active_toolbar = ImportToolbar()
    _active_toolbar.init(fake_ctx)

    # Set imported data with scene references
    _active_toolbar.set_imported_data(
        imported_objects,
        imported_materials,
        materials_before_import,
        original_scene=original_scene,
        temp_scene=temp_scene
    )

    # Set up callbacks
    def on_accept():
        """Handle accept - close toolbar."""
        global _active_toolbar, _draw_handler
        cleanup_toolbar()

    def on_cancel():
        """Handle cancel - cleanup is done in toolbar, just close."""
        global _active_toolbar, _draw_handler
        cleanup_toolbar()

    _active_toolbar.on_accept = on_accept
    _active_toolbar.on_cancel = on_cancel

    # Add draw handler
    if _draw_handler is None:
        _draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            _draw_toolbar,
            (),
            'WINDOW',
            'POST_PIXEL'
        )

    # Start modal operator for mouse handling
    # We need to do this with proper context override
    try:
        # Validate all components before creating override
        if not context.window_manager.windows:
            print("⚠️ No windows available for modal operator")
            return {'CANCELLED'}
        
        window = context.window_manager.windows[0]
        if window is None or window.screen is None:
            print("⚠️ Invalid window for modal operator")
            return {'CANCELLED'}
        
        region = next((r for r in area_3d.regions if r.type == 'WINDOW'), None)
        if region is None:
            print("⚠️ No WINDOW region found in viewport")
            return {'CANCELLED'}
        
        if context.scene is None or context.scene.name not in bpy.data.scenes:
            print("⚠️ Invalid scene for modal operator")
            return {'CANCELLED'}
        
        override = {
            'window': window,
            'screen': window.screen,
            'area': area_3d,
            'region': region,
            'scene': context.scene,
            'view_layer': context.view_layer,
        }

        with context.temp_override(**override):
            bpy.ops.quixel.import_confirm('INVOKE_DEFAULT')
    except Exception as e:
        print(f"⚠️ Could not start modal operator: {e}")
        import traceback
        traceback.print_exc()
        # If modal operator fails, we'll rely on manual cleanup

    # Tag viewport for redraw
    area_3d.tag_redraw()

    # Print removed to reduce console clutter
    return {'FINISHED'}


def cleanup_toolbar():
    """Remove toolbar and handlers."""
    global _active_toolbar, _draw_handler, _mouse_tracker_running

    # Cancel any running modal operators first
    try:
        # Try to cancel the modal operator if it's still running
        # We need to check all windows for active modal handlers
        for window in bpy.context.window_manager.windows:
            # Check if there's an active modal operator
            if hasattr(window, 'modal_handler') and window.modal_handler:
                # Try to cancel it
                try:
                    if hasattr(window.modal_handler, 'cancel'):
                        window.modal_handler.cancel(bpy.context)
                except:
                    pass
    except:
        pass

    # Hide toolbar
    if _active_toolbar:
        _active_toolbar.visible = False
        _active_toolbar = None

    # Remove draw handler
    if _draw_handler:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_draw_handler, 'WINDOW')
        except:
            pass
        _draw_handler = None

    # Stop mouse tracker
    _mouse_tracker_running = False

    # Tag all 3D viewports for redraw
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except:
        pass

    # Print removed to reduce console clutter
