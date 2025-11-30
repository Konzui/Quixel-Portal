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
    
    print(f"⏱️  PERFORMANCE BREAKDOWN")
    
    # Import timing
    if _performance_data['import_start_time']:
        total_import_time = time.time() - _performance_data['import_start_time']
        print(f"\n📥 ASSET IMPORT:")
        print(f"   Total Import Time: {_format_time_ms(total_import_time)}")
        
        if _performance_data['import_times']:
            print(f"   Breakdown:")
            for step_name, step_time in _performance_data['import_times'].items():
                percentage = (step_time / total_import_time * 100) if total_import_time > 0 else 0
                print(f"      - {step_name}: {_format_time_ms(step_time)} ({percentage:.2f}%)")
    
    # LOD switching
    if _performance_data['lod_switch_times']:
        total_lod_time = sum(_performance_data['lod_switch_times'])
        avg_lod_time = total_lod_time / len(_performance_data['lod_switch_times'])
        min_lod_time = min(_performance_data['lod_switch_times'])
        max_lod_time = max(_performance_data['lod_switch_times'])
        
        print(f"\n🎚️  LOD SWITCHING:")
        print(f"   Total Switches: {len(_performance_data['lod_switch_times'])}")
        print(f"   Total Time: {_format_time_ms(total_lod_time)}")
        print(f"   Average Time: {_format_time_ms(avg_lod_time)}")
        print(f"   Min Time: {_format_time_ms(min_lod_time)}")
        print(f"   Max Time: {_format_time_ms(max_lod_time)}")
    
    # Accept/Cancel timing
    if _performance_data['accept_start_time']:
        accept_time = time.time() - _performance_data['accept_start_time']
        print(f"\n✅ ACCEPT OPERATION:")
        print(f"   Time: {_format_time_ms(accept_time)}")
    
    if _performance_data['cancel_start_time']:
        cancel_time = time.time() - _performance_data['cancel_start_time']
        print(f"\n❌ CANCEL OPERATION:")
        print(f"   Time: {_format_time_ms(cancel_time)}")
    
    # Total operations
    print(f"\n📊 SUMMARY:")
    print(f"   Total Operations Tracked: {_performance_data['total_operations']}")
    
    
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
        print(f"  ⚠️ Could not get valid context for framing")
        return
    
    # Skip framing in temp scenes to avoid crashes with invalid depsgraph
    if skip_if_temp_scene:
        try:
            scene_name = context.scene.name if context.scene else None
            if scene_name and scene_name.startswith("__QuixelPreview__"):
                print(f"  ⚠️ Skipping frame in temp preview scene to avoid crashes")
                return
        except:
            pass
    
    # Validate context is valid and scene exists
    try:
        if context.scene is None or context.scene.name not in bpy.data.scenes:
            print(f"  ⚠️ Context scene is invalid, skipping frame")
            return
        if context.window_manager is None:
            print(f"  ⚠️ Context window_manager is invalid, skipping frame")
            return
    except (AttributeError, KeyError, ReferenceError):
        print(f"  ⚠️ Context validation failed, skipping frame")
        return
    
    # Filter to only valid, existing objects with proper validation
    valid_objects = []
    for obj in imported_objects:
        try:
            # Check if object reference is valid and object exists in data
            if obj is None:
                continue
            # Re-fetch from bpy.data.objects to ensure reference is valid
            if obj.name in bpy.data.objects:
                # Verify the object is the same one (not a new object with same name)
                fetched_obj = bpy.data.objects[obj.name]
                if fetched_obj == obj:
                    # Also verify object is in the current scene
                    if obj.name in context.scene.objects:
                        valid_objects.append(obj)
        except (ReferenceError, AttributeError, KeyError):
            # Object reference is invalid, skip it
            continue
    
    if not valid_objects:
        return
    
    try:
        # Deselect all objects first
        bpy.ops.object.select_all(action='DESELECT')
        
        # Select all imported objects with additional safety checks
        selected_count = 0
        for obj in valid_objects:
            try:
                # Double-check object is still valid before selecting
                if obj and obj.name in bpy.data.objects and bpy.data.objects[obj.name] == obj:
                    if obj.name in context.scene.objects:
                        obj.select_set(True)
                        selected_count += 1
            except (ReferenceError, AttributeError, KeyError):
                # Object became invalid, skip it
                continue
        
        if selected_count == 0:
            return
        
        # Set active object (use first valid object)
        if valid_objects:
            try:
                first_obj = valid_objects[0]
                if first_obj and first_obj.name in bpy.data.objects and bpy.data.objects[first_obj.name] == first_obj:
                    if first_obj.name in context.scene.objects:
                        context.view_layer.objects.active = first_obj
            except (ReferenceError, AttributeError, KeyError):
                pass
        
        # Frame the selected objects in the viewport
        # Find a 3D viewport area with proper context validation
        try:
            for window in context.window_manager.windows:
                if window is None:
                    continue
                if window.screen is None:
                    continue
                for area in window.screen.areas:
                    if area is None or area.type != 'VIEW_3D':
                        continue
                    # Override context to use this area
                    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                    if region is None:
                        continue
                    
                    # Validate all context components before using
                    if context.scene is None or context.scene.name not in bpy.data.scenes:
                        continue
                    if context.view_layer is None:
                        continue
                        
                    override = {
                        'window': window,
                        'screen': window.screen,
                        'area': area,
                        'region': region,
                        'view_layer': context.view_layer,
                        'scene': context.scene,
                    }
                    
                    # Use context override to frame selected
                    # Wrap in multiple try-except layers to catch any possible crash
                    try:
                        # Double-check scene still exists before framing
                        if context.scene.name not in bpy.data.scenes:
                            continue
                        
                        # Use a fresh context override to avoid stale references
                        with context.temp_override(**override):
                            # This operation can crash if depsgraph is invalid
                            # Catch all possible exceptions including SystemExit
                            try:
                                bpy.ops.view3d.view_selected()
                            except (SystemExit, KeyboardInterrupt):
                                # Re-raise these
                                raise
                            except Exception as e:
                                print(f"  ⚠️ Could not frame view (non-critical): {e}")
                                continue
                    except (SystemExit, KeyboardInterrupt):
                        # Re-raise these
                        raise
                    except Exception as e:
                        # Catch any other exception that might cause a crash
                        print(f"  ⚠️ Could not create context override for framing: {e}")
                        continue
                    
                    # Only frame in the first 3D viewport found
                    # Print removed to reduce console clutter
                    return
        except Exception as e:
            print(f"  ⚠️ Could not find viewport for framing: {e}")
        
    except Exception as e:
        print(f"  ⚠️ Could not frame imported objects: {e}")
        # Non-critical error, continue anyway


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
            if objects_to_remove:
                print(f"  🧹 Cleaned {len(objects_to_remove)} leftover object(s) from temp scene")
        except Exception as e:
            print(f"  ⚠️ Could not clean temp scene: {e}")

    # Track all imported objects and materials for toolbar cleanup
    all_imported_objects_tracker = []
    all_imported_materials_tracker = []

    # Find all FBX files
    fbx_files = find_fbx_files(asset_dir)

    if not fbx_files:
        print(f"❌ No FBX files found")
        # Clean up temp scene before returning
        if temp_scene:
            switch_to_scene(bpy.context, original_scene)
            cleanup_preview_scene(temp_scene)
        return {'CANCELLED'}

    # STEP 1: Import all FBX files
    step_start = time.time()
    import_results = []
    for fbx_file in fbx_files:
        imported_objects, base_name = import_fbx_file(fbx_file, context)
        if imported_objects:
            import_results.append((fbx_file, imported_objects, base_name))
    
    if not import_results:
        print(f"❌ Failed to import any FBX files")
        # Clean up temp scene before returning
        if temp_scene:
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
    for fbx_file, imported_objects, _ in import_results:
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
                        print(f"    📏 Applied root scale to child: {child.name} -> scale={child.scale}")
                    
                    # Unparent the child
                    child.parent = None
            
            # Remove old world root objects
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
        
        step4_start = time.time()
        variations = organize_objects_by_variation(all_objects_to_process)
        _performance_data['import_times']['Step 4: Detect Variations'] = time.time() - step4_start
        
        if not variations:
            print(f"  ⚠️ No mesh variations found in asset group")
            continue
        
        # STEP 5: Create materials
        
        step5_start = time.time()
        create_materials_for_all_variations(
            asset_dir,
            attach_root_base_name,
            variations,
            import_groups,
            context,
            texture_resolution
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
        print(f"✅ Import complete - {len(all_imported_objects_tracker)} objects imported")
        
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

    # Skip framing in temp scene - it can cause crashes with invalid depsgraph
    # The toolbar will handle showing the objects, and we'll frame after accepting
    # frame_imported_objects(all_imported_objects_tracker, context)
    
    # Validate context one more time before showing toolbar to prevent crashes
    try:
        # Force refresh context to ensure it's valid
        context = bpy.context
        if context.scene is None or context.scene.name not in bpy.data.scenes:
            print(f"❌ Context scene is invalid before showing toolbar")
            # Switch back to original scene and cleanup
            if temp_scene:
                switch_to_scene(bpy.context, original_scene)
                cleanup_preview_scene(temp_scene)
            return {'CANCELLED'}
    except Exception as e:
        print(f"❌ Context validation failed before showing toolbar: {e}")
        # Switch back to original scene and cleanup
        try:
            if temp_scene:
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
                frame_imported_objects(transferred_objects, bpy.context)

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

            print(f"❌ USER CANCELLED IMPORT - DISCARDING ASSETS")
        
            try:
                # Switch back to original scene first
                switch_to_scene(bpy.context, original_scene)

                # Delete temporary preview scene (auto-cleanup of objects)
                cleanup_preview_scene(temp_scene)

                # Clean up materials that were created during import
                cleanup_imported_materials(
                    all_imported_materials_tracker,
                    materials_before_import
                )

                print(f"✅ Import cancelled - all assets discarded")

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

