"""Naming utility functions for asset and material naming conventions.

This module handles JSON parsing, name extraction, and variation detection.
"""

import json
import re
from pathlib import Path


def find_json_file(asset_dir):
    """Find the JSON metadata file in the asset directory.
    
    Args:
        asset_dir: Path to the asset directory
        
    Returns:
        Path or None: Path to JSON file if found, None otherwise
    """
    asset_dir = Path(asset_dir)
    json_files = list(asset_dir.glob("*.json"))
    
    if not json_files:
        # Also check subdirectories
        json_files = list(asset_dir.glob("**/*.json"))
    
    # Prefer files that look like metadata (not config files)
    for json_file in json_files:
        if json_file.stem not in ['config', 'settings', 'package']:
            return json_file
    
    # Return first JSON file if no specific one found
    return json_files[0] if json_files else None


def get_name_from_json(asset_dir):
    """Extract name from JSON file following the naming convention.
    
    Args:
        asset_dir: Path to the asset directory
        
    Returns:
        tuple: (name: str or None, json_file: Path or None)
    """
    json_file = find_json_file(asset_dir)
    if not json_file:
        return None, None
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        # Get name from semanticTags.name
        semantic_tags = json_data.get('semanticTags', {})
        semantic_name = semantic_tags.get('name', '')
        
        if not semantic_name:
            return None, None
        
        # Replace spaces with underscores and convert to lowercase
        semantic_name_clean = semantic_name.replace(' ', '_').lower()
        
        # Get JSON filename without extension and convert to lowercase
        json_stem = json_file.stem.lower()
        
        # Construct name: quixel_{semantic_name}_{json_filename}_a (all lowercase)
        name = f"quixel_{semantic_name_clean}_{json_stem}_a"
        
        return name, json_file
    except Exception as e:
        print(f"  ⚠️ Failed to parse JSON file {json_file}: {e}")
        return None, None


def get_material_name_from_json(asset_dir, json_filename=None):
    """Extract material name from JSON file following the naming convention.
    
    Args:
        asset_dir: Path to the asset directory
        json_filename: Optional JSON filename (unused, kept for compatibility)
        
    Returns:
        str or None: Material name if found, None otherwise
    """
    name, _ = get_name_from_json(asset_dir)
    return name


def detect_variation_number(obj_name):
    """Detect variation NUMBER from object name (not the final suffix).

    This extracts the numeric identifier like _00, _01, _02 from filenames like:
    Aset_building__M_wkkmfa3dw_00_LOD0 → 0
    Aset_building__M_wkkmfa3dw_01_LOD0 → 1

    Also handles IOI format:
    Aset_building__M_wkkmfa3dw_00_a_LOD_0_______ → index 0 (from letter 'a')

    Args:
        obj_name: Object name to analyze

    Returns:
        int: Variation index (0 as default if no variation detected)
    """
    # Remove Blender's auto-numbering suffix (.001, .002, etc.) FIRST if present
    # This happens when objects are renamed and Blender adds a number to avoid duplicates
    # We need to remove this BEFORE removing LOD suffixes so the LOD regex patterns work correctly
    name_without_numbering = re.sub(r'\.\d+$', '', obj_name)
    
    # Remove LOD suffix to isolate the variation suffix
    # Handle both standard format (LOD0, LOD1) and IOI format (_LOD_0_______)
    # Note: IOI format must be checked first because it's more specific
    # IOI format: _LOD_ followed by exactly 8 characters (digits or underscores)
    name_without_lod = re.sub(r'_LOD_[_0-9]{8}$', '', name_without_numbering, flags=re.IGNORECASE)  # IOI format
    name_without_lod = re.sub(r'_?LOD\d+$', '', name_without_lod, flags=re.IGNORECASE)  # Standard format
    
    # Pattern 1: _A, _B, _C (case insensitive, single letter at end)
    # Convert to index: a=0, b=1, c=2, etc.
    # This pattern must come BEFORE the numeric patterns to prioritize letter suffixes
    # Try to match a single letter suffix at the end
    match = re.search(r'_([a-z])$', name_without_lod, re.IGNORECASE)
    if match:
        letter = match.group(1).lower()
        index = ord(letter) - ord('a')
        # Print removed to reduce console clutter
        return index
    
    # Pattern 2: _01, _02, _03 (numerical suffixes, 2 digits at end)
    match = re.search(r'_(\d{2})$', name_without_lod)
    if match:
        index = int(match.group(1))
        # Print removed to reduce console clutter
        return index
    
    # Pattern 3: Single digit at end (1, 2, 3)
    match = re.search(r'_(\d)$', name_without_lod)
    if match:
        index = int(match.group(1))
        # Print removed to reduce console clutter
        return index
    
    # Default: first variation
    # Print removed to reduce console clutter
    return 0


def index_to_letter_suffix(index):
    """Convert a numeric index to a letter suffix.
    
    0 → 'a'
    1 → 'b'
    25 → 'z'
    26 → 'aa'
    27 → 'ab'
    etc.
    
    Args:
        index: Numeric index to convert
        
    Returns:
        str: Letter suffix
    """
    if index < 0:
        index = 0
    
    suffix = ''
    
    # Handle indices 0-25 (a-z)
    if index < 26:
        suffix = chr(ord('a') + index)
    else:
        # Handle indices >= 26 (aa, ab, ac, etc.)
        # Convert to base-26 representation
        while index >= 0:
            suffix = chr(ord('a') + (index % 26)) + suffix
            index = index // 26 - 1
            if index < 0:
                break
    
    # Print removed to reduce console clutter
    return suffix


def get_base_name(name):
    """Extract base name from object name, removing only the LOD suffix at the end.
    
    Args:
        name: Object name to process
        
    Returns:
        str: Base name without LOD suffix
    """
    # Pattern to match LOD suffixes
    lod_pattern = re.compile(r'_?LOD\d+$', re.IGNORECASE)
    
    # Remove LOD suffix if present (only at the very end)
    match = lod_pattern.search(name)
    if match:
        # Verify the match is at the very end of the string
        if match.end() == len(name):
            # Only remove if the match is at the very end
            base_name = name[:match.start()]
            return base_name
    
    return name

