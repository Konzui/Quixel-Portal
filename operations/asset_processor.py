"""Asset processor module for organizing and processing imported assets.

This module handles object organization, hierarchy creation, and asset type detection.
"""

import bpy
import math
import mathutils
import re
from pathlib import Path

from ..utils.naming import (
    detect_variation_number,
    index_to_letter_suffix,
    get_name_from_json,
)
from ..utils.validation import validate_asset_directory


def detect_asset_type(asset_dir):
    """Detect the type of asset (FBX or surface material).
    
    Args:
        asset_dir: Path to the asset directory
        
    Returns:
        str: 'fbx', 'surface', or None
    """
    is_valid, error_msg, asset_type = validate_asset_directory(asset_dir)
    return asset_type


def organize_objects_by_variation(objects):
    """Group objects by their variation index, then convert to letter suffixes.
    
    Args:
        objects: List of Blender objects to organize
        
    Returns:
        dict: {variation_letter_suffix: [list of objects]}
        
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
        variation_index = detect_variation_number(obj.name)
        
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
        letter_suffix = index_to_letter_suffix(variation_index)
        variations[letter_suffix] = index_groups[variation_index]
    
    print(f"\n  📊 VARIATION SUMMARY:")
    for suffix in sorted(variations.keys()):
        mesh_names = [obj.name for obj in variations[suffix]]
        print(f"    Variation '_{suffix}': {len(variations[suffix])} meshes")
        for name in mesh_names:
            print(f"      - {name}")
    
    return variations


def extract_lod_from_object_name(obj_name):
    """Extract LOD level from object name.

    Supports multiple formats:
    - IOI format: base_name_LOD_0_______ (LOD level indicated by position of number)
    - Standard format: base_name_LOD0, base_name_LOD1, etc.

    Args:
        obj_name: Name of the object

    Returns:
        int: LOD level (0-7), defaults to 0 if not found
    """
    # First, try to match IOI format: _LOD_ followed by 8 characters where the number's position indicates LOD level
    # Example: _LOD_0_______ (LOD 0), _LOD__1______ (LOD 1), _LOD___2_____ (LOD 2)
    ioi_pattern = re.compile(r'_LOD_([_0-9]{8})', re.IGNORECASE)
    ioi_match = ioi_pattern.search(obj_name)

    if ioi_match:
        lod_string = ioi_match.group(1)  # e.g., "0_______" or "__1______"
        # Find the position of the digit (0-7)
        for i, char in enumerate(lod_string):
            if char.isdigit():
                # The position of the digit is the LOD level
                return max(0, min(7, i))
        # If no digit found in the IOI format, default to 0
        return 0

    # Fall back to standard LOD patterns: _LOD0, _LOD1, LOD0, LOD1, etc.
    standard_patterns = [
        re.compile(r'_?LOD(\d+)', re.IGNORECASE),  # Matches _LOD0, LOD1, etc.
        re.compile(r'LOD(\d+)', re.IGNORECASE),     # Matches LOD0, LOD1 (without underscore)
    ]

    for pattern in standard_patterns:
        match = pattern.search(obj_name)
        if match:
            lod_level = int(match.group(1))
            # Clamp to valid range (0-7)
            return max(0, min(7, lod_level))

    # No LOD found, default to 0
    return 0


def set_ioi_lod_properties(obj, lod_level=None):
    """Set IOI LOD properties on an object and rename it to match IOI naming convention.
    
    Sets IoiIsLODLevel{i}Member properties for LOD levels 0-7.
    The object's LOD level is set to True, all others to False.
    Also renames the object to IOI format: base_name_LOD_0_______ (where numbers indicate active LODs).
    
    Args:
        obj: Blender object (must be a mesh)
        lod_level: Optional LOD level (0-7). If None, extracted from object name.
    """
    if obj.type != 'MESH' or not obj.data:
        return None, None
    
    # Store original name before any processing
    original_name = obj.name
    
    # Extract LOD level from object name if not provided
    if lod_level is None:
        lod_level = extract_lod_from_object_name(original_name)
    
    # Clamp to valid range (0-7)
    lod_level = max(0, min(7, lod_level))
    
    # Set all LOD level properties
    for i in range(8):
        prop_name = f"IoiIsLODLevel{str(i)}Member"
        if i == lod_level:
            obj[prop_name] = bool(True)
        else:
            obj[prop_name] = bool(False)
    
    # Rename object to match IOI naming convention: base_name_LOD_0_______
    # IOI format: base_name_LOD_ followed by 8 characters (numbers for active LODs, underscores for inactive)
    obj_name = original_name
    
    # Remove any existing LOD suffix (like _LOD0, LOD1, _LOD_01234567, etc.)
    # IOI splits on "_LOD" to get the clean base name
    if "_LOD" in obj_name.upper():
        # Split on _LOD (case insensitive - handle both _LOD and _lod)
        parts = obj_name.split("_LOD", 1)
        if len(parts) > 1:
            # Remove everything after _LOD (including old LOD numbers or IOI format)
            clean_name = parts[0]
        else:
            clean_name = parts[0]
    else:
        # Try to remove LOD pattern without underscore (like LOD0 at end)
        clean_name = re.sub(r'LOD\d+$', '', obj_name, flags=re.IGNORECASE)
        if clean_name == obj_name:
            # No LOD pattern found, use original name
            clean_name = obj_name
    
    # Remove trailing underscores
    clean_name = clean_name.rstrip('_')
    
    # Build IOI LOD suffix: _LOD_ followed by 8 characters (numbers for active, underscores for inactive)
    lod_string = ""
    for i in range(8):
        if i == lod_level:
            lod_string += str(i)
        else:
            lod_string += "_"
    
    # Create new name in IOI format: base_name_LOD_0_______
    new_name = clean_name + "_LOD_" + lod_string
    
    # Only rename if different
    if obj.name != new_name:
        old_name = obj.name
        obj.name = new_name
        return old_name, new_name
    
    return None, None


def set_ioi_lod_properties_for_objects(objects):
    """Set IOI LOD properties on multiple objects.
    
    Args:
        objects: List of Blender objects to process
    """
    print(f"\n  {'─'*40}")
    print(f"  🏷️  SETTING IOI LOD PROPERTIES")
    print(f"  {'─'*40}")
    
    processed_count = 0
    renamed_count = 0
    for obj in objects:
        if obj.type == 'MESH' and obj.data:
            # Store original name before processing (for logging)
            original_name = obj.name
            # Let set_ioi_lod_properties handle LOD extraction and renaming
            old_name, new_name = set_ioi_lod_properties(obj, lod_level=None)
            processed_count += 1
            
            if old_name and new_name:
                renamed_count += 1
                # Extract LOD level for logging
                lod_level = extract_lod_from_object_name(old_name)
                print(f"    ✅ Set LOD properties and renamed '{old_name}' → '{new_name}' (LOD{lod_level})")
            else:
                # Extract LOD level for logging
                lod_level = extract_lod_from_object_name(obj.name)
                print(f"    ✅ Set LOD properties on '{obj.name}' (LOD{lod_level}, name already correct)")
    
    print(f"    📊 Processed {processed_count} object(s), renamed {renamed_count} object(s)")


def calculate_variation_bbox(mesh_objects):
    """Calculate the combined bounding box of all meshes in a variation.
    
    Args:
        mesh_objects: List of mesh objects
        
    Returns:
        dict: Dictionary with min_x, max_x, width, height, depth in world space units.
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


