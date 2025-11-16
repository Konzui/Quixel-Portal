# Quixel Portal - Blender Addon

A Blender addon that opens Quixel Megascans in a dedicated Electron-based browser with persistent login sessions.

## Features

- One-click access to Quixel Megascans from within Blender
- Dedicated browser with navigation toolbar (back, forward, home, reload)
- Persistent session storage - stays logged in between sessions
- Compatible with Blender 4.2.1 LTS and Python 3.11

## Project Structure

```
Quixel Portal/
├── __init__.py              # Blender addon main file
├── electron_app/            # Electron application
│   ├── main.js             # Main Electron process
│   ├── preload.js          # Preload script for IPC
│   └── package.json        # Node.js dependencies
└── README.md               # This file
```

## Installation

### Step 1: Install Node.js Dependencies

1. Open a terminal/command prompt
2. Navigate to the `electron_app` directory:
   ```bash
   cd "C:\Users\Benutzer1\OneDrive - Hogeschool West-Vlaanderen\Documenten\_Dev\Blender\Addons\Quixel Portal\electron_app"
   ```
3. Install dependencies:
   ```bash
   npm install
   ```

### Step 2: Install Blender Addon

1. Open Blender 4.2.1 LTS
2. Go to `Edit > Preferences > Add-ons`
3. Click `Install...`
4. Navigate to and select the entire `Quixel Portal` folder (or zip it first and select the zip)
5. Enable the addon by checking the checkbox next to "Import-Export: Quixel Portal"

**Alternative method (for development):**
1. Copy the entire `Quixel Portal` folder to your Blender addons directory:
   - Windows: `%APPDATA%\Blender Foundation\Blender\4.2\scripts\addons\`
   - macOS: `~/Library/Application Support/Blender/4.2/scripts/addons/`
   - Linux: `~/.config/blender/4.2/scripts/addons/`
2. Restart Blender
3. Enable the addon in preferences

## Usage

1. In Blender, open the 3D Viewport
2. Press `N` to open the sidebar
3. Click on the `Quixel` tab
4. Click the `Open Quixel Portal` button
5. The Electron app will launch and navigate to Quixel Megascans
6. Log in to your Quixel account (this will be remembered for future sessions)

## How It Works

### Persistent Sessions

The Electron app uses a persistent partition (`persist:quixel`) which stores:
- Cookies
- Local storage
- Session storage
- Cache
- Other browser data

This means once you log in to Quixel, your session will be remembered even after closing and reopening the application.

### Navigation

The Electron browser automatically loads `https://quixel.com/megascans/home` on startup. While the current implementation focuses on the Quixel website, the navigation infrastructure is in place for future enhancements.

### Communication

- The Blender addon launches the Electron app as a separate process
- The Electron app runs independently and can remain open while using Blender
- IPC (Inter-Process Communication) is set up between the main and renderer processes for navigation controls

## Development

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

## Troubleshooting

### "Electron app not found" error
- Make sure you've installed npm dependencies in the `electron_app` directory
- Verify the `electron_app` folder exists in the addon directory

### "npm install" fails
- Ensure Node.js is installed (download from https://nodejs.org/)
- Try running the command prompt as administrator
- Clear npm cache: `npm cache clean --force`

### Addon doesn't appear in Blender
- Make sure you're using Blender 4.2.1 LTS or compatible version
- Check that the entire addon folder structure is intact
- Look for error messages in Blender's console (Window > Toggle System Console)

### Electron app opens but shows blank screen
- Check your internet connection
- Try reloading the page manually (this can be added as a feature)
- Check if quixel.com is accessible in a regular browser

## Requirements

- Blender 4.2.1 LTS (or compatible version)
- Python 3.11 (bundled with Blender)
- Node.js 16 or higher
- Internet connection

## License

MIT

## Future Enhancements

Potential features for future versions:
- Visual navigation toolbar within the Electron window
- URL address bar for manual navigation
- Bookmark functionality
- Download integration with Blender
- Multiple window support
- Custom keybindings
