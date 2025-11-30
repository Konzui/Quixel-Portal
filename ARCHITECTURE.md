# Architecture Documentation

This document explains the architecture and design decisions of the Quixel Portal Blender addon.

## Overview

The addon is structured as a modular system with clear separation of concerns:

```
Quixel Bridge Export
    ↓ (sends JSON via socket)
Socket Listener (communication/quixel_bridge_socket.py)
    ↓ (queues import request)
Main Flow (main.py)
    ↓
Operations Layer (operations/)
    ↓
Utilities (utils/)
```

Communication with Quixel Bridge happens independently through the `communication/` layer.

## Module Responsibilities

### `__init__.py` - Addon Registration
- **Purpose**: Minimal entry point for Blender addon registration
- **Responsibilities**:
  - Register Blender operators
  - Start socket listener for Quixel Bridge communication
  - Start background timer to check for pending imports
  - Load icons and resources
- **Dependencies**: All other modules
- **Key Functions**: `register()`, `unregister()`

### `main.py` - Workflow Orchestration
- **Purpose**: High-level workflow coordination
- **Responsibilities**:
  - Orchestrate the import process
  - Coordinate between operations modules
  - Handle asset type detection
  - Manage import flow (FBX vs surface materials)
- **Key Functions**:
  - `import_asset()`: Main entry point for asset imports
  - `_import_fbx_asset()`: FBX import workflow
- **Dependencies**: `operations/`, `communication/`, `utils/`

### `communication/` - Quixel Bridge Communication

#### `quixel_bridge_socket.py`
- **Purpose**: Socket communication with Quixel Bridge application
- **Responsibilities**:
  - Socket listener on port 24981
  - Parse JSON data from Quixel Bridge
  - Queue import requests for main thread processing
  - Thread-safe access to pending imports
- **Key Functions**:
  - `start_socket_listener()`: Start the socket listener thread
  - `stop_socket_listener()`: Stop the socket listener
  - `check_pending_imports()`: Timer function that processes queued imports
  - `parse_bridge_json()`: Parse JSON data from Quixel Bridge
- **Socket Details**:
  - Host: `localhost` (127.0.0.1)
  - Port: `24981`
  - Protocol: TCP socket
  - Data Format: JSON

### `operations/` - Business Logic

#### `fbx_importer.py`
- **Purpose**: Import FBX files into Blender
- **Responsibilities**:
  - Find FBX files in asset directories
  - Import FBX files using Blender's importer
  - Group imported objects by base name
  - Apply transforms to objects
- **Key Functions**:
  - `find_fbx_files()`: Discover FBX files
  - `import_fbx_file()`: Import single FBX file
  - `group_imported_objects()`: Group by base name
  - `apply_transforms()`: Apply scale and rotation

#### `material_creator.py`
- **Purpose**: Create materials from textures
- **Responsibilities**:
  - Find textures for variations
  - Create materials with proper node setup
  - Handle texture type identification
  - Optimize material reuse (hash-based caching)
  - Support surface materials (textures only, no FBX)
- **Key Functions**:
  - `create_material_from_textures()`: Create material from texture paths
  - `find_textures_for_variation()`: Find textures for a variation
  - `create_surface_material()`: Create material for surface assets
  - `create_materials_for_all_variations()`: Create materials with caching

#### `asset_processor.py`
- **Purpose**: Organize and process imported assets
- **Responsibilities**:
  - Detect asset type (FBX vs surface material)
  - Organize objects by variation
  - Calculate bounding boxes
  - Create attach root hierarchy
  - Clean up temporary materials
- **Key Functions**:
  - `detect_asset_type()`: Determine asset type
  - `organize_objects_by_variation()`: Group by variation
  - `create_asset_hierarchy()`: Create attach roots with spacing
  - `cleanup_unused_materials()`: Remove temporary materials

