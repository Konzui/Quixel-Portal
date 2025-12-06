# Quixel Bridge Panel - UI Location Guide

## Where to Find the Bridge Button

### Location
The Quixel Bridge panel is in the **3D Viewport Sidebar (N-Panel)**

### How to Access
1. Make sure you're in the **3D Viewport** (the main 3D view)
2. Press the **`N`** key on your keyboard to toggle the sidebar
3. Look for the **"Quixel"** tab at the top of the sidebar
4. Click on the **"Quixel"** tab

### Visual Layout

```
┌─────────────────────────────────────────────┐
│  3D Viewport                                │
│                                             │
│                                             │
│                       ┌────────────────────┐│
│                       │ Tool │ View │ Item ││
│                       │──────┴──────┴──────││
│                       │  👉 QUIXEL TAB 👈  ││
│                       ├────────────────────┤│
│                       │ Quixel Bridge      ││
│                       │                    ││
│                       │ Multi-Instance     ││
│                       │ Control            ││
│                       │                    ││
│                       │ ┌────────────────┐ ││
│                       │ │ Launch Bridge  │ ││
│                       │ │  & Claim Active│ ││ <- BIG BUTTON
│                       │ └────────────────┘ ││
│                       │                    ││
│                       │ Mode: Hub/Client   ││
│                       │ Status: Active     ││
│                       │ Instance: Blender  ││
│                       │                    ││
│                       │ Manual Import      ││
│                       │ Import FBX Manually││
│                       │                    ││
│                       │ How It Works       ││
│                       │ 1. Click button... ││
│                       │ 2. This instance...││
│                       │ 3. Export from...  ││
│                       │ 4. Assets appear...││
│                       └────────────────────┘│
└─────────────────────────────────────────────┘
        Sidebar (Press N to toggle)
```

### Panel Sections

**1. Multi-Instance Control** (Top Box)
   - 🎯 **"Launch Bridge & Claim Active"** button (LARGE, 2x height)
   - Shows current mode: "Hub (Primary)" or "Client (Secondary)"
   - Shows status: "Active (Receiving Imports)" or "Inactive"
   - Shows instance name: e.g., "Blender - scene.blend"

**2. Manual Import** (Middle Box)
   - "Import FBX Manually" button for manual imports

**3. How It Works** (Bottom Box)
   - Quick instructions for using the system

### What the Panel Tells You

#### Mode Indicators
- **🟢 "Mode: Hub (Primary)"** - You're the first instance, listening on port 24981
- **🔵 "Mode: Client (Secondary)"** - You're a secondary instance, connected to hub

#### Status Indicators
- **✅ "Status: Active (Receiving Imports)"** - Bridge exports come to THIS instance
- **⚪ "Status: Inactive"** - Bridge exports go to another instance

### Quick Start

**Single Blender Instance:**
1. Press `N` → Click "Quixel" tab
2. Click "Launch Bridge & Claim Active"
3. Export from Bridge → Assets appear

**Multiple Blender Instances:**
1. Open 2+ Blender instances
2. In the instance you want to receive imports:
   - Press `N` → Click "Quixel" tab
   - Click "Launch Bridge & Claim Active"
3. Export from Bridge → Assets appear in that instance

### Troubleshooting

**Can't see the "Quixel" tab?**
- Make sure the addon is enabled (Edit → Preferences → Add-ons)
- Reload Blender or disable/re-enable the addon
- Check the Blender console for error messages

**Panel is empty or shows errors?**
- Check console for initialization errors
- Ensure pywin32 is installed (see MULTI_INSTANCE_SETUP.md)
- Restart Blender

**Button doesn't work?**
- Check Blender console for error messages
- Verify Bridge.exe path exists (C:\Program Files\Bridge\Bridge.exe)
- Make sure you have permission to run Bridge
