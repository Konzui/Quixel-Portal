"""Validation utilities for paths and asset directories.

This module provides functions to validate file paths and asset structures.
"""

from pathlib import Path


def validate_path(path):
    """Validate that a path exists.
    
    Args:
        path: Path to validate (str or Path)
        
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    path = Path(path)
    
    if not path.exists():
        return False, f"Path does not exist: {path}"
    
    return True, None


def validate_asset_directory(asset_dir):
    """Validate that an asset directory exists and contains expected files.
    
    Args:
        asset_dir: Path to asset directory (str or Path)
        
    Returns:
        tuple: (is_valid: bool, error_message: str or None, asset_type: str or None)
               asset_type can be 'fbx', 'surface', or None
    """
    asset_dir = Path(asset_dir)
    
    if not asset_dir.exists():
        return False, f"Asset directory does not exist: {asset_dir}", None
    
    if not asset_dir.is_dir():
        return False, f"Path is not a directory: {asset_dir}", None
    
    # Check for FBX files
    fbx_files = list(asset_dir.glob("**/*.fbx"))
    if fbx_files:
        return True, None, 'fbx'
    
    # Check for surface material (JSON + textures)
    from .naming import find_json_file
    from .texture_loader import find_texture_files
    
    json_file = find_json_file(asset_dir)
    texture_files = find_texture_files(asset_dir)
    
    if json_file and texture_files:
        return True, None, 'surface'
    
    return False, "Asset directory contains neither FBX files nor surface material files", None

