"""Scene management utilities for temporary preview scenes.

This module handles creation, switching, and cleanup of temporary preview
scenes used during asset import.
"""

import bpy
import mathutils


def create_preview_scene(context, base_name="__QuixelPreview__"):
    """Create a temporary preview scene for asset import.

    Args:
        context: Blender context
        base_name: Base name for the preview scene

    Returns:
        bpy.types.Scene: The created preview scene
    """
    # Clean up any existing preview scenes first (this removes all objects in them)
    cleanup_orphaned_preview_scenes()

    # Get original scene to copy settings from
    original_scene = context.scene

    # Create new temporary scene
    temp_scene = bpy.data.scenes.new(name=base_name)
    
    # Ensure the new scene is completely empty (no default objects)
    # Remove any default objects that might have been created
    for obj in list(temp_scene.collection.objects):
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
        except:
            pass

    # Copy important settings from original scene
    temp_scene.world = original_scene.world  # Keep same lighting/environment

    # Set render engine - use EEVEE_NEXT for Blender 4.2+, fallback to EEVEE for older versions
    try:
        temp_scene.render.engine = 'BLENDER_EEVEE_NEXT'  # Blender 4.2+
    except TypeError:
        try:
            temp_scene.render.engine = 'BLENDER_EEVEE'  # Blender 3.x - 4.1
        except TypeError:
            # If both fail, use whatever the original scene had
            temp_scene.render.engine = original_scene.render.engine

    # Configure Eevee settings if available (works for both EEVEE and EEVEE_NEXT)
    if hasattr(temp_scene, 'eevee'):
        try:
            temp_scene.eevee.use_gtao = True  # Ambient occlusion for better preview
            temp_scene.eevee.use_bloom = False  # Disable bloom for cleaner preview
        except AttributeError:
            pass  # Settings might not be available in this version

    # Copy view layer settings
    temp_scene.view_layers[0].use_pass_combined = True

    print(f"✅ Created temporary preview scene: {temp_scene.name}")

    return temp_scene


def switch_to_scene(context, target_scene):
    """Switch the current context to a different scene.

    Args:
        context: Blender context
        target_scene: Scene to switch to

    Returns:
        bool: True if switch was successful
    """
    if not target_scene or target_scene.name not in bpy.data.scenes:
        print(f"⚠️ Cannot switch to scene: scene not found")
        return False

    try:
        # Switch scene in current window
        context.window.scene = target_scene

        # Update view layer
        context.view_layer.update()

        # Tag all viewports for redraw
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        # Print removed to reduce console clutter
        return True

    except Exception as e:
        print(f"⚠️ Failed to switch scene: {e}")
        return False


def transfer_assets_to_original_scene(
    temp_scene,
    original_scene,
    imported_objects,
    imported_materials
):
    """Transfer imported objects and materials from temp scene to original scene.

    Args:
        temp_scene: Temporary preview scene
        original_scene: User's original scene
        imported_objects: List of objects to transfer (should include attach roots)
        imported_materials: List of materials to transfer

    Returns:
        list: List of successfully transferred objects (including all children)
    """
    # Header prints removed to reduce console clutter

    transferred_objects = []
    transferred_names = set()  # Track transferred object names to avoid duplicates

    # First, collect all objects to transfer (including children of attach roots)
    all_objects_to_transfer = []
    for obj in imported_objects:
        try:
            # Check if object still exists
            if obj.name not in bpy.data.objects:
                # Print removed to reduce console clutter
                continue
            
            # Add the object itself
            if obj.name not in transferred_names:
                all_objects_to_transfer.append(obj)
                transferred_names.add(obj.name)
            
            # If this is an attach root, also collect all its children
            if obj.get("ioiAttachRootNode"):
                for child in obj.children:
                    if child.name not in transferred_names:
                        all_objects_to_transfer.append(child)
                        transferred_names.add(child.name)
        except (ReferenceError, AttributeError, KeyError):
            continue

    # Transfer all objects (attach roots and their children)
    for obj in all_objects_to_transfer:
        try:
            # Double-check object still exists
            if obj.name not in bpy.data.objects:
                continue
            
            # Get all collections this object is linked to
            collections_to_unlink = list(obj.users_collection)
            
            # Unlink from all collections (including temp scene's collection)
            for collection in collections_to_unlink:
                try:
                    collection.objects.unlink(obj)
                except:
                    pass  # Collection might already be deleted or object not in it

            # Link to original scene's active collection
            original_scene.collection.objects.link(obj)
            transferred_objects.append(obj)

            # Print removed to reduce console clutter

        except Exception as e:
            # Print removed to reduce console clutter
            import traceback
            traceback.print_exc()

    # Materials are stored globally in bpy.data.materials
    # They're automatically available in all scenes, no transfer needed
    # Print removed to reduce console clutter

    # Print removed to reduce console clutter

    return transferred_objects


