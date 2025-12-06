"""FBX importer module for importing and processing FBX files.

This module handles FBX file discovery, import execution, and object grouping.
"""

import bpy
import math
import mathutils
import re
from pathlib import Path

from ..utils.naming import get_base_name


def detect_3d_plant_structure(asset_dir):
    """Detect if this is a 3D plant structure with variation folders.
    
    3D plants have structure like:
    - Var 1/LOD0.fbx, Var 1/LOD1.fbx
    - Var 2/LOD0.fbx, Var 2/LOD1.fbx
    
    Args:
        asset_dir: Path to the asset directory
        
    Returns:
        tuple: (is_3d_plant: bool, variation_folders: dict)
               variation_folders maps variation_index -> folder_path
    """
    asset_dir = Path(asset_dir)
    
    # Look for folders matching "Var 1", "Var 2", "Variation 1", etc.
    var_pattern = re.compile(r'^var(?:iation)?\s*(\d+)$', re.IGNORECASE)
    
    variation_folders = {}
    
    for item in asset_dir.iterdir():
        if not item.is_dir():
            continue
        
        match = var_pattern.match(item.name)
        if match:
            var_index = int(match.group(1)) - 1  # Convert to 0-based index (Var 1 -> 0, Var 2 -> 1)
            variation_folders[var_index] = item
            print(f"🌱 [3D PLANT] Found variation folder: {item.name} -> index {var_index}")
    
    is_3d_plant = len(variation_folders) > 0
    
    if is_3d_plant:
        print(f"🌱 [3D PLANT] Detected 3D plant structure with {len(variation_folders)} variation(s)")
    
    return is_3d_plant, variation_folders


def detect_lod_levels_from_fbx(fbx_files):
    """Detect LOD levels from FBX filenames.
    
    Args:
        fbx_files: List of FBX file paths
        
    Returns:
        tuple: (lod_levels: list, max_lod: int)
               lod_levels: Sorted list of LOD level numbers (e.g., [0, 1, 2, 3])
               max_lod: Maximum LOD level found (or 0 if none found)
    """
    lod_pattern = re.compile(r'_?LOD(\d+)', re.IGNORECASE)
    lod_levels = set()
    
    for fbx_file in fbx_files:
        fbx_path = Path(fbx_file)
        lod_match = lod_pattern.search(fbx_path.stem)
        if lod_match:
            lod_level = int(lod_match.group(1))
            lod_levels.add(lod_level)
    
    sorted_lods = sorted(lod_levels) if lod_levels else [0]
    max_lod = max(sorted_lods) if sorted_lods else 0
    
    print(f"🔍 [LOD DETECTION] Detected LOD levels: {sorted_lods} (max: {max_lod})")
    
    return sorted_lods, max_lod


def find_fbx_files(asset_dir, detect_plants=True):
    """Find all FBX files in the asset directory.
    
    For 3D plants, also tracks which variation folder each FBX belongs to.
    
    Args:
        asset_dir: Path to the asset directory
        detect_plants: Whether to detect and handle 3D plant structure
        
    Returns:
        tuple: (fbx_files: list, is_3d_plant: bool, fbx_variation_map: dict)
               fbx_variation_map maps fbx_file -> variation_index (for 3D plants)
    """
    asset_dir = Path(asset_dir)
    
    # Detect 3D plant structure
    is_3d_plant = False
    variation_folders = {}
    fbx_variation_map = {}
    
    if detect_plants:
        is_3d_plant, variation_folders = detect_3d_plant_structure(asset_dir)
    
    # Find all FBX files
    all_fbx_files = list(asset_dir.glob("**/*.fbx"))
    
    if is_3d_plant:
        print(f"🌱 [3D PLANT] Found {len(all_fbx_files)} FBX file(s) total")
        
        # Map each FBX file to its variation folder
        for fbx_file in all_fbx_files:
            # Find which variation folder this FBX belongs to
            for var_index, var_folder in variation_folders.items():
                try:
                    # Check if FBX is inside this variation folder
                    if var_folder in fbx_file.parents or fbx_file.parent == var_folder:
                        fbx_variation_map[fbx_file] = var_index
                        print(f"🌱 [3D PLANT]   {fbx_file.name} -> Variation {var_index} (from {var_folder.name})")
                        break
                except:
                    pass
            
            # If not found in any variation folder, it might be in root (shared)
            if fbx_file not in fbx_variation_map:
                print(f"🌱 [3D PLANT]   {fbx_file.name} -> No variation folder (root/shared)")
    
    return all_fbx_files, is_3d_plant, fbx_variation_map


