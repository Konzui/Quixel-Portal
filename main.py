"""Main application flow orchestrator.

This module provides high-level workflow functions that coordinate between
communication, operations, and utilities. It abstracts away the details of
Electron communication and provides a clean interface for the UI layer.
"""

import bpy
import re
import math
import mathutils
from pathlib import Path

from .operations.portal_launcher import open_quixel_portal
from .operations.fbx_importer import (
    find_fbx_files,
    import_fbx_file,
    group_imported_objects,
    apply_transforms,
)
from .operations.material_creator import (
    create_surface_material,
    create_materials_for_all_variations,
)
from .operations.asset_processor import (
    detect_asset_type,
    organize_objects_by_variation,
    create_asset_hierarchy,
    cleanup_unused_materials,
    set_ioi_lod_properties_for_objects,
)
from .communication.electron_bridge import write_import_complete
from .utils.naming import get_name_from_json, get_base_name
from .utils.texture_loader import find_texture_files
from .utils.validation import is_folder_empty, check_folder_contents
from .utils.scene_manager import (
    create_preview_scene,
    switch_to_scene,
    transfer_assets_to_original_scene,
    cleanup_preview_scene,
    cleanup_imported_materials,
    setup_preview_camera,
)
from .ui.import_modal import show_import_toolbar


def import_asset(asset_path, thumbnail_path=None, asset_name=None, glacier_setup=True):
    """Main entry point for importing an asset.

    This function orchestrates the entire import process:
    1. Detects asset type (FBX or surface material)
    2. Imports FBX files or creates surface material
    3. Organizes objects by variation
    4. Creates materials and assigns them
    5. Creates asset hierarchy
    6. Cleans up temporary materials
    7. Notifies Electron of completion

    Args:
        asset_path: Path to the asset directory
        thumbnail_path: Optional path to thumbnail image
        asset_name: Optional asset name override
        glacier_setup: Whether to show toolbar with import settings (default: True)

    Returns:
        dict: Blender operator result {'FINISHED'} or {'CANCELLED'}
    """
    print(f"\n{'='*80}")
    print(f"🚀 STARTING QUIXEL ASSET IMPORT")
    print(f"{'='*80}")

    # Cancel any active toolbar before starting new import
    from .ui.import_modal import get_active_toolbar
    active_toolbar = get_active_toolbar()
    if active_toolbar:
        print(f"⚠️  Canceling active toolbar from previous import")
        try:
            active_toolbar._handle_cancel(None)
        except Exception as e:
            print(f"⚠️  Failed to cancel active toolbar: {e}")

    # Track materials that exist before import
    materials_before_import = set(bpy.data.materials.keys())
    
    asset_dir = Path(asset_path)
    context = bpy.context
    
    if not asset_dir.exists():
        print(f"❌ Asset directory not found: {asset_dir}")
        return {'CANCELLED'}
    
    print(f"📁 Asset directory: {asset_dir}")
    
    # Check if folder is empty before attempting import
    is_empty, empty_error = is_folder_empty(asset_dir)
    if is_empty:
        print(f"❌ Asset directory is empty: {empty_error or 'Folder contains no files'}")
        print(f"   This may indicate a failed download or extraction.")
        print(f"   Please try downloading the asset again.")
        return {'CANCELLED'}
    
    # Get detailed folder contents for better error messages
    folder_status = check_folder_contents(asset_dir)
    if folder_status.get('error') and not folder_status.get('has_fbx') and not folder_status.get('has_surface_material'):
        print(f"⚠️ Asset directory validation:")
        print(f"   - FBX files found: {folder_status.get('fbx_count', 0)}")
        print(f"   - Surface material: {folder_status.get('has_surface_material', False)}")
        print(f"   - Error: {folder_status.get('error')}")
        print(f"   This may indicate an incomplete download. Please try downloading again.")
    
    # Detect asset type
    asset_type = detect_asset_type(asset_dir)
    
    if asset_type == 'surface':
        # Handle surface material
        print(f"✅ Detected surface material (JSON + textures)")
        if create_surface_material(asset_dir, context):
            # Force Blender to update the viewport/depsgraph before notifying
            bpy.context.view_layer.update()
            
            # Get asset name
            if not asset_name:
                asset_name = asset_dir.name
                json_name, _ = get_name_from_json(asset_dir)
                if json_name:
                    asset_name = json_name
            
            # Send notification to Electron
            write_import_complete(asset_dir, asset_name, thumbnail_path)
            
            return {'FINISHED'}
        else:
            print(f"❌ Failed to create surface material")
            return {'CANCELLED'}
    
    elif asset_type == 'fbx':
        # Handle FBX import
        return _import_fbx_asset(asset_dir, materials_before_import, context, thumbnail_path, asset_name, glacier_setup)
    
    else:
        print(f"⚠️ No FBX files or surface materials found in {asset_dir}")
        return {'CANCELLED'}


