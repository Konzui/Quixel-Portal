"""Main application flow orchestrator.

This module provides high-level workflow functions that coordinate between
communication, operations, and utilities. It provides a clean interface
for asset import and processing.
"""

import bpy
import re
import math
import mathutils
import time
from pathlib import Path

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
from .utils.floor_plane_manager import (
    create_floor_plane,
    cleanup_floor_plane,
)
from .ui.import_modal import show_import_toolbar


# Global performance tracking
_performance_data = {
    'import_start_time': None,
    'import_times': {},
    'lod_switch_times': [],
    'accept_start_time': None,
    'cancel_start_time': None,
    'total_operations': 0,
}


def _format_time_ms(seconds):
    """Format time in seconds to milliseconds with 6 decimal places.
    
    Args:
        seconds: Time in seconds
        
    Returns:
        str: Formatted time string (e.g., "123.456789 ms")
    """
    ms = seconds * 1000.0
    return f"{ms:.6f} ms"


def _print_performance_breakdown():
    """Print a detailed performance breakdown after accept/cancel."""
    global _performance_data
    
    # Performance breakdown disabled - prints removed to reduce console clutter
    # Data is still tracked internally if needed for future debugging
    
    # Reset performance data
    _performance_data = {
        'import_start_time': None,
        'import_times': {},
        'lod_switch_times': [],
        'accept_start_time': None,
        'cancel_start_time': None,
        'total_operations': 0,
    }


def frame_imported_objects(imported_objects, context=None, skip_if_temp_scene=True):
    """Select imported objects and frame the view to show them.

    Args:
        imported_objects: List of imported Blender objects to select and frame
        context: Optional Blender context (defaults to bpy.context)
        skip_if_temp_scene: If True, skip framing if we're in a temp preview scene
    """
    if not imported_objects:
        return

    # Always use fresh context to avoid stale references
    try:
        context = bpy.context
    except:
        return

    # Skip framing in temp scenes to avoid crashes with invalid depsgraph
    if skip_if_temp_scene:
        try:
            scene_name = context.scene.name if context.scene else None
            if scene_name and scene_name.startswith("__QuixelPreview__"):
                return
        except:
            pass

    # Filter to only valid, existing objects
    valid_objects = []
    for obj in imported_objects:
        try:
            if obj and obj.name in bpy.data.objects and obj.name in context.scene.objects:
                valid_objects.append(obj)
        except (ReferenceError, AttributeError, KeyError):
            continue

    if not valid_objects:
        return

    try:
        # Deselect all objects first
        bpy.ops.object.select_all(action='DESELECT')

        # Select all valid objects
        for obj in valid_objects:
            try:
                obj.select_set(True)
            except:
                continue

        # Set active object
        if valid_objects:
            try:
                context.view_layer.objects.active = valid_objects[0]
            except:
                pass

        # Frame the selected objects - use simple approach
        # Find any 3D viewport and frame the view
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                # Find the 3D view region
                region = None
                for r in area.regions:
                    if r.type == 'WINDOW':
                        region = r
                        break

                if region is None:
                    continue

                # Override context to this 3D view with region
                with context.temp_override(area=area, region=region):
                    try:
                        bpy.ops.view3d.view_selected()
                        return
                    except Exception as e:
                        continue

    except Exception as e:
        print(f"  ⚠️ Could not frame imported objects: {e}")
        import traceback
        traceback.print_exc()


