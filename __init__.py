bl_info = {
    "name": "Quixel Portal",
    "author": "Your Name",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "Topbar",
    "description": "Open Quixel Megascans Portal in dedicated browser",
    "category": "Import-Export",
}

import bpy
import bpy.utils.previews
import mathutils
import os
import subprocess
import sys
import json
import glob
import math
import uuid
import time
from pathlib import Path

# Try to import psutil for process verification
# If not available, we'll use a fallback method
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("⚠️ Quixel Portal: psutil not available, using fallback process verification")

# Global variable to store icons
custom_icons = None

# Track if we've registered in this session to prevent duplicates
_draw_function_registered = False

# Timer for checking import requests
_import_timer = None

# Track last button click time for debouncing
_last_portal_open_time = 0

# Store instance ID globally (per Blender process, not per scene)
# This persists across scene changes and ensures one ID per Blender instance
_blender_instance_id = None

def load_texture(nodes, tex_type, tex_path, color_space='sRGB'):
    """Load texture and create image texture node"""
    if not tex_path or not tex_path.exists():
        return None
    
    # Create image texture node
    tex_node = nodes.new(type='ShaderNodeTexImage')
    tex_node.location = (-600, -200 * len([n for n in nodes if isinstance(n, bpy.types.ShaderNodeTexImage)]))
    
    # Load image
    try:
        img = bpy.data.images.load(str(tex_path))
        img.colorspace_settings.name = color_space
        tex_node.image = img
        print(f"    ✅ Loaded {tex_type}: {tex_path.name}")
        return tex_node
    except Exception as e:
        print(f"    ❌ Failed to load {tex_type} texture {tex_path.name}: {e}")
        nodes.remove(tex_node)
        return None

def _draw_quixel_button_impl(self, context):
    """Internal implementation of the draw function"""
    global custom_icons
    layout = self.layout
    
    # Create button with custom icon if available
    if custom_icons:
        try:
            # Check if icon exists and get its ID
            if "quixel_logo" in custom_icons:
                icon_item = custom_icons["quixel_logo"]
                if hasattr(icon_item, 'icon_id') and icon_item.icon_id != 0:
                    layout.operator("quixel.open_portal", text="Quixel Portal", icon_value=icon_item.icon_id, emboss=True)
                    return
        except Exception as e:
            print(f"⚠️ Quixel Portal: Error accessing icon: {e}")
    
    # Fallback button without custom icon
    layout.operator("quixel.open_portal", text="Quixel Portal", icon='WORLD', emboss=True)

# Create a wrapper function with a unique identifier
# This allows us to identify our function even after module reloads
def draw_quixel_button(self, context):
    """Draw function to add Quixel Portal button to topbar"""
    _draw_quixel_button_impl(self, context)

# Mark the wrapper with a unique attribute for identification
draw_quixel_button._quixel_portal_id = "quixel_portal_button_v1"


class QUIXEL_OT_cleanup_requests(bpy.types.Operator):
    """Force cleanup of stuck import request files"""
    bl_idname = "quixel.cleanup_requests"
    bl_label = "Clear Stuck Import Requests"
    bl_options = {'REGISTER'}

    def execute(self, context):
        import tempfile

        try:
            temp_dir = Path(tempfile.gettempdir()) / "quixel_portal"
            request_file = temp_dir / "import_request.json"

            if request_file.exists():
                request_file.unlink()
                self.report({'INFO'}, "✅ Deleted stuck import request file")
                print(f"✅ Quixel Portal: Manually deleted import request file")
            else:
                self.report({'INFO'}, "No stuck request files found")
                print(f"ℹ️  Quixel Portal: No import request file found")

        except Exception as e:
            self.report({'ERROR'}, f"Failed to cleanup: {e}")
            print(f"❌ Quixel Portal: Manual cleanup failed: {e}")

        return {'FINISHED'}