#### `name_corrector.py`
- **Purpose**: Fix incorrect object names after FBX import
- **Responsibilities**:
  - Match imported objects to their source FBX files
  - Detect canonical base name from correctly named objects
  - Rename objects to follow naming convention
  - Validate LOD completeness
- **Key Functions**:
  - `correct_object_names()`: Main function that corrects all object names
  - `find_canonical_base_name()`: Find the correct base name
  - `match_objects_to_fbx()`: Match objects to FBX files
  - `rename_objects_to_match()`: Rename objects to expected names

### `utils/` - Helper Functions

#### `naming.py`
- **Purpose**: Naming conventions and JSON parsing
- **Responsibilities**:
  - Extract names from JSON metadata
  - Detect variation numbers from object names
  - Convert indices to letter suffixes
  - Parse JSON files
- **Key Functions**:
  - `get_name_from_json()`: Extract asset name from JSON
  - `detect_variation_number()`: Detect variation from object name
  - `index_to_letter_suffix()`: Convert index to letter (0→a, 1→b, etc.)

#### `texture_loader.py`
- **Purpose**: Texture loading utilities
- **Responsibilities**:
  - Find texture files in directories
  - Identify texture types from filenames
  - Create image texture nodes in Blender
- **Key Functions**:
  - `load_texture()`: Create image texture node
  - `find_texture_files()`: Discover texture files
  - `identify_texture_type()`: Identify texture type from filename

#### `validation.py`
- **Purpose**: Path and asset validation
- **Responsibilities**:
  - Validate file paths
  - Validate asset directories
  - Detect asset types
- **Key Functions**:
  - `validate_path()`: Check if path exists
  - `validate_asset_directory()`: Validate asset structure
  - `is_folder_empty()`: Check if folder is empty
  - `check_folder_contents()`: Get detailed folder contents

#### `scene_manager.py`
- **Purpose**: Scene management utilities
- **Responsibilities**:
  - Create temporary preview scenes for import
  - Manage scene switching
  - Transfer assets between scenes
  - Clean up preview scenes
- **Key Functions**:
  - `create_preview_scene()`: Create temporary preview scene
  - `switch_to_scene()`: Switch to a different scene
  - `transfer_assets_to_original_scene()`: Transfer assets between scenes
  - `cleanup_preview_scene()`: Remove preview scene

### `ui/` - User Interface

#### `operators.py`
- **Purpose**: Blender operators (UI entry points)
- **Responsibilities**:
  - Provide Blender operator interface
  - Call main.py functions
  - Handle user-facing errors
- **Key Classes**:
  - `QUIXEL_OT_import_fbx`: Import asset operator
  - `QUIXEL_OT_cleanup_requests`: Cleanup operator

#### `import_modal.py`
- **Purpose**: Import confirmation modal
- **Responsibilities**:
  - Show import confirmation toolbar
  - Manage preview scene
  - Handle accept/cancel callbacks
- **Key Functions**:
  - `show_import_toolbar()`: Show the import toolbar
  - `get_active_toolbar()`: Get the currently active toolbar
  - `cleanup_toolbar()`: Clean up the toolbar

#### `import_toolbar.py`
- **Purpose**: Import toolbar with LOD controls
- **Responsibilities**:
  - Display LOD slider for switching between LOD levels
  - Provide wireframe toggle
  - Show accept/cancel buttons
  - Manage toolbar state
- **Key Functions**:
  - `position_lods_for_preview()`: Position LODs for preview
  - `set_lod_levels()`: Set available LOD levels
  - `_handle_slider_change()`: Handle LOD slider changes
  - `_handle_wireframe_toggle()`: Handle wireframe toggle

## Data Flow

### Import Request Flow

```
Quixel Bridge
    ↓ (sends JSON via socket to port 24981)
Socket Listener (quixel_bridge_socket.py)
    ↓ (parses JSON and queues request)
check_pending_imports() (timer function)
    ↓ (processes one import at a time)
main.py::import_asset()
    ↓ (detects asset type)
operations/fbx_importer.py
operations/material_creator.py
operations/asset_processor.py
    ↓ (import complete)
User sees preview toolbar
```

