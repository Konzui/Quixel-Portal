"""Floor plane manager for import preview.

This module handles creation and cleanup of a temporary floor plane with dev texture
that appears during the import process.
"""

import bpy
import os
from pathlib import Path


def create_floor_plane(context):
    """Create a temporary floor plane with dev.tex texture.

    The floor is a 500x500 meter plane with the dev_tex.png texture tiled every 1 meter.
    It has a radial gradient that fades to transparent at the edges for an infinite appearance.
    Single-sided rendering means it's only visible from above (backface culling enabled).

    Args:
        context: Blender context

    Returns:
        tuple: (floor_object, floor_material) or (None, None) if creation failed
    """
    try:
        # Get addon directory
        addon_dir = Path(__file__).parent.parent
        dev_tex_path = addon_dir / "assets" / "img" / "dev_tex.png"

        if not dev_tex_path.exists():
            print(f"⚠️ Dev texture not found: {dev_tex_path}")
            return None, None

        # Create large plane (500x500 meters = 5x the original 100m)
        bpy.ops.mesh.primitive_plane_add(size=500, location=(0, 0, 0))
        floor_obj = context.active_object
        floor_obj.name = "__QuixelFloor__"
        floor_obj.hide_select = True  # Disable selection to prevent accidental selection
        # Don't flip normals - default plane normals point up (Z+) which is correct

        # Create material
        floor_mat = bpy.data.materials.new(name="__QuixelFloorMaterial__")
        floor_mat.use_nodes = True
        floor_mat.blend_method = 'BLEND'  # Smooth gradient transparency (imported models use HASHED to avoid sorting conflicts)
        floor_mat.use_backface_culling = True  # Single-sided rendering

        nodes = floor_mat.node_tree.nodes
        links = floor_mat.node_tree.links

        # Clear default nodes
        nodes.clear()

        # Create nodes
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (600, 0)

        bsdf_node = nodes.new(type='ShaderNodeBsdfPrincipled')
        bsdf_node.location = (400, 0)
        bsdf_node.inputs['Alpha'].default_value = 1.0

        # Texture coordinate and mapping for the dev texture
        tex_coord_node = nodes.new(type='ShaderNodeTexCoord')
        tex_coord_node.location = (-800, 200)

        mapping_node = nodes.new(type='ShaderNodeMapping')
        mapping_node.location = (-600, 200)
        # Scale for 1m texture repetition (500x500 meter plane)
        mapping_node.inputs['Scale'].default_value = (250, 250, 250)

        image_node = nodes.new(type='ShaderNodeTexImage')
        image_node.location = (-400, 200)

        # Load image
        if str(dev_tex_path) in bpy.data.images:
            image = bpy.data.images[str(dev_tex_path)]
        else:
            image = bpy.data.images.load(str(dev_tex_path))
        image_node.image = image

        # Create edge fade gradient using UV coordinates
        # This creates a box-shaped fade that only appears at the plane edges
        tex_coord_fade = nodes.new(type='ShaderNodeTexCoord')
        tex_coord_fade.location = (-1200, -200)

        separate_xyz = nodes.new(type='ShaderNodeSeparateXYZ')
        separate_xyz.location = (-1000, -200)

        # Remap UV from [0,1] to [-0.5,0.5] so center is at 0
        # For X axis
        subtract_x = nodes.new(type='ShaderNodeMath')
        subtract_x.operation = 'SUBTRACT'
        subtract_x.inputs[1].default_value = 0.5  # Subtract 0.5 to center
        subtract_x.location = (-800, -100)

        abs_x = nodes.new(type='ShaderNodeMath')
        abs_x.operation = 'ABSOLUTE'
        abs_x.location = (-600, -100)

        # For Y axis
        subtract_y = nodes.new(type='ShaderNodeMath')
        subtract_y.operation = 'SUBTRACT'
        subtract_y.inputs[1].default_value = 0.5  # Subtract 0.5 to center
        subtract_y.location = (-800, -250)

        abs_y = nodes.new(type='ShaderNodeMath')
        abs_y.operation = 'ABSOLUTE'
        abs_y.location = (-600, -250)

        # Get maximum of X and Y to create square falloff
        max_xy = nodes.new(type='ShaderNodeMath')
        max_xy.operation = 'MAXIMUM'
        max_xy.location = (-400, -200)

        # ColorRamp to control fade distance at edges
        color_ramp = nodes.new(type='ShaderNodeValToRGB')
        color_ramp.location = (-200, -200)
        # Center (0.0) = full opacity (white), edges (0.5) = transparent (black)
        # Start fade at 0.35 (70% from center), fully transparent at 0.5 (edge)
        color_ramp.color_ramp.elements[0].position = 0.0
        color_ramp.color_ramp.elements[0].color = (1, 1, 1, 1)  # Opaque at center
        color_ramp.color_ramp.elements[1].position = 0.35
        color_ramp.color_ramp.elements[1].color = (1, 1, 1, 1)  # Still opaque
        # Add third element for edge transparency
        if len(color_ramp.color_ramp.elements) < 3:
            color_ramp.color_ramp.elements.new(0.5)
        color_ramp.color_ramp.elements[2].position = 0.5
        color_ramp.color_ramp.elements[2].color = (0, 0, 0, 1)  # Transparent at edge

        # Connect gradient nodes
        links.new(tex_coord_fade.outputs['UV'], separate_xyz.inputs['Vector'])
        links.new(separate_xyz.outputs['X'], subtract_x.inputs[0])
        links.new(subtract_x.outputs['Value'], abs_x.inputs[0])
        links.new(separate_xyz.outputs['Y'], subtract_y.inputs[0])
        links.new(subtract_y.outputs['Value'], abs_y.inputs[0])
        links.new(abs_x.outputs['Value'], max_xy.inputs[0])
        links.new(abs_y.outputs['Value'], max_xy.inputs[1])
        links.new(max_xy.outputs['Value'], color_ramp.inputs['Fac'])

        # Connect texture nodes
        links.new(tex_coord_node.outputs['UV'], mapping_node.inputs['Vector'])
        links.new(mapping_node.outputs['Vector'], image_node.inputs['Vector'])
        links.new(image_node.outputs['Color'], bsdf_node.inputs['Base Color'])

        # Connect alpha (gradient controls transparency)
        links.new(color_ramp.outputs['Color'], bsdf_node.inputs['Alpha'])

        # Connect to output
        links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])

        # Assign material to disc
        if floor_obj.data.materials:
            floor_obj.data.materials[0] = floor_mat
        else:
            floor_obj.data.materials.append(floor_mat)

        return floor_obj, floor_mat

    except Exception as e:
        print(f"⚠️ Failed to create floor plane: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def cleanup_floor_plane(floor_obj=None, floor_mat=None):
    """Remove the temporary floor plane and its material.

    Args:
        floor_obj: Floor object to remove (optional, will search by name if None)
        floor_mat: Floor material to remove (optional, will search by name if None)
    """
    try:
        # Find floor object if not provided
        if floor_obj is None:
            floor_obj = bpy.data.objects.get("__QuixelFloor__")

        # Remove floor object
        if floor_obj:
            try:
                bpy.data.objects.remove(floor_obj, do_unlink=True)
            except Exception as e:
                pass

        # Find floor material if not provided
        if floor_mat is None:
            floor_mat = bpy.data.materials.get("__QuixelFloorMaterial__")

        # Remove floor material
        if floor_mat:
            try:
                bpy.data.materials.remove(floor_mat)
            except Exception as e:
                pass

    except Exception as e:
        print(f"⚠️ Error during floor plane cleanup: {e}")
        import traceback
        traceback.print_exc()
