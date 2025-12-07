"""Material creator module for creating materials from textures.

This module handles material creation, texture discovery, and material assignment.
"""

import bpy
import re
import hashlib
from pathlib import Path

from ..utils.texture_loader import load_texture, find_texture_files, identify_texture_type, is_billboard_texture
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
            # Use HASHED for grass/foliage with alpha cutouts (avoids transparency sorting issues)
            mat.blend_method = 'HASHED'
            # Print removed to reduce console clutter
    
    # Print removed to reduce console clutter
    return mat


def get_texture_hash(textures):
    """Create a hash string from texture paths for caching materials.
    
    Args:
        textures: Dictionary of texture paths by type: {'albedo': path, 'roughness': path, ...}
                  Paths can be Path objects, dicts with 'path' key, or strings
        
    Returns:
        str: Hash string representing the texture combination
    """
    # Create a sorted string of all texture paths
    texture_types = ['albedo', 'roughness', 'normal', 'metallic', 'opacity']
    path_strings = []
    
    for tex_type in texture_types:
        if tex_type in textures and textures[tex_type]:
            tex_value = textures[tex_type]
            
            # Handle different formats: Path object, dict with 'path' key, or string
            if isinstance(tex_value, dict):
                # Extract path from dict
                tex_path = tex_value.get('path', tex_value)
            else:
                tex_path = tex_value
            
            # Convert to Path and resolve
            try:
                resolved_path = str(Path(tex_path).resolve())
                path_strings.append(f"{tex_type}:{resolved_path}")
            except (TypeError, ValueError, OSError) as e:
                # Fallback to string representation if Path conversion fails
                path_strings.append(f"{tex_type}:{str(tex_path)}")
        else:
            path_strings.append(f"{tex_type}:none")
    
    # Join and hash
    combined = "|".join(path_strings)
    hash_obj = hashlib.md5(combined.encode())
    return hash_obj.hexdigest()[:12]  # Use first 12 chars for readability


