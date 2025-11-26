"""Floating toolbar UI widgets for import confirmation.

This module provides a clean widget-based UI system for showing Accept/Cancel
buttons at the bottom of the 3D viewport during asset import.

Architecture:
    - BL_UI_Widget: Base widget class for position tracking and event handling
    - BL_UI_Button: Button widget with hover/pressed states
    - ImportToolbar: Container that manages buttons and drawing
"""

import bpy
import blf
import gpu
import math
import mathutils
from pathlib import Path
from gpu_extras.batch import batch_for_shader
from gpu_extras.presets import draw_circle_2d
from mathutils import Vector, Matrix


# Pre-computed shader constants for smooth circle rendering
class DrawConstants:
    """Pre-computed shader and batch data for efficient circle rendering."""

    filled_circle_shader = None
    filled_circle_batch = None
    uniform_shader = None

    # Cached batches for rounded rectangles
    rect_batch_h = None
    rect_batch_v = None

    # Cached batches for corner arcs (32 segments per arc)
    arc_batches = {}  # Key: radius, Value: batch

    # Cached batch for simple lines
    line_batch = None

    # Cached batch for dropdown chevron arrow
    chevron_batch = None

    @classmethod
    def initialize(cls):
        """Initialize shaders and batches. Call once at startup."""
        if cls.filled_circle_shader is None:
            # Create shader for filled circles
            cls.uniform_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            cls.filled_circle_shader = cls.uniform_shader

            # Create a unit circle batch (will be scaled during drawing)
            segments = 64  # High quality circle
            vertices = [(0, 0)]  # Center point
            for i in range(segments + 1):
                angle = 2 * math.pi * i / segments
                x = math.cos(angle)
                y = math.sin(angle)
                vertices.append((x, y))

            indices = []
            for i in range(segments):
                indices.append((0, i + 1, i + 2))

            cls.filled_circle_batch = batch_for_shader(
                cls.uniform_shader, 'TRIS', {"pos": vertices}, indices=indices
            )

            # Create reusable rectangle batches (unit square, will be scaled)
            vertices = [(0, 0), (1, 0), (1, 1), (0, 1)]
            indices = [(0, 1, 2), (0, 2, 3)]
            cls.rect_batch_h = batch_for_shader(
                cls.uniform_shader, 'TRIS', {"pos": vertices}, indices=indices
            )
            cls.rect_batch_v = batch_for_shader(
                cls.uniform_shader, 'TRIS', {"pos": vertices}, indices=indices
            )

            # Create line batch for simple 2-point lines
            vertices = [(0, 0), (1, 1)]
            cls.line_batch = batch_for_shader(
                cls.uniform_shader, 'LINES', {"pos": vertices}
            )

            # Create chevron batch for dropdown arrow (V shape)
            # Unit chevron pointing down: two lines forming a V
            arrow_size = 1.0
            vertices = (
                (-arrow_size, arrow_size),     # Left top point
                (0, 0),                         # Center bottom point
                (0, 0),                         # Center bottom point (duplicate for second line)
                (arrow_size, arrow_size)       # Right top point
            )
            cls.chevron_batch = batch_for_shader(
                cls.uniform_shader, 'LINES', {"pos": vertices}
            )

    @classmethod
    def get_arc_batch(cls, radius, segments=32):
        """Get or create a cached arc batch for the given radius."""
        key = (radius, segments)
        if key not in cls.arc_batches:
            # Create unit quarter-circle arc (0 to π/2)
            vertices = []
            for i in range(segments + 1):
                angle = 0.5 * math.pi * i / segments
                x = math.cos(angle)
                y = math.sin(angle)
                vertices.append((x, y))

            cls.arc_batches[key] = batch_for_shader(
                cls.uniform_shader, 'LINE_STRIP', {"pos": vertices}
            )
        return cls.arc_batches[key]


def draw_rounded_rect(x, y, width, height, radius, color, segments=16):
    """Draw a filled rounded rectangle using cached batches and smooth shader-based circles.

    Args:
        x, y: Bottom-left position
        width, height: Rectangle dimensions
        radius: Corner radius
        color: RGBA color tuple
        segments: Ignored (kept for API compatibility)
    """
    # Initialize shaders if needed
    DrawConstants.initialize()

    gpu.state.blend_set('ALPHA')

    shader = DrawConstants.uniform_shader
    shader.bind()
    shader.uniform_float("color", color)

    # Draw horizontal strip using cached batch and matrix transforms
    with gpu.matrix.push_pop():
        gpu.matrix.translate((x + radius, y))
        gpu.matrix.scale((width - 2 * radius, height))
        DrawConstants.rect_batch_h.draw(shader)

    # Draw vertical strip using cached batch and matrix transforms
    with gpu.matrix.push_pop():
        gpu.matrix.translate((x, y + radius))
        gpu.matrix.scale((width, height - 2 * radius))
        DrawConstants.rect_batch_v.draw(shader)

    # Draw smooth filled circles at corners using pre-computed batch
    corners = [
        (x + radius, y + radius),              # Bottom-left
        (x + width - radius, y + radius),      # Bottom-right
        (x + width - radius, y + height - radius),  # Top-right
        (x + radius, y + height - radius),     # Top-left
    ]

    for cx, cy in corners:
        with gpu.matrix.push_pop():
            gpu.matrix.translate((cx, cy))
            gpu.matrix.scale_uniform(radius)
            DrawConstants.filled_circle_batch.draw(shader)

    gpu.state.blend_set('NONE')


class BL_UI_Widget:
    """Base widget class for UI elements.

    Handles position tracking, coordinate conversion, and basic event detection.
    """

    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y
        self.x_screen = x
        self.y_screen = y
        self.width = width
        self.height = height
        self.area_height = 0
        self._bg_color = (0.2, 0.2, 0.2, 0.9)
        self._visible = True

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, value):
        self._visible = value

    def init(self, context):
        """Initialize widget with context information."""
        self.area_height = context.area.height
        self.update(self.x, self.y)

    def update(self, x, y):
        """Update widget position."""
        self.x_screen = x
        self.y_screen = y

    def is_in_rect(self, x, y):
        """Check if point (x, y) is inside widget bounds.

        Args:
            x: Mouse X coordinate in region space
            y: Mouse Y coordinate in region space

        Returns:
            bool: True if point is inside widget
        """
        # Both mouse coordinates and widget position use Y=0 at bottom
        if ((self.x_screen <= x <= (self.x_screen + self.width)) and
                (self.y_screen <= y <= (self.y_screen + self.height))):
            return True
        return False

    def draw(self):
        """Draw the widget as a rounded rectangle."""
        if not self._visible:
            return

        # Use the rounded rectangle drawing function
        draw_rounded_rect(
            self.x_screen,
            self.y_screen,
            self.width,
            self.height,
            8,  # 8px corner radius for background
            self._bg_color,
            segments=16
        )


class BL_UI_Button(BL_UI_Widget):
    """Button widget with hover and pressed states.

    States:
        0 = normal
        1 = pressed
        2 = hover
    """

    def __init__(self, x, y, width, height):
        super().__init__(x, y, width, height)
        self._text = "Button"
        self._text_size = 12
        self._text_color = (1.0, 1.0, 1.0, 1.0)
        self._hover_bg_color = (0.3, 0.5, 0.7, 0.95)
        self._pressed_bg_color = (0.2, 0.4, 0.6, 1.0)
        self._normal_bg_color = (0.25, 0.25, 0.25, 0.9)

        self.__state = 0
        self.mouse_up_func = None

        # Pre-create shader and batch for rectangle
        self.shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        vertices = ((0, 0), (1, 0), (1, 1), (0, 1))
        indices = ((0, 1, 2), (0, 2, 3))
        self.batch = batch_for_shader(
            self.shader, 'TRIS',
            {"pos": vertices},
            indices=indices
        )

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        self._text = value

    @property
    def text_size(self):
        return self._text_size

    @text_size.setter
    def text_size(self, value):
        self._text_size = value

    def set_mouse_up(self, func):
        """Set callback for mouse up event."""
        self.mouse_up_func = func

    def get_button_color(self):
        """Get current button color based on state."""
        if self.__state == 1:  # pressed
            return self._pressed_bg_color
        elif self.__state == 2:  # hover
            return self._hover_bg_color
        return self._normal_bg_color

    def draw(self):
        """Draw the button with current state and rounded corners."""
        if not self.visible:
            return

        area_height = self.area_height
        color = self.get_button_color()

        # Draw filled rounded rectangle
        draw_rounded_rect(
            self.x_screen,
            self.y_screen,
            self.width,
            self.height,
            4,  # 4px corner radius for buttons
            color,
            segments=16
        )

        # Draw text
        self.draw_text(area_height)

    def draw_text(self, area_height):
        """Draw button text centered."""
        blf.size(0, self._text_size)

        # Get text dimensions
        text_width, text_height = blf.dimensions(0, self._text)

        # Calculate centered position
        # Y=0 is at bottom in GPU coordinates, so we add to y_screen
        text_x = self.x_screen + (self.width - text_width) / 2.0
        text_y = self.y_screen + (self.height / 2) - (text_height / 2)

        blf.position(0, text_x, text_y, 0)

        r, g, b, a = self._text_color
        blf.color(0, r, g, b, a)

        blf.draw(0, self._text)

    def mouse_down(self, x, y):
        """Handle mouse down event."""
        if self.is_in_rect(x, y):
            self.__state = 1
            return True
        return False

    def mouse_up(self, x, y):
        """Handle mouse up event."""
        if self.is_in_rect(x, y):
            self.__state = 2
            if self.mouse_up_func:
                self.mouse_up_func(self)
            return True
        else:
            self.__state = 0
        return False

    def mouse_move(self, x, y):
        """Handle mouse move event for hover state."""
        if self.is_in_rect(x, y):
            if self.__state != 1:  # Not pressed
                self.__state = 2  # Hover
        else:
            self.__state = 0  # Normal


