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


def is_folder_empty(asset_dir):
    """Check if a folder is completely empty.
    
    Args:
        asset_dir: Path to asset directory (str or Path)
        
    Returns:
        tuple: (is_empty: bool, error_message: str or None)
    """
    asset_dir = Path(asset_dir)
    
    if not asset_dir.exists():
        return False, f"Directory does not exist: {asset_dir}"
    
    if not asset_dir.is_dir():
        return False, f"Path is not a directory: {asset_dir}"
    
    try:
        # Check if directory has any entries
        entries = list(asset_dir.iterdir())
        if len(entries) == 0:
            return True, "Folder is completely empty"
        return False, None
    except PermissionError:
        return False, f"Permission denied accessing directory: {asset_dir}"
    except Exception as e:
        return False, f"Error checking directory: {e}"


def check_folder_contents(asset_dir):
    """Check folder contents and provide detailed status.
    
    Args:
        asset_dir: Path to asset directory (str or Path)
        
    Returns:
        dict: {
            'exists': bool,
            'is_directory': bool,
            'is_empty': bool,
            'has_fbx': bool,
            'has_surface_material': bool,
            'fbx_count': int,
            'json_file': Path or None,
            'texture_count': int,
            'error': str or None
        }
    """
    asset_dir = Path(asset_dir)
    result = {
        'exists': False,
        'is_directory': False,
        'is_empty': False,
        'has_fbx': False,
        'has_surface_material': False,
        'fbx_count': 0,
        'json_file': None,
        'texture_count': 0,
        'error': None
    }
    
    if not asset_dir.exists():
        result['error'] = f"Directory does not exist: {asset_dir}"
        return result
    
    result['exists'] = True
    
    if not asset_dir.is_dir():
        result['error'] = f"Path is not a directory: {asset_dir}"
        return result
    
    result['is_directory'] = True
    
    try:
        # Check if empty
        entries = list(asset_dir.iterdir())
        if len(entries) == 0:
            result['is_empty'] = True
            result['error'] = "Folder is completely empty"
            return result
        
        # Check for FBX files
        fbx_files = list(asset_dir.glob("**/*.fbx"))
        result['fbx_count'] = len(fbx_files)
        result['has_fbx'] = len(fbx_files) > 0
        
        # Check for surface material (JSON + textures)
        from .naming import find_json_file
        from .texture_loader import find_texture_files
        
        json_file = find_json_file(asset_dir)
        texture_files = find_texture_files(asset_dir)
        
        result['json_file'] = json_file
        result['texture_count'] = len(texture_files) if texture_files else 0
        result['has_surface_material'] = json_file is not None and texture_files is not None and len(texture_files) > 0
        
        # If neither FBX nor surface material found, set error
        if not result['has_fbx'] and not result['has_surface_material']:
            result['error'] = "Folder exists but contains neither FBX files nor surface material files"
        
    except PermissionError:
        result['error'] = f"Permission denied accessing directory: {asset_dir}"
    except Exception as e:
        result['error'] = f"Error checking directory contents: {e}"
    
    return result


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
    
    # Check if folder is empty
    is_empty, empty_error = is_folder_empty(asset_dir)
    if is_empty:
        return False, empty_error or "Asset directory is empty", None
    
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

