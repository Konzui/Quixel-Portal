"""FBX importer module for importing and processing FBX files.

This module handles FBX file discovery, import execution, and object grouping.
"""

import bpy
import math
import mathutils
import re
from pathlib import Path

from ..utils.naming import get_base_name


def find_fbx_files(asset_dir):
    """Find all FBX files in the asset directory.
    
    Args:
        asset_dir: Path to the asset directory
        
    Returns:
        list: List of Path objects to FBX files
    """
    asset_dir = Path(asset_dir)
    return list(asset_dir.glob("**/*.fbx"))


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
        import_results: List of tuples (fbx_file, imported_objects, base_name)
        
    Returns:
        dict: Maps base_name -> list of import groups
              Each import group is {'fbx_file': Path, 'objects': list}
    """
    all_imported_objects = {}
    
    for fbx_file, imported_objects, base_name in import_results:
        if not base_name:
            continue
        
        if base_name not in all_imported_objects:
            all_imported_objects[base_name] = []
        
        all_imported_objects[base_name].append({
            'fbx_file': fbx_file,
            'objects': imported_objects
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