def find_textures_for_variation(asset_dir, variation_suffix, import_groups, texture_resolution=None, is_3d_plant=False, variation_folders=None):
    """Extract texture paths organized by LOD level for a specific variation.

    Args:
        asset_dir: Path to the asset directory
        variation_suffix: Variation suffix (e.g., 'a', 'b', '00', '01')
        import_groups: List of import groups containing FBX files and objects
        texture_resolution: Optional texture resolution filter (e.g., "2K", "4K", "8K")
        is_3d_plant: Whether this is a 3D plant asset
        variation_folders: Dict mapping variation_index -> folder_path (for 3D plants)

    Returns:
        dict: Dictionary structure: {lod_level: {'albedo': path, 'roughness': path, ...}}
    """
    asset_dir = Path(asset_dir)

    # For 3D plants, find the variation folder for this variation
    search_dir = asset_dir
    if is_3d_plant and variation_folders:
        # Convert variation_suffix to index (a->0, b->1, etc.)
        if variation_suffix.isdigit():
            variation_index = int(variation_suffix)
        else:
            # Convert letter to index: a->0, b->1, etc.
            variation_index = ord(variation_suffix.lower()) - ord('a')
        
        if variation_index in variation_folders:
            search_dir = variation_folders[variation_index]
    
    # Also search root directory for shared textures (billboard textures might be there)
    # Find all texture files in both the variation folder (for 3D plants) and root directory
    texture_files = []
    
    # Search in variation folder (for 3D plants) or root (for regular assets)
    variation_textures = find_texture_files(search_dir, texture_resolution=texture_resolution)
    texture_files.extend(variation_textures)
    
    # For 3D plants, also search root for shared/billboard textures
    if is_3d_plant and search_dir != asset_dir:
        root_textures = find_texture_files(asset_dir, texture_resolution=texture_resolution)
        texture_files.extend(root_textures)
    
    # Remove duplicates
    texture_files = list(set(texture_files))
    
    if not texture_files:
        return {}
    
    # Pattern to extract LOD level from FBX filenames (still needed for import groups)
    lod_pattern = re.compile(r'_?LOD(\d+)', re.IGNORECASE)
    
    # Common single letters that are NOT variations (part of asset naming)
    # These appear in asset names like "Aset_bricks_rubble_M_rjgse" where M is not a variation
    non_variation_letters = {'m'}  # Add more if needed (e.g., 's' for 'surface', etc.)
    
    # Group textures by LOD level and type
    # Structure: {lod_level: {'albedo': path, 'roughness': path, 'normal': path, 'metallic': path}}
    lod_textures = {}
    
    for tex_file in texture_files:
        # Split filename by underscores into words
        words = tex_file.stem.split('_')
        words_lower = [w.lower() for w in words]
        
        # For 3D plants, textures are in variation folders, so we don't need to filter by variation identifier
        # For regular assets, check if texture belongs to this variation
        belongs_to_variation = True
        
        if not is_3d_plant:
            # Regular asset: Check for variation identifier in words
            # Valid variations are: single letters (a-z) or two-digit numbers (00-99)
            # But exclude common non-variation letters like 'M' in asset names
            variation_found = False
            found_variation_value = None
            
            # Check for letter variation (a, b, c, etc.)
            if not variation_suffix.isdigit():
                # Looking for letter variation like 'a', 'b', 'c'
                variation_lower = variation_suffix.lower()
                if variation_lower in words_lower:
                    variation_found = True
                    found_variation_value = variation_lower
            else:
                # Looking for numeric variation like '00', '01', '02'
                # Check if the variation suffix exists as a word
                if variation_suffix in words:
                    variation_found = True
                    found_variation_value = variation_suffix
                # Also check zero-padded versions (e.g., '0' -> '00')
                elif len(variation_suffix) == 1:
                    padded = f"0{variation_suffix}"
                    if padded in words:
                        variation_found = True
                        found_variation_value = padded
            
            # Also check for any other variation identifiers that might conflict
            # Look for single letters or two-digit numbers that could be variations
            # BUT exclude known non-variation letters
            other_variations = []
            for word in words:
                word_lower = word.lower()
                # Single letter (a-z) - but exclude non-variation letters
                if len(word) == 1 and word_lower.isalpha() and word_lower not in non_variation_letters:
                    if word_lower != variation_suffix.lower():
                        other_variations.append(word_lower)
                # Two-digit number (00-99)
                elif len(word) == 2 and word.isdigit() and word != variation_suffix:
                    other_variations.append(word)
            
            if other_variations:
                # Texture has a variation identifier that doesn't match
                belongs_to_variation = False
        
        if not belongs_to_variation:
            continue
        
        # Extract LOD level from words
        # Look for "LOD" followed by a number, or "LOD0", "LOD1", etc. as a word
        lod_level = "0"  # Default
        lod_found_in_name = False
        for i, word in enumerate(words):
            word_lower = word.lower()
            # Check for "LOD" as a word followed by a number word
            if word_lower == "lod" and i + 1 < len(words):
                next_word = words[i + 1]
                if next_word.isdigit():
                    lod_level = next_word
                    lod_found_in_name = True
                    break
            # Check for "LOD0", "LOD1", etc. as a single word
            elif word_lower.startswith("lod") and len(word_lower) > 3:
                lod_num = word_lower[3:]
                if lod_num.isdigit():
                    lod_level = lod_num
                    lod_found_in_name = True
                    break
        
        # For 3D plants, if LOD not found in filename, check if texture is in a LOD-specific subfolder
        if not lod_found_in_name and is_3d_plant:
            # Check if texture is in a folder named "LOD0", "LOD1", etc.
            for parent in tex_file.parents:
                parent_name_lower = parent.name.lower()
                if parent_name_lower.startswith("lod"):
                    lod_num = parent_name_lower[3:]
                if lod_num.isdigit():
                    lod_level = lod_num
                    lod_found_in_name = True
                    break
        
        # Check if this is a billboard texture
        is_billboard = is_billboard_texture(tex_file.stem)
        
        # Identify texture type by filename
        tex_type = identify_texture_type(tex_file.stem)
        if not tex_type:
            continue
        
        # For textures without LOD in filename, assign to all LODs (except last if it's not billboard)
        # For billboard textures, only assign to last LOD
        # For textures with LOD in filename, assign to that specific LOD
        
        if is_billboard:
            # Billboard textures only go to the last LOD (we'll determine this later)
            # Store them separately for now
            if 'billboard_textures' not in lod_textures:
                lod_textures['billboard_textures'] = {}
            if tex_type not in lod_textures['billboard_textures']:
                lod_textures['billboard_textures'][tex_type] = tex_file
        else:
            # Regular texture - assign to the detected LOD level
            # If no LOD found, it will default to LOD 0, but we'll distribute it later
            if lod_level not in lod_textures:
                lod_textures[lod_level] = {}
            
            # Store texture info
            texture_info = {
                'path': tex_file,
                'is_billboard': False
            }
            
            # If there's already a texture of this type, keep the existing one
            if tex_type not in lod_textures[lod_level]:
                lod_textures[lod_level][tex_type] = texture_info
    
    # Get all LOD levels that have objects (from FBX imports)
    lod_levels_with_objects = set()
    for import_group in import_groups:
        fbx_file = import_group['fbx_file']
        lod_match = lod_pattern.search(fbx_file.stem)
        lod_level = lod_match.group(1) if lod_match else "0"
        lod_levels_with_objects.add(lod_level)
    
    # Find the highest/last LOD level
    all_lod_levels = sorted(lod_levels_with_objects, key=lambda x: int(x))
    last_lod_level = all_lod_levels[-1] if all_lod_levels else "0"
    
    # Extract billboard textures (stored separately)
    billboard_textures_dict = lod_textures.pop('billboard_textures', {})
    
    # Separate billboard and regular textures from lod_textures
    billboard_textures = {}  # {lod_level: {tex_type: path}}
    regular_textures = {}    # {lod_level: {tex_type: path}}
    
    # Initialize all LOD levels
    for lod_level in all_lod_levels:
        billboard_textures[lod_level] = {}
        regular_textures[lod_level] = {}
    
    # Process textures from lod_textures
    for lod_level, textures in lod_textures.items():
        for tex_type, texture_info in textures.items():
            # Handle both old format (just path) and new format (dict with path and is_billboard)
            if isinstance(texture_info, dict):
                is_billboard = texture_info.get('is_billboard', False)
                tex_path = texture_info['path']
            else:
                # Old format - check if it's billboard
                is_billboard = is_billboard_texture(texture_info.stem if hasattr(texture_info, 'stem') else str(texture_info))
                tex_path = texture_info
            
            if is_billboard:
                billboard_textures[lod_level][tex_type] = tex_path
            else:
                regular_textures[lod_level][tex_type] = tex_path
    
    # For textures without LOD in filename (defaulted to LOD 0), distribute them to all LODs
    # If billboard textures exist, last LOD will use those instead
    # If no billboard textures, last LOD will also get regular textures
    textures_without_lod = regular_textures.get("0", {})
    if textures_without_lod:
        has_billboard = bool(billboard_textures_dict)
        if has_billboard:
            # Distribute to all LODs except last (last will use billboard)
            for lod_level in all_lod_levels:
                if lod_level == last_lod_level:
                    continue  # Skip last LOD - it will use billboard textures
                
                for tex_type, tex_path in textures_without_lod.items():
                    if tex_type not in regular_textures[lod_level]:
                        regular_textures[lod_level][tex_type] = tex_path
        else:
            # No billboard textures - distribute to all LODs including last
            for lod_level in all_lod_levels:
                for tex_type, tex_path in textures_without_lod.items():
                    if tex_type not in regular_textures[lod_level]:
                        regular_textures[lod_level][tex_type] = tex_path
    
    # Assign billboard textures to last LOD
    if billboard_textures_dict:
        for tex_type, tex_path in billboard_textures_dict.items():
            billboard_textures[last_lod_level][tex_type] = tex_path
    
    # Now assign textures: billboard only to last LOD, regular to all LODs
    final_lod_textures = {}
    texture_types = ['albedo', 'roughness', 'normal', 'metallic', 'opacity']
    
    for lod_level in all_lod_levels:
        final_lod_textures[lod_level] = {}
        
        # For the last LOD level, use billboard textures if available, otherwise regular
        if lod_level == last_lod_level:
            # Prefer billboard textures for last LOD
            for tex_type in texture_types:
                if tex_type in billboard_textures.get(lod_level, {}):
                    final_lod_textures[lod_level][tex_type] = billboard_textures[lod_level][tex_type]
                elif tex_type in regular_textures.get(lod_level, {}):
                    final_lod_textures[lod_level][tex_type] = regular_textures[lod_level][tex_type]
        else:
            # For all other LOD levels, use regular textures only
            for tex_type in texture_types:
                if tex_type in regular_textures.get(lod_level, {}):
                    final_lod_textures[lod_level][tex_type] = regular_textures[lod_level][tex_type]
    
    # Fill in missing LOD levels with textures from previous available LOD
    # IMPORTANT: Don't fill the last LOD from previous LODs - it should have its own textures (billboard or regular)
    for lod_level in all_lod_levels:
        if lod_level not in final_lod_textures:
            final_lod_textures[lod_level] = {}
        
        # Skip filling for the last LOD - it should have its own textures
        if lod_level == last_lod_level:
            continue
        
        # For each texture type, find the most recent previous LOD that has it
        for tex_type in texture_types:
            if tex_type not in final_lod_textures[lod_level]:
                # Look backwards through LOD levels to find the most recent one with this texture
                current_lod_num = int(lod_level)
                for prev_lod_num in range(current_lod_num - 1, -1, -1):
                    prev_lod_str = str(prev_lod_num)
                    if prev_lod_str in final_lod_textures and tex_type in final_lod_textures[prev_lod_str]:
                        final_lod_textures[lod_level][tex_type] = final_lod_textures[prev_lod_str][tex_type]
                        break
    
    lod_textures = final_lod_textures
    
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
    
    return True