def import_asset(asset_path, thumbnail_path=None, asset_name=None, glacier_setup=True, texture_resolution=None):
    """Main entry point for importing an asset.

    This function orchestrates the entire import process:
    1. Detects asset type (FBX or surface material)
    2. Imports FBX files or creates surface material
    3. Organizes objects by variation
    4. Creates materials and assigns them
    5. Creates asset hierarchy
    6. Cleans up temporary materials

    Args:
        asset_path: Path to the asset directory
        thumbnail_path: Optional path to thumbnail image
        asset_name: Optional asset name override
        glacier_setup: Whether to show toolbar with import settings (default: True)
        texture_resolution: Optional texture resolution from Bridge (e.g., "2K", "4K", "8K")

    Returns:
        dict: Blender operator result {'FINISHED'} or {'CANCELLED'}
    """
    
    # Start performance tracking
    global _performance_data
    _performance_data['import_start_time'] = time.time()
    _performance_data['import_times'] = {}
    _performance_data['lod_switch_times'] = []
    _performance_data['total_operations'] = 0

    # Cancel any active toolbar before starting new import
    from .ui.import_modal import get_active_toolbar
    active_toolbar = get_active_toolbar()
    if active_toolbar:
        try:
            active_toolbar._handle_cancel(None)
        except Exception as e:
            pass

    # Track materials that exist before import
    materials_before_import = set(bpy.data.materials.keys())
    
    asset_dir = Path(asset_path)
    context = bpy.context
    
    if not asset_dir.exists():
        print(f"❌ Asset directory not found: {asset_dir}")
        return {'CANCELLED'}
    
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
        if create_surface_material(asset_dir, context):
            # Force Blender to update the viewport/depsgraph before notifying
            bpy.context.view_layer.update()
            
            # Get asset name
            if not asset_name:
                asset_name = asset_dir.name
                json_name, _ = get_name_from_json(asset_dir)
                if json_name:
                    asset_name = json_name
            
            return {'FINISHED'}
        else:
            print(f"❌ Failed to create surface material")
            return {'CANCELLED'}
    
    elif asset_type == 'fbx':
        # Handle FBX import
        return _import_fbx_asset(asset_dir, materials_before_import, context, thumbnail_path, asset_name, glacier_setup, texture_resolution)
    
    else:
        print(f"⚠️ No FBX files or surface materials found in {asset_dir}")
        return {'CANCELLED'}