class BL_UI_Dropdown(BL_UI_Widget):
    """Dropdown widget for selecting LOD levels."""

    def __init__(self, x, y, width, height):
        super().__init__(x, y, width, height)
        self._items = []
        self._selected_index = 0
        self._is_open = False
        self._bg_color = (0.157, 0.157, 0.157, 1.0)  # #282828
        self._hover_bg_color = (0.475, 0.475, 0.475, 1.0)  # #797979
        self._text_color = (1.0, 1.0, 1.0, 1.0)
        self._text_size = 12
        self.on_change = None
        self._hovered_item_index = -1  # Track which item is being hovered

        # Pre-create shader and batch
        self.shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        vertices = ((0, 0), (1, 0), (1, 1), (0, 1))
        indices = ((0, 1, 2), (0, 2, 3))
        self.batch = batch_for_shader(
            self.shader, 'TRIS',
            {"pos": vertices},
            indices=indices
        )

    def set_items(self, items):
        """Set the dropdown items."""
        self._items = items
        if items and self._selected_index >= len(items):
            self._selected_index = 0

    def get_selected_item(self):
        """Get the currently selected item."""
        if self._items and 0 <= self._selected_index < len(self._items):
            return self._items[self._selected_index]
        return None

    def _draw_selective_rounded_rect(self, x, y, width, height, color,
                                      top_left=True, top_right=True, bottom_left=True, bottom_right=True):
        """Draw a filled rectangle with selective rounded corners using cached batches.

        Args:
            x, y: Bottom-left position
            width, height: Rectangle dimensions
            color: RGBA color tuple
            top_left, top_right, bottom_left, bottom_right: Which corners to round
        """
        # Initialize shaders if needed
        DrawConstants.initialize()

        gpu.state.blend_set('ALPHA')

        radius = 4
        shader = DrawConstants.uniform_shader
        shader.bind()
        shader.uniform_float("color", color)

        # Draw main horizontal strip using cached batch
        h_left = x if not bottom_left and not top_left else x + radius
        h_right = x + width if not bottom_right and not top_right else x + width - radius
        h_width = h_right - h_left

        with gpu.matrix.push_pop():
            gpu.matrix.translate((h_left, y))
            gpu.matrix.scale((h_width, height))
            DrawConstants.rect_batch_h.draw(shader)

        # Draw left vertical strip if needed
        if bottom_left or top_left:
            bl_y = (y + radius) if bottom_left else y
            tl_y = (y + height - radius) if top_left else (y + height)
            v_height = tl_y - bl_y

            with gpu.matrix.push_pop():
                gpu.matrix.translate((x, bl_y))
                gpu.matrix.scale((radius, v_height))
                DrawConstants.rect_batch_v.draw(shader)

        # Draw right vertical strip if needed
        if bottom_right or top_right:
            br_y = (y + radius) if bottom_right else y
            tr_y = (y + height - radius) if top_right else (y + height)
            v_height = tr_y - br_y

            with gpu.matrix.push_pop():
                gpu.matrix.translate((x + width - radius, br_y))
                gpu.matrix.scale((radius, v_height))
                DrawConstants.rect_batch_v.draw(shader)

        # Draw smooth circles at rounded corners only
        if bottom_left:
            with gpu.matrix.push_pop():
                gpu.matrix.translate((x + radius, y + radius))
                gpu.matrix.scale_uniform(radius)
                DrawConstants.filled_circle_batch.draw(shader)

        if bottom_right:
            with gpu.matrix.push_pop():
                gpu.matrix.translate((x + width - radius, y + radius))
                gpu.matrix.scale_uniform(radius)
                DrawConstants.filled_circle_batch.draw(shader)

        if top_right:
            with gpu.matrix.push_pop():
                gpu.matrix.translate((x + width - radius, y + height - radius))
                gpu.matrix.scale_uniform(radius)
                DrawConstants.filled_circle_batch.draw(shader)

        if top_left:
            with gpu.matrix.push_pop():
                gpu.matrix.translate((x + radius, y + height - radius))
                gpu.matrix.scale_uniform(radius)
                DrawConstants.filled_circle_batch.draw(shader)

        gpu.state.blend_set('NONE')

    def _draw_rounded_border(self, x, y, width, height, radius, color, thickness):
        """Draw a rounded rectangle border using smooth arc outlines.

        Args:
            x, y: Bottom-left position
            width, height: Rectangle dimensions
            radius: Corner radius
            color: RGBA color tuple
            thickness: Border line thickness
        """
        DrawConstants.initialize()

        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(thickness)

        shader = DrawConstants.uniform_shader
        shader.bind()
        shader.uniform_float("color", color)

        # Draw straight edge lines - Bottom edge
        vertices = [(x + radius, y), (x + width - radius, y)]
        batch = batch_for_shader(shader, 'LINES', {"pos": vertices})
        batch.draw(shader)

        # Right edge
        vertices = [(x + width, y + radius), (x + width, y + height - radius)]
        batch = batch_for_shader(shader, 'LINES', {"pos": vertices})
        batch.draw(shader)

        # Top edge
        vertices = [(x + width - radius, y + height), (x + radius, y + height)]
        batch = batch_for_shader(shader, 'LINES', {"pos": vertices})
        batch.draw(shader)

        # Left edge
        vertices = [(x, y + height - radius), (x, y + radius)]
        batch = batch_for_shader(shader, 'LINES', {"pos": vertices})
        batch.draw(shader)

        # Draw quarter-circle arcs at corners
        segments_per_arc = 32

        # Corner definitions: (center_x, center_y, start_angle, end_angle)
        corners = [
            (x + radius, y + radius, math.pi, 1.5 * math.pi),              # Bottom-left
            (x + width - radius, y + radius, 1.5 * math.pi, 2 * math.pi),  # Bottom-right
            (x + width - radius, y + height - radius, 0, 0.5 * math.pi),   # Top-right
            (x + radius, y + height - radius, 0.5 * math.pi, math.pi),     # Top-left
        ]

        for cx, cy, start_angle, end_angle in corners:
            arc_vertices = []
            for i in range(segments_per_arc + 1):
                angle = start_angle + (end_angle - start_angle) * i / segments_per_arc
                vx = cx + radius * math.cos(angle)
                vy = cy + radius * math.sin(angle)
                arc_vertices.append((vx, vy))

            arc_batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": arc_vertices})
            arc_batch.draw(shader)

        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')

    def draw(self):
        """Draw the dropdown widget."""
        if not self.visible:
            return

        # Draw main dropdown box with rounded corners
        draw_rounded_rect(
            self.x_screen,
            self.y_screen,
            self.width,
            self.height,
            4,  # 4px corner radius for dropdown
            self._bg_color,
            segments=16
        )

        # Draw border with accept button color (0.329, 0.329, 0.329, 1.0)
        self._draw_rounded_border(
            self.x_screen,
            self.y_screen,
            self.width,
            self.height,
            4,  # Same corner radius
            (0.329, 0.329, 0.329, 1.0),  # Accept button color
            1  # Border thickness
        )

        # Draw text
        if self._items and 0 <= self._selected_index < len(self._items):
            selected_text = self._items[self._selected_index]
            blf.size(0, self._text_size)
            text_width, text_height = blf.dimensions(0, selected_text)

            text_x = self.x_screen + 8  # Left padding
            text_y = self.y_screen + (self.height / 2) - (text_height / 2)

            blf.position(0, text_x, text_y, 0)
            r, g, b, a = self._text_color
            blf.color(0, r, g, b, a)
            blf.draw(0, selected_text)

        # Draw dropdown arrow using cached chevron batch
        arrow_x = self.x_screen + self.width - 16
        arrow_y = self.y_screen + self.height / 2 + 2  # 2px higher
        arrow_size = 4

        DrawConstants.initialize()
        gpu.state.blend_set('ALPHA')

        shader = DrawConstants.uniform_shader
        shader.bind()
        shader.uniform_float("color", (1.0, 1.0, 1.0, 1.0))

        # Use cached chevron batch with matrix transform
        with gpu.matrix.push_pop():
            gpu.matrix.translate((arrow_x, arrow_y - arrow_size))
            gpu.matrix.scale_uniform(arrow_size)
            DrawConstants.chevron_batch.draw(shader)

        gpu.state.blend_set('NONE')

        # If dropdown is open, draw items
        if self._is_open and self._items:
            item_height = 24
            dropdown_y = self.y_screen + self.height

            for i, item in enumerate(self._items):
                item_y = dropdown_y + (i * item_height)

                # Check if this item is being hovered
                is_hovered = (i == self._hovered_item_index)

                # Determine which corners should be rounded
                is_first_item = (i == 0)
                is_last_item = (i == len(self._items) - 1)

                # Draw item background with selective rounded corners
                color = self._hover_bg_color if is_hovered else self._bg_color

                if is_first_item and is_last_item:
                    # Single item - round all corners
                    self._draw_selective_rounded_rect(
                        self.x_screen, item_y, self.width, item_height,
                        color, top_left=True, top_right=True, bottom_left=True, bottom_right=True
                    )
                elif is_first_item:
                    # First item (at bottom of list) - round only bottom corners
                    self._draw_selective_rounded_rect(
                        self.x_screen, item_y, self.width, item_height,
                        color, top_left=False, top_right=False, bottom_left=True, bottom_right=True
                    )
                elif is_last_item:
                    # Last item (at top of list) - round only top corners
                    self._draw_selective_rounded_rect(
                        self.x_screen, item_y, self.width, item_height,
                        color, top_left=True, top_right=True, bottom_left=False, bottom_right=False
                    )
                else:
                    # Middle items - no rounded corners
                    self._draw_selective_rounded_rect(
                        self.x_screen, item_y, self.width, item_height,
                        color, top_left=False, top_right=False, bottom_left=False, bottom_right=False
                    )

                # Draw item text
                blf.size(0, self._text_size)
                text_x = self.x_screen + 8
                text_y = item_y + (item_height / 2) - 6

                blf.position(0, text_x, text_y, 0)
                blf.color(0, 1.0, 1.0, 1.0, 1.0)
                blf.draw(0, item)

    def mouse_move(self, x, y):
        """Handle mouse move event to track hover state."""
        if not self._is_open:
            self._hovered_item_index = -1
            return

        # Check which dropdown item is being hovered
        item_height = 24
        dropdown_y = self.y_screen + self.height

        self._hovered_item_index = -1  # Reset
        for i, item in enumerate(self._items):
            item_y = dropdown_y + (i * item_height)
            if (self.x_screen <= x <= (self.x_screen + self.width) and
                    item_y <= y <= (item_y + item_height)):
                self._hovered_item_index = i
                break

    def mouse_down(self, x, y):
        """Handle mouse down event."""
        if self.is_in_rect(x, y):
            self._is_open = not self._is_open
            if not self._is_open:
                self._hovered_item_index = -1  # Reset hover when closing
            return True
        elif self._is_open:
            # Check if clicked on an item in the dropdown
            item_height = 24
            dropdown_y = self.y_screen + self.height

            for i, item in enumerate(self._items):
                item_y = dropdown_y + (i * item_height)
                if (self.x_screen <= x <= (self.x_screen + self.width) and
                        item_y <= y <= (item_y + item_height)):
                    self._selected_index = i
                    self._is_open = False
                    self._hovered_item_index = -1  # Reset hover when selecting
                    if self.on_change:
                        self.on_change(item)
                    return True

            # Clicked outside dropdown, close it
            self._is_open = False
            self._hovered_item_index = -1  # Reset hover when closing
        return False


