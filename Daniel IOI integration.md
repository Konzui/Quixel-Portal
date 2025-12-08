# Daniel IOI Integration Documentation

This document describes how the Quixel Portal Blender addon integrates with the IOI (IO Interactive) Glacier engine workflow, including project structure, attach root logic, object properties, and collision implementation guidance.

## Table of Contents

1. [Project Overview](#project-overview)
2. [Project Structure](#project-structure)
3. [How the Project Works](#how-the-project-works)
4. [Attach Roots Logic](#attach-roots-logic)
5. [Object Properties Setup](#object-properties-setup)
6. [Collision Implementation Guide](#collision-implementation-guide)

---

## Project Overview

The Quixel Portal addon is a Blender addon that:
- Connects to Quixel Bridge via socket communication (port 24981)
- Automatically imports Quixel Megascans assets into Blender
- Organizes assets with proper IOI-compatible naming, properties, and hierarchy
- Creates attach root nodes compatible with the IOI Glacier engine workflow
- Sets up LOD (Level of Detail) properties for efficient rendering

### IOI Integration Goals

The addon is designed to prepare assets for export to the IOI Glacier engine by:
1. Creating attach root nodes with proper IOI properties
2. Setting LOD properties on objects (IoiIsLODLevel{i}Member)
3. Renaming objects to IOI naming convention (base_name_LOD_0_______)
4. Organizing variations with proper spacing
5. Maintaining proper object hierarchy for game engine export

---

## Project Structure

The addon is organized into several key modules:

```
Quixel Portal/
├── __init__.py                 # Addon registration and entry point
├── main.py                     # Main workflow orchestration
├── communication/              # Quixel Bridge communication layer
│   ├── quixel_bridge_socket.py # Socket listener (port 24981)
│   ├── bridge_client.py        # Multi-instance client support
│   └── bridge_coordinator.py  # Multi-instance coordination
├── operations/                 # Business logic layer
│   ├── fbx_importer.py        # FBX file import operations
│   ├── material_creator.py    # Material creation from textures
│   ├── asset_processor.py     # Object organization & attach root creation
│   └── name_corrector.py      # Object name correction
├── utils/                      # Helper utilities
│   ├── naming.py              # Naming conventions & JSON parsing
│   ├── texture_loader.py      # Texture loading utilities
│   ├── validation.py          # Path and asset validation
│   └── scene_manager.py       # Scene management
└── ui/                         # User interface
    ├── operators.py           # Blender operators
    ├── import_modal.py        # Import confirmation modal
    └── import_toolbar.py     # Custom bottom toolbar UI
```

### Key Modules for IOI Integration

**`operations/asset_processor.py`** - Core IOI integration logic:
- Creates attach root nodes
- Sets IOI LOD properties
- Organizes object hierarchy
- Calculates bounding boxes for spacing

**`main.py`** - Workflow orchestration:
- Coordinates the entire import process
- Calls asset processor functions in correct order
- Manages scene setup and cleanup

---

## How the Project Works

### Import Workflow

The import process follows these steps:

```
1. Quixel Bridge Export
   ↓ (sends JSON via socket to port 24981)
2. Socket Listener (communication/quixel_bridge_socket.py)
   ↓ (parses JSON and queues import request)
3. Main Flow (main.py::import_asset())
   ↓
4. Asset Type Detection (operations/asset_processor.py::detect_asset_type())
   ↓
5. FBX Import (operations/fbx_importer.py)
   ↓
6. Name Correction (operations/name_corrector.py)
   ↓
7. IOI Properties Setup (operations/asset_processor.py::set_ioi_lod_properties())
   ↓
8. Variation Organization (operations/asset_processor.py::organize_objects_by_variation())
   ↓
9. Material Creation (operations/material_creator.py)
   ↓
10. Attach Root Creation (operations/asset_processor.py::create_asset_hierarchy())
    ↓
11. Preview Toolbar (ui/import_toolbar.py)
```

### Data Flow

1. **Socket Communication**: Quixel Bridge sends JSON data containing asset path, name, and resolution
2. **Import Queue**: Socket listener queues import requests for main thread processing
3. **FBX Import**: All FBX files are imported into Blender
4. **Processing**: Objects are organized by variation, LOD levels are detected, and names are corrected
5. **IOI Setup**: IOI properties are set on all objects, and objects are renamed to IOI format
6. **Hierarchy Creation**: Attach roots are created for each variation with proper spacing
7. **Preview**: User sees preview toolbar with LOD controls before accepting import

### Key Functions

**Main Entry Point**: `main.py::import_asset()`
- Orchestrates entire import process
- Handles both FBX assets and surface materials
- Manages preview scene creation and cleanup

**IOI Properties**: `operations/asset_processor.py::set_ioi_lod_properties()`
- Sets `IoiIsLODLevel{i}Member` properties (i = 0-7)
- Renames objects to IOI format: `base_name_LOD_0_______`
- Stores LOD level as custom property

**Attach Root Creation**: `operations/asset_processor.py::create_asset_hierarchy()`
- Creates empty objects (attach roots) for each variation
- Sets IOI attach root properties
- Parents all variation objects to attach roots
- Positions variations with spacing

---

## Attach Roots Logic

### What Are Attach Roots?

Attach roots are empty Blender objects that serve as parent nodes for asset variations. They are required for IOI Glacier engine export and provide:
- A single point of reference for each variation
- Proper object hierarchy for game engine
- IOI-compatible naming and properties
- Efficient LOD organization

### Current Implementation

**Location**: `operations/asset_processor.py::create_asset_hierarchy()`

**What It Does**:

1. **Calculates Bounding Boxes**: Before creating attach roots, calculates bounding boxes for all variations to determine spacing
   ```python
   bbox = calculate_variation_bbox(variation_objects)
   ```

2. **Creates Attach Root Objects**: Creates empty objects with proper naming
   ```python
   attach_root = bpy.data.objects.new(attach_root_name, None)
   attach_root.empty_display_type = 'ARROWS'
   attach_root.empty_display_size = 1.0
   ```

3. **Sets IOI Properties**: Adds IOI-compatible custom properties
   ```python
   attach_root["ioiAttachRootNode"] = bool(True)
   attach_root["IoiG2ObjectType"] = str("static")
   attach_root["IoiGizmoSize"] = attach_root.empty_display_size * 100
   ```

4. **Organizes LOD Data**: Stores LOD organization on attach root for efficient access
   ```python
   attach_root["lod_levels"] = sorted(list(lod_levels_set))
   attach_root["variation_suffix"] = variation_suffix
   attach_root[f"lod_{lod_level}_objects"] = ",".join(obj_names)
   ```

5. **Positions Variations**: Spaces variations along Y-axis with 1-meter margin
   ```python
   attach_root.location.y = current_y_offset
   current_y_offset += bbox['height'] + margin  # margin = 1.0
   ```

6. **Parents Objects**: All variation objects become children of attach root
   ```python
   obj.parent = attach_root
   ```

### How to Modify Attach Root Logic

#### Changing Spacing Between Variations

**Location**: `operations/asset_processor.py::create_asset_hierarchy()`, around line 426

**Current spacing**:
```python
margin = 1.0  # Fixed 1 meter margin between variations
current_y_offset += bbox['height'] + margin
```

**Example: Change to 2 meters**:
```python
margin = 2.0  # Changed from 1.0 to 2.0
```

**Example: Percentage-based spacing**:
```python
margin_percent = 0.5  # 50% of height
current_y_offset += bbox['height'] * (1 + margin_percent)
```

#### Changing Positioning Direction

**Current**: Variations are spaced along Y-axis (vertical stacking)

**Example: Stack horizontally (X-axis)**:
```python
# Change from:
attach_root.location.y = current_y_offset
current_y_offset += bbox['height'] + margin

# To:
attach_root.location.x = current_x_offset
current_x_offset += bbox['width'] + margin
```

**Example: Arrange in grid**:
```python
grid_cols = 2
col = len(created_attach_roots) % grid_cols
row = len(created_attach_roots) // grid_cols

attach_root.location.x = col * (max_width + margin)
attach_root.location.y = row * (max_height + margin)
```

#### Adding Custom Properties to Attach Roots

**Location**: `operations/asset_processor.py::create_asset_hierarchy()`, after line 454

**Example: Add bounding box data**:
```python
attach_root["bbox_width"] = bbox['width']
attach_root["bbox_height"] = bbox['height']
attach_root["bbox_depth"] = bbox['depth']
attach_root["bbox_min_x"] = bbox['min_x']
attach_root["bbox_max_x"] = bbox['max_x']
```

**Example: Add variation metadata**:
```python
attach_root["variation_index"] = variation_index
attach_root["asset_name"] = attach_root_base_name
attach_root["object_count"] = len(variation_objects)
```

#### Modifying Attach Root Naming

**Location**: `operations/asset_processor.py::create_asset_hierarchy()`, around line 435

**Current naming**: `{attach_root_base_name}_{variation_suffix}`

**Example: Add LOD to name**:
```python
# Get LOD from first object in variation
first_obj = variation_objects[0]
lod_level = extract_lod_from_object_name(first_obj.name)
attach_root_name = f"{attach_root_base_name}_{variation_suffix}_LOD{lod_level}"
```

**Example: Custom naming scheme**:
```python
attach_root_name = f"Root_Variation{variation_suffix.upper()}"
```

### Accessing Attach Root Data

**In Blender Python Console**:
```python
import bpy

# Find all attach roots
attach_roots = [obj for obj in bpy.data.objects if obj.get("ioiAttachRootNode")]

# Access properties
for root in attach_roots:
    print(f"Root: {root.name}")
    print(f"  Variation: {root.get('variation_suffix')}")
    print(f"  LOD Levels: {root.get('lod_levels')}")
    print(f"  Gizmo Size: {root.get('IoiGizmoSize')}")
    
    # Get objects for a specific LOD
    lod_0_objects = root.get("lod_0_objects", "").split(",")
    print(f"  LOD 0 Objects: {lod_0_objects}")
```

---

## Object Properties Setup

### IOI LOD Properties

All mesh objects are automatically set up with IOI-compatible LOD properties during import.

**Location**: `operations/asset_processor.py::set_ioi_lod_properties()`

**What It Does**:

1. **Sets LOD Level Properties**: Sets `IoiIsLODLevel{i}Member` for levels 0-7
   ```python
   for i in range(8):
       prop_name = f"IoiIsLODLevel{str(i)}Member"
       if i == lod_level:
           obj[prop_name] = bool(True)
       else:
           obj[prop_name] = bool(False)
   ```

2. **Renames to IOI Format**: Converts object names to IOI naming convention
   - Input: `AssetName_00_LOD0`
   - Output: `AssetName_00_LOD_0_______`
   - Format: `base_name_LOD_` followed by 8 characters (number for active LOD, underscores for inactive)

3. **Stores Metadata**: Stores LOD level and variation as custom properties
   ```python
   obj["lod_level"] = lod_level
   obj["variation_index"] = variation_index
   obj["is_quixel_import"] = True
   ```

### Custom Properties on Objects

**Standard Properties** (set automatically):
- `lod_level` (int): LOD level (0-7)
- `variation_index` (int): Variation index (0, 1, 2, ...)
- `is_quixel_import` (bool): Marks object as imported by Quixel Portal
- `IoiIsLODLevel{i}Member` (bool): IOI LOD membership flags (i = 0-7)

### How to Add Custom Properties

**Location**: `operations/asset_processor.py::set_ioi_lod_properties()` or `process_object_single_pass()`

**Example: Add collision type property**:
```python
# In set_ioi_lod_properties() or process_object_single_pass()
obj["IoiCollisionType"] = str("static")  # or "dynamic", "kinematic"
obj["IoiCollisionEnabled"] = bool(True)
```

**Example: Add export flags**:
```python
obj["IoiExportEnabled"] = bool(True)
obj["IoiCastShadows"] = bool(True)
obj["IoiReceiveShadows"] = bool(True)
```

**Example: Add material properties**:
```python
obj["IoiMaterialOverride"] = str("")  # Empty = use assigned material
obj["IoiMaterialTint"] = (1.0, 1.0, 1.0, 1.0)  # RGBA tint
```

### Property Access Patterns

**In Blender Python Console**:
```python
import bpy

# Find all Quixel-imported objects
quixel_objects = [obj for obj in bpy.data.objects 
                   if obj.get("is_quixel_import")]

# Access LOD properties
for obj in quixel_objects:
    lod_level = obj.get("lod_level", 0)
    variation = obj.get("variation_index", 0)
    
    # Check IOI LOD membership
    is_lod0 = obj.get("IoiIsLODLevel0Member", False)
    is_lod1 = obj.get("IoiIsLODLevel1Member", False)
    
    print(f"{obj.name}: LOD {lod_level}, Variation {variation}")
```

**In Scripts**:
```python
# Check if object is part of LOD level
def is_object_in_lod(obj, lod_level):
    prop_name = f"IoiIsLODLevel{lod_level}Member"
    return obj.get(prop_name, False)

# Get all objects for a specific LOD
def get_objects_for_lod(attach_root, lod_level):
    prop_name = f"lod_{lod_level}_objects"
    obj_names = attach_root.get(prop_name, "").split(",")
    return [bpy.data.objects[name] for name in obj_names if name in bpy.data.objects]
```

---

## Collision Implementation Guide

### Overview

Currently, the addon does **not** automatically create collision meshes. This section describes how collision could be implemented and where to add the logic.

### Collision Types in IOI Glacier

IOI Glacier typically supports:
- **Static Collision**: Non-moving objects (buildings, terrain)
- **Dynamic Collision**: Moving objects (props, vehicles)
- **Kinematic Collision**: Objects that move but don't respond to physics
- **Trigger Volumes**: Non-physical collision for events

### Where to Implement Collision

#### Option 1: During Import (Recommended)

**Location**: `operations/asset_processor.py::create_asset_hierarchy()` or new function `create_collision_meshes()`

**Implementation Steps**:

1. **Create new function** in `operations/asset_processor.py`:
   ```python
   def create_collision_meshes(variation_objects, attach_root, context):
       """Create collision meshes for a variation.
       
       Args:
           variation_objects: List of mesh objects in the variation
           attach_root: Parent attach root object
           context: Blender context
           
       Returns:
           list: Created collision mesh objects
       """
       collision_objects = []
       
       for obj in variation_objects:
           if obj.type != 'MESH' or not obj.data:
               continue
           
           # Create collision mesh (simplified version of original)
           collision_mesh = obj.data.copy()
           collision_obj = bpy.data.objects.new(f"{obj.name}_Collision", collision_mesh)
           
           # Set collision properties
           collision_obj["IoiCollisionType"] = str("static")
           collision_obj["IoiCollisionEnabled"] = bool(True)
           collision_obj["IoiIsCollisionMesh"] = bool(True)
           
           # Link to scene
           context.collection.objects.link(collision_obj)
           
           # Parent to attach root
           collision_obj.parent = attach_root
           
           # Copy transform from original object
           collision_obj.location = obj.location.copy()
           collision_obj.rotation_euler = obj.rotation_euler.copy()
           collision_obj.scale = obj.scale.copy()
           
           collision_objects.append(collision_obj)
       
       return collision_objects
   ```

2. **Call from create_asset_hierarchy()**:
   ```python
   # After parenting variation objects to attach root (around line 500)
   # Create collision meshes
   collision_objects = create_collision_meshes(variation_objects, attach_root, context)
   
   # Store collision objects on attach root
   attach_root["collision_objects"] = ",".join([obj.name for obj in collision_objects])
   ```

#### Option 2: Post-Import Operator

**Location**: `ui/operators.py` - Create new operator

**Implementation**:
```python
class QUIXEL_OT_create_collision(bpy.types.Operator):
    """Create collision meshes for selected attach roots."""
    bl_idname = "quixel.create_collision"
    bl_label = "Create Collision Meshes"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        from ..operations.asset_processor import create_collision_meshes
        
        # Get selected attach roots
        selected = [obj for obj in context.selected_objects 
                   if obj.get("ioiAttachRootNode")]
        
        for attach_root in selected:
            # Get all children (variation objects)
            variation_objects = [child for child in attach_root.children 
                                if child.type == 'MESH']
            
            # Create collision meshes
            create_collision_meshes(variation_objects, attach_root, context)
        
        return {'FINISHED'}
```

### Collision Mesh Simplification

For better performance, collision meshes should be simplified versions of the original geometry.

**Implementation**:
```python
def create_simplified_collision_mesh(original_obj, decimate_ratio=0.1):
    """Create a simplified collision mesh from original object.
    
    Args:
        original_obj: Original mesh object
        decimate_ratio: Ratio of faces to keep (0.1 = 10% of faces)
        
    Returns:
        bpy.types.Mesh: Simplified mesh data
    """
    # Create mesh copy
    collision_mesh = original_obj.data.copy()
    
    # Create object with mesh
    collision_obj = bpy.data.objects.new(f"{original_obj.name}_Collision", collision_mesh)
    bpy.context.collection.objects.link(collision_obj)
    
    # Select and make active
    bpy.ops.object.select_all(action='DESELECT')
    collision_obj.select_set(True)
    bpy.context.view_layer.objects.active = collision_obj
    
    # Enter edit mode and decimate
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.decimate(ratio=decimate_ratio)
    bpy.ops.object.mode_set(mode='OBJECT')
    
    return collision_mesh
```

### Collision Properties

**Required IOI Properties**:
```python
# On collision mesh objects
obj["IoiCollisionType"] = str("static")  # or "dynamic", "kinematic"
obj["IoiCollisionEnabled"] = bool(True)
obj["IoiIsCollisionMesh"] = bool(True)

# Optional properties
obj["IoiCollisionMaterial"] = str("default")  # Physics material
obj["IoiCollisionFriction"] = 0.5  # Friction coefficient
obj["IoiCollisionRestitution"] = 0.0  # Bounciness (0-1)
```

### Collision Mesh Organization

**Option 1: Separate Objects**
- Each variation object gets its own collision mesh
- Collision meshes are siblings of original objects under attach root

**Option 2: Combined Collision**
- Single collision mesh per variation (combines all objects)
- More efficient but less flexible

**Implementation for Combined Collision**:
```python
def create_combined_collision_mesh(variation_objects, attach_root, context):
    """Create a single combined collision mesh for all variation objects."""
    import bmesh
    
    # Create new mesh
    collision_mesh = bpy.data.meshes.new(f"{attach_root.name}_Collision")
    bm = bmesh.new()
    
    # Add geometry from all objects
    for obj in variation_objects:
        if obj.type != 'MESH' or not obj.data:
            continue
        
        # Get world matrix
        world_matrix = obj.matrix_world
        
        # Create bmesh from object
        obj_bm = bmesh.new()
        obj_bm.from_mesh(obj.data)
        obj_bm.transform(world_matrix)
        
        # Merge into main bmesh
        bmesh.ops.join(bm, [obj_bm], [bm.verts[0] if bm.verts else None])
    
    # Update mesh
    bm.to_mesh(collision_mesh)
    bm.free()
    
    # Create object
    collision_obj = bpy.data.objects.new(f"{attach_root.name}_Collision", collision_mesh)
    context.collection.objects.link(collision_obj)
    collision_obj.parent = attach_root
    
    # Set properties
    collision_obj["IoiCollisionType"] = str("static")
    collision_obj["IoiCollisionEnabled"] = bool(True)
    collision_obj["IoiIsCollisionMesh"] = bool(True)
    
    return collision_obj
```

### Integration Points Summary

**Where to add collision logic**:

1. **During Import** (Automatic):
   - `operations/asset_processor.py::create_asset_hierarchy()` - After line 500
   - Create collision meshes for each variation automatically

2. **Post-Import** (Manual):
   - `ui/operators.py` - New operator `QUIXEL_OT_create_collision`
   - User can manually create collision for selected attach roots

3. **Toolbar Integration** (UI):
   - `ui/import_toolbar.py` - Add collision toggle button
   - Allow user to enable/disable collision during preview

### Recommended Implementation Order

1. **Phase 1**: Basic collision mesh creation
   - Create simplified collision meshes during import
   - Set basic IOI collision properties

2. **Phase 2**: Collision options
   - Add user preferences for collision settings
   - Allow choosing between separate or combined collision

3. **Phase 3**: Advanced features
   - Collision mesh simplification with decimation
   - Collision material assignment
   - Trigger volume support

---

## Summary

### Key Files for IOI Integration

- **Attach Roots**: `operations/asset_processor.py::create_asset_hierarchy()`
- **IOI Properties**: `operations/asset_processor.py::set_ioi_lod_properties()`
- **Object Processing**: `operations/asset_processor.py::process_object_single_pass()`
- **Main Workflow**: `main.py::_import_fbx_asset()`

### Customization Points

1. **Attach Root Spacing**: Modify `margin` variable in `create_asset_hierarchy()`
2. **Attach Root Properties**: Add custom properties after line 454
3. **Object Properties**: Modify `set_ioi_lod_properties()` or `process_object_single_pass()`
4. **Collision**: Create new function `create_collision_meshes()` and call from `create_asset_hierarchy()`

### Testing Your Changes

1. Import a test asset from Quixel Bridge
2. Check attach root properties in Blender Python console:
   ```python
   import bpy
   roots = [obj for obj in bpy.data.objects if obj.get("ioiAttachRootNode")]
   for root in roots:
       print(root.name, root.get("lod_levels"))
   ```
3. Verify object properties:
   ```python
   objs = [obj for obj in bpy.data.objects if obj.get("is_quixel_import")]
   for obj in objs[:5]:  # Check first 5
       print(obj.name, obj.get("lod_level"), obj.get("IoiIsLODLevel0Member"))
   ```

---

*Last Updated: Based on current codebase structure*