def _import_fbx_asset(asset_dir, materials_before_import, context, thumbnail_path, asset_name, glacier_setup=True):
    """Import an FBX asset with all processing steps.

    Args:
        asset_dir: Path to asset directory
        materials_before_import: Set of material names before import
        context: Blender context
        thumbnail_path: Optional thumbnail path
        asset_name: Optional asset name
        glacier_setup: Whether to show toolbar with import settings (default: True)

    Returns:
        dict: Blender operator result
    """
    # Store original scene reference BEFORE creating temp scene
    original_scene = context.scene
    original_collection = context.collection

    print(f"\n{'='*80}")
    print(f"🎬 SCENE SETUP: CREATING TEMPORARY PREVIEW SCENE")
    print(f"{'='*80}")
    print(f"  📌 Original scene: {original_scene.name}")

    # Create temporary preview scene for import
    temp_scene = create_preview_scene(context)

    # Switch to temporary scene for import
    if not switch_to_scene(context, temp_scene):
        print(f"❌ Failed to switch to preview scene")
        return {'CANCELLED'}

    # Update context after scene switch
    context = bpy.context

    print(f"  ✅ Now working in temporary preview scene: {temp_scene.name}")

    # Track all imported objects and materials for toolbar cleanup
    all_imported_objects_tracker = []
    all_imported_materials_tracker = []

    # Find all FBX files
    fbx_files = find_fbx_files(asset_dir)

    if not fbx_files:
        print(f"⚠️ No FBX files found")
        # Clean up temp scene before returning
        switch_to_scene(bpy.context, original_scene)
        cleanup_preview_scene(temp_scene)
        return {'CANCELLED'}
    
    print(f"📦 Found {len(fbx_files)} FBX file(s) to import:")
    for fbx_file in fbx_files:
        print(f"   - {fbx_file.name}")
    
    # STEP 1: Import all FBX files
    print(f"\n{'='*80}")
    print(f"📥 STEP 1: IMPORTING FBX FILES")
    print(f"{'='*80}")
    
    import_results = []
    for fbx_file in fbx_files:
        print(f"\n🔄 Importing: {fbx_file.name}")
        imported_objects, base_name = import_fbx_file(fbx_file, context)
        if imported_objects:
            import_results.append((fbx_file, imported_objects, base_name))
    
    if not import_results:
        print(f"❌ Failed to import any FBX files")
        # Clean up temp scene before returning
        switch_to_scene(bpy.context, original_scene)
        cleanup_preview_scene(temp_scene)
        return {'CANCELLED'}
    
    # NEW STEP: Correct object names before grouping
    # This ensures objects with incorrect names are renamed to match expected convention
    # and that all objects from the same asset get the same base name
    print(f"\n{'='*80}")
    print(f"🔤 STEP 1.5: CORRECTING OBJECT NAMES")
    print(f"{'='*80}")
    
    # Try to get fallback base name from FBX filenames (in case no objects are correctly named)
    fallback_base_name = None
    if import_results:
        first_fbx = import_results[0][0]
        fbx_stem = Path(first_fbx).stem
        # Remove LOD suffix to get base name
        fallback_base_name = re.sub(r'_?LOD\d+', '', fbx_stem, flags=re.IGNORECASE).strip('_')
        # Remove variation suffix if present
        fallback_base_name = re.sub(r'_\d{2}_[a-z]$|_[a-z]$', '', fallback_base_name, flags=re.IGNORECASE)
    
    from .operations.name_corrector import correct_object_names
    correction_results = correct_object_names(import_results, fallback_base_name=fallback_base_name)
    
    if correction_results['canonical_base_name']:
        if correction_results['rename_stats']['renamed'] > 0:
            print(f"\n✅ Name correction complete: {correction_results['rename_stats']['renamed']} object(s) renamed")
            print(f"   📌 Canonical base name: '{correction_results['canonical_base_name']}'")
        else:
            print(f"\n✅ Name correction: All objects already have correct names")
            print(f"   📌 Canonical base name: '{correction_results['canonical_base_name']}'")
    else:
        print(f"\n⚠️  Could not determine base name for correction - objects may be grouped incorrectly")
    
    # Set IOI LOD properties on all imported objects (for IOI addon compatibility)
    print(f"\n{'='*80}")
    print(f"🏷️  STEP 1.6: SETTING IOI LOD PROPERTIES")
    print(f"{'='*80}")
    all_imported_objects_list = []
    for fbx_file, imported_objects, _ in import_results:
        all_imported_objects_list.extend(imported_objects)
    set_ioi_lod_properties_for_objects(all_imported_objects_list)

    # Track all imported objects for toolbar
    all_imported_objects_tracker.extend(all_imported_objects_list)
    print(f"\n  📊 DEBUG: Tracked {len(all_imported_objects_list)} objects initially")
    for obj in all_imported_objects_list[:10]:  # Show first 10
        if obj.type == 'MESH':
            print(f"    - {obj.name} (type: {obj.type})")

    # Group imported objects by base name (after correction)
    all_imported_objects = group_imported_objects(import_results)
    
    print(f"\n✅ Import complete: {len(import_results)} FBX file(s) imported into {len(all_imported_objects)} asset group(s)")
    
    # STEP 2: Process each asset group
    print(f"\n{'='*80}")
    print(f"⚙️  STEP 2: PROCESSING ASSET GROUPS")
    print(f"{'='*80}")
    
    for base_name, import_groups in all_imported_objects.items():
        print(f"\n{'─'*80}")
        print(f"📦 Processing asset group: '{base_name}'")
        print(f"{'─'*80}")
        
        # Get proper name from JSON
        json_name, json_file = get_name_from_json(asset_dir)
        if json_name:
            # Remove trailing letter suffix pattern
            attach_root_base_name = re.sub(r'_[a-z]+$', '', json_name, flags=re.IGNORECASE)
            print(f"  📋 Using JSON name for attach roots: {json_name}")
            if attach_root_base_name != json_name:
                print(f"  ✂️  Removed existing suffix: '{json_name}' → '{attach_root_base_name}'")
        else:
            attach_root_base_name = f"quixel_{base_name}"
        
        # Collect all objects and process old world roots
        # CRITICAL: Detect rotation and scale from old world roots BEFORE removing them
        all_objects_to_process = []
        detected_scale = None
        detected_rotation = None
        
        for import_group in import_groups:
            imported_objects = import_group['objects']
            fbx_file = import_group['fbx_file']
            
            # Identify and remove old world root objects (empty objects that are parents of other imported objects)
            old_world_roots = []
            for obj in imported_objects:
                # Check if this object is a parent of other imported objects
                is_parent = any(child in imported_objects for child in obj.children)
                # Check if it's an empty object (no mesh data)
                is_empty = (obj.type == 'EMPTY' or 
                           (hasattr(obj, 'data') and obj.data is None) or
                           (obj.type == 'MESH' and obj.data is not None and len(obj.data.vertices) == 0))
                # For safety, also check if it has a name that suggests it's a root
                if is_parent and (is_empty or obj.name == fbx_file.stem):
                    old_world_roots.append(obj)
            
            # Detect rotation AND scale from old world roots before removing them
            # The old world roots typically have the correct rotation (e.g., X rotation of 90) and scale
            old_root_scale = None
            for old_root in old_world_roots:
                # Get the rotation from the old world root
                rotation_euler = old_root.rotation_euler
                if detected_rotation is None:
                    detected_rotation = rotation_euler.copy()
                    print(f"  🔄 Detected rotation from old world root: X={math.degrees(rotation_euler.x):.1f}°, Y={math.degrees(rotation_euler.y):.1f}°, Z={math.degrees(rotation_euler.z):.1f}°")
                
                # Get the scale from the old world root
                root_scale = old_root.scale
                if abs(root_scale.x - 1.0) > 0.001 or abs(root_scale.y - 1.0) > 0.001 or abs(root_scale.z - 1.0) > 0.001:
                    # The root has a non-identity scale, we need to preserve this
                    old_root_scale = root_scale.copy()
                    print(f"  📏 Detected scale from old world root: {root_scale}")
                
                break  # Use the first old world root's rotation and scale
            
            # If no rotation detected from old world roots, check the imported objects
            # Sometimes the rotation is on the mesh objects themselves
            if detected_rotation is None:
                for obj in imported_objects:
                    if obj.type == 'MESH' and obj.data:
                        # Check if the object has a significant rotation (like 90 degrees on X)
                        rotation_euler = obj.rotation_euler
                        # Check if X rotation is close to 90 degrees (common FBX import)
                        x_rot_deg = math.degrees(rotation_euler.x)
                        if abs(x_rot_deg - 90) < 5 or abs(x_rot_deg - (-90)) < 5:
                            detected_rotation = rotation_euler.copy()
                            print(f"  🔄 Detected rotation from mesh object: X={x_rot_deg:.1f}°, Y={math.degrees(rotation_euler.y):.1f}°, Z={math.degrees(rotation_euler.z):.1f}°")
                            break
            
            # Collect all children of old world roots and apply scale if needed
            children_to_reparent = []
            for old_root in old_world_roots:
                for child in old_root.children:
                    children_to_reparent.append(child)
                    
                    # CRITICAL: If old root has a scale, apply it to children BEFORE unparenting
                    # This preserves the correct size
                    if old_root_scale is not None:
                        # Multiply child's scale by parent's scale
                        child.scale.x *= old_root_scale.x
                        child.scale.y *= old_root_scale.y
                        child.scale.z *= old_root_scale.z
                        print(f"    📏 Applied root scale to child: {child.name} -> scale={child.scale}")
                    
                    # Unparent the child
                    child.parent = None
            
            # Remove old world root objects
            print(f"    🗑️  DEBUG: Removing {len(old_world_roots)} world root object(s)")
            for old_root in old_world_roots:
                print(f"      - Deleting: {old_root.name}")
                bpy.data.objects.remove(old_root, do_unlink=True)
                imported_objects.remove(old_root)
            
            # Add the children to our list of objects to process
            imported_objects.extend(children_to_reparent)
            
            # Detect the scale from the imported objects (typically 0.01 or 0.1)
            # Check the scale of mesh objects (they should have the correct scale)
            for obj in imported_objects:
                if obj.type == 'MESH' and obj.data:
                    # Get the scale from the object
                    scale = obj.scale
                    # Check if it's a small scale like 0.01 or 0.1
                    if scale.x < 1.0 and scale.x > 0:
                        # Use the X scale as reference (assuming uniform or similar scales)
                        if detected_scale is None or abs(scale.x - 0.01) < abs(detected_scale - 0.01):
                            detected_scale = scale.x
                    break  # Use the first mesh object's scale
            
            all_objects_to_process.extend(imported_objects)
            
            if old_world_roots:
                print(f"  ✅ Removed {len(old_world_roots)} old world root object(s) from: {fbx_file.name}")
        
        # Use detected scale or default to 0.01 if not found
        if detected_scale is None:
            detected_scale = 0.01
            print(f"  ⚠️ No scale detected, using default: {detected_scale}")
        else:
            print(f"  📏 Detected scale: {detected_scale}")
        
        # Use detected rotation or default to (90, 0, 0) if not found (common FBX import rotation)
        if detected_rotation is None:
            detected_rotation = mathutils.Euler((math.radians(90), 0, 0), 'XYZ')
            print(f"  ⚠️ No rotation detected, using default: X=90°")
        else:
            print(f"  🔄 Using rotation: X={math.degrees(detected_rotation.x):.1f}°, Y={math.degrees(detected_rotation.y):.1f}°, Z={math.degrees(detected_rotation.z):.1f}°")
        
        # CRITICAL: Set the detected rotation and scale on all objects BEFORE applying transforms
        # This ensures we apply the CORRECT transforms, not whatever random transforms the objects have
        print(f"\n  {'─'*40}")
        print(f"  🔧 STEP 3A: SETTING TRANSFORMS ON OBJECTS")
        print(f"  {'─'*40}")
        for obj in all_objects_to_process:
            if obj.type == 'MESH' and obj.data:
                # Set the detected rotation
                obj.rotation_euler = detected_rotation.copy()
                # Set the detected scale (uniform scale)
                obj.scale = (detected_scale, detected_scale, detected_scale)
                print(f"    ✅ Set transforms on '{obj.name}': rotation={detected_rotation}, scale={detected_scale}")
        
        # STEP 3B: Apply transforms (bake them into mesh geometry)
        print(f"\n  {'─'*40}")
        print(f"  🔧 STEP 3B: APPLYING TRANSFORMS (BAKING INTO MESH)")
        print(f"  {'─'*40}")
        apply_transforms(all_objects_to_process)
        
        # STEP 4: Group by variation
        print(f"\n  {'─'*40}")
        print(f"  🔍 STEP 4: DETECTING VARIATIONS")
        print(f"  {'─'*40}")
        variations = organize_objects_by_variation(all_objects_to_process)
        
        if not variations:
            print(f"  ⚠️ No mesh variations found in asset group")
            continue
        
        # STEP 5: Create materials
        print(f"\n  {'─'*40}")
        print(f"  🎨 STEP 5: CREATING MATERIALS (OPTIMIZED)")
        print(f"  {'─'*40}")
        create_materials_for_all_variations(
            asset_dir,
            attach_root_base_name,
            variations,
            import_groups,
            context
        )
        
        # STEP 6: Create attach roots
        print(f"\n  {'─'*40}")
        print(f"  📦 STEP 6: CREATING ATTACH ROOTS")
        print(f"  {'─'*40}")
        attach_roots = create_asset_hierarchy(variations, attach_root_base_name, context)

        # Track attach roots for cleanup
        if attach_roots:
            all_imported_objects_tracker.extend(attach_roots)
    
    # STEP 7: Cleanup
    print(f"\n  {'─'*40}")
    print(f"  🧹 STEP 7: CLEANING UP")
    print(f"  {'─'*40}")
    cleanup_unused_materials(materials_before_import)

    # Force Blender to update
    bpy.context.view_layer.update()

    # Collect all materials created during import
    materials_after_import = set(bpy.data.materials.keys())
    new_materials = materials_after_import - materials_before_import
    all_imported_materials_tracker = [bpy.data.materials[name] for name in new_materials if name in bpy.data.materials]

    # Get asset name (needed for completion notification)
    if not asset_name:
        asset_name = asset_dir.name
        json_name, _ = get_name_from_json(asset_dir)
        if json_name:
            asset_name = json_name

    # Notify Electron immediately after import completes
    # This ensures the import button won't get stuck if user cancels
    write_import_complete(asset_dir, asset_name, thumbnail_path)

    # Check if Glacier Setup is enabled
    if not glacier_setup:
        # Import directly without showing toolbar - just transfer to original scene
        print(f"\n{'='*80}")
        print(f"✅ IMPORT COMPLETE - GLACIER SETUP DISABLED")
        print(f"{'='*80}")
        print(f"  📦 Imported {len(all_imported_objects_tracker)} object(s)")
        print(f"  🎨 Created {len(all_imported_materials_tracker)} material(s)")
        print(f"  📡 Electron notified of successful import")
        print(f"  ⚡ Asset imported directly without toolbar (Glacier Setup disabled)")

        # Transfer assets to original scene automatically
        transferred_objects = transfer_assets_to_original_scene(
            temp_scene,
            original_scene,
            all_imported_objects_tracker,
            all_imported_materials_tracker
        )

        # Switch back to original scene
        switch_to_scene(bpy.context, original_scene)

        # Delete temporary preview scene
        cleanup_preview_scene(temp_scene)

        print(f"  🎬 Assets transferred to original scene: {original_scene.name}")

        return {'FINISHED'}

    print(f"\n{'='*80}")
    print(f"✅ IMPORT COMPLETE - SHOWING CONFIRMATION TOOLBAR")
    print(f"{'='*80}")
    print(f"  📦 Imported {len(all_imported_objects_tracker)} object(s)")
    print(f"  🎨 Created {len(all_imported_materials_tracker)} material(s)")
    print(f"  📡 Electron notified of successful import")
    print(f"  ⏳ Waiting for user confirmation in preview scene...")

    # Detect LOD levels from ALL imported objects right before showing toolbar
    # This ensures we capture all LOD levels after all processing is complete
    # We need to clean the tracker list first to remove any objects that were deleted during processing
    from .operations.asset_processor import extract_lod_from_object_name

    print(f"\n{'='*80}")
    print(f"🔍 DEBUG: LOD DETECTION PROCESS")
    print(f"{'='*80}")
    print(f"  📊 Objects in tracker before cleanup: {len(all_imported_objects_tracker)}")

    # Also show what's in the entire scene
    all_scene_meshes = [obj for obj in bpy.data.objects if obj.type == 'MESH']
    print(f"  🌍 Total mesh objects in entire scene: {len(all_scene_meshes)}")
    print(f"  🔍 Sample mesh names in scene (first 15):")
    for obj in all_scene_meshes[:15]:
        print(f"    - {obj.name}")

    # Clean up all_imported_objects_tracker to remove deleted objects
    valid_objects = []
    deleted_count = 0
    for obj in all_imported_objects_tracker:
        try:
            # Check if object still exists in bpy.data.objects
            if obj and obj.name in bpy.data.objects:
                valid_objects.append(obj)
            else:
                deleted_count += 1
        except ReferenceError:
            # Object has been removed during processing, skip it
            deleted_count += 1
            pass

    print(f"  🗑️  Objects deleted during processing: {deleted_count}")
    print(f"  ✅ Valid objects remaining: {len(valid_objects)}")

    # Update the tracker with only valid objects
    all_imported_objects_tracker.clear()
    all_imported_objects_tracker.extend(valid_objects)

    # Now detect LOD levels from valid objects
    print(f"\n  🔍 Scanning valid objects for LOD levels:")
    lod_levels_set = set()
    for obj in all_imported_objects_tracker:
        if obj.type == 'MESH' and obj.data:
            lod_level = extract_lod_from_object_name(obj.name)
            lod_levels_set.add(lod_level)
            print(f"    - {obj.name} → LOD{lod_level}")

    lod_levels_tracker = sorted(list(lod_levels_set))
    print(f"\n  📋 Complete LOD set collected: {lod_levels_set}")
    print(f"  📋 Sorted LOD list: {lod_levels_tracker}")

    if lod_levels_tracker:
        print(f"  📊 Detected LOD levels for toolbar: {lod_levels_tracker}")
    else:
        # Default to LOD0 if no LOD levels detected
        lod_levels_tracker = [0]
        print(f"  ⚠️  No LOD levels detected, defaulting to: {lod_levels_tracker}")

    # Show import confirmation toolbar with scene references
    from .ui.import_modal import show_import_toolbar, get_active_toolbar

    result = show_import_toolbar(
        context,
        all_imported_objects_tracker,
        all_imported_materials_tracker,
        materials_before_import,
        original_scene=original_scene,
        temp_scene=temp_scene
    )

    # Set the accept callback and LOD levels on the toolbar
    toolbar = get_active_toolbar()
    if toolbar:
        # Set available LOD levels
        toolbar.set_lod_levels(lod_levels_tracker)

        # Position LODs for preview with text labels
        toolbar.position_lods_for_preview()

        # Define accept callback - transfer assets and return to original scene
        def on_accept():
            """Handle accept - transfer assets to original scene and cleanup."""
            from .ui.import_modal import cleanup_toolbar

            print(f"\n{'='*80}")
            print(f"✅ USER ACCEPTED IMPORT - TRANSFERRING ASSETS")
            print(f"{'='*80}")

            # Transfer all assets from temp scene to original scene
            transferred_objects = transfer_assets_to_original_scene(
                temp_scene,
                original_scene,
                all_imported_objects_tracker,
                all_imported_materials_tracker
            )

            # Switch back to original scene
            switch_to_scene(bpy.context, original_scene)

            # Delete temporary preview scene
            cleanup_preview_scene(temp_scene)

            # Clean up toolbar UI
            cleanup_toolbar()

            print(f"\n{'='*80}")
            print(f"✅ IMPORT COMPLETE - ASSETS TRANSFERRED TO ORIGINAL SCENE")
            print(f"{'='*80}")
            print(f"  📦 Transferred {len(transferred_objects)} object(s)")
            print(f"  🎨 Created {len(all_imported_materials_tracker)} material(s)")
            print(f"  🎬 Returned to scene: {original_scene.name}")

        # Define cancel callback - discard everything and return to original scene
        def on_cancel():
            """Handle cancel - discard all assets and return to original scene."""
            from .ui.import_modal import cleanup_toolbar

            print(f"\n{'='*80}")
            print(f"❌ USER CANCELLED IMPORT - DISCARDING ASSETS")
            print(f"{'='*80}")

            # Switch back to original scene first
            switch_to_scene(bpy.context, original_scene)

            # Delete temporary preview scene (auto-cleanup of objects)
            cleanup_preview_scene(temp_scene)

            # Clean up materials that were created during import
            cleanup_imported_materials(
                all_imported_materials_tracker,
                materials_before_import
            )

            # Clean up toolbar UI
            cleanup_toolbar()

            print(f"\n{'='*80}")
            print(f"✅ IMPORT CANCELLED - ORIGINAL SCENE UNCHANGED")
            print(f"{'='*80}")
            print(f"  🎬 Returned to scene: {original_scene.name}")
            print(f"  🧹 All imported assets discarded")

        # Set the callbacks on the toolbar
        toolbar.on_accept = on_accept
        toolbar.on_cancel = on_cancel

    return {'FINISHED'}