class BL_UI_Checkbox(BL_UI_Widget):
    """Checkbox widget with label."""

    def __init__(self, x, y, width, height):
        super().__init__(x, y, width, height)
        self._text = "Checkbox"
        self._text_size = 12
        self._text_color = (1.0, 1.0, 1.0, 1.0)
        self._checked = False
        self._checkbox_size = 16
        self._checkbox_border_color = (0.329, 0.329, 0.329, 1.0)  # Accept button color
        self._checkbox_bg_color = (0.157, 0.157, 0.157, 1.0)  # #282828
        self._checkbox_check_color = (0.2, 0.5, 0.8, 1.0)  # Blue checkmark
        self.on_change = None

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        self._text = value

    @property
    def checked(self):
        return self._checked

    @checked.setter
    def checked(self, value):
        self._checked = value

    def draw(self):
        """Draw the checkbox with label."""
        if not self.visible:
            return

        # Calculate checkbox position (left side)
        checkbox_x = self.x_screen
        checkbox_y = self.y_screen + (self.height - self._checkbox_size) / 2

        # Draw checkbox background
        draw_rounded_rect(
            checkbox_x,
            checkbox_y,
            self._checkbox_size,
            self._checkbox_size,
            2,  # 2px corner radius
            self._checkbox_bg_color,
            segments=8
        )

        # Draw checkbox border
        self._draw_checkbox_border(checkbox_x, checkbox_y, self._checkbox_size, self._checkbox_border_color, 1)

        # Draw checkmark if checked
        if self._checked:
            self._draw_checkmark(checkbox_x, checkbox_y, self._checkbox_size)

        # Draw label text (to the right of checkbox)
        blf.size(0, self._text_size)
        text_x = checkbox_x + self._checkbox_size + 6  # 6px gap between checkbox and text
        text_y = self.y_screen + (self.height / 2) - (blf.dimensions(0, self._text)[1] / 2)

        blf.position(0, text_x, text_y, 0)
        r, g, b, a = self._text_color
        blf.color(0, r, g, b, a)
        blf.draw(0, self._text)

    def _draw_checkbox_border(self, x, y, size, color, thickness):
        """Draw checkbox border."""
        import math
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(thickness)

        radius = 2
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        vertices = []

        # Create rounded rectangle border
        segments = 4
        # Bottom edge
        vertices.append((x + radius, y))
        vertices.append((x + size - radius, y))
        # Bottom-right corner
        cx, cy = x + size - radius, y + radius
        for i in range(segments + 1):
            angle = 1.5 * math.pi + (0.5 * math.pi * i / segments)
            vertices.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        # Right edge
        vertices.append((x + size, y + size - radius))
        # Top-right corner
        cx, cy = x + size - radius, y + size - radius
        for i in range(segments + 1):
            angle = 0 + (0.5 * math.pi * i / segments)
            vertices.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        # Top edge
        vertices.append((x + size - radius, y + size))
        vertices.append((x + radius, y + size))
        # Top-left corner
        cx, cy = x + radius, y + size - radius
        for i in range(segments + 1):
            angle = 0.5 * math.pi + (0.5 * math.pi * i / segments)
            vertices.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        # Left edge
        vertices.append((x, y + size - radius))
        vertices.append((x, y + radius))
        # Bottom-left corner
        cx, cy = x + radius, y + radius
        for i in range(segments + 1):
            angle = math.pi + (0.5 * math.pi * i / segments)
            vertices.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        vertices.append((x + radius, y))

        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": vertices})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)

        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')

    def _draw_checkmark(self, x, y, size):
        """Draw checkmark inside checkbox."""
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(2.0)

        shader = gpu.shader.from_builtin('UNIFORM_COLOR')

        # Create checkmark shape
        padding = 3
        vertices = (
            (x + padding + 2, y + size / 2),
            (x + size / 2 - 1, y + padding + 2),
            (x + size - padding, y + size - padding)
        )

        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": vertices})
        shader.bind()
        shader.uniform_float("color", self._checkbox_check_color)
        batch.draw(shader)

        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')

    def mouse_down(self, x, y):
        """Handle mouse down event."""
        if self.is_in_rect(x, y):
            self._checked = not self._checked
            if self.on_change:
                self.on_change(self._checked)
            return True
        return False


class BL_UI_ToggleButton(BL_UI_Widget):
    """Square toggle button widget (for wireframe, etc.)."""

    def __init__(self, x, y, size):
        super().__init__(x, y, size, size)
        self._toggled = False
        self._icon_text = "W"  # Text to show in button (fallback)
        self._icon_size = 14
        self._icon_path = None  # Path to icon image (PNG)
        self._icon_image = None  # Loaded Blender image
        self._icon_texture = None  # GPU texture from image
        self._bg_color = (0.133, 0.133, 0.133, 1.0)  # #222222
        self._toggled_bg_color = (0.047, 0.549, 0.914, 1.0)  # Blue when toggled
        self._hover_bg_color = (0.2, 0.2, 0.2, 1.0)
        self._border_color = (0.329, 0.329, 0.329, 1.0)
        self._text_color = (1.0, 1.0, 1.0, 1.0)
        self._is_hovered = False
        self.on_toggle = None

    @property
    def toggled(self):
        return self._toggled

    @toggled.setter
    def toggled(self, value):
        self._toggled = value

    @property
    def icon_text(self):
        return self._icon_text

    @icon_text.setter
    def icon_text(self, value):
        self._icon_text = value

    @property
    def icon_path(self):
        return self._icon_path

    @icon_path.setter
    def icon_path(self, value):
        self._icon_path = value
        # Load image when path is set
        if value:
            self._load_icon_image()

    def _load_icon_image(self):
        """Load icon image and create GPU texture."""
        if not self._icon_path:
            return

        icon_path = Path(self._icon_path)
        
        if not icon_path.exists():
            print(f"⚠️ Wireframe icon not found at: {icon_path}")
            return

        try:
            # Load image
            self._icon_image = bpy.data.images.load(str(icon_path))
            # Create GPU texture
            self._icon_texture = gpu.texture.from_image(self._icon_image)
        except Exception as e:
            print(f"⚠️ Failed to load wireframe icon: {e}")
            self._icon_image = None
            self._icon_texture = None

    def init(self, context):
        """Initialize widget and load icon if path is set."""
        super().init(context)
        if self._icon_path:
            self._load_icon_image()

    def draw(self):
        """Draw the square toggle button."""
        if not self.visible:
            return

        # Determine background color
        if self._toggled:
            bg_color = self._toggled_bg_color
        elif self._is_hovered:
            bg_color = self._hover_bg_color
        else:
            bg_color = self._bg_color

        # Draw background
        draw_rounded_rect(
            self.x_screen,
            self.y_screen,
            self.width,
            self.height,
            2,  # 2px corner radius
            bg_color,
            segments=8
        )

        # Border removed - no border drawing

        # Draw icon image or text
        if self._icon_texture:
            # Draw icon image centered
            self._draw_icon_image()
        else:
            # Draw icon text centered (fallback)
            blf.size(0, self._icon_size)
            text_width, text_height = blf.dimensions(0, self._icon_text)
            text_x = self.x_screen + (self.width - text_width) / 2
            text_y = self.y_screen + (self.height - text_height) / 2

            blf.position(0, text_x, text_y, 0)
            r, g, b, a = self._text_color
            blf.color(0, r, g, b, a)
            blf.draw(0, self._icon_text)

    def _draw_icon_image(self):
        """Draw the icon image centered in the button."""
        if not self._icon_texture:
            return

        # Calculate icon size (leave some padding)
        padding = 4
        icon_size = min(self.width, self.height) - (padding * 2)
        icon_x = self.x_screen + (self.width - icon_size) / 2
        icon_y = self.y_screen + (self.height - icon_size) / 2

        # Use 2D image shader to draw the texture
        gpu.state.blend_set('ALPHA')
        
        # Create shader for image drawing (2D_IMAGE is the correct builtin shader)
        try:
            shader = gpu.shader.from_builtin('2D_IMAGE')
        except:
            # Fallback: try alternative shader name for different Blender versions
            try:
                shader = gpu.shader.from_builtin('IMAGE')
            except:
                # If shader not available, fall back to text
                blf.size(0, self._icon_size)
                text_width, text_height = blf.dimensions(0, self._icon_text)
                text_x = self.x_screen + (self.width - text_width) / 2
                text_y = self.y_screen + (self.height - text_height) / 2
                blf.position(0, text_x, text_y, 0)
                r, g, b, a = self._text_color
                blf.color(0, r, g, b, a)
                blf.draw(0, self._icon_text)
                gpu.state.blend_set('NONE')
                return
        
        shader.bind()
        shader.uniform_sampler("image", self._icon_texture)
        
        # Create quad vertices for the icon
        vertices = (
            (icon_x, icon_y),
            (icon_x + icon_size, icon_y),
            (icon_x + icon_size, icon_y + icon_size),
            (icon_x, icon_y + icon_size)
        )
        
        # Texture coordinates (corrected to fix vertical mirroring)
        tex_coords = (
            (0, 0),  # Bottom-left vertex -> bottom-left of texture
            (1, 0),  # Bottom-right vertex -> bottom-right of texture
            (1, 1),  # Top-right vertex -> top-right of texture
            (0, 1)   # Top-left vertex -> top-left of texture
        )
        
        indices = ((0, 1, 2), (0, 2, 3))
        batch = batch_for_shader(shader, 'TRIS', {"pos": vertices, "texCoord": tex_coords}, indices=indices)
        batch.draw(shader)
        
        gpu.state.blend_set('NONE')

    def _draw_border(self, x, y, size, color, thickness):
        """Draw button border."""
        import math
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(thickness)

        radius = 2
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        vertices = []

        # Create rounded rectangle border
        segments = 4
        # Bottom edge
        vertices.append((x + radius, y))
        vertices.append((x + size - radius, y))
        # Bottom-right corner
        cx, cy = x + size - radius, y + radius
        for i in range(segments + 1):
            angle = 1.5 * math.pi + (0.5 * math.pi * i / segments)
            vertices.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        # Right edge
        vertices.append((x + size, y + size - radius))
        # Top-right corner
        cx, cy = x + size - radius, y + size - radius
        for i in range(segments + 1):
            angle = 0 + (0.5 * math.pi * i / segments)
            vertices.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        # Top edge
        vertices.append((x + size - radius, y + size))
        vertices.append((x + radius, y + size))
        # Top-left corner
        cx, cy = x + radius, y + size - radius
        for i in range(segments + 1):
            angle = 0.5 * math.pi + (0.5 * math.pi * i / segments)
            vertices.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        # Left edge
        vertices.append((x, y + size - radius))
        vertices.append((x, y + radius))
        # Bottom-left corner
        cx, cy = x + radius, y + radius
        for i in range(segments + 1):
            angle = math.pi + (0.5 * math.pi * i / segments)
            vertices.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))

        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": vertices})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)

        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')

    def mouse_down(self, x, y):
        """Handle mouse down event."""
        if self.is_in_rect(x, y):
            return True
        return False

    def mouse_up(self, x, y):
        """Handle mouse up event - toggle state."""
        if self.is_in_rect(x, y):
            self._toggled = not self._toggled
            if self.on_toggle:
                self.on_toggle(self._toggled)
            return True
        return False

    def mouse_move(self, x, y):
        """Handle mouse move event for hover state."""
        self._is_hovered = self.is_in_rect(x, y)


