# Quixel Portal - Blender Addon

A Blender addon that integrates with Quixel Bridge for seamless asset import directly into Blender.

## Features

- Direct integration with Quixel Bridge application
- Automatic asset import from Quixel Bridge exports
- Support for FBX models and surface materials
- Automatic material creation with texture mapping
- Variation support with proper spacing
- LOD (Level of Detail) switching and preview
- **Custom preview workspace** with distraction-free 3D viewport-only layout
- Automatic workspace restoration after import/cancel
- Compatible with Blender 4.2.1 LTS and Python 3.11

## Project Structure

```
Quixel Portal/
├── __init__.py                    # Blender addon registration (minimal entry point)
├── main.py                        # Main application flow orchestrator
├── communication/                 # Quixel Bridge communication
│   ├── __init__.py
│   └── quixel_bridge_socket.py   # Socket listener for Bridge communication
├── operations/                    # Asset import and processing
│   ├── __init__.py
│   ├── fbx_importer.py           # FBX file import operations
│   ├── material_creator.py       # Material creation from textures
│   ├── asset_processor.py        # Object organization and hierarchy
│   └── name_corrector.py         # Object name correction
├── utils/                         # Helper functions
│   ├── __init__.py
│   ├── naming.py                 # Naming conventions and JSON parsing
│   ├── texture_loader.py         # Texture loading utilities
│   ├── validation.py             # Path and asset validation
│   └── scene_manager.py          # Scene management utilities
├── ui/                           # Blender UI components
│   ├── __init__.py
│   ├── operators.py             # Blender operators (UI entry points)
│   ├── import_modal.py          # Import confirmation modal
│   └── import_toolbar.py        # Import toolbar with LOD controls
└── assets/                       # Addon assets
    └── icons/                    # Icon files
```

## Architecture

The addon is organized into clear, modular components:

### Communication Layer (`communication/`)

Handles all interaction with Quixel Bridge:


- **quixel_bridge_socket.py**: Socket listener that receives JSON data from Quixel Bridge on port 24981

### Operations Layer (`operations/`)

Contains the core business logic for asset processing:

- **fbx_importer.py**: Imports FBX files and groups objects
- **material_creator.py**: Creates materials from textures with variation support
- **asset_processor.py**: Organizes objects by variation and creates hierarchy
- **name_corrector.py**: Corrects object names to match expected conventions

### Utilities (`utils/`)

Reusable helper functions:

- **naming.py**: Asset naming conventions, JSON parsing, variation detection
- **texture_loader.py**: Texture file discovery and image node creation
- **validation.py**: Path validation and asset type detection
- **scene_manager.py**: Preview scene creation and management

### UI Layer (`ui/`)

Blender-specific UI components:

- **operators.py**: Thin wrapper operators that call main.py functions
- **import_modal.py**: Import confirmation modal with preview
- **import_toolbar.py**: Toolbar with LOD switching and wireframe toggle

### Main Orchestrator (`main.py`)

High-level workflow functions that coordinate between modules.

## Installation

### Step 1: Install Blender Addon

**Method 1: Install from Zip File (Recommended)**

1. Open Blender 4.2.1 LTS (or compatible version)
2. Go to `Edit > Preferences > Add-ons`
3. Click `Install...`
4. Navigate to and select the `Quixel_Portal_v1.0.0.zip` file
5. Click `Install Add-on`
6. Enable the addon by checking the checkbox next to "Import-Export: Quixel Portal"

**Method 2: Install from Folder (Development)**