def create_asset_hierarchy(variations, attach_root_base_name, context):
    """Create attach root hierarchy for asset variations.
    
    Args:
        variations: Dictionary mapping variation_suffix to list of objects
        attach_root_base_name: Base name for attach roots (without variation suffix)
        context: Blender context
        
    Returns:
        list: List of created attach root objects
    """
    print(f"\n  {'─'*40}")
    print(f"  📦 STEP 6A: CALCULATING BOUNDING BOXES")
    print(f"  {'─'*40}")
    
    # Calculate bounding boxes for all variations BEFORE parenting
    variation_bboxes = {}
    for variation_suffix in sorted(variations.keys()):
        variation_objects = variations[variation_suffix]
        print(f"\n    📏 Calculating bbox for variation '_{variation_suffix}':")
        bbox = calculate_variation_bbox(variation_objects)
        variation_bboxes[variation_suffix] = bbox
    
    print(f"\n  {'─'*40}")
    print(f"  📦 STEP 6B: CREATING ATTACH ROOTS WITH PROPER SPACING")
    print(f"  {'─'*40}")
    
    current_y_offset = 0.0
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
        attach_root.scale = (1.0, 1.0, 1.0)
        attach_root.rotation_euler = (0.0, 0.0, 0.0)
        
        # Position attach root at current Y offset (this is the ONLY thing that moves in world space)
        attach_root.location.x = 0.0
        attach_root.location.y = current_y_offset
        attach_root.location.z = 0.0
        
        # Add IOI addon compatibility properties
        attach_root["ioiAttachRootNode"] = bool(True)
        attach_root["IoiG2ObjectType"] = str("static")
        attach_root["IoiGizmoSize"] = attach_root.empty_display_size * 100
        
        context.collection.objects.link(attach_root)
        created_attach_roots.append(attach_root)
        
        print(f"    📦 Created: {attach_root_name} at world position (0, {current_y_offset}, 0)")
        
        # Parent all variation objects to attach root
        # Objects keep their original world positions - Blender automatically calculates local positions
        # We don't modify object locations - they stay exactly where they are in world space
        for obj in variation_objects:
            if obj.type == 'MESH' and obj.data:
                # Store the object's current world position (for logging)
                world_pos = obj.location.copy()
                
                # Parent to attach root
                # Blender automatically converts world position to local position
                # The object's world position remains unchanged
                obj.parent = attach_root
                
                # After parenting, obj.location is now in LOCAL space relative to attach_root
                # We don't modify it - Blender already calculated it correctly to preserve world position
                print(f"      📍 Object '{obj.name}' at local position ({obj.location.x:.2f}, {obj.location.y:.2f}, {obj.location.z:.2f}) relative to attach root (world: {world_pos.x:.2f}, {world_pos.y:.2f}, {world_pos.z:.2f})")
        
        print(f"    ✅ Parented {len(variation_objects)} object(s) to attach root")
        
        # Update Y offset for next variation
        current_y_offset += bbox['height'] + margin
    
    return created_attach_roots


