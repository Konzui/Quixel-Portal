"""Material creator module for creating materials from textures.

This module handles material creation, texture discovery, and material assignment.
"""

import bpy
import re
import hashlib
from pathlib import Path

from ..utils.texture_loader import load_texture, find_texture_files, identify_texture_type
from ..utils.naming import find_json_file


def create_material_from_textures(material_name, textures, context):
    """Create a material from texture paths and return it.

    If a material with the same name already exists, it will be reused instead of creating a new one.
    This allows multiple imports of the same asset to share materials.

    Args:
        material_name: Name for the material
        textures: Dictionary of texture paths by type: {'albedo': path, 'roughness': path, ...}
        context: Blender context

    Returns:
        bpy.types.Material: Created or existing material object
    """
    # Check if material already exists - if so, reuse it
    if material_name in bpy.data.materials:
        mat = bpy.data.materials[material_name]
        print(f"  ♻️  Reusing existing material: {material_name}")
        return mat

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


def get_texture_hash(textures):
    """Create a hash string from texture paths for caching materials.
    
    Args:
        textures: Dictionary of texture paths by type: {'albedo': path, 'roughness': path, ...}
        
    Returns:
        str: Hash string representing the texture combination
    """
    # Create a sorted string of all texture paths
    texture_types = ['albedo', 'roughness', 'normal', 'metallic', 'opacity']
    path_strings = []
    
    for tex_type in texture_types:
        if tex_type in textures and textures[tex_type]:
            # Use resolved path for consistent hashing
            path_strings.append(f"{tex_type}:{str(Path(textures[tex_type]).resolve())}")
        else:
            path_strings.append(f"{tex_type}:none")
    
    # Join and hash
    combined = "|".join(path_strings)
    hash_obj = hashlib.md5(combined.encode())
    return hash_obj.hexdigest()[:12]  # Use first 12 chars for readability


def find_textures_for_variation(asset_dir, variation_suffix, import_groups):
    """Extract texture paths organized by LOD level for a specific variation.
    
    Args:
        asset_dir: Path to the asset directory
        variation_suffix: Variation suffix (e.g., 'a', 'b', '00', '01')
        import_groups: List of import groups containing FBX files and objects
        
    Returns:
        dict: Dictionary structure: {lod_level: {'albedo': path, 'roughness': path, ...}}
    """
    asset_dir = Path(asset_dir)
    
    # Find all texture files in the asset directory
    texture_files = find_texture_files(asset_dir)
    
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
        variation_patterns.append(re.compile(rf'{variation_suffix}(?:_|LOD|$)', re.IGNORECASE))
    else:
        # Letter variation: try _a, _b, etc.
        variation_patterns.append(re.compile(rf'_{variation_suffix}(?:_|LOD|$)', re.IGNORECASE))
        variation_patterns.append(re.compile(rf'{variation_suffix}(?:_|LOD|$)', re.IGNORECASE))
    
    # Group textures by LOD level and type
    # Structure: {lod_level: {'albedo': path, 'roughness': path, 'normal': path, 'metallic': path}}
    lod_textures = {}
    
    for tex_file in texture_files:
        filename_lower = tex_file.stem.lower()
        
        # Check if this texture belongs to this variation
        belongs_to_variation = True
        
        # Check if filename contains any variation identifier (letter or numeric)
        any_variation_pattern = re.compile(r'(_[a-z]{1,2}|_\d{1,2})(?:_|LOD|$)', re.IGNORECASE)
        variation_matches = list(any_variation_pattern.finditer(tex_file.stem))
        
        if variation_matches:
            # Texture has variation identifier(s) - check if it matches this variation
            has_matching_variation = any(pattern.search(tex_file.stem) for pattern in variation_patterns)
            if not has_matching_variation:
                # Texture has variation identifier but doesn't match this variation
                belongs_to_variation = False
        
        if not belongs_to_variation:
            continue
        
        # Extract LOD level
        lod_match = lod_pattern.search(tex_file.stem)
        lod_level = lod_match.group(1) if lod_match else "0"
        
        if lod_level not in lod_textures:
            lod_textures[lod_level] = {}
        
        # Identify texture type by filename
        tex_type = identify_texture_type(tex_file.stem)
        if tex_type:
            lod_textures[lod_level][tex_type] = tex_file
    
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


def compare_texture_sets(texture_sets):
    """Compare texture sets across variations to determine if they are identical.
    
    Args:
        texture_sets: Dictionary mapping variation_suffix to texture dict
                     {variation_suffix: {lod_level: {'albedo': path, ...}}}
    
    Returns:
        tuple: (are_identical: bool, shared_textures: dict or None)
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
                first_path_str = str(Path(first_path).resolve()) if first_path else None
                other_path_str = str(Path(other_path).resolve()) if other_path else None
                
                if first_path_str != other_path_str:
                    return False, None
    
    # All variations have identical textures
    return True, first_textures


def create_surface_material(asset_dir, context):
    """Create a material for a surface asset from JSON and textures.
    
    Args:
        asset_dir: Path to the asset directory
        context: Blender context
        
    Returns:
        bool: True if material was created successfully, False otherwise
    """
    asset_dir = Path(asset_dir)
    
    # Find JSON file
    json_file = find_json_file(asset_dir)
    if not json_file:
        print(f"  ⚠️ No JSON file found in {asset_dir}")
        return False
    
    # Get material name from JSON
    from ..utils.naming import get_material_name_from_json
    material_name = get_material_name_from_json(asset_dir)
    if not material_name:
        print(f"  ⚠️ Could not extract material name from JSON")
        return False
    
    # Find all texture files
    texture_files = find_texture_files(asset_dir)

    if not texture_files:
        print(f"  ⚠️ No texture files found in {asset_dir}")
        return False

    # Check if material already exists - if so, reuse it
    if material_name in bpy.data.materials:
        mat = bpy.data.materials[material_name]
        print(f"  ♻️  Reusing existing surface material: {material_name}")
    else:
        # Organize textures by type
        textures = {}
        for tex_file in texture_files:
            tex_type = identify_texture_type(tex_file.stem)
            if tex_type:
                textures[tex_type] = tex_file

        # Create material
        mat = create_material_from_textures(material_name, textures, context)
    
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


def create_materials_for_all_variations(asset_dir, attach_root_base_name, variations, all_import_groups, context):
    """Create materials for all variations using hash-based caching to optimize material reuse.
    
    Args:
        asset_dir: Path to the asset directory
        attach_root_base_name: Base name for attach roots (without variation suffix)
        variations: Dictionary mapping variation_suffix to list of objects
        all_import_groups: List of all import groups (FBX files and their objects)
        context: Blender context
    """
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
        variation_textures = find_textures_for_variation(asset_dir, variation_suffix, all_import_groups)
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
            texture_hash = get_texture_hash(textures)
            
            # Check if material already exists in cache
            if texture_hash in material_cache:
                # Reuse existing material
                mat = material_cache[texture_hash]
                print(f"         ♻️  LOD{lod_level}: Reusing material '{mat.name}' (hash: {texture_hash})")
            else:
                # Create new material
                material_name = f"{attach_root_name}_LOD{lod_level}"
                mat = create_material_from_textures(material_name, textures, context)
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