def cleanup_preview_scene(temp_scene):
    """Delete a temporary preview scene and its data.

    Args:
        temp_scene: Scene to delete
    """
    if not temp_scene or temp_scene.name not in bpy.data.scenes:
        print(f"⚠️ Preview scene already deleted or not found")
        return

    scene_name = temp_scene.name

    try:
        # Before deleting the scene, ensure all objects are unlinked from it
        # This prevents objects from being deleted if they're only in this scene
        objects_in_scene = list(temp_scene.collection.objects)
        for obj in objects_in_scene:
            try:
                # Unlink from temp scene's collection
                temp_scene.collection.objects.unlink(obj)
            except:
                pass  # Object might already be unlinked
        
        # Remove the scene
        # Objects that are ONLY in this scene will be deleted
        # Objects linked to other scenes will remain
        bpy.data.scenes.remove(temp_scene, do_unlink=True)

        # Print removed to reduce console clutter

    except Exception as e:
        print(f"⚠️ Failed to delete preview scene: {e}")
        import traceback
        traceback.print_exc()


def cleanup_orphaned_preview_scenes():
    """Remove any orphaned preview scenes from previous sessions.

    This is called on addon startup and before creating new preview scenes.
    """
    # Safety check: bpy.data might not be fully initialized during addon registration
    try:
        if not hasattr(bpy.data, 'scenes'):
            return
    except AttributeError:
        return

    preview_pattern = "__QuixelPreview__"
    removed_count = 0

    scenes_to_remove = []
    try:
        for scene in bpy.data.scenes:
            if scene.name.startswith(preview_pattern):
                scenes_to_remove.append(scene)
    except (AttributeError, RuntimeError):
        # bpy.data not ready yet, skip cleanup
        return

    for scene in scenes_to_remove:
        try:
            bpy.data.scenes.remove(scene, do_unlink=True)
            removed_count += 1
        except Exception as e:
            print(f"⚠️ Failed to remove orphaned scene '{scene.name}': {e}")

    if removed_count > 0:
        print(f"🧹 Cleaned up {removed_count} orphaned preview scene(s)")


def cleanup_imported_materials(imported_materials, materials_before_import):
    """Clean up materials that were created during import.

    Called when import is cancelled to remove unwanted materials.

    Args:
        imported_materials: List of materials created during import
        materials_before_import: Set of material names that existed before import
    """
    print(f"\n🧹 CLEANING UP IMPORTED MATERIALS:")

    removed_count = 0

    for mat in imported_materials:
        # Store material name before accessing it (in case it gets deleted)
        mat_name = None
        try:
            # Try to get the material name
            mat_name = mat.name
        except ReferenceError:
            # Material was already deleted (e.g., when preview scene was deleted)
            continue

        try:
            # Check if material still exists in bpy.data.materials
            if mat_name not in bpy.data.materials:
                continue

            # Check if this material was created during this import
            if mat_name not in materials_before_import:
                # Remove the material
                bpy.data.materials.remove(mat, do_unlink=True)
                print(f"  🗑️ Removed: {mat_name}")
                removed_count += 1

        except ReferenceError:
            # Material was deleted between checks - this is fine
            continue
        except Exception as e:
            # Only print error if we have a valid material name
            if mat_name:
                print(f"  ⚠️ Failed to remove material '{mat_name}': {e}")
            else:
                print(f"  ⚠️ Failed to remove material (already deleted): {e}")

    if removed_count > 0:
        print(f"  ✅ Cleaned up {removed_count} material(s)")
    else:
        print(f"  ℹ️ No materials to clean up (may have been auto-deleted with preview scene)")


def setup_preview_camera(temp_scene, imported_objects):
    """Set up a camera in the preview scene to frame imported objects.

    Args:
        temp_scene: Preview scene
        imported_objects: List of imported objects to frame
    """
    if not imported_objects:
        return

    # Calculate combined bounding box of all objects
    all_coords = []
    for obj in imported_objects:
        if obj.type == 'MESH' and obj.data:
            for corner in obj.bound_box:
                world_coord = obj.matrix_world @ mathutils.Vector(corner)
                all_coords.append(world_coord)

    if not all_coords:
        return

    # Calculate center and size
    min_x = min(coord.x for coord in all_coords)
    max_x = max(coord.x for coord in all_coords)
    min_y = min(coord.y for coord in all_coords)
    max_y = max(coord.y for coord in all_coords)
    min_z = min(coord.z for coord in all_coords)
    max_z = max(coord.z for coord in all_coords)

    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    center_z = (min_z + max_z) / 2

    # Calculate distance needed to frame objects
    width = max_x - min_x
    height = max_y - min_y
    depth = max_z - min_z
    max_dimension = max(width, height, depth)

    # Create camera
    camera_data = bpy.data.cameras.new(name="QuixelPreviewCamera")
    camera_obj = bpy.data.objects.new(name="QuixelPreviewCamera", object_data=camera_data)
    temp_scene.collection.objects.link(camera_obj)

    # Position camera to view objects from an angle
    distance = max_dimension * 2.5
    camera_obj.location = (
        center_x + distance * 0.7,
        center_y - distance * 0.7,
        center_z + distance * 0.5
    )

    # Point camera at center
    direction = mathutils.Vector((center_x, center_y, center_z)) - camera_obj.location
    camera_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

    # Set as active camera
    temp_scene.camera = camera_obj

    print(f"✅ Created preview camera framing {len(imported_objects)} object(s)")