def _import_fbx_asset(asset_dir, materials_before_import, context, thumbnail_path, asset_name, glacier_setup=True, texture_resolution=None):
    """Import an FBX asset with all processing steps.

    Args:
        asset_dir: Path to asset directory
        materials_before_import: Set of material names before import
        context: Blender context
        thumbnail_path: Optional thumbnail path
        asset_name: Optional asset name
        glacier_setup: Whether to show toolbar with import settings (default: True)
        texture_resolution: Optional texture resolution from Bridge (e.g., "2K", "4K", "8K")

    Returns:
        dict: Blender operator result
    """
    # Clean up any leftover state from previous imports
    from .ui.import_modal import cleanup_toolbar
    cleanup_toolbar()
    
    # Always use fresh context to avoid stale references
    try:
        context = bpy.context
    except:
        print(f"❌ Could not get valid context")
        return {'CANCELLED'}
    
    # Validate context before proceeding
    try:
        if context.scene is None or context.scene.name not in bpy.data.scenes:
            print(f"❌ Context scene is invalid")
            return {'CANCELLED'}
    except (AttributeError, KeyError, ReferenceError):
        print(f"❌ Context validation failed")
        return {'CANCELLED'}
    
    # Store original scene reference BEFORE creating temp scene
    original_scene = context.scene
    original_collection = context.collection

    # Only create preview scene if Glacier setup is enabled
    temp_scene = None
    floor_obj = None
    floor_mat = None
    if glacier_setup:
        # Create temporary preview scene for import
        temp_scene = create_preview_scene(context)

        # Switch to temporary scene for import
        if not switch_to_scene(context, temp_scene):
            print(f"❌ Failed to switch to preview scene")
            return {'CANCELLED'}

        # Update context after scene switch
        context = bpy.context

        # Ensure temp scene is completely clean - remove any leftover objects
        # This prevents interference from previous imports
        try:
            objects_to_remove = [obj for obj in temp_scene.collection.objects]
            for obj in objects_to_remove:
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                except:
                    pass
        except Exception as e:
            pass

        # Create temporary floor plane with dev texture
        floor_obj, floor_mat = create_floor_plane(context)

    # Track all imported objects and materials for toolbar cleanup
    all_imported_objects_tracker = []
    all_imported_materials_tracker = []

    # Find all FBX files and detect 3D plant structure
    fbx_files, is_3d_plant, fbx_variation_map = find_fbx_files(asset_dir)

    if not fbx_files:
        print(f"❌ No FBX files found")
        # Clean up temp scene and floor plane before returning
        if temp_scene:
            cleanup_floor_plane(floor_obj, floor_mat)
            switch_to_scene(bpy.context, original_scene)
            cleanup_preview_scene(temp_scene)
        return {'CANCELLED'}
    
    # Detect LOD levels from FBX filenames BEFORE importing
    from .operations.fbx_importer import detect_lod_levels_from_fbx
    detected_lod_levels, max_lod = detect_lod_levels_from_fbx(fbx_files)

    # STEP 1: Import all FBX files
    step_start = time.time()
    import_results = []
    for fbx_file in fbx_files:
        imported_objects, base_name = import_fbx_file(fbx_file, context)
        if imported_objects:
            # For 3D plants, store variation index with import results
            variation_index = fbx_variation_map.get(fbx_file) if is_3d_plant else None
            import_results.append((fbx_file, imported_objects, base_name, variation_index))
    
    if not import_results:
        print(f"❌ Failed to import any FBX files")
        # Clean up temp scene and floor plane before returning
        if temp_scene:
            cleanup_floor_plane(floor_obj, floor_mat)
            switch_to_scene(bpy.context, original_scene)
            cleanup_preview_scene(temp_scene)
        return {'CANCELLED'}
    
    _performance_data['import_times']['Step 1: Import FBX Files'] = time.time() - step_start

    # NEW STEP: Correct object names before grouping
    # This ensures objects with incorrect names are renamed to match expected convention
    # and that all objects from the same asset get the same base name
    
    step_start = time.time()
    
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
    
    # Name correction summary prints removed to reduce console clutter
    # Results are still available in correction_results dict if needed
    
    _performance_data['import_times']['Step 1.5: Correct Object Names'] = time.time() - step_start
    
    # Set IOI LOD properties on all imported objects (for IOI addon compatibility)
    
    step_start = time.time()
    all_imported_objects_list = []
    for result in import_results:
        # Handle both old format (3 elements) and new format (4 elements)
        if len(result) == 3:
            _, imported_objects, _ = result
        else:
            _, imported_objects, _, _ = result
        all_imported_objects_list.extend(imported_objects)
    set_ioi_lod_properties_for_objects(all_imported_objects_list)
    _performance_data['import_times']['Step 1.6: Set IOI LOD Properties'] = time.time() - step_start

    # Track all imported objects for toolbar
    all_imported_objects_tracker.extend(all_imported_objects_list)

    # Group imported objects by base name (after correction)
    all_imported_objects = group_imported_objects(import_results)
    
    # STEP 2: Process each asset group
    step_start = time.time()
    for base_name, import_groups in all_imported_objects.items():
        # import_groups now contains variation_index for 3D plants
        # Get proper name from JSON
        json_name, json_file = get_name_from_json(asset_dir)
        if json_name:
            # Remove trailing letter suffix pattern
            attach_root_base_name = re.sub(r'_[a-z]+$', '', json_name, flags=re.IGNORECASE)
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
                
                # Get the scale from the old world root
                root_scale = old_root.scale
                if abs(root_scale.x - 1.0) > 0.001 or abs(root_scale.y - 1.0) > 0.001 or abs(root_scale.z - 1.0) > 0.001:
                    # The root has a non-identity scale, we need to preserve this
                    old_root_scale = root_scale.copy()
                
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
                    
                    # Unparent the child
                    child.parent = None
            
            # Remove old world root objects
            for old_root in old_world_roots:
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
        
        # Use detected scale or default to 0.01 if not found
        if detected_scale is None:
            detected_scale = 0.01

        # Use detected rotation or default to (90, 0, 0) if not found (common FBX import rotation)
        if detected_rotation is None:
            detected_rotation = mathutils.Euler((math.radians(90), 0, 0), 'XYZ')
        
        # CRITICAL: Set the detected rotation and scale on all objects BEFORE applying transforms
        # This ensures we apply the CORRECT transforms, not whatever random transforms the objects have
        for obj in all_objects_to_process:
            if obj.type == 'MESH' and obj.data:
                # Set the detected rotation
                obj.rotation_euler = detected_rotation.copy()
                # Set the detected scale (uniform scale)
                obj.scale = (detected_scale, detected_scale, detected_scale)
                # Print removed to reduce console clutter
        
        # STEP 3B: Apply transforms (bake them into mesh geometry)
        apply_transforms(all_objects_to_process)
        
        # STEP 4: Group by variation
        # For 3D plants, use folder-based variation organization
        # For regular assets, use object name-based variation detection
        
        step4_start = time.time()
        if is_3d_plant:
            from .operations.asset_processor import organize_3d_plant_objects_by_variation
            variations = organize_3d_plant_objects_by_variation(import_groups)
        else:
            variations = organize_objects_by_variation(all_objects_to_process)
        _performance_data['import_times']['Step 4: Detect Variations'] = time.time() - step4_start
        
        if not variations:
            print(f"  ⚠️ No mesh variations found in asset group")
            continue
        
        # STEP 5: Create materials
        
        step5_start = time.time()
        # Get variation folders for 3D plants
        variation_folders_for_materials = None
        if is_3d_plant:
            from .operations.fbx_importer import detect_3d_plant_structure
            _, variation_folders_for_materials = detect_3d_plant_structure(asset_dir)
        
        create_materials_for_all_variations(
            asset_dir,
            attach_root_base_name,
            variations,
            import_groups,
            context,
            texture_resolution,
            is_3d_plant=is_3d_plant,
            variation_folders=variation_folders_for_materials
        )
        _performance_data['import_times']['Step 5: Create Materials'] = time.time() - step5_start
        
        # STEP 6: Create attach roots
        
        step6_start = time.time()
        attach_roots = create_asset_hierarchy(variations, attach_root_base_name, context)
        _performance_data['import_times']['Step 6: Create Attach Roots'] = time.time() - step6_start

        # Track attach roots for cleanup
        if attach_roots:
            all_imported_objects_tracker.extend(attach_roots)
    
    _performance_data['import_times']['Step 2: Process Asset Groups'] = time.time() - step_start
    
    # STEP 7: Cleanup
    
    step7_start = time.time()
    cleanup_unused_materials(materials_before_import)
    _performance_data['import_times']['Step 7: Cleanup'] = time.time() - step7_start

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

    # Import complete - no notification needed (socket-based system)

    # Check if Glacier Setup is enabled
    if not glacier_setup:
        # Import directly without showing toolbar - assets are already in original scene
        # Select and frame the imported objects
        frame_imported_objects(all_imported_objects_tracker, context)

        return {'FINISHED'}

    # Import completion prints removed to reduce console clutter

    # Detect LOD levels from ALL imported objects right before showing toolbar
    # This ensures we capture all LOD levels after all processing is complete
    # We need to clean the tracker list first to remove any objects that were deleted during processing
    from .operations.asset_processor import extract_lod_from_object_name

    # Clean up all_imported_objects_tracker to remove deleted objects
    valid_objects = []
    for obj in all_imported_objects_tracker:
        try:
            # Check if object still exists in bpy.data.objects
            if obj and obj.name in bpy.data.objects:
                valid_objects.append(obj)
        except ReferenceError:
            # Object has been removed during processing, skip it
            pass

    # Update the tracker with only valid objects
    all_imported_objects_tracker.clear()
    all_imported_objects_tracker.extend(valid_objects)

    # Now detect LOD levels from valid objects
    lod_levels_set = set()
    for obj in all_imported_objects_tracker:
        try:
            # Validate object reference before accessing properties
            if obj is None:
                continue
            if obj.name not in bpy.data.objects:
                continue
            if bpy.data.objects[obj.name] != obj:
                continue
            if obj.type != 'MESH' or not obj.data:
                continue
            lod_level = extract_lod_from_object_name(obj.name)
            lod_levels_set.add(lod_level)
            # Print removed to reduce console clutter
        except (ReferenceError, AttributeError, KeyError) as e:
            # Object reference is invalid, skip it
            continue

    lod_levels_tracker = sorted(list(lod_levels_set))
    # LOD detection prints removed to reduce console clutter

    if lod_levels_tracker:
        # Print removed to reduce console clutter
        pass
    else:
        # Default to LOD0 if no LOD levels detected
        lod_levels_tracker = [0]
        # Print removed to reduce console clutter

    # Frame imported objects immediately after import
    frame_imported_objects(all_imported_objects_tracker, context, skip_if_temp_scene=False)

    # Validate context one more time before showing toolbar to prevent crashes
    try:
        # Force refresh context to ensure it's valid
        context = bpy.context
        if context.scene is None or context.scene.name not in bpy.data.scenes:
            print(f"❌ Context scene is invalid before showing toolbar")
            # Switch back to original scene and cleanup
            if temp_scene:
                cleanup_floor_plane(floor_obj, floor_mat)
                switch_to_scene(bpy.context, original_scene)
                cleanup_preview_scene(temp_scene)
            return {'CANCELLED'}
    except Exception as e:
        print(f"❌ Context validation failed before showing toolbar: {e}")
        # Switch back to original scene and cleanup
        try:
            if temp_scene:
                cleanup_floor_plane(floor_obj, floor_mat)
                switch_to_scene(bpy.context, original_scene)
                cleanup_preview_scene(temp_scene)
        except:
            pass
        return {'CANCELLED'}
    
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
        
        # Set max LOD dropdown to detected maximum
        if max_lod is not None:
            toolbar.set_max_lod(max_lod)

        # Position LODs for preview with text labels
        toolbar.position_lods_for_preview()

        # Define accept callback - transfer assets and return to original scene
        def on_accept():
            """Handle accept - transfer assets to original scene and cleanup."""
            from .ui.import_modal import cleanup_toolbar

            # Start accept timing
            _performance_data['accept_start_time'] = time.time()

            # Print removed to reduce console clutter

            try:
                # Clean up temporary floor plane before transferring assets
                cleanup_floor_plane(floor_obj, floor_mat)

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

                # Frame the view to show transferred objects in original scene
                frame_imported_objects(transferred_objects, bpy.context, skip_if_temp_scene=False)

                # Print removed to reduce console clutter

            except Exception as e:
                print(f"\n⚠️ Error during accept cleanup: {e}")
                import traceback
                traceback.print_exc()

            finally:
                # ALWAYS clean up toolbar UI, even if cleanup failed
                # This prevents the toolbar from getting stuck on screen
                cleanup_toolbar()
                
                # Print performance breakdown
                _print_performance_breakdown()

        # Define cancel callback - discard everything and return to original scene
        def on_cancel():
            """Handle cancel - discard all assets and return to original scene."""
            from .ui.import_modal import cleanup_toolbar

            # Start cancel timing
            _performance_data['cancel_start_time'] = time.time()

            try:
                # Clean up temporary floor plane before cleanup
                cleanup_floor_plane(floor_obj, floor_mat)

                # Switch back to original scene first
                switch_to_scene(bpy.context, original_scene)

                # Delete temporary preview scene (auto-cleanup of objects)
                cleanup_preview_scene(temp_scene)

                # Clean up materials that were created during import
                cleanup_imported_materials(
                    all_imported_materials_tracker,
                    materials_before_import
                )

            except Exception as e:
                print(f"\n⚠️ Error during cancel cleanup: {e}")
                import traceback
                traceback.print_exc()

            finally:
                # ALWAYS clean up toolbar UI, even if cleanup failed
                # This prevents the toolbar from getting stuck on screen
                cleanup_toolbar()
                
                # Print performance breakdown
                _print_performance_breakdown()

        # Set the callbacks on the toolbar
        toolbar.on_accept = on_accept
        toolbar.on_cancel = on_cancel

    return {'FINISHED'}