def import_fbx_file(filepath, context):
    """Import a single FBX file.
    
    Args:
        filepath: Path to the FBX file
        context: Blender context
        
    Returns:
        tuple: (imported_objects: list, base_name: str or None)
               Returns empty list and None if import failed
    """
    filepath = Path(filepath)
    
    try:
        # Store current selection and existing objects
        selected_objects = list(context.selected_objects)
        active_object = context.active_object
        existing_objects = set(context.scene.objects)
        
        # Clear selection
        bpy.ops.object.select_all(action='DESELECT')
        
        # Import the FBX file
        bpy.ops.import_scene.fbx(filepath=str(filepath))
        
        # Find all newly imported objects (objects that didn't exist before)
        imported_objects = [obj for obj in context.scene.objects if obj not in existing_objects]
        
        if not imported_objects:
            print(f"  ⚠️ No objects imported from: {filepath.name}")
            # Restore previous selection
            bpy.ops.object.select_all(action='DESELECT')
            for obj in selected_objects:
                obj.select_set(True)
            if active_object:
                context.view_layer.objects.active = active_object
            return [], None

        # Get the base name from the imported object names (not the filename)
        object_names = [obj.name for obj in imported_objects]
        main_object_name = object_names[0]  # Start with first object
        for obj_name in object_names:
            # Prefer names that don't contain common child object indicators
            if not any(indicator in obj_name.lower() for indicator in ['_child', '_helper', '_bone', '_armature']):
                main_object_name = obj_name
                break

        base_name = get_base_name(main_object_name)

        # Restore previous selection
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected_objects:
            obj.select_set(True)
        if active_object:
            context.view_layer.objects.active = active_object

        return imported_objects, base_name
        
    except Exception as e:
        print(f"  ❌ Failed to import {filepath.name}: {e}")
        return [], None


def group_imported_objects(import_results):
    """Group imported objects by base name.
    
    Args:
        import_results: List of tuples (fbx_file, imported_objects, base_name, variation_index)
                        variation_index is None for non-3D-plant assets
        
    Returns:
        dict: Maps base_name -> list of import groups
              Each import group is {'fbx_file': Path, 'objects': list, 'variation_index': int or None}
    """
    all_imported_objects = {}
    
    for result in import_results:
        # Handle both old format (3 elements) and new format (4 elements)
        if len(result) == 3:
            fbx_file, imported_objects, base_name = result
            variation_index = None
        else:
            fbx_file, imported_objects, base_name, variation_index = result
        
        if not base_name:
            continue
        
        if base_name not in all_imported_objects:
            all_imported_objects[base_name] = []
        
        all_imported_objects[base_name].append({
            'fbx_file': fbx_file,
            'objects': imported_objects,
            'variation_index': variation_index
        })
    
    return all_imported_objects


def apply_transforms(objects):
    """Apply scale and rotation to all objects.
    
    This bakes the transforms into the mesh geometry.
    CRITICAL: Must be done BEFORE parenting to attach roots!
    
    Args:
        objects: List of Blender objects to process
    """
    import math
    
    # Header and detail prints removed to reduce console clutter
    
    failed_objects = []
    
    for obj in objects:
        if obj.type != 'MESH' or not obj.data:
            # Print removed to reduce console clutter
            continue
        
        # Store original values for debug
        orig_scale = obj.scale.copy()
        orig_rotation = obj.rotation_euler.copy()
        
        # Print removed to reduce console clutter
        
        # Select object
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        
        # Apply BOTH scale AND rotation (CRITICAL FIX!)
        # This bakes them into the mesh vertex positions
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        
        # Print removed to reduce console clutter
        
        # Verify transforms are now neutral
        scale_ok = all(abs(s - 1.0) < 0.001 for s in obj.scale)
        rotation_ok = all(abs(r) < 0.001 for r in obj.rotation_euler)
        
        if scale_ok and rotation_ok:
            # Print removed to reduce console clutter
            pass
        else:
            # Print removed to reduce console clutter
            failed_objects.append(obj.name)
    
    # Clear selection
    bpy.ops.object.select_all(action='DESELECT')
    
    # Report any failures (prints removed to reduce console clutter)
    # Failed objects are still tracked in failed_objects list for potential future use