### Socket Communication Flow

```
Quixel Bridge Export
    ↓ (connects to localhost:24981)
Socket Listener accepts connection
    ↓ (receives JSON data)
_importer_callback() parses JSON
    ↓ (queues import request)
Main thread processes via timer
    ↓ (calls import_asset())
Import workflow executes
```

## Design Principles

### 1. Separation of Concerns
Each module has a single, well-defined responsibility. Communication, operations, and UI are completely isolated.

### 2. Abstraction
The `main.py` module hides communication details from business logic. Operations modules don't need to know about socket communication.

### 3. Dependency Injection
Functions receive dependencies as parameters rather than using global state (with minimal exceptions for socket listener management).

### 4. Extensibility
New import types can be added by:
1. Creating a new module in `operations/`
2. Adding detection logic to `main.py`
3. No changes needed to communication layer

### 5. Testability
Each module can be tested independently. Communication can be mocked for testing operations.

### 6. Thread Safety
Socket communication uses thread-safe mechanisms:
- Global lock for accessing pending imports
- Queue-based system to safely pass data from socket thread to main thread
- Import flag to prevent concurrent imports

## Extension Points

### Adding New Import Types

1. Create importer in `operations/` (e.g., `obj_importer.py`)
2. Add detection in `main.py::import_asset()`
3. Follow the same pattern as `fbx_importer.py`

### Modifying Communication

All communication is in `communication/`:
- Change socket protocol? Modify `quixel_bridge_socket.py`
- Change JSON format? Modify `parse_bridge_json()`
- Operations remain unchanged

### Adding New Utilities

Add helper functions to appropriate `utils/` modules:
- Naming logic → `utils/naming.py`
- File operations → `utils/validation.py`
- Scene management → `utils/scene_manager.py`
- Blender operations → `utils/texture_loader.py` or new module

## Socket Communication Protocol

### JSON Format from Quixel Bridge

Quixel Bridge sends JSON data in the following format:

**Array format** (multiple assets):
```json
[
  {
    "path": "C:/path/to/asset",
    "name": "Asset Name",
    "resolution": "2K"
  }
]
```

**Single object format**:
```json
{
  "path": "C:/path/to/asset",
  "name": "Asset Name",
  "resolution": "2K"
}
```

**Fields**:
- `path`: Path to the exported asset directory (required)
- `name`: Name of the asset (optional, falls back to directory name)
- `resolution`: Texture resolution (e.g., "2K", "4K", "8K") (optional)

### Socket Details

- **Host**: `localhost` (127.0.0.1)
- **Port**: `24981`
- **Protocol**: TCP socket
- **Connection**: Quixel Bridge connects to the addon (not the other way around)
- **Data Format**: JSON (UTF-8 encoded)

### Thread Safety

The socket listener runs in a separate thread and uses:
- Global lock (`_bridge_data_lock`) for thread-safe access to pending imports
- Import flag (`_import_in_progress`) to prevent concurrent imports
- Queue-based system to safely pass data from socket thread to main Blender thread

## Error Handling Strategy

Currently, errors are logged to console. Future improvements could include:
- User-facing error dialogs
- Retry mechanisms for failed imports
- Validation error reporting
- Graceful degradation

## Performance Considerations

- **Socket Listener**: Runs in separate thread, doesn't block Blender
- **Import Processing**: Timer checks every 1 second (or 0.1 seconds if imports pending)
- **One Import at a Time**: Prevents blocking and ensures stability
- **Material Caching**: Hash-based caching prevents duplicate material creation
- **Lazy Imports**: Modules imported only when needed

## Security Considerations

- Socket communication is localhost-only (no external network access)
- Port 24981 is only accessible from local machine
- JSON data is validated before processing
- Path validation ensures only valid asset directories are processed
- No network communication from Blender side - all communication is local
