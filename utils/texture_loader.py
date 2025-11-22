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
        print(f"    ✅ Loaded {tex_type}: {Path(tex_path).name}")
        return tex_node
    except Exception as e:
        print(f"    ❌ Failed to load {tex_type} texture {Path(tex_path).name}: {e}")
        nodes.remove(tex_node)
        return None


def find_texture_files(asset_dir, extensions=None):
    """Find all texture files in an asset directory.
    
    Args:
        asset_dir: Path to the asset directory
        extensions: Optional list of extensions to search for.
                   Defaults to common image formats.
        
    Returns:
        list: List of Path objects to texture files
    """
    if extensions is None:
        extensions = ['.png', '.jpg', '.jpeg', '.tga', '.tif', '.tiff', '.exr']
    
    asset_dir = Path(asset_dir)
    texture_files = []
    
    for ext in extensions:
        texture_files.extend(asset_dir.glob(f"**/*{ext}"))
        texture_files.extend(asset_dir.glob(f"**/*{ext.upper()}"))
    
    return texture_files


def identify_texture_type(filename):
    """Identify texture type from filename.
    
    Args:
        filename: Filename (or Path) to analyze
        
    Returns:
        str or None: Texture type ('albedo', 'roughness', 'normal', 'metallic', 'opacity', etc.)
                    or None if type cannot be determined
    """
    filename_lower = str(filename).lower()
    
    if 'albedo' in filename_lower or 'diffuse' in filename_lower or 'color' in filename_lower:
        return 'albedo'
    elif 'roughness' in filename_lower or 'rough' in filename_lower:
        return 'roughness'
    elif 'normal' in filename_lower and 'gl' not in filename_lower:
        return 'normal'
    elif 'displacement' in filename_lower or 'height' in filename_lower:
        return 'displacement'
    elif 'metallic' in filename_lower or 'metalness' in filename_lower:
        return 'metallic'
    elif 'opacity' in filename_lower or 'alpha' in filename_lower or 'mask' in filename_lower:
        return 'opacity'
    
    return None

