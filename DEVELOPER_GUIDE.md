# Developer Guide

This guide explains how the Quixel Portal Blender addon works, how to navigate the codebase, and how to extend it with custom functionality.

## Table of Contents

1. [Project Overview](#project-overview)
2. [Project Structure](#project-structure)
3. [Quixel Bridge Communication](#quixel-bridge-communication)
4. [Function Location Guide](#function-location-guide)
5. [Extension Points](#extension-points)
6. [Import Workflow Walkthrough](#import-workflow-walkthrough)
7. [Code Examples](#code-examples)

---

## Project Overview

### What This Addon Does

The Quixel Portal addon integrates Quixel Bridge with Blender by:
- Listening for asset exports from Quixel Bridge via socket communication
- Automatically importing exported assets into Blender
- Organizing assets with proper materials, LODs, and variations

### High-Level Architecture

The addon consists of a single Python component:

1. **Python Addon** (Blender side)
   - Runs inside Blender
   - Handles asset import and processing
   - Communicates with Quixel Bridge via socket on port 24981

### Communication Method

The addon communicates with Quixel Bridge using **socket-based communication**:
- Python listens on `localhost:24981` for JSON data from Quixel Bridge
- Quixel Bridge sends JSON data when assets are exported
- No file-based IPC needed - direct socket communication

---

## Project Structure

### Directory Layout

```
Quixel Portal/
├── __init__.py                 # Addon entry point and registration
├── main.py                     # Main workflow orchestration
├── communication/              # Quixel Bridge communication
│   └── quixel_bridge_socket.py # Socket listener for Bridge communication
├── operations/                  # Business logic layer
│   ├── fbx_importer.py         # FBX file import
│   ├── material_creator.py     # Material creation from textures
│   ├── asset_processor.py      # Object organization and hierarchy
│   └── name_corrector.py       # Object name correction
├── utils/                       # Helper functions
│   ├── naming.py               # Naming conventions and JSON parsing
│   ├── texture_loader.py       # Texture loading utilities
│   ├── validation.py           # Path and asset validation
│   └── scene_manager.py        # Scene management utilities
├── ui/                          # Blender UI components
│   ├── operators.py            # Blender operators (UI entry points)
│   ├── import_modal.py         # Import confirmation modal
│   └── import_toolbar.py       # Import toolbar with LOD controls
└── assets/                      # Addon assets
    └── icons/                   # Icon files
```

### Module Responsibilities

#### `__init__.py` - Addon Registration
**Purpose**: Entry point that Blender calls when loading the addon

**What it does**:
- Registers Blender operators (UI buttons/commands)
- Starts socket listener for Quixel Bridge communication
- Starts background timer to check for pending imports
- Loads custom icons

**Key functions**:
- `register()`: Called when addon is enabled
- `unregister()`: Called when addon is disabled

**When to modify**: Only when adding new UI operators or changing registration logic

---

#### `main.py` - Workflow Orchestration
**Purpose**: High-level coordinator that orchestrates the entire import process

**What it does**:
- Receives import requests from socket listener
- Detects asset type (FBX vs surface material)
- Coordinates between different operation modules
- Manages the step-by-step import workflow

**Key functions**:
- `import_asset()`: Main entry point - starts the import process
- `_import_fbx_asset()`: Handles FBX asset import workflow

**Data flow**:
```
import_asset() 
  → detect_asset_type() 
  → _import_fbx_asset() 
    → import FBX files
    → correct names
    → apply transforms
    → organize by variation
    → create materials
    → create attach roots
```

**When to modify**: When changing the overall import workflow or adding new asset types

---

#### `communication/` - Quixel Bridge Communication Layer

##### `quixel_bridge_socket.py`
**Purpose**: Socket communication with Quixel Bridge application

**What it does**:
- Listens on port 24981 for JSON data from Quixel Bridge
- Parses JSON data and converts to import requests
- Queues import requests for processing in main thread
- Provides thread-safe access to pending imports

**Key functions**:
- `start_socket_listener()`: Start the socket listener thread
- `stop_socket_listener()`: Stop the socket listener
- `check_pending_imports()`: Timer function that processes queued imports
- `parse_bridge_json()`: Parse JSON data from Quixel Bridge

**Socket details**:
- Host: `localhost`
- Port: `24981`
- Protocol: TCP socket
- Data format: JSON

**When to modify**: When changing socket protocol or JSON format

---

#### `operations/` - Business Logic Layer

##### `fbx_importer.py`
**Purpose**: Import FBX files into Blender

**What it does**:
- Finds all FBX files in asset directories
- Imports FBX files using Blender's built-in importer
- Groups imported objects by base name
- Applies transforms (scale and rotation) to objects

**Key functions**:
- `find_fbx_files()`: Discovers FBX files recursively
- `import_fbx_file()`: Imports a single FBX file
- `group_imported_objects()`: Groups objects by base name
- `apply_transforms()`: Bakes scale/rotation into mesh geometry

**When to modify**: When changing FBX import behavior or adding new import types

---

##### `material_creator.py`
**Purpose**: Create materials from texture files

**What it does**:
- Finds textures for each variation and LOD
- Creates Blender materials with proper node setup
- Identifies texture types from filenames
- Optimizes material reuse (hash-based caching)
- Handles surface materials (textures only, no FBX)

**Key functions**:
- `create_material_from_textures()`: Creates a material from texture paths
- `find_textures_for_variation()`: Finds textures for a specific variation
- `create_surface_material()`: Creates material for surface-only assets
- `create_materials_for_all_variations()`: Creates materials with caching

**Texture types supported**:
- Albedo/Diffuse/Color
- Roughness
- Normal
- Metallic/Metalness
- Opacity/Alpha/Mask
- Displacement/Height

**When to modify**: When adding new texture types or material node setups

---

##### `asset_processor.py`
**Purpose**: Organize and process imported assets

**What it does**:
- Detects asset type (FBX vs surface material)
- Organizes objects by variation (groups objects with same base name)
- Calculates bounding boxes for variations
- Creates attach root hierarchy (empty objects that parent variations)
- Cleans up temporary materials

**Key functions**:
- `detect_asset_type()`: Determines if asset is FBX or surface material
- `organize_objects_by_variation()`: Groups objects by variation suffix
- `calculate_variation_bbox()`: Calculates bounding box for a variation
- `create_asset_hierarchy()`: Creates attach roots with proper spacing
- `cleanup_unused_materials()`: Removes temporary materials

**When to modify**: When changing object organization, attach root logic, or spacing

---

##### `name_corrector.py`
**Purpose**: Fix incorrect object names after FBX import

**What it does**:
- Matches imported objects to their source FBX files
- Detects canonical base name from correctly named objects
- Renames objects to follow naming convention
- Validates LOD completeness

**Key functions**:
- `correct_object_names()`: Main function that corrects all object names
- `find_canonical_base_name()`: Finds the correct base name
- `match_objects_to_fbx()`: Matches objects to FBX files
- `rename_objects_to_match()`: Renames objects to expected names

**When to modify**: When changing naming conventions or name correction logic

---

#### `utils/` - Helper Functions

##### `naming.py`
**Purpose**: Naming conventions and JSON parsing

**What it does**:
- Extracts asset names from JSON metadata files
- Detects variation numbers from object names
- Converts numeric indices to letter suffixes (0→a, 1→b, 26→aa, etc.)
- Parses JSON files for metadata

**Key functions**:
- `get_name_from_json()`: Extracts asset name from JSON
- `detect_variation_number()`: Detects variation from object name
- `index_to_letter_suffix()`: Converts index to letter suffix
- `get_base_name()`: Removes LOD suffix from name

**When to modify**: When changing naming conventions or JSON parsing

---

##### `texture_loader.py`
**Purpose**: Texture loading utilities

**What it does**:
- Finds texture files in directories
- Identifies texture types from filenames
- Creates image texture nodes in Blender materials

**Key functions**:
- `load_texture()`: Creates an image texture node in a material
- `find_texture_files()`: Discovers texture files recursively
- `identify_texture_type()`: Identifies texture type from filename

**When to modify**: When adding new texture types or changing texture loading

---

##### `validation.py`
**Purpose**: Path and asset validation

**What it does**:
- Validates that file paths exist
- Validates asset directory structure
- Detects asset types

**Key functions**:
- `validate_path()`: Checks if a path exists
- `validate_asset_directory()`: Validates asset structure and type
- `is_folder_empty()`: Checks if folder is empty
- `check_folder_contents()`: Gets detailed folder contents

**When to modify**: When changing validation rules

---

##### `scene_manager.py`
**Purpose**: Scene management utilities

**What it does**:
- Creates temporary preview scenes for import
- Manages scene switching
- Transfers assets between scenes
- Cleans up preview scenes

**Key functions**:
- `create_preview_scene()`: Creates temporary preview scene
- `switch_to_scene()`: Switches to a different scene
- `transfer_assets_to_original_scene()`: Transfers assets between scenes
- `cleanup_preview_scene()`: Removes preview scene

**When to modify**: When changing preview scene behavior

---

#### `ui/` - User Interface

##### `operators.py`
**Purpose**: Blender operators (UI entry points)

**What it does**:
- Provides Blender operator classes (UI buttons/commands)
- Calls main.py functions
- Handles user-facing errors

**Key classes**:
- `QUIXEL_OT_import_fbx`: Imports an asset manually
- `QUIXEL_OT_cleanup_requests`: Cleans up stuck requests

**When to modify**: When adding new UI operators or changing user-facing behavior

---

##### `import_modal.py`
**Purpose**: Import confirmation modal

**What it does**:
- Shows import confirmation toolbar
- Manages preview scene
- Handles accept/cancel callbacks

**Key functions**:
- `show_import_toolbar()`: Shows the import toolbar
- `get_active_toolbar()`: Gets the currently active toolbar
- `cleanup_toolbar()`: Cleans up the toolbar

**When to modify**: When changing import confirmation UI

---

##### `import_toolbar.py`
**Purpose**: Import toolbar with LOD controls

**What it does**:
- Displays LOD slider for switching between LOD levels
- Provides wireframe toggle
- Shows accept/cancel buttons
- Manages toolbar state

**Key functions**:
- `position_lods_for_preview()`: Positions LODs for preview
- `set_lod_levels()`: Sets available LOD levels
- `_handle_slider_change()`: Handles LOD slider changes
- `_handle_wireframe_toggle()`: Handles wireframe toggle

**When to modify**: When changing toolbar UI or adding new controls

---

## Quixel Bridge Communication

### How It Works

The Python addon communicates with Quixel Bridge using **socket-based communication** - Quixel Bridge sends JSON data over a TCP socket when assets are exported.

### Communication Flow

```
┌─────────────────┐                    ┌──────────────────┐
│ Quixel Bridge   │                    │  Python Addon    │
│                 │                    │                  │
│  1. User exports│                    │                  │
│     asset       │                    │                  │
│                 │                    │                  │
│  2. Send JSON   │ ────(socket)─────> │  3. Socket       │
│     data to     │                    │     listener     │
│     port 24981  │                    │     receives     │
│                 │                    │                  │
│                 │                    │  4. Parse JSON   │
│                 │                    │     and queue     │
│                 │                    │                  │
│                 │                    │  5. Process      │
│                 │                    │     import       │
│                 │                    │                  │
│                 │                    │  6. Import       │
│                 │                    │     complete     │
└─────────────────┘                    └──────────────────┘
```

### Socket Details

- **Host**: `localhost` (127.0.0.1)
- **Port**: `24981`
- **Protocol**: TCP socket
- **Data Format**: JSON

### JSON Format

Quixel Bridge sends JSON data in the following format:

```json
[
  {
    "path": "C:/Users/.../Downloads/asset_folder",
    "name": "Rock_Asset_01",
    "resolution": "2K"
  }
]
```

Or a single object:

```json
{
  "path": "C:/Users/.../Downloads/asset_folder",
  "name": "Rock_Asset_01",
  "resolution": "2K"
}
```

**Fields**:
- `path`: Path to the exported asset directory (required)
- `name`: Name of the asset (optional, falls back to directory name)
- `resolution`: Texture resolution (e.g., "2K", "4K", "8K") (optional)

### Socket Listener

The socket listener runs in a separate thread and:
- Binds to `localhost:24981` when the addon is enabled
- Accepts connections from Quixel Bridge
- Receives JSON data and parses it
- Queues import requests for processing in the main Blender thread
- Handles connection errors gracefully

### Import Request Processing

Import requests are processed in the main Blender thread via a timer:
- Timer runs every 1 second (or 0.1 seconds if imports are pending)
- Processes one import at a time to avoid blocking
- Calls `main.py::import_asset()` for each queued request

### Thread Safety

The socket listener uses thread-safe mechanisms:
- Global lock (`_bridge_data_lock`) for accessing pending imports
- Import flag (`_import_in_progress`) to prevent concurrent imports
- Queue-based system to safely pass data from socket thread to main thread

---

## Function Location Guide

### Where to Find Import Logic

**Main entry point**: `main.py::import_asset()`
- Detects asset type and routes to appropriate handler

**FBX import**: `operations/fbx_importer.py`
- `find_fbx_files()`: Find FBX files
- `import_fbx_file()`: Import single FBX
- `group_imported_objects()`: Group by base name
- `apply_transforms()`: Apply scale/rotation

**Surface material import**: `operations/material_creator.py::create_surface_material()`
- Creates material from JSON + textures (no FBX)

---

### Where to Find Material Creation

**Main material creation**: `operations/material_creator.py`
- `create_material_from_textures()`: Creates a material from texture paths
- `create_materials_for_all_variations()`: Creates materials for all variations with caching
- `find_textures_for_variation()`: Finds textures for a specific variation

**Texture type identification**: `utils/texture_loader.py::identify_texture_type()`
- Identifies texture type from filename (albedo, roughness, normal, etc.)

**Texture loading**: `utils/texture_loader.py::load_texture()`
- Creates image texture node in Blender material

---

### Where to Find Object Organization

**Variation grouping**: `operations/asset_processor.py::organize_objects_by_variation()`
- Groups objects by variation suffix (a, b, c, etc.)

**Name correction**: `operations/name_corrector.py::correct_object_names()`
- Corrects object names to match naming convention

**Base name extraction**: `utils/naming.py::get_base_name()`
- Extracts base name from object name (removes LOD suffix)

**Variation detection**: `utils/naming.py::detect_variation_number()`
- Detects variation number from object name

---

### Where to Find Naming Utilities

**All naming functions**: `utils/naming.py`
- `get_name_from_json()`: Extract name from JSON metadata
- `detect_variation_number()`: Detect variation from object name
- `index_to_letter_suffix()`: Convert index to letter (0→a, 1→b, etc.)
- `get_base_name()`: Remove LOD suffix from name

**Name correction**: `operations/name_corrector.py`
- `correct_object_names()`: Main name correction function
- `find_canonical_base_name()`: Find correct base name
- `rename_objects_to_match()`: Rename objects to expected names

---

### Where to Find Validation

**Path validation**: `utils/validation.py::validate_path()`
- Checks if a path exists

**Asset validation**: `utils/validation.py::validate_asset_directory()`
- Validates asset directory structure
- Detects asset type (FBX vs surface)

**Folder validation**: `utils/validation.py::is_folder_empty()`
- Checks if folder is empty

---

## Extension Points

### Custom Attach Roots Logic

#### Current Implementation

Attach roots are created in: `operations/asset_processor.py::create_asset_hierarchy()`

**What it does**:
1. Calculates bounding boxes for all variations
2. Creates empty objects (attach roots) for each variation
3. Positions attach roots with 1-meter spacing between variations
4. Parents all variation objects to their attach root

**Current spacing logic**:
```python
current_x_offset = 0.0
margin = 1.0  # Fixed 1 meter margin

for variation_suffix in sorted(variations.keys()):
    # Create attach root at current_x_offset
    attach_root.location.x = current_x_offset
    
    # Parent objects to attach root
    for obj in variation_objects:
        obj.parent = attach_root
    
    # Move to next position
    current_x_offset += bbox['width'] + margin
```

#### How to Modify Spacing

**Location**: `operations/asset_processor.py::create_asset_hierarchy()`

**Example: Change margin to 2 meters**:
```python
# Line ~170 in create_asset_hierarchy()
margin = 2.0  # Changed from 1.0 to 2.0
```

**Example: Use percentage-based spacing**:
```python
# Replace fixed margin with percentage
margin_percent = 0.5  # 50% of width
current_x_offset += bbox['width'] * (1 + margin_percent)
```

#### How to Modify Positioning

**Current**: Variations are spaced along X-axis only

**Example: Stack vertically instead**:
```python
# In create_asset_hierarchy(), change:
attach_root.location.x = 0.0
attach_root.location.y = current_y_offset  # Use Y instead of X
attach_root.location.z = 0.0

# Update offset
current_y_offset += bbox['height'] + margin
```

**Example: Arrange in grid**:
```python
# Arrange in 2x2 grid
grid_cols = 2
col = len(created_attach_roots) % grid_cols
row = len(created_attach_roots) // grid_cols

attach_root.location.x = col * (max_width + margin)
attach_root.location.y = row * (max_height + margin)
attach_root.location.z = 0.0
```

#### How to Modify Naming

**Location**: `operations/asset_processor.py::create_asset_hierarchy()`

**Current naming**: `{attach_root_base_name}_{variation_suffix}`

**Example: Add LOD to name**:
```python
# Get LOD from first object in variation
first_obj = variation_objects[0]
lod_level = extract_lod_from_name(first_obj.name)  # You'd need to implement this

attach_root_name = f"{attach_root_base_name}_{variation_suffix}_LOD{lod_level}"
```

**Example: Use custom naming scheme**:
```python
# Custom naming: "Root_VariationA", "Root_VariationB"
attach_root_name = f"Root_Variation{variation_suffix.upper()}"
```

#### How to Add Custom Properties to Attach Roots

**Location**: `operations/asset_processor.py::create_asset_hierarchy()`

**Example: Add LOD level as custom property**:
```python
# After creating attach_root
attach_root["lod_level"] = lod_level  # Store as custom property
attach_root["variation_index"] = variation_index
attach_root["asset_name"] = attach_root_base_name
```

**Example: Add bounding box data**:
```python
# Store bounding box in custom properties
attach_root["bbox_width"] = bbox['width']
attach_root["bbox_height"] = bbox['height']
attach_root["bbox_depth"] = bbox['depth']
```

**Accessing custom properties later**:
```python
# In Blender Python console or another script
lod = attach_root.get("lod_level")
variation = attach_root.get("variation_index")
```

---

### Custom Material Types

#### Current Implementation

Materials are created in: `operations/material_creator.py::create_material_from_textures()`

**Current texture types**:
- Albedo/Diffuse/Color → Base Color input
- Roughness → Roughness input
- Normal → Normal Map node → Normal input
- Metallic → Metallic input
- Opacity/Alpha/Mask → Alpha input + Blend mode

**Texture type identification**: `utils/texture_loader.py::identify_texture_type()`

#### How to Add a New Texture Type

**Step 1: Add texture identification**

**Location**: `utils/texture_loader.py::identify_texture_type()`

```python
def identify_texture_type(filename):
    filename_lower = str(filename).lower()
    
    # ... existing checks ...
    
    # Add new texture type
    elif 'emission' in filename_lower or 'emissive' in filename_lower:
        return 'emission'
    elif 'ao' in filename_lower or 'ambient_occlusion' in filename_lower:
        return 'ao'
    
    return None
```

**Step 2: Add material node setup**

**Location**: `operations/material_creator.py::create_material_from_textures()`

```python
def create_material_from_textures(material_name, textures, context):
    # ... existing code ...
    
    # Add Emission texture
    if 'emission' in textures and textures['emission']:
        emission_node = load_texture(nodes, 'Emission', textures['emission'], 'sRGB')
        if emission_node:
            links.new(emission_node.outputs['Color'], bsdf.inputs['Emission'])
            # Set emission strength
            bsdf.inputs['Emission Strength'].default_value = 1.0
    
    # Add Ambient Occlusion (multiply with base color)
    if 'ao' in textures and textures['ao']:
        ao_node = load_texture(nodes, 'AO', textures['ao'], 'Non-Color')
        if ao_node:
            # Create multiply node
            multiply_node = nodes.new(type='ShaderNodeMixRGB')
            multiply_node.blend_type = 'MULTIPLY'
            multiply_node.location = (-400, -200)
            
            # Connect: AO → Multiply → Base Color
            links.new(ao_node.outputs['Color'], multiply_node.inputs['Color2'])
            # Get existing base color connection
            if 'albedo' in textures and textures['albedo']:
                albedo_node = nodes.get('Albedo')
                if albedo_node:
                    links.new(albedo_node.outputs['Color'], multiply_node.inputs['Color1'])
                    links.new(multiply_node.outputs['Color'], bsdf.inputs['Base Color'])
    
    # ... rest of existing code ...
```

**Step 3: Add to texture types list**

**Location**: `operations/material_creator.py::find_textures_for_variation()`

```python
# Line ~191, add to texture_types list
texture_types = ['albedo', 'roughness', 'normal', 'metallic', 'opacity', 'emission', 'ao']
```

**Step 4: Add to hash calculation** (for material caching)

**Location**: `operations/material_creator.py::get_texture_hash()`

```python
# Line ~94, add to texture_types list
texture_types = ['albedo', 'roughness', 'normal', 'metallic', 'opacity', 'emission', 'ao']
```

#### How to Add Custom Material Nodes

**Example: Add displacement mapping**:

```python
# In create_material_from_textures()
if 'displacement' in textures and textures['displacement']:
    displacement_node = load_texture(nodes, 'Displacement', textures['displacement'], 'Non-Color')
    if displacement_node:
        # Create displacement node
        displacement_shader = nodes.new(type='ShaderNodeDisplacement')
        displacement_shader.location = (-200, -600)
        
        # Connect displacement
        links.new(displacement_node.outputs['Color'], displacement_shader.inputs['Height'])
        
        # Connect to material output
        material_output = nodes.get('Material Output')
        if material_output:
            links.new(displacement_shader.outputs['Displacement'], material_output.inputs['Displacement'])
```

**Example: Add custom shader setup**:

```python
# Replace Principled BSDF with custom node setup
# Remove default BSDF
nodes.remove(bsdf)

# Create custom nodes
custom_shader = nodes.new(type='ShaderNodeBsdfPrincipled')
# ... set up custom shader ...
```

---

### Custom Attributes (LODs, etc.)

#### Current LOD Handling

LODs are currently:
- **Extracted from filenames**: `operations/name_corrector.py::extract_lod_from_fbx()`
- **Used in naming**: Objects named `{base}_{variation}_LOD{level}`
- **Used in materials**: Materials named `{attach_root}_LOD{level}`
- **NOT stored as custom properties**: LOD info is only in names

#### How to Add LOD as Custom Property

**Location**: Multiple places depending on when you want to add it

**Option 1: Add during FBX import**

**Location**: `operations/fbx_importer.py::import_fbx_file()`

```python
def import_fbx_file(filepath, context):
    # ... existing import code ...
    
    # After importing objects
    for obj in imported_objects:
        if obj.type == 'MESH' and obj.data:
            # Extract LOD from filename
            lod_level = extract_lod_from_fbx(filepath)
            
            # Add as custom property
            obj["lod_level"] = lod_level[0]  # lod_level is tuple (level, has_lod)
            obj["source_fbx"] = str(filepath)
    
    return imported_objects, base_name
```

**Option 2: Add during name correction**

**Location**: `operations/name_corrector.py::rename_objects_to_match()`

```python
def rename_objects_to_match(objects, fbx_mapping):
    # ... existing code ...
    
    for obj in objects:
        # ... existing renaming code ...
        
        # Add custom properties
        mapping = fbx_mapping[obj]
        obj["lod_level"] = mapping['lod_level']
        obj["variation_index"] = variation_index
        obj["base_name"] = expected_base
```

**Option 3: Add during attach root creation**

**Location**: `operations/asset_processor.py::create_asset_hierarchy()`

```python
def create_asset_hierarchy(variations, attach_root_base_name, context):
    # ... existing code ...
    
    for variation_suffix in sorted(variations.keys()):
        variation_objects = variations[variation_suffix]
        
        # Add custom properties to attach root
        attach_root["variation_suffix"] = variation_suffix
        attach_root["variation_count"] = len(variation_objects)
        
        # Add custom properties to objects
        for obj in variation_objects:
            if obj.type == 'MESH' and obj.data:
                # Extract LOD from object name
                lod_match = re.search(r'_?LOD(\d+)', obj.name, re.IGNORECASE)
                if lod_match:
                    obj["lod_level"] = lod_match.group(1)
                
                obj["variation_suffix"] = variation_suffix
                obj["attach_root"] = attach_root_name
```

#### How to Add Other Custom Attributes

**Example: Add asset metadata from JSON**:

**Location**: `main.py::_import_fbx_asset()` or `operations/asset_processor.py::create_asset_hierarchy()`

```python
# In create_asset_hierarchy() or similar
from ..utils.naming import get_name_from_json

# Get JSON data
json_name, json_file = get_name_from_json(asset_dir)
if json_file:
    import json
    with open(json_file, 'r') as f:
        json_data = json.load(f)
    
    # Add metadata to attach root
    attach_root["asset_id"] = json_data.get('id', '')
    attach_root["asset_category"] = json_data.get('category', '')
    attach_root["asset_tags"] = str(json_data.get('tags', []))
```

**Example: Add bounding box data**:

```python
# In create_asset_hierarchy(), after calculating bbox
for obj in variation_objects:
    if obj.type == 'MESH' and obj.data:
        # Calculate object bbox
        obj_bbox = calculate_object_bbox(obj)  # You'd need to implement this
        
        obj["bbox_min_x"] = obj_bbox['min_x']
        obj["bbox_max_x"] = obj_bbox['max_x']
        obj["bbox_width"] = obj_bbox['width']
        # ... etc
```

**Example: Add import metadata**:

```python
# In main.py::_import_fbx_asset()
import time

# After successful import
for attach_root in created_attach_roots:
    attach_root["import_timestamp"] = time.time()
    attach_root["import_date"] = time.strftime("%Y-%m-%d %H:%M:%S")
    attach_root["blender_version"] = bpy.app.version_string
```

#### Accessing Custom Properties

**In Blender Python console**:
```python
import bpy

# Get object
obj = bpy.data.objects["MyObject"]

# Read custom property
lod_level = obj.get("lod_level")
variation = obj.get("variation_suffix")

# Check if property exists
if "lod_level" in obj:
    print(f"LOD Level: {obj['lod_level']}")
```

**In another script**:
```python
# Iterate all objects with LOD property
for obj in bpy.data.objects:
    if "lod_level" in obj:
        print(f"{obj.name}: LOD {obj['lod_level']}")
```

---

## Import Workflow Walkthrough

### Complete Import Process

Here's the step-by-step flow when an asset is imported:

#### Step 1: Socket Reception
**Location**: `communication/quixel_bridge_socket.py::_importer_callback()`

1. Socket listener receives JSON data from Quixel Bridge
2. Parses JSON data using `parse_bridge_json()`
3. Queues import requests in thread-safe queue
4. Returns to listening for next connection

#### Step 2: Request Processing
**Location**: `communication/quixel_bridge_socket.py::check_pending_imports()`

1. Timer runs every 1 second (or 0.1 seconds if imports pending)
2. Checks for queued import requests
3. Processes one import at a time
4. Calls `main.py::import_asset()` with request data

#### Step 3: Asset Type Detection
**Location**: `main.py::import_asset()`

1. Calls `operations/asset_processor.py::detect_asset_type()`
2. Determines if asset is:
   - **FBX**: Contains `.fbx` files
   - **Surface**: Contains JSON + textures (no FBX)
3. Routes to appropriate handler

#### Step 4: FBX Import (if FBX asset)
**Location**: `main.py::_import_fbx_asset()`

**4.1: Import FBX Files**
- `operations/fbx_importer.py::find_fbx_files()`: Find all FBX files
- `operations/fbx_importer.py::import_fbx_file()`: Import each FBX
- Groups imported objects by base name

**4.2: Correct Object Names**
- `operations/name_corrector.py::correct_object_names()`:
  - Finds canonical base name
  - Matches objects to FBX files
  - Renames objects to match naming convention

**4.3: Remove Old World Roots**
- Detects empty parent objects from FBX import
- Extracts rotation and scale from old roots
- Removes old roots and reparents children

**4.4: Set Transforms**
- Sets detected rotation and scale on all objects
- `operations/fbx_importer.py::apply_transforms()`: Bakes transforms into mesh

**4.5: Organize by Variation**
- `operations/asset_processor.py::organize_objects_by_variation()`:
  - Groups objects by variation suffix (a, b, c, etc.)
  - Converts numeric indices to letter suffixes

**4.6: Create Materials**
- `operations/material_creator.py::create_materials_for_all_variations()`:
  - Finds textures for each variation and LOD
  - Creates materials with hash-based caching
  - Assigns materials to objects

**4.7: Create Attach Roots**
- `operations/asset_processor.py::create_asset_hierarchy()`:
  - Calculates bounding boxes
  - Creates attach roots with spacing
  - Parents variation objects to attach roots

**4.8: Cleanup**
- `operations/asset_processor.py::cleanup_unused_materials()`:
  - Removes temporary materials from FBX import

#### Step 5: Surface Material (if surface asset)
**Location**: `main.py::import_asset()`

1. `operations/material_creator.py::create_surface_material()`:
   - Finds JSON file
   - Finds texture files
   - Creates material
   - Assigns to selected objects (if any)

### Critical Order of Operations

**IMPORTANT**: The order matters! Here's why:

1. **Import FBX first**: Objects must exist before processing
2. **Correct names before grouping**: Grouping relies on correct base names
3. **Remove old roots before setting transforms**: Old roots have the correct transforms
4. **Set transforms before applying**: Must set correct values before baking
5. **Apply transforms before parenting**: Transforms must be baked before parenting
6. **Organize by variation before materials**: Materials are assigned per variation
7. **Create materials before attach roots**: Materials are named after attach roots
8. **Calculate bbox before creating roots**: Spacing needs bbox data

---

## Code Examples

### Example 1: Adding Emission Texture Type

**Step 1**: Add to texture identification (`utils/texture_loader.py`):

```python
def identify_texture_type(filename):
    filename_lower = str(filename).lower()
    
    # ... existing checks ...
    
    elif 'emission' in filename_lower or 'emissive' in filename_lower:
        return 'emission'
    
    return None
```

**Step 2**: Add to material creation (`operations/material_creator.py`):

```python
def create_material_from_textures(material_name, textures, context):
    # ... existing code ...
    
    # Load Emission texture
    if 'emission' in textures and textures['emission']:
        emission_node = load_texture(nodes, 'Emission', textures['emission'], 'sRGB')
        if emission_node:
            links.new(emission_node.outputs['Color'], bsdf.inputs['Emission'])
            bsdf.inputs['Emission Strength'].default_value = 1.0
    
    # ... rest of code ...
```

**Step 3**: Add to texture types list (`operations/material_creator.py::find_textures_for_variation()`):

```python
texture_types = ['albedo', 'roughness', 'normal', 'metallic', 'opacity', 'emission']
```

**Step 4**: Add to hash calculation (`operations/material_creator.py::get_texture_hash()`):

```python
texture_types = ['albedo', 'roughness', 'normal', 'metallic', 'opacity', 'emission']
```

---

### Example 2: Modifying Attach Root Spacing

**Change spacing to 2 meters** (`operations/asset_processor.py::create_asset_hierarchy()`):

```python
# Line ~170
margin = 2.0  # Changed from 1.0
```

**Use percentage-based spacing**:

```python
# Replace fixed margin
margin_percent = 0.5  # 50% of width
current_x_offset += bbox['width'] * (1 + margin_percent)
```

**Stack vertically instead of horizontally**:

```python
# Change from X-axis to Y-axis
current_y_offset = 0.0
margin = 1.0

for variation_suffix in sorted(variations.keys()):
    # ... create attach root ...
    
    attach_root.location.x = 0.0
    attach_root.location.y = current_y_offset  # Y instead of X
    attach_root.location.z = 0.0
    
    # ... parent objects ...
    
    current_y_offset += bbox['height'] + margin  # Height instead of width
```

---

### Example 3: Adding LOD as Custom Property

**Add during name correction** (`operations/name_corrector.py::rename_objects_to_match()`):

```python
def rename_objects_to_match(objects, fbx_mapping):
    # ... existing code ...
    
    for obj in objects:
        # ... existing renaming code ...
        
        # Add custom properties
        mapping = fbx_mapping[obj]
        obj["lod_level"] = mapping['lod_level']
        obj["variation_index"] = variation_index
        obj["base_name"] = expected_base
        obj["source_fbx"] = str(mapping['fbx_file'])
```

**Add during attach root creation** (`operations/asset_processor.py::create_asset_hierarchy()`):

```python
def create_asset_hierarchy(variations, attach_root_base_name, context):
    # ... existing code ...
    
    for variation_suffix in sorted(variations.keys()):
        variation_objects = variations[variation_suffix]
        
        # Add to attach root
        attach_root["variation_suffix"] = variation_suffix
        attach_root["object_count"] = len(variation_objects)
        
        # Add to objects
        for obj in variation_objects:
            if obj.type == 'MESH' and obj.data:
                # Extract LOD from name
                import re
                lod_match = re.search(r'_?LOD(\d+)', obj.name, re.IGNORECASE)
                if lod_match:
                    obj["lod_level"] = lod_match.group(1)
                
                obj["variation_suffix"] = variation_suffix
```

---

### Example 4: Adding Custom Material Node Setup

**Add displacement mapping** (`operations/material_creator.py::create_material_from_textures()`):

```python
def create_material_from_textures(material_name, textures, context):
    # ... existing code ...
    
    # Add Displacement
    if 'displacement' in textures and textures['displacement']:
        displacement_node = load_texture(nodes, 'Displacement', textures['displacement'], 'Non-Color')
        if displacement_node:
            # Create displacement shader node
            displacement_shader = nodes.new(type='ShaderNodeDisplacement')
            displacement_shader.location = (-200, -600)
            displacement_shader.inputs['Scale'].default_value = 0.1
            
            # Connect displacement
            links.new(displacement_node.outputs['Color'], displacement_shader.inputs['Height'])
            
            # Connect to material output
            material_output = nodes.get('Material Output')
            if material_output:
                links.new(displacement_shader.outputs['Displacement'], material_output.inputs['Displacement'])
```

---

## Summary

This guide has covered:
- **Project structure**: Where everything is located
- **Communication**: How Python communicates with Quixel Bridge
- **Function locations**: Where to find specific functionality
- **Extension points**: How to customize attach roots, materials, and attributes
- **Workflow**: Step-by-step import process
- **Examples**: Practical code examples for common tasks

For more details on architecture, see `ARCHITECTURE.md`.

For questions or issues, check the code comments or Blender console output (enable with `Window > Toggle System Console` on Windows).
