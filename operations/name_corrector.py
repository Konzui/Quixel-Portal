"""Name corrector module for fixing incorrect object names after FBX import.

This module handles matching imported objects to their source FBX files and
renaming them to follow the correct naming convention.
"""

import re
from pathlib import Path
from collections import defaultdict

from ..utils.naming import get_base_name, detect_variation_number, index_to_letter_suffix


def extract_lod_from_fbx(fbx_file):
    """Extract LOD level from FBX filename.
    
    Args:
        fbx_file: Path to FBX file
        
    Returns:
        tuple: (lod_level: str, has_lod: bool)
               Returns ("0", False) if no LOD found
    """
    fbx_file = Path(fbx_file)
    filename = fbx_file.stem  # Get filename without extension
    
    # Pattern to match LOD in filename: _LOD0, _LOD1, LOD0, LOD1, etc.
    lod_patterns = [
        re.compile(r'_?LOD(\d+)', re.IGNORECASE),  # Matches _LOD0, LOD1, etc.
        re.compile(r'LOD(\d+)', re.IGNORECASE),     # Matches LOD0, LOD1 (without underscore)
    ]
    
    for pattern in lod_patterns:
        match = pattern.search(filename)
        if match:
            lod_level = match.group(1)
            return lod_level, True
    
    # No LOD found, default to 0
    return "0", False


def build_expected_naming(fbx_files, base_name):
    """Build expected naming patterns for objects from FBX files.
    
    Args:
        fbx_files: List of FBX file paths
        base_name: Base name for the asset
        
    Returns:
        dict: Maps fbx_file -> {'lod_level': str, 'expected_base': str}
    """
    expected_naming = {}
    
    for fbx_file in fbx_files:
        lod_level, has_lod = extract_lod_from_fbx(fbx_file)
        expected_naming[fbx_file] = {
            'lod_level': lod_level,
            'expected_base': base_name,
            'has_lod_in_filename': has_lod
        }
    
    return expected_naming


def find_canonical_base_name(import_results):
    """Find the canonical base name from correctly named objects.
    
    This function looks at all imported objects and finds the most common
    base name from objects that follow the expected naming pattern.
    This ensures all objects from the same asset get the same base name.
    
    Args:
        import_results: List of tuples (fbx_file, imported_objects, base_name)
        
    Returns:
        str or None: Canonical base name if found, None otherwise
    """
    from collections import Counter
    
    # Collect all base names from objects that look correctly named
    # A correctly named object should have: {base}_{variation}_LOD{lod}
    # Example: "Aset_props__M_wk2jchx_00_a_LOD2"
    base_name_candidates = []
    
    for fbx_file, imported_objects, _ in import_results:
        for obj in imported_objects:
            if obj.type != 'MESH' or not obj.data:
                continue
            
            obj_name = obj.name
            
            # Check if object name follows expected pattern
            # Pattern: {base}_{variation}_LOD{lod}
            # Look for LOD suffix at the end
            lod_match = re.search(r'_?LOD\d+$', obj_name, re.IGNORECASE)
            if not lod_match:
                continue  # Skip objects without LOD suffix
            
            # Check for variation pattern: _00_a, _01_b, etc. or just _a, _b before LOD
            # Pattern 1: _00_a_LOD0 or _01_b_LOD1 (with numbers)
            # Pattern 2: _a_LOD0 or _b_LOD1 (without numbers)
            variation_pattern = r'_\d{2}_[a-z]_LOD|_[a-z]_LOD'
            has_variation = bool(re.search(variation_pattern, obj_name, re.IGNORECASE))
            
            # If it has LOD and looks like it has a variation pattern, it's likely correctly named
            if has_variation:
                # Extract base name by removing variation and LOD
                # Remove LOD suffix first
                name_without_lod = obj_name[:lod_match.start()]
                # Remove variation suffix: _00_a or _a
                base_clean = re.sub(r'_\d{2}_[a-z]$|_[a-z]$', '', name_without_lod, flags=re.IGNORECASE)
                if base_clean and len(base_clean) > 3:  # Must be meaningful
                    base_name_candidates.append(base_clean)
                    print(f"    🔍 Found candidate base name: '{base_clean}' from object '{obj_name}'")
            else:
                # Even without clear variation pattern, if it has LOD, try to extract base
                # This handles cases like "Aset_props__M_wk2jchx_LOD2"
                name_without_lod = obj_name[:lod_match.start()]
                # Remove trailing underscores
                base_clean = name_without_lod.rstrip('_')
                if base_clean and len(base_clean) > 3:
                    base_name_candidates.append(base_clean)
                    print(f"    🔍 Found candidate base name (no variation): '{base_clean}' from object '{obj_name}'")
    
    if not base_name_candidates:
        # Fallback: try to extract from FBX filenames
        for fbx_file, _, _ in import_results:
            fbx_stem = Path(fbx_file).stem
            # Remove LOD suffix
            lod_match = re.search(r'_?LOD\d+$', fbx_stem, re.IGNORECASE)
            if lod_match:
                name_without_lod = fbx_stem[:lod_match.start()]
                # Remove variation suffix if present
                base_clean = re.sub(r'_\d{2}_[a-z]$|_[a-z]$', '', name_without_lod, flags=re.IGNORECASE).strip('_')
                if base_clean and len(base_clean) > 3:
                    base_name_candidates.append(base_clean)
                    print(f"    🔍 Found candidate base name from FBX: '{base_clean}' from '{fbx_file.name}'")
    
    if not base_name_candidates:
        return None
    
    # Find the most common base name (should be the canonical one)
    base_name_counter = Counter(base_name_candidates)
    canonical_base = base_name_counter.most_common(1)[0][0]
    
    print(f"    ✅ Canonical base name determined: '{canonical_base}' (appears {base_name_counter[canonical_base]} time(s))")
    
    return canonical_base