class QUIXEL_OT_open_portal(bpy.types.Operator):
    """Open Quixel Portal in dedicated browser"""
    bl_idname = "quixel.open_portal"
    bl_label = "Open Quixel Portal"
    bl_options = {'REGISTER'}

    def execute(self, context):
        import tempfile
        global _last_portal_open_time, _blender_instance_id

        # ═══════════════════════════════════════════════════════════════
        # 🚦 DEBOUNCING - Prevent rapid clicks
        # ═══════════════════════════════════════════════════════════════
        current_time = time.time()
        time_since_last_click = current_time - _last_portal_open_time

        if time_since_last_click < 2.0:  # Ignore clicks within 2 seconds
            self.report({'WARNING'}, f"Please wait... (opening portal)")
            return {'CANCELLED'}

        _last_portal_open_time = current_time

        # ═══════════════════════════════════════════════════════════════
        # 🔑 INSTANCE ID - Use GLOBAL storage, not per-scene!
        # ═══════════════════════════════════════════════════════════════
        # CRITICAL: Instance ID must be global to the Blender PROCESS,
        # not per-scene, otherwise switching scenes or restarting Blender
        # will generate new IDs and launch multiple Electron instances!

        if not _blender_instance_id:
            # Generate NEW instance ID (only happens once per Blender session)
            instance_id = str(uuid.uuid4())
            _blender_instance_id = instance_id
            print(f"🔑 Quixel Portal: Generated new instance ID: {instance_id}")
        else:
            # Retrieve EXISTING instance ID from global variable
            instance_id = _blender_instance_id

        # Check if Electron is already running for this instance
        temp_dir = Path(tempfile.gettempdir()) / "quixel_portal"
        lock_file = temp_dir / f"electron_lock_{instance_id}.txt"

        if lock_file.exists():
            # Check if lock file is stale (older than 2 minutes)
            try:
                file_mtime = lock_file.stat().st_mtime
                file_age = time.time() - file_mtime

                if file_age > 120:  # 2 minutes
                    # Stale lock file - Electron probably crashed
                    print(f"⚠️ Quixel Portal: Stale lock file detected (age: {file_age:.0f}s), removing...")
                    lock_file.unlink()
                else:
                    # ═══════════════════════════════════════════════════════════════
                    # 🔍 PROCESS VERIFICATION - Check if Electron is actually running
                    # ═══════════════════════════════════════════════════════════════

                    # Read lock file to get PID
                    try:
                        with open(lock_file, 'r') as f:
                            lock_data = json.load(f)

                        electron_pid = lock_data.get('pid')

                        if electron_pid:
                            # Verify process is actually running
                            process_alive = False

                            if PSUTIL_AVAILABLE:
                                # Use psutil for accurate process verification
                                try:
                                    process = psutil.Process(electron_pid)
                                    # Check if it's actually our Electron process (not a different process with reused PID)
                                    process_name = process.name().lower()

                                    if 'electron' in process_name or 'quixel' in process_name:
                                        process_alive = True
                                        print(f"✅ Quixel Portal: Verified Electron process is alive (PID: {electron_pid})")
                                except psutil.NoSuchProcess:
                                    print(f"⚠️ Quixel Portal: Process {electron_pid} no longer exists")
                                except psutil.AccessDenied:
                                    # Can't access process info, assume it's alive
                                    process_alive = True
                                    print(f"⚠️ Quixel Portal: Cannot verify process {electron_pid} (access denied), assuming alive")
                            else:
                                # Fallback: Use OS-specific process check
                                if sys.platform == "win32":
                                    # Windows: Use tasklist command with better error handling
                                    try:
                                        # Use shell=True with encoding handling to avoid Unicode errors
                                        result = subprocess.run(
                                            f'tasklist /FI "PID eq {electron_pid}" /NH',
                                            shell=True,
                                            capture_output=True,
                                            text=True,
                                            encoding='cp850',  # Windows console encoding to avoid Unicode errors
                                            errors='ignore',   # Ignore decode errors
                                            timeout=3,
                                            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                                        )
                                        output = result.stdout.strip() if result.stdout else ""

                                        # Check if PID appears in output
                                        if str(electron_pid) in output and result.returncode == 0:
                                            process_alive = True
                                            print(f"✅ Quixel Portal: Process {electron_pid} is running (tasklist check)")
                                    except subprocess.TimeoutExpired:
                                        # Timeout - assume process is alive to be safe
                                        process_alive = True
                                    except UnicodeDecodeError:
                                        # Unicode decode error - assume process is alive
                                        process_alive = True
                                    except Exception:
                                        # If check fails, assume process is alive to be safe
                                        process_alive = True
                                else:
                                    # Linux/Mac: Use kill -0 signal
                                    try:
                                        os.kill(electron_pid, 0)  # Signal 0 doesn't kill, just checks if process exists
                                        process_alive = True
                                        print(f"✅ Quixel Portal: Process {electron_pid} is running (kill -0 check)")
                                    except OSError:
                                        pass  # Process is dead
                                    except Exception:
                                        # If check fails, assume process is alive to be safe
                                        process_alive = True

                            if not process_alive:
                                # Process is dead, remove stale lock file
                                print(f"🧹 Quixel Portal: Removing stale lock file (process is dead)")
                                lock_file.unlink()
                                # Continue to launch new instance below
                            else:
                                # ═══════════════════════════════════════════════════════════════
                                # 📤 SEND SHOW WINDOW SIGNAL + WAIT FOR CONFIRMATION
                                # ═══════════════════════════════════════════════════════════════

                                print(f"🔒 Quixel Portal: Electron already running for this instance")
                                print(f"👁️ Quixel Portal: Sending show window signal...")

                                # Create signal file to tell Electron to show window
                                signal_file = temp_dir / f"show_window_{instance_id}.txt"

                                # Create temp directory if it doesn't exist
                                if not temp_dir.exists():
                                    temp_dir.mkdir(parents=True, exist_ok=True)

                                # Write signal file with timestamp
                                with open(signal_file, 'w') as f:
                                    f.write(str(time.time()))

                                # ═══════════════════════════════════════════════════════════════
                                # ⏳ POLL FOR CONFIRMATION - Wait for Electron to delete signal
                                # ═══════════════════════════════════════════════════════════════

                                self.report({'INFO'}, "Showing Quixel Portal...")

                                # Poll for up to 3 seconds (30 checks * 100ms)
                                max_attempts = 30
                                for attempt in range(max_attempts):
                                    time.sleep(0.1)  # Wait 100ms between checks

                                    if not signal_file.exists():
                                        # Signal was processed by Electron!
                                        print(f"✅ Quixel Portal: Signal acknowledged by Electron (took {(attempt + 1) * 100}ms)")
                                        self.report({'INFO'}, "Quixel Portal window shown!")
                                        return {'FINISHED'}

                                # Timeout - signal was not processed
                                print(f"⚠️ Quixel Portal: Timeout waiting for signal acknowledgment")
                                print(f"🧹 Quixel Portal: Removing unresponsive lock file")

                                # Clean up signal file
                                if signal_file.exists():
                                    signal_file.unlink()

                                # Remove lock file and continue to launch new instance
                                lock_file.unlink()
                        else:
                            # No PID in lock file, might be old format
                            print(f"⚠️ Quixel Portal: Lock file has no PID, assuming stale")
                            lock_file.unlink()

                    except (json.JSONDecodeError, KeyError) as e:
                        print(f"⚠️ Quixel Portal: Failed to read lock file: {e}")
                        # Lock file is corrupted, remove it
                        lock_file.unlink()

            except Exception as e:
                print(f"⚠️ Quixel Portal: Error checking lock file: {e}")
                # Continue to launch new instance if check failed

        # ═══════════════════════════════════════════════════════════════
        # 🚀 LAUNCH NEW ELECTRON INSTANCE
        # ═══════════════════════════════════════════════════════════════

        print(f"🚀 Quixel Portal: Launching new Electron instance...")

        # Get the addon directory
        addon_dir = Path(__file__).parent
        electron_app_dir = addon_dir / "electron_app"

        # Path to the built executable
        exe_path = electron_app_dir / "build" / "win-unpacked" / "Quixel Portal.exe"

        # Check if executable exists
        if exe_path.exists():
            # Use the built executable with instance ID argument
            try:
                subprocess.Popen(
                    [str(exe_path), '--blender-instance', instance_id],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                self.report({'INFO'}, "Quixel Portal launched!")
                return {'FINISHED'}
            except Exception as e:
                self.report({'ERROR'}, f"Failed to launch Quixel Portal: {str(e)}")
                return {'CANCELLED'}
        else:
            # Fallback to npm start if exe doesn't exist
            if not electron_app_dir.exists():
                self.report({'ERROR'}, "Electron app not found. Please ensure the addon is properly installed.")
                return {'CANCELLED'}

            node_modules = electron_app_dir / "node_modules"
            if not node_modules.exists():
                self.report({'ERROR'}, "Electron app not built. Please run 'npm install' in the electron_app directory.")
                return {'CANCELLED'}

            try:
                if sys.platform == "win32":
                    npm_cmd = "npm.cmd"
                else:
                    npm_cmd = "npm"

                subprocess.Popen(
                    [npm_cmd, "start", "--", "--blender-instance", instance_id],
                    cwd=str(electron_app_dir),
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                self.report({'INFO'}, "Quixel Portal launched!")
                return {'FINISHED'}

            except Exception as e:
                self.report({'ERROR'}, f"Failed to launch Quixel Portal: {str(e)}")
                return {'CANCELLED'}


class QUIXEL_OT_import_fbx(bpy.types.Operator):
    """Import FBX files from a directory"""
    bl_idname = "quixel.import_fbx"
    bl_label = "Import Quixel Asset"
    bl_options = {'REGISTER', 'UNDO'}

    directory: bpy.props.StringProperty(
        name="Asset Directory",
        description="Directory containing the downloaded asset",
        subtype='DIR_PATH'
    )

    thumbnail_path: bpy.props.StringProperty(
        name="Thumbnail Path",
        description="Path to the asset thumbnail image",
        default=""
    )

    asset_name_override: bpy.props.StringProperty(
        name="Asset Name",
        description="Override asset name from request",
        default=""
    )
    
    def _find_json_file(self, asset_dir):
        """Find the JSON metadata file in the asset directory"""
        json_files = list(asset_dir.glob("*.json"))
        if not json_files:
            # Also check subdirectories
            json_files = list(asset_dir.glob("**/*.json"))
        
        # Prefer files that look like metadata (not config files)
        for json_file in json_files:
            if json_file.stem not in ['config', 'settings', 'package']:
                return json_file
        
        # Return first JSON file if no specific one found
        return json_files[0] if json_files else None
    
    def _get_name_from_json(self, asset_dir):
        """Extract name from JSON file following the naming convention"""
        json_file = self._find_json_file(asset_dir)
        if not json_file:
            return None, None
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            
            # Get name from semanticTags.name
            semantic_tags = json_data.get('semanticTags', {})
            semantic_name = semantic_tags.get('name', '')
            
            if not semantic_name:
                return None, None
            
            # Replace spaces with underscores and convert to lowercase
            semantic_name_clean = semantic_name.replace(' ', '_').lower()
            
            # Get JSON filename without extension and convert to lowercase
            json_stem = json_file.stem.lower()
            
            # Construct name: quixel_{semantic_name}_{json_filename}_A (all lowercase)
            name = f"quixel_{semantic_name_clean}_{json_stem}_a"
            
            return name, json_file
        except Exception as e:
            print(f"  ⚠️ Failed to parse JSON file {json_file}: {e}")
            return None, None
    
    def _get_material_name_from_json(self, asset_dir, json_filename):
        """Extract material name from JSON file following the naming convention"""
        name, _ = self._get_name_from_json(asset_dir)
        return name

    def _detect_variation_number(self, obj_name):
        """
        Detect variation NUMBER from object name (not the final suffix).
        This extracts the numeric identifier like _00, _01, _02 from filenames like:
        Aset_building__M_wkkmfa3dw_00_LOD0 → 0
        Aset_building__M_wkkmfa3dw_01_LOD0 → 1

        Returns an integer representing the variation index.
        Returns 0 as default if no variation detected.
        """
        import re

        # Remove LOD suffix first to isolate the variation suffix
        name_without_lod = re.sub(r'_?LOD\d+$', '', obj_name, flags=re.IGNORECASE)

        # Pattern 1: _A, _B, _C (case insensitive, single letter at end)
        # Convert to index: a=0, b=1, c=2, etc.
        match = re.search(r'_([a-z])$', name_without_lod, re.IGNORECASE)
        if match:
            letter = match.group(1).lower()
            index = ord(letter) - ord('a')
            print(f"    🔍 Variation detection: '{obj_name}' -> index {index} (from letter '_{letter}')")
            return index

        # Pattern 2: _01, _02, _03 (numerical suffixes, 2 digits at end)
        match = re.search(r'_(\d{2})$', name_without_lod)
        if match:
            index = int(match.group(1))
            print(f"    🔍 Variation detection: '{obj_name}' -> index {index} (from '_{match.group(1)}')")
            return index

        # Pattern 3: Single digit at end (1, 2, 3)
        match = re.search(r'_(\d)$', name_without_lod)
        if match:
            index = int(match.group(1))
            print(f"    🔍 Variation detection: '{obj_name}' -> index {index} (from '_{match.group(1)}')")
            return index

        # Default: first variation
        print(f"    🔍 Variation detection: '{obj_name}' -> index 0 (default, no pattern found)")
        return 0

    def _index_to_letter_suffix(self, index):
        """
        Convert a numeric index to a letter suffix.
        0 → 'a'
        1 → 'b'
        25 → 'z'
        26 → 'aa'
        27 → 'ab'
        etc.
        """
        if index < 0:
            index = 0

        suffix = ''
        index_copy = index

        # Handle indices 0-25 (a-z)
        if index < 26:
            suffix = chr(ord('a') + index)
        else:
            # Handle indices >= 26 (aa, ab, ac, etc.)
            # Convert to base-26 representation
            while index >= 0:
                suffix = chr(ord('a') + (index % 26)) + suffix
                index = index // 26 - 1
                if index < 0:
                    break

        print(f"    🔤 Index {index_copy} → suffix '{suffix}'")
        return suffix

    def _group_objects_by_variation(self, objects):
        """
        Group objects by their variation index, then convert to letter suffixes.
        Returns dict: {variation_letter_suffix: [list of objects]}

        Example:
        Input objects: Aset_building_00_LOD0, Aset_building_01_LOD0, Aset_building_02_LOD0
        Detected indices: 0, 1, 2
        Output keys: 'a', 'b', 'c'
        """
        # First, group by numeric index
        index_groups = {}

        print(f"\n  🔍 GROUPING {len(objects)} OBJECTS BY VARIATION:")

        for obj in objects:
            # Only process mesh objects
            if obj.type != 'MESH' or not obj.data:
                print(f"    ⏭️  Skipping non-mesh object: {obj.name}")
                continue

            # Detect the variation index (numeric)
            variation_index = self._detect_variation_number(obj.name)

            if variation_index not in index_groups:
                index_groups[variation_index] = []

            index_groups[variation_index].append(obj)

        # Now convert indices to letter suffixes
        # Sort indices to ensure consistent ordering
        sorted_indices = sorted(index_groups.keys())

        variations = {}

        print(f"\n  🔤 CONVERTING INDICES TO LETTER SUFFIXES:")
        for variation_index in sorted_indices:
            # Convert index to letter suffix (0→a, 1→b, 25→z, 26→aa, etc.)
            letter_suffix = self._index_to_letter_suffix(variation_index)
            variations[letter_suffix] = index_groups[variation_index]

        print(f"\n  📊 VARIATION SUMMARY:")
        for suffix in sorted(variations.keys()):
            mesh_names = [obj.name for obj in variations[suffix]]
            print(f"    Variation '_{suffix}': {len(variations[suffix])} meshes")
            for name in mesh_names:
                print(f"      - {name}")

        return variations

    def _calculate_variation_bbox(self, mesh_objects):
        """
        Calculate the combined bounding box of all meshes in a variation.
        Returns dictionary with min_x, max_x, width, height, depth in world space units.
        This should be called BEFORE parenting to attach root.
        """
        if not mesh_objects:
            print(f"    ⚠️  No mesh objects for bbox calculation")
            return {'min_x': 0.0, 'max_x': 0.0, 'width': 0.0, 'height': 0.0, 'depth': 0.0}

        # Get world space bounding box coordinates for all objects
        all_coords = []
        for obj in mesh_objects:
            if obj.type == 'MESH' and obj.data:
                # Get bounding box in world space
                for corner in obj.bound_box:
                    world_coord = obj.matrix_world @ mathutils.Vector(corner)
                    all_coords.append(world_coord)

        if not all_coords:
            print(f"    ⚠️  No valid coordinates for bbox calculation")
            return {'min_x': 0.0, 'max_x': 0.0, 'width': 0.0, 'height': 0.0, 'depth': 0.0}

        # Calculate min and max coordinates
        min_x = min(coord.x for coord in all_coords)
        max_x = max(coord.x for coord in all_coords)
        min_y = min(coord.y for coord in all_coords)
        max_y = max(coord.y for coord in all_coords)
        min_z = min(coord.z for coord in all_coords)
        max_z = max(coord.z for coord in all_coords)

        width = max_x - min_x
        height = max_y - min_y
        depth = max_z - min_z

        print(f"    📏 BOUNDING BOX: width={width:.2f}, height={height:.2f}, depth={depth:.2f}")
        print(f"       X: [{min_x:.2f}, {max_x:.2f}]")
        print(f"       Y: [{min_y:.2f}, {max_y:.2f}]")
        print(f"       Z: [{min_z:.2f}, {max_z:.2f}]")

        return {
            'min_x': min_x,
            'max_x': max_x,
            'width': width,
            'height': height,
            'depth': depth
        }

    def _apply_transforms_to_objects(self, objects):
        """
        Apply scale and rotation to all objects.
        This bakes the transforms into the mesh geometry.
        CRITICAL: Must be done BEFORE parenting to attach roots!
        """
        print(f"\n  🔧 APPLYING TRANSFORMS TO {len(objects)} OBJECTS:")

        failed_objects = []

        for obj in objects:
            if obj.type != 'MESH' or not obj.data:
                print(f"    ⏭️  Skipping non-mesh: {obj.name}")
                continue

            # Store original values for debug
            orig_scale = obj.scale.copy()
            orig_rotation = obj.rotation_euler.copy()

            print(f"    🔧 Object: {obj.name}")
            print(f"       BEFORE: scale={orig_scale}, rotation=({math.degrees(orig_rotation.x):.1f}°, {math.degrees(orig_rotation.y):.1f}°, {math.degrees(orig_rotation.z):.1f}°)")

            # Select object
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj

            # Apply BOTH scale AND rotation (CRITICAL FIX!)
            # This bakes them into the mesh vertex positions
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

            print(f"       AFTER:  scale={obj.scale}, rotation=({math.degrees(obj.rotation_euler.x):.1f}°, {math.degrees(obj.rotation_euler.y):.1f}°, {math.degrees(obj.rotation_euler.z):.1f}°)")

            # Verify transforms are now neutral
            scale_ok = all(abs(s - 1.0) < 0.001 for s in obj.scale)
            rotation_ok = all(abs(r) < 0.001 for r in obj.rotation_euler)

            if scale_ok and rotation_ok:
                print(f"       ✅ Transforms applied and baked into mesh geometry")
            else:
                print(f"       ⚠️  WARNING: Transforms not fully neutral!")
                print(f"          Scale: {obj.scale} (expected: ~1.0, 1.0, 1.0)")
                print(f"          Rotation: {obj.rotation_euler} (expected: ~0, 0, 0)")
                failed_objects.append(obj.name)

        # Clear selection
        bpy.ops.object.select_all(action='DESELECT')

        # Report any failures
        if failed_objects:
            print(f"\n  ⚠️  {len(failed_objects)} object(s) have non-neutral transforms:")
            for name in failed_objects:
                print(f"     - {name}")
        else:
            print(f"\n  ✅ All transforms verified as neutral (scale=1, rotation=0)")

    def _create_surface_material(self, asset_dir, context):
        """Create a material for a surface asset from JSON and textures"""
        import re
        
        # Find JSON file
        json_file = self._find_json_file(asset_dir)
        if not json_file:
            print(f"  ⚠️ No JSON file found in {asset_dir}")
            return False
        
        # Get material name from JSON
        material_name = self._get_material_name_from_json(asset_dir, json_file)
        if not material_name:
            print(f"  ⚠️ Could not extract material name from JSON")
            return False
        
        # Find all texture files
        texture_extensions = ['.png', '.jpg', '.jpeg', '.tga', '.tif', '.tiff', '.exr']
        texture_files = []
        for ext in texture_extensions:
            texture_files.extend(asset_dir.glob(f"**/*{ext}"))
            texture_files.extend(asset_dir.glob(f"**/*{ext.upper()}"))
        
        if not texture_files:
            print(f"  ⚠️ No texture files found in {asset_dir}")
            return False
        
        # Check if material already exists
        if material_name in bpy.data.materials:
            mat = bpy.data.materials[material_name]
            bpy.data.materials.remove(mat, do_unlink=True)
        
        # Create new material
        mat = bpy.data.materials.new(name=material_name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        # Get or create Principled BSDF
        bsdf = nodes.get("Principled BSDF")
        if not bsdf:
            bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
        
        # Find textures by type
        textures = {}
        for tex_file in texture_files:
            filename_lower = tex_file.stem.lower()
            
            if 'albedo' in filename_lower or 'diffuse' in filename_lower or 'color' in filename_lower:
                textures['albedo'] = tex_file
            elif 'roughness' in filename_lower or 'rough' in filename_lower:
                textures['roughness'] = tex_file
            elif 'normal' in filename_lower and 'gl' not in filename_lower:
                textures['normal'] = tex_file
            elif 'displacement' in filename_lower or 'height' in filename_lower:
                textures['displacement'] = tex_file
            elif 'metallic' in filename_lower or 'metalness' in filename_lower:
                textures['metallic'] = tex_file
            elif 'opacity' in filename_lower or 'alpha' in filename_lower or 'mask' in filename_lower:
                textures['opacity'] = tex_file
        
        # Load Albedo texture
        if 'albedo' in textures:
            albedo_node = load_texture(nodes, 'Albedo', textures['albedo'], 'sRGB')
            if albedo_node:
                links.new(albedo_node.outputs['Color'], bsdf.inputs['Base Color'])
        
        # Load Roughness texture
        if 'roughness' in textures:
            roughness_node = load_texture(nodes, 'Roughness', textures['roughness'], 'Non-Color')
            if roughness_node:
                links.new(roughness_node.outputs['Color'], bsdf.inputs['Roughness'])
        
        # Load Normal texture
        if 'normal' in textures:
            normal_node = load_texture(nodes, 'Normal', textures['normal'], 'Non-Color')
            if normal_node:
                # Create normal map node
                normal_map_node = nodes.new(type='ShaderNodeNormalMap')
                normal_map_node.location = (-300, -400)
                links.new(normal_node.outputs['Color'], normal_map_node.inputs['Color'])
                links.new(normal_map_node.outputs['Normal'], bsdf.inputs['Normal'])
        
        # Load Displacement texture
        if 'displacement' in textures:
            displacement_node = load_texture(nodes, 'Displacement', textures['displacement'], 'Non-Color')
            if displacement_node:
                # Create displacement node
                displacement_shader = nodes.new(type='ShaderNodeDisplacement')
                displacement_shader.location = (-300, -600)
                links.new(displacement_node.outputs['Color'], displacement_shader.inputs['Height'])
                
                # Connect to material output
                output = nodes.get("Material Output")
                if output:
                    links.new(displacement_shader.outputs['Displacement'], output.inputs['Displacement'])
        
        # Load Metallic texture
        if 'metallic' in textures:
            metallic_node = load_texture(nodes, 'Metallic', textures['metallic'], 'Non-Color')
            if metallic_node:
                links.new(metallic_node.outputs['Color'], bsdf.inputs['Metallic'])
        
        # Load Opacity/Alpha/Mask texture
        if 'opacity' in textures:
            opacity_node = load_texture(nodes, 'Opacity', textures['opacity'], 'Non-Color')
            if opacity_node:
                # Connect to Alpha input of Principled BSDF
                links.new(opacity_node.outputs['Color'], bsdf.inputs['Alpha'])
                # Enable alpha blending for the material
                mat.blend_method = 'BLEND'
                print(f"    ✅ Enabled alpha blending for material")
        
        # Assign material to selected objects if any are selected
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if selected_objects:
            for obj in selected_objects:
                # Assign material to object
                if len(obj.data.materials) == 0:
                    obj.data.materials.append(mat)
                else:
                    obj.data.materials[0] = mat
                print(f"    ✅ Assigned material to selected object: {obj.name}")
        else:
            print(f"  ℹ️  No mesh objects selected - material created but not assigned")
        
        print(f"  🎨 Created surface material: {material_name}")
        return True
    
    def _get_textures_for_variation(self, asset_dir, variation_suffix, import_groups):
        """
        Extract texture paths organized by LOD level for a specific variation.
        
        Args:
            asset_dir: Path to the asset directory
            variation_suffix: Variation suffix (e.g., 'a', 'b', '00', '01')
            import_groups: List of import groups containing FBX files and objects
        
        Returns:
            Dictionary structure: {lod_level: {'albedo': path, 'roughness': path, ...}}
        """
        import re
        
        # Find all texture files in the asset directory
        texture_extensions = ['.png', '.jpg', '.jpeg', '.tga', '.tif', '.tiff', '.exr']
        texture_files = []
        for ext in texture_extensions:
            texture_files.extend(asset_dir.glob(f"**/*{ext}"))
            texture_files.extend(asset_dir.glob(f"**/*{ext.upper()}"))
        
        if not texture_files:
            return {}
        
        # Pattern to extract LOD level from texture filename
        lod_pattern = re.compile(r'_?LOD(\d+)', re.IGNORECASE)
        
        # Pattern to match variation suffix in filename
        # Try both letter format (_a, _b) and numeric format (_00, _01)
        variation_patterns = []
        if variation_suffix.isdigit():
            # Numeric variation: try _00, _01, etc.
            variation_patterns.append(re.compile(rf'_{variation_suffix}(?:_|LOD|$)', re.IGNORECASE))
            # Also try without underscore prefix
            variation_patterns.append(re.compile(rf'{variation_suffix}(?:_|LOD|$)', re.IGNORECASE))
        else:
            # Letter variation: try _a, _b, etc.
            variation_patterns.append(re.compile(rf'_{variation_suffix}(?:_|LOD|$)', re.IGNORECASE))
            # Also try without underscore prefix
            variation_patterns.append(re.compile(rf'{variation_suffix}(?:_|LOD|$)', re.IGNORECASE))
        
        # Group textures by LOD level and type
        # Structure: {lod_level: {'albedo': path, 'roughness': path, 'normal': path, 'metallic': path}}
        lod_textures = {}
        
        for tex_file in texture_files:
            filename_lower = tex_file.stem.lower()
            
            # Check if this texture belongs to this variation
            # Strategy:
            # 1. If texture has no variation identifier → shared (belongs to all variations)
            # 2. If texture has variation identifier matching this variation → include it
            # 3. If texture has variation identifier for different variation → exclude it
            
            belongs_to_variation = True
            
            # Check if filename contains any variation identifier (letter or numeric)
            # Pattern to match common variation formats: _a, _b, _00, _01, etc.
            any_variation_pattern = re.compile(r'(_[a-z]{1,2}|_\d{1,2})(?:_|LOD|$)', re.IGNORECASE)
            variation_matches = list(any_variation_pattern.finditer(tex_file.stem))
            
            if variation_matches:
                # Texture has variation identifier(s) - check if it matches this variation
                has_matching_variation = any(pattern.search(tex_file.stem) for pattern in variation_patterns)
                if not has_matching_variation:
                    # Texture has variation identifier but doesn't match this variation
                    belongs_to_variation = False
            # If no variation identifier found, texture is shared (belongs to all variations)
            
            if not belongs_to_variation:
                continue
            
            # Extract LOD level
            lod_match = lod_pattern.search(tex_file.stem)
            lod_level = lod_match.group(1) if lod_match else "0"
            
            if lod_level not in lod_textures:
                lod_textures[lod_level] = {}
            
            # Identify texture type by filename
            if 'albedo' in filename_lower or 'diffuse' in filename_lower or 'color' in filename_lower:
                lod_textures[lod_level]['albedo'] = tex_file
            elif 'roughness' in filename_lower or 'rough' in filename_lower:
                lod_textures[lod_level]['roughness'] = tex_file
            elif 'normal' in filename_lower and 'gl' not in filename_lower:
                lod_textures[lod_level]['normal'] = tex_file
            elif 'metallic' in filename_lower or 'metalness' in filename_lower:
                lod_textures[lod_level]['metallic'] = tex_file
            elif 'opacity' in filename_lower or 'alpha' in filename_lower or 'mask' in filename_lower:
                lod_textures[lod_level]['opacity'] = tex_file
        
        # Get all LOD levels that have objects (from FBX imports)
        lod_levels_with_objects = set()
        for import_group in import_groups:
            fbx_file = import_group['fbx_file']
            lod_match = lod_pattern.search(fbx_file.stem)
            lod_level = lod_match.group(1) if lod_match else "0"
            lod_levels_with_objects.add(lod_level)
        
        # Fill in missing LOD levels with textures from previous available LOD
        # Sort LOD levels numerically
        all_lod_levels = sorted(lod_levels_with_objects, key=lambda x: int(x))
        texture_types = ['albedo', 'roughness', 'normal', 'metallic', 'opacity']
        
        # For each LOD level that has objects, ensure it has textures
        # Use textures from the most recent previous LOD level that has that texture type
        for lod_level in all_lod_levels:
            if lod_level not in lod_textures:
                lod_textures[lod_level] = {}
            
            # For each texture type, find the most recent previous LOD that has it
            for tex_type in texture_types:
                if tex_type not in lod_textures[lod_level]:
                    # Look backwards through LOD levels to find the most recent one with this texture
                    current_lod_num = int(lod_level)
                    for prev_lod_num in range(current_lod_num - 1, -1, -1):
                        prev_lod_str = str(prev_lod_num)
                        if prev_lod_str in lod_textures and tex_type in lod_textures[prev_lod_str]:
                            lod_textures[lod_level][tex_type] = lod_textures[prev_lod_str][tex_type]
                            break
        
        return lod_textures
    
    def _compare_texture_sets(self, texture_sets):
        """
        Compare texture sets across variations to determine if they are identical.
        
        Args:
            texture_sets: Dictionary mapping variation_suffix to texture dict
                         {variation_suffix: {lod_level: {'albedo': path, ...}}}
        
        Returns:
            Tuple (are_identical, shared_textures)
            - are_identical: True if all variations use the same textures
            - shared_textures: The shared texture set if identical, None otherwise
        """
        if not texture_sets or len(texture_sets) == 0:
            return True, None
        
        if len(texture_sets) == 1:
            # Only one variation, so textures are "shared" by default
            return True, list(texture_sets.values())[0]
        
        # Get all variation suffixes
        variation_suffixes = list(texture_sets.keys())
        
        # Compare first variation with all others
        first_variation = variation_suffixes[0]
        first_textures = texture_sets[first_variation]
        
        # Compare each LOD level
        for variation_suffix in variation_suffixes[1:]:
            other_textures = texture_sets[variation_suffix]
            
            # Get all LOD levels from both
            all_lod_levels = set(list(first_textures.keys()) + list(other_textures.keys()))
            
            for lod_level in all_lod_levels:
                first_lod = first_textures.get(lod_level, {})
                other_lod = other_textures.get(lod_level, {})
                
                # Compare texture types
                texture_types = ['albedo', 'roughness', 'normal', 'metallic', 'opacity']
                for tex_type in texture_types:
                    first_path = first_lod.get(tex_type)
                    other_path = other_lod.get(tex_type)
                    
                    # Both missing is OK (they match)
                    if first_path is None and other_path is None:
                        continue
                    
                    # One missing and one present means they differ
                    if first_path is None or other_path is None:
                        return False, None
                    
                    # Compare file paths (normalize for comparison)
                    first_path_str = str(first_path.resolve()) if first_path else None
                    other_path_str = str(other_path.resolve()) if other_path else None
                    
                    if first_path_str != other_path_str:
                        return False, None
        
        # All variations have identical textures
        return True, first_textures
    
    def _get_texture_hash(self, textures):
        """
        Create a hash string from texture paths for caching materials.

        Args:
            textures: Dictionary of texture paths by type: {'albedo': path, 'roughness': path, ...}

        Returns:
            Hash string representing the texture combination
        """
        import hashlib

        # Create a sorted string of all texture paths
        texture_types = ['albedo', 'roughness', 'normal', 'metallic', 'opacity']
        path_strings = []

        for tex_type in texture_types:
            if tex_type in textures and textures[tex_type]:
                # Use resolved path for consistent hashing
                path_strings.append(f"{tex_type}:{str(textures[tex_type].resolve())}")
            else:
                path_strings.append(f"{tex_type}:none")

        # Join and hash
        combined = "|".join(path_strings)
        hash_obj = hashlib.md5(combined.encode())
        return hash_obj.hexdigest()[:12]  # Use first 12 chars for readability

    def _create_material_from_textures(self, material_name, textures, context):
        """
        Create a material from texture paths and return it.

        Args:
            material_name: Name for the material
            textures: Dictionary of texture paths by type: {'albedo': path, 'roughness': path, ...}
            context: Blender context

        Returns:
            Created material object
        """
        # Check if material already exists
        if material_name in bpy.data.materials:
            mat = bpy.data.materials[material_name]
            bpy.data.materials.remove(mat, do_unlink=True)

        # Create new material
        mat = bpy.data.materials.new(name=material_name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        # Get or create Principled BSDF
        bsdf = nodes.get("Principled BSDF")
        if not bsdf:
            bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')

        # Load Albedo texture
        if 'albedo' in textures and textures['albedo']:
            albedo_node = load_texture(nodes, 'Albedo', textures['albedo'], 'sRGB')
            if albedo_node:
                links.new(albedo_node.outputs['Color'], bsdf.inputs['Base Color'])

        # Load Roughness texture
        if 'roughness' in textures and textures['roughness']:
            roughness_node = load_texture(nodes, 'Roughness', textures['roughness'], 'Non-Color')
            if roughness_node:
                links.new(roughness_node.outputs['Color'], bsdf.inputs['Roughness'])

        # Load Normal texture
        if 'normal' in textures and textures['normal']:
            normal_node = load_texture(nodes, 'Normal', textures['normal'], 'Non-Color')
            if normal_node:
                # Create normal map node
                normal_map_node = nodes.new(type='ShaderNodeNormalMap')
                normal_map_node.location = (-300, -400)
                links.new(normal_node.outputs['Color'], normal_map_node.inputs['Color'])
                links.new(normal_map_node.outputs['Normal'], bsdf.inputs['Normal'])

        # Load Metallic texture
        if 'metallic' in textures and textures['metallic']:
            metallic_node = load_texture(nodes, 'Metallic', textures['metallic'], 'Non-Color')
            if metallic_node:
                links.new(metallic_node.outputs['Color'], bsdf.inputs['Metallic'])

        # Load Opacity/Alpha/Mask texture
        if 'opacity' in textures and textures['opacity']:
            opacity_node = load_texture(nodes, 'Opacity', textures['opacity'], 'Non-Color')
            if opacity_node:
                # Connect to Alpha input of Principled BSDF
                links.new(opacity_node.outputs['Color'], bsdf.inputs['Alpha'])
                # Enable alpha blending for the material
                mat.blend_method = 'BLEND'
                print(f"    ✅ Enabled alpha blending for material")

        print(f"  🎨 Created material: {material_name}")
        return mat
    
    def _create_materials_for_all_variations(self, asset_dir, base_name, attach_root_base_name, variations, all_import_groups, context):
        """
        Create materials for all variations using hash-based caching to optimize material reuse.

        Args:
            asset_dir: Path to the asset directory
            base_name: Base name for the asset
            attach_root_base_name: Base name for attach roots (without variation suffix)
            variations: Dictionary mapping variation_suffix to list of objects
            all_import_groups: List of all import groups (FBX files and their objects)
            context: Blender context
        """
        import re

        print(f"\n    🎨 CREATING MATERIALS WITH HASH-BASED CACHING:")

        lod_pattern = re.compile(r'_?LOD(\d+)', re.IGNORECASE)

        # Get all LOD levels from import groups
        all_lod_levels = set()
        for import_group in all_import_groups:
            fbx_file = import_group['fbx_file']
            lod_match = lod_pattern.search(fbx_file.stem)
            lod_level = lod_match.group(1) if lod_match else "0"
            all_lod_levels.add(lod_level)
        all_lod_levels = sorted(all_lod_levels, key=lambda x: int(x))

        # Material cache: {texture_hash: material_object}
        material_cache = {}

        # Process each variation
        for variation_suffix in sorted(variations.keys()):
            print(f"\n      🎨 Processing materials for variation '_{variation_suffix}':")

            # Get textures for this variation
            variation_textures = self._get_textures_for_variation(asset_dir, variation_suffix, all_import_groups)
            variation_objects = variations[variation_suffix]
            attach_root_name = f"{attach_root_base_name}_{variation_suffix}"

            # Create mapping of objects to LOD levels for this variation
            lod_objects = {}
            for import_group in all_import_groups:
                fbx_file = import_group['fbx_file']
                objects = import_group.get('objects', [])

                # Extract LOD level from FBX filename
                lod_match = lod_pattern.search(fbx_file.stem)
                lod_level = lod_match.group(1) if lod_match else "0"

                # Only include objects that belong to this variation
                for obj in objects:
                    if obj in variation_objects and obj.type == 'MESH' and obj.data:
                        if lod_level not in lod_objects:
                            lod_objects[lod_level] = []
                        lod_objects[lod_level].append(obj)

            # Process each LOD level
            for lod_level in all_lod_levels:
                if lod_level not in variation_textures:
                    continue

                textures = variation_textures[lod_level]

                # Calculate texture hash
                texture_hash = self._get_texture_hash(textures)

                # Check if material already exists in cache
                if texture_hash in material_cache:
                    # Reuse existing material
                    mat = material_cache[texture_hash]
                    print(f"         ♻️  LOD{lod_level}: Reusing material '{mat.name}' (hash: {texture_hash})")
                else:
                    # Create new material
                    material_name = f"{attach_root_name}_LOD{lod_level}"
                    mat = self._create_material_from_textures(material_name, textures, context)
                    material_cache[texture_hash] = mat
                    print(f"         ✨ LOD{lod_level}: Created new material '{material_name}' (hash: {texture_hash})")

                # Assign material to objects from this LOD level
                if lod_level in lod_objects:
                    for obj in lod_objects[lod_level]:
                        # Clear all existing materials (including temporary MATID materials from FBX import)
                        obj.data.materials.clear()
                        # Assign our custom material
                        obj.data.materials.append(mat)
                        print(f"            ✅ Assigned to: {obj.name}")

        # Summary
        unique_materials = len(material_cache)
        total_variations = len(variations)
        total_lods = len(all_lod_levels)
        max_possible = total_variations * total_lods

        print(f"\n    📊 MATERIAL OPTIMIZATION SUMMARY:")
        print(f"       Created {unique_materials} unique material(s) for {total_variations} variation(s) × {total_lods} LOD(s)")
        print(f"       Saved {max_possible - unique_materials} redundant material(s) ({100 * (1 - unique_materials/max(max_possible, 1)):.1f}% reduction)")
    
    def _create_materials_for_asset(self, asset_dir, base_name, attach_root_name, import_groups, variation_objects, context):
        """Create materials and assign textures for each LOD level within a variation"""
        import re
        
        # Find all texture files in the asset directory
        texture_extensions = ['.png', '.jpg', '.jpeg', '.tga', '.tif', '.tiff', '.exr']
        texture_files = []
        for ext in texture_extensions:
            texture_files.extend(asset_dir.glob(f"**/*{ext}"))
            texture_files.extend(asset_dir.glob(f"**/*{ext.upper()}"))
        
        if not texture_files:
            print(f"  ⚠️ No texture files found in {asset_dir}")
            return
        
        # Pattern to extract LOD level from texture filename
        lod_pattern = re.compile(r'_?LOD(\d+)', re.IGNORECASE)
        
        # Group textures by LOD level and type
        # Structure: {lod_level: {'albedo': path, 'roughness': path, 'normal': path, 'metallic': path}}
        lod_textures = {}
        
        for tex_file in texture_files:
            filename_lower = tex_file.stem.lower()
            
            # Extract LOD level
            lod_match = lod_pattern.search(tex_file.stem)
            lod_level = lod_match.group(1) if lod_match else "0"
            
            if lod_level not in lod_textures:
                lod_textures[lod_level] = {}
            
            # Identify texture type by filename
            if 'albedo' in filename_lower or 'diffuse' in filename_lower or 'color' in filename_lower:
                lod_textures[lod_level]['albedo'] = tex_file
            elif 'roughness' in filename_lower or 'rough' in filename_lower:
                lod_textures[lod_level]['roughness'] = tex_file
            elif 'normal' in filename_lower and 'gl' not in filename_lower:
                lod_textures[lod_level]['normal'] = tex_file
            elif 'metallic' in filename_lower or 'metalness' in filename_lower:
                lod_textures[lod_level]['metallic'] = tex_file
            elif 'opacity' in filename_lower or 'alpha' in filename_lower or 'mask' in filename_lower:
                lod_textures[lod_level]['opacity'] = tex_file
        
        # Get all LOD levels that have objects (from FBX imports)
        lod_levels_with_objects = set()
        for import_group in import_groups:
            fbx_file = import_group['fbx_file']
            lod_match = lod_pattern.search(fbx_file.stem)
            lod_level = lod_match.group(1) if lod_match else "0"
            lod_levels_with_objects.add(lod_level)
        
        # Fill in missing LOD levels with textures from previous available LOD
        # Sort LOD levels numerically
        all_lod_levels = sorted(lod_levels_with_objects, key=lambda x: int(x))
        texture_types = ['albedo', 'roughness', 'normal', 'metallic', 'opacity']
        
        # For each LOD level that has objects, ensure it has textures
        # Use textures from the most recent previous LOD level that has that texture type
        for lod_level in all_lod_levels:
            if lod_level not in lod_textures:
                lod_textures[lod_level] = {}
            
            # For each texture type, find the most recent previous LOD that has it
            for tex_type in texture_types:
                if tex_type not in lod_textures[lod_level]:
                    # Look backwards through LOD levels to find the most recent one with this texture
                    current_lod_num = int(lod_level)
                    for prev_lod_num in range(current_lod_num - 1, -1, -1):
                        prev_lod_str = str(prev_lod_num)
                        if prev_lod_str in lod_textures and tex_type in lod_textures[prev_lod_str]:
                            lod_textures[lod_level][tex_type] = lod_textures[prev_lod_str][tex_type]
                            print(f"    📋 Using {tex_type} from LOD{prev_lod_str} for LOD{lod_level}")
                            break
        
        # Create a mapping of objects to their LOD levels based on which FBX file they came from
        # Structure: {lod_level: [list of objects]}
        lod_objects = {}
        for import_group in import_groups:
            fbx_file = import_group['fbx_file']
            objects = import_group['objects']
            
            # Extract LOD level from FBX filename
            lod_match = lod_pattern.search(fbx_file.stem)
            lod_level = lod_match.group(1) if lod_match else "0"
            
            if lod_level not in lod_objects:
                lod_objects[lod_level] = []
            
            # Add mesh objects from this import
            for obj in objects:
                if obj.type == 'MESH' and obj.data:
                    lod_objects[lod_level].append(obj)
        
        # Create materials for each LOD level that has objects
        # Use the sorted list of LOD levels with objects to ensure we process them in order
        for lod_level in all_lod_levels:
            # Get textures for this LOD level (may be filled from previous LODs)
            textures = lod_textures.get(lod_level, {})
            # Material name: same as attach root name with LOD suffix
            material_name = f"{attach_root_name}_LOD{lod_level}"
            
            # Check if material already exists
            if material_name in bpy.data.materials:
                mat = bpy.data.materials[material_name]
                bpy.data.materials.remove(mat, do_unlink=True)
            
            # Create new material
            mat = bpy.data.materials.new(name=material_name)
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            
            # Get or create Principled BSDF
            bsdf = nodes.get("Principled BSDF")
            if not bsdf:
                bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
            
            # Load Albedo texture
            if 'albedo' in textures:
                albedo_node = load_texture(nodes, 'Albedo', textures['albedo'], 'sRGB')
                if albedo_node:
                    links.new(albedo_node.outputs['Color'], bsdf.inputs['Base Color'])
            
            # Load Roughness texture
            if 'roughness' in textures:
                roughness_node = load_texture(nodes, 'Roughness', textures['roughness'], 'Non-Color')
                if roughness_node:
                    links.new(roughness_node.outputs['Color'], bsdf.inputs['Roughness'])
            
            # Load Normal texture
            if 'normal' in textures:
                normal_node = load_texture(nodes, 'Normal', textures['normal'], 'Non-Color')
                if normal_node:
                    # Create normal map node
                    normal_map_node = nodes.new(type='ShaderNodeNormalMap')
                    normal_map_node.location = (-300, -400)
                    links.new(normal_node.outputs['Color'], normal_map_node.inputs['Color'])
                    links.new(normal_map_node.outputs['Normal'], bsdf.inputs['Normal'])
            
            # Load Metallic texture
            if 'metallic' in textures:
                metallic_node = load_texture(nodes, 'Metallic', textures['metallic'], 'Non-Color')
                if metallic_node:
                    links.new(metallic_node.outputs['Color'], bsdf.inputs['Metallic'])
            
            # Load Opacity/Alpha/Mask texture
            if 'opacity' in textures:
                opacity_node = load_texture(nodes, 'Opacity', textures['opacity'], 'Non-Color')
                if opacity_node:
                    # Connect to Alpha input of Principled BSDF
                    links.new(opacity_node.outputs['Color'], bsdf.inputs['Alpha'])
                    # Enable alpha blending for the material
                    mat.blend_method = 'BLEND'
                    print(f"    ✅ Enabled alpha blending for material")
            
            print(f"  🎨 Created material: {material_name}")
            
            # Assign material to mesh objects from this LOD level
            if lod_level in lod_objects:
                for obj in lod_objects[lod_level]:
                    # Assign material to object
                    if len(obj.data.materials) == 0:
                        obj.data.materials.append(mat)
                    else:
                        obj.data.materials[0] = mat
                    print(f"    ✅ Assigned material to: {obj.name}")

    def _cleanup_unused_materials(self, materials_before_import, imported_objects=None):
        """
        Clean up unused materials that were created during FBX import but are not being used.
        Removes materials like 'MatID_1', 'MatID_2', etc. that are created by the FBX importer.

        Args:
            materials_before_import: Set of material names that existed before import
            imported_objects: Optional list of objects that were imported (for more aggressive cleanup)
        """
        import re

        print(f"\n  🧹 CLEANING UP TEMPORARY MATERIALS:")

        # Pattern to match temporary materials created by FBX importer
        # Matches: MatID_1, MatID_2, MATID_1, MatID_1.001, Material.001, etc.
        temp_material_patterns = [
            re.compile(r'^MatID_\d+', re.IGNORECASE),      # Matches MatID_1, MatID_1.001, etc.
            re.compile(r'^MATID_\d+', re.IGNORECASE),      # Matches MATID_1, MATID_1.001, etc.
            re.compile(r'^Material\.\d+$', re.IGNORECASE), # Matches Material.001, Material.002
            re.compile(r'^Material$', re.IGNORECASE),      # Matches just "Material"
        ]

        removed_count = 0

        # Iterate through ALL materials in the scene (not just new ones)
        # This catches duplicates like MatID_1.001, MatID_1.002, etc.
        for mat in list(bpy.data.materials):
            mat_name = mat.name

            # Check if it matches temporary material patterns
            is_temp_material = any(pattern.match(mat_name) for pattern in temp_material_patterns)

            if not is_temp_material:
                continue

            # Try to remove it
            try:
                # Check if material has any users
                if mat.users == 0:
                    bpy.data.materials.remove(mat, do_unlink=True)
                    print(f"    🗑️  Removed unused temporary material: {mat_name}")
                    removed_count += 1
                else:
                    # Material is in use - try to unlink and remove anyway
                    # This is safe because we've already assigned our custom materials
                    print(f"    🗑️  Force removing temporary material (has {mat.users} users): {mat_name}")
                    mat.user_clear()  # Clear all users
                    bpy.data.materials.remove(mat, do_unlink=True)
                    removed_count += 1
            except Exception as e:
                print(f"    ⚠️  Failed to remove material '{mat_name}': {e}")

        if removed_count > 0:
            print(f"    ✅ Cleaned up {removed_count} temporary material(s)")
        else:
            print(f"    ℹ️  No temporary materials found")
    
    def execute(self, context):
        import re

        print(f"\n{'='*80}")
        print(f"🚀 STARTING QUIXEL ASSET IMPORT")
        print(f"{'='*80}")

        # Track materials that exist before import
        materials_before_import = set(bpy.data.materials.keys())

        asset_dir = Path(self.directory)

        if not asset_dir.exists():
            self.report({'ERROR'}, f"Asset directory not found: {asset_dir}")
            return {'CANCELLED'}

        print(f"📁 Asset directory: {asset_dir}")

        # Find all FBX files in the directory (including subdirectories)
        fbx_files = list(asset_dir.glob("**/*.fbx"))

        # Check if this is a surface material (no FBX files, but has textures and JSON)
        if not fbx_files:
            print(f"ℹ️  No FBX files found - checking for surface material...")
            # Check if it's a surface material
            json_file = self._find_json_file(asset_dir)
            texture_extensions = ['.png', '.jpg', '.jpeg', '.tga', '.tif', '.tiff', '.exr']
            texture_files = []
            for ext in texture_extensions:
                texture_files.extend(asset_dir.glob(f"**/*{ext}"))

            if json_file and texture_files:
                # This is a surface material, create it
                print(f"✅ Detected surface material (JSON + textures)")
                if self._create_surface_material(asset_dir, context):
                    self.report({'INFO'}, f"Surface material imported from {asset_dir.name}")

                    # Force Blender to update the viewport/depsgraph before notifying
                    bpy.context.view_layer.update()

                    # Send notification to Electron
                    self._notify_import_complete(asset_dir)

                    return {'FINISHED'}
                else:
                    self.report({'ERROR'}, "Failed to create surface material")
                    return {'CANCELLED'}
            else:
                self.report({'WARNING'}, f"No FBX files or surface materials found in {asset_dir}")
                return {'CANCELLED'}

        print(f"📦 Found {len(fbx_files)} FBX file(s) to import:")
        for fbx_file in fbx_files:
            print(f"   - {fbx_file.name}")

        # Pattern to match LOD suffixes
        lod_pattern = re.compile(r'_?LOD\d+$', re.IGNORECASE)

        def get_base_name(name):
            """Extract base name from object name, removing only the LOD suffix at the end"""
            # Remove LOD suffix if present (only at the very end)
            match = lod_pattern.search(name)
            if match:
                # Verify the match is at the very end of the string
                if match.end() == len(name):
                    # Only remove if the match is at the very end
                    base_name = name[:match.start()]
                    return base_name
            return name

        # ═══════════════════════════════════════════════════════════════
        # STEP 1: IMPORT ALL FBX FILES
        # ═══════════════════════════════════════════════════════════════
        print(f"\n{'='*80}")
        print(f"📥 STEP 1: IMPORTING FBX FILES")
        print(f"{'='*80}")

        imported_count = 0
        all_imported_objects = {}  # Maps base_name -> list of (fbx_file, imported_objects)

        for fbx_file in fbx_files:
            print(f"\n🔄 Importing: {fbx_file.name}")
            try:
                # Store current selection and existing objects
                selected_objects = list(context.selected_objects)
                active_object = context.active_object
                existing_objects = set(context.scene.objects)

                # Clear selection
                bpy.ops.object.select_all(action='DESELECT')

                # Import the FBX file
                bpy.ops.import_scene.fbx(filepath=str(fbx_file))

                # Find all newly imported objects (objects that didn't exist before)
                imported_objects = [obj for obj in context.scene.objects if obj not in existing_objects]

                if not imported_objects:
                    print(f"  ⚠️ No objects imported from: {fbx_file.name}")
                    continue

                print(f"  🔧 Imported {len(imported_objects)} raw object(s):")
                for obj in imported_objects:
                    print(f"     - {obj.name} (type: {obj.type}, scale: {obj.scale}, rotation: ({math.degrees(obj.rotation_euler.x):.1f}°, {math.degrees(obj.rotation_euler.y):.1f}°, {math.degrees(obj.rotation_euler.z):.1f}°))")

                # Get the base name from the imported object names (not the filename)
                object_names = [obj.name for obj in imported_objects]
                main_object_name = object_names[0]  # Start with first object
                for obj_name in object_names:
                    # Prefer names that don't contain common child object indicators
                    if not any(indicator in obj_name.lower() for indicator in ['_child', '_helper', '_bone', '_armature']):
                        main_object_name = obj_name
                        break

                base_name = get_base_name(main_object_name)

                # Group by base name
                if base_name not in all_imported_objects:
                    all_imported_objects[base_name] = []

                all_imported_objects[base_name].append({
                    'fbx_file': fbx_file,
                    'objects': imported_objects
                })

                imported_count += 1
                print(f"  ✅ Successfully imported (base name: '{base_name}')")

                # Restore previous selection
                bpy.ops.object.select_all(action='DESELECT')
                for obj in selected_objects:
                    obj.select_set(True)
                if active_object:
                    context.view_layer.objects.active = active_object

            except Exception as e:
                print(f"  ❌ Failed to import {fbx_file.name}: {e}")

        if imported_count == 0:
            self.report({'ERROR'}, "Failed to import any FBX files")
            return {'CANCELLED'}

        print(f"\n✅ Import complete: {imported_count} FBX file(s) imported into {len(all_imported_objects)} asset group(s)")

        # ═══════════════════════════════════════════════════════════════
        # STEP 2: PROCESS EACH ASSET GROUP
        # ═══════════════════════════════════════════════════════════════
        print(f"\n{'='*80}")
        print(f"⚙️  STEP 2: PROCESSING ASSET GROUPS")
        print(f"{'='*80}")

        for base_name, import_groups in all_imported_objects.items():
            print(f"\n{'─'*80}")
            print(f"📦 Processing asset group: '{base_name}'")
            print(f"{'─'*80}")

            # Try to get the proper name from JSON file (for 3D models)
            json_name, json_file = self._get_name_from_json(asset_dir)
            if json_name:
                # Use JSON-based name for attach root base instead of base_name
                # BUT: Remove any existing letter suffix at the end (like _a, _b, _c)
                # because we'll add our own variation suffixes
                import re
                # Remove trailing _a, _b, _c, _aa, _ab, etc. pattern
                attach_root_base_name = re.sub(r'_[a-z]+$', '', json_name, flags=re.IGNORECASE)
                print(f"  📋 Using JSON name for attach roots: {json_name}")
                if attach_root_base_name != json_name:
                    print(f"  ✂️  Removed existing suffix: '{json_name}' → '{attach_root_base_name}'")
            else:
                # Fallback to base_name with quixel_ prefix
                attach_root_base_name = f"quixel_{base_name}"

            # Collect all objects from all LOD imports for this asset
            all_objects_to_process = []
            detected_scale = None
            detected_rotation = None
            
            # Process all LOD imports to collect objects and detect scale/rotation
            for import_group in import_groups:
                imported_objects = import_group['objects']
                fbx_file = import_group['fbx_file']
                
                # Identify and remove old world root objects (empty objects that are parents of other imported objects)
                old_world_roots = []
                for obj in imported_objects:
                    # Check if this object is a parent of other imported objects
                    is_parent = any(child in imported_objects for child in obj.children)
                    # Check if it's an empty object (no mesh data)
                    is_empty = (obj.type == 'EMPTY' or 
                               (hasattr(obj, 'data') and obj.data is None) or
                               (obj.type == 'MESH' and obj.data is not None and len(obj.data.vertices) == 0))
                    # For safety, also check if it has a name that suggests it's a root
                    if is_parent and (is_empty or obj.name == fbx_file.stem):
                        old_world_roots.append(obj)
                
                # Detect rotation AND scale from old world roots before removing them
                # The old world roots typically have the correct rotation (e.g., X rotation of 90) and scale
                old_root_scale = None
                for old_root in old_world_roots:
                    # Get the rotation from the old world root
                    rotation_euler = old_root.rotation_euler
                    if detected_rotation is None:
                        detected_rotation = rotation_euler.copy()
                        print(f"  🔄 Detected rotation from old world root: X={math.degrees(rotation_euler.x):.1f}°, Y={math.degrees(rotation_euler.y):.1f}°, Z={math.degrees(rotation_euler.z):.1f}°")

                    # Get the scale from the old world root
                    root_scale = old_root.scale
                    if abs(root_scale.x - 1.0) > 0.001 or abs(root_scale.y - 1.0) > 0.001 or abs(root_scale.z - 1.0) > 0.001:
                        # The root has a non-identity scale, we need to preserve this
                        old_root_scale = root_scale.copy()
                        print(f"  📏 Detected scale from old world root: {root_scale}")

                    break  # Use the first old world root's rotation and scale

                # If no rotation detected from old world roots, check the imported objects
                # Sometimes the rotation is on the mesh objects themselves
                if detected_rotation is None:
                    for obj in imported_objects:
                        if obj.type == 'MESH' and obj.data:
                            # Check if the object has a significant rotation (like 90 degrees on X)
                            rotation_euler = obj.rotation_euler
                            # Check if X rotation is close to 90 degrees (common FBX import)
                            x_rot_deg = math.degrees(rotation_euler.x)
                            if abs(x_rot_deg - 90) < 5 or abs(x_rot_deg - (-90)) < 5:
                                detected_rotation = rotation_euler.copy()
                                print(f"  🔄 Detected rotation from mesh object: X={x_rot_deg:.1f}°, Y={math.degrees(rotation_euler.y):.1f}°, Z={math.degrees(rotation_euler.z):.1f}°")
                                break

                # Collect all children of old world roots and apply scale if needed
                children_to_reparent = []
                for old_root in old_world_roots:
                    for child in old_root.children:
                        children_to_reparent.append(child)

                        # CRITICAL: If old root has a scale, apply it to children BEFORE unparenting
                        # This preserves the correct size
                        if old_root_scale is not None:
                            # Multiply child's scale by parent's scale
                            child.scale.x *= old_root_scale.x
                            child.scale.y *= old_root_scale.y
                            child.scale.z *= old_root_scale.z
                            print(f"    📏 Applied root scale to child: {child.name} -> scale={child.scale}")

                        # Unparent the child
                        child.parent = None

                # Remove old world root objects
                for old_root in old_world_roots:
                    bpy.data.objects.remove(old_root, do_unlink=True)
                    imported_objects.remove(old_root)
                
                # Add the children to our list of objects to parent
                imported_objects.extend(children_to_reparent)
                
                # Detect the scale from the imported objects (typically 0.01 or 0.1)
                # Check the scale of mesh objects (they should have the correct scale)
                for obj in imported_objects:
                    if obj.type == 'MESH' and obj.data:
                        # Get the scale from the object
                        scale = obj.scale
                        # Check if it's a small scale like 0.01 or 0.1
                        if scale.x < 1.0 and scale.x > 0:
                            # Use the X scale as reference (assuming uniform or similar scales)
                            if detected_scale is None or abs(scale.x - 0.01) < abs(detected_scale - 0.01):
                                detected_scale = scale.x
                        break  # Use the first mesh object's scale
                
                all_objects_to_process.extend(imported_objects)

                if old_world_roots:
                    print(f"  ✅ Removed {len(old_world_roots)} old world root object(s) from: {fbx_file.name}")
            
            # Use detected scale or default to 0.01 if not found
            if detected_scale is None:
                detected_scale = 0.01
                print(f"  ⚠️ No scale detected, using default: {detected_scale}")
            else:
                print(f"  📏 Detected scale: {detected_scale}")
            
            # Use detected rotation or default to (90, 0, 0) if not found (common FBX import rotation)
            if detected_rotation is None:
                detected_rotation = mathutils.Euler((math.radians(90), 0, 0), 'XYZ')
                print(f"  ⚠️ No rotation detected, using default: X=90°")
            else:
                print(f"  🔄 Using rotation: X={math.degrees(detected_rotation.x):.1f}°, Y={math.degrees(detected_rotation.y):.1f}°, Z={math.degrees(detected_rotation.z):.1f}°")

            # ═══════════════════════════════════════════════════════════════
            # STEP 3: APPLY TRANSFORMS (CRITICAL - BEFORE GROUPING!)
            # ═══════════════════════════════════════════════════════════════
            print(f"\n  {'─'*40}")
            print(f"  🔧 STEP 3: APPLYING TRANSFORMS")
            print(f"  {'─'*40}")

            # Apply scale and rotation to all objects BEFORE grouping by variation
            # This is CRITICAL because bounding box calculations need correct transforms
            self._apply_transforms_to_objects(all_objects_to_process)

            # ═══════════════════════════════════════════════════════════════
            # STEP 4: GROUP BY VARIATION
            # ═══════════════════════════════════════════════════════════════
            print(f"\n  {'─'*40}")
            print(f"  🔍 STEP 4: DETECTING VARIATIONS")
            print(f"  {'─'*40}")

            # Group objects by variation suffix
            variations = self._group_objects_by_variation(all_objects_to_process)

            if not variations:
                print(f"  ⚠️ No mesh variations found in asset group")
                continue

            # ═══════════════════════════════════════════════════════════════
            # STEP 5: CREATE MATERIALS FOR ALL VARIATIONS (OPTIMIZED)
            # ═══════════════════════════════════════════════════════════════
            print(f"\n  {'─'*40}")
            print(f"  🎨 STEP 5: CREATING MATERIALS (OPTIMIZED)")
            print(f"  {'─'*40}")
            
            # Create materials for all variations at once, optimizing by reusing when textures are identical
            self._create_materials_for_all_variations(
                asset_dir, 
                base_name, 
                attach_root_base_name, 
                variations, 
                import_groups, 
                context
            )

            # ═══════════════════════════════════════════════════════════════
            # STEP 6: CREATE ATTACH ROOTS PER VARIATION
            # ═══════════════════════════════════════════════════════════════
            print(f"\n  {'─'*40}")
            print(f"  📦 STEP 6A: CALCULATING BOUNDING BOXES")
            print(f"  {'─'*40}")

            # Calculate bounding boxes for all variations BEFORE parenting
            variation_bboxes = {}
            for variation_suffix in sorted(variations.keys()):
                variation_objects = variations[variation_suffix]
                print(f"\n    📏 Calculating bbox for variation '_{variation_suffix}':")
                bbox = self._calculate_variation_bbox(variation_objects)
                variation_bboxes[variation_suffix] = bbox

            print(f"\n  {'─'*40}")
            print(f"  📦 STEP 6B: CREATING ATTACH ROOTS WITH PROPER SPACING")
            print(f"  {'─'*40}")

            current_x_offset = 0.0
            created_attach_roots = []
            margin = 1.0  # Fixed 1 meter margin between variations

            for variation_suffix in sorted(variations.keys()):
                variation_objects = variations[variation_suffix]
                bbox = variation_bboxes[variation_suffix]

                print(f"\n  📌 Creating attach root for variation '_{variation_suffix}':")

                # Create attach root name with variation suffix
                attach_root_name = f"{attach_root_base_name}_{variation_suffix}"

                # Create attach root (empty object)
                attach_root = bpy.data.objects.new(attach_root_name, None)
                attach_root.empty_display_type = 'ARROWS'
                attach_root.empty_display_size = 1.0

                # Set scale and rotation to NEUTRAL (1,1,1) and (0,0,0)
                # Since we already applied transforms to the meshes, the attach root should be neutral
                attach_root.scale = (1.0, 1.0, 1.0)
                attach_root.rotation_euler = (0.0, 0.0, 0.0)

                # Position: Place at current X offset
                attach_root.location.x = current_x_offset
                attach_root.location.y = 0.0
                attach_root.location.z = 0.0

                context.collection.objects.link(attach_root)
                created_attach_roots.append(attach_root)

                print(f"    📦 Created: {attach_root_name}")

                # Calculate the center of the variation objects in world space
                objects_center_x = (bbox['min_x'] + bbox['max_x']) / 2.0
                objects_center_y = 0.0  # Assuming Y is at origin
                objects_center_z = 0.0  # Assuming Z is at origin

                # STEP 1: Position attach root at objects' center
                attach_root.location.x = objects_center_x
                attach_root.location.y = objects_center_y
                attach_root.location.z = objects_center_z

                # STEP 2: Parent all objects - they will be at ~(0,0,0) local
                for obj in variation_objects:
                    obj.parent = attach_root
                    obj.matrix_parent_inverse.identity()

                # STEP 3: Move ONLY the attach root to the desired position
                # Objects move with it automatically since they're parented
                attach_root.location.x = current_x_offset
                attach_root.location.y = 0.0
                attach_root.location.z = 0.0

                print(f"    ✅ Parented {len(variation_objects)} object(s) to attach root")
                print(f"    📍 Attach root positioned at X={current_x_offset:.2f}")
                print(f"       All child objects at local (0, 0, 0)")
                print(f"       Scale: (1.0, 1.0, 1.0) - neutral, transforms already applied to meshes")
                print(f"       Rotation: (0°, 0°, 0°) - neutral, transforms already applied to meshes")

                # Calculate next position: current position + width + margin
                next_offset = current_x_offset + bbox['width'] + margin

                print(f"    📍 Next variation will be at X={next_offset:.2f} (current={current_x_offset:.2f} + width={bbox['width']:.2f} + margin={margin:.2f})")

                current_x_offset = next_offset

            # ═══════════════════════════════════════════════════════════════
            # FINAL: SELECT ALL CREATED ATTACH ROOTS
            # ═══════════════════════════════════════════════════════════════
            bpy.ops.object.select_all(action='DESELECT')
            for attach_root in created_attach_roots:
                attach_root.select_set(True)
            if created_attach_roots:
                context.view_layer.objects.active = created_attach_roots[0]

            print(f"\n  ✅ Created {len(created_attach_roots)} attach root(s) for {len(variations)} variation(s)")

        # ═══════════════════════════════════════════════════════════════
        # COMPLETE!
        # ═══════════════════════════════════════════════════════════════
        print(f"\n{'='*80}")
        print(f"✅ IMPORT COMPLETE!")
        print(f"{'='*80}")
        print(f"📊 Summary:")
        print(f"   - {imported_count} FBX file(s) imported")
        print(f"   - {len(all_imported_objects)} asset group(s) processed")
        print(f"{'='*80}\n")

        # ═══════════════════════════════════════════════════════════════
        # CLEANUP: Remove unused temporary materials
        # ═══════════════════════════════════════════════════════════════
        # Collect all imported objects for cleanup
        all_imported_objects_list = []
        for import_groups in all_imported_objects.values():
            for import_group in import_groups:
                all_imported_objects_list.extend(import_group.get('objects', []))
        
        self._cleanup_unused_materials(materials_before_import, all_imported_objects_list)

        self.report({'INFO'}, f"Imported {imported_count} FBX file(s) with variations")

        # Force Blender to update the viewport/depsgraph before notifying
        bpy.context.view_layer.update()

        # Send notification to Electron
        self._notify_import_complete(asset_dir)

        return {'FINISHED'}

    def _notify_import_complete(self, asset_dir):
        """Write completion file to notify Electron app"""
        import tempfile
        try:
            temp_dir = Path(tempfile.gettempdir()) / "quixel_portal"

            # Ensure directory exists
            if not temp_dir.exists():
                temp_dir.mkdir(parents=True, exist_ok=True)

            completion_file = temp_dir / "import_complete.json"

            # Use thumbnail path from property if provided
            thumbnail_path = self.thumbnail_path if self.thumbnail_path else None

            # Use asset name override if provided, otherwise get from JSON
            asset_name = self.asset_name_override if self.asset_name_override else None
            if not asset_name:
                asset_name = asset_dir.name
                json_name, _ = self._get_name_from_json(asset_dir)
                if json_name:
                    asset_name = json_name

            completion_data = {
                "asset_path": str(asset_dir),
                "asset_name": asset_name,
                "thumbnail": str(thumbnail_path) if thumbnail_path else None,
                "timestamp": bpy.context.scene.frame_current
            }

            with open(completion_file, 'w') as f:
                json.dump(completion_data, f, indent=2)

            print(f"✅ Quixel Portal: Notified Electron of import completion for '{asset_name}'")

        except Exception as e:
            print(f"⚠️ Quixel Portal: Failed to notify import completion: {e}")


def check_import_requests():
    """Background timer function to check for import requests from Electron"""
    # Get the temp directory for communication
    import tempfile
    global _blender_instance_id

    temp_dir = Path(tempfile.gettempdir()) / "quixel_portal"
    request_file = temp_dir / "import_request.json"

    if request_file.exists():
        try:
            # Read the import request
            with open(request_file, 'r') as f:
                request_data = json.load(f)

            asset_path = request_data.get('asset_path')
            thumbnail_path = request_data.get('thumbnail')
            asset_name = request_data.get('asset_name')
            request_instance_id = request_data.get('blender_instance_id')

            # Get this Blender instance's ID from GLOBAL variable
            my_instance_id = _blender_instance_id

            # ═══════════════════════════════════════════════════════════════
            # 🔒 CRITICAL: Only process if this request is for THIS instance
            # ═══════════════════════════════════════════════════════════════

            # Check if request has timestamp and if it's too old (>30 seconds), delete it
            request_timestamp = request_data.get('timestamp', 0)
            current_time = time.time()
            age_seconds = current_time - request_timestamp if request_timestamp else 999

            if age_seconds > 30:
                print(f"🗑️ Quixel Portal: Deleting stale import request ({age_seconds:.1f}s old)")
                request_file.unlink()
                return 1.0

            # If this Blender instance has NO instance ID, it means the user
            # never opened Quixel Portal from this instance
            if not my_instance_id:
                # If request is old enough (stale), delete it
                # If it's recent, another instance might still need it
                if age_seconds > 5:
                    print(f"🗑️ Quixel Portal: Deleting request file (no portal opened in this instance, request is {age_seconds:.1f}s old)")
                    request_file.unlink()
                else:
                    print(f"🔒 Quixel Portal: Ignoring recent import request (this instance has no Portal opened)")
                return 1.0  # Continue checking

            # If the request has NO instance ID (old format), delete it immediately
            if not request_instance_id:
                print(f"⚠️ Quixel Portal: Deleting malformed request (no instance ID)")
                request_file.unlink()
                return 1.0

            # Check if this request is for THIS specific Blender instance
            if request_instance_id != my_instance_id:
                # This request is for a DIFFERENT Blender instance, ignore it
                print(f"🔒 Quixel Portal: Ignoring import request for different instance")
                print(f"   My ID: {my_instance_id}")
                print(f"   Request ID: {request_instance_id}")
                return 1.0  # Continue checking (DON'T delete file - let the correct instance handle it)

            # ═══════════════════════════════════════════════════════════════
            # ✅ THIS REQUEST IS FOR THIS INSTANCE - Process it!
            # ═══════════════════════════════════════════════════════════════

            print(f"📥 Quixel Portal: Import request received for THIS instance:")
            print(f"   Asset path: {asset_path}")
            print(f"   Thumbnail: {thumbnail_path}")
            print(f"   Asset name: {asset_name}")
            print(f"   Instance ID: {request_instance_id}")

            # CRITICAL: Delete request file FIRST to prevent infinite loops
            # Even if import fails, we don't want to keep retrying
            try:
                request_file.unlink()
                print(f"🗑️ Quixel Portal: Deleted import request file")
            except Exception as del_error:
                print(f"⚠️ Quixel Portal: Failed to delete request file: {del_error}")

            # Now process the import
            if asset_path and Path(asset_path).exists():
                try:
                    # Import the asset
                    bpy.ops.quixel.import_fbx(
                        directory=asset_path,
                        thumbnail_path=thumbnail_path or '',
                        asset_name_override=asset_name or ''
                    )
                    print(f"✅ Quixel Portal: Successfully imported asset from {asset_path}")
                except Exception as import_error:
                    print(f"❌ Quixel Portal: Import failed: {import_error}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"⚠️ Quixel Portal: Asset path doesn't exist: {asset_path}")

        except Exception as e:
            print(f"❌ Quixel Portal: Error processing import request: {e}")
            import traceback
            traceback.print_exc()
            # Try to delete the file anyway to prevent repeated errors
            try:
                if request_file.exists():
                    request_file.unlink()
                    print(f"🗑️ Quixel Portal: Deleted request file after error")
            except Exception as cleanup_error:
                print(f"⚠️ Quixel Portal: Could not delete request file: {cleanup_error}")

    # Continue the timer
    return 1.0  # Check every 1 second


def write_heartbeat():
    """Write heartbeat file to signal Electron that Blender is still alive"""
    import tempfile
    global _blender_instance_id

    try:
        # Get this Blender instance's ID from GLOBAL variable
        instance_id = _blender_instance_id

        # If no instance ID yet, skip (portal hasn't been opened yet)
        if not instance_id:
            return 30.0  # Check again in 30 seconds

        # Get temp directory
        temp_dir = Path(tempfile.gettempdir()) / "quixel_portal"

        # Create directory if it doesn't exist
        if not temp_dir.exists():
            temp_dir.mkdir(parents=True, exist_ok=True)

        # Write heartbeat file with timestamp and PID
        heartbeat_file = temp_dir / f"heartbeat_{instance_id}.txt"
        heartbeat_data = {
            "timestamp": time.time(),
            "blender_pid": os.getpid(),
            "instance_id": instance_id
        }

        with open(heartbeat_file, 'w') as f:
            json.dump(heartbeat_data, f, indent=2)

        print(f"💓 Quixel Portal: Heartbeat written (timestamp: {heartbeat_data['timestamp']:.0f})")

        # Clean up old heartbeat files (>2 hours old)
        try:
            current_time = time.time()
            for old_file in temp_dir.glob("heartbeat_*.txt"):
                # Skip our own file
                if old_file == heartbeat_file:
                    continue

                # Check file age
                try:
                    file_age = current_time - old_file.stat().st_mtime
                    if file_age > 7200:  # 2 hours in seconds
                        old_file.unlink()
                        print(f"🧹 Quixel Portal: Cleaned up old heartbeat file: {old_file.name}")
                except Exception as e:
                    # Failed to delete old file, not critical
                    pass
        except Exception as e:
            # Failed to clean up, not critical
            pass

    except Exception as e:
        print(f"⚠️ Quixel Portal: Failed to write heartbeat: {e}")

    # Continue the timer - write heartbeat every 30 seconds
    return 30.0


def _is_already_registered():
    """Check if our draw function is already registered by checking a persistent marker"""
    # Store a marker on the header type itself to track registration
    # This marker persists across module reloads (as long as Blender is running)
    marker_name = '_quixel_portal_button_registered'
    
    try:
        # Check if we've set a marker indicating registration
        if hasattr(bpy.types.TOPBAR_HT_upper_bar, marker_name):
            return getattr(bpy.types.TOPBAR_HT_upper_bar, marker_name) == True
    except:
        pass
    
    return False


def _mark_as_registered(registered=True):
    """Mark the header type to indicate our function is registered"""
    marker_name = '_quixel_portal_button_registered'
    try:
        setattr(bpy.types.TOPBAR_HT_upper_bar, marker_name, registered)
    except:
        pass


def _cleanup_orphaned_import_requests():
    """Clean up any orphaned import request files on addon reload/registration"""
    import tempfile

    try:
        temp_dir = Path(tempfile.gettempdir()) / "quixel_portal"
        if not temp_dir.exists():
            return

        request_file = temp_dir / "import_request.json"

        if request_file.exists():
            # On addon reload, ALWAYS delete the request file
            # If it was valid, it should have been processed already
            # If it wasn't, it's stuck and needs to be removed
            try:
                request_file.unlink()
                print(f"🧹 Quixel Portal: Cleaned up import request file on addon reload")
            except Exception as e:
                print(f"⚠️ Quixel Portal: Failed to delete import request: {e}")

    except Exception as e:
        print(f"⚠️ Quixel Portal: Error during import request cleanup: {e}")


def register():
    global custom_icons, _draw_function_registered, _import_timer

    # Clean up any orphaned import requests from previous sessions
    _cleanup_orphaned_import_requests()

    # Register custom icons
    custom_icons = bpy.utils.previews.new()

    # Load the Quixel logo icon
    addon_dir = Path(__file__).parent
    icon_path = addon_dir / "electron_app" / "assets" / "icons" / "logo_48.png"

    if icon_path.exists():
        try:
            custom_icons.load("quixel_logo", str(icon_path), 'IMAGE')
            # Verify the icon was loaded successfully
            if "quixel_logo" in custom_icons:
                icon_item = custom_icons["quixel_logo"]
                if hasattr(icon_item, 'icon_id'):
                    print(f"✅ Quixel Portal: Icon loaded successfully from {icon_path} (ID: {icon_item.icon_id})")
                else:
                    print(f"⚠️ Quixel Portal: Icon loaded but icon_id not available")
            else:
                print(f"⚠️ Quixel Portal: Icon load failed - not in collection")
        except Exception as e:
            print(f"⚠️ Quixel Portal: Error loading icon: {e}")
    else:
        print(f"⚠️ Quixel Portal: Icon not found at {icon_path}")

    # Register the operators
    bpy.utils.register_class(QUIXEL_OT_cleanup_requests)
    bpy.utils.register_class(QUIXEL_OT_open_portal)
    bpy.utils.register_class(QUIXEL_OT_import_fbx)

    # Register draw function to topbar
    # Use a persistent marker on the header type to track registration across module reloads
    # This marker persists as long as Blender is running, even if the module reloads

    # Check if already registered using the persistent marker
    if not _is_already_registered() and not _draw_function_registered:
        try:
            bpy.types.TOPBAR_HT_upper_bar.append(draw_quixel_button)
            _draw_function_registered = True
            _mark_as_registered(True)
            print("✅ Quixel Portal: Button added to topbar")
        except Exception as e:
            print(f"⚠️ Quixel Portal: Error adding button to topbar: {e}")
    else:
        if _is_already_registered():
            # If marker says registered but our flag doesn't, sync the flag
            _draw_function_registered = True
            print("ℹ️ Quixel Portal: Button already registered (detected from previous session)")
        else:
            print("ℹ️ Quixel Portal: Button already registered in this session (skipping)")

    # Start the background timer to check for import requests
    if not bpy.app.timers.is_registered(check_import_requests):
        bpy.app.timers.register(check_import_requests)
        print("✅ Quixel Portal: Import request monitor started")

    # Start the background timer to write heartbeat
    if not bpy.app.timers.is_registered(write_heartbeat):
        bpy.app.timers.register(write_heartbeat)
        print("✅ Quixel Portal: Heartbeat writer started (writing every 30 seconds)")


def unregister():
    global custom_icons, _draw_function_registered, _import_timer, _blender_instance_id

    # Stop the background timers
    if bpy.app.timers.is_registered(check_import_requests):
        bpy.app.timers.unregister(check_import_requests)
        print("✅ Quixel Portal: Import request monitor stopped")

    if bpy.app.timers.is_registered(write_heartbeat):
        bpy.app.timers.unregister(write_heartbeat)
        print("✅ Quixel Portal: Heartbeat writer stopped")

    # Clean up heartbeat file when Blender closes gracefully
    try:
        import tempfile
        instance_id = _blender_instance_id  # Use global instance ID
        if instance_id:
            temp_dir = Path(tempfile.gettempdir()) / "quixel_portal"
            heartbeat_file = temp_dir / f"heartbeat_{instance_id}.txt"
            if heartbeat_file.exists():
                heartbeat_file.unlink()
                print("✅ Quixel Portal: Heartbeat file deleted")
    except Exception as e:
        # Failed to delete heartbeat file, not critical
        pass

    # Remove draw function from topbar
    # Check both the session flag and the persistent marker
    if _draw_function_registered or _is_already_registered():
        try:
            bpy.types.TOPBAR_HT_upper_bar.remove(draw_quixel_button)
            _draw_function_registered = False
            _mark_as_registered(False)
        except:
            # If removal fails (e.g., function wasn't actually registered or was already removed),
            # reset both flags anyway
            _draw_function_registered = False
            _mark_as_registered(False)

    # Unregister the operators
    try:
        bpy.utils.unregister_class(QUIXEL_OT_cleanup_requests)
    except:
        pass

    try:
        bpy.utils.unregister_class(QUIXEL_OT_open_portal)
    except:
        pass

    try:
        bpy.utils.unregister_class(QUIXEL_OT_import_fbx)
    except:
        pass

    # Remove custom icons
    if custom_icons:
        try:
            bpy.utils.previews.remove(custom_icons)
            custom_icons = None
        except:
            pass

    print("✅ Quixel Portal: Addon unregistered")


if __name__ == "__main__":
    register()