class BL_UI_Slider(BL_UI_Widget):
    """Slider widget with discrete LOD markers (LOD0-LOD7)."""

    def __init__(self, x, y, width, height):
        super().__init__(x, y, width, height)
        self._min_value = 0
        self._max_value = 7
        self._current_value = 0
        self._is_dragging = False
        self._marker_positions = []
        self._available_lods = [0, 1, 2, 3, 4, 5, 6, 7]  # All LODs available by default

        # Visual properties
        self._track_height = 4
        self._track_color = (0.333, 0.333, 0.333, 1.0)  # #555555
        self._track_border_color = (0.329, 0.329, 0.329, 1.0)
        self._handle_radius = 8
        self._handle_color = (0.047, 0.549, 0.914, 1.0)  # Blue like Accept button
        self._handle_hover_color = (0.067, 0.629, 1.0, 1.0)
        self._handle_pressed_color = (0.039, 0.469, 0.834, 1.0)
        self._marker_active_color = (0.333, 0.333, 0.333, 1.0)  # #555555 for available LODs
        self._marker_inactive_color = (0.071, 0.071, 0.071, 1.0)  # #121212 for unavailable LODs
        self._minmax_marker_color = (0.804, 0.804, 0.804, 1.0)  # #CDCDCD for min/max LOD markers

        # State
        self._is_hovered = False
        self.on_value_changed = None

        # Min/Max LOD markers (set from toolbar)
        self._min_lod = None
        self._max_lod = None

    def set_available_lods(self, lod_levels):
        """Set which LOD levels are available (enabled markers)."""
        self._available_lods = lod_levels

    def set_min_max_lods(self, min_lod, max_lod):
        """Set the min and max LOD values for displaying markers above the track."""
        self._min_lod = min_lod
        self._max_lod = max_lod

    def set_value(self, value):
        """Set the slider value (LOD level 0-7), clamped to min/max range."""
        # First clamp to overall slider range (0-7)
        value = max(self._min_value, min(self._max_value, value))

        # Then clamp to min/max LOD range if set
        if self._min_lod is not None:
            value = max(value, self._min_lod)
        if self._max_lod is not None:
            value = min(value, self._max_lod)

        self._current_value = value

    def get_value(self):
        """Get the current slider value."""
        return self._current_value

    def _calculate_marker_positions(self):
        """Calculate X positions for each LOD marker."""
        if not self._marker_positions:
            num_markers = self._max_value - self._min_value + 1
            usable_width = self.width - (self._handle_radius * 2)
            spacing = usable_width / (num_markers - 1) if num_markers > 1 else 0

            self._marker_positions = []
            for i in range(num_markers):
                x = self.x_screen + self._handle_radius + (i * spacing)
                self._marker_positions.append(x)

    def _get_handle_position(self):
        """Get the X position of the handle for current value."""
        if not self._marker_positions:
            self._calculate_marker_positions()

        if self._current_value < len(self._marker_positions):
            return self._marker_positions[self._current_value]
        return self.x_screen + self.width / 2

    def _value_from_position(self, x):
        """Convert X position to nearest LOD value, clamped to min/max range."""
        if not self._marker_positions:
            self._calculate_marker_positions()

        # Find closest marker
        min_dist = float('inf')
        closest_value = self._current_value

        for i, marker_x in enumerate(self._marker_positions):
            dist = abs(x - marker_x)
            if dist < min_dist:
                min_dist = dist
                closest_value = i

        # Clamp value to min/max LOD range
        if self._min_lod is not None:
            closest_value = max(closest_value, self._min_lod)
        if self._max_lod is not None:
            closest_value = min(closest_value, self._max_lod)

        return closest_value

    def draw(self):
        """Draw the slider with track, markers, and handle."""
        if not self._visible:
            return

        # Recalculate marker positions if needed
        self._calculate_marker_positions()

        # Draw track
        track_y = self.y_screen + (self.height - self._track_height) / 2
        draw_rounded_rect(
            self.x_screen + self._handle_radius,
            track_y,
            self.width - (self._handle_radius * 2),
            self._track_height,
            2,
            self._track_color,
            segments=8
        )

        # Draw markers
        for i, marker_x in enumerate(self._marker_positions):
            is_min_lod = (self._min_lod is not None and i == self._min_lod)
            is_max_lod = (self._max_lod is not None and i == self._max_lod)
            is_minmax = is_min_lod or is_max_lod

            # Determine marker properties based on type
            if is_minmax:
                # Min/Max LOD markers: #CDCDCD color, extra tall
                marker_color = self._minmax_marker_color
                marker_width = 3
                marker_height = 16
            else:
                # Regular LOD markers: all the same #555555 color
                marker_color = self._marker_active_color
                marker_width = 2
                marker_height = 12

            marker_y = self.y_screen + (self.height - marker_height) / 2

            gpu.state.blend_set('ALPHA')
            gpu.state.line_width_set(marker_width)

            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            vertices = (
                (marker_x, marker_y),
                (marker_x, marker_y + marker_height)
            )
            batch = batch_for_shader(shader, 'LINES', {"pos": vertices})
            shader.bind()
            shader.uniform_float("color", marker_color)
            batch.draw(shader)

            gpu.state.line_width_set(1.0)
            gpu.state.blend_set('NONE')

        # Draw handle
        handle_x = self._get_handle_position()
        handle_y = self.y_screen + self.height / 2

        # Choose handle color based on state
        if self._is_dragging:
            handle_color = self._handle_pressed_color
        elif self._is_hovered:
            handle_color = self._handle_hover_color
        else:
            handle_color = self._handle_color

        # Draw handle circle
        self._draw_circle(handle_x, handle_y, self._handle_radius, handle_color)

        # Draw white outline
        self._draw_circle_outline(handle_x, handle_y, self._handle_radius, (1.0, 1.0, 1.0, 1.0), 2)

    def _draw_circle(self, cx, cy, radius, color):
        """Draw a filled circle."""
        gpu.state.blend_set('ALPHA')

        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        segments = 32
        vertices = [(cx, cy)]  # Center

        for i in range(segments + 1):
            angle = 2 * math.pi * i / segments
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            vertices.append((x, y))

        indices = []
        for i in range(segments):
            indices.append((0, i + 1, i + 2))

        batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)

        gpu.state.blend_set('NONE')

    def _draw_circle_outline(self, cx, cy, radius, color, thickness):
        """Draw a circle outline."""
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(thickness)

        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        segments = 32
        vertices = []

        for i in range(segments + 1):
            angle = 2 * math.pi * i / segments
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            vertices.append((x, y))

        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": vertices})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)

        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')

    def _is_handle_hovered(self, x, y):
        """Check if mouse is over the handle."""
        handle_x = self._get_handle_position()
        handle_y = self.y_screen + self.height / 2

        dist = math.sqrt((x - handle_x) ** 2 + (y - handle_y) ** 2)
        return dist <= self._handle_radius

    def mouse_down(self, x, y):
        """Handle mouse down event."""
        if self._is_handle_hovered(x, y):
            self._is_dragging = True
            return True

        # Also allow clicking on track to jump to position
        if self.is_in_rect(x, y):
            new_value = self._value_from_position(x)
            if new_value != self._current_value:
                self._current_value = new_value
                if self.on_value_changed:
                    self.on_value_changed(self._current_value)
            return True

        return False

    def mouse_up(self, x, y):
        """Handle mouse up event."""
        if self._is_dragging:
            self._is_dragging = False
            # Snap to nearest marker
            if self.is_in_rect(x, y):
                new_value = self._value_from_position(x)
                if new_value != self._current_value:
                    self._current_value = new_value
                    if self.on_value_changed:
                        self.on_value_changed(self._current_value)
            return True
        return False

    def mouse_move(self, x, y):
        """Handle mouse move event."""
        # Update hover state
        was_hovered = self._is_hovered
        self._is_hovered = self._is_handle_hovered(x, y)

        # Update dragging
        if self._is_dragging:
            # Update value while dragging and trigger callback immediately
            new_value = self._value_from_position(x)
            if new_value != self._current_value:
                self._current_value = new_value
                # Trigger callback during drag for real-time updates
                if self.on_value_changed:
                    self.on_value_changed(self._current_value)
            return True

        return was_hovered != self._is_hovered

    def update(self, x, y):
        """Update widget position."""
        super().update(x, y)
        # Clear cached positions when widget moves
        self._marker_positions = []