def match_objects_to_fbx(import_results, canonical_base_name):
    """Match imported objects to their source FBX files.
    
    Since objects are imported together with their FBX file, we can directly
    match them. Uses the canonical base name for all objects from the same asset.
    
    Args:
        import_results: List of tuples (fbx_file, imported_objects, base_name)
        canonical_base_name: The canonical base name to use for all objects
        
    Returns:
        dict: Maps object -> {'fbx_file': Path, 'lod_level': str, 'expected_base': str, 'match_confidence': str}
    """
    object_to_fbx = {}
    
    # Use canonical base name for all objects from this asset
    # This ensures objects with wrong names still get grouped correctly
    for fbx_file, imported_objects, _ in import_results:
        lod_level, has_lod = extract_lod_from_fbx(fbx_file)
        
        # Use canonical base name for all objects from this asset
        expected_base = canonical_base_name if canonical_base_name else "unknown"
        
        # Match all objects from this import to this FBX file
        for obj in imported_objects:
            if obj.type != 'MESH' or not obj.data:
                continue
            
            # Objects imported together definitely belong to this FBX
            # Check if name matches expected pattern
            match_confidence = _match_object_to_fbx(obj, fbx_file, lod_level, expected_base)
            
            object_to_fbx[obj] = {
                'fbx_file': fbx_file,
                'lod_level': lod_level,
                'expected_base': expected_base,
                'match_confidence': match_confidence or 'direct'  # Direct import match is most reliable
            }
    
    return object_to_fbx


def _match_object_to_fbx(obj, fbx_file, lod_level, expected_base):
    """Check if an object's name matches the expected pattern for an FBX file.
    
    Returns:
        str or None: Match confidence level ('high', 'medium', 'low') or None if no match
    """
    obj_name_lower = obj.name.lower()
    fbx_name_lower = Path(fbx_file).stem.lower()
    expected_base_lower = expected_base.lower()
    
    # HIGH CONFIDENCE: Object name contains expected base AND LOD level
    if expected_base_lower in obj_name_lower:
        # Check if LOD matches
        lod_in_name = f"lod{lod_level}" in obj_name_lower
        if lod_in_name:
            return 'high'
        # Base matches but LOD doesn't - still likely a match
        return 'medium'
    
    # MEDIUM CONFIDENCE: Object name contains part of FBX filename
    # Extract base from FBX filename (remove LOD suffix)
    fbx_base = re.sub(r'_?lod\d+', '', fbx_name_lower, flags=re.IGNORECASE).strip('_')
    if fbx_base and fbx_base in obj_name_lower:
        return 'medium'
    
    # LOW CONFIDENCE: Name doesn't match, but object was imported with this FBX
    # This is the fallback case - we'll rename it anyway
    return 'low'


