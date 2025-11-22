# Developer Guide

This guide explains how to extend and modify the Quixel Portal addon.

## Quick Start

### Understanding the Structure

The addon is organized into layers:

1. **UI Layer** (`ui/`) - Blender operators (entry points)
2. **Main Layer** (`main.py`) - Workflow orchestration
3. **Operations Layer** (`operations/`) - Business logic
4. **Communication Layer** (`communication/`) - Electron IPC
5. **Utilities** (`utils/`) - Helper functions

### Key Principle

**You can modify or extend any layer without understanding the others!**

- Want to add OBJ import? Work in `operations/` - no need to understand Electron communication
- Want to change IPC protocol? Work in `communication/` - import logic stays the same
- Want to add UI elements? Work in `ui/` - business logic stays the same

## Common Tasks

### Adding a New Import Type (e.g., OBJ files)

**Step 1**: Create the importer module

Create `operations/obj_importer.py`:

```python
"""OBJ importer module for importing OBJ files."""

import bpy
from pathlib import Path

def find_obj_files(asset_dir):
    """Find all OBJ files in the asset directory."""
    asset_dir = Path(asset_dir)
    return list(asset_dir.glob("**/*.obj"))

def import_obj_file(filepath, context):
    """Import a single OBX file."""
    # Your import logic here
    pass
```

**Step 2**: Update `main.py`

In `main.py`, add detection and import logic:

```python
from .operations.obj_importer import find_obj_files, import_obj_file

def import_asset(asset_path, thumbnail_path=None, asset_name=None):
    # ... existing code ...
    
    # Detect asset type
    asset_type = detect_asset_type(asset_dir)
    
    if asset_type == 'obj':  # Add this
        return _import_obj_asset(asset_dir, materials_before_import, context, thumbnail_path, asset_name)
    elif asset_type == 'surface':
        # ... existing code ...
```

**Step 3**: Implement the import function

Add `_import_obj_asset()` function following the same pattern as `_import_fbx_asset()`.

**That's it!** No need to touch communication or UI layers.

### Modifying Material Creation

**Example**: Add support for a new texture type (e.g., "emission")

**Step 1**: Update texture identification

In `utils/texture_loader.py`, add to `identify_texture_type()`:

```python
def identify_texture_type(filename):
    filename_lower = str(filename).lower()
    
    # ... existing checks ...
    
    elif 'emission' in filename_lower or 'emissive' in filename_lower:
        return 'emission'
    
    return None
```

**Step 2**: Update material creation

In `operations/material_creator.py`, add to `create_material_from_textures()`:

```python
# Load Emission texture
if 'emission' in textures and textures['emission']:
    emission_node = load_texture(nodes, 'Emission', textures['emission'], 'sRGB')
    if emission_node:
        links.new(emission_node.outputs['Color'], bsdf.inputs['Emission'])
```

**Step 3**: Update texture finding

In `operations/material_creator.py`, add 'emission' to texture types list in `find_textures_for_variation()`.

### Changing Communication Protocol

**Example**: Change polling interval from 1 second to 0.5 seconds

**Location**: `communication/file_watcher.py`

```python
def check_import_requests():
    # ... existing code ...
    
    # Change this line:
    return 1.0  # Check every 1 second
    
    # To:
    return 0.5  # Check every 0.5 seconds
```

**That's it!** No other modules need to change.

### Adding New Utility Functions

**Example**: Add a function to calculate object bounding box

**Location**: `utils/validation.py` or create new `utils/geometry.py`

```python
def calculate_object_bbox(obj):
    """Calculate bounding box of a single object."""
    # Your implementation
    pass
```

Then import and use in any operation module:

```python
from ..utils.validation import calculate_object_bbox  # or utils.geometry
```

### Modifying UI

**Example**: Add a new operator for manual import

**Location**: `ui/operators.py`