class ImportToolbar:
    """Container for import confirmation toolbar.

    Manages Accept and Cancel buttons, positioning, and drawing.
    """

    def __init__(self):
        self.accept_button = None
        self.cancel_button = None
        self.min_lod_dropdown = None  # Renamed from lod_dropdown
        self.max_lod_dropdown = None  # New max LOD dropdown
        self.auto_lod_checkbox = None  # New auto LOD checkbox
        self.background_panel = None

        # Top toolbar widgets (new LOD slider toolbar)
        self.top_background_panel = None
        self.lod_slider = None
        self.show_all_checkbox = None
        self.wireframe_toggle = None

        self.visible = False

        # Store imported data for cleanup
        self.imported_objects = []
        self.imported_materials = []
        self.materials_before_import = set()
        self.original_scene = None  # Reference to original scene
        self.temp_scene = None  # Reference to temporary preview scene
        self.lod_levels = []  # List of available LOD levels
        self.selected_min_lod = None  # Currently selected min LOD level
        self.selected_max_lod = 5  # Default max LOD is LOD5
        self.auto_lod_enabled = True  # Auto LOD enabled by default
        self.wireframe_enabled = False  # Wireframe toggle state
        self.current_preview_lod = 0  # Current LOD being previewed

        # LOD positioning data (for restoring original positions)
        self.lod_original_positions = {}  # {obj_name: (x, y, z)}
        self.lod_text_objects = []  # List of created text objects

        # LOD slider state
        self.show_all_lods = True  # Show All checkbox state
        self.current_preview_lod = 0  # Currently visible LOD (when Show All = False)

        # Callbacks
        self.on_accept = None
        self.on_cancel = None

    def init(self, context):
        """Initialize toolbar with buttons."""
        area = context.area

        # Dimensions from spec
        button_width = 100  # Reduced from 120
        button_height = 28  # Updated to 28px
        button_spacing = 4  # Gap between Cancel and Accept buttons
        margin_bottom = 20
        panel_padding = 8  # Updated to 8px padding
        panel_height = 44  # Fixed panel height
        accept_right_padding = 8  # Right padding for accept button

        # LOD controls dimensions
        min_lod_label_width = 56  # Width for "Min LOD" (no colon)
        max_lod_label_width = 66  # Width for "Max LOD" (no colon)
        label_dropdown_gap = 4  # 4px gap between label and dropdown
        lod_dropdown_width = 80
        dropdown_to_max_lod_gap = 8  # 8px gap between Min LOD dropdown and Max LOD label
        max_lod_to_auto_lod_gap = 16  # 16px gap between Max LOD dropdown and Auto LOD (doubled)
        auto_lod_width = 100  # Width for Auto LOD checkbox
        auto_lod_to_divider_gap = 8  # 8px gap between Auto LOD and divider
        divider_spacing = 20  # Space for divider line

        # Calculate total width with all LOD controls
        # Layout: Min LOD [4px] dropdown [8px] Max LOD [4px] dropdown [16px] Auto LOD [8px] divider [20px] Cancel | Accept
        buttons_width = button_width * 2 + button_spacing
        lod_section_width = (min_lod_label_width + label_dropdown_gap + lod_dropdown_width + dropdown_to_max_lod_gap +
                            max_lod_label_width + label_dropdown_gap + lod_dropdown_width + max_lod_to_auto_lod_gap +
                            auto_lod_width)
        total_content_width = lod_section_width + auto_lod_to_divider_gap + divider_spacing + buttons_width + accept_right_padding

        # Center everything
        panel_width = total_content_width + panel_padding * 2
        panel_x = (area.width - panel_width) / 2
        panel_y = margin_bottom

        # Center buttons vertically within the panel
        button_y = margin_bottom + (panel_height - button_height) / 2

        # LOD section on the left with 8px padding
        min_lod_label_x = panel_x + panel_padding + 8  # Add 8px left padding
        min_lod_dropdown_x = min_lod_label_x + min_lod_label_width + label_dropdown_gap

        max_lod_label_x = min_lod_dropdown_x + lod_dropdown_width + dropdown_to_max_lod_gap
        max_lod_dropdown_x = max_lod_label_x + max_lod_label_width + label_dropdown_gap

        auto_lod_x = max_lod_dropdown_x + lod_dropdown_width + max_lod_to_auto_lod_gap

        # Divider position
        divider_x = auto_lod_x + auto_lod_width + auto_lod_to_divider_gap

        # Buttons on the right (SWAPPED: Cancel first, then Accept)
        buttons_start_x = divider_x + divider_spacing

        # Create background panel
        self.background_panel = BL_UI_Widget(panel_x, panel_y, panel_width, panel_height)
        # Color #1d1d1d = RGB(29, 29, 29) = (29/255, 29/255, 29/255)
        self.background_panel._bg_color = (0.114, 0.114, 0.114, 1.0)  # #1d1d1d
        self.background_panel.init(context)

        # Store label positions and divider position for drawing
        self.min_lod_label_x = min_lod_label_x
        self.min_lod_label_y = button_y + button_height / 2
        self.max_lod_label_x = max_lod_label_x
        self.max_lod_label_y = button_y + button_height / 2
        self.divider_x = divider_x
        self.divider_y_start = panel_y + 8
        self.divider_y_end = panel_y + panel_height - 8

        # Create Min LOD dropdown (renamed from lod_dropdown)
        self.min_lod_dropdown = BL_UI_Dropdown(min_lod_dropdown_x, button_y, lod_dropdown_width, button_height)
        self.min_lod_dropdown.init(context)
        # Set items based on detected LOD levels (will be updated later)
        if self.lod_levels:
            self.min_lod_dropdown.set_items([f"LOD{level}" for level in self.lod_levels])
        else:
            self.min_lod_dropdown.set_items(["LOD0"])  # Default

        # Create Max LOD dropdown (LOD0-LOD7, default LOD5)
        self.max_lod_dropdown = BL_UI_Dropdown(max_lod_dropdown_x, button_y, lod_dropdown_width, button_height)
        self.max_lod_dropdown.init(context)
        self.max_lod_dropdown.set_items(["LOD0", "LOD1", "LOD2", "LOD3", "LOD4", "LOD5", "LOD6", "LOD7"])
        self.max_lod_dropdown._selected_index = 5  # Default to LOD5
        self.max_lod_dropdown.on_change = self._on_max_lod_changed

        # Create Auto LOD checkbox
        self.auto_lod_checkbox = BL_UI_Checkbox(auto_lod_x, button_y, auto_lod_width, button_height)
        self.auto_lod_checkbox.text = "Auto LOD"
        self.auto_lod_checkbox._text_size = 12
        self.auto_lod_checkbox.checked = True  # Start enabled
        self.auto_lod_checkbox.on_change = self._handle_auto_lod_change
        self.auto_lod_checkbox.init(context)

        # Create Cancel button (FIRST, on the left)
        self.cancel_button = BL_UI_Button(buttons_start_x, button_y, button_width, button_height)
        self.cancel_button.text = "Cancel"
        # Normal: #1d1d1d = RGB(29, 29, 29)
        self.cancel_button._normal_bg_color = (0.114, 0.114, 0.114, 1.0)
        # Hover: #797979 = RGB(121, 121, 121)
        self.cancel_button._hover_bg_color = (0.475, 0.475, 0.475, 1.0)
        self.cancel_button._pressed_bg_color = (0.08, 0.08, 0.08, 1.0)
        self.cancel_button.set_mouse_up(self._handle_cancel)
        self.cancel_button.init(context)

        # Create Accept button (SECOND, on the right)
        accept_x = buttons_start_x + button_width + button_spacing
        self.accept_button = BL_UI_Button(accept_x, button_y, button_width, button_height)
        self.accept_button.text = "Accept"
        # Normal: #0c8ce9 = RGB(12, 140, 233) = (12/255, 140/255, 233/255)
        self.accept_button._normal_bg_color = (0.047, 0.549, 0.914, 1.0)
        # Hover: slightly lighter blue
        self.accept_button._hover_bg_color = (0.067, 0.629, 1.0, 1.0)
        # Pressed: slightly darker blue
        self.accept_button._pressed_bg_color = (0.027, 0.469, 0.834, 1.0)
        self.accept_button.set_mouse_up(self._handle_accept)
        self.accept_button.init(context)

        # ========================================
        # TOP TOOLBAR (LOD Slider)
        # ========================================
        toolbar_gap = 8  # Gap between bottom and top toolbar
        top_panel_y = panel_y + panel_height + toolbar_gap

        # Top toolbar dimensions (label + slider + divider + wireframe button)
        lod_label_width = 60  # Width for "LOD0", "LOD1", etc.
        label_to_slider_gap = 2
        slider_width = 240
        slider_to_divider_gap = 8
        divider_spacing = 16  # Space for divider line
        wireframe_button_size = button_height  # Square button
        top_right_padding = 8

        # Calculate top toolbar width
        top_content_width = (lod_label_width + label_to_slider_gap + slider_width +
                            slider_to_divider_gap + divider_spacing + wireframe_button_size +
                            top_right_padding)
        top_panel_width = top_content_width + panel_padding * 2
        top_panel_x = (area.width - top_panel_width) / 2

        # Create top background panel
        self.top_background_panel = BL_UI_Widget(top_panel_x, top_panel_y, top_panel_width, panel_height)
        self.top_background_panel._bg_color = (0.114, 0.114, 0.114, 1.0)  # #1d1d1d
        self.top_background_panel.init(context)

        # Center widgets vertically within top panel
        top_widget_y = top_panel_y + (panel_height - button_height) / 2

        # Calculate positions for top toolbar elements
        lod_label_x = top_panel_x + panel_padding + 8  # 8px left padding
        slider_x = lod_label_x + lod_label_width + label_to_slider_gap
        top_divider_x = slider_x + slider_width + slider_to_divider_gap
        wireframe_x = top_divider_x + divider_spacing

        # Store label position and divider position for drawing
        self.lod_slider_label_x = lod_label_x
        self.lod_slider_label_y = top_widget_y + button_height / 2
        self.lod_slider_label_text = "LOD0"  # Default label

        # Store divider position
        self.top_divider_x = top_divider_x
        self.top_divider_y_start = top_panel_y + 8
        self.top_divider_y_end = top_panel_y + panel_height - 8

        # Create LOD slider
        self.lod_slider = BL_UI_Slider(slider_x, top_widget_y, slider_width, button_height)
        self.lod_slider.init(context)
        self.lod_slider.on_value_changed = self._handle_slider_change

        # Create wireframe toggle button
        self.wireframe_toggle = BL_UI_ToggleButton(wireframe_x, top_widget_y, wireframe_button_size)
        # Set icon path (fallback to "W" text if icon not found)
        addon_dir = Path(__file__).parent.parent
        icon_path = addon_dir / "electron_app" / "assets" / "icons" / "wireframe_32.png"
        if icon_path.exists():
            self.wireframe_toggle.icon_path = str(icon_path)
        else:
            # Fallback to text if icon not found
            self.wireframe_toggle.icon_text = "W"
        self.wireframe_toggle.on_toggle = self._handle_wireframe_toggle
        self.wireframe_toggle.init(context)

        self.visible = True

    def _handle_slider_change(self, lod_level):
        """Handle LOD slider value change."""
        self.current_preview_lod = lod_level
        self.lod_slider_label_text = f"LOD{lod_level}"
        print(f"  🎚️  Slider changed to LOD{lod_level}")

        # Update visibility immediately
        self.update_lod_visibility()

    def _handle_wireframe_toggle(self, toggled):
        """Handle wireframe toggle button."""
        import bpy
        self.wireframe_enabled = toggled
        print(f"  🔲  Wireframe {'enabled' if toggled else 'disabled'}")

        # Apply wireframe to all imported objects
        for obj in self.imported_objects:
            if hasattr(obj, 'show_wire'):
                obj.show_wire = toggled
                obj.show_all_edges = toggled

        # Force viewport update
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    def _disable_wireframe(self):
        """Disable wireframe mode and reset the toggle button."""
        import bpy

        # Disable wireframe on all imported objects
        for obj in self.imported_objects:
            if hasattr(obj, 'show_wire'):
                obj.show_wire = False
                obj.show_all_edges = False

        # Reset wireframe state
        self.wireframe_enabled = False

        # Reset toggle button visual state if it exists
        if self.wireframe_toggle:
            self.wireframe_toggle.is_toggled = False

        # Force viewport update
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        print("  🔲  Wireframe disabled")

    def _handle_auto_lod_change(self, checked):
        """Handle Auto LOD checkbox change."""
        self.auto_lod_enabled = checked
        print(f"Auto LOD {'enabled' if self.auto_lod_enabled else 'disabled'}")

    def update_lod_visibility(self):
        """Show/hide LODs based on slider position.

        Only the selected LOD (from slider) is visible at its original position.
        All LODs remain at their original positions (no X offset).
        """
        import bpy
        from ..operations.asset_processor import extract_lod_from_object_name

        if not self.imported_objects:
            return

        print(f"\n  👁️  Updating LOD visibility (Current LOD: {self.current_preview_lod})")

        # Update visibility for all imported objects
        for obj in self.imported_objects:
            # Skip if object no longer exists or isn't a mesh
            if not obj or obj.name not in bpy.data.objects:
                continue
            if obj.type != 'MESH' or not obj.data:
                continue

            # Get LOD level from object name
            lod_level = extract_lod_from_object_name(obj.name)

            # Only show the currently selected LOD using the eye icon (hide_viewport)
            # Also ensure the monitor/display icon is NOT hiding the object (hide_set)
            if lod_level == self.current_preview_lod:
                obj.hide_viewport = False  # Eye icon - visible
                obj.hide_set(False)  # Monitor icon - enabled in viewport
            else:
                obj.hide_viewport = True  # Eye icon - hidden
                obj.hide_set(False)  # Monitor icon - enabled in viewport (so eye icon works)

        # Update text label visibility - only show label for current LOD
        for text_obj, lod_level in self.lod_text_objects:
            if text_obj and text_obj.name in bpy.data.objects:
                if lod_level == self.current_preview_lod:
                    text_obj.hide_viewport = False
                    text_obj.hide_render = False
                else:
                    text_obj.hide_viewport = True
                    text_obj.hide_render = True

        # Force viewport update
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        print(f"  ✅ Visibility updated: Showing LOD{self.current_preview_lod}")

    def _handle_accept(self, button):
        """Handle Accept button click."""
        print("Accepted Import")

        # Disable wireframe mode if it was enabled
        if self.wireframe_enabled:
            self._disable_wireframe()

        # Get selected min LOD level from dropdown
        selected_lod_text = self.min_lod_dropdown.get_selected_item() if self.min_lod_dropdown else None
        if selected_lod_text:
            # Extract LOD number from "LOD2" -> 2
            import re
            match = re.search(r'LOD(\d+)', selected_lod_text)
            target_lod = int(match.group(1)) if match else 0
        else:
            target_lod = 0

        # Get selected max LOD level from dropdown
        max_lod_text = self.max_lod_dropdown.get_selected_item() if self.max_lod_dropdown else None
        if max_lod_text:
            match = re.search(r'LOD(\d+)', max_lod_text)
            max_lod = int(match.group(1)) if match else 5
        else:
            max_lod = 5

        # Step 0: Reset LOD positions and delete text labels
        self.reset_lod_positions_and_cleanup()

        # Step 1: Apply material from selected LOD to all LOD levels
        print(f"\n  🎨 Applying material from LOD{target_lod} to all LOD levels")
        self._apply_material_to_all_lods(target_lod)

        # Step 2: Apply LOD filtering if target LOD > 0 (BEFORE auto LOD generation)
        # This renames LODs so that the selected min LOD becomes LOD0
        if target_lod > 0:
            print(f"\n  📊 Applying LOD filter: keeping LOD{target_lod} and above")
            self._apply_lod_filter(target_lod)
            # After filtering, the base is now LOD0, so we generate from 0 to max_lod
            adjusted_min_lod = 0
        else:
            adjusted_min_lod = target_lod

        # Step 3: Generate auto LOD levels if enabled (AFTER filtering)
        if self.auto_lod_enabled:
            print(f"\n  🔧 Generating Auto LOD levels (LOD{adjusted_min_lod} to LOD{max_lod})")
            self._generate_auto_lods(adjusted_min_lod, max_lod)

        # Step 4: Clean up unused materials
        print(f"\n  🧹 Cleaning up unused materials")
        self._cleanup_unused_materials()

        # Step 5: Show only the lowest LOD level (highest number)
        print(f"\n  👁️ Setting visibility: showing only lowest LOD")
        self._show_only_lowest_lod()

        if self.on_accept:
            self.on_accept()

    def _generate_auto_lods(self, min_lod, max_lod):
        """Generate LOD levels using decimate modifier.

        This creates LOD levels from the minimum LOD (highest quality) to the maximum LOD
        (lowest quality) by duplicating objects and applying decimate modifiers.

        Args:
            min_lod: Starting LOD level (e.g., 0 = highest quality)
            max_lod: Ending LOD level (e.g., 5 = lowest quality)
        """
        import bpy
        from ..operations.asset_processor import extract_lod_from_object_name, set_ioi_lod_properties

        # Find the object at min_lod level to use as the base
        base_objects = []
        for obj in self.imported_objects:
            if not obj or obj.name not in bpy.data.objects:
                continue
            if obj.type != 'MESH' or not obj.data:
                continue

            lod_level = extract_lod_from_object_name(obj.name)
            if lod_level == min_lod:
                base_objects.append(obj)

        if not base_objects:
            print(f"  ⚠️  No objects found at LOD{min_lod} to use as base for auto LOD generation")
            return

        print(f"  📋 Found {len(base_objects)} base object(s) at LOD{min_lod}")

        # Calculate decimation ratios based on steps from base LOD
        # Each step is 50% of the base: step 1 = 50%, step 2 = 25%, step 3 = 12.5%, etc.
        print(f"  📊 LOD decimation ratios (relative to LOD{min_lod}):")

        # Generate LOD levels
        new_objects = []
        for base_obj in base_objects:
            # Get polycount of base object
            base_polycount = len(base_obj.data.polygons)

            for target_lod in range(min_lod + 1, max_lod + 1):
                # Skip if this LOD already exists
                existing = False
                for obj in self.imported_objects:
                    if obj and obj.name in bpy.data.objects:
                        if extract_lod_from_object_name(obj.name) == target_lod:
                            # Check if it's the same variation (same parent)
                            if obj.parent == base_obj.parent:
                                existing = True
                                break

                if existing:
                    print(f"    ⏭️  LOD{target_lod} already exists for {base_obj.name}, skipping")
                    continue

                # Calculate decimation ratio based on steps from base LOD
                # Steps from base: LOD(min+1) = 1 step, LOD(min+2) = 2 steps, etc.
                steps_from_base = target_lod - min_lod
                ratio = 0.5 ** steps_from_base  # 50% per step

                # Duplicate base object
                new_obj = base_obj.copy()
                new_obj.data = base_obj.data.copy()
                bpy.context.collection.objects.link(new_obj)

                # Update name to reflect new LOD level
                import re
                old_name = new_obj.name
                if "_LOD_" in old_name:
                    # IOI format
                    parts = old_name.split("_LOD_")
                    if len(parts) == 2:
                        base_name = parts[0]
                        set_ioi_lod_properties(new_obj, target_lod)
                else:
                    # Simple format
                    new_name = re.sub(r'_?LOD\d+', f'_LOD{target_lod}', old_name)
                    new_obj.name = new_name
                    set_ioi_lod_properties(new_obj, target_lod)

                # Add decimate modifier
                modifier = new_obj.modifiers.new(name=f"Decimate_LOD{target_lod}", type='DECIMATE')
                modifier.decimate_type = 'COLLAPSE'  # Use edge collapse method
                modifier.ratio = ratio
                modifier.use_collapse_triangulate = True

                # Preserve UV seams and sharp edges
                modifier.delimit = {'UV'}  # Preserve UV seam boundaries
                modifier.use_symmetry = False  # Don't force symmetry

                # Apply the modifier to bake the decimation
                bpy.context.view_layer.objects.active = new_obj
                bpy.ops.object.modifier_apply(modifier=modifier.name)

                # Calculate new polycount
                new_polycount = len(new_obj.data.polygons)

                print(f"    ✅ Created LOD{target_lod}: {base_polycount:,} → {new_polycount:,} tris ({ratio*100:.1f}% of LOD{min_lod}, step {steps_from_base})")

                # Add to tracking lists
                new_objects.append(new_obj)
                self.imported_objects.append(new_obj)

        print(f"  ✅ Generated {len(new_objects)} new LOD object(s)")

    def _apply_material_to_all_lods(self, target_lod):
        """Apply material from target LOD to all LOD levels and rename it.

        Args:
            target_lod: The LOD level whose material to use for all LODs
        """
        import bpy
        import re
        from ..operations.asset_processor import extract_lod_from_object_name

        # Step 1: Find the material from the target LOD level
        target_material = None
        target_obj = None

        for obj in self.imported_objects:
            if not obj or obj.name not in bpy.data.objects:
                continue
            if obj.type != 'MESH' or not obj.data:
                continue

            # Check if this object is at the target LOD level
            lod_level = extract_lod_from_object_name(obj.name)
            if lod_level == target_lod:
                # Get the material from this object
                if obj.data.materials and len(obj.data.materials) > 0:
                    target_material = obj.data.materials[0]
                    target_obj = obj
                    break

        if not target_material:
            print(f"  ⚠️  No material found on LOD{target_lod}, skipping material application")
            return

        print(f"  ✅ Found material '{target_material.name}' on LOD{target_lod}")

        # Step 2: Remove LOD suffix from material name
        old_mat_name = target_material.name
        # Remove patterns like _LOD0, _LOD1, _LOD_0_______, etc.
        new_mat_name = re.sub(r'_LOD_[_0-9]{8}', '', old_mat_name)  # IOI format
        new_mat_name = re.sub(r'_LOD\d+', '', new_mat_name)  # Standard format

        if new_mat_name != old_mat_name:
            target_material.name = new_mat_name
            print(f"  ✏️  Renamed material: '{old_mat_name}' → '{new_mat_name}'")

        # Step 3: Apply this material to ALL LOD levels
        materials_applied = 0
        for obj in self.imported_objects:
            if not obj or obj.name not in bpy.data.objects:
                continue
            if obj.type != 'MESH' or not obj.data:
                continue

            # Clear existing materials and apply the target material
            obj.data.materials.clear()
            obj.data.materials.append(target_material)
            materials_applied += 1

        print(f"  ✅ Applied material '{target_material.name}' to {materials_applied} object(s)")

    def _apply_lod_filter(self, target_lod):
        """Filter and rename LODs based on selection.

        Deletes all LODs below target_lod and renamesremaining LODs.
        Example: If target_lod=2, delete LOD0 and LOD1, rename LOD2→LOD0, LOD3→LOD1, etc.

        Args:
            target_lod: The LOD level to start from (becomes new LOD0)
        """
        import bpy
        from ..operations.asset_processor import extract_lod_from_object_name, set_ioi_lod_properties

        objects_to_delete = []
        objects_to_rename = []

        # Step 1: Categorize objects by LOD level
        for obj in list(self.imported_objects):
            if not obj or obj.name not in bpy.data.objects:
                continue

            if obj.type != 'MESH' or not obj.data:
                continue

            # Get LOD level from object name
            lod_level = extract_lod_from_object_name(obj.name)

            if lod_level < target_lod:
                # Delete this object
                objects_to_delete.append(obj)
            else:
                # Rename this object
                objects_to_rename.append((obj, lod_level))

        # Step 2: Delete lower LODs
        print(f"  🗑️  Deleting {len(objects_to_delete)} object(s) from LOD levels below LOD{target_lod}")
        for obj in objects_to_delete:
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
                self.imported_objects.remove(obj)
            except:
                pass

        # Step 3: Rename remaining objects
        print(f"  ✏️  Renaming {len(objects_to_rename)} object(s) to new LOD levels")
        for obj, old_lod in objects_to_rename:
            new_lod = old_lod - target_lod

            # Replace LOD number in name
            # Pattern: _LOD_X_______ or _LODX
            old_name = obj.name

            # Handle IOI format: _LOD_X_______
            if "_LOD_" in old_name:
                # Split at _LOD_ and rebuild
                parts = old_name.split("_LOD_")
                if len(parts) == 2:
                    base_name = parts[0]
                    # Set new LOD properties and get new name
                    set_ioi_lod_properties(obj, new_lod)
                    print(f"    ✅ Renamed '{old_name}' (LOD{old_lod}) → '{obj.name}' (LOD{new_lod})")
            else:
                # Handle simple format: _LOD0, _LOD1
                import re
                new_name = re.sub(r'_?LOD\d+', f'_LOD{new_lod}', old_name)
                if new_name != old_name:
                    obj.name = new_name
                    set_ioi_lod_properties(obj, new_lod)
                    print(f"    ✅ Renamed '{old_name}' (LOD{old_lod}) → '{new_name}' (LOD{new_lod})")

        print(f"  ✅ LOD filtering complete")

    def _cleanup_unused_materials(self):
        """Remove all materials that are not being used by any imported objects."""
        import bpy

        # Step 1: Find which materials are currently in use by imported objects
        materials_in_use = set()
        for obj in self.imported_objects:
            if not obj or obj.name not in bpy.data.objects:
                continue
            if obj.type != 'MESH' or not obj.data:
                continue

            # Collect all materials used by this object
            for mat_slot in obj.data.materials:
                if mat_slot:
                    materials_in_use.add(mat_slot.name)

        print(f"  📋 Materials in use: {len(materials_in_use)}")
        for mat_name in materials_in_use:
            print(f"    - {mat_name}")

        # Step 2: Remove materials that were imported but are no longer in use
        removed_count = 0
        for mat in list(self.imported_materials):
            try:
                # Store name before any operations that might delete it
                if not mat or mat.name not in bpy.data.materials:
                    continue

                mat_name = mat.name  # Store name before deletion

                # If this material is not in use, remove it
                if mat_name not in materials_in_use:
                    bpy.data.materials.remove(mat, do_unlink=True)
                    removed_count += 1
                    print(f"    🗑️  Removed unused material: {mat_name}")
            except ReferenceError:
                # Material already deleted, skip
                pass
            except Exception as e:
                # For other errors, try to get name safely
                try:
                    error_name = mat.name
                except:
                    error_name = "<deleted>"
                print(f"    ⚠️  Could not remove material '{error_name}': {e}")

        # Step 3: Also check for materials created during import (not just tracked ones)
        for mat_name in list(bpy.data.materials.keys()):
            try:
                # Skip if it was there before import
                if mat_name in self.materials_before_import:
                    continue

                mat = bpy.data.materials.get(mat_name)
                if not mat:
                    continue

                # Store name before deletion
                current_mat_name = mat.name

                # If not in use, remove it
                if current_mat_name not in materials_in_use:
                    bpy.data.materials.remove(mat, do_unlink=True)
                    removed_count += 1
                    print(f"    🗑️  Removed unused material: {current_mat_name}")
            except ReferenceError:
                # Material already deleted, skip
                pass
            except Exception as e:
                # For other errors, use the mat_name from the loop
                print(f"    ⚠️  Could not remove material '{mat_name}': {e}")

        if removed_count > 0:
            print(f"  ✅ Removed {removed_count} unused material(s)")
        else:
            print(f"  ℹ️  No unused materials to remove")

    def _show_only_lowest_lod(self):
        """Show all LOD levels in viewport after accepting import."""
        import bpy
        from ..operations.asset_processor import extract_lod_from_object_name

        # Find all LOD levels in imported objects
        lod_levels = set()
        for obj in self.imported_objects:
            if not obj or obj.name not in bpy.data.objects:
                continue
            if obj.type != 'MESH' or not obj.data:
                continue

            lod_level = extract_lod_from_object_name(obj.name)
            lod_levels.add(lod_level)

        if not lod_levels:
            print(f"  ℹ️  No LOD levels found")
            return

        print(f"  📊 Available LOD levels: {sorted(lod_levels)}")
        print(f"  👁️ Showing all LOD levels")

        # Show all LODs using the eye icon
        for obj in self.imported_objects:
            if not obj or obj.name not in bpy.data.objects:
                continue
            if obj.type != 'MESH' or not obj.data:
                continue

            lod_level = extract_lod_from_object_name(obj.name)

            # Show all LODs using the eye icon (hide_viewport)
            # Also ensure the monitor/display icon is NOT hiding the object (hide_set)
            obj.hide_viewport = False  # Eye icon - visible
            obj.hide_set(False)  # Monitor icon - enabled in viewport

        print(f"  ✅ Visibility set: All {len(lod_levels)} LOD level(s) visible")

    def _handle_cancel(self, button):
        """Handle Cancel button click."""
        print("Cancelling Import - Cleaning up...")

        # Disable wireframe mode if it was enabled
        if self.wireframe_enabled:
            self._disable_wireframe()

        # Delete text labels first
        self._delete_text_labels()

        # Then cleanup imported objects and materials
        self._cleanup_import()

        if self.on_cancel:
            self.on_cancel()

    def _cleanup_import(self):
        """Remove all imported objects and materials."""
        # Remove imported objects
        removed_objects = 0
        for obj in list(self.imported_objects):
            try:
                if obj and obj.name in bpy.data.objects:
                    bpy.data.objects.remove(obj, do_unlink=True)
                    removed_objects += 1
            except:
                pass

        if removed_objects > 0:
            print(f"  🗑️  Removed {removed_objects} imported object(s)")

        # Remove imported materials (only if not used by other objects)
        removed_materials = 0
        skipped_materials = 0

        # Get all materials created during import
        materials_to_check = set()
        for mat in list(self.imported_materials):
            if mat and mat.name in bpy.data.materials:
                materials_to_check.add(mat)

        for mat_name in list(bpy.data.materials.keys()):
            if mat_name not in self.materials_before_import:
                mat = bpy.data.materials.get(mat_name)
                if mat:
                    materials_to_check.add(mat)

        # Check each material and only delete if not used
        for mat in materials_to_check:
            try:
                if mat.name not in bpy.data.materials:
                    continue  # Already deleted

                # Check if material is used by any remaining objects
                is_used = False
                for obj in bpy.data.objects:
                    if obj.type == 'MESH' and obj.data:
                        for mat_slot in obj.data.materials:
                            if mat_slot and mat_slot.name == mat.name:
                                is_used = True
                                break
                    if is_used:
                        break

                if not is_used:
                    # Material is not used, safe to delete
                    bpy.data.materials.remove(mat, do_unlink=True)
                    removed_materials += 1
                else:
                    # Material is still used by other objects, skip
                    skipped_materials += 1
                    print(f"  ⏭️  Skipped material '{mat.name}' (used by existing objects)")
            except Exception as e:
                print(f"  ⚠️  Error checking material: {e}")

        if removed_materials > 0:
            print(f"  🗑️  Removed {removed_materials} unused imported material(s)")
        if skipped_materials > 0:
            print(f"  ℹ️  Kept {skipped_materials} material(s) in use by other objects")

        print("✅ Import cleanup complete")

    def set_imported_data(self, objects, materials, materials_before, original_scene=None, temp_scene=None):
        """Store references to imported data for cleanup.

        Args:
            objects: List of imported Blender objects
            materials: List of created materials
            materials_before: Set of material names before import
            original_scene: Optional reference to original scene
            temp_scene: Optional reference to temporary preview scene
        """
        self.imported_objects = objects
        self.imported_materials = materials
        self.materials_before_import = materials_before
        self.original_scene = original_scene
        self.temp_scene = temp_scene

    def set_lod_levels(self, lod_levels):
        """Set available LOD levels and update dropdown.

        Args:
            lod_levels: List of LOD level numbers (e.g., [0, 1, 2, 3])
        """
        self.lod_levels = sorted(lod_levels)
        if self.min_lod_dropdown and self.lod_levels:
            items = [f"LOD{level}" for level in self.lod_levels]
            self.min_lod_dropdown.set_items(items)
            # Set callback for when dropdown selection changes
            self.min_lod_dropdown.on_change = self._on_lod_selection_changed
            print(f"  🔽 Min LOD dropdown populated with {len(items)} LOD levels: {items}")
            print(f"     ℹ️  Click the dropdown to see all available LOD levels")
            # Default to lowest LOD
            self.selected_lod_level = self.lod_levels[0] if self.lod_levels else 0

        # Update LOD slider with available LODs
        if self.lod_slider and self.lod_levels:
            self.lod_slider.set_available_lods(self.lod_levels)
            # Set slider to lowest available LOD
            lowest_lod = self.lod_levels[0] if self.lod_levels else 0
            self.lod_slider.set_value(lowest_lod)
            self.current_preview_lod = lowest_lod
            self.lod_slider_label_text = f"LOD{lowest_lod}"
            print(f"  🎚️  LOD slider initialized with {len(self.lod_levels)} LOD level(s), starting at LOD{lowest_lod}")

            # Initialize min/max markers on slider
            self._update_slider_minmax_markers()

    def _update_slider_minmax_markers(self):
        """Update the slider's min/max LOD markers based on dropdown selections."""
        if not self.lod_slider:
            return

        # Get min LOD from dropdown
        min_lod = 0  # Default
        if self.min_lod_dropdown:
            min_lod_text = self.min_lod_dropdown.get_selected_item()
            if min_lod_text:
                import re
                match = re.search(r'LOD(\d+)', min_lod_text)
                if match:
                    min_lod = int(match.group(1))

        # Get max LOD from dropdown
        max_lod = 5  # Default
        if self.max_lod_dropdown:
            max_lod_text = self.max_lod_dropdown.get_selected_item()
            if max_lod_text:
                import re
                match = re.search(r'LOD(\d+)', max_lod_text)
                if match:
                    max_lod = int(match.group(1))

        # Update slider markers
        self.lod_slider.set_min_max_lods(min_lod, max_lod)

    def _on_lod_selection_changed(self, selected_text):
        """Handle min LOD dropdown selection change - update text colors and markers."""
        import re
        import bpy

        # Extract LOD number from selected text (e.g., "LOD2" -> 2)
        match = re.search(r'LOD(\d+)', selected_text)
        if match:
            selected_lod = int(match.group(1))
            self.selected_lod_level = selected_lod

            print(f"  🎨 Updating text colors for selected LOD{selected_lod}")

            # Update slider min/max markers
            self._update_slider_minmax_markers()

            # Update all text object colors
            for item in self.lod_text_objects:
                try:
                    # Handle both tuple (text_obj, lod_level) and just text_obj
                    if isinstance(item, tuple):
                        text_obj, lod_level = item
                    else:
                        # Try to extract LOD from name if not a tuple
                        text_obj = item
                        name_match = re.search(r'LOD(\d+)', text_obj.name)
                        lod_level = int(name_match.group(1)) if name_match else 0

                    # Check if object still exists
                    if text_obj and text_obj.name in bpy.data.objects:
                        text_data = text_obj.data
                        # Clear existing materials
                        text_data.materials.clear()

                        # Apply new color based on LOD hierarchy
                        # Selected = Blue, Below selected (lower numbers) = Black, Above selected (higher numbers) = White
                        if lod_level == selected_lod:
                            # Vibrant blue for selected
                            text_data.materials.append(self._get_or_create_text_material("LOD_Selected", (0.1, 0.4, 1.0, 1.0)))
                        elif lod_level < selected_lod:
                            # Almost black for LODs with lower numbers (worse quality)
                            text_data.materials.append(self._get_or_create_text_material("LOD_Below", (0.15, 0.15, 0.15, 1.0)))
                        else:
                            # Almost white for LODs with higher numbers (better quality)
                            text_data.materials.append(self._get_or_create_text_material("LOD_Above", (0.9, 0.9, 0.9, 1.0)))
                except:
                    pass

    def _on_max_lod_changed(self, selected_text):
        """Handle max LOD dropdown selection change - update markers."""
        print(f"  📊 Max LOD changed to: {selected_text}")
        # Update slider min/max markers
        self._update_slider_minmax_markers()

    def position_lods_for_preview(self):
        """Position LODs in Y direction with 1m gap and create text labels showing LOD level and polycount."""
        import bpy
        from ..operations.asset_processor import extract_lod_from_object_name

        print(f"\n{'='*80}")
        print(f"📐 POSITIONING LODs FOR PREVIEW")
        print(f"{'='*80}")

        # Group objects by attach root (variation), then by LOD level
        # This ensures each variation's LODs are positioned independently
        variations = {}
        for obj in self.imported_objects:
            if not obj or obj.name not in bpy.data.objects:
                continue
            if obj.type != 'MESH' or not obj.data:
                continue

            # Get the attach root (parent) of this object
            parent = obj.parent
            parent_name = parent.name if parent else "no_parent"

            # Initialize this variation if not seen before
            if parent_name not in variations:
                variations[parent_name] = {}

            # Group by LOD level within this variation
            lod_level = extract_lod_from_object_name(obj.name)
            if lod_level not in variations[parent_name]:
                variations[parent_name][lod_level] = []
            variations[parent_name][lod_level].append(obj)

        print(f"  📊 Found {len(variations)} variation(s) with LOD levels")

        # Process each variation independently
        for variation_name in sorted(variations.keys()):
            lods_by_level = variations[variation_name]

            print(f"\n  📦 Processing variation: {variation_name}")

            for lod_level in sorted(lods_by_level.keys()):
                objects = lods_by_level[lod_level]

                # Calculate bounding box for this LOD level
                min_x, max_x = None, None
                min_z, max_z = None, None
                total_tris = 0

                for obj in objects:
                    # Store original position (in local space relative to parent)
                    self.lod_original_positions[obj.name] = obj.location.copy()

                    # Calculate world bounding box
                    bbox_corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
                    for corner in bbox_corners:
                        if min_x is None or corner.x < min_x:
                            min_x = corner.x
                        if max_x is None or corner.x > max_x:
                            max_x = corner.x
                        if min_z is None or corner.z < min_z:
                            min_z = corner.z
                        if max_z is None or corner.z > max_z:
                            max_z = corner.z

                    # Count triangles
                    if obj.data:
                        total_tris += len(obj.data.polygons)

                width = max_x - min_x if min_x is not None else 0.0
                height = max_z - min_z if min_z is not None else 0.0
                depth = 0.0  # Will calculate from Y bounds

                # Calculate depth for text sizing
                min_y, max_y = None, None
                for obj in objects:
                    bbox_corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
                    for corner in bbox_corners:
                        if min_y is None or corner.y < min_y:
                            min_y = corner.y
                        if max_y is None or corner.y > max_y:
                            max_y = corner.y
                depth = max_y - min_y if min_y is not None else 0.0

                # Calculate text size based on mesh size (5% of the largest dimension)
                max_dimension = max(width, depth, height)
                text_size = max(0.1, max_dimension * 0.05)  # At least 0.1, up to 5% of mesh size

                # Calculate the center of the bounding box in local space
                # This will be used to position the text
                center_x = (min_x + max_x) / 2.0 if min_x is not None else 0.0
                center_y = (min_y + max_y) / 2.0 if min_y is not None else 0.0

                # Don't move objects - they stay at their original positions
                print(f"    📍 LOD{lod_level}: {len(objects)} object(s), {total_tris:,} tris at original position")

                # Create text object showing LOD level and polycount
                text_data = bpy.data.curves.new(name=f"{variation_name}_LOD{lod_level}_Label", type='FONT')
                text_data.body = f"LOD{lod_level}\n{total_tris:,} tris"
                text_data.align_x = 'CENTER'
                text_data.align_y = 'BOTTOM'
                text_data.size = text_size  # Text size based on mesh size

                text_obj = bpy.data.objects.new(name=f"{variation_name}_LOD{lod_level}_Label", object_data=text_data)
                bpy.context.collection.objects.link(text_obj)

                # Rotate text 90 degrees on X axis (to face upward/toward camera)
                text_obj.rotation_euler.x = math.radians(90)

                # Set text color based on LOD hierarchy
                # Selected = Blue, Below selected (lower numbers) = Black, Above selected (higher numbers) = White
                selected_lod = self.selected_lod_level if self.selected_lod_level is not None else 0
                if lod_level == selected_lod:
                    # Vibrant blue color for selected LOD
                    text_data.materials.append(self._get_or_create_text_material("LOD_Selected", (0.1, 0.4, 1.0, 1.0)))
                elif lod_level < selected_lod:
                    # Almost black for LODs with lower numbers (worse quality)
                    text_data.materials.append(self._get_or_create_text_material("LOD_Below", (0.15, 0.15, 0.15, 1.0)))
                else:
                    # Almost white for LODs with higher numbers (better quality)
                    text_data.materials.append(self._get_or_create_text_material("LOD_Above", (0.9, 0.9, 0.9, 1.0)))

                # Position text above the LOD at its original position
                # Get the first object's parent (attach root) to position text relative to it
                if objects:
                    first_obj = objects[0]
                    if first_obj.parent:
                        # Position text relative to parent
                        text_obj.parent = first_obj.parent
                        # Center X on the LOD's bounding box center (no offset)
                        text_obj.location.x = center_x - first_obj.parent.location.x
                        # Center Y on the bounding box center (in parent's local space)
                        text_obj.location.y = center_y - first_obj.parent.location.y
                        # Position above the highest point
                        text_obj.location.z = max_z - first_obj.parent.location.z + text_size * 1.5
                    else:
                        # No parent, use world space
                        text_obj.location.x = center_x
                        text_obj.location.y = center_y
                        text_obj.location.z = max_z + text_size * 1.5 if max_z is not None else text_size * 1.5

                # Store text object for later cleanup (with LOD level info)
                self.lod_text_objects.append((text_obj, lod_level))

                print(f"    ✅ Created label '{text_obj.name}' (size: {text_size:.2f}m)")

        print(f"✅ Positioned {len(variations)} variation(s) with LOD levels for preview")

        # Initialize visibility: show only LOD0 by default
        print(f"\n  👁️  Initializing LOD visibility (showing LOD{self.current_preview_lod} only)")
        self.update_lod_visibility()

    def _get_or_create_text_material(self, mat_name, color):
        """Get or create a material for text objects with specified color.

        Args:
            mat_name: Name of the material
            color: RGBA tuple (r, g, b, a)

        Returns:
            Material object
        """
        import bpy

        # Check if material already exists
        if mat_name in bpy.data.materials:
            return bpy.data.materials[mat_name]

        # Create new material
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True

        # Get the principled BSDF node
        nodes = mat.node_tree.nodes
        bsdf = nodes.get("Principled BSDF")

        if bsdf:
            # Set base color
            bsdf.inputs["Base Color"].default_value = color
            # Make it emit light so it's visible
            bsdf.inputs["Emission Strength"].default_value = 0.5
            bsdf.inputs["Emission Color"].default_value = color

        return mat

    def _delete_text_labels(self):
        """Delete all LOD text labels."""
        import bpy

        deleted_count = 0
        for item in list(self.lod_text_objects):
            try:
                # Handle both tuple (text_obj, lod_level) and just text_obj
                text_obj = item[0] if isinstance(item, tuple) else item

                if text_obj and text_obj.name in bpy.data.objects:
                    bpy.data.objects.remove(text_obj, do_unlink=True)
                    deleted_count += 1
            except ReferenceError:
                # Text object already deleted, skip it
                pass
            except Exception as e:
                print(f"  ⚠️  Error deleting text object: {e}")

        if deleted_count > 0:
            print(f"  🗑️  Deleted {deleted_count} text label(s)")

        # Clear the list
        self.lod_text_objects.clear()

    def reset_lod_positions_and_cleanup(self):
        """Reset LOD positions to original and delete text labels."""
        import bpy

        print(f"\n{'='*80}")
        print(f"🔄 RESETTING LOD POSITIONS AND CLEANING UP LABELS")
        print(f"{'='*80}")

        # Reset object positions
        reset_count = 0
        for obj in self.imported_objects:
            try:
                # Check if object still exists
                if not obj or obj.name not in bpy.data.objects:
                    continue

                # Restore original position if we stored it
                if obj.name in self.lod_original_positions:
                    original_pos = self.lod_original_positions[obj.name]
                    obj.location = original_pos.copy()
                    reset_count += 1
            except ReferenceError:
                # Object has been deleted, skip it
                pass
            except Exception as e:
                print(f"  ⚠️  Error resetting object position: {e}")

        if reset_count > 0:
            print(f"  ✅ Reset {reset_count} object(s) to original positions")

        # Delete text objects using helper method
        self._delete_text_labels()

        # Clear the tracking dictionary
        self.lod_original_positions.clear()

        print(f"✅ LOD preview cleanup complete")

    def draw(self):
        """Draw all toolbar elements."""
        if not self.visible:
            return

        # ========================================
        # TOP TOOLBAR (LOD Slider)
        # ========================================
        # Draw top background panel
        if self.top_background_panel:
            self.top_background_panel.draw()

        # Draw LOD slider label
        if hasattr(self, 'lod_slider_label_x'):
            blf.size(0, 12)  # Same size as other labels
            text_height = blf.dimensions(0, self.lod_slider_label_text)[1]
            blf.position(0, self.lod_slider_label_x, self.lod_slider_label_y - text_height / 2, 0)
            blf.color(0, 1.0, 1.0, 1.0, 1.0)
            blf.draw(0, self.lod_slider_label_text)

        # Draw LOD slider
        if self.lod_slider:
            self.lod_slider.draw()

        # Draw top divider line
        if hasattr(self, 'top_divider_x'):
            DrawConstants.initialize()
            gpu.state.blend_set('ALPHA')

            shader = DrawConstants.uniform_shader
            vertices = [
                (self.top_divider_x, self.top_divider_y_start),
                (self.top_divider_x, self.top_divider_y_end)
            ]
            batch = batch_for_shader(shader, 'LINES', {"pos": vertices})

            shader.bind()
            shader.uniform_float("color", (0.2, 0.2, 0.2, 0.5))
            batch.draw(shader)

            gpu.state.blend_set('NONE')

        # Draw wireframe toggle button
        if self.wireframe_toggle:
            self.wireframe_toggle.draw()

        # ========================================
        # BOTTOM TOOLBAR (LOD Controls & Buttons)
        # ========================================
        # Draw background panel first
        if self.background_panel:
            self.background_panel.draw()

        # Draw Min LOD label (no colon)
        if hasattr(self, 'min_lod_label_x'):
            blf.size(0, 12)
            text_height = blf.dimensions(0, "Min LOD")[1]
            blf.position(0, self.min_lod_label_x, self.min_lod_label_y - text_height / 2, 0)
            blf.color(0, 1.0, 1.0, 1.0, 1.0)
            blf.draw(0, "Min LOD")

        # Draw Max LOD label (no colon)
        if hasattr(self, 'max_lod_label_x'):
            blf.size(0, 12)
            text_height = blf.dimensions(0, "Max LOD")[1]
            blf.position(0, self.max_lod_label_x, self.max_lod_label_y - text_height / 2, 0)
            blf.color(0, 1.0, 1.0, 1.0, 1.0)
            blf.draw(0, "Max LOD")

        # Draw divider line
        if hasattr(self, 'divider_x'):
            DrawConstants.initialize()
            gpu.state.blend_set('ALPHA')

            shader = DrawConstants.uniform_shader
            vertices = [
                (self.divider_x, self.divider_y_start),
                (self.divider_x, self.divider_y_end)
            ]
            batch = batch_for_shader(shader, 'LINES', {"pos": vertices})

            shader.bind()
            shader.uniform_float("color", (0.2, 0.2, 0.2, 0.5))
            batch.draw(shader)

            gpu.state.blend_set('NONE')

        # Draw Min LOD dropdown
        if self.min_lod_dropdown:
            self.min_lod_dropdown.draw()

        # Draw Max LOD dropdown
        if self.max_lod_dropdown:
            self.max_lod_dropdown.draw()

        # Draw Auto LOD checkbox
        if self.auto_lod_checkbox:
            self.auto_lod_checkbox.draw()

        # Draw buttons on top
        if self.cancel_button:
            self.cancel_button.draw()
        if self.accept_button:
            self.accept_button.draw()

    def handle_mouse_down(self, x, y):
        """Handle mouse down events."""
        if not self.visible:
            return False

        # Check top toolbar widgets first
        if self.lod_slider and self.lod_slider.mouse_down(x, y):
            return True
        if self.wireframe_toggle and self.wireframe_toggle.mouse_down(x, y):
            return True

        # Check dropdowns (they might be expanded)
        if self.min_lod_dropdown and self.min_lod_dropdown.mouse_down(x, y):
            return True
        if self.max_lod_dropdown and self.max_lod_dropdown.mouse_down(x, y):
            return True
        # Check Auto LOD checkbox
        if self.auto_lod_checkbox and self.auto_lod_checkbox.mouse_down(x, y):
            return True
        # Check action buttons
        if self.accept_button and self.accept_button.mouse_down(x, y):
            return True
        if self.cancel_button and self.cancel_button.mouse_down(x, y):
            return True
        return False

    def handle_mouse_up(self, x, y):
        """Handle mouse up events."""
        if not self.visible:
            return False

        # Check top toolbar widgets
        if self.lod_slider and self.lod_slider.mouse_up(x, y):
            return True
        if self.wireframe_toggle and self.wireframe_toggle.mouse_up(x, y):
            return True

        # Check action buttons
        if self.accept_button and self.accept_button.mouse_up(x, y):
            return True
        if self.cancel_button and self.cancel_button.mouse_up(x, y):
            return True
        return False

    def handle_mouse_move(self, x, y):
        """Handle mouse move events for hover effects."""
        if not self.visible:
            return

        # Handle top toolbar hover/drag states
        if self.lod_slider:
            self.lod_slider.mouse_move(x, y)
        if self.wireframe_toggle:
            self.wireframe_toggle.mouse_move(x, y)

        # Handle dropdown hover states
        if self.min_lod_dropdown:
            self.min_lod_dropdown.mouse_move(x, y)
        if self.max_lod_dropdown:
            self.max_lod_dropdown.mouse_move(x, y)

        # Handle button hover states
        if self.accept_button:
            self.accept_button.mouse_move(x, y)
        if self.cancel_button:
            self.cancel_button.mouse_move(x, y)
