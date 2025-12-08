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

        except Exception as e:
            import traceback
            traceback.print_exc()

    # Materials are stored globally in bpy.data.materials
    # They're automatically available in all scenes, no transfer needed

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


def cleanup_imported_materials(imported_materials, materials_before_import):
    """Clean up materials that were created during import.

    Called when import is cancelled to remove unwanted materials.

    Args:
        imported_materials: List of materials created during import
        materials_before_import: Set of material names that existed before import
    """
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


def maximize_viewport_area(context):
    """Maximize the 3D viewport area to focus on preview.

    This hides all other UI panels and maximizes the 3D viewport,
    creating a distraction-free preview environment.

    Args:
        context: Blender context

    Returns:
        bool: True if maximization was successful, False otherwise
    """
    try:
        # Find the 3D viewport area
        viewport_area = None
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                viewport_area = area
                break

        if not viewport_area:
            print("⚠️ Could not find 3D viewport to maximize")
            return False

        # Create a temporary context override for the viewport area
        override_context = context.copy()
        override_context['area'] = viewport_area
        override_context['region'] = viewport_area.regions[-1]  # Use last region (usually the main one)

        # Maximize the viewport area (hides all other panels)
        with context.temp_override(**override_context):
            bpy.ops.screen.screen_full_area(use_hide_panels=True)

        return True

    except Exception as e:
        print(f"⚠️ Failed to maximize viewport: {e}")
        import traceback
        traceback.print_exc()
        return False


def restore_previous_area(context):
    """Restore the previous area layout after maximization.

    This returns the UI to its state before maximize_viewport_area() was called.

    Args:
        context: Blender context

    Returns:
        bool: True if restoration was successful, False otherwise
    """
    try:
        # Find the 3D viewport area (it should still be maximized)
        viewport_area = None
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                viewport_area = area
                break

        if not viewport_area:
            print("⚠️ Could not find 3D viewport to restore")
            return False

        # Create a temporary context override for the viewport area
        override_context = context.copy()
        override_context['area'] = viewport_area
        override_context['region'] = viewport_area.regions[-1]

        # Restore previous layout
        with context.temp_override(**override_context):
            bpy.ops.screen.back_to_previous()

        return True

    except Exception as e:
        print(f"⚠️ Failed to restore previous area: {e}")
        import traceback
        traceback.print_exc()
        return False


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


def create_preview_sphere(context, material, material_size_x, material_size_y):
    """Create a UV sphere for material preview.

    Creates a 2-meter diameter sphere hovering 1 meter above the floor,
    with the material applied and UV scaling adjusted for proper tiling.

    Args:
        context: Blender context
        material: Material to apply to the sphere
        material_size_x: Material size in X direction (meters)
        material_size_y: Material size in Y direction (meters)

    Returns:
        bpy.types.Object: The created sphere object
    """
    # Create UV sphere (2m diameter = 1m radius)
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=1.0,
        location=(0, 0, 1),  # Center at 1m height, so bottom touches floor at z=0
        segments=64,
        ring_count=32
    )

    sphere_obj = context.active_object
    sphere_obj.name = "QuixelMaterialPreviewSphere"

    # Apply shade smooth to the sphere for better material preview
    bpy.ops.object.shade_smooth()

    # Add Subdivision Surface modifier for better displacement preview
    subsurf_modifier = sphere_obj.modifiers.new(name="Subdivision", type='SUBSURF')
    subsurf_modifier.levels = 4
    subsurf_modifier.render_levels = 4

    # Apply material to sphere
    if len(sphere_obj.data.materials) == 0:
        sphere_obj.data.materials.append(material)
    else:
        sphere_obj.data.materials[0] = material

    # Apply correct UV scale to the material for this specific object
    # The sphere is 2m in diameter, and we want the material to tile correctly
    # based on its real-world size
    from ..operations.material_creator import apply_correct_uv_scale
    apply_correct_uv_scale(material, sphere_obj, material_size_x, material_size_y)

    return sphere_obj
