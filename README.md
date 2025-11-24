# Quixel Portal - Blender Addon

A Blender addon that opens Quixel Megascans in a dedicated Electron-based browser with persistent login sessions and seamless asset import.

## Features

- One-click access to Quixel Megascans from within Blender
- Dedicated browser with navigation toolbar (back, forward, home, reload)
- Persistent session storage - stays logged in between sessions
- Automatic asset import from Quixel downloads
- Support for FBX models and surface materials
- Automatic material creation with texture mapping
- Variation support with proper spacing
- Compatible with Blender 4.2.1 LTS and Python 3.11

## Project Structure

```
Quixel Portal/
├── __init__.py                    # Blender addon registration (minimal entry point)
├── main.py                        # Main application flow orchestrator
├── communication/                 # Electron-Blender IPC communication
│   ├── __init__.py
│   ├── electron_bridge.py        # Instance management, process verification, IPC
│   └── file_watcher.py           # Import request polling and validation
├── operations/                    # Asset import and processing
│   ├── __init__.py
│   ├── portal_launcher.py        # Electron app launching
│   ├── fbx_importer.py           # FBX file import operations
│   ├── material_creator.py       # Material creation from textures
│   └── asset_processor.py       # Object organization and hierarchy
├── utils/                         # Helper functions
│   ├── __init__.py
│   ├── naming.py                 # Naming conventions and JSON parsing
│   ├── texture_loader.py         # Texture loading utilities
│   └── validation.py             # Path and asset validation
├── ui/                           # Blender UI components
│   ├── __init__.py
│   └── operators.py             # Blender operators (UI entry points)
└── electron_app/                 # Electron application
    ├── main.js                  # Main Electron process
    ├── preload.js               # Preload script for IPC
    └── package.json             # Node.js dependencies
```

## Architecture

The addon is organized into clear, modular components:

### Communication Layer (`communication/`)

Handles all interaction with the Electron application:

- **electron_bridge.py**: Manages instance IDs, process verification, heartbeat system, and file-based IPC
- **file_watcher.py**: Monitors for import requests from Electron and validates them

### Operations Layer (`operations/`)

Contains the core business logic for asset processing:

- **portal_launcher.py**: Launches and manages the Electron application
- **fbx_importer.py**: Imports FBX files and groups objects
- **material_creator.py**: Creates materials from textures with variation support
- **asset_processor.py**: Organizes objects by variation and creates hierarchy

### Utilities (`utils/`)

Reusable helper functions:

- **naming.py**: Asset naming conventions, JSON parsing, variation detection
- **texture_loader.py**: Texture file discovery and image node creation
- **validation.py**: Path validation and asset type detection

### UI Layer (`ui/`)

Blender-specific UI components:

- **operators.py**: Thin wrapper operators that call main.py functions

### Main Orchestrator (`main.py`)

High-level workflow functions that coordinate between modules, hiding communication details from business logic.

## Installation

### Step 1: Install Node.js Dependencies

1. Open a terminal/command prompt
2. Navigate to the `electron_app` directory
3. Install dependencies:
   ```bash
   npm install
   ```

### Step 2: Build Production Version (Optional)

If you have the source code and want to build a production-ready zip file:

1. Open a terminal/command prompt in the root directory
2. Run the build script:
   ```bashöö'
   python build.p
   ```
3. This will create `Quixel_Portal_v1.0.0.zip` ready for distribution

### Step 3: Install Blender Addon

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

## Usage

1. In Blender, look for the "Quixel Portal" button in the topbar
2. Click the button to open Quixel Portal
3. The Electron app will launch and navigate to Quixel Megascans
4. Log in to your Quixel account (this will be remembered for future sessions)
5. Download assets from Quixel - they will automatically import into Blender
6. Assets are organized by variation with proper spacing

## How It Works

### Communication Flow

