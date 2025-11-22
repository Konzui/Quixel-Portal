"""Utility modules for common helper functions.

This package contains utility functions for naming, texture loading, and validation.
"""

from .naming import (
    find_json_file,
    get_name_from_json,
    get_material_name_from_json,
    detect_variation_number,
    index_to_letter_suffix,
    get_base_name,
)
from .texture_loader import (
    load_texture,
    find_texture_files,
    identify_texture_type,
)
from .validation import (
    validate_asset_directory,
    validate_path,
)

__all__ = [
    'find_json_file',
    'get_name_from_json',
    'get_material_name_from_json',
    'detect_variation_number',
    'index_to_letter_suffix',
    'get_base_name',
    'load_texture',
    'find_texture_files',
    'identify_texture_type',
    'validate_asset_directory',
    'validate_path',
]

