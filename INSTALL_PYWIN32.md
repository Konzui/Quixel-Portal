# Installing pywin32 for Multi-Instance Support

The Quixel Portal addon will work WITHOUT pywin32, but you'll only be able to use it with a single Blender instance at a time.

To enable **multi-instance coordination** (where you can have multiple Blender instances and choose which one receives Bridge imports), you need to install pywin32.

## Option 1: Automatic Installation (Recommended)

1. **Right-click** `install_pywin32.bat`
2. Select **"Run as Administrator"**
3. Wait for installation to complete
4. Restart Blender

## Option 2: Manual Installation

1. **Open Command Prompt as Administrator**
   - Press Windows Key
   - Type "cmd"
   - Right-click "Command Prompt"
   - Select "Run as administrator"

2. **Run the installation command**

   For Blender 4.4:
   ```cmd
   "C:\Program Files\Blender Foundation\Blender 4.4\4.4\python\bin\python.exe" -m pip install pywin32
   ```

   For Blender 4.2:
   ```cmd
   "C:\Program Files\Blender Foundation\Blender 4.2\4.2\python\bin\python.exe" -m pip install pywin32
   ```

   For Blender 4.3:
   ```cmd
   "C:\Program Files\Blender Foundation\Blender 4.3\4.3\python\bin\python.exe" -m pip install pywin32
   ```

3. **Restart Blender**

## Verifying Installation

After installing pywin32 and restarting Blender:

1. Enable the Quixel Portal addon
2. Press `N` in the 3D viewport
3. Go to the "Quixel" tab
4. You should see **"Launch Bridge & Claim Active"** instead of **"Launch Bridge (Single Instance)"**
5. The panel should NOT show the warning "⚠️ Multi-instance disabled"

## Without pywin32

The addon will still work! You can:
- ✅ Launch Quixel Bridge
- ✅ Import assets from Bridge
- ✅ Use all import features (LOD, materials, etc.)

You CANNOT:
- ❌ Use multiple Blender instances simultaneously
- ❌ Choose which Blender instance receives imports
- ❌ Switch active instance between multiple Blenders

## Troubleshooting

### "Access Denied" Error
- Make sure you're running Command Prompt **as Administrator**
- Some systems require admin rights to install Python packages

### "No module named 'pip'"
- Blender's Python should come with pip
- Try reinstalling Blender

### Installation seems stuck
- Be patient - it can take 1-2 minutes
- Check your internet connection

### Still not working after installation
1. Close ALL Blender instances
2. Restart your computer
3. Open Blender fresh
4. Try again

### Wrong Blender version
- Adjust the path in the command to match YOUR Blender version
- The version number appears twice: `Blender 4.4\4.4\python`

## Optional: Install psutil

For better process detection (optional but recommended):

```cmd
"C:\Program Files\Blender Foundation\Blender 4.4\4.4\python\bin\python.exe" -m pip install psutil
```

This helps the addon detect when Blender instances crash or close unexpectedly.