def create_materials_for_all_variations(asset_dir, attach_root_base_name, variations, all_import_groups, context, texture_resolution=None, is_3d_plant=False, variation_folders=None):
    """Create materials for all variations using hash-based caching to optimize material reuse.

    Args:
        asset_dir: Path to the asset directory
        attach_root_base_name: Base name for attach roots (without variation suffix)
        variations: Dictionary mapping variation_suffix to list of objects
        all_import_groups: List of all import groups (FBX files and their objects)
        context: Blender context
        texture_resolution: Optional texture resolution from Bridge (e.g., "2K", "4K", "8K")
        is_3d_plant: Whether this is a 3D plant asset
        variation_folders: Dict mapping variation_index -> folder_path (for 3D plants)
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
        # Get textures for this variation
        variation_textures = find_textures_for_variation(
            asset_dir, 
            variation_suffix, 
            all_import_groups, 
            texture_resolution,
            is_3d_plant=is_3d_plant,
            variation_folders=variation_folders
        )
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
        
        # Find the last/highest LOD level
        last_lod_level = all_lod_levels[-1] if all_lod_levels else None
        
        # Process each LOD level
        for lod_level in all_lod_levels:
            if lod_level not in variation_textures:
                continue
            
            textures = variation_textures[lod_level]
            
            # Normalize texture paths to Path objects (handle dict format)
            normalized_textures = {}
            for tex_type, tex_value in textures.items():
                if tex_value:
                    # Handle dict format: {'path': Path, 'is_billboard': bool}
                    if isinstance(tex_value, dict):
                        normalized_textures[tex_type] = tex_value.get('path', tex_value)
                    else:
                        normalized_textures[tex_type] = tex_value
                else:
                    normalized_textures[tex_type] = None
            
            # For the last LOD level, always create a separate material (for billboard support)
            # Include LOD level in hash to ensure unique material
            
            # Calculate hash with normalized textures
            texture_hash = get_texture_hash(normalized_textures)
            if lod_level == last_lod_level:
                texture_hash = texture_hash + f"_LOD{lod_level}"
            
            # Check if material already exists in cache
            if texture_hash in material_cache:
                # Reuse existing material
                mat = material_cache[texture_hash]
            else:
                # Create new material (use normalized textures)
                material_name = f"{attach_root_name}_LOD{lod_level}"
                mat = create_material_from_textures(material_name, normalized_textures, context)
                material_cache[texture_hash] = mat
            
            # Assign material to objects from this LOD level
            if lod_level in lod_objects:
                for obj in lod_objects[lod_level]:
                    # Clear all existing materials (including temporary MATID materials from FBX import)
                    obj.data.materials.clear()
                    # Assign our custom material
                    obj.data.materials.append(mat)

