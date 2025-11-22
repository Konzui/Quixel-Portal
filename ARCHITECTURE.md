# Architecture Documentation

This document explains the architecture and design decisions of the Quixel Portal Blender addon.

## Overview

The addon is structured as a modular system with clear separation of concerns:

```
User Action (UI)
    ↓
Operators (ui/operators.py)
    ↓
Main Flow (main.py)
    ↓
Operations Layer (operations/)
    ↓
Utilities (utils/)
```

Communication with Electron happens independently through the `communication/` layer.

## Module Responsibilities

### `__init__.py` - Addon Registration
- **Purpose**: Minimal entry point for Blender addon registration
- **Responsibilities**:
  - Register Blender operators
  - Register UI elements (topbar button)
  - Start background timers (request watcher, heartbeat)
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

### `communication/` - Electron IPC

#### `electron_bridge.py`
- **Purpose**: Direct communication with Electron application
- **Responsibilities**:
  - Instance ID management (unique per Blender session)
  - Process verification (check if Electron is running)
  - Launch Electron application
  - Heartbeat system (signal Blender is alive)
  - File-based IPC (read/write request and completion files)
- **Key Functions**:
  - `get_or_create_instance_id()`: Get or create Blender instance ID
  - `launch_electron_app()`: Launch Electron with instance ID
  - `write_heartbeat()`: Write heartbeat file
  - `read_import_request()`: Read import request from Electron
  - `write_import_complete()`: Notify Electron of completion

#### `file_watcher.py`
- **Purpose**: Monitor for import requests from Electron
- **Responsibilities**:
  - Poll for import request files
  - Validate requests (instance ID matching, timestamp checking)
  - Clean up stale requests
  - Bridge requests to main import function
- **Key Functions**:
  - `check_import_requests()`: Timer function that polls for requests
  - `validate_request()`: Validate request data
  - `setup_request_watcher()`: Register the timer

### `operations/` - Business Logic

#### `portal_launcher.py`
- **Purpose**: Launch and manage Electron application
- **Responsibilities**:
  - Handle debouncing (prevent rapid clicks)
  - Check if Electron is already running
  - Send show window signals
  - Launch new Electron instances
- **Key Functions**:
  - `open_quixel_portal()`: Main entry point for opening portal

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

### `ui/` - User Interface

#### `operators.py`
- **Purpose**: Blender operators (UI entry points)
- **Responsibilities**:
  - Provide Blender operator interface
  - Call main.py functions
  - Handle user-facing errors
- **Key Classes**:
  - `QUIXEL_OT_open_portal`: Open portal operator
  - `QUIXEL_OT_import_fbx`: Import asset operator
  - `QUIXEL_OT_cleanup_requests`: Cleanup operator

## Data Flow

### Import Request Flow

```
Electron App
    ↓ (writes import_request.json)
Temp Directory (%TEMP%/quixel_portal/)
    ↓ (file_watcher polls every 1 second)
file_watcher.py
    ↓ (validates request)
main.py::import_asset()
    ↓ (detects asset type)
operations/fbx_importer.py
operations/material_creator.py
operations/asset_processor.py
    ↓ (writes import_complete.json)
Electron App (reads completion)
```

### Portal Launch Flow

```
User clicks button
    ↓
ui/operators.py::QUIXEL_OT_open_portal
    ↓
operations/portal_launcher.py::open_quixel_portal()
    ↓
communication/electron_bridge.py::launch_electron_app()
    ↓
Electron App launches
```

## Design Principles

### 1. Separation of Concerns
Each module has a single, well-defined responsibility. Communication, operations, and UI are completely isolated.

### 2. Abstraction
The `main.py` module hides communication details from business logic. Operations modules don't need to know about Electron IPC.

### 3. Dependency Injection
Functions receive dependencies as parameters rather than using global state (with minimal exceptions for instance ID management).

### 4. Extensibility
New import types can be added by:
1. Creating a new module in `operations/`
2. Adding detection logic to `main.py`
3. No changes needed to communication layer

### 5. Testability
Each module can be tested independently. Communication can be mocked for testing operations.

## Extension Points

### Adding New Import Types

1. Create importer in `operations/` (e.g., `obj_importer.py`)
2. Add detection in `main.py::import_asset()`
3. Follow the same pattern as `fbx_importer.py`

### Modifying Communication

All communication is in `communication/`:
- Change IPC protocol? Modify `electron_bridge.py`
- Change polling? Modify `file_watcher.py`
- Operations remain unchanged

### Adding New Utilities

Add helper functions to appropriate `utils/` modules:
- Naming logic → `utils/naming.py`
- File operations → `utils/validation.py`
- Blender operations → `utils/texture_loader.py` or new module

## File-Based IPC Protocol

### Request Format (`import_request.json`)
```json
{
  "asset_path": "C:/path/to/asset",
  "thumbnail": "C:/path/to/thumbnail.png",
  "asset_name": "Asset Name",
  "asset_type": "3d",
  "blender_instance_id": "uuid-here",
  "timestamp": 1234567890
}
```

### Completion Format (`import_complete.json`)
```json
{
  "asset_path": "C:/path/to/asset",
  "asset_name": "Asset Name",
  "thumbnail": "C:/path/to/thumbnail.png",
  "timestamp": 1234567890
}
```

### Heartbeat Format (`heartbeat_{instance_id}.txt`)
```json
{
  "timestamp": 1234567890,
  "blender_pid": 12345,
  "instance_id": "uuid-here"
}
```

## Instance ID System

Each Blender instance gets a unique UUID that:
- Persists for the entire Blender session
- Is passed to Electron when launching
- Is used to match import requests to the correct Blender instance
- Prevents cross-instance interference when multiple Blender windows are open

## Error Handling Strategy

Currently, errors are logged to console. Future improvements could include:
- User-facing error dialogs
- Retry mechanisms for failed imports
- Validation error reporting
- Graceful degradation

## Performance Considerations

- **Polling Interval**: Import requests checked every 1 second (configurable in `file_watcher.py`)
- **Heartbeat Interval**: Written every 30 seconds (configurable in `electron_bridge.py`)
- **Material Caching**: Hash-based caching prevents duplicate material creation
- **Lazy Imports**: Modules imported only when needed

## Security Considerations

- File-based IPC uses temp directory (OS-managed, secure)
- Instance ID matching prevents cross-instance attacks
- No network communication from Blender side
- Electron app handles all network requests

