"""Operations module for asset import and processing.

This package contains modules for importing FBX files, creating materials,
and processing assets.
"""

from .fbx_importer import (
    find_fbx_files,
    import_fbx_file,
    group_imported_objects,
    apply_transforms,
)
from .material_creator import (
    create_material_from_textures,
    find_textures_for_variation,
    compare_texture_sets,
    get_texture_hash,
    create_surface_material,
    create_materials_for_all_variations,
)
from .asset_processor import (
    process_asset_directory,
    detect_asset_type,
    organize_objects_by_variation,
    create_asset_hierarchy,
    cleanup_unused_materials,
    calculate_variation_bbox,
    set_ioi_lod_properties,
    set_ioi_lod_properties_for_objects,
)
from .name_corrector import (
    extract_lod_from_fbx,
    build_expected_naming,
    find_canonical_base_name,
    match_objects_to_fbx,
    rename_objects_to_match,
    validate_lod_completeness,
    correct_object_names,
)

__all__ = [
    'find_fbx_files',
    'import_fbx_file',
    'group_imported_objects',
    'apply_transforms',
    'create_material_from_textures',
    'find_textures_for_variation',
    'compare_texture_sets',
    'get_texture_hash',
    'create_surface_material',
    'create_materials_for_all_variations',
    'process_asset_directory',
    'detect_asset_type',
    'organize_objects_by_variation',
    'create_asset_hierarchy',
    'cleanup_unused_materials',
    'calculate_variation_bbox',
    'set_ioi_lod_properties',
    'set_ioi_lod_properties_for_objects',
    'extract_lod_from_fbx',
    'build_expected_naming',
    'find_canonical_base_name',
    'match_objects_to_fbx',
    'rename_objects_to_match',
    'validate_lod_completeness',
    'correct_object_names',
]