def rename_objects_to_match(objects, fbx_mapping):
    """Rename objects to match expected naming convention.
    
    Args:
        objects: List of objects to potentially rename
        fbx_mapping: Dict mapping object -> {'fbx_file', 'lod_level', 'expected_base', 'match_confidence'}
        
    Returns:
        dict: Statistics about renaming (renamed_count, skipped_count, etc.)
    """
    stats = {
        'renamed': 0,
        'skipped': 0,
        'no_match': 0,
        'already_correct': 0
    }
    
    print(f"\n  {'─'*40}")
    print(f"  🔤 RENAMING OBJECTS TO MATCH NAMING CONVENTION")
    print(f"  {'─'*40}")
    
    for obj in objects:
        if obj.type != 'MESH' or not obj.data:
            continue
        
        # Check if object is in mapping
        if obj not in fbx_mapping:
            stats['no_match'] += 1
            print(f"    ⚠️  Object '{obj.name}' has no FBX match - skipping")
            continue
        
        mapping = fbx_mapping[obj]
        fbx_file = mapping['fbx_file']
        lod_level = mapping['lod_level']
        expected_base = mapping['expected_base']
        confidence = mapping['match_confidence']
        
        # Extract variation from current object name
        variation_index = detect_variation_number(obj.name)
        variation_suffix = index_to_letter_suffix(variation_index)
        
        # Build expected name: {base}_{variation}_LOD{lod}
        expected_name = f"{expected_base}_{variation_suffix}_LOD{lod_level}"
        
        # Check if name already matches
        if obj.name == expected_name:
            stats['already_correct'] += 1
            print(f"    ✅ Object '{obj.name}' already has correct name")
            continue
        
        # Check if name is close (maybe just missing LOD or variation)
        current_base = get_base_name(obj.name)
        if current_base == expected_base:
            # Base matches, just needs LOD/variation fix
            old_name = obj.name
            obj.name = expected_name
            stats['renamed'] += 1
            print(f"    🔤 Renamed '{old_name}' → '{expected_name}' (confidence: {confidence})")
        else:
            # Name is completely wrong - rename it
            old_name = obj.name
            obj.name = expected_name
            stats['renamed'] += 1
            print(f"    🔤 Renamed '{old_name}' → '{expected_name}' (confidence: {confidence}, name was incorrect)")
    
    print(f"\n  📊 Renaming Summary:")
    print(f"     ✅ Renamed: {stats['renamed']}")
    print(f"     ✓ Already correct: {stats['already_correct']}")
    print(f"     ⚠️  No match: {stats['no_match']}")
    
    return stats


def validate_lod_completeness(import_groups):
    """Validate that all expected LOD levels are present.
    
    Args:
        import_groups: List of import groups, each with 'fbx_file' and 'objects'
        
    Returns:
        dict: Validation results with missing LODs and warnings
    """
    print(f"\n  {'─'*40}")
    print(f"  ✅ VALIDATING LOD COMPLETENESS")
    print(f"  {'─'*40}")
    
    # Extract LOD levels from FBX files
    expected_lods = set()
    fbx_to_lod = {}
    
    for import_group in import_groups:
        fbx_file = import_group['fbx_file']
        lod_level, has_lod = extract_lod_from_fbx(fbx_file)
        expected_lods.add(lod_level)
        fbx_to_lod[fbx_file] = lod_level
    
    # Check which LODs have objects
    found_lods = set()
    for import_group in import_groups:
        fbx_file = import_group['fbx_file']
        objects = import_group.get('objects', [])
        lod_level = fbx_to_lod[fbx_file]
        
        # Check if any mesh objects exist for this LOD
        has_meshes = any(obj.type == 'MESH' and obj.data for obj in objects)
        if has_meshes:
            found_lods.add(lod_level)
    
    # Find missing LODs
    missing_lods = expected_lods - found_lods
    
    if missing_lods:
        print(f"    ⚠️  Missing LOD levels: {sorted(missing_lods)}")
        print(f"    ℹ️  Expected LODs: {sorted(expected_lods)}")
        print(f"    ℹ️  Found LODs: {sorted(found_lods)}")
    else:
        print(f"    ✅ All expected LOD levels present: {sorted(expected_lods)}")
    
    return {
        'expected_lods': expected_lods,
        'found_lods': found_lods,
        'missing_lods': missing_lods,
        'is_complete': len(missing_lods) == 0
    }


