# Custom UI Toolbar Documentation

This document describes how the custom UI toolbar at the bottom of the screen works, including widget architecture, button creation, event handling, and rendering system.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Widget System](#widget-system)
4. [Button Creation](#button-creation)
5. [Event Handling](#event-handling)
6. [Rendering System](#rendering-system)
7. [Toolbar Implementation](#toolbar-implementation)
8. [Customization Guide](#customization-guide)

---

## Overview

The custom UI toolbar is a GPU-based overlay system that displays at the bottom of the 3D viewport during asset import. It provides:

- **Accept/Cancel buttons** for confirming or discarding imports
- **LOD controls** (slider, dropdowns) for switching between detail levels
- **Wireframe toggle** for preview mode
- **HDRI selection** for environment lighting
- **Smooth anti-aliased rendering** using custom GPU shaders

### Key Features

- **Non-blocking UI**: Renders as overlay, doesn't block Blender operations
- **GPU-accelerated**: Uses Blender's GPU module for fast rendering
- **Custom shaders**: Anti-aliased rendering with smooth edges
- **Event-driven**: Mouse and keyboard event handling
- **Widget-based**: Modular widget system for reusable UI components

---

## Architecture

### File Structure

**Location**: `ui/import_toolbar.py`

**Key Components**:

```
import_toolbar.py
├── DrawConstants (class)          # Shader and batch caching
├── BL_UI_Widget (base class)     # Base widget with position/event handling
├── BL_UI_Button (widget)          # Button with hover/pressed states
├── BL_UI_Dropdown (widget)       # Dropdown menu for LOD selection
├── BL_UI_Checkbox (widget)       # Checkbox for toggles
├── BL_UI_ToggleButton (widget)   # Toggle button (wireframe, etc.)
├── BL_UI_Slider (widget)         # Slider for LOD control
├── BL_UI_HDRIThumbnailButton     # HDRI preview button
├── BL_UI_HDRIPanel               # HDRI selection panel
└── ImportToolbar (container)      # Main toolbar that manages all widgets
```

### Registration System

The toolbar is registered as a Blender draw handler:

**Location**: `ui/import_modal.py::show_import_toolbar()`

```python
# Register draw handler
bpy.types.SpaceView3D.draw_handler_add(
    toolbar.draw,
    (),
    'WINDOW',
    'POST_PIXEL'
)
```

**Draw Handler Type**: `POST_PIXEL` - Draws after all 3D viewport content, ensuring toolbar is always on top.

---

## Widget System

### Base Widget Class

**Class**: `BL_UI_Widget`

**Purpose**: Base class for all UI widgets, providing:
- Position tracking (x, y, width, height)
- Coordinate conversion (screen space)
- Hit testing (is_in_rect)
- Basic drawing (rounded rectangle background)

**Key Methods**:

```python
class BL_UI_Widget:
    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y
        self.x_screen = x  # Screen-space X
        self.y_screen = y  # Screen-space Y
        self.width = width
        self.height = height
        self.visible = True
    
    def init(self, context):
        """Initialize with context (gets area height for coordinate conversion)"""
        self.area_height = context.area.height
        self.update(self.x, self.y)
    
    def update(self, x, y):
        """Update widget position"""
        self.x_screen = x
        self.y_screen = y
    
    def is_in_rect(self, x, y):
        """Check if point (x, y) is inside widget bounds"""
        return (self.x_screen <= x <= (self.x_screen + self.width) and
                self.y_screen <= y <= (self.y_screen + self.height))
    
    def draw(self):
        """Draw widget background (rounded rectangle)"""
        draw_rounded_rect(
            self.x_screen, self.y_screen,
            self.width, self.height,
            8,  # Corner radius
            self._bg_color
        )
```

### Widget Hierarchy

All widgets inherit from `BL_UI_Widget`:

```
BL_UI_Widget (base)
├── BL_UI_Button
├── BL_UI_Dropdown
├── BL_UI_Checkbox
├── BL_UI_ToggleButton
├── BL_UI_Slider
├── BL_UI_HDRIThumbnailButton
└── BL_UI_HDRIPanel
```

---

## Button Creation

### Basic Button

**Class**: `BL_UI_Button`

**States**:
- `0` = Normal (default appearance)
- `1` = Pressed (mouse down)
- `2` = Hover (mouse over)

**Creating a Button**:

```python
# Create button
accept_button = BL_UI_Button(x=100, y=50, width=120, height=40)

# Set text
accept_button.text = "Accept"
accept_button.text_size = 14
accept_button.text_color = (1.0, 1.0, 1.0, 1.0)

# Set colors
accept_button._normal_bg_color = (0.25, 0.25, 0.25, 0.9)
accept_button._hover_bg_color = (0.3, 0.5, 0.7, 0.95)
accept_button._pressed_bg_color = (0.2, 0.4, 0.6, 1.0)

# Set callback
def on_accept_click(button):
    print("Accept clicked!")
    # Handle accept logic

accept_button.set_mouse_up(on_accept_click)

# Initialize with context
accept_button.init(context)
```

### Button Drawing

Buttons are drawn with:
1. **Rounded rectangle background** (4px corner radius)
2. **State-based color** (normal/hover/pressed)
3. **Centered text** using Blender's font rendering (BLF)

**Drawing Process**:

```python
def draw(self):
    # 1. Get color based on state
    color = self.get_button_color()
    
    # 2. Draw rounded rectangle background
    draw_rounded_rect(
        self.x_screen, self.y_screen,
        self.width, self.height,
        4,  # Corner radius
        color
    )
    
    # 3. Draw text
    self.draw_text(area_height)
```

### Button Text Rendering

Text is rendered using Blender's Font API (BLF):

```python
def draw_text(self, area_height):
    # Set font size
    blf.size(0, self._text_size)
    
    # Get text dimensions
    text_width, text_height = blf.dimensions(0, self._text)
    
    # Calculate centered position
    text_x = self.x_screen + (self.width - text_width) / 2.0
    text_y = self.y_screen + (self.height / 2) - (text_height / 2)
    
    # Set position and color
    blf.position(0, text_x, text_y, 0)
    blf.color(0, r, g, b, a)
    
    # Draw text
    blf.draw(0, self._text)
```

---

## Event Handling

### Mouse Events

Widgets handle three mouse events:

1. **mouse_down(x, y)**: Mouse button pressed
2. **mouse_up(x, y)**: Mouse button released
3. **mouse_move(x, y)**: Mouse moved (for hover)

**Button Event Handling**:

```python
def mouse_down(self, x, y):
    """Handle mouse down - set pressed state"""
    if self.is_in_rect(x, y):
        self.__state = 1  # Pressed
        return True
    return False

def mouse_up(self, x, y):
    """Handle mouse up - trigger callback if clicked"""
    if self.is_in_rect(x, y):
        self.__state = 2  # Hover
        if self.mouse_up_func:
            self.mouse_up_func(self)  # Call callback
        return True
    else:
        self.__state = 0  # Normal
    return False

def mouse_move(self, x, y):
    """Handle mouse move - update hover state"""
    if self.is_in_rect(x, y):
        if self.__state != 1:  # Not pressed
            self.__state = 2  # Hover
    else:
        self.__state = 0  # Normal
```

### Event Registration

Events are registered in the toolbar's modal operator:

**Location**: `ui/import_modal.py`

```python
def modal(self, context, event):
    # Get mouse position in region space
    mouse_x = event.mouse_region_x
    mouse_y = event.mouse_region_y
    
    # Handle mouse events
    if event.type == 'LEFTMOUSE':
        if event.value == 'PRESS':
            # Pass to all widgets
            for widget in self.toolbar.widgets:
                widget.mouse_down(mouse_x, mouse_y)
        elif event.value == 'RELEASE':
            for widget in self.toolbar.widgets:
                widget.mouse_up(mouse_x, mouse_y)
    
    elif event.type == 'MOUSEMOVE':
        # Update hover states
        for widget in self.toolbar.widgets:
            widget.mouse_move(mouse_x, mouse_y)
    
    return {'RUNNING_MODAL'}
```

### Keyboard Events

Keyboard events are handled in the modal operator:

```python
def modal(self, context, event):
    # ESC key cancels
    if event.type == 'ESC':
        self.toolbar._handle_cancel(None)
        return {'CANCELLED'}
    
    # Enter key accepts
    if event.type == 'RET':
        self.toolbar._handle_accept(None)
        return {'FINISHED'}
    
    return {'RUNNING_MODAL'}
```

---

## Rendering System

### GPU-Based Rendering

The toolbar uses Blender's GPU module for fast, hardware-accelerated rendering:

**Key Modules**:
- `gpu` - GPU state and shaders
- `gpu_extras.batch_for_shader` - Batch creation for efficient drawing
- `blf` - Blender Font Library for text rendering

### Shader System

**DrawConstants Class**: Caches shaders and batches for efficient rendering

**Pre-computed Shaders**:
- `filled_circle_shader` - Filled circles (buttons, checkboxes)
- `anti_aliased_circle_shader` - Anti-aliased circles (smooth edges)
- `anti_aliased_rect_shader` - Anti-aliased rectangles (smooth edges)
- `anti_aliased_arc_shader` - Anti-aliased arcs (rounded corners)

**Shader Initialization**:

```python
class DrawConstants:
    @classmethod
    def initialize(cls):
        """Initialize all shaders and batches once"""
        if cls.filled_circle_shader is None:
            # Create shader
            cls.uniform_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            
            # Create circle batch (64 segments for smooth circle)
            segments = 64
            vertices = [(0, 0)]  # Center
            for i in range(segments + 1):
                angle = 2 * math.pi * i / segments
                vertices.append((math.cos(angle), math.sin(angle)))
            
            # Create indices for triangles
            indices = []
            for i in range(segments):
                indices.append((0, i + 1, i + 2))
            
            cls.filled_circle_batch = batch_for_shader(
                cls.uniform_shader, 'TRIS',
                {"pos": vertices},
                indices=indices
            )
```

### Rounded Rectangle Drawing

**Function**: `draw_rounded_rect(x, y, width, height, radius, color)`

**How It Works**:

1. **Draw four corner circles** (anti-aliased)
2. **Draw horizontal strip** (between top and bottom circles)
3. **Draw vertical strips** (left and right sides)

**Implementation**:

```python
def draw_rounded_rect(x, y, width, height, radius, color):
    # Initialize shaders
    DrawConstants.initialize()
    
    # Enable alpha blending
    gpu.state.blend_set('ALPHA')
    
    # Draw four corner circles
    corners = [
        (x + radius, y + radius),              # Bottom-left
        (x + width - radius, y + radius),      # Bottom-right
        (x + width - radius, y + height - radius),  # Top-right
        (x + radius, y + height - radius)      # Top-left
    ]
    
    for cx, cy in corners:
        # Draw anti-aliased circle
        draw_anti_aliased_circle(cx, cy, radius, color)
    
    # Draw horizontal strip (between top and bottom circles)
    draw_rect(x + radius, y, width - 2*radius, height, color)
    
    # Draw vertical strips (left and right)
    draw_rect(x, y + radius, radius, height - 2*radius, color)
    draw_rect(x + width - radius, y + radius, radius, height - 2*radius, color)
    
    gpu.state.blend_set('NONE')
```

### Anti-Aliasing

Anti-aliasing is achieved using custom fragment shaders with distance-based alpha falloff:

**Fragment Shader Example** (for circles):

```glsl
uniform vec4 color;
uniform vec2 center;
uniform float radius;
uniform float edgeSoftness;

void main() {
    // Calculate distance from center
    float dist = distance(screenPos, center);
    
    // Use smoothstep for soft edge anti-aliasing
    float alpha = 1.0 - smoothstep(
        radius - edgeSoftness,
        radius + edgeSoftness,
        dist
    );
    
    fragColor = vec4(color.rgb, color.a * alpha);
}
```

**Benefits**:
- Smooth edges at any resolution
- No pixelation or jagged edges
- Professional appearance

---

## Toolbar Implementation

### ImportToolbar Class

**Location**: `ui/import_toolbar.py::ImportToolbar`

**Purpose**: Container class that manages all widgets and coordinates drawing/events

**Key Properties**:

```python
class ImportToolbar:
    def __init__(self):
        # Buttons
        self.accept_button = None
        self.cancel_button = None
        
        # LOD controls
        self.lod_slider = None
        self.min_lod_dropdown = None
        self.max_lod_dropdown = None
        self.show_all_checkbox = None
        
        # Other controls
        self.wireframe_toggle = None
        self.hdri_panel = None
        
        # State
        self.visible = False
        self.lod_levels = []
        self.selected_min_lod = None
        self.selected_max_lod = 5
        
        # Callbacks
        self.on_accept = None
        self.on_cancel = None
```

### Toolbar Setup

**Creating the Toolbar**:

```python
def setup_toolbar(self, context):
    """Create and position all widgets"""
    
    # Get viewport dimensions
    area = context.area
    region = context.region
    width = region.width
    height = 60  # Toolbar height
    
    # Calculate position (centered at bottom)
    x = (width - toolbar_width) / 2
    y = 20  # 20px from bottom
    
    # Create Accept button
    self.accept_button = BL_UI_Button(
        x=x, y=y,
        width=120, height=40
    )
    self.accept_button.text = "Accept"
    self.accept_button.set_mouse_up(self._handle_accept)
    self.accept_button.init(context)
    
    # Create Cancel button
    self.cancel_button = BL_UI_Button(
        x=x + 130, y=y,  # 10px gap
        width=120, height=40
    )
    self.cancel_button.text = "Cancel"
    self.cancel_button.set_mouse_up(self._handle_cancel)
    self.cancel_button.init(context)
    
    # Create LOD slider
    self.lod_slider = BL_UI_Slider(
        x=x + 260, y=y + 10,
        width=200, height=20
    )
    self.lod_slider.set_change_callback(self._handle_slider_change)
    self.lod_slider.init(context)
    
    # ... create other widgets
```

### Toolbar Drawing

**Drawing Process**:

```python
def draw(self):
    """Draw all widgets"""
    if not self.visible:
        return
    
    # Draw background bar (optional)
    draw_rounded_rect(
        0, 0,  # Full width
        self.area_width, 60,
        0,  # No corner radius for full-width bar
        (0.1, 0.1, 0.1, 0.9)  # Dark background
    )
    
    # Draw all widgets
    if self.accept_button:
        self.accept_button.draw()
    
    if self.cancel_button:
        self.cancel_button.draw()
    
    if self.lod_slider:
        self.lod_slider.draw()
    
    # ... draw other widgets
```

### Widget List Management

For efficient event handling, widgets are stored in a list:

```python
def get_all_widgets(self):
    """Get all widgets for event handling"""
    widgets = []
    
    if self.accept_button:
        widgets.append(self.accept_button)
    if self.cancel_button:
        widgets.append(self.cancel_button)
    if self.lod_slider:
        widgets.append(self.lod_slider)
    # ... add other widgets
    
    return widgets
```

---

## Customization Guide

### Adding a New Button

**Step 1: Create the button**:

```python
# In ImportToolbar.setup_toolbar()
self.my_button = BL_UI_Button(
    x=500, y=50,
    width=100, height=40
)
self.my_button.text = "My Button"
self.my_button.text_size = 12
self.my_button._normal_bg_color = (0.2, 0.2, 0.2, 0.9)
self.my_button._hover_bg_color = (0.3, 0.3, 0.3, 0.95)
self.my_button.set_mouse_up(self._handle_my_button)
self.my_button.init(context)
```

**Step 2: Add callback**:

```python
def _handle_my_button(self, button):
    """Handle my button click"""
    print("My button clicked!")
    # Your logic here
```

**Step 3: Add to draw method**:

```python
def draw(self):
    # ... existing drawing code ...
    if self.my_button:
        self.my_button.draw()
```

**Step 4: Add to widget list**:

```python
def get_all_widgets(self):
    widgets = []
    # ... existing widgets ...
    if self.my_button:
        widgets.append(self.my_button)
    return widgets
```

### Changing Button Colors

**Modify button color properties**:

```python
# Normal state
button._normal_bg_color = (0.25, 0.25, 0.25, 0.9)  # Dark gray

# Hover state
button._hover_bg_color = (0.3, 0.5, 0.7, 0.95)  # Blue

# Pressed state
button._pressed_bg_color = (0.2, 0.4, 0.6, 1.0)  # Darker blue

# Text color
button._text_color = (1.0, 1.0, 1.0, 1.0)  # White
```

### Changing Button Size

**Modify dimensions**:

```python
# In setup_toolbar()
button.width = 150  # Change width
button.height = 50   # Change height

# Update position if needed
button.update(new_x, new_y)
```

### Adding Custom Widget

**Create new widget class**:

```python
class BL_UI_MyWidget(BL_UI_Widget):
    """Custom widget"""
    
    def __init__(self, x, y, width, height):
        super().__init__(x, y, width, height)
        self._custom_property = None
    
    def draw(self):
        """Draw custom widget"""
        if not self.visible:
            return
        
        # Draw background
        super().draw()
        
        # Draw custom content
        # ... your drawing code ...
    
    def handle_event(self, event):
        """Handle custom events"""
        # ... your event handling ...
```

### Modifying Toolbar Position

**Change toolbar Y position**:

```python
# In setup_toolbar()
toolbar_y = 50  # 50px from bottom (instead of 20px)

# Update all widget positions
self.accept_button.update(x, toolbar_y)
self.cancel_button.update(x + 130, toolbar_y)
# ... update other widgets
```

### Adding Tooltips

**Implement tooltip system**:

```python
def draw_tooltip(self, widget, text):
    """Draw tooltip for widget"""
    if widget.is_in_rect(mouse_x, mouse_y):
        # Draw tooltip background
        tooltip_x = widget.x_screen
        tooltip_y = widget.y_screen + widget.height + 5
        
        draw_rounded_rect(
            tooltip_x, tooltip_y,
            tooltip_width, tooltip_height,
            4, (0.2, 0.2, 0.2, 0.9)
        )
        
        # Draw tooltip text
        blf.size(0, 11)
        blf.position(0, tooltip_x + 5, tooltip_y + 5, 0)
        blf.draw(0, text)
```

---

## Summary

### Key Concepts

1. **Widget System**: Modular, reusable UI components
2. **GPU Rendering**: Fast, hardware-accelerated drawing
3. **Event Handling**: Mouse and keyboard events
4. **Anti-Aliasing**: Smooth edges using custom shaders
5. **State Management**: Button states (normal/hover/pressed)

### File Locations

- **Widget Classes**: `ui/import_toolbar.py` (lines 615-2660)
- **Toolbar Container**: `ui/import_toolbar.py` (lines 3271-6073)
- **Modal Operator**: `ui/import_modal.py`
- **Registration**: `ui/import_modal.py::show_import_toolbar()`

### Common Tasks

- **Add Button**: Create `BL_UI_Button`, set callback, add to draw method
- **Change Colors**: Modify `_normal_bg_color`, `_hover_bg_color`, etc.
- **Add Widget**: Create new class inheriting from `BL_UI_Widget`
- **Handle Events**: Implement `mouse_down`, `mouse_up`, `mouse_move`

---

*Last Updated: Based on current codebase structure*