1. Copy the entire `Quixel Portal` folder to your Blender addons directory:
   - Windows: `%APPDATA%\Blender Foundation\Blender\4.2\scripts\addons\`
   - macOS: `~/Library/Application Support/Blender/4.2/scripts/addons/`
   - Linux: `~/.config/blender/4.2/scripts/addons/`
2. Restart Blender
3. Enable the addon in preferences

### Step 2: Install Quixel Bridge

1. Download and install Quixel Bridge from [Quixel's website](https://quixel.com/bridge)
2. Make sure Quixel Bridge is running
3. Configure Quixel Bridge to export assets to your preferred location

## Usage

1. **Enable the Addon**: In Blender, go to `Edit > Preferences > Add-ons` and enable "Quixel Portal"
2. **Start Quixel Bridge**: Launch Quixel Bridge application
3. **Export from Bridge**: In Quixel Bridge, select assets and export them. The addon will automatically detect and import them into Blender
4. **Import Confirmation**: When an asset is detected, a toolbar will appear allowing you to:
   - Preview the asset with different LOD levels
   - Toggle wireframe mode
   - Accept or cancel the import
5. **Asset Organization**: Imported assets are automatically organized by variation with proper spacing

## How It Works

### Communication Flow

1. **Socket Listener**: The addon starts a socket listener on port 24981 when enabled
2. **Bridge Export**: When you export an asset from Quixel Bridge, Bridge sends JSON data to the socket
3. **Asset Detection**: The addon receives the JSON data and parses asset information
4. **Import Processing**: The asset is imported into Blender with materials and proper organization
5. **Preview Toolbar**: A toolbar appears allowing you to preview and confirm the import

### Socket Communication

The addon listens on `localhost:24981` for JSON data from Quixel Bridge. The JSON format includes:

- `path`: Path to the asset directory
- `name`: Asset name
- `resolution`: Texture resolution (e.g., "2K", "4K", "8K")

## Development

### Code Structure

The addon is designed for easy extension:

- **Adding new import types**: Create a new module in `operations/` (e.g., `obj_importer.py`) and update `main.py` to detect and call it
- **Modifying communication**: All Bridge communication is isolated in `communication/` - changes here don't affect import logic
- **Extending utilities**: Add helper functions to `utils/` modules as needed

### Adding a New Import Type

To add support for importing OBJ files (for example):

1. Create `operations/obj_importer.py`:

   ```python
   def find_obj_files(asset_dir):
       # Find OBJ files
       pass

   def import_obj_file(filepath, context):
       # Import OBJ file
       pass
   ```

2. Update `main.py` to detect OBJ files:

   ```python
   # In import_asset() function
   elif asset_type == 'obj':
       return _import_obj_asset(...)
   ```

### Extending Material Creation

To add new texture types or material nodes:

1. Modify `utils/texture_loader.py` to identify new texture types
2. Update `operations/material_creator.py` to handle new texture types
3. The communication layer remains unchanged

## Troubleshooting

### "Port 24981 already in use" error

- Another Blender instance may be running with the addon enabled
- Close other Blender instances or disable the addon in other instances
- Check if another application is using port 24981

### Addon doesn't appear in Blender

- Make sure you're using Blender 4.2.1 LTS or compatible version
- Check that the entire addon folder structure is intact
- Look for error messages in Blender's console (Window > Toggle System Console)
- Verify all `__init__.py` files are present in subdirectories

### Assets not importing from Bridge

- Make sure Quixel Bridge is running
- Verify the socket listener started successfully (check Blender console)
- Check that Quixel Bridge is configured to send data to the addon
- Ensure port 24981 is not blocked by firewall

### Import errors

- Check that asset directories contain valid FBX files or surface materials
- Verify JSON metadata files are present and valid
- Check Blender console for specific error messages
- Ensure textures are in supported formats (PNG, JPG, TGA, EXR, etc.)

### Import requests not processing

- Check Blender console for socket connection errors
- Verify the socket listener is running (should see startup message in console)
- Ensure Quixel Bridge is sending data to the correct port (24981)

## Requirements

- Blender 4.2.1 LTS (or compatible version)
- Python 3.11 (bundled with Blender)
- Quixel Bridge application
- Internet connection (for downloading assets from Quixel)

## License

MIT

## Future Enhancements

Potential features for future versions:

- Support for additional file formats (OBJ, GLTF, etc.)
- Custom import settings and preferences
- Asset library tracking within Blender
- Batch import functionality
- Material customization options
- Custom keybindings