def cleanup_unused_materials(materials_before_import, imported_objects=None):
    """Clean up unused materials that were created during FBX import.

    Removes materials like 'MatID_1', 'MatID_2', etc. that are created by the FBX importer.
    ONLY removes materials that were created during THIS import, not existing ones.

    Args:
        materials_before_import: Set of material names that existed before import
        imported_objects: Optional list of objects that were imported (for more aggressive cleanup)
    """
    print(f"\n  🧹 CLEANING UP TEMPORARY MATERIALS:")

    # Pattern to match temporary materials created by FBX importer
    temp_material_patterns = [
        re.compile(r'^MatID_\d+', re.IGNORECASE),
        re.compile(r'^MATID_\d+', re.IGNORECASE),
        re.compile(r'^Material\.\d+$', re.IGNORECASE),
        re.compile(r'^Material$', re.IGNORECASE),
    ]

    removed_count = 0

    # Get current materials
    materials_after_import = set(bpy.data.materials.keys())

    # Find materials created during this import
    new_materials = materials_after_import - materials_before_import

    # Iterate through ONLY newly created materials
    for mat_name in new_materials:
        if mat_name not in bpy.data.materials:
            continue

        mat = bpy.data.materials[mat_name]

        # Check if it matches temporary material patterns
        is_temp_material = any(pattern.match(mat_name) for pattern in temp_material_patterns)

        if not is_temp_material:
            continue

        # This is a temp material created during THIS import - safe to remove
        try:
            if mat.users == 0:
                bpy.data.materials.remove(mat, do_unlink=True)
                print(f"    🗑️  Removed unused temporary material: {mat_name}")
                removed_count += 1
            else:
                # Material is in use - try to unlink and remove anyway
                print(f"    🗑️  Force removing temporary material (has {mat.users} users): {mat_name}")
                mat.user_clear()
                bpy.data.materials.remove(mat, do_unlink=True)
                removed_count += 1
        except Exception as e:
            print(f"    ⚠️  Failed to remove material '{mat_name}': {e}")

    if removed_count > 0:
        print(f"    ✅ Cleaned up {removed_count} temporary material(s)")
    else:
        print(f"    ℹ️  No temporary materials found to clean up")


def process_asset_directory(asset_dir):
    """Process an asset directory and return its type.
    
    This is a convenience function that validates and detects asset type.
    
    Args:
        asset_dir: Path to the asset directory
        
    Returns:
        tuple: (is_valid: bool, asset_type: str or None, error_message: str or None)
    """
    is_valid, error_msg, asset_type = validate_asset_directory(asset_dir)
    return is_valid, asset_type, error_msg