```python
class QUIXEL_OT_manual_import(bpy.types.Operator):
    """Manually import an asset from file browser"""
    bl_idname = "quixel.manual_import"
    bl_label = "Manual Import"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    
    def execute(self, context):
        from ..main import import_asset
        return import_asset(self.filepath)
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
```

Then register in `__init__.py`:

```python
from ui.operators import QUIXEL_OT_manual_import

def register():
    # ... existing code ...
    bpy.utils.register_class(QUIXEL_OT_manual_import)
```

## Module Interaction Patterns

### Calling Operations from Main

```python
# In main.py
from .operations.fbx_importer import import_fbx_file

result = import_fbx_file(filepath, context)
```

### Calling Utilities from Operations

```python
# In operations/material_creator.py
from ..utils.texture_loader import load_texture

texture_node = load_texture(nodes, 'Albedo', texture_path)
```

### Calling Communication from Operations

```python
# In operations/portal_launcher.py
from ..communication.electron_bridge import launch_electron_app

success, error = launch_electron_app(instance_id)
```

### Calling Main from UI

```python
# In ui/operators.py
from ..main import import_asset

result = import_asset(asset_path, thumbnail_path, asset_name)
```

## Best Practices

### 1. Keep Functions Focused
Each function should do one thing well. If a function is doing multiple things, split it.

### 2. Use Type Hints (Optional but Recommended)
```python
def import_fbx_file(filepath: Path, context: bpy.types.Context) -> tuple[list, str | None]:
    """Import a single FBX file."""
    pass
```

### 3. Document Complex Logic
Add comments for non-obvious code:

```python
# CRITICAL: Apply transforms BEFORE parenting
# Bounding box calculations need correct transforms
apply_transforms(objects)
```

### 4. Follow Existing Patterns
When adding new functionality, follow the patterns used in similar modules:
- Import structure
- Error handling style
- Logging format
- Function naming

### 5. Test Incrementally
After making changes:
1. Test the specific functionality you modified
2. Test the full import workflow
3. Check Blender console for errors

## Debugging Tips

### Enable Console Output

In Blender: `Window > Toggle System Console` (Windows) or check terminal (Linux/Mac)

### Common Issues

**Import errors**: Check that all relative imports use `.` prefix
```python
# Correct
from ..utils.naming import get_name_from_json

# Wrong
from utils.naming import get_name_from_json
```

**Circular imports**: Use lazy imports or restructure
```python
# Lazy import (in function)
def some_function():
    from ..main import import_asset
    import_asset(...)
```

**Module not found**: Ensure `__init__.py` exists in all package directories

### Logging

The addon uses print statements for logging. Look for:
- `✅` - Success messages
- `⚠️` - Warnings
- `❌` - Errors
- `🔍` - Debug/process information

## File Locations Reference

| Purpose | Location |
|---------|----------|
| Add new import type | `operations/` |
| Modify material creation | `operations/material_creator.py` |
| Change communication | `communication/` |
| Add utilities | `utils/` |
| Modify UI | `ui/operators.py` |
| Change workflow | `main.py` |
| Addon registration | `__init__.py` |

## Example: Complete Feature Addition

Let's say you want to add support for importing GLTF files:

1. **Create importer**: `operations/gltf_importer.py`
   - `find_gltf_files(asset_dir)`
   - `import_gltf_file(filepath, context)`

2. **Update validation**: `utils/validation.py`
   - Add 'gltf' detection in `validate_asset_directory()`

3. **Update main flow**: `main.py`
   - Add `elif asset_type == 'gltf'` branch
   - Create `_import_gltf_asset()` function

4. **Test**: Import a GLTF asset and verify it works

**No changes needed to**:
- Communication layer
- UI layer (unless you want a GLTF-specific operator)
- Material creation (unless GLTF needs special handling)

## Getting Help

- Check `ARCHITECTURE.md` for system design
- Review existing code in similar modules
- Check Blender console for error messages
- Review function docstrings for usage

## Contributing

When adding features:
1. Follow existing code style
2. Add docstrings to new functions
3. Test thoroughly
4. Update documentation if needed

