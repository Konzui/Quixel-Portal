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
from ..utils.floor_plane_manager import create_floor_plane


# Pre-computed shader constants for smooth circle rendering
class DrawConstants:
    """Pre-computed shader and batch data for efficient circle rendering."""

    filled_circle_shader = None
    filled_circle_batch = None
    uniform_shader = None
    
    # Anti-aliased circle shader and quad batch
    anti_aliased_circle_shader = None
    circle_quad_batch = None
    
    # Anti-aliased circle outline shader
    anti_aliased_circle_outline_shader = None
    
    # Anti-aliased quarter-circle arc shader for borders
    anti_aliased_arc_shader = None
    
    # Anti-aliased rectangle shader
    anti_aliased_rect_shader = None
    
    # Anti-aliased border shader
    anti_aliased_border_shader = None

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
            
            # Create anti-aliased circle shader
            cls._create_anti_aliased_circle_shader()
            
            # Create anti-aliased circle outline shader
            cls._create_anti_aliased_circle_outline_shader()
            
            # Create anti-aliased quarter-circle arc shader for borders
            cls._create_anti_aliased_arc_shader()
            
            # Create anti-aliased rectangle shader
            cls._create_anti_aliased_rect_shader()
            
            # Create unit quad batch for anti-aliased circles (will be scaled/translated)
            quad_vertices = [(0, 0), (1, 0), (1, 1), (0, 1)]
            quad_indices = [(0, 1, 2), (0, 2, 3)]
            cls.circle_quad_batch = batch_for_shader(
                cls.anti_aliased_circle_shader, 'TRIS', {"pos": quad_vertices}, indices=quad_indices
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
    
    @classmethod
    def _create_anti_aliased_circle_shader(cls):
        """Create a custom shader for anti-aliased circle rendering.
        
        Uses distance-based alpha falloff with smoothstep for smooth edges.
        Uses screen-space coordinates with proper viewport handling.
        """
        vertex_shader = '''
        in vec2 pos;
        uniform vec2 center;
        uniform vec2 viewportSize;
        uniform float scale;
        
        out vec2 screenPos;
        
        void main() {
            // Transform unit quad (0,0 to 1,1) to screen space
            // Center the quad at origin, then scale and translate
            vec2 local = (pos - vec2(0.5, 0.5)) * scale;
            vec2 screen = center + local;
            screenPos = screen;
            
            // Convert screen coordinates to NDC (-1 to 1 range)
            // Blender's screen space: (0,0) at bottom-left
            vec2 ndc = vec2(
                (screen.x / viewportSize.x) * 2.0 - 1.0,
                (screen.y / viewportSize.y) * 2.0 - 1.0
            );
            
            gl_Position = vec4(ndc.x, ndc.y, 0.0, 1.0);
        }
        '''
        
        fragment_shader = '''
        uniform vec4 color;
        uniform vec2 center;
        uniform float radius;
        uniform float edgeSoftness;
        
        in vec2 screenPos;
        out vec4 fragColor;
        
        void main() {
            // Calculate distance from center in screen space (pixels)
            float dist = distance(screenPos, center);
            
            // Use smoothstep for soft edge anti-aliasing
            // The fade goes from (radius - edgeSoftness) to (radius + edgeSoftness)
            // We adjust the radius in the calling code so outer edge aligns with rectangle
            float alpha = 1.0 - smoothstep(radius - edgeSoftness, radius + edgeSoftness, dist);
            
            // Apply gamma correction to match Blender's built-in shader color handling
            // Colors appear brighter without this, suggesting they need to be in linear space
            // Convert sRGB input to linear for correct display
            vec3 linearColor = mix(
                color.rgb / 12.92,
                pow((color.rgb + 0.055) / 1.055, vec3(2.4)),
                step(0.04045, color.rgb)
            );
            
            fragColor = vec4(linearColor, color.a * alpha);
        }
        '''
        
        try:
            cls.anti_aliased_circle_shader = gpu.types.GPUShader(vertex_shader, fragment_shader)
        except Exception as e:
            # Fallback: if shader creation fails, we'll use the old method
            print(f"Warning: Failed to create anti-aliased circle shader: {e}")
            cls.anti_aliased_circle_shader = None
    
    @classmethod
    def _create_anti_aliased_circle_outline_shader(cls):
        """Create a custom shader for anti-aliased circle outline rendering.
        
        Uses distance-based alpha falloff to create smooth outline edges.
        Uses screen-space coordinates with proper viewport handling.
        """
        vertex_shader = '''
        in vec2 pos;
        uniform vec2 center;
        uniform vec2 viewportSize;
        uniform float scale;
        
        out vec2 screenPos;
        
        void main() {
            // Transform unit quad (0,0 to 1,1) to screen space
            // Center the quad at origin, then scale and translate
            vec2 local = (pos - vec2(0.5, 0.5)) * scale;
            vec2 screen = center + local;
            screenPos = screen;
            
            // Convert screen coordinates to NDC (-1 to 1 range)
            vec2 ndc = vec2(
                (screen.x / viewportSize.x) * 2.0 - 1.0,
                (screen.y / viewportSize.y) * 2.0 - 1.0
            );
            
            gl_Position = vec4(ndc.x, ndc.y, 0.0, 1.0);
        }
        '''
        
        fragment_shader = '''
        uniform vec4 color;
        uniform vec2 center;
        uniform float radius;
        uniform float thickness;
        uniform float edgeSoftness;
        
        in vec2 screenPos;
        out vec4 fragColor;
        
        void main() {
            // Calculate distance from center in screen space (pixels)
            float dist = distance(screenPos, center);
            
            // Create a ring shape: inside radius - thickness/2, outside radius + thickness/2
            float innerRadius = radius - thickness * 0.5;
            float outerRadius = radius + thickness * 0.5;
            
            // Use smoothstep for soft edge anti-aliasing on both inner and outer edges
            float innerAlpha = smoothstep(innerRadius - edgeSoftness, innerRadius + edgeSoftness, dist);
            float outerAlpha = 1.0 - smoothstep(outerRadius - edgeSoftness, outerRadius + edgeSoftness, dist);
            
            // Combine both edges (ring shape)
            float alpha = innerAlpha * outerAlpha;
            
            // Apply gamma correction to match Blender's built-in shader color handling
            // Colors appear brighter without this, suggesting they need to be in linear space
            // Convert sRGB input to linear for correct display
            vec3 linearColor = mix(
                color.rgb / 12.92,
                pow((color.rgb + 0.055) / 1.055, vec3(2.4)),
                step(0.04045, color.rgb)
            );
            
            fragColor = vec4(linearColor, color.a * alpha);
        }
        '''
        
        try:
            cls.anti_aliased_circle_outline_shader = gpu.types.GPUShader(vertex_shader, fragment_shader)
        except Exception as e:
            # Fallback: if shader creation fails, we'll use the old method
            print(f"Warning: Failed to create anti-aliased circle outline shader: {e}")
            cls.anti_aliased_circle_outline_shader = None
    
    @classmethod
    def _create_anti_aliased_arc_shader(cls):
        """Create a custom shader for anti-aliased quarter-circle arc rendering.
        
        Uses distance-based alpha falloff to create smooth arc edges.
        Only draws pixels within the specified angle range.
        """
        vertex_shader = '''
        in vec2 pos;
        uniform vec2 center;
        uniform vec2 viewportSize;
        uniform float scale;
        
        out vec2 screenPos;
        
        void main() {
            // Transform unit quad (0,0 to 1,1) to screen space
            vec2 local = (pos - vec2(0.5, 0.5)) * scale;
            vec2 screen = center + local;
            screenPos = screen;
            
            // Convert screen coordinates to NDC (-1 to 1 range)
            vec2 ndc = vec2(
                (screen.x / viewportSize.x) * 2.0 - 1.0,
                (screen.y / viewportSize.y) * 2.0 - 1.0
            );
            
            gl_Position = vec4(ndc.x, ndc.y, 0.0, 1.0);
        }
        '''
        
        fragment_shader = '''
        uniform vec4 color;
        uniform vec2 center;
        uniform float radius;
        uniform float thickness;
        uniform float edgeSoftness;
        uniform float startAngle;
        uniform float endAngle;
        
        in vec2 screenPos;
        out vec4 fragColor;
        
        // Convert sRGB to linear color space
        vec3 srgb_to_linear(vec3 srgb) {
            return mix(
                srgb / 12.92,
                pow((srgb + 0.055) / 1.055, vec3(2.4)),
                step(0.04045, srgb)
            );
        }
        
        void main() {
            // Calculate distance from center
            vec2 offset = screenPos - center;
            float dist = length(offset);
            
            // Calculate angle from center
            float angle = atan(offset.y, offset.x);
            // Normalize angle to [0, 2π]
            if (angle < 0.0) {
                angle += 6.28318530718; // 2 * PI
            }
            
            // Normalize start and end angles to [0, 2π]
            float start = startAngle;
            float end = endAngle;
            if (start < 0.0) start += 6.28318530718;
            if (end < 0.0) end += 6.28318530718;
            
            // Check if angle is within range
            bool inAngleRange = false;
            if (end > start) {
                inAngleRange = (angle >= start && angle <= end);
            } else {
                // Handle wrap-around case
                inAngleRange = (angle >= start || angle <= end);
            }
            
            if (!inAngleRange) {
                fragColor = vec4(0.0, 0.0, 0.0, 0.0);
                return;
            }
            
            // Create a ring shape: inside radius - thickness/2, outside radius + thickness/2
            float innerRadius = radius - thickness * 0.5;
            float outerRadius = radius + thickness * 0.5;
            
            // Use smoothstep for soft edge anti-aliasing on both inner and outer edges
            float innerAlpha = smoothstep(innerRadius - edgeSoftness, innerRadius + edgeSoftness, dist);
            float outerAlpha = 1.0 - smoothstep(outerRadius - edgeSoftness, outerRadius + edgeSoftness, dist);
            
            // Combine both edges (ring shape)
            float alpha = innerAlpha * outerAlpha;
            
            // Apply sRGB to linear conversion
            vec3 linearColor = srgb_to_linear(color.rgb);
            
            fragColor = vec4(linearColor, color.a * alpha);
        }
        '''
        
        try:
            cls.anti_aliased_arc_shader = gpu.types.GPUShader(vertex_shader, fragment_shader)
        except Exception as e:
            # Fallback: if shader creation fails, we'll use the old method
            print(f"Warning: Failed to create anti-aliased arc shader: {e}")
            cls.anti_aliased_arc_shader = None
    
    @classmethod
    def _create_anti_aliased_rect_shader(cls):
        """Create a custom shader for anti-aliased rectangle rendering.
        
        Uses distance-based alpha falloff on all edges for smooth anti-aliasing.
        Uses screen-space coordinates with proper viewport handling.
        """
        vertex_shader = '''
        in vec2 pos;
        uniform vec2 rectPos;
        uniform vec2 rectSize;
        uniform vec2 viewportSize;
        
        out vec2 screenPos;
        
        void main() {
            // Transform unit quad (0,0 to 1,1) to screen space
            vec2 screen = rectPos + pos * rectSize;
            screenPos = screen;
            
            // Convert screen coordinates to NDC (-1 to 1 range)
            vec2 ndc = vec2(
                (screen.x / viewportSize.x) * 2.0 - 1.0,
                (screen.y / viewportSize.y) * 2.0 - 1.0
            );
            
            gl_Position = vec4(ndc.x, ndc.y, 0.0, 1.0);
        }
        '''
        
        fragment_shader = '''
        uniform vec4 color;
        uniform vec2 rectPos;
        uniform vec2 rectSize;
        uniform float edgeSoftness;
        
        in vec2 screenPos;
        out vec4 fragColor;
        
        void main() {
            // Calculate distance to each edge (all should be positive inside the rectangle)
            float distLeft = screenPos.x - rectPos.x;
            float distRight = (rectPos.x + rectSize.x) - screenPos.x;
            float distBottom = screenPos.y - rectPos.y;
            float distTop = (rectPos.y + rectSize.y) - screenPos.y;
            
            // Find minimum distance to any edge (this is the distance to the nearest edge)
            float minDist = min(min(distLeft, distRight), min(distBottom, distTop));
            
            // Use smoothstep for soft edge anti-aliasing
            // Rectangle is opaque inside, fades smoothly at the very edges
            // edgeSoftness controls the transition width (typically 1.0-2.0 pixels)
            // When minDist >= edgeSoftness (inside): alpha = 1.0 (fully opaque)
            // When 0 < minDist < edgeSoftness (near edge): alpha fades smoothly
            // When minDist <= 0 (outside): alpha = 0.0 (transparent)
            float alpha = 1.0;
            if (minDist < edgeSoftness) {
                // Fade at edges for anti-aliasing
                alpha = smoothstep(0.0, edgeSoftness, minDist);
            }
            
            // Apply gamma correction to match Blender's built-in shader color handling
            // Convert sRGB input to linear for correct display
            vec3 linearColor = mix(
                color.rgb / 12.92,
                pow((color.rgb + 0.055) / 1.055, vec3(2.4)),
                step(0.04045, color.rgb)
            );
            
            fragColor = vec4(linearColor, color.a * alpha);
        }
        '''
        
        try:
            cls.anti_aliased_rect_shader = gpu.types.GPUShader(vertex_shader, fragment_shader)
            # Debug: verify shader was created
            # print("Anti-aliased rectangle shader created successfully")
        except Exception as e:
            # Fallback: if shader creation fails, we'll use the old method
            print(f"Warning: Failed to create anti-aliased rectangle shader: {e}")
            import traceback
            traceback.print_exc()
            cls.anti_aliased_rect_shader = None


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

    # Draw corners FIRST, then rectangles on top
    # This ensures corners blend correctly with the background for anti-aliasing,
    # and rectangles cover inner edges to maintain color consistency
    corners = [
        (x + radius, y + radius),              # Bottom-left
        (x + width - radius, y + radius),      # Bottom-right
        (x + width - radius, y + height - radius),  # Top-right
        (x + radius, y + height - radius),     # Top-left
    ]

    # Draw anti-aliased circles at corners for smooth edges
    # The rectangles drawn on top will cover the inner parts, ensuring color match
    if DrawConstants.anti_aliased_circle_shader is not None:
        aa_shader = DrawConstants.anti_aliased_circle_shader
        
        # Get viewport size for coordinate conversion
        viewport = gpu.state.viewport_get()
        viewport_width = viewport[2] if len(viewport) > 2 else 1920
        viewport_height = viewport[3] if len(viewport) > 3 else 1080
        
        # Calculate scale to cover the circle area (with some padding for edge softness)
        scale_size = (radius + 1.0) * 2.0
        
        # Ensure color is a proper tuple with 4 components (RGBA)
        if len(color) == 3:
            color_rgba = (color[0], color[1], color[2], 1.0)
        else:
            color_rgba = color
        
        for cx, cy in corners:
            # Bind shader and set uniforms for each corner
            aa_shader.bind()
            aa_shader.uniform_float("center", (cx, cy))
            aa_shader.uniform_float("viewportSize", (viewport_width, viewport_height))
            # Adjust radius so the anti-aliased outer edge aligns perfectly with rectangle boundary
            # The anti-aliasing extends from (radius - edgeSoftness) to (radius + edgeSoftness)
            # To align outer edge at exact radius, we reduce the shader radius by edgeSoftness
            edge_softness = 1.0
            effective_radius = radius - edge_softness  # Outer edge will be at radius
            aa_shader.uniform_float("radius", effective_radius)
            aa_shader.uniform_float("color", color_rgba)  # Use the exact same color as the rectangles
            aa_shader.uniform_float("edgeSoftness", edge_softness)  # 1-pixel soft edge for smooth anti-aliasing
            aa_shader.uniform_float("scale", scale_size)
            
            DrawConstants.circle_quad_batch.draw(aa_shader)
    else:
        # Fallback to regular circles if anti-aliased shader not available
        shader = DrawConstants.uniform_shader
        shader.bind()
        shader.uniform_float("color", color)
        for cx, cy in corners:
            with gpu.matrix.push_pop():
                gpu.matrix.translate((cx, cy))
                gpu.matrix.scale_uniform(radius)
                DrawConstants.filled_circle_batch.draw(shader)

    # Now draw the rectangular parts on top of the corners with anti-aliasing
    # Get viewport size for coordinate conversion
    viewport = gpu.state.viewport_get()
    viewport_width = viewport[2] if len(viewport) > 2 else 1920
    viewport_height = viewport[3] if len(viewport) > 3 else 1080
    
    # Ensure color is a proper tuple with 4 components (RGBA)
    if len(color) == 3:
        color_rgba = (color[0], color[1], color[2], 1.0)
    else:
        color_rgba = color
    
    # Use anti-aliased rectangle shader if available
    if DrawConstants.anti_aliased_rect_shader is not None:
        aa_rect_shader = DrawConstants.anti_aliased_rect_shader
        aa_rect_shader.bind()
        aa_rect_shader.uniform_float("viewportSize", (viewport_width, viewport_height))
        aa_rect_shader.uniform_float("color", color_rgba)
        aa_rect_shader.uniform_float("edgeSoftness", 1.0)  # 1-pixel soft edge for smooth anti-aliasing
        
        # Draw horizontal strip with anti-aliasing
        aa_rect_shader.uniform_float("rectPos", (x + radius, y))
        aa_rect_shader.uniform_float("rectSize", (width - 2 * radius, height))
        DrawConstants.circle_quad_batch.draw(aa_rect_shader)
        
        # Draw vertical strip with anti-aliasing
        aa_rect_shader.uniform_float("rectPos", (x, y + radius))
        aa_rect_shader.uniform_float("rectSize", (width, height - 2 * radius))
        DrawConstants.circle_quad_batch.draw(aa_rect_shader)
    else:
        # Fallback to regular rectangles
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
        self._bg_color = (0.157, 0.157, 0.157, 1.0)  # #282828 - Button background
        self._menu_bg_color = (0.235, 0.235, 0.235, 1.0)  # #3C3C3C - Menu wrapper and items background
        self._hover_bg_color = (0.475, 0.475, 0.475, 1.0)  # #797979
        self._active_bg_color = (0.475, 0.475, 0.475, 1.0)  # Use hover color for selected item
        self._text_color = (1.0, 1.0, 1.0, 1.0)
        self._text_size = 12
        self.on_change = None
        self._hovered_item_index = -1  # Track which item is being hovered
        self._has_ever_hovered = False  # Track if we've ever hovered over an item

        # Check icon for selected item
        self._check_icon_path = None
        self._check_icon_image = None
        self._check_icon_texture = None

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

    def _load_check_icon(self):
        """Load check icon image and create GPU texture."""
        if not self._check_icon_path:
            return

        icon_path = Path(self._check_icon_path)

        if not icon_path.exists():
            print(f"⚠️ Check icon not found at: {icon_path}")
            return

        try:
            self._check_icon_image = bpy.data.images.load(str(icon_path))
            self._check_icon_texture = gpu.texture.from_image(self._check_icon_image)
        except Exception as e:
            print(f"⚠️ Failed to load check icon: {e}")
            self._check_icon_image = None
            self._check_icon_texture = None

    def init(self, context):
        """Initialize widget and load check icon if path is set."""
        super().init(context)
        if self._check_icon_path:
            self._load_check_icon()

    def _draw_selective_rounded_rect(self, x, y, width, height, color,
                                      top_left=True, top_right=True, bottom_left=True, bottom_right=True,
                                      radius=4):
        """Draw a filled rectangle with selective rounded corners using cached batches.

        Args:
            x, y: Bottom-left position
            width, height: Rectangle dimensions
            color: RGBA color tuple
            top_left, top_right, bottom_left, bottom_right: Which corners to round
            radius: Corner radius (default 4)
        """
        # Initialize shaders if needed
        DrawConstants.initialize()

        gpu.state.blend_set('ALPHA')
        
        # Get viewport size for coordinate conversion
        viewport = gpu.state.viewport_get()
        viewport_width = viewport[2] if len(viewport) > 2 else 1920
        viewport_height = viewport[3] if len(viewport) > 3 else 1080
        
        # Ensure color is a proper tuple with 4 components (RGBA)
        if len(color) == 3:
            color_rgba = (color[0], color[1], color[2], 1.0)
        else:
            color_rgba = color
        
        # Draw corners FIRST with anti-aliasing
        corners_to_draw = []
        if bottom_left:
            corners_to_draw.append((x + radius, y + radius))
        if bottom_right:
            corners_to_draw.append((x + width - radius, y + radius))
        if top_right:
            corners_to_draw.append((x + width - radius, y + height - radius))
        if top_left:
            corners_to_draw.append((x + radius, y + height - radius))
        
        # Draw anti-aliased circles at corners
        if DrawConstants.anti_aliased_circle_shader is not None and corners_to_draw:
            aa_shader = DrawConstants.anti_aliased_circle_shader
            scale_size = (radius + 1.0) * 2.0
            
            for cx, cy in corners_to_draw:
                aa_shader.bind()
                aa_shader.uniform_float("center", (cx, cy))
                aa_shader.uniform_float("viewportSize", (viewport_width, viewport_height))
                # Adjust radius so the anti-aliased outer edge aligns perfectly
                edge_softness = 1.0
                effective_radius = radius - edge_softness  # Outer edge will be at radius
                aa_shader.uniform_float("radius", effective_radius)
                aa_shader.uniform_float("color", color_rgba)
                aa_shader.uniform_float("edgeSoftness", edge_softness)
                aa_shader.uniform_float("scale", scale_size)
                DrawConstants.circle_quad_batch.draw(aa_shader)
        else:
            # Fallback to regular circles
            shader = DrawConstants.uniform_shader
            shader.bind()
            shader.uniform_float("color", color)
            for cx, cy in corners_to_draw:
                with gpu.matrix.push_pop():
                    gpu.matrix.translate((cx, cy))
                    gpu.matrix.scale_uniform(radius)
                    DrawConstants.filled_circle_batch.draw(shader)
        
        # Draw rectangular parts with anti-aliasing
        if DrawConstants.anti_aliased_rect_shader is not None:
            aa_rect_shader = DrawConstants.anti_aliased_rect_shader
            aa_rect_shader.bind()
            aa_rect_shader.uniform_float("viewportSize", (viewport_width, viewport_height))
            aa_rect_shader.uniform_float("color", color_rgba)
            aa_rect_shader.uniform_float("edgeSoftness", 1.0)
            
            # Draw main horizontal strip
            h_left = x if not bottom_left and not top_left else x + radius
            h_right = x + width if not bottom_right and not top_right else x + width - radius
            h_width = h_right - h_left
            if h_width > 0:
                aa_rect_shader.uniform_float("rectPos", (h_left, y))
                aa_rect_shader.uniform_float("rectSize", (h_width, height))
                DrawConstants.circle_quad_batch.draw(aa_rect_shader)
            
            # Draw left vertical strip if needed
            if bottom_left or top_left:
                bl_y = (y + radius) if bottom_left else y
                tl_y = (y + height - radius) if top_left else (y + height)
                v_height = tl_y - bl_y
                if v_height > 0:
                    aa_rect_shader.uniform_float("rectPos", (x, bl_y))
                    aa_rect_shader.uniform_float("rectSize", (radius, v_height))
                    DrawConstants.circle_quad_batch.draw(aa_rect_shader)
            
            # Draw right vertical strip if needed
            if bottom_right or top_right:
                br_y = (y + radius) if bottom_right else y
                tr_y = (y + height - radius) if top_right else (y + height)
                v_height = tr_y - br_y
                if v_height > 0:
                    aa_rect_shader.uniform_float("rectPos", (x + width - radius, br_y))
                    aa_rect_shader.uniform_float("rectSize", (radius, v_height))
                    DrawConstants.circle_quad_batch.draw(aa_rect_shader)
        else:
            # Fallback to regular rectangles
            shader = DrawConstants.uniform_shader
            shader.bind()
            shader.uniform_float("color", color)
            
            # Draw main horizontal strip
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

        gpu.state.blend_set('NONE')

    def _draw_rounded_border(self, x, y, width, height, radius, color, thickness):
        """Draw a rounded rectangle border with anti-aliased edges.

        Args:
            x, y: Bottom-left position
            width, height: Rectangle dimensions
            radius: Corner radius
            color: RGBA color tuple
            thickness: Border line thickness
        """
        DrawConstants.initialize()

        gpu.state.blend_set('ALPHA')
        
        # Get viewport size for coordinate conversion
        viewport = gpu.state.viewport_get()
        viewport_width = viewport[2] if len(viewport) > 2 else 1920
        viewport_height = viewport[3] if len(viewport) > 3 else 1080
        
        # Ensure color is a proper tuple with 4 components (RGBA)
        if len(color) == 3:
            color_rgba = (color[0], color[1], color[2], 1.0)
        else:
            color_rgba = color
        
        # Draw straight edges FIRST with anti-aliased rectangles
        # This ensures edges cover the inner parts of corners, preventing corners from sticking out
        if DrawConstants.anti_aliased_rect_shader is not None:
            aa_rect_shader = DrawConstants.anti_aliased_rect_shader
            aa_rect_shader.bind()
            aa_rect_shader.uniform_float("viewportSize", (viewport_width, viewport_height))
            aa_rect_shader.uniform_float("color", color_rgba)
            # For thin borders, use very small edge softness to ensure visibility
            # The border should be mostly opaque with just a tiny fade at the very edges
            border_edge_softness = max(0.1, min(0.3, thickness * 0.3))
            aa_rect_shader.uniform_float("edgeSoftness", border_edge_softness)
            
            # Extend slightly into corner area for seamless connection
            edge_overlap = 0.5  # Extend 0.5px into corner area
            
            # Draw bottom edge (positioned so the border line is at y)
            # For a 1px border, we want it from y to y + thickness, with anti-aliasing
            if width - 2 * radius + 2 * edge_overlap > 0:
                # Position rectangle so the bottom edge aligns with y
                aa_rect_shader.uniform_float("rectPos", (x + radius - edge_overlap, y))
                aa_rect_shader.uniform_float("rectSize", (width - 2 * radius + 2 * edge_overlap, thickness))
                DrawConstants.circle_quad_batch.draw(aa_rect_shader)
            
            # Draw top edge (positioned so the border line is at y + height)
            if width - 2 * radius + 2 * edge_overlap > 0:
                # Position rectangle so the top edge aligns with y + height
                aa_rect_shader.uniform_float("rectPos", (x + radius - edge_overlap, y + height - thickness))
                aa_rect_shader.uniform_float("rectSize", (width - 2 * radius + 2 * edge_overlap, thickness))
                DrawConstants.circle_quad_batch.draw(aa_rect_shader)
            
            # Draw left edge (positioned so the border line is at x)
            # For very thin vertical borders, use simple solid rectangles to ensure visibility
            if height - 2 * radius + 2 * edge_overlap > 0:
                if thickness <= 1.0:
                    # For 1px borders, use simple solid rectangle without anti-aliasing
                    # This ensures the border is fully visible
                    simple_shader = DrawConstants.uniform_shader
                    simple_shader.bind()
                    simple_shader.uniform_float("color", color_rgba)
                    with gpu.matrix.push_pop():
                        gpu.matrix.translate((x, y + radius - edge_overlap))
                        gpu.matrix.scale((thickness, height - 2 * radius + 2 * edge_overlap))
                        DrawConstants.rect_batch_h.draw(simple_shader)
                else:
                    # For thicker borders, use anti-aliased shader
                    vertical_edge_softness = max(0.05, min(0.2, thickness * 0.2))
                    aa_rect_shader.uniform_float("edgeSoftness", vertical_edge_softness)
                    aa_rect_shader.uniform_float("rectPos", (x, y + radius - edge_overlap))
                    aa_rect_shader.uniform_float("rectSize", (thickness, height - 2 * radius + 2 * edge_overlap))
                    DrawConstants.circle_quad_batch.draw(aa_rect_shader)
                    aa_rect_shader.uniform_float("edgeSoftness", border_edge_softness)
            
            # Draw right edge (positioned so the border line is at x + width)
            if height - 2 * radius + 2 * edge_overlap > 0:
                if thickness <= 1.0:
                    # For 1px borders, use simple solid rectangle without anti-aliasing
                    simple_shader = DrawConstants.uniform_shader
                    simple_shader.bind()
                    simple_shader.uniform_float("color", color_rgba)
                    with gpu.matrix.push_pop():
                        gpu.matrix.translate((x + width - thickness, y + radius - edge_overlap))
                        gpu.matrix.scale((thickness, height - 2 * radius + 2 * edge_overlap))
                        DrawConstants.rect_batch_h.draw(simple_shader)
                else:
                    # For thicker borders, use anti-aliased shader
                    vertical_edge_softness = max(0.05, min(0.2, thickness * 0.2))
                    aa_rect_shader.uniform_float("edgeSoftness", vertical_edge_softness)
                    aa_rect_shader.uniform_float("rectPos", (x + width - thickness, y + radius - edge_overlap))
                    aa_rect_shader.uniform_float("rectSize", (thickness, height - 2 * radius + 2 * edge_overlap))
                    DrawConstants.circle_quad_batch.draw(aa_rect_shader)
                    aa_rect_shader.uniform_float("edgeSoftness", border_edge_softness)
        
        # Use anti-aliased quarter-circle arc shader for corners
        # Draw corners AFTER edges so they blend correctly on the outer edge
        if DrawConstants.anti_aliased_arc_shader is not None:
            aa_arc_shader = DrawConstants.anti_aliased_arc_shader
            scale_size = (radius + thickness * 0.5 + 1.0) * 2.0
            edge_softness = 1.0
            
            # Adjust radius to account for edge softness, similar to filled rectangles
            # This prevents corners from sticking out
            effective_radius = radius - edge_softness * 0.5
            
            # Corner definitions: (center_x, center_y, start_angle, end_angle)
            corners = [
                (x + radius, y + radius, math.pi, 1.5 * math.pi),              # Bottom-left
                (x + width - radius, y + radius, 1.5 * math.pi, 2.0 * math.pi),  # Bottom-right
                (x + width - radius, y + height - radius, 0.0, 0.5 * math.pi),   # Top-right
                (x + radius, y + height - radius, 0.5 * math.pi, math.pi),     # Top-left
            ]
            
            for cx, cy, start_angle, end_angle in corners:
                aa_arc_shader.bind()
                aa_arc_shader.uniform_float("center", (cx, cy))
                aa_arc_shader.uniform_float("viewportSize", (viewport_width, viewport_height))
                aa_arc_shader.uniform_float("radius", effective_radius)
                aa_arc_shader.uniform_float("thickness", thickness)
                aa_arc_shader.uniform_float("color", color_rgba)
                aa_arc_shader.uniform_float("edgeSoftness", edge_softness)
                aa_arc_shader.uniform_float("startAngle", start_angle)
                aa_arc_shader.uniform_float("endAngle", end_angle)
                aa_arc_shader.uniform_float("scale", scale_size)
                DrawConstants.circle_quad_batch.draw(aa_arc_shader)
        else:
            # Fallback to regular border
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

    def _draw_check_icon(self, x, y, item_height, item_width=None):
        """Draw the check icon on the right side of a dropdown item.
        
        Args:
            x: Left position of the item
            y: Bottom position of the item
            item_height: Height of the item
            item_width: Width of the item (defaults to self.width if not provided)
        """
        if not self._check_icon_texture:
            return

        # Icon size is 16px
        icon_size = 16
        # Use provided width or fall back to self.width
        width = item_width if item_width is not None else self.width
        # Position on the right side with padding
        icon_x = x + width - icon_size - 8  # 8px right padding
        icon_y = y + (item_height - icon_size) / 2  # Center vertically

        # Use IMAGE shader to draw the texture
        gpu.state.blend_set('ALPHA')

        try:
            shader = gpu.shader.from_builtin('IMAGE')
        except:
            gpu.state.blend_set('NONE')
            return

        # Create batch for image quad
        vertices = [
            (icon_x, icon_y),
            (icon_x + icon_size, icon_y),
            (icon_x + icon_size, icon_y + icon_size),
            (icon_x, icon_y + icon_size)
        ]

        texcoords = [(0, 0), (1, 0), (1, 1), (0, 1)]
        indices = [(0, 1, 2), (0, 2, 3)]

        batch = batch_for_shader(
            shader, 'TRIS',
            {"pos": vertices, "texCoord": texcoords},
            indices=indices
        )

        shader.bind()
        shader.uniform_sampler("image", self._check_icon_texture)
        batch.draw(shader)

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
            gap = 2  # 2px gap between button and dropdown menu
            wrapper_padding = 2  # 2px padding inside wrapper
            wrapper_border = 1  # 1px border
            wrapper_radius = 4  # Same border radius as dropdown button
            
            # Position dropdown menu with 2px gap from button
            dropdown_y = self.y_screen + self.height + gap
            total_height = len(self._items) * item_height
            
            # Calculate wrapper dimensions
            wrapper_width = self.width
            wrapper_height = total_height + (wrapper_padding * 2) + (wrapper_border * 2)
            wrapper_x = self.x_screen
            wrapper_y = dropdown_y
            
            # Inner content area (inside padding and border)
            inner_x = wrapper_x + wrapper_border + wrapper_padding
            inner_y = wrapper_y + wrapper_border + wrapper_padding
            inner_width = wrapper_width - (wrapper_border * 2) - (wrapper_padding * 2)
            inner_height = total_height
            
            # Draw wrapper background with rounded corners (use menu background color)
            draw_rounded_rect(
                wrapper_x, wrapper_y, wrapper_width, wrapper_height,
                wrapper_radius, self._menu_bg_color, segments=16
            )
            
            # Draw wrapper border
            self._draw_rounded_border(
                wrapper_x, wrapper_y, wrapper_width, wrapper_height,
                wrapper_radius, (0.329, 0.329, 0.329, 1.0), wrapper_border
            )

            # Draw all items with menu background color and rounded corners
            item_radius = 2  # Half the size of dropdown button radius (4px)
            for i in range(len(self._items)):
                item_y = inner_y + (i * item_height)
                # Draw each item with menu background color and rounded corners
                draw_rounded_rect(
                    inner_x, item_y, inner_width, item_height,
                    item_radius, self._menu_bg_color, segments=16
                )

            # Draw active (selected) item with hover color background
            # Only show background when no item is being hovered AND we haven't ever hovered
            if 0 <= self._selected_index < len(self._items) and self._hovered_item_index == -1 and not self._has_ever_hovered:
                active_item_y = inner_y + (self._selected_index * item_height)
                item_radius = 2  # Half the size of dropdown button radius (4px)
                # Draw active item background with all corners rounded (2px radius)
                draw_rounded_rect(
                    inner_x, active_item_y, inner_width, item_height,
                    item_radius, self._active_bg_color, segments=16
                )

            # Now draw hovered item on top with different color (takes priority over active)
            if 0 <= self._hovered_item_index < len(self._items):
                hovered_item_y = inner_y + (self._hovered_item_index * item_height)
                item_radius = 2  # Half the size of dropdown button radius (4px)
                # Draw hovered item background with all corners rounded (2px radius)
                draw_rounded_rect(
                    inner_x, hovered_item_y, inner_width, item_height,
                    item_radius, self._hover_bg_color, segments=16
                )

            # Draw item text for all items
            for i, item in enumerate(self._items):
                item_y = inner_y + (i * item_height)

                # Draw item text
                blf.size(0, self._text_size)
                text_x = inner_x + 8
                text_y = item_y + (item_height / 2) - 6

                blf.position(0, text_x, text_y, 0)
                blf.color(0, 1.0, 1.0, 1.0, 1.0)
                blf.draw(0, item)

            # Draw check icon for selected item (always visible, regardless of hover)
            if 0 <= self._selected_index < len(self._items):
                selected_item_y = inner_y + (self._selected_index * item_height)
                self._draw_check_icon(inner_x, selected_item_y, item_height, inner_width)

    def mouse_move(self, x, y):
        """Handle mouse move event to track hover state."""
        if not self._is_open:
            self._hovered_item_index = -1
            return

        # Check which dropdown item is being hovered
        item_height = 24
        gap = 2  # 2px gap between button and dropdown menu
        wrapper_padding = 2  # 2px padding inside wrapper
        wrapper_border = 1  # 1px border
        
        # Position dropdown menu with 2px gap from button
        dropdown_y = self.y_screen + self.height + gap
        inner_y = dropdown_y + wrapper_border + wrapper_padding
        inner_x = self.x_screen + wrapper_border + wrapper_padding
        inner_width = self.width - (wrapper_border * 2) - (wrapper_padding * 2)

        self._hovered_item_index = -1  # Reset
        for i, item in enumerate(self._items):
            item_y = inner_y + (i * item_height)
            if (inner_x <= x <= (inner_x + inner_width) and
                    item_y <= y <= (item_y + item_height)):
                self._hovered_item_index = i
                self._has_ever_hovered = True  # Mark that we've hovered
                break

    def mouse_down(self, x, y):
        """Handle mouse down event."""
        if self.is_in_rect(x, y):
            was_open = self._is_open
            self._is_open = not self._is_open
            if not self._is_open:
                self._hovered_item_index = -1  # Reset hover when closing
                self._has_ever_hovered = False  # Reset hover flag when closing
            elif not was_open:
                # Just opened - reset hover flag
                self._has_ever_hovered = False
            return True
        elif self._is_open:
            # Check if clicked on an item in the dropdown
            item_height = 24
            gap = 2  # 2px gap between button and dropdown menu
            wrapper_padding = 2  # 2px padding inside wrapper
            wrapper_border = 1  # 1px border
            
            # Position dropdown menu with 2px gap from button
            dropdown_y = self.y_screen + self.height + gap
            inner_y = dropdown_y + wrapper_border + wrapper_padding
            inner_x = self.x_screen + wrapper_border + wrapper_padding
            inner_width = self.width - (wrapper_border * 2) - (wrapper_padding * 2)

            for i, item in enumerate(self._items):
                item_y = inner_y + (i * item_height)
                if (inner_x <= x <= (inner_x + inner_width) and
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
        """Draw checkbox border with anti-aliasing."""
        DrawConstants.initialize()
        
        gpu.state.blend_set('ALPHA')
        
        # Get viewport size for coordinate conversion
        viewport = gpu.state.viewport_get()
        viewport_width = viewport[2] if len(viewport) > 2 else 1920
        viewport_height = viewport[3] if len(viewport) > 3 else 1080
        
        # Ensure color is a proper tuple with 4 components (RGBA)
        if len(color) == 3:
            color_rgba = (color[0], color[1], color[2], 1.0)
        else:
            color_rgba = color
        
        radius = 2
        
        # Draw straight edges FIRST with anti-aliased rectangles
        if DrawConstants.anti_aliased_rect_shader is not None:
            aa_rect_shader = DrawConstants.anti_aliased_rect_shader
            aa_rect_shader.bind()
            aa_rect_shader.uniform_float("viewportSize", (viewport_width, viewport_height))
            aa_rect_shader.uniform_float("color", color_rgba)
            # Use very small edge softness for thin borders
            border_edge_softness = max(0.1, min(0.3, thickness * 0.3))
            aa_rect_shader.uniform_float("edgeSoftness", border_edge_softness)
            
            edge_overlap = 0.5
            
            # Draw bottom edge
            if size - 2 * radius + 2 * edge_overlap > 0:
                aa_rect_shader.uniform_float("rectPos", (x + radius - edge_overlap, y))
                aa_rect_shader.uniform_float("rectSize", (size - 2 * radius + 2 * edge_overlap, thickness))
                DrawConstants.circle_quad_batch.draw(aa_rect_shader)
            
            # Draw top edge
            if size - 2 * radius + 2 * edge_overlap > 0:
                aa_rect_shader.uniform_float("rectPos", (x + radius - edge_overlap, y + size - thickness))
                aa_rect_shader.uniform_float("rectSize", (size - 2 * radius + 2 * edge_overlap, thickness))
                DrawConstants.circle_quad_batch.draw(aa_rect_shader)
            
            # Draw left edge
            if size - 2 * radius + 2 * edge_overlap > 0:
                if thickness <= 1.0:
                    # For 1px borders, use simple solid rectangle
                    simple_shader = DrawConstants.uniform_shader
                    simple_shader.bind()
                    simple_shader.uniform_float("color", color_rgba)
                    with gpu.matrix.push_pop():
                        gpu.matrix.translate((x, y + radius - edge_overlap))
                        gpu.matrix.scale((thickness, size - 2 * radius + 2 * edge_overlap))
                        DrawConstants.rect_batch_h.draw(simple_shader)
                else:
                    vertical_edge_softness = max(0.05, min(0.2, thickness * 0.2))
                    aa_rect_shader.uniform_float("edgeSoftness", vertical_edge_softness)
                    aa_rect_shader.uniform_float("rectPos", (x, y + radius - edge_overlap))
                    aa_rect_shader.uniform_float("rectSize", (thickness, size - 2 * radius + 2 * edge_overlap))
                    DrawConstants.circle_quad_batch.draw(aa_rect_shader)
                    aa_rect_shader.uniform_float("edgeSoftness", border_edge_softness)
            
            # Draw right edge
            if size - 2 * radius + 2 * edge_overlap > 0:
                if thickness <= 1.0:
                    # For 1px borders, use simple solid rectangle
                    simple_shader = DrawConstants.uniform_shader
                    simple_shader.bind()
                    simple_shader.uniform_float("color", color_rgba)
                    with gpu.matrix.push_pop():
                        gpu.matrix.translate((x + size - thickness, y + radius - edge_overlap))
                        gpu.matrix.scale((thickness, size - 2 * radius + 2 * edge_overlap))
                        DrawConstants.rect_batch_h.draw(simple_shader)
                else:
                    vertical_edge_softness = max(0.05, min(0.2, thickness * 0.2))
                    aa_rect_shader.uniform_float("edgeSoftness", vertical_edge_softness)
                    aa_rect_shader.uniform_float("rectPos", (x + size - thickness, y + radius - edge_overlap))
                    aa_rect_shader.uniform_float("rectSize", (thickness, size - 2 * radius + 2 * edge_overlap))
                    DrawConstants.circle_quad_batch.draw(aa_rect_shader)
                    aa_rect_shader.uniform_float("edgeSoftness", border_edge_softness)
        
        # Use anti-aliased quarter-circle arc shader for corners
        if DrawConstants.anti_aliased_arc_shader is not None:
            aa_arc_shader = DrawConstants.anti_aliased_arc_shader
            scale_size = (radius + thickness * 0.5 + 1.0) * 2.0
            edge_softness = 1.0
            effective_radius = radius - edge_softness * 0.5
            
            # Corner definitions: (center_x, center_y, start_angle, end_angle)
            corners = [
                (x + radius, y + radius, math.pi, 1.5 * math.pi),              # Bottom-left
                (x + size - radius, y + radius, 1.5 * math.pi, 2.0 * math.pi),  # Bottom-right
                (x + size - radius, y + size - radius, 0.0, 0.5 * math.pi),   # Top-right
                (x + radius, y + size - radius, 0.5 * math.pi, math.pi),     # Top-left
            ]
            
            for cx, cy, start_angle, end_angle in corners:
                aa_arc_shader.bind()
                aa_arc_shader.uniform_float("center", (cx, cy))
                aa_arc_shader.uniform_float("viewportSize", (viewport_width, viewport_height))
                aa_arc_shader.uniform_float("radius", effective_radius)
                aa_arc_shader.uniform_float("thickness", thickness)
                aa_arc_shader.uniform_float("color", color_rgba)
                aa_arc_shader.uniform_float("edgeSoftness", edge_softness)
                aa_arc_shader.uniform_float("startAngle", start_angle)
                aa_arc_shader.uniform_float("endAngle", end_angle)
                aa_arc_shader.uniform_float("scale", scale_size)
                DrawConstants.circle_quad_batch.draw(aa_arc_shader)
        else:
            # Fallback to regular border
            gpu.state.line_width_set(thickness)
            shader = DrawConstants.uniform_shader
            shader.bind()
            shader.uniform_float("color", color)
            
            vertices = []
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
        self._bg_color = (0.114, 0.114, 0.114, 1.0)  # #1d1d1d (same as toolbar background)
        self._toggled_bg_color = (0.0745, 0.541, 0.910, 1.0)  # #138ae8 when toggled
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


class BL_UI_DropdownButton(BL_UI_Widget):
    """Narrow dropdown button widget (16px wide, 32px tall)."""

    def __init__(self, x, y, width, height):
        super().__init__(x, y, width, height)
        self._icon_path = None
        self._icon_image = None
        self._icon_texture = None
        self._bg_color = (0.114, 0.114, 0.114, 1.0)  # #1d1d1d (same as toolbar background)
        self._hover_bg_color = (0.475, 0.475, 0.475, 1.0)  # #797979
        self._is_hovered = False
        self.on_click = None

    @property
    def icon_path(self):
        return self._icon_path

    @icon_path.setter
    def icon_path(self, value):
        self._icon_path = value
        if value:
            self._load_icon_image()

    def _load_icon_image(self):
        """Load icon image and create GPU texture."""
        if not self._icon_path:
            return

        icon_path = Path(self._icon_path)

        if not icon_path.exists():
            print(f"⚠️ Dropdown icon not found at: {icon_path}")
            return

        try:
            self._icon_image = bpy.data.images.load(str(icon_path))
            self._icon_texture = gpu.texture.from_image(self._icon_image)
        except Exception as e:
            print(f"⚠️ Failed to load dropdown icon: {e}")
            self._icon_image = None
            self._icon_texture = None

    def init(self, context):
        """Initialize widget and load icon if path is set."""
        super().init(context)
        if self._icon_path:
            self._load_icon_image()

    def draw(self):
        """Draw the dropdown button."""
        if not self.visible:
            return

        # Determine background color
        bg_color = self._hover_bg_color if self._is_hovered else self._bg_color

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

        # Draw icon if available
        if self._icon_texture:
            self._draw_icon_image()

    def _draw_icon_image(self):
        """Draw the icon image centered in the button."""
        if not self._icon_texture:
            return

        # Calculate icon size (leave some padding)
        padding = 4
        icon_width = self.width - (padding * 2)
        icon_height = min(self.height - (padding * 2), icon_width)  # Keep aspect ratio
        icon_x = self.x_screen + (self.width - icon_width) / 2
        icon_y = self.y_screen + (self.height - icon_height) / 2

        # Use IMAGE shader to draw the texture
        gpu.state.blend_set('ALPHA')

        try:
            shader = gpu.shader.from_builtin('IMAGE')
        except:
            gpu.state.blend_set('NONE')
            return

        # Create batch for image quad
        vertices = [
            (icon_x, icon_y),
            (icon_x + icon_width, icon_y),
            (icon_x + icon_width, icon_y + icon_height),
            (icon_x, icon_y + icon_height)
        ]

        texcoords = [(0, 0), (1, 0), (1, 1), (0, 1)]
        indices = [(0, 1, 2), (0, 2, 3)]

        batch = batch_for_shader(
            shader, 'TRIS',
            {"pos": vertices, "texCoord": texcoords},
            indices=indices
        )

        shader.bind()
        shader.uniform_sampler("image", self._icon_texture)
        batch.draw(shader)

        gpu.state.blend_set('NONE')

    def mouse_down(self, x, y):
        """Handle mouse down event."""
        if self.is_in_rect(x, y):
            return True
        return False

    def mouse_up(self, x, y):
        """Handle mouse up event."""
        if self.is_in_rect(x, y):
            if self.on_click:
                self.on_click()
            return True
        return False

    def mouse_move(self, x, y):
        """Handle mouse move event for hover state."""
        self._is_hovered = self.is_in_rect(x, y)


class BL_UI_HDRIThumbnailButton(BL_UI_Widget):
    """HDRI thumbnail button widget (128x128px)."""

    def __init__(self, x, y, size, thumbnail_path, hdr_path, hdri_name):
        super().__init__(x, y, size, size)
        self.thumbnail_path = thumbnail_path
        self.hdr_path = hdr_path
        self.hdri_name = hdri_name
        self._thumbnail_image = None
        self._thumbnail_texture = None
        self._is_hovered = False
        self._is_selected = False
        self._bg_color = (0.114, 0.114, 0.114, 1.0)  # #1d1d1d
        self._hover_color = (0.2, 0.2, 0.2, 1.0)
        self._selected_color = (0.0745, 0.541, 0.910, 1.0)  # #138ae8
        self.on_select = None

    def _load_thumbnail(self):
        """Load thumbnail image and create GPU texture."""
        if not self.thumbnail_path:
            return

        thumb_path = Path(self.thumbnail_path)

        if not thumb_path.exists():
            print(f"⚠️ HDRI thumbnail not found at: {thumb_path}")
            return

        try:
            self._thumbnail_image = bpy.data.images.load(str(thumb_path))
            self._thumbnail_texture = gpu.texture.from_image(self._thumbnail_image)
        except Exception as e:
            print(f"⚠️ Failed to load HDRI thumbnail: {e}")
            self._thumbnail_image = None
            self._thumbnail_texture = None

    def init(self, context):
        """Initialize widget and load thumbnail."""
        super().init(context)
        self._load_thumbnail()

    @property
    def is_selected(self):
        return self._is_selected

    @is_selected.setter
    def is_selected(self, value):
        self._is_selected = value

    def draw(self):
        """Draw the HDRI thumbnail button."""
        if not self.visible:
            return

        # Determine border color
        if self._is_selected:
            border_color = self._selected_color
            border_width = 2
        elif self._is_hovered:
            border_color = self._hover_color
            border_width = 2
        else:
            border_color = None
            border_width = 0

        # Draw background
        draw_rounded_rect(
            self.x_screen,
            self.y_screen,
            self.width,
            self.height,
            18,  # 18px corner radius
            self._bg_color,
            segments=16
        )

        # Draw thumbnail image
        if self._thumbnail_texture:
            self._draw_thumbnail_image()

        # Draw border if needed
        if border_color and border_width > 0:
            self._draw_border(border_color, border_width)

    def _draw_thumbnail_image(self):
        """Draw the thumbnail image."""
        if not self._thumbnail_texture:
            return

        # Image fills entire button with small padding
        padding = 4
        img_width = self.width - (padding * 2)
        img_height = self.height - (padding * 2)
        img_x = self.x_screen + padding
        img_y = self.y_screen + padding

        gpu.state.blend_set('ALPHA')

        try:
            shader = gpu.shader.from_builtin('IMAGE')
        except:
            gpu.state.blend_set('NONE')
            return

        # Create batch for image quad
        vertices = [
            (img_x, img_y),
            (img_x + img_width, img_y),
            (img_x + img_width, img_y + img_height),
            (img_x, img_y + img_height)
        ]

        texcoords = [(0, 0), (1, 0), (1, 1), (0, 1)]
        indices = [(0, 1, 2), (0, 2, 3)]

        batch = batch_for_shader(
            shader, 'TRIS',
            {"pos": vertices, "texCoord": texcoords},
            indices=indices
        )

        shader.bind()
        shader.uniform_sampler("image", self._thumbnail_texture)
        batch.draw(shader)

        gpu.state.blend_set('NONE')

    def _draw_border(self, color, width):
        """Draw border around the thumbnail."""
        DrawConstants.initialize()
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(width)

        shader = DrawConstants.uniform_shader

        # Create rounded rectangle outline
        radius = 18
        x, y = self.x_screen, self.y_screen
        w, h = self.width, self.height

        vertices = []
        segments = 16

        # Bottom edge
        vertices.append((x + radius, y))
        vertices.append((x + w - radius, y))
        # Bottom-right corner
        cx, cy = x + w - radius, y + radius
        for i in range(segments + 1):
            angle = 1.5 * math.pi + (0.5 * math.pi * i / segments)
            vertices.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        # Right edge
        vertices.append((x + w, y + h - radius))
        # Top-right corner
        cx, cy = x + w - radius, y + h - radius
        for i in range(segments + 1):
            angle = 0 + (0.5 * math.pi * i / segments)
            vertices.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        # Top edge
        vertices.append((x + w - radius, y + h))
        vertices.append((x + radius, y + h))
        # Top-left corner
        cx, cy = x + radius, y + h - radius
        for i in range(segments + 1):
            angle = 0.5 * math.pi + (0.5 * math.pi * i / segments)
            vertices.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        # Left edge
        vertices.append((x, y + h - radius))
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
        """Handle mouse up event."""
        if self.is_in_rect(x, y):
            if self.on_select:
                self.on_select(self.hdr_path, self.hdri_name)
            return True
        return False

    def mouse_move(self, x, y):
        """Handle mouse move event for hover state."""
        self._is_hovered = self.is_in_rect(x, y)


class BL_UI_HDRIPanel(BL_UI_Widget):
    """HDRI selection panel with thumbnail grid."""

    def __init__(self, x, y, available_hdris):
        self.available_hdris = available_hdris
        self.thumbnail_buttons = []

        # Calculate panel dimensions
        thumbnail_size = 128
        thumbnail_spacing = 8
        panel_padding = 12
        label_height = 20  # Space for HDRI name label under each thumbnail

        # Calculate grid layout (8 thumbnails in a single row)
        thumbnails_per_row = 8
        num_rows = 1

        panel_width = (thumbnail_size * thumbnails_per_row +
                      thumbnail_spacing * (thumbnails_per_row - 1) +
                      panel_padding * 2)
        # Panel height: thumbnails + labels + spacing between rows + padding top and bottom
        # For single row: thumbnail_size + label_height + panel_padding * 2
        panel_height = (thumbnail_size * num_rows +
                       label_height * num_rows +
                       thumbnail_spacing * (num_rows - 1) +
                       panel_padding * 2)

        super().__init__(x, y, panel_width, panel_height)

        self._bg_color = (0.114, 0.114, 0.114, 1.0)  # #1d1d1d
        self.on_hdri_selected = None
        self.selected_hdri_path = None

        # Create thumbnail buttons
        for idx, (thumb_path, hdr_path, hdri_name) in enumerate(available_hdris):
            row = idx // thumbnails_per_row
            col = idx % thumbnails_per_row

            btn_x = x + panel_padding + col * (thumbnail_size + thumbnail_spacing)
            # Position buttons from top of panel
            # In Blender, y=0 is at bottom, so panel top is at y + panel_height
            # Button bottom should be at: panel_top - panel_padding - thumbnail_size
            # For row 0: y + panel_height - panel_padding - thumbnail_size
            btn_y = y + panel_height - panel_padding - thumbnail_size - row * (thumbnail_size + label_height + thumbnail_spacing)

            btn = BL_UI_HDRIThumbnailButton(btn_x, btn_y, thumbnail_size,
                                           thumb_path, hdr_path, hdri_name)
            btn.on_select = self._handle_thumbnail_select
            self.thumbnail_buttons.append(btn)

    def init(self, context):
        """Initialize panel and all thumbnail buttons."""
        super().init(context)
        for btn in self.thumbnail_buttons:
            btn.init(context)

    def _handle_thumbnail_select(self, hdr_path, hdri_name):
        """Handle thumbnail selection."""
        self.selected_hdri_path = hdr_path

        # Update selected state for all buttons
        for btn in self.thumbnail_buttons:
            btn.is_selected = (btn.hdr_path == hdr_path)

        # Call parent callback
        if self.on_hdri_selected:
            self.on_hdri_selected(hdr_path, hdri_name)

    def draw(self):
        """Draw the HDRI panel."""
        if not self.visible:
            return

        # Draw background panel
        draw_rounded_rect(
            self.x_screen,
            self.y_screen,
            self.width,
            self.height,
            16,  # 16px corner radius
            self._bg_color,
            segments=16
        )

        # Draw all thumbnail buttons
        for btn in self.thumbnail_buttons:
            btn.draw()
        
        # Draw HDRI name labels under each thumbnail
        thumbnail_size = 128
        label_height = 20
        label_gap = 4  # Small gap between thumbnail and label
        panel_padding = 12
        
        for btn in self.thumbnail_buttons:
            # Calculate label position (centered under thumbnail)
            label_x = btn.x_screen
            # Position label below the thumbnail button
            # btn.y_screen is the bottom of the button (Y=0 at bottom in Blender)
            # So label should be at: button bottom - gap - label_height
            label_y = btn.y_screen - label_gap - label_height
            
            # Get HDRI name and truncate if needed
            hdri_name = btn.hdri_name
            max_width = thumbnail_size
            
            # Measure text width
            blf.size(0, 12)  # Font size for labels
            text_width, text_height = blf.dimensions(0, hdri_name)
            
            # Truncate text if too long
            if text_width > max_width - 8:  # Leave 4px padding on each side
                # Calculate how many characters fit
                ellipsis = "..."
                ellipsis_width, _ = blf.dimensions(0, ellipsis)
                available_width = max_width - 8 - ellipsis_width
                
                # Binary search for fitting text
                low, high = 0, len(hdri_name)
                while low < high:
                    mid = (low + high + 1) // 2
                    test_text = hdri_name[:mid]
                    test_width, _ = blf.dimensions(0, test_text)
                    if test_width <= available_width:
                        low = mid
                    else:
                        high = mid - 1
                
                hdri_name = hdri_name[:low] + ellipsis
            
            # Draw label text (centered)
            text_width, text_height = blf.dimensions(0, hdri_name)
            text_x = label_x + (thumbnail_size - text_width) / 2
            # Position text vertically centered in label area
            text_y = label_y + (label_height - text_height) / 2
            
            blf.position(0, text_x, text_y, 0)
            blf.color(0, 0.8, 0.8, 0.8, 1.0)  # Light gray text
            blf.draw(0, hdri_name)

    def mouse_down(self, x, y):
        """Handle mouse down events."""
        # Check if click is within panel bounds
        if not self.is_in_rect(x, y):
            return False

        # Check thumbnail buttons
        for btn in self.thumbnail_buttons:
            if btn.mouse_down(x, y):
                return True

        # Click was on panel background (consume event)
        return True

    def mouse_up(self, x, y):
        """Handle mouse up events."""
        if not self.is_in_rect(x, y):
            return False

        for btn in self.thumbnail_buttons:
            if btn.mouse_up(x, y):
                return True

        return True

    def mouse_move(self, x, y):
        """Handle mouse move events."""
        if not self.visible:
            return

        for btn in self.thumbnail_buttons:
            btn.mouse_move(x, y)

    def update_position(self, x, y):
        """Update panel position and reposition all thumbnails."""
        # Update panel position (including screen coordinates)
        self.x = x
        self.y = y
        self.x_screen = x
        self.y_screen = y

        # Recalculate thumbnail positions
        thumbnail_size = 128
        thumbnail_spacing = 8
        panel_padding = 12
        label_height = 20  # Space for HDRI name label under each thumbnail
        thumbnails_per_row = 8  # Single row with 8 thumbnails

        for idx, btn in enumerate(self.thumbnail_buttons):
            row = idx // thumbnails_per_row
            col = idx % thumbnails_per_row

            btn_x = x + panel_padding + col * (thumbnail_size + thumbnail_spacing)
            # Position buttons from top of panel
            # In Blender, y=0 is at bottom, so panel top is at y + self.height
            # Button bottom should be at: panel_top - panel_padding - thumbnail_size
            # For row 0: y + self.height - panel_padding - thumbnail_size
            btn_y = y + self.height - panel_padding - thumbnail_size - row * (thumbnail_size + label_height + thumbnail_spacing)

            btn.x = btn_x
            btn.y = btn_y
            btn.x_screen = btn_x
            btn.y_screen = btn_y


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
        self._track_color = (0.333, 0.333, 0.333, 1.0)  # #555555 (inside min/max range)
        self._track_color_outside = (0.2, 0.2, 0.2, 1.0)  # Darker gray for outside range (slightly brighter)
        self._track_border_color = (0.329, 0.329, 0.329, 1.0)
        self._handle_radius = 8
        self._handle_color = (0.0745, 0.541, 0.910, 1.0)  # #138ae8
        self._handle_hover_color = (0.094, 0.620, 1.0, 1.0)  # Slightly lighter
        self._handle_pressed_color = (0.055, 0.463, 0.820, 1.0)  # Slightly darker
        self._marker_active_color = (0.333, 0.333, 0.333, 1.0)  # #555555 for markers inside range
        self._marker_inactive_color = (0.071, 0.071, 0.071, 1.0)  # #121212 for unavailable LODs
        self._marker_outside_range_color = (0.2, 0.2, 0.2, 1.0)  # Darker gray for markers outside range (slightly brighter)
        self._minmax_marker_color = (0.804, 0.804, 0.804, 1.0)  # #CDCDCD for min/max LOD markers

        # State
        self._is_hovered = False
        self._is_loading = False  # Track loading state for visual feedback
        self.on_value_changed = None

        # Min/Max LOD markers (set from toolbar)
        self._min_lod = None
        self._max_lod = None
        self._object_max_lod = None  # Object's maximum available LOD level
        self._auto_lod_enabled = False  # Auto LOD enabled state
        
        # Number label properties
        self._number_label_size = 8  # Font size for number labels (smaller)
        self._number_label_gap = 3  # Vertical spacing between numbers and markers
        self._gray_number_color = (0.5, 0.5, 0.5, 1.0)  # Gray for most numbers
        self._white_number_color = (1.0, 1.0, 1.0, 1.0)  # White for 0 and MAX LOD
        self._orange_warning_color = (1.0, 0.5, 0.0, 1.0)  # Orange for warning state

    def set_available_lods(self, lod_levels):
        """Set which LOD levels are available (enabled markers)."""
        self._available_lods = lod_levels

    def set_min_max_lods(self, min_lod, max_lod):
        """Set the min and max LOD values for displaying markers above the track."""
        # Only update if values actually changed to avoid unnecessary recalculations
        if self._min_lod != min_lod or self._max_lod != max_lod:
            self._min_lod = min_lod
            self._max_lod = max_lod
            # Clear marker positions to force recalculation on next draw
            self._marker_positions = []

    def set_object_max_lod(self, max_lod):
        """Set the object's maximum available LOD level."""
        self._object_max_lod = max_lod
        # Don't change _max_value - keep it at 7 to show all markers
        # Clear marker positions to force recalculation
        self._marker_positions = []

    def set_loading_state(self, is_loading):
        """Set the loading state of the slider (affects handle color)."""
        self._is_loading = is_loading

    def set_auto_lod_enabled(self, enabled):
        """Set the Auto LOD enabled state (affects orange indicators)."""
        self._auto_lod_enabled = enabled

    def set_value(self, value):
        """Set the slider value (LOD level 0-7), clamped to min/max range."""
        # First clamp to overall slider range (0-7)
        value = max(self._min_value, min(self._max_value, value))

        # Then clamp to min/max LOD range if set
        # The knob should slide in the range from 0 to maxLOD (including auto-generated LODs)
        # Position 0 corresponds to Quixel LOD minLOD (shown at bottom)
        # Position maxLOD corresponds to the max LOD (shown at top)
        if self._min_lod is not None and self._max_lod is not None:
            # Allow sliding from position 0 to position maxLOD (to include auto-generated LODs)
            value = max(0, min(value, self._max_lod))
        elif self._min_lod is not None:
            value = max(0, value)  # Start from position 0
        elif self._max_lod is not None:
            value = min(value, self._max_lod)

        self._current_value = value

    def get_value(self):
        """Get the current slider value."""
        return self._current_value

    def _calculate_marker_positions(self):
        """Calculate X positions for each LOD marker."""
        # Always show markers from 0 to 7 (full range)
        num_markers = self._max_value - self._min_value + 1
        
        # Recalculate if positions don't exist or if the number of markers has changed
        if not self._marker_positions or len(self._marker_positions) != num_markers:
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
        # The knob should slide in the range from 0 to maxLOD (including auto-generated LODs)
        # Position 0 corresponds to Quixel LOD minLOD (shown at bottom)
        # Position maxLOD corresponds to the max LOD (shown at top)
        if self._min_lod is not None and self._max_lod is not None:
            # Allow sliding from position 0 to position maxLOD (to include auto-generated LODs)
            closest_value = max(0, min(closest_value, self._max_lod))
        elif self._min_lod is not None:
            closest_value = max(0, closest_value)  # Start from position 0
        elif self._max_lod is not None:
            closest_value = min(closest_value, self._max_lod)

        return closest_value

    def draw(self):
        """Draw the slider with track, markers, and handle."""
        if not self._visible:
            return

        # Recalculate marker positions if needed
        self._calculate_marker_positions()

        # Determine if we're in warning state (min_lod > 0)
        is_warning_state = (self._min_lod is not None and self._min_lod > 0)
        
        # Determine which LODs need auto-generation or are missing
        # Preview LOD i maps to Quixel LOD (minLOD + i)
        # We need to check all preview LODs from 0 to maxLOD (the slider positions)
        # If the Quixel LOD they map to is not in available_lods, it needs auto-generation or is missing
        auto_generated_lods = set()
        missing_lods = set()  # LODs that are missing (not in available_lods)
        if self._min_lod is not None and self._max_lod is not None and self._available_lods is not None:
            # Check each preview LOD position from 0 to maxLOD
            # Preview LOD i maps to Quixel LOD (minLOD + i)
            for preview_lod in range(0, self._max_lod + 1):
                quixel_lod = self._min_lod + preview_lod
                # Check if this Quixel LOD is in available_lods
                is_missing = False
                if isinstance(self._available_lods, (list, set, tuple)):
                    if quixel_lod not in self._available_lods:
                        is_missing = True
                elif not self._available_lods:
                    # If available_lods is empty or falsy, all LODs are missing
                    is_missing = True
                
                if is_missing:
                    missing_lods.add(quixel_lod)
                    # Only add to auto_generated_lods if autoLOD is enabled
                    if self._auto_lod_enabled:
                        auto_generated_lods.add(quixel_lod)

        # Draw track (split into segments based on min/max range)
        track_y = self.y_screen + (self.height - self._track_height) / 2
        track_start_x = self.x_screen + self._handle_radius
        track_full_width = self.width - (self._handle_radius * 2)

        # Draw track - always full width from start to end
        track_end_x = track_start_x + track_full_width
        
        if self._min_lod is not None and self._max_lod is not None and len(self._marker_positions) > 0:
            # Calculate positions
            # Min marker at position 0 (where bottom shows minLOD, top shows 0)
            # Max marker at position maxLOD (where top shows maxLOD, aligned with top row)
            min_marker_index = 0
            max_marker_index = self._max_lod  # For the max marker (aligned with top row)
            min_lod_x = self._marker_positions[min_marker_index] if min_marker_index < len(self._marker_positions) else track_start_x
            max_lod_x = self._marker_positions[max_marker_index] if max_marker_index < len(self._marker_positions) else track_end_x

            # Segment 1: Start to min_lod (darker gray)
            if min_lod_x > track_start_x:
                segment1_width = min_lod_x - track_start_x
                draw_rounded_rect(
                    track_start_x,
                    track_y,
                    segment1_width,
                    self._track_height,
                    2,
                    self._track_color_outside,
                    segments=8
                )

            # Find the first orange segment position (if any)
            first_orange_preview_lod = None
            for preview_lod in range(0, self._max_lod + 1):
                quixel_lod = self._min_lod + preview_lod
                if quixel_lod in auto_generated_lods:
                    first_orange_preview_lod = preview_lod
                    break

            # Segment 2: min_lod to max_lod - draw per preview LOD level
            # Draw each preview LOD segment separately, using orange for auto-generated ones
            # Preview LOD i maps to Quixel LOD (minLOD + i)
            # Position i shows Preview LOD i (top) and Quixel LOD (minLOD + i) (bottom)
            for preview_lod in range(0, self._max_lod + 1):
                quixel_lod = self._min_lod + preview_lod
                # Calculate start position: where this preview LOD is shown
                segment_start_index = preview_lod
                
                # Ensure we have valid indices
                if segment_start_index >= len(self._marker_positions):
                    continue
                
                segment_start_x = self._marker_positions[segment_start_index]
                
                # Calculate end position: next preview LOD or max marker position
                if preview_lod < self._max_lod:
                    segment_end_index = preview_lod + 1
                    if segment_end_index < len(self._marker_positions):
                        segment_end_x = self._marker_positions[segment_end_index]
                    else:
                        # Use max marker position if next index is out of range
                        segment_end_x = max_lod_x
                    segment_width = segment_end_x - segment_start_x
                else:
                    # Last preview LOD segment - extend to max marker position (at position maxLOD)
                    segment_width = max_lod_x - segment_start_x
                
                # Ensure segment width is positive
                if segment_width <= 0:
                    continue
                
                # Use orange if this Quixel LOD needs auto-generation, otherwise normal color
                # IMPORTANT: Check if this Quixel LOD needs auto-generation
                is_auto_generated = quixel_lod in auto_generated_lods
                if is_auto_generated:
                    segment_color = self._orange_warning_color
                else:
                    segment_color = self._track_color
                
                # Draw the segment
                draw_rounded_rect(
                    segment_start_x,
                    track_y,
                    segment_width,
                    self._track_height,
                    2,
                    segment_color,
                    segments=8
                )

                # Draw gradient when transitioning from non-orange to orange segment (autoLOD enabled)
                # Check if current segment is orange and previous segment was not orange
                if is_auto_generated and self._auto_lod_enabled:
                    if preview_lod > 0:
                        # Check if previous segment was orange
                        prev_quixel_lod = self._min_lod + (preview_lod - 1)
                        prev_is_orange = prev_quixel_lod in auto_generated_lods

                        # Only draw gradient if previous segment was NOT orange (transition point)
                        if not prev_is_orange:
                            # Draw gradient from previous marker to this orange marker
                            prev_segment_start_index = preview_lod - 1
                            if prev_segment_start_index < len(self._marker_positions):
                                prev_segment_start_x = self._marker_positions[prev_segment_start_index]
                                gradient_width = segment_start_x - prev_segment_start_x
                                if gradient_width > 0:
                                    # Draw full gradient from previous marker to orange marker
                                    gradient_segments = 30  # More segments for smoother gradient
                                    for i in range(gradient_segments):
                                        t = i / (gradient_segments - 1) if gradient_segments > 1 else 0
                                        blend_color = (
                                            self._track_color[0] * (1 - t) + self._orange_warning_color[0] * t,
                                            self._track_color[1] * (1 - t) + self._orange_warning_color[1] * t,
                                            self._track_color[2] * (1 - t) + self._orange_warning_color[2] * t,
                                            self._track_color[3] * (1 - t) + self._orange_warning_color[3] * t
                                        )
                                        seg_width = gradient_width / gradient_segments
                                        draw_rounded_rect(
                                            prev_segment_start_x + i * seg_width,
                                            track_y,
                                            seg_width,
                                            self._track_height,
                                            2,
                                            blend_color,
                                            segments=8
                                        )
                    else:
                        # First orange segment is at position 0, draw gradient from min_lod_x to first marker
                        orange_segment_width = segment_start_x - min_lod_x
                        if orange_segment_width > 0:
                            # Draw full gradient from min_lod_x to orange marker
                            gradient_segments = 30  # More segments for smoother gradient
                            for i in range(gradient_segments):
                                t = i / (gradient_segments - 1) if gradient_segments > 1 else 0
                                blend_color = (
                                    self._track_color[0] * (1 - t) + self._orange_warning_color[0] * t,
                                    self._track_color[1] * (1 - t) + self._orange_warning_color[1] * t,
                                    self._track_color[2] * (1 - t) + self._orange_warning_color[2] * t,
                                    self._track_color[3] * (1 - t) + self._orange_warning_color[3] * t
                                )
                                seg_width = orange_segment_width / gradient_segments
                                draw_rounded_rect(
                                    min_lod_x + i * seg_width,
                                    track_y,
                                    seg_width,
                                    self._track_height,
                                    2,
                                    blend_color,
                                    segments=8
                                )
                
                # Draw indicator (orange dot or "?" question mark) underneath segments at marker position
                # Check if this LOD is missing (not in available_lods)
                is_missing = quixel_lod in missing_lods
                if is_missing:
                    # Calculate position to align with bottom row numbers (same as Quixel LOD numbers)
                    marker_y = self.y_screen + (self.height - 12) / 2
                    blf.size(0, self._number_label_size)  # Use same font size as numbers
                    question_text = "?"
                    text_width, text_height = blf.dimensions(0, question_text)
                    number_y = marker_y - self._number_label_gap - text_height  # Same position calculation as numbers

                    if self._auto_lod_enabled:
                        # Draw orange dot when auto LOD is enabled (3px higher than "?" position)
                        dot_radius = 2
                        self._draw_circle(segment_start_x, number_y + 3, dot_radius, self._orange_warning_color)
                    else:
                        # Draw "?" question mark when auto LOD is disabled
                        question_x = segment_start_x - text_width / 2
                        blf.position(0, question_x, number_y, 0)
                        blf.color(0, 0.7, 0.7, 0.7, 1.0)  # Light gray for question mark
                        blf.draw(0, question_text)

            # Draw indicator (orange dot or "?") at maxLOD position if that LOD is missing
            if self._max_lod is not None:
                max_quixel_lod = self._min_lod + self._max_lod
                if max_quixel_lod in missing_lods:
                    # Calculate position to align with bottom row numbers
                    marker_y = self.y_screen + (self.height - 12) / 2
                    blf.size(0, self._number_label_size)
                    question_text = "?"
                    text_width, text_height = blf.dimensions(0, question_text)
                    number_y = marker_y - self._number_label_gap - text_height

                    if self._auto_lod_enabled:
                        # Draw orange dot when auto LOD is enabled
                        dot_radius = 2
                        self._draw_circle(max_lod_x, number_y + 3, dot_radius, self._orange_warning_color)
                    else:
                        # Draw "?" question mark when auto LOD is disabled
                        question_x = max_lod_x - text_width / 2
                        blf.position(0, question_x, number_y, 0)
                        blf.color(0, 0.7, 0.7, 0.7, 1.0)
                        blf.draw(0, question_text)

            # Segment 3: max marker to end (darker gray)
            # Preview LODs beyond maxLOD should NOT be auto-generated and should NOT be orange
            # They are outside the range and should remain dark gray
            if max_lod_x < track_end_x:
                segment3_width = track_end_x - max_lod_x
                draw_rounded_rect(
                    max_lod_x,
                    track_y,
                    segment3_width,
                    self._track_height,
                    2,
                    self._track_color_outside,
                    segments=8
                )
        else:
            # No min/max range set, draw full track with normal color
            draw_rounded_rect(
                track_start_x,
                track_y,
                track_full_width,
                self._track_height,
                2,
                self._track_color,
                segments=8
            )

        # Draw markers
        # Calculate min/max marker positions
        # Min marker: aligned with bottom row (position 0 where bottom shows minLOD)
        # Max marker: aligned with top row (position maxLOD where top shows maxLOD)
        min_marker_index = 0 if self._min_lod is not None else None
        max_marker_index = self._max_lod if self._max_lod is not None else None
        
        for i, marker_x in enumerate(self._marker_positions):
            is_min_lod = (min_marker_index is not None and i == min_marker_index)
            is_max_lod = (max_marker_index is not None and i == max_marker_index)
            is_minmax = is_min_lod or is_max_lod

            # Check if marker is inside or outside min/max range
            # Map marker index to Quixel LOD: position 0 = minLOD, position 1 = minLOD+1, etc.
            # If min_lod is None, use marker index directly (no Quixel LOD mapping)
            quixel_lod_for_marker = (self._min_lod + i) if self._min_lod is not None else i
            is_inside_range = True
            if self._min_lod is not None and self._max_lod is not None:
                # Check if preview LOD position i is within range [0, maxLOD]
                # Preview LOD i corresponds to Quixel LOD (minLOD + i)
                is_inside_range = (i <= self._max_lod)
            
            # Check if this Quixel LOD needs auto-generation (only when autoLOD is enabled)
            # Preview LOD i maps to Quixel LOD (minLOD + i)
            quixel_lod_for_marker = (self._min_lod + i) if self._min_lod is not None else i
            needs_auto_generation = (self._auto_lod_enabled and self._min_lod is not None and quixel_lod_for_marker in auto_generated_lods)

            # Check if this preview LOD (top row) needs auto-generation
            # Preview LOD i maps to Quixel LOD (minLOD + i) when minLOD is set
            # ONLY mark as auto-generated if within minLOD to maxLOD range but not in available_lods
            # Preview LODs beyond maxLOD should NOT be auto-generated and should NOT be orange
            preview_lod_needs_auto = False
            if self._auto_lod_enabled and self._min_lod is not None and self._max_lod is not None:
                quixel_lod_for_preview = self._min_lod + i if self._min_lod is not None else i
                # ONLY check if within the minLOD to maxLOD range
                # Preview LODs beyond maxLOD are not part of the range and should not be orange
                if self._min_lod <= quixel_lod_for_preview <= self._max_lod:
                    # Check if this Quixel LOD needs auto-generation (not in available LODs)
                    if self._available_lods:
                        preview_lod_needs_auto = (quixel_lod_for_preview not in self._available_lods)
                    else:
                        preview_lod_needs_auto = True
            
            # Determine marker properties based on type
            # Priority: orange for auto-generation (only when autoLOD enabled) > minmax color > inside/outside range colors
            if is_minmax:
                # Min/Max LOD markers: use orange if needs auto-generation (and autoLOD enabled), otherwise light gray
                marker_color = self._orange_warning_color if (needs_auto_generation or preview_lod_needs_auto) else self._minmax_marker_color
                marker_width = 3
                marker_height = 14
            else:
                # Regular LOD markers: orange if needs auto-generation (and autoLOD enabled), otherwise normal colors
                # Don't make missing LODs darker - use normal colors when autoLOD is disabled
                if needs_auto_generation or preview_lod_needs_auto:
                    marker_color = self._orange_warning_color
                elif not is_inside_range:
                    marker_color = self._marker_outside_range_color
                else:
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

        # Draw number labels above markers
        # Top row always shows numbers 0, 1, 2, 3, 4, 5, 6, 7
        blf.size(0, self._number_label_size)
        for i, marker_x in enumerate(self._marker_positions):
            # LOD number is the index (0, 1, 2, 3, 4, 5, 6, 7)
            lod_number = i
            
            # Determine number color: white for 0 and maxLOD, gray for others
            # Top numbers should NOT be orange - keep normal colors
            if lod_number == 0 or (self._max_lod is not None and lod_number == self._max_lod):
                number_color = self._white_number_color
            else:
                number_color = self._gray_number_color

            # Calculate position above marker
            marker_y = self.y_screen + (self.height - 12) / 2  # Use standard marker height for positioning
            number_y = marker_y + 12 + self._number_label_gap  # Above the marker

            # Center text horizontally on marker
            number_text = str(lod_number)
            text_width, text_height = blf.dimensions(0, number_text)
            number_x = marker_x - text_width / 2

            blf.position(0, number_x, number_y, 0)
            blf.color(0, number_color[0], number_color[1], number_color[2], number_color[3])
            blf.draw(0, number_text)

        # Draw number labels below markers
        # Bottom row shows only Quixel LOD levels that exist in available_lods
        if self._min_lod is not None and self._max_lod is not None and len(self._marker_positions) > 0 and self._available_lods:
            marker_y = self.y_screen + (self.height - 12) / 2

            # Find the first and last available LODs within the current min/max range
            available_lods_in_range = []
            for lod in self._available_lods:
                # Check if this LOD is within the current min/max slider range
                if self._min_lod <= lod <= self._min_lod + self._max_lod:
                    available_lods_in_range.append(lod)

            # Determine first and last for white highlighting
            first_available_in_range = min(available_lods_in_range) if available_lods_in_range else None
            last_available_in_range = max(available_lods_in_range) if available_lods_in_range else None

            # Draw numbers incrementing from MIN LOD
            # Only draw numbers for LODs that exist in available_lods
            for i, marker_x in enumerate(self._marker_positions):
                # Calculate the Quixel LOD number for this position
                quixel_lod_number = self._min_lod + i

                # Stop if we exceed the slider's MAX LOD
                if quixel_lod_number > self._min_lod + self._max_lod:
                    break

                # Only draw if this Quixel LOD exists in available_lods
                if quixel_lod_number not in self._available_lods:
                    continue

                # Determine number color: white for first and last available LOD in range, gray for others
                is_first = (quixel_lod_number == first_available_in_range)
                is_last = (quixel_lod_number == last_available_in_range)
                if is_first or is_last:
                    number_color = self._white_number_color
                else:
                    number_color = self._gray_number_color

                # Center text horizontally on marker
                number_text = str(quixel_lod_number)
                text_width, text_height = blf.dimensions(0, number_text)
                number_x = marker_x - text_width / 2
                number_y = marker_y - self._number_label_gap - text_height  # Below the marker

                blf.position(0, number_x, number_y, 0)
                blf.color(0, number_color[0], number_color[1],
                         number_color[2], number_color[3])
                blf.draw(0, number_text)

        # Draw handle
        handle_x = self._get_handle_position()
        handle_y = self.y_screen + self.height / 2

        # Choose handle color based on state
        # Loading state takes priority (gray when loading)
        if self._is_loading:
            handle_color = (0.5, 0.5, 0.5, 1.0)  # Gray when loading
        elif self._is_dragging:
            handle_color = self._handle_pressed_color
        elif self._is_hovered:
            handle_color = self._handle_hover_color
        else:
            handle_color = self._handle_color

        # Draw handle circle
        self._draw_circle(handle_x, handle_y, self._handle_radius, handle_color)

        # Draw outline (always white - knob should never be orange)
        outline_color = (1.0, 1.0, 1.0, 1.0)
        self._draw_circle_outline(handle_x, handle_y, self._handle_radius, outline_color, 2)

    def _draw_circle(self, cx, cy, radius, color):
        """Draw a filled circle with anti-aliased edges."""
        # Initialize shader if needed
        DrawConstants.initialize()
        
        # Fallback to old method if shader creation failed
        if DrawConstants.anti_aliased_circle_shader is None:
            # Use original triangle fan method as fallback
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
            return
        
        gpu.state.blend_set('ALPHA')

        shader = DrawConstants.anti_aliased_circle_shader
        shader.bind()
        
        # Get viewport size for coordinate conversion
        viewport = gpu.state.viewport_get()
        viewport_width = viewport[2] if len(viewport) > 2 else 1920
        viewport_height = viewport[3] if len(viewport) > 3 else 1080
        
        # Set shader uniforms
        shader.uniform_float("center", (cx, cy))
        shader.uniform_float("viewportSize", (viewport_width, viewport_height))
        shader.uniform_float("radius", radius)
        shader.uniform_float("color", color)
        shader.uniform_float("edgeSoftness", 1.0)  # 1-pixel soft edge for smooth anti-aliasing
        
        # Calculate scale to cover the circle area (with some padding for edge softness)
        # Scale the unit quad to cover radius + edgeSoftness on each side
        scale_size = (radius + 1.0) * 2.0
        shader.uniform_float("scale", scale_size)
        
        # Draw the quad (no matrix transforms needed, shader handles coordinates)
        DrawConstants.circle_quad_batch.draw(shader)

        gpu.state.blend_set('NONE')

    def _draw_circle_outline(self, cx, cy, radius, color, thickness):
        """Draw a circle outline with anti-aliased edges."""
        # Initialize shader if needed
        DrawConstants.initialize()
        
        # Fallback to old method if shader creation failed
        if DrawConstants.anti_aliased_circle_outline_shader is None:
            # Use original line strip method as fallback
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
            return
        
        gpu.state.blend_set('ALPHA')

        shader = DrawConstants.anti_aliased_circle_outline_shader
        shader.bind()
        
        # Get viewport size for coordinate conversion
        viewport = gpu.state.viewport_get()
        viewport_width = viewport[2] if len(viewport) > 2 else 1920
        viewport_height = viewport[3] if len(viewport) > 3 else 1080
        
        # Set shader uniforms
        shader.uniform_float("center", (cx, cy))
        shader.uniform_float("viewportSize", (viewport_width, viewport_height))
        shader.uniform_float("radius", radius)
        shader.uniform_float("thickness", thickness)
        shader.uniform_float("color", color)
        shader.uniform_float("edgeSoftness", 1.0)  # 1-pixel soft edge for smooth anti-aliasing
        
        # Calculate scale to cover the outline area (with some padding for edge softness)
        # Scale the unit quad to cover radius + thickness/2 + edgeSoftness on each side
        scale_size = (radius + thickness * 0.5 + 1.0) * 2.0
        shader.uniform_float("scale", scale_size)
        
        # Draw the quad (no matrix transforms needed, shader handles coordinates)
        DrawConstants.circle_quad_batch.draw(shader)

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

        # Also allow clicking on track/markers to jump to position and enable dragging
        if self.is_in_rect(x, y):
            new_value = self._value_from_position(x)
            if new_value != self._current_value:
                self._current_value = new_value
                if self.on_value_changed:
                    self.on_value_changed(self._current_value)
            # Enable dragging so user can click and drag from any position on the slider
            self._is_dragging = True
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
        self.floor_toggle = None
        self.wireframe_toggle = None

        # Bridge button (to launch Quixel Bridge and claim active)
        self.bridge_button = None

        # Floor plane tracking
        self.floor_obj = None
        self.floor_mat = None
        self.floor_enabled = False
        self.previous_grid_settings = {}  # Store previous grid overlay settings

        # HDRI widgets
        self.hdri_toggle = None           # Main HDRI toggle button
        self.hdri_dropdown_button = None  # Dropdown arrow button
        self.hdri_panel = None            # Popup panel with thumbnails
        self.hdri_enabled = False         # HDRI viewport shading state
        self.hdri_panel_visible = False   # Panel visibility state
        self.current_hdri = None          # Currently selected HDRI path
        self.available_hdris = []         # List of available HDRIs
        self.previous_shading_type = None # Store previous shading mode before enabling HDRI
        self.previous_use_scene_world = None  # Store previous use_scene_world state
        self.original_world_nodes = None  # Store original world node setup

        # Store original render settings for restoration
        self.previous_render_engine = None
        self.previous_use_raytracing = None
        self.previous_ray_tracing_method = None
        self.previous_ray_tracing_resolution = None
        self.previous_fast_gi = None
        self.previous_use_shadows = None

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

        # OPTIMIZED: Store attach roots as source of truth
        # Attach roots contain ALL data needed:
        #  - attach_root.children = all objects for this variation
        #  - attach_root["lod_levels"] = [0, 1, 2, ...]
        #  - attach_root["lod_0_objects"] = "obj1,obj2,obj3"
        # No need for global object lists or redundant organization!
        self.attach_roots = []

        # LOD slider state
        self.show_all_lods = True  # Show All checkbox state
        self.current_preview_lod = 0  # Currently visible LOD (when Show All = False)

        # LOD loading state management for debouncing
        self.lod_loading_state = False  # Track if LOD is currently loading
        self.pending_lod_timer = None  # Store timer handle for debouncing
        self.target_lod = None  # The LOD level that should be loaded after debounce

        # Callbacks
        self.on_accept = None
        self.on_cancel = None

    def _scan_hdri_assets(self):
        """Scan assets/img folder for HDRI files.

        Returns list of tuples: (thumbnail_path, hdr_path, hdri_name)
        """
        addon_dir = Path(__file__).parent.parent
        hdri_dir = addon_dir / "assets" / "img"

        if not hdri_dir.exists():
            print(f"⚠️ HDRI directory not found: {hdri_dir}")
            return []

        hdri_list = []

        # Scan for PNG files (thumbnails)
        for png_file in hdri_dir.glob("*.png"):
            # Get corresponding HDR file
            hdr_file = png_file.with_suffix(".hdr")

            if hdr_file.exists():
                hdri_name = png_file.stem  # Filename without extension
                hdri_list.append((str(png_file), str(hdr_file), hdri_name))

        # Sort by name, but put default HDRI first
        default_hdri_name = "kloofendal_48d_partly_cloudy_puresky_1k"

        def sort_key(item):
            # Return 0 for default HDRI to put it first, otherwise use name
            if item[2] == default_hdri_name:
                return (0, "")
            else:
                return (1, item[2])

        hdri_list.sort(key=sort_key)

        return hdri_list

    def init(self, context):
        """Initialize toolbar with buttons."""
        import bpy

        area = context.area

        # Backup the original world state BEFORE any modifications
        # This ensures we capture Blender's default state, not a modified one
        if self.original_world_nodes is None:
            world = bpy.context.scene.world
            if world:
                self.original_world_nodes = self._backup_world_nodes(world)

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
        divider_spacing = 8  # Space for divider line

        # Calculate total width with all LOD controls
        # Layout: Min LOD [4px] dropdown [8px] Max LOD [4px] dropdown [16px] Auto LOD [8px] divider [8px] Cancel | Accept
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

        # Get addon directory for icon paths
        addon_dir = Path(__file__).parent.parent

        # Create Min LOD dropdown (renamed from lod_dropdown)
        self.min_lod_dropdown = BL_UI_Dropdown(min_lod_dropdown_x, button_y, lod_dropdown_width, button_height)
        # Set check icon path
        check_icon_path = addon_dir / "assets" / "icons" / "check_16.png"
        if check_icon_path.exists():
            self.min_lod_dropdown._check_icon_path = str(check_icon_path)
        self.min_lod_dropdown.init(context)
        # Set items based on detected LOD levels (will be updated later)
        if self.lod_levels:
            self.min_lod_dropdown.set_items([f"LOD{level}" for level in self.lod_levels])
        else:
            self.min_lod_dropdown.set_items(["LOD0"])  # Default

        # Create Max LOD dropdown (LOD0-LOD7, default LOD5)
        self.max_lod_dropdown = BL_UI_Dropdown(max_lod_dropdown_x, button_y, lod_dropdown_width, button_height)
        # Set check icon path
        if check_icon_path.exists():
            self.max_lod_dropdown._check_icon_path = str(check_icon_path)
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
        # Normal: #138ae8 = RGB(19, 138, 232) = (19/255, 138/255, 232/255)
        self.accept_button._normal_bg_color = (0.0745, 0.541, 0.910, 1.0)
        # Hover: slightly lighter blue
        self.accept_button._hover_bg_color = (0.094, 0.620, 1.0, 1.0)
        # Pressed: slightly darker blue
        self.accept_button._pressed_bg_color = (0.055, 0.463, 0.820, 1.0)
        self.accept_button.set_mouse_up(self._handle_accept)
        self.accept_button.init(context)

        # ========================================
        # TOP TOOLBAR (LOD Slider)
        # ========================================
        toolbar_gap = 8  # Gap between bottom and top toolbar
        top_panel_y = panel_y + panel_height + toolbar_gap

        # Top toolbar dimensions (label + slider + divider + wireframe button + HDRI buttons)
        lod_label_width = 72  # Width for "LOD0" and "Quixel LOD0"
        label_to_slider_gap = 8  # 8px gap between label and slider
        slider_width = 240
        slider_to_divider_gap = 8
        divider_spacing = 16  # Space for divider line
        floor_button_size = button_height  # Square floor button
        floor_button_gap = 4  # Gap between floor and wireframe
        wireframe_button_size = button_height  # Square button
        hdri_button_gap = 4  # Gap between wireframe and HDRI
        hdri_button_size = button_height  # Square HDRI button (same as wireframe)
        hdri_dropdown_width = 16  # Dropdown arrow width
        hdri_total_width = hdri_button_size + hdri_dropdown_width
        top_right_padding = 8

        # Calculate top toolbar width
        top_content_width = (lod_label_width + label_to_slider_gap + slider_width +
                            slider_to_divider_gap + divider_spacing + floor_button_size +
                            floor_button_gap + wireframe_button_size +
                            hdri_button_gap + hdri_total_width + top_right_padding)
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
        floor_x = top_divider_x + divider_spacing
        wireframe_x = floor_x + floor_button_size + floor_button_gap

        # Store label position and divider position for drawing
        self.lod_slider_label_x = lod_label_x
        self.lod_slider_label_y = top_widget_y + button_height / 2
        self.lod_slider_label_text = "LOD0"  # Default label (preview LOD)
        self.lod_slider_quixel_label_text = "Quixel LOD0"  # Default Quixel LOD label
        self.lod_slider_status_text = None  # Status text ("Generated" or "Missing")

        # Store divider position
        self.top_divider_x = top_divider_x
        self.top_divider_y_start = top_panel_y + 8
        self.top_divider_y_end = top_panel_y + panel_height - 8

        # Create LOD slider
        self.lod_slider = BL_UI_Slider(slider_x, top_widget_y, slider_width, button_height)
        self.lod_slider.init(context)
        self.lod_slider.on_value_changed = self._handle_slider_change

        # Create floor toggle button
        self.floor_toggle = BL_UI_ToggleButton(floor_x, top_widget_y, floor_button_size)
        # Set icon path (fallback to "F" text if icon not found)
        addon_dir = Path(__file__).parent.parent
        floor_icon_path = addon_dir / "assets" / "icons" / "floor_32.png"
        if floor_icon_path.exists():
            self.floor_toggle.icon_path = str(floor_icon_path)
        else:
            # Fallback to text if icon not found
            self.floor_toggle.icon_text = "F"
        self.floor_toggle.on_toggle = self._handle_floor_toggle
        self.floor_toggle.toggled = True  # Enabled by default
        self.floor_toggle.init(context)
        # Enable floor by default (this will create the floor and disable Blender's grid)
        self._handle_floor_toggle(True)

        # Create wireframe toggle button
        self.wireframe_toggle = BL_UI_ToggleButton(wireframe_x, top_widget_y, wireframe_button_size)
        # Set icon path (fallback to "W" text if icon not found)
        addon_dir = Path(__file__).parent.parent
        icon_path = addon_dir / "assets" / "icons" / "wireframe_32.png"
        if icon_path.exists():
            self.wireframe_toggle.icon_path = str(icon_path)
        else:
            # Fallback to text if icon not found
            self.wireframe_toggle.icon_text = "W"
        self.wireframe_toggle.on_toggle = self._handle_wireframe_toggle
        self.wireframe_toggle.init(context)

        # ========================================
        # HDRI BUTTONS (next to wireframe)
        # ========================================
        # Scan available HDRIs
        self.available_hdris = self._scan_hdri_assets()

        # Position after wireframe button
        hdri_button_x = wireframe_x + wireframe_button_size + hdri_button_gap

        # Create HDRI toggle button
        self.hdri_toggle = BL_UI_ToggleButton(hdri_button_x, top_widget_y, hdri_button_size)
        hdri_icon_path = addon_dir / "assets" / "icons" / "hdri_32.png"
        if hdri_icon_path.exists():
            self.hdri_toggle.icon_path = str(hdri_icon_path)
        else:
            self.hdri_toggle.icon_text = "H"
        self.hdri_toggle.on_toggle = self._handle_hdri_toggle
        self.hdri_toggle.init(context)

        # Create dropdown button (attached to right side of HDRI button)
        dropdown_x = hdri_button_x + hdri_button_size
        self.hdri_dropdown_button = BL_UI_DropdownButton(dropdown_x, top_widget_y,
                                                          hdri_dropdown_width, button_height)
        dropdown_icon_path = addon_dir / "assets" / "icons" / "dropdown_2_16.png"
        if dropdown_icon_path.exists():
            self.hdri_dropdown_button.icon_path = str(dropdown_icon_path)
        self.hdri_dropdown_button.on_click = self._handle_hdri_dropdown_click
        self.hdri_dropdown_button.init(context)

        # Create HDRI panel (initially hidden, position will be set when opened)
        if self.available_hdris:
            # Initial position (will be updated when panel is shown)
            hdri_panel_x = 0
            hdri_panel_y = 0
            self.hdri_panel = BL_UI_HDRIPanel(hdri_panel_x, hdri_panel_y, self.available_hdris)
            self.hdri_panel.visible = False
            self.hdri_panel.on_hdri_selected = self._handle_hdri_selected
            self.hdri_panel.init(context)

        self.visible = True

    def _update_slider_labels(self):
        """Update LOD slider labels (preview LOD, Quixel LOD, and status)."""
        if not hasattr(self, 'lod_slider') or not self.lod_slider:
            return

        # Get current preview LOD from slider
        preview_lod = self.lod_slider.get_value()

        # Update preview LOD label
        self.lod_slider_label_text = f"LOD{preview_lod}"

        # Get min_lod from dropdown
        min_lod = 0
        if hasattr(self, 'min_lod_dropdown') and self.min_lod_dropdown:
            min_lod_text = self.min_lod_dropdown.get_selected_item()
            if min_lod_text:
                import re
                match = re.search(r'LOD(\d+)', min_lod_text)
                if match:
                    min_lod = int(match.group(1))

        # Calculate and update Quixel LOD
        current_quixel_lod = min_lod + preview_lod
        self.current_quixel_lod = current_quixel_lod
        self.lod_slider_quixel_label_text = f"Quixel LOD{current_quixel_lod}"

        # Determine status text
        if current_quixel_lod in self.lod_levels:
            self.lod_slider_status_text = None
        else:
            if self.auto_lod_enabled:
                self.lod_slider_status_text = "Generated"
            else:
                self.lod_slider_status_text = "Missing"

    def _handle_slider_change(self, lod_level):
        """Handle LOD slider value change with debouncing.
        
        Immediately updates slider visual position and sets loading state.
        Defers actual LOD visibility update via timer to avoid processing
        intermediate steps when sliding quickly.
        """
        import bpy
        
        # OPTIMIZATION: Only update if LOD level actually changed!
        # This prevents hundreds of redundant calls during slider drag
        if hasattr(self, 'current_preview_lod') and self.current_preview_lod == lod_level:
            return

        # Immediately update label text for responsive UI
        self.lod_slider_label_text = f"LOD{lod_level}"

        # Get min_lod from dropdown
        min_lod = 0
        if hasattr(self, 'min_lod_dropdown') and self.min_lod_dropdown:
            min_lod_text = self.min_lod_dropdown.get_selected_item()
            if min_lod_text:
                import re
                match = re.search(r'LOD(\d+)', min_lod_text)
                if match:
                    min_lod = int(match.group(1))

        # Calculate and update Quixel LOD
        current_quixel_lod = min_lod + lod_level
        self.current_quixel_lod = current_quixel_lod
        self.lod_slider_quixel_label_text = f"Quixel LOD{current_quixel_lod}"

        # Determine status text
        if current_quixel_lod in self.lod_levels:
            self.lod_slider_status_text = None
        else:
            if self.auto_lod_enabled:
                self.lod_slider_status_text = "Generated"
            else:
                self.lod_slider_status_text = "Missing"

        # Store target LOD for timer callback
        self.target_lod = lod_level
        
        # Set loading state (gray handle)
        self.lod_loading_state = True
        if self.lod_slider:
            self.lod_slider.set_loading_state(True)
        
        # Cancel any existing pending timer
        if self.pending_lod_timer is not None:
            if bpy.app.timers.is_registered(self.pending_lod_timer):
                bpy.app.timers.unregister(self.pending_lod_timer)
            self.pending_lod_timer = None
        
        # Register new timer to process LOD change after debounce delay (150ms)
        self.pending_lod_timer = self._process_lod_change_timer
        bpy.app.timers.register(self.pending_lod_timer, first_interval=0.15)

    def _process_lod_change_timer(self):
        """Timer callback to process LOD change after debounce delay.
        
        This is called by bpy.app.timers after the debounce period.
        Processes the target LOD and updates loading state.
        """
        import bpy
        
        # Check if we still have a valid target LOD
        if self.target_lod is None:
            # No target, clear loading state and unregister
            self.lod_loading_state = False
            if self.lod_slider:
                self.lod_slider.set_loading_state(False)
            self.pending_lod_timer = None
            return None  # Unregister timer
        
        # Process the LOD change
        target = self.target_lod
        self.current_preview_lod = target
        
        # Update visibility (this is the actual operation that was deferred)
        self.update_lod_visibility()
        
        # Update text labels with Quixel LOD info
        self._update_lod_text_labels()
        
        # Clear loading state (blue handle)
        self.lod_loading_state = False
        if self.lod_slider:
            self.lod_slider.set_loading_state(False)
        
        # Clear timer reference
        self.pending_lod_timer = None
        self.target_lod = None
        
        # Unregister timer (return None)
        return None

    def _handle_wireframe_toggle(self, toggled):
        """Handle wireframe toggle button."""
        import bpy
        self.wireframe_enabled = toggled

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
            self.wireframe_toggle._toggled = False

        # Force viewport update
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    def _handle_floor_toggle(self, toggled):
        """Handle floor toggle button."""
        import bpy
        context = bpy.context
        self.floor_enabled = toggled

        if toggled:
            # Save current grid overlay settings before disabling
            self._save_grid_settings()

            # Disable Blender's grid
            self._disable_grid()

            # Create floor plane if it doesn't exist
            if self.floor_obj is None:
                # Check if floor already exists in scene
                existing_floor = bpy.data.objects.get("__QuixelFloor__")
                if existing_floor:
                    self.floor_obj = existing_floor
                    self.floor_obj.hide_select = True  # Ensure selection is disabled
                    self.floor_mat = bpy.data.materials.get("__QuixelFloorMaterial__")
                else:
                    # Create new floor plane
                    try:
                        if context is None or context.scene is None:
                            print(f"  ⚠️  Cannot create floor: invalid context")
                            return
                        self.floor_obj, self.floor_mat = create_floor_plane(context)
                        if self.floor_obj is None or self.floor_mat is None:
                            return
                    except Exception as e:
                        print(f"  ⚠️  Error creating floor plane: {e}")
                        import traceback
                        traceback.print_exc()
                        return

            # Show floor plane
            if self.floor_obj:
                # Ensure object is in current collection (objects are linked to collections, not view layers)
                # Check if object is in any collection in the current scene
                if not self.floor_obj.users_collection:
                    # Object not in any collection, link it to the active collection
                    context.collection.objects.link(self.floor_obj)
                self.floor_obj.hide_set(False)
                self.floor_obj.hide_viewport = False
        else:
            # Restore previous grid settings
            self._restore_grid_settings()

            # Hide floor plane
            if self.floor_obj:
                # Hide the floor object
                self.floor_obj.hide_set(True)
                self.floor_obj.hide_viewport = True

        # Force viewport update
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    def _save_grid_settings(self):
        """Save current grid overlay settings."""
        import bpy
        self.previous_grid_settings = {}
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        overlay = space.overlay
                        self.previous_grid_settings = {
                            'show_floor': overlay.show_floor,
                            'show_axis_x': overlay.show_axis_x,
                            'show_axis_y': overlay.show_axis_y,
                            'show_axis_z': overlay.show_axis_z,
                        }
                        return

    def _disable_grid(self):
        """Disable Blender's grid overlay."""
        import bpy
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        overlay = space.overlay
                        overlay.show_floor = False
                        overlay.show_axis_x = False
                        overlay.show_axis_y = False
                        overlay.show_axis_z = False

    def _restore_grid_settings(self):
        """Restore previous grid overlay settings."""
        import bpy
        # If no previous settings were saved, restore to defaults (all enabled)
        if not self.previous_grid_settings:
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            overlay = space.overlay
                            overlay.show_floor = True
                            overlay.show_axis_x = True
                            overlay.show_axis_y = True
                            overlay.show_axis_z = True
            return

        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        overlay = space.overlay
                        overlay.show_floor = self.previous_grid_settings.get('show_floor', True)
                        overlay.show_axis_x = self.previous_grid_settings.get('show_axis_x', True)
                        overlay.show_axis_y = self.previous_grid_settings.get('show_axis_y', True)
                        overlay.show_axis_z = self.previous_grid_settings.get('show_axis_z', True)

    def _disable_floor(self):
        """Disable floor and restore grid settings."""
        import bpy

        # Hide floor plane
        if self.floor_obj:
            # Check if object is in current view layer before hiding
            view_layer = bpy.context.view_layer
            if self.floor_obj.name in view_layer.objects:
                self.floor_obj.hide_set(True)
            # Always set hide_viewport (doesn't require view layer membership)
            self.floor_obj.hide_viewport = True
            self.floor_obj.hide_viewport = True

        # Restore grid settings
        self._restore_grid_settings()

        # Reset floor state
        self.floor_enabled = False

        # Reset toggle button visual state if it exists
        if self.floor_toggle:
            self.floor_toggle._toggled = False

        # Force viewport update
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                    area.tag_redraw()


    def _handle_hdri_toggle(self, toggled):
        """Handle HDRI toggle button - enables/disables viewport shading."""
        import bpy
        self.hdri_enabled = toggled

        if toggled:
            # Load default HDRI if this is the first time enabling and no HDRI is set
            if not self.current_hdri:
                # Find the default HDRI
                default_hdri_name = "kloofendal_48d_partly_cloudy_puresky_1k"
                for thumb_path, hdr_path, hdri_name in self.available_hdris:
                    if hdri_name == default_hdri_name:
                        self.current_hdri = hdr_path
                        self._setup_hdri_background(hdr_path)
                        # Update panel selection if it exists
                        if self.hdri_panel:
                            for btn in self.hdri_panel.thumbnail_buttons:
                                btn.is_selected = (btn.hdr_path == hdr_path)
                        break
            else:
                # Re-enable with previously selected HDRI
                self._setup_hdri_background(self.current_hdri)
        else:
            # When disabling, restore original world setup
            self._restore_world_background()

        # Set viewport shading mode
        self._set_viewport_shading(toggled)

    def _handle_hdri_dropdown_click(self):
        """Handle HDRI dropdown button click - show/hide HDRI panel."""
        import bpy

        # Toggle panel visibility
        self.hdri_panel_visible = not self.hdri_panel_visible

        if self.hdri_panel_visible and self.hdri_panel:
            # Calculate panel position (centered above top toolbar)
            # Get current area dimensions
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        # Position panel 16px above the top toolbar and centered horizontally
                        panel_gap = 16
                        if self.top_background_panel:
                            # Center horizontally (same as other toolbars)
                            panel_x = (area.width - self.hdri_panel.width) / 2
                            # Position above top toolbar - use x, y properties which are in screen coordinates
                            panel_y = (self.top_background_panel.y_screen +
                                     self.top_background_panel.height + panel_gap)
                            self.hdri_panel.update_position(panel_x, panel_y)

                        self.hdri_panel.visible = True
                        area.tag_redraw()
                        break
        elif self.hdri_panel:
            self.hdri_panel.visible = False
            # Force redraw
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()

    def _handle_hdri_selected(self, hdr_path, hdri_name):
        """Handle HDRI selection from panel."""
        import bpy

        self.current_hdri = hdr_path

        # Apply HDRI to world background
        self._setup_hdri_background(hdr_path)

        # If HDRI is not currently enabled, enable it automatically
        if not self.hdri_enabled:
            self.hdri_enabled = True
            if self.hdri_toggle:
                self.hdri_toggle._toggled = True
            self._set_viewport_shading(True)

        # Keep the panel open so user can try different HDRIs
        # Panel will close when clicking outside or toggling dropdown

        # Force viewport update
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    def _close_all_dropdowns(self, exclude_dropdown=None):
        """Close all dropdown menus except the excluded one.
        
        Args:
            exclude_dropdown: Dropdown to exclude from closing (optional)
        """
        if self.min_lod_dropdown and self.min_lod_dropdown != exclude_dropdown:
            if self.min_lod_dropdown._is_open:
                self.min_lod_dropdown._is_open = False
                self.min_lod_dropdown._hovered_item_index = -1
                self.min_lod_dropdown._has_ever_hovered = False
        if self.max_lod_dropdown and self.max_lod_dropdown != exclude_dropdown:
            if self.max_lod_dropdown._is_open:
                self.max_lod_dropdown._is_open = False
                self.max_lod_dropdown._hovered_item_index = -1
                self.max_lod_dropdown._has_ever_hovered = False

    def _close_hdri_panel(self):
        """Close HDRI selection panel."""
        import bpy

        self.hdri_panel_visible = False
        if self.hdri_panel:
            self.hdri_panel.visible = False

        # Force viewport update
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    def _is_point_in_hdri_panel(self, x, y):
        """Check if point is inside HDRI panel bounds."""
        if not self.hdri_panel or not self.hdri_panel_visible:
            return False
        return self.hdri_panel.is_in_rect(x, y)

    def _set_viewport_shading(self, enabled):
        """Enable/disable rendered shading with HDRI and EEVEE settings in viewport."""
        import bpy

        scene = bpy.context.scene

        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        if enabled:
                            # Store current viewport shading settings ONLY if not already stored
                            if self.previous_shading_type is None:
                                self.previous_shading_type = space.shading.type
                            if self.previous_use_scene_world is None:
                                self.previous_use_scene_world = space.shading.use_scene_world

                            # Store current render engine and EEVEE settings
                            if self.previous_render_engine is None:
                                self.previous_render_engine = scene.render.engine

                            # Check if current or previous engine is EEVEE (legacy or Next)
                            is_eevee = scene.render.engine in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT')
                            was_eevee = self.previous_render_engine in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT')

                            if is_eevee or was_eevee:
                                eevee = scene.eevee
                                if self.previous_use_raytracing is None:
                                    self.previous_use_raytracing = eevee.use_raytracing if hasattr(eevee, 'use_raytracing') else False
                                    if hasattr(eevee, 'ray_tracing_method'):
                                        self.previous_ray_tracing_method = eevee.ray_tracing_method
                                    if hasattr(eevee, 'ray_tracing_options') and hasattr(eevee.ray_tracing_options, 'resolution_scale'):
                                        self.previous_ray_tracing_resolution = eevee.ray_tracing_options.resolution_scale
                                    self.previous_fast_gi = eevee.use_fast_gi if hasattr(eevee, 'use_fast_gi') else False
                                    self.previous_use_shadows = eevee.use_shadows if hasattr(eevee, 'use_shadows') else True

                            # Enable RENDERED shading mode with scene world
                            space.shading.type = 'RENDERED'
                            space.shading.use_scene_world = True

                            # Switch to EEVEE render engine (use EEVEE_NEXT if available, otherwise legacy EEVEE)
                            try:
                                scene.render.engine = 'BLENDER_EEVEE_NEXT'
                            except:
                                try:
                                    scene.render.engine = 'BLENDER_EEVEE'
                                except Exception as e:
                                    pass

                            # Configure EEVEE settings with error handling
                            try:
                                eevee = scene.eevee

                                # Enable raytracing
                                if hasattr(eevee, 'use_raytracing'):
                                    eevee.use_raytracing = True

                                # Set raytracing method
                                if hasattr(eevee, 'ray_tracing_method'):
                                    try:
                                        eevee.ray_tracing_method = 'SCREEN'
                                    except Exception as e:
                                        pass

                                # Set raytracing resolution
                                if hasattr(eevee, 'ray_tracing_options'):
                                    if hasattr(eevee.ray_tracing_options, 'resolution_scale'):
                                        try:
                                            eevee.ray_tracing_options.resolution_scale = 2
                                        except Exception as e:
                                            pass

                                # Enable Fast GI
                                if hasattr(eevee, 'use_fast_gi'):
                                    eevee.use_fast_gi = True

                                # Enable shadows
                                if hasattr(eevee, 'use_shadows'):
                                    eevee.use_shadows = True

                            except Exception as e:
                                pass

                        else:
                            # Restore previous shading mode
                            if self.previous_shading_type is not None:
                                space.shading.type = self.previous_shading_type
                            else:
                                space.shading.type = 'SOLID'

                            # Restore previous use_scene_world setting
                            if self.previous_use_scene_world is not None:
                                space.shading.use_scene_world = self.previous_use_scene_world
                            else:
                                space.shading.use_scene_world = False

                            # Restore render engine
                            if self.previous_render_engine is not None:
                                scene.render.engine = self.previous_render_engine

                            # Restore EEVEE settings if applicable (supports both legacy and Next)
                            if scene.render.engine in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):
                                eevee = scene.eevee
                                if self.previous_use_raytracing is not None and hasattr(eevee, 'use_raytracing'):
                                    eevee.use_raytracing = self.previous_use_raytracing
                                if self.previous_ray_tracing_method is not None and hasattr(eevee, 'ray_tracing_method'):
                                    eevee.ray_tracing_method = self.previous_ray_tracing_method
                                if self.previous_ray_tracing_resolution is not None and hasattr(eevee, 'ray_tracing_options') and hasattr(eevee.ray_tracing_options, 'resolution_scale'):
                                    eevee.ray_tracing_options.resolution_scale = self.previous_ray_tracing_resolution
                                if self.previous_fast_gi is not None and hasattr(eevee, 'use_fast_gi'):
                                    eevee.use_fast_gi = self.previous_fast_gi
                                if self.previous_use_shadows is not None and hasattr(eevee, 'use_shadows'):
                                    eevee.use_shadows = self.previous_use_shadows

                area.tag_redraw()

    def _setup_hdri_background(self, hdri_path):
        """Set up world shader with HDRI environment texture."""
        import bpy

        # Get or create world
        world = bpy.context.scene.world
        if not world:
            world = bpy.data.worlds.new("World")
            bpy.context.scene.world = world

        # Enable nodes
        world.use_nodes = True
        nodes = world.node_tree.nodes
        links = world.node_tree.links

        # Clear existing nodes
        nodes.clear()

        # Create Environment Texture node
        env_node = nodes.new('ShaderNodeTexEnvironment')
        try:
            env_node.image = bpy.data.images.load(hdri_path, check_existing=True)
            env_node.interpolation = 'Cubic'  # Set interpolation to Cubic for better quality
        except Exception as e:
            print(f"⚠️ Failed to load HDRI: {e}")
            return
        env_node.location = (-300, 300)

        # Create Background node
        bg_node = nodes.new('ShaderNodeBackground')
        bg_node.location = (0, 300)

        # Create Output node
        output_node = nodes.new('ShaderNodeOutputWorld')
        output_node.location = (300, 300)

        # Link nodes
        links.new(env_node.outputs['Color'], bg_node.inputs['Color'])
        links.new(bg_node.outputs['Background'], output_node.inputs['Surface'])

    def _backup_world_nodes(self, world):
        """Backup the current world node setup."""
        import bpy

        if not world or not world.use_nodes:
            return None

        backup = {
            'nodes': [],
            'links': []
        }

        # Store node information
        for node in world.node_tree.nodes:
            node_data = {
                'type': node.bl_idname,
                'location': tuple(node.location),
                'name': node.name
            }

            # Store node-specific data
            if node.bl_idname == 'ShaderNodeBackground':
                node_data['color'] = tuple(node.inputs['Color'].default_value)
                node_data['strength'] = node.inputs['Strength'].default_value
            elif node.bl_idname == 'ShaderNodeTexEnvironment':
                if node.image:
                    node_data['image_name'] = node.image.name

            backup['nodes'].append(node_data)

        # Store link information
        for link in world.node_tree.links:
            link_data = {
                'from_node': link.from_node.name,
                'from_socket': link.from_socket.name,
                'to_node': link.to_node.name,
                'to_socket': link.to_socket.name
            }
            backup['links'].append(link_data)

        return backup

    def _restore_world_background(self):
        """Restore the original world background setup."""
        import bpy

        world = bpy.context.scene.world
        if not world:
            return

        # If we have a backup, restore it
        if self.original_world_nodes:
            world.use_nodes = True
            nodes = world.node_tree.nodes
            links = world.node_tree.links

            # Clear current nodes
            nodes.clear()

            # Recreate original nodes
            node_map = {}
            for node_data in self.original_world_nodes['nodes']:
                new_node = nodes.new(node_data['type'])
                new_node.location = node_data['location']
                node_map[node_data['name']] = new_node

                # Restore node-specific data
                if node_data['type'] == 'ShaderNodeBackground':
                    if 'color' in node_data:
                        new_node.inputs['Color'].default_value = node_data['color']
                    if 'strength' in node_data:
                        new_node.inputs['Strength'].default_value = node_data['strength']
                elif node_data['type'] == 'ShaderNodeTexEnvironment':
                    if 'image_name' in node_data and node_data['image_name'] in bpy.data.images:
                        new_node.image = bpy.data.images[node_data['image_name']]

            # Recreate links
            for link_data in self.original_world_nodes['links']:
                from_node = node_map.get(link_data['from_node'])
                to_node = node_map.get(link_data['to_node'])

                if from_node and to_node:
                    from_socket = from_node.outputs.get(link_data['from_socket'])
                    to_socket = to_node.inputs.get(link_data['to_socket'])

                    if from_socket and to_socket:
                        links.new(from_socket, to_socket)
        else:
            # No backup available, create default gray world
            world.use_nodes = True
            nodes = world.node_tree.nodes
            links = world.node_tree.links
            nodes.clear()

            bg_node = nodes.new('ShaderNodeBackground')
            bg_node.inputs['Color'].default_value = (0.05, 0.05, 0.05, 1.0)
            bg_node.location = (0, 300)

            output_node = nodes.new('ShaderNodeOutputWorld')
            output_node.location = (300, 300)

            links.new(bg_node.outputs['Background'], output_node.inputs['Surface'])

    def _handle_auto_lod_change(self, checked):
        """Handle Auto LOD checkbox change."""
        self.auto_lod_enabled = checked
        # Update slider with Auto LOD state
        if self.lod_slider:
            self.lod_slider.set_auto_lod_enabled(checked)
        # Update slider labels to reflect status change (Generated/Missing)
        self._update_slider_labels()

    def update_lod_visibility(self):
        """Show/hide LODs based on slider position.

        OPTIMIZED: Uses attach roots as source of truth.
        Reads LOD level from custom property (instant), no name parsing needed!
        Maps preview LOD position to Quixel LOD: quixel_lod = min_lod + preview_lod
        """
        import bpy

        if not self.attach_roots:
            return

        # Get min LOD to calculate target Quixel LOD
        min_lod = 0
        if self.min_lod_dropdown:
            min_lod_text = self.min_lod_dropdown.get_selected_item()
            if min_lod_text:
                import re
                match = re.search(r'LOD(\d+)', min_lod_text)
                if match:
                    min_lod = int(match.group(1))

        # Calculate target Quixel LOD from preview LOD position
        # Preview LOD position maps to Quixel LOD: quixel_lod = min_lod + preview_lod
        target_quixel_lod = min_lod + self.current_preview_lod

        # Loop through each attach root (one per variation)
        for attach_root in self.attach_roots:
            # Loop through children of this attach root
            for child in attach_root.children:
                # Skip non-mesh objects
                if child.type != 'MESH':
                    continue

                # Read LOD level from custom property (this is the Quixel LOD)
                quixel_lod = child.get("lod_level", 0)

                # Match by Quixel LOD, not preview LOD position
                should_hide = (quixel_lod != target_quixel_lod)
                child.hide_set(should_hide)

        # Update text labels using eye icon
        if self.lod_text_objects:
            for item in self.lod_text_objects:
                # Handle tuple (text_obj, lod_level, total_tris) or (text_obj, lod_level)
                # lod_level here is the Quixel LOD stored with the text object
                if isinstance(item, tuple) and len(item) >= 2:
                    text_obj = item[0]
                    text_quixel_lod = item[1]  # This is the Quixel LOD the text represents
                else:
                    continue
                
                # Always hide text objects below minLOD (regardless of target_quixel_lod)
                if text_quixel_lod < min_lod:
                    text_obj.hide_set(True)
                    text_obj.hide_viewport = True
                    # Also hide secondary text object if it exists
                    secondary_text_name = f"{text_obj.name}_Secondary"
                    if secondary_text_name in bpy.data.objects:
                        secondary_obj = bpy.data.objects[secondary_text_name]
                        secondary_obj.hide_set(True)
                        secondary_obj.hide_viewport = True
                    continue
                
                # Match by Quixel LOD, not preview LOD position
                should_hide = (text_quixel_lod != target_quixel_lod)
                text_obj.hide_set(should_hide)
                text_obj.hide_viewport = should_hide

        # Tag viewport for redraw
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    def _handle_accept(self, button):
        """Handle Accept button click."""
        import bpy

        # Restore HDRI and viewport state to original
        if self.hdri_enabled:
            # Turn off HDRI toggle
            if self.hdri_toggle:
                self.hdri_toggle._toggled = False
            self.hdri_enabled = False
            # Restore original world
            self._restore_world_background()
            # Restore original viewport shading
            self._set_viewport_shading(False)

        # Close HDRI panel if open
        if self.hdri_panel_visible:
            self.hdri_panel_visible = False
            if self.hdri_panel:
                self.hdri_panel.visible = False

        # Reset stored viewport states for next time toolbar is used
        self.previous_shading_type = None
        self.previous_use_scene_world = None
        self.previous_render_engine = None
        self.previous_use_raytracing = None
        self.previous_ray_tracing_method = None
        self.previous_ray_tracing_resolution = None
        self.previous_fast_gi = None
        self.previous_use_shadows = None

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
        # Print removed to reduce console clutter
        self._apply_material_to_all_lods(target_lod)

        # Step 2: Apply LOD filtering if target LOD > 0 (BEFORE auto LOD generation)
        # This renames LODs so that the selected min LOD becomes LOD0
        if target_lod > 0:
            # Print removed to reduce console clutter
            self._apply_lod_filter(target_lod)
            # After filtering, the base is now LOD0, so we generate from 0 to max_lod
            adjusted_min_lod = 0
        else:
            adjusted_min_lod = target_lod

        # Step 3: Generate auto LOD levels if enabled (AFTER filtering)
        if self.auto_lod_enabled:
            # Print removed to reduce console clutter
            self._generate_auto_lods(adjusted_min_lod, max_lod)

        # Step 4: Clean up unused materials
        # Print removed to reduce console clutter
        self._cleanup_unused_materials()

        # Step 5: Show only the lowest LOD level (highest number)
        # Print removed to reduce console clutter
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
            try:
                # Quick validity check without expensive name lookup
                if obj.type != 'MESH' or not obj.data:
                    continue

                lod_level = extract_lod_from_object_name(obj.name)
                if lod_level == min_lod:
                    base_objects.append(obj)
            except (AttributeError, ReferenceError):
                # Object was deleted or is invalid
                continue

        if not base_objects:
            # Print removed to reduce console clutter
            return

        # Prints removed to reduce console clutter

        # Calculate decimation ratios based on steps from base LOD
        # Each step is 50% of the base: step 1 = 50%, step 2 = 25%, step 3 = 12.5%, etc.

        # Generate LOD levels
        new_objects = []
        for base_obj in base_objects:
            # Get polycount of base object
            base_polycount = len(base_obj.data.polygons)

            for target_lod in range(min_lod + 1, max_lod + 1):
                # Skip if this LOD already exists
                existing = False
                for obj in self.imported_objects:
                    try:
                        if extract_lod_from_object_name(obj.name) == target_lod:
                            # Check if it's the same variation (same parent)
                            if obj.parent == base_obj.parent:
                                existing = True
                                break
                    except (AttributeError, ReferenceError):
                        continue

                if existing:
                    # Print removed to reduce console clutter
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

                # Print removed to reduce console clutter

                # Add to tracking lists
                new_objects.append(new_obj)
                self.imported_objects.append(new_obj)

        # Print removed to reduce console clutter

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
            try:
                # Quick validity check without expensive name lookup
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
            except (AttributeError, ReferenceError):
                # Object was deleted or is invalid
                continue

        if not target_material:
            # Print removed to reduce console clutter
            return

        # Print removed to reduce console clutter

        # Step 2: Remove LOD suffix from material name
        old_mat_name = target_material.name
        # Remove patterns like _LOD0, _LOD1, _LOD_0_______, etc.
        new_mat_name = re.sub(r'_LOD_[_0-9]{8}', '', old_mat_name)  # IOI format
        new_mat_name = re.sub(r'_LOD\d+', '', new_mat_name)  # Standard format

        if new_mat_name != old_mat_name:
            target_material.name = new_mat_name
            # Print removed to reduce console clutter

        # Step 3: Apply this material to ALL LOD levels
        materials_applied = 0
        for obj in self.imported_objects:
            try:
                # Quick validity check without expensive name lookup
                if obj.type != 'MESH' or not obj.data:
                    continue

                # Clear existing materials and apply the target material
                obj.data.materials.clear()
                obj.data.materials.append(target_material)
                materials_applied += 1
            except (AttributeError, ReferenceError):
                # Object was deleted or is invalid
                continue

        # Print removed to reduce console clutter

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
            try:
                # Quick validity check without expensive name lookup
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
            except (AttributeError, ReferenceError):
                # Object was deleted or is invalid
                continue

        # Step 2: Delete lower LODs
        for obj in objects_to_delete:
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
                self.imported_objects.remove(obj)
            except:
                pass

        # Step 3: Rename remaining objects
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
            else:
                # Handle simple format: _LOD0, _LOD1
                import re
                new_name = re.sub(r'_?LOD\d+', f'_LOD{new_lod}', old_name)
                if new_name != old_name:
                    obj.name = new_name
                    set_ioi_lod_properties(obj, new_lod)

    def _cleanup_unused_materials(self):
        """Remove all materials that are not being used by any imported objects."""
        import bpy

        # Step 1: Find which materials are currently in use by imported objects
        materials_in_use = set()
        for obj in self.imported_objects:
            try:
                # Quick validity check without expensive name lookup
                if obj.type != 'MESH' or not obj.data:
                    continue

                # Collect all materials used by this object
                for mat_slot in obj.data.materials:
                    if mat_slot:
                        materials_in_use.add(mat_slot.name)
            except (AttributeError, ReferenceError):
                # Object was deleted or is invalid
                continue

        # Material tracking prints removed to reduce console clutter

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
                    # Print removed to reduce console clutter
            except ReferenceError:
                # Material already deleted, skip
                pass
            except Exception as e:
                # Print removed to reduce console clutter
                pass

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
                    # Print removed to reduce console clutter
            except ReferenceError:
                # Material already deleted, skip
                pass
            except Exception as e:
                # Print removed to reduce console clutter
                pass

        # Cleanup summary prints removed to reduce console clutter

    def _show_only_lowest_lod(self):
        """Show all LOD levels in viewport after accepting import."""
        import bpy
        from ..operations.asset_processor import extract_lod_from_object_name

        # Find all LOD levels in imported objects
        lod_levels = set()
        for obj in self.imported_objects:
            try:
                # Quick validity check without expensive name lookup
                if obj.type != 'MESH' or not obj.data:
                    continue

                lod_level = extract_lod_from_object_name(obj.name)
                lod_levels.add(lod_level)
            except (AttributeError, ReferenceError):
                # Object was deleted or is invalid
                continue

        if not lod_levels:
            # Print removed to reduce console clutter
            return

        # Visibility prints removed to reduce console clutter

        # Show all LODs using the eye icon
        for obj in self.imported_objects:
            try:
                # Quick validity check without expensive name lookup
                if obj.type != 'MESH' or not obj.data:
                    continue

                lod_level = extract_lod_from_object_name(obj.name)

                # Show all LODs using eye icon (hide_set) - instant local visibility
                obj.hide_set(False)
            except (AttributeError, ReferenceError):
                # Object was deleted or is invalid
                continue

        # Print removed to reduce console clutter

    def _handle_cancel(self, button):
        """Handle Cancel button click."""
        import bpy

        # Cancel any pending LOD timer
        if self.pending_lod_timer is not None:
            if bpy.app.timers.is_registered(self.pending_lod_timer):
                bpy.app.timers.unregister(self.pending_lod_timer)
            self.pending_lod_timer = None
            self.target_lod = None
            self.lod_loading_state = False
            if self.lod_slider:
                self.lod_slider.set_loading_state(False)

        # Restore HDRI and viewport state to original
        if self.hdri_enabled:
            # Turn off HDRI toggle
            if self.hdri_toggle:
                self.hdri_toggle._toggled = False
            self.hdri_enabled = False
            # Restore original world
            self._restore_world_background()
            # Restore original viewport shading
            self._set_viewport_shading(False)

        # Close HDRI panel if open
        if self.hdri_panel_visible:
            self.hdri_panel_visible = False
            if self.hdri_panel:
                self.hdri_panel.visible = False

        # Reset stored viewport states for next time toolbar is used
        self.previous_shading_type = None
        self.previous_use_scene_world = None
        self.previous_render_engine = None
        self.previous_use_raytracing = None
        self.previous_ray_tracing_method = None
        self.previous_ray_tracing_resolution = None
        self.previous_fast_gi = None
        self.previous_use_shadows = None

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
            except Exception as e:
                pass

    def set_imported_data(self, objects, materials, materials_before, original_scene=None, temp_scene=None):
        """Store references to imported data for cleanup.

        Args:
            objects: List of imported Blender objects
            materials: List of created materials
            materials_before: Set of material names before import
            original_scene: Optional reference to original scene
            temp_scene: Optional reference to temporary preview scene
        """
        import bpy
        from ..operations.asset_processor import extract_lod_from_object_name

        self.imported_objects = objects
        self.imported_materials = materials
        self.materials_before_import = materials_before
        self.original_scene = original_scene
        self.temp_scene = temp_scene

        # OPTIMIZED: Extract attach roots from imported objects
        # Attach roots already have LOD organization built in during import!
        # No need to loop through objects or reorganize anything
        self.attach_roots = []
        for obj in objects:
            try:
                # Validate object reference before accessing properties
                if obj is None:
                    continue
                if obj.name not in bpy.data.objects:
                    continue
                if bpy.data.objects[obj.name] != obj:
                    continue
                if obj.get("ioiAttachRootNode"):
                    self.attach_roots.append(obj)
            except (ReferenceError, AttributeError, KeyError):
                # Object reference is invalid, skip it
                continue

        # Attach root summary prints removed to reduce console clutter

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
            # Default to lowest LOD
            self.selected_lod_level = self.lod_levels[0] if self.lod_levels else 0

        # Update LOD slider with available LODs
        if self.lod_slider and self.lod_levels:
            self.lod_slider.set_available_lods(self.lod_levels)
            # Pass object's maximum LOD to slider
            max_lod = max(self.lod_levels)
            self.lod_slider.set_object_max_lod(max_lod)
            # Set slider to lowest available LOD
            lowest_lod = self.lod_levels[0] if self.lod_levels else 0
            self.lod_slider.set_value(lowest_lod)
            self.current_preview_lod = lowest_lod
            self.lod_slider_label_text = f"LOD{lowest_lod}"

            # Initialize min/max markers on slider
            self._update_slider_minmax_markers()
    
    def set_max_lod(self, max_lod):
        """Set the max LOD dropdown to the specified LOD level.
        
        Args:
            max_lod: Maximum LOD level (0-7)
        """
        if not self.max_lod_dropdown:
            print(f"⚠️ [TOOLBAR] Max LOD dropdown not initialized")
            return
        
        # Clamp max_lod to valid range (0-7)
        max_lod = max(0, min(7, int(max_lod)))
        
        # Find the index for this LOD level
        target_item = f"LOD{max_lod}"
        items = self.max_lod_dropdown._items
        
        if target_item in items:
            index = items.index(target_item)
            self.max_lod_dropdown._selected_index = index
            self.selected_max_lod = max_lod
        else:
            # Fallback to closest available LOD
            if max_lod <= 7:
                # Use the max_lod as index directly (since items are LOD0-LOD7)
                self.max_lod_dropdown._selected_index = max_lod
                self.selected_max_lod = max_lod
        
        # Trigger the change handler to update slider
        if self.max_lod_dropdown.on_change:
            self.max_lod_dropdown.on_change(target_item)

    def _update_slider_minmax_markers(self):
        """Update the slider's min/max LOD markers based on dropdown selections."""
        if not self.lod_slider:
            return

        # Ensure object max LOD is set if lod_levels is available
        if self.lod_levels and self.lod_slider._object_max_lod is None:
            max_lod = max(self.lod_levels)
            self.lod_slider.set_object_max_lod(max_lod)

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

        # Validate: min_lod should not be greater than max_lod
        if min_lod > max_lod:
            min_lod, max_lod = max_lod, min_lod

        # Update slider markers
        self.lod_slider.set_min_max_lods(min_lod, max_lod)
        # Also update Auto LOD state
        self.lod_slider.set_auto_lod_enabled(self.auto_lod_enabled)

    def _on_lod_selection_changed(self, selected_text):
        """Handle min LOD dropdown selection change - update text colors and markers."""
        import re
        import bpy

        # Extract LOD number from selected text (e.g., "LOD2" -> 2)
        match = re.search(r'LOD(\d+)', selected_text)
        if match:
            selected_lod = int(match.group(1))
            self.selected_lod_level = selected_lod

            # Get current minLOD to determine which text objects should have their colors updated
            # Only update colors for LODs >= minLOD (LODs below minLOD should keep their original colors)
            min_lod = 0
            if self.min_lod_dropdown:
                min_lod_text = self.min_lod_dropdown.get_selected_item()
                if min_lod_text:
                    min_match = re.search(r'LOD(\d+)', min_lod_text)
                    if min_match:
                        min_lod = int(min_match.group(1))

            # Update slider min/max markers
            self._update_slider_minmax_markers()

            # Update text object colors - but only for LODs >= minLOD
            # LODs below minLOD should keep their original colors (they're hidden anyway)
            for item in self.lod_text_objects:
                try:
                    # Handle tuple (text_obj, lod_level, total_tris) or (text_obj, lod_level) or just text_obj
                    if isinstance(item, tuple) and len(item) >= 2:
                        text_obj = item[0]
                        lod_level = item[1]  # This is the Quixel LOD
                    else:
                        # Try to extract LOD from name if not a tuple
                        text_obj = item
                        name_match = re.search(r'LOD(\d+)', text_obj.name)
                        lod_level = int(name_match.group(1)) if name_match else 0

                    # Skip color update for LODs below minLOD - they should keep their original colors
                    if lod_level < min_lod:
                        continue

                    # Quick validity check without expensive name lookup
                    text_data = text_obj.data
                    # Clear existing materials
                    text_data.materials.clear()

                    # Apply new color based on LOD hierarchy
                    # Compare Quixel LODs (both lod_level and selected_lod are Quixel LODs)
                    # Selected = White (no blue), Below selected (lower numbers) = Black, Above selected (higher numbers) = White
                    if lod_level == selected_lod:
                        # White for selected (removed blue)
                        text_data.materials.append(self._get_or_create_text_material("LOD_Selected", (1.0, 1.0, 1.0, 1.0)))
                    elif lod_level < selected_lod:
                        # Almost black for LODs with lower numbers (worse quality)
                        text_data.materials.append(self._get_or_create_text_material("LOD_Below", (0.15, 0.15, 0.15, 1.0)))
                    else:
                        # Almost white for LODs with higher numbers (better quality)
                        text_data.materials.append(self._get_or_create_text_material("LOD_Above", (0.9, 0.9, 0.9, 1.0)))
                except:
                    pass
            
            # Immediately update visibility and text labels when minLOD changes
            self.update_lod_visibility()
            self._update_lod_text_labels()
            self._update_slider_labels()  # Update slider Quixel LOD labels

    def _on_max_lod_changed(self, selected_text):
        """Handle max LOD dropdown selection change - update markers."""
        # Update slider min/max markers
        self._update_slider_minmax_markers()
        # Update text labels with Quixel LOD info (maxLOD might affect display)
        self._update_lod_text_labels()
        self._update_slider_labels()  # Update slider Quixel LOD labels

    def position_lods_for_preview(self):
        """Position LODs in Y direction with 1m gap and create text labels showing LOD level and polycount."""
        import bpy
        from ..operations.asset_processor import extract_lod_from_object_name

        # Header prints removed to reduce console clutter

        # Group objects by attach root (variation), then by LOD level
        # This ensures each variation's LODs are positioned independently
        variations = {}
        for obj in self.imported_objects:
            try:
                # Quick validity check without expensive name lookup
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
            except (AttributeError, ReferenceError):
                # Object was deleted or is invalid
                continue

        # Variation count print removed to reduce console clutter

        # Process each variation independently
        for variation_name in sorted(variations.keys()):
            lods_by_level = variations[variation_name]

            # Processing variation print removed to reduce console clutter

            # Calculate position once for LOD0 (first LOD in sorted order) and reuse for all LODs
            sorted_lod_levels = sorted(lods_by_level.keys())
            lod0_position_offsets = None  # Will store (x_offset, y_offset, z_offset) relative to parent
            lod0_parent = None
            lod0_text_size = None

            for lod_level in sorted_lod_levels:
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
                # LOD position print removed to reduce console clutter

                # Create text object showing LOD level and polycount
                text_data = bpy.data.curves.new(name=f"{variation_name}_LOD{lod_level}_Label", type='FONT')
                text_data.body = f"LOD{lod_level}\n{total_tris:,} tris"
                text_data.align_x = 'CENTER'
                text_data.align_y = 'BOTTOM'
                text_data.size = text_size  # Text size based on mesh size

                text_obj = bpy.data.objects.new(name=f"{variation_name}_LOD{lod_level}_Label", object_data=text_data)

                # Rotate text 90 degrees on X axis (to face upward/toward camera)
                text_obj.rotation_euler.x = math.radians(90)

                # Set text color based on LOD hierarchy
                # Selected = White (no blue), Below selected (lower numbers) = Black, Above selected (higher numbers) = White
                selected_lod = self.selected_lod_level if self.selected_lod_level is not None else 0
                if lod_level == selected_lod:
                    # White color for selected LOD (removed blue)
                    text_data.materials.append(self._get_or_create_text_material("LOD_Selected", (1.0, 1.0, 1.0, 1.0)))
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
                        # For LOD0 (first LOD), calculate and store position offsets
                        if lod0_position_offsets is None:
                            # Calculate position relative to parent for LOD0
                            lod0_parent = first_obj.parent
                            lod0_text_size = text_size
                            x_offset = center_x - first_obj.parent.location.x
                            y_offset = center_y - first_obj.parent.location.y
                            z_offset = max_z - first_obj.parent.location.z + text_size * 1.5
                            lod0_position_offsets = (x_offset, y_offset, z_offset)
                        
                        # Use stored position offsets for all LODs (calculated once for LOD0)
                        text_obj.parent = lod0_parent
                        text_obj.location.x = lod0_position_offsets[0]
                        text_obj.location.y = lod0_position_offsets[1]
                        text_obj.location.z = lod0_position_offsets[2]
                        
                        # Link to the same collections as the mesh objects (which are in attach root collections)
                        if first_obj.users_collection:
                            for collection in first_obj.users_collection:
                                collection.objects.link(text_obj)
                        else:
                            # Fallback to context collection if mesh has no collections
                            bpy.context.collection.objects.link(text_obj)
                    else:
                        # No parent, use world space
                        # For LOD0, calculate and store position
                        if lod0_position_offsets is None:
                            lod0_text_size = text_size
                            x_offset = center_x
                            y_offset = center_y
                            z_offset = max_z + text_size * 1.5 if max_z is not None else text_size * 1.5
                            lod0_position_offsets = (x_offset, y_offset, z_offset)
                        
                        # Use stored position for all LODs
                        text_obj.location.x = lod0_position_offsets[0]
                        text_obj.location.y = lod0_position_offsets[1]
                        text_obj.location.z = lod0_position_offsets[2]
                        
                        # Link to the same collections as the mesh objects
                        if first_obj.users_collection:
                            for collection in first_obj.users_collection:
                                collection.objects.link(text_obj)
                        else:
                            # Fallback to context collection if mesh has no collections
                            bpy.context.collection.objects.link(text_obj)
                else:
                    # No objects found, fallback to context collection
                    bpy.context.collection.objects.link(text_obj)

                # Store text object for later cleanup (with LOD level info and tris count)
                self.lod_text_objects.append((text_obj, lod_level, total_tris))

                # Label creation print removed to reduce console clutter

        # Positioning summary print removed to reduce console clutter

        # Initialize visibility: show only LOD0 by default
        # Visibility initialization print removed to reduce console clutter
        self.update_lod_visibility()
        # Update text labels with Quixel LOD info
        self._update_lod_text_labels()

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
            bsdf.inputs["Emission Strength"].default_value = 10.0
            bsdf.inputs["Emission Color"].default_value = color

        return mat

    def _update_lod_text_labels(self):
        """Update text labels to show Quixel LOD info for currently visible LOD."""
        # Get min LOD for Quixel LOD calculation
        min_lod = 0
        if self.min_lod_dropdown:
            min_lod_text = self.min_lod_dropdown.get_selected_item()
            if min_lod_text:
                import re
                match = re.search(r'LOD(\d+)', min_lod_text)
                if match:
                    min_lod = int(match.group(1))
        
        # Get max LOD
        max_lod = 5  # Default
        if self.max_lod_dropdown:
            max_lod_text = self.max_lod_dropdown.get_selected_item()
            if max_lod_text:
                import re
                match = re.search(r'LOD(\d+)', max_lod_text)
                if match:
                    max_lod = int(match.group(1))
        
        # Calculate Quixel LOD for currently previewed LOD
        # Formula: quixel_lod = min_lod + preview_position
        quixel_lod = min_lod + self.current_preview_lod
        
        # Check if this LOD needs auto-generation
        # Only mark as auto-generated if within minLOD to maxLOD range
        needs_auto_generation = False
        if self.auto_lod_enabled and min_lod is not None and max_lod is not None:
            # Only check if within the minLOD to maxLOD range
            if min_lod <= quixel_lod <= max_lod:
                # Check if this Quixel LOD is not in available LODs (needs auto-generation)
                if self.lod_levels:
                    needs_auto_generation = (quixel_lod not in self.lod_levels)
                else:
                    needs_auto_generation = True
        
        # Update text for currently visible LOD
        # Map preview LOD to Quixel LOD: quixel_lod = min_lod + current_preview_lod
        target_quixel_lod = quixel_lod  # This is the Quixel LOD we want to show
        
        import bpy
        
        # Hide text objects for LODs below minLOD (they should not be visible at all)
        # Also show text objects that are now within range (if minLOD decreased)
        for item in self.lod_text_objects:
            try:
                if isinstance(item, tuple) and len(item) >= 2:
                    text_obj = item[0]
                    text_quixel_lod = item[1]
                    # Hide text objects for Quixel LODs below minLOD
                    if text_quixel_lod < min_lod:
                        text_obj.hide_set(True)
                    # Note: We don't explicitly show objects here - visibility is handled by update_lod_visibility()
                    # which will show the correct text object based on target_quixel_lod
            except (AttributeError, ReferenceError):
                continue
        
        # Now update the visible text objects (only those >= minLOD)
        # First, hide all text objects that don't match the target LOD (same logic as update_lod_visibility)
        import bpy
        if self.lod_text_objects:
            for item in self.lod_text_objects:
                try:
                    # Handle tuple (text_obj, lod_level, total_tris) or (text_obj, lod_level)
                    if isinstance(item, tuple) and len(item) >= 2:
                        text_obj = item[0]
                        text_quixel_lod = item[1]  # This is the Quixel LOD stored with the text object
                    else:
                        continue
                    
                    # Always hide text objects below minLOD (regardless of target_quixel_lod)
                    if text_quixel_lod < min_lod:
                        text_obj.hide_set(True)
                        text_obj.hide_viewport = True
                        continue

                    # Match by Quixel LOD, not preview LOD position
                    should_hide = (text_quixel_lod != target_quixel_lod)
                    text_obj.hide_set(should_hide)
                    text_obj.hide_viewport = should_hide
                except (AttributeError, ReferenceError):
                    continue
        
        # Check if text object exists for target LOD
        text_obj = None
        text_quixel_lod = None
        total_tris = 0
        lod_exists = False
        
        # First, check if the LOD actually exists in available LODs (not just if text object exists)
        # This determines if we need to show "??? tris" (LOD needs generation) or actual count
        actual_lod_exists = (target_quixel_lod in self.lod_levels) if self.lod_levels else False
        
        for item in self.lod_text_objects:
            try:
                # Handle tuple (text_obj, lod_level, total_tris) or (text_obj, lod_level)
                if isinstance(item, tuple) and len(item) >= 2:
                    temp_text_obj = item[0]
                    temp_quixel_lod = item[1]  # This is the Quixel LOD stored with the text object
                    temp_total_tris = item[2] if len(item) >= 3 else 0
                else:
                    continue
                
                # Match by Quixel LOD, not preview LOD position
                if temp_quixel_lod == target_quixel_lod:
                    text_obj = temp_text_obj
                    text_quixel_lod = temp_quixel_lod
                    total_tris = temp_total_tris
                    lod_exists = True
                    break
            except (AttributeError, ReferenceError):
                continue
        
        # If LOD doesn't exist, create text objects for ALL variations (not just one)
        if not lod_exists:
            import math
            preview_lod_display = self.current_preview_lod
            
            # Group existing text objects by variation to find reference for each variation
            # Text objects are named like: {variation_name}_LOD{lod_level}_Label
            variations_with_text = {}
            for item in self.lod_text_objects:
                try:
                    if isinstance(item, tuple) and len(item) >= 2:
                        ref_obj = item[0]
                        ref_quixel_lod = item[1]
                        # Extract variation name from text object name
                        ref_name = ref_obj.name
                        if "_LOD" in ref_name and "_Label" in ref_name:
                            variation_name = ref_name.split("_LOD")[0]
                            # Store reference text object for this variation (prefer LOD0)
                            if variation_name not in variations_with_text:
                                variations_with_text[variation_name] = None
                            # Prefer LOD0 as reference, otherwise use first available
                            if ref_quixel_lod == 0 or (variations_with_text[variation_name] is None and ref_quixel_lod >= min_lod):
                                variations_with_text[variation_name] = ref_obj
                except (AttributeError, ReferenceError):
                    continue
            
            # If no variations found in text objects, try to find variations from attach roots
            if not variations_with_text and self.attach_roots:
                for attach_root in self.attach_roots:
                    # Try to find a text object that belongs to this attach root's variation
                    # Look for text objects that are children of this attach root or in same collections
                    for item in self.lod_text_objects:
                        try:
                            if isinstance(item, tuple) and len(item) >= 2:
                                ref_obj = item[0]
                                # Check if text object is related to this attach root
                                if ref_obj.parent == attach_root or any(coll in attach_root.users_collection for coll in ref_obj.users_collection):
                                    ref_name = ref_obj.name
                                    if "_LOD" in ref_name and "_Label" in ref_name:
                                        variation_name = ref_name.split("_LOD")[0]
                                        if variation_name not in variations_with_text:
                                            variations_with_text[variation_name] = ref_obj
                                            break
                        except (AttributeError, ReferenceError):
                            continue
            
            # Create text object for each variation
            created_any = False
            for variation_name, reference_text_obj in variations_with_text.items():
                if reference_text_obj is None or not reference_text_obj.data:
                    continue
                
                reference_text_data = reference_text_obj.data
                
                # Create text object for missing LOD for this variation
                text_data = bpy.data.curves.new(name=f"{variation_name}_LOD{target_quixel_lod}_Label", type='FONT')
                text_data.body = f"LOD{preview_lod_display}\n??? tris"
                text_data.align_x = 'CENTER'
                text_data.align_y = 'BOTTOM'
                text_data.size = reference_text_data.size
                
                text_obj_name = f"{variation_name}_LOD{target_quixel_lod}_Label"
                text_obj = bpy.data.objects.new(name=text_obj_name, object_data=text_data)
                
                # Link to the same collections as the reference text object
                if reference_text_obj.users_collection:
                    for collection in reference_text_obj.users_collection:
                        collection.objects.link(text_obj)
                else:
                    # Fallback to context collection if reference has no collections
                    bpy.context.collection.objects.link(text_obj)
                
                # Position at same location as reference text object
                text_obj.parent = reference_text_obj.parent
                text_obj.location.x = reference_text_obj.location.x
                text_obj.location.y = reference_text_obj.location.y
                text_obj.location.z = reference_text_obj.location.z
                text_obj.rotation_euler.x = math.radians(90)
                
                # Set text color
                # Compare Quixel LODs, not preview LOD positions, to fix color issue when minLOD > 0
                text_data.materials.clear()
                selected_lod_quixel = self.selected_lod_level if self.selected_lod_level is not None else 0
                # Compare target_quixel_lod (current) with selected_lod_quixel (selected) - both are Quixel LODs
                if target_quixel_lod == selected_lod_quixel:
                    text_data.materials.append(self._get_or_create_text_material("LOD_Selected", (1.0, 1.0, 1.0, 1.0)))
                elif target_quixel_lod < selected_lod_quixel:
                    text_data.materials.append(self._get_or_create_text_material("LOD_Below", (0.15, 0.15, 0.15, 1.0)))
                else:
                    text_data.materials.append(self._get_or_create_text_material("LOD_Above", (0.9, 0.9, 0.9, 1.0)))
                
                # Make it visible
                text_obj.hide_set(False)
                text_obj.hide_viewport = False
                
                # Store in lod_text_objects for future reference
                self.lod_text_objects.append((text_obj, target_quixel_lod, 0))
                created_any = True
            
            # If we created text objects, we need to find the one for the current variation to update
            if created_any:
                # Find the text object we just created (or use the first one if we can't determine variation)
                for item in self.lod_text_objects:
                    try:
                        if isinstance(item, tuple) and len(item) >= 2:
                            temp_text_obj = item[0]
                            temp_quixel_lod = item[1]
                            if temp_quixel_lod == target_quixel_lod:
                                text_obj = temp_text_obj
                                text_quixel_lod = temp_quixel_lod
                                total_tris = 0
                                lod_exists = True
                                break
                    except (AttributeError, ReferenceError):
                        continue
            else:
                return
        
        # Now update ALL text objects for the target LOD (for all variations)
        # Find all text objects matching the target Quixel LOD
        text_objects_to_update = []
        for item in self.lod_text_objects:
            try:
                if isinstance(item, tuple) and len(item) >= 2:
                    temp_text_obj = item[0]
                    temp_quixel_lod = item[1]
                    temp_total_tris = item[2] if len(item) >= 3 else 0
                    if temp_quixel_lod == target_quixel_lod:
                        text_objects_to_update.append((temp_text_obj, temp_total_tris))
            except (AttributeError, ReferenceError):
                continue
        
        # Update all text objects for this LOD
        preview_lod_display = self.current_preview_lod
        selected_lod_quixel = self.selected_lod_level if self.selected_lod_level is not None else 0
        
        for text_obj_to_update, obj_total_tris in text_objects_to_update:
            if not text_obj_to_update or not text_obj_to_update.data:
                continue
            
            text_data = text_obj_to_update.data
            import bpy
            import math
            
            # Update main text body
            # Display preview LOD position, not Quixel LOD
            # Use actual_lod_exists to determine if we show "??? tris" (LOD needs generation)
            # If LOD doesn't exist in available LODs, show "??? tris" even if text object exists
            if actual_lod_exists:
                text_data.body = f"LOD{preview_lod_display}\n{obj_total_tris:,} tris"
            else:
                text_data.body = f"LOD{preview_lod_display}\n??? tris"
            
            # Remove blue coloring - use normal white/gray based on hierarchy
            # Compare Quixel LODs, not preview LOD positions, to fix color issue when minLOD > 0
            text_data.materials.clear()
            # Compare target_quixel_lod (current) with selected_lod_quixel (selected) - both are Quixel LODs
            if target_quixel_lod == selected_lod_quixel:
                # Use white instead of blue for selected
                text_data.materials.append(self._get_or_create_text_material("LOD_Selected", (1.0, 1.0, 1.0, 1.0)))
            elif target_quixel_lod < selected_lod_quixel:
                text_data.materials.append(self._get_or_create_text_material("LOD_Below", (0.15, 0.15, 0.15, 1.0)))
            else:
                text_data.materials.append(self._get_or_create_text_material("LOD_Above", (0.9, 0.9, 0.9, 1.0)))
        

    def _delete_text_labels(self):
        """Delete all LOD text labels."""
        import bpy

        deleted_count = 0
        for item in list(self.lod_text_objects):
            try:
                # Handle both tuple (text_obj, lod_level) and just text_obj
                text_obj = item[0] if isinstance(item, tuple) else item

                # Quick validity check without expensive name lookup
                bpy.data.objects.remove(text_obj, do_unlink=True)
                deleted_count += 1
            except (ReferenceError, AttributeError):
                # Text object already deleted or invalid, skip it
                pass
            except Exception as e:
                print(f"  ⚠️  Error deleting text object: {e}")

        # Print removed to reduce console clutter

        # Clear the list
        self.lod_text_objects.clear()

    def reset_lod_positions_and_cleanup(self):
        """Reset LOD positions to original and delete text labels."""
        import bpy

        # Header prints removed to reduce console clutter

        # Reset object positions
        reset_count = 0
        for obj in self.imported_objects:
            try:
                # Quick validity check without expensive name lookup
                # Restore original position if we stored it
                if obj.name in self.lod_original_positions:
                    original_pos = self.lod_original_positions[obj.name]
                    obj.location = original_pos.copy()
                    reset_count += 1
            except (ReferenceError, AttributeError):
                # Object has been deleted or is invalid, skip it
                pass
            except Exception as e:
                # Print removed to reduce console clutter
                pass

        # Print removed to reduce console clutter

        # Delete text objects using helper method
        self._delete_text_labels()

        # Clear the tracking dictionary
        self.lod_original_positions.clear()

        # Print removed to reduce console clutter

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

        # Draw LOD slider label (two lines)
        if hasattr(self, 'lod_slider_label_x'):
            # Calculate line height and spacing
            blf.size(0, 12)  # Top line size
            top_text_height = blf.dimensions(0, self.lod_slider_label_text)[1]
            line_spacing = 4  # Space between lines

            # Draw top line (Preview LOD) - WHITE
            top_y = self.lod_slider_label_y + line_spacing / 2
            blf.position(0, self.lod_slider_label_x, top_y, 0)
            blf.color(0, 1.0, 1.0, 1.0, 1.0)  # White
            blf.draw(0, self.lod_slider_label_text)

            # Draw bottom line (Quixel LOD or Status) - DARK GRAY
            blf.size(0, 10)  # Slightly smaller for bottom line

            # Build bottom text - show status if missing, otherwise show Quixel LOD
            if self.lod_slider_status_text:
                bottom_text = self.lod_slider_status_text
            else:
                bottom_text = self.lod_slider_quixel_label_text

            # Always calculate height based on a consistent reference to avoid position shift
            # Use the Quixel LOD text for consistent height calculation
            reference_text_height = blf.dimensions(0, self.lod_slider_quixel_label_text)[1]
            bottom_y = self.lod_slider_label_y - line_spacing / 2 - reference_text_height

            blf.position(0, self.lod_slider_label_x, bottom_y, 0)
            blf.color(0, 0.6, 0.6, 0.6, 1.0)  # Dark gray
            blf.draw(0, bottom_text)

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

        # Draw floor toggle button
        if self.floor_toggle:
            self.floor_toggle.draw()

        # Draw wireframe toggle button
        if self.wireframe_toggle:
            self.wireframe_toggle.draw()

        # Draw HDRI toggle button
        if self.hdri_toggle:
            self.hdri_toggle.draw()

        # Draw HDRI dropdown button
        if self.hdri_dropdown_button:
            self.hdri_dropdown_button.draw()

        # ========================================
        # HDRI PANEL (drawn on top of everything)
        # ========================================
        # Draw HDRI panel if visible
        if self.hdri_panel and self.hdri_panel_visible:
            self.hdri_panel.draw()

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

        # Check HDRI panel first (if visible, it's on top)
        if self.hdri_panel_visible and self.hdri_panel:
            if self.hdri_panel.mouse_down(x, y):
                return True
            # Click outside HDRI panel - close it
            if not self._is_point_in_hdri_panel(x, y):
                # Also check if clicking on the HDRI buttons themselves
                is_on_hdri_button = False
                if self.hdri_toggle and self.hdri_toggle.is_in_rect(x, y):
                    is_on_hdri_button = True
                if self.hdri_dropdown_button and self.hdri_dropdown_button.is_in_rect(x, y):
                    is_on_hdri_button = True

                # Only close if not clicking on HDRI buttons
                if not is_on_hdri_button:
                    self._close_hdri_panel()
                    # Don't consume the event, let it pass through

        # Check top toolbar widgets
        if self.lod_slider and self.lod_slider.mouse_down(x, y):
            return True
        if self.floor_toggle and self.floor_toggle.mouse_down(x, y):
            return True
        if self.wireframe_toggle and self.wireframe_toggle.mouse_down(x, y):
            return True
        if self.hdri_toggle and self.hdri_toggle.mouse_down(x, y):
            return True
        if self.hdri_dropdown_button and self.hdri_dropdown_button.mouse_down(x, y):
            return True

        # Check dropdowns (they might be expanded)
        # Close other dropdowns before opening a new one
        if self.min_lod_dropdown and self.min_lod_dropdown.is_in_rect(x, y):
            # Close all other dropdowns before opening this one
            self._close_all_dropdowns(exclude_dropdown=self.min_lod_dropdown)
            if self.min_lod_dropdown.mouse_down(x, y):
                return True
        elif self.max_lod_dropdown and self.max_lod_dropdown.is_in_rect(x, y):
            # Close all other dropdowns before opening this one
            self._close_all_dropdowns(exclude_dropdown=self.max_lod_dropdown)
            if self.max_lod_dropdown.mouse_down(x, y):
                return True
        else:
            # Clicked outside both dropdown buttons
            # Let dropdowns handle their own mouse_down (they'll close themselves if open and clicked outside)
            # But also close other dropdowns when one is handling a click
            if self.min_lod_dropdown and self.min_lod_dropdown.mouse_down(x, y):
                # If min dropdown handled the click, close max dropdown
                self._close_all_dropdowns(exclude_dropdown=self.min_lod_dropdown)
                return True
            if self.max_lod_dropdown and self.max_lod_dropdown.mouse_down(x, y):
                # If max dropdown handled the click, close min dropdown
                self._close_all_dropdowns(exclude_dropdown=self.max_lod_dropdown)
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

        # Check HDRI panel first (if visible)
        if self.hdri_panel_visible and self.hdri_panel:
            if self.hdri_panel.mouse_up(x, y):
                return True

        # Check top toolbar widgets
        if self.lod_slider and self.lod_slider.mouse_up(x, y):
            return True
        if self.floor_toggle and self.floor_toggle.mouse_up(x, y):
            return True
        if self.wireframe_toggle and self.wireframe_toggle.mouse_up(x, y):
            return True
        if self.hdri_toggle and self.hdri_toggle.mouse_up(x, y):
            return True
        if self.hdri_dropdown_button and self.hdri_dropdown_button.mouse_up(x, y):
            return True

        # Check action buttons
        if self.accept_button and self.accept_button.mouse_up(x, y):
            return True
        if self.cancel_button and self.cancel_button.mouse_up(x, y):
            return True
        return False

    def handle_mouse_move(self, x, y):
        """Handle mouse move events for hover effects.

        Returns:
            bool: True if dragging (should consume event), False otherwise
        """
        if not self.visible:
            return False

        # Handle HDRI panel hover (if visible)
        if self.hdri_panel_visible and self.hdri_panel:
            self.hdri_panel.mouse_move(x, y)

        # Handle top toolbar hover/drag states
        is_dragging = False
        if self.lod_slider:
            self.lod_slider.mouse_move(x, y)
            # Check if slider is currently dragging
            if hasattr(self.lod_slider, '_is_dragging'):
                is_dragging = self.lod_slider._is_dragging

        if self.floor_toggle:
            self.floor_toggle.mouse_move(x, y)
        if self.wireframe_toggle:
            self.wireframe_toggle.mouse_move(x, y)

        if self.bridge_button:
            self.bridge_button.mouse_move(x, y)

        if self.hdri_toggle:
            self.hdri_toggle.mouse_move(x, y)

        if self.hdri_dropdown_button:
            self.hdri_dropdown_button.mouse_move(x, y)

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

        return is_dragging
