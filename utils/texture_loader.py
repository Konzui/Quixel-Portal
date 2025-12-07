"""Texture loading utilities for creating image texture nodes in Blender.

This module handles texture file discovery and image node creation.
"""

import bpy
from pathlib import Path


def load_texture(nodes, tex_type, tex_path, color_space='sRGB'):
    """Load texture and create image texture node.
    
    Args:
        nodes: Blender node tree nodes collection
        tex_type: Type of texture (for logging)
        tex_path: Path to texture file
        color_space: Color space setting ('sRGB' or 'Non-Color')
        
    Returns:
        bpy.types.ShaderNodeTexImage or None: Created texture node, or None if failed
    """
    if not tex_path or not Path(tex_path).exists():
        return None
    
    # Create image texture node
    tex_node = nodes.new(type='ShaderNodeTexImage')
    tex_node.location = (-600, -200 * len([n for n in nodes if isinstance(n, bpy.types.ShaderNodeTexImage)]))
    
    # Load image
    try:
        img = bpy.data.images.load(str(tex_path))
        img.colorspace_settings.name = color_space
        tex_node.image = img
        return tex_node
    except Exception as e:
        print(f"    ❌ Failed to load {tex_type} texture {Path(tex_path).name}: {e}")
        nodes.remove(tex_node)
        return None


def find_texture_files(asset_dir, extensions=None, texture_resolution=None):
    """Find all texture files in an asset directory.

    Args:
        asset_dir: Path to the asset directory
        extensions: Optional list of extensions to search for.
                   Defaults to common image formats.
        texture_resolution: Optional resolution filter (e.g., "2K", "4K", "8K").
                           If specified, only textures matching this resolution will be returned.

    Returns:
        list: List of Path objects to texture files
    """
    if extensions is None:
        extensions = ['.png', '.jpg', '.jpeg', '.tga', '.tif', '.tiff', '.exr', '.hdr']

    asset_dir = Path(asset_dir)
    texture_files = []

    for ext in extensions:
        texture_files.extend(asset_dir.glob(f"**/*{ext}"))
        texture_files.extend(asset_dir.glob(f"**/*{ext.upper()}"))

    # Filter by resolution if specified
    if texture_resolution:
        # Normalize resolution (e.g., "2K" -> "2k" for comparison)
        resolution_lower = texture_resolution.lower()
        resolution_upper = texture_resolution.upper()

        filtered_files = []
        for tex_file in texture_files:
            # Split filename by underscores into words
            words = tex_file.stem.split('_')
            words_lower = [w.lower() for w in words]
            
            # Check if resolution exists as a word (e.g., "2K" or "2k" in the word list)
            # This handles both "2K" and "2k" formats
            has_resolution = (texture_resolution in words or 
                            resolution_lower in words_lower or 
                            resolution_upper in words)
            
            if has_resolution:
                filtered_files.append(tex_file)

        texture_files = filtered_files

    return texture_files


def is_billboard_texture(filename):
    """Check if a texture is a billboard texture.
    
    Billboard textures are typically used for the last LOD level in 3D plants.
    They usually have "billboard" in the filename.
    
    Args:
        filename: Filename (or Path) to analyze
        
    Returns:
        bool: True if texture appears to be a billboard texture
    """
    # Split filename by underscores into words
    words = str(filename).split('_')
    words_lower = [w.lower() for w in words]
    
    # Check for billboard keywords
    billboard_keywords = ['billboard', 'bb', 'bill']
    
    # Check if any billboard keyword exists as a word
    return any(keyword in words_lower for keyword in billboard_keywords)


def identify_texture_type(filename):
    """Identify texture type from filename using word-splitting approach.
    
    Splits filename by underscores and checks if texture type keywords exist as words.
    This is more reliable than substring matching.
    
    Args:
        filename: Filename (or Path) to analyze
        
    Returns:
        str or None: Texture type ('albedo', 'roughness', 'normal', 'metallic', 'opacity', etc.)
                    or None if type cannot be determined
    """
    # Split filename by underscores into words (case-insensitive comparison)
    words = str(filename).split('_')
    words_lower = [w.lower() for w in words]
    
    # Check each texture type - look for keywords as complete words
    checks = [
        ('albedo', ['albedo', 'diffuse', 'color']),
        ('roughness', ['roughness', 'rough']),
        ('normal', ['normal'], ['gl', 'gloss']),  # normal but not gl/gloss (those are separate types)
        ('displacement', ['displacement', 'height']),
        ('metallic', ['metallic', 'metalness']),
        ('opacity', ['opacity', 'alpha', 'mask']),
    ]
    
    for tex_type, keywords, *exclusions in checks:
        exclusions = exclusions[0] if exclusions else []
        
        # Check if any keyword exists as a word (exact match, case-insensitive)
        keyword_found = any(kw.lower() in words_lower for kw in keywords)
        
        # Check if any exclusion exists as a word
        exclusion_found = any(ex.lower() in words_lower for ex in exclusions) if exclusions else False
        
        if keyword_found and not exclusion_found:
            return tex_type
    
    return None

