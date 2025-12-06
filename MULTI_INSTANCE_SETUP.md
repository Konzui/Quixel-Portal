# Multi-Instance Blender Support

This addon now supports multiple Blender instances with coordinated Quixel Bridge imports!

## How It Works

### Architecture

The addon uses a **Hub/Client** architecture:

1. **First Blender instance** (Hub):
   - Binds to port 24981 (Quixel Bridge communication port)
   - Runs an IPC server via Windows Named Pipe
   - Routes import requests to the active instance
   - Manages which instance is "active" for imports

2. **Additional Blender instances** (Clients):
   - Connect to the hub via IPC
   - Can claim "active" status by clicking the "Bridge" button
   - Receive import data routed from the hub

### User Workflow

1. **Open multiple Blender instances**
   - First instance automatically becomes the hub
   - Additional instances become clients

2. **Access the Quixel Bridge panel**
   - Open the 3D Viewport sidebar (press `N`)
   - Look for the "Quixel" tab
   - You'll see the "Quixel Bridge" panel

3. **Click "Launch Bridge & Claim Active"**
   - The large button in the panel
   - Makes that instance the active target for Bridge imports
   - Launches Quixel Bridge if not already running
   - Panel shows your current status (Hub/Client, Active/Inactive)

4. **Export from Bridge**
   - Bridge sends data to the hub (port 24981)
   - Hub routes to the active instance
   - Active instance shows the import preview

### Panel Location

The Quixel Bridge panel is located in:
- **3D Viewport** → Press `N` to open sidebar → **Quixel tab**

The panel shows:
- **Mode**: Hub (Primary) or Client (Secondary)
- **Status**: Active (Receiving Imports) or Inactive
- **Instance name**: Your current Blender instance
- **Launch Bridge button**: Large, prominent button to claim active status

## Installation Requirements

### Python Dependencies

The multi-instance system requires **pywin32** for Windows named pipe communication:

```bash
# Install pywin32 in Blender's Python
"C:\Program Files\Blender Foundation\Blender 4.2\4.2\python\bin\python.exe" -m pip install pywin32
```

**Note**: You may also need **psutil** for process detection (optional but recommended):

```bash
"C:\Program Files\Blender Foundation\Blender 4.2\4.2\python\bin\python.exe" -m pip install psutil
```

## Technical Details

### Communication Protocol

**IPC Messages** (between instances via named pipe `\\.\pipe\QuixelBridge_IPC`):
- `REGISTER`: Client registers with hub
- `UNREGISTER`: Client disconnects from hub
- `CLAIM_ACTIVE`: Client requests to become active instance
- `RELEASE_ACTIVE`: Client releases active status
- `HEARTBEAT`: Keep-alive ping
- `IMPORT_DATA`: Hub forwards Bridge data to active instance
- `ACK`: Acknowledgment
- `ERROR`: Error response

**Shared State** (file-based at `%TEMP%\QuixelBridge_Hub.json`):
- Hub process ID
- Active instance information
- Registered instances list
- Last heartbeat timestamp

### Failure Handling

- **Hub crash**: Secondary instances detect via heartbeat timeout (future: re-election)
- **Client crash**: Hub detects via process check, removes from registry
- **Active instance crash**: Hub clears active instance, waits for user to claim
- **Stale state**: Hub cleans up dead instances every 2 seconds

## Files Added

### Communication Layer
- `communication/shared_state.py`: File-based state management
- `communication/ipc_protocol.py`: IPC message protocol
- `communication/bridge_hub.py`: Hub instance (primary)
- `communication/bridge_client.py`: Client instance (secondary)
- `communication/bridge_coordinator.py`: Auto-detection of hub/client mode

### UI Layer
- `ui/bridge_launcher.py`: Bridge button operator
- `ui/import_toolbar.py`: Updated with Bridge button

### Modified Files
- `__init__.py`: Initialize coordinator and register Bridge operator
- `communication/quixel_bridge_socket.py`: Integrated with coordinator routing

## Troubleshooting

### Port 24981 Already in Use
- This is expected! The first Blender instance claims the port
- Additional instances automatically become clients
- Check console for "Running as CLIENT" vs "Running as HUB"

### Bridge Imports Going to Wrong Instance
- Click the "Bridge" button in the instance you want to receive imports
- The button claims active status for that instance
- You should see: "This Blender instance is now active for Bridge imports"

### Import Not Working
1. Check console messages for errors
2. Verify hub is running (first instance started)
3. Ensure pywin32 is installed
4. Check `%TEMP%\QuixelBridge_Hub.json` for state information

### State File Corruption
- Delete `%TEMP%\QuixelBridge_Hub.json`
- Restart all Blender instances
- First instance will recreate the file

## Future Enhancements

- Hub re-election if primary instance crashes
- Visual indicator of active instance in UI
- "Transfer active" between instances without clicking
- Multi-hub support for isolated project groups
- Bridge instance isolation (per-Blender Bridge configs)