def correct_object_names(import_results, fallback_base_name=None):
    """Main function to correct object names after import.
    
    This function:
    1. Finds the canonical base name from correctly named objects
    2. Matches objects to their source FBX files
    3. Renames objects to match expected naming convention
    4. Updates base_name in import_results to ensure correct grouping
    5. Validates LOD completeness
    
    Args:
        import_results: List of tuples (fbx_file, imported_objects, base_name)
                       NOTE: base_name in tuples will be updated in-place
        fallback_base_name: Optional fallback base name if none can be detected
        
    Returns:
        dict: Statistics and validation results, including canonical_base_name
    """
    print(f"\n  {'─'*40}")
    print(f"  🔍 NAME CORRECTION SYSTEM")
    print(f"  {'─'*40}")
    
    # Step 1: Find canonical base name from correctly named objects
    print(f"\n  Step 1: Finding canonical base name...")
    canonical_base_name = find_canonical_base_name(import_results)
    
    if not canonical_base_name:
        if fallback_base_name:
            canonical_base_name = fallback_base_name
            print(f"    ⚠️  Using fallback base name: '{canonical_base_name}'")
        else:
            print(f"    ⚠️  Could not determine canonical base name - skipping name correction")
            return {
                'rename_stats': {'renamed': 0, 'skipped': 0, 'no_match': 0, 'already_correct': 0},
                'validation': {'is_complete': False},
                'objects_matched': 0,
                'canonical_base_name': None
            }
    
    # Step 2: Match objects to FBX files using canonical base name
    print(f"\n  Step 2: Matching objects to FBX files...")
    object_to_fbx = match_objects_to_fbx(import_results, canonical_base_name)
    print(f"    ✅ Matched {len(object_to_fbx)} object(s) to FBX files")
    
    # Step 3: Collect all objects that need checking
    all_objects = []
    for fbx_file, imported_objects, _ in import_results:
        all_objects.extend(imported_objects)
    
    # Step 4: Rename objects
    print(f"\n  Step 3: Renaming objects...")
    rename_stats = rename_objects_to_match(all_objects, object_to_fbx)
    
    # Step 5: Update base_name in import_results to ensure correct grouping
    # This is critical - we need to update the base_name so grouping works correctly
    print(f"\n  Step 4: Updating base names in import results...")
    for i, (fbx_file, imported_objects, old_base_name) in enumerate(import_results):
        # Update the base_name in the tuple (we need to recreate the tuple)
        import_results[i] = (fbx_file, imported_objects, canonical_base_name)
        if old_base_name != canonical_base_name:
            print(f"    🔤 Updated base name for FBX '{fbx_file.name}': '{old_base_name}' → '{canonical_base_name}'")
    
    # Step 6: Validate completeness
    print(f"\n  Step 5: Validating LOD completeness...")
    import_groups = []
    for fbx_file, imported_objects, _ in import_results:
        import_groups.append({
            'fbx_file': fbx_file,
            'objects': imported_objects
        })
    validation = validate_lod_completeness(import_groups)
    
    return {
        'rename_stats': rename_stats,
        'validation': validation,
        'objects_matched': len(object_to_fbx),
        'canonical_base_name': canonical_base_name
    }