1. **Portal Launch**: Blender launches Electron app with a unique instance ID
2. **Import Request**: Electron writes `import_request.json` to temp directory when asset is downloaded
3. **Request Monitoring**: Blender polls for import requests every second
4. **Asset Import**: Blender processes the request and imports the asset
5. **Completion Notification**: Blender writes `import_complete.json` to notify Electron
6. **Heartbeat**: Blender writes heartbeat files every 30 seconds to signal it's alive

### File-Based IPC

All communication happens via JSON files in `%TEMP%/quixel_portal/`:

- `import_request.json`: Electron → Blender (asset download request)
- `import_complete.json`: Blender → Electron (import completion notification)
- `heartbeat_{instance_id}.txt`: Blender → Electron (alive signal)
- `electron_lock_{instance_id}.txt`: Electron → Blender (process lock)

### Persistent Sessions

The Electron app uses a persistent partition (`persist:quixel`) which stores:

- Cookies
- Local storage
- Session storage
- Cache
- Other browser data

This means once you log in to Quixel, your session will be remembered even after closing and reopening the application.

## Development

### Code Structure

The addon is designed for easy extension:

- **Adding new import types**: Create a new module in `operations/` (e.g., `obj_importer.py`) and update `main.py` to detect and call it
- **Modifying communication**: All Electron communication is isolated in `communication/` - changes here don't affect import logic
- **Extending utilities**: Add helper functions to `utils/` modules as needed

### Testing the Electron App

You can test the Electron app independently:

```bash
cd electron_app
npm start
```

### Building Standalone Executables

To build standalone executables:

```bash
# Windows
npm run build-win

# macOS
npm run build-mac

# Linux
npm run build-linux
```

Built files will be in `electron_app/build/`

## Developer Guide

### Adding a New Import Type

To add support for importing OBJ files (for example):

1. Create `operations/obj_importer.py`:

   ```python
   def find_obj_files(asset_dir):
       # Find OBJ files
       pass

   def import_obj_file(filepath, context):
       # Import OBX file
       pass
   ```

2. Update `main.py` to detect OBJ files:

   ```python
   # In import_asset() function
   elif asset_type == 'obj':
       return _import_obj_asset(...)
   ```

3. No need to understand Electron communication - it's already handled!

### Extending Material Creation

To add new texture types or material nodes:

1. Modify `utils/texture_loader.py` to identify new texture types
2. Update `operations/material_creator.py` to handle new texture types
3. The communication layer remains unchanged

### Modifying Communication

All Electron communication is in `communication/`:

- Change IPC protocol? Modify `electron_bridge.py`
- Change polling frequency? Modify `file_watcher.py`
- Import/export logic is unaffected

## Troubleshooting

### "Electron app not found" error

- Make sure you've installed npm dependencies in the `electron_app` directory
- Verify the `electron_app` folder exists in the addon directory
- Check that the executable path is correct in `communication/electron_bridge.py`

### "npm install" fails

- Ensure Node.js is installed (download from https://nodejs.org/)
- Try running the command prompt as administrator
- Clear npm cache: `npm cache clean --force`

### Addon doesn't appear in Blender

- Make sure you're using Blender 4.2.1 LTS or compatible version
- Check that the entire addon folder structure is intact
- Look for error messages in Blender's console (Window > Toggle System Console)
- Verify all `__init__.py` files are present in subdirectories

### Import errors

- Check that asset directories contain valid FBX files or surface materials
- Verify JSON metadata files are present and valid
- Check Blender console for specific error messages
- Ensure textures are in supported formats (PNG, JPG, TGA, EXR, etc.)

### Electron app opens but shows blank screen

- Check your internet connection
- Try reloading the page manually
- Check if quixel.com is accessible in a regular browser
- Verify Electron app is using the correct URL

### Import requests not processing

- Check that the temp directory is accessible: `%TEMP%/quixel_portal/`
- Verify instance IDs match between Blender and Electron
- Check Blender console for import request validation errors
- Ensure heartbeat files are being written (check temp directory)

## Requirements

- Blender 4.2.1 LTS (or compatible version)
- Python 3.11 (bundled with Blender)
- Node.js 16 or higher
- Internet connection

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
