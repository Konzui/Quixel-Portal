bl_info = {
    "name": "Quixel Portal",
    "author": "Your Name",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "Topbar",
    "description": "Open Quixel Megascans Portal in dedicated browser",
    "category": "Import-Export",
}

import bpy
import bpy.utils.previews
import mathutils
import os
import subprocess
import sys
import json
import glob
import math
from pathlib import Path

# Global variable to store icons
custom_icons = None

# Track if we've registered in this session to prevent duplicates
_draw_function_registered = False

# Timer for checking import requests
_import_timer = None

def load_texture(nodes, tex_type, tex_path, color_space='sRGB'):
    """Load texture and create image texture node"""
    if not tex_path or not tex_path.exists():
        return None
    
    # Create image texture node
    tex_node = nodes.new(type='ShaderNodeTexImage')
    tex_node.location = (-600, -200 * len([n for n in nodes if isinstance(n, bpy.types.ShaderNodeTexImage)]))
    
    # Load image
    try:
        img = bpy.data.images.load(str(tex_path))
        img.colorspace_settings.name = color_space
        tex_node.image = img
        print(f"    ✅ Loaded {tex_type}: {tex_path.name}")
        return tex_node
    except Exception as e:
        print(f"    ❌ Failed to load {tex_type} texture {tex_path.name}: {e}")
        nodes.remove(tex_node)
        return None

def _draw_quixel_button_impl(self, context):
    """Internal implementation of the draw function"""
    global custom_icons
    layout = self.layout
    
    # Create button with custom icon if available
    if custom_icons:
        try:
            # Check if icon exists and get its ID
            if "quixel_logo" in custom_icons:
                icon_item = custom_icons["quixel_logo"]
                if hasattr(icon_item, 'icon_id') and icon_item.icon_id != 0:
                    layout.operator("quixel.open_portal", text="Quixel Portal", icon_value=icon_item.icon_id, emboss=True)
                    return
        except Exception as e:
            print(f"⚠️ Quixel Portal: Error accessing icon: {e}")
    
    # Fallback button without custom icon
    layout.operator("quixel.open_portal", text="Quixel Portal", icon='WORLD', emboss=True)

# Create a wrapper function with a unique identifier
# This allows us to identify our function even after module reloads
def draw_quixel_button(self, context):
    """Draw function to add Quixel Portal button to topbar"""
    _draw_quixel_button_impl(self, context)

# Mark the wrapper with a unique attribute for identification
draw_quixel_button._quixel_portal_id = "quixel_portal_button_v1"


class QUIXEL_OT_open_portal(bpy.types.Operator):
    """Open Quixel Portal in dedicated browser"""
    bl_idname = "quixel.open_portal"
    bl_label = "Open Quixel Portal"
    bl_options = {'REGISTER'}

    def execute(self, context):
        # Get the addon directory
        addon_dir = Path(__file__).parent
        electron_app_dir = addon_dir / "electron_app"

        # Path to the built executable
        exe_path = electron_app_dir / "build" / "win-unpacked" / "Quixel Portal.exe"

        # Check if executable exists
        if exe_path.exists():
            # Use the built executable
            try:
                subprocess.Popen(
                    [str(exe_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                self.report({'INFO'}, "Quixel Portal launched!")
                return {'FINISHED'}
            except Exception as e:
                self.report({'ERROR'}, f"Failed to launch Quixel Portal: {str(e)}")
                return {'CANCELLED'}
        else:
            # Fallback to npm start if exe doesn't exist
            if not electron_app_dir.exists():
                self.report({'ERROR'}, "Electron app not found. Please ensure the addon is properly installed.")
                return {'CANCELLED'}

            node_modules = electron_app_dir / "node_modules"
            if not node_modules.exists():
                self.report({'ERROR'}, "Electron app not built. Please run 'npm install' in the electron_app directory.")
                return {'CANCELLED'}

            try:
                if sys.platform == "win32":
                    npm_cmd = "npm.cmd"
                else:
                    npm_cmd = "npm"

                subprocess.Popen(
                    [npm_cmd, "start"],
                    cwd=str(electron_app_dir),
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                self.report({'INFO'}, "Quixel Portal launched!")
                return {'FINISHED'}

            except Exception as e:
                self.report({'ERROR'}, f"Failed to launch Quixel Portal: {str(e)}")
                return {'CANCELLED'}


class QUIXEL_OT_import_fbx(bpy.types.Operator):
    """Import FBX files from a directory"""
    bl_idname = "quixel.import_fbx"
    bl_label = "Import Quixel Asset"
    bl_options = {'REGISTER', 'UNDO'}

    directory: bpy.props.StringProperty(
        name="Asset Directory",
        description="Directory containing the downloaded asset",
        subtype='DIR_PATH'
    )

    thumbnail_path: bpy.props.StringProperty(
        name="Thumbnail Path",
        description="Path to the asset thumbnail image",
        default=""
    )

    asset_name_override: bpy.props.StringProperty(
        name="Asset Name",
        description="Override asset name from request",
        default=""
    )
    
    def _find_json_file(self, asset_dir):
        """Find the JSON metadata file in the asset directory"""
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
    
    def _get_name_from_json(self, asset_dir):
        """Extract name from JSON file following the naming convention"""
        json_file = self._find_json_file(asset_dir)
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
            
            # Construct name: quixel_{semantic_name}_{json_filename}_A (all lowercase)
            name = f"quixel_{semantic_name_clean}_{json_stem}_a"
            
            return name, json_file
        except Exception as e:
            print(f"  ⚠️ Failed to parse JSON file {json_file}: {e}")
            return None, None
    
    def _get_material_name_from_json(self, asset_dir, json_filename):
        """Extract material name from JSON file following the naming convention"""
        name, _ = self._get_name_from_json(asset_dir)
        return name
    
    def _create_surface_material(self, asset_dir, context):
        """Create a material for a surface asset from JSON and textures"""
        import re
        
        # Find JSON file
        json_file = self._find_json_file(asset_dir)
        if not json_file:
            print(f"  ⚠️ No JSON file found in {asset_dir}")
            return False
        
        # Get material name from JSON
        material_name = self._get_material_name_from_json(asset_dir, json_file)
        if not material_name:
            print(f"  ⚠️ Could not extract material name from JSON")
            return False
        
        # Find all texture files
        texture_extensions = ['.png', '.jpg', '.jpeg', '.tga', '.tif', '.tiff', '.exr']
        texture_files = []
        for ext in texture_extensions:
            texture_files.extend(asset_dir.glob(f"**/*{ext}"))
            texture_files.extend(asset_dir.glob(f"**/*{ext.upper()}"))
        
        if not texture_files:
            print(f"  ⚠️ No texture files found in {asset_dir}")
            return False
        
        # Check if material already exists
        if material_name in bpy.data.materials:
            mat = bpy.data.materials[material_name]
            bpy.data.materials.remove(mat, do_unlink=True)
        
        # Create new material
        mat = bpy.data.materials.new(name=material_name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        # Get or create Principled BSDF
        bsdf = nodes.get("Principled BSDF")
        if not bsdf:
            bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
        
        # Find textures by type
        textures = {}
        for tex_file in texture_files:
            filename_lower = tex_file.stem.lower()
            
            if 'albedo' in filename_lower or 'diffuse' in filename_lower or 'color' in filename_lower:
                textures['albedo'] = tex_file
            elif 'roughness' in filename_lower or 'rough' in filename_lower:
                textures['roughness'] = tex_file
            elif 'normal' in filename_lower and 'gl' not in filename_lower:
                textures['normal'] = tex_file
            elif 'displacement' in filename_lower or 'height' in filename_lower:
                textures['displacement'] = tex_file
            elif 'metallic' in filename_lower or 'metalness' in filename_lower:
                textures['metallic'] = tex_file
            elif 'opacity' in filename_lower or 'alpha' in filename_lower or 'mask' in filename_lower:
                textures['opacity'] = tex_file
        
        # Load Albedo texture
        if 'albedo' in textures:
            albedo_node = load_texture(nodes, 'Albedo', textures['albedo'], 'sRGB')
            if albedo_node:
                links.new(albedo_node.outputs['Color'], bsdf.inputs['Base Color'])
        
        # Load Roughness texture
        if 'roughness' in textures:
            roughness_node = load_texture(nodes, 'Roughness', textures['roughness'], 'Non-Color')
            if roughness_node:
                links.new(roughness_node.outputs['Color'], bsdf.inputs['Roughness'])
        
        # Load Normal texture
        if 'normal' in textures:
            normal_node = load_texture(nodes, 'Normal', textures['normal'], 'Non-Color')
            if normal_node:
                # Create normal map node
                normal_map_node = nodes.new(type='ShaderNodeNormalMap')
                normal_map_node.location = (-300, -400)
                links.new(normal_node.outputs['Color'], normal_map_node.inputs['Color'])
                links.new(normal_map_node.outputs['Normal'], bsdf.inputs['Normal'])
        
        # Load Displacement texture
        if 'displacement' in textures:
            displacement_node = load_texture(nodes, 'Displacement', textures['displacement'], 'Non-Color')
            if displacement_node:
                # Create displacement node
                displacement_shader = nodes.new(type='ShaderNodeDisplacement')
                displacement_shader.location = (-300, -600)
                links.new(displacement_node.outputs['Color'], displacement_shader.inputs['Height'])
                
                # Connect to material output
                output = nodes.get("Material Output")
                if output:
                    links.new(displacement_shader.outputs['Displacement'], output.inputs['Displacement'])
        
        # Load Metallic texture
        if 'metallic' in textures:
            metallic_node = load_texture(nodes, 'Metallic', textures['metallic'], 'Non-Color')
            if metallic_node:
                links.new(metallic_node.outputs['Color'], bsdf.inputs['Metallic'])
        
        # Load Opacity/Alpha/Mask texture
        if 'opacity' in textures:
            opacity_node = load_texture(nodes, 'Opacity', textures['opacity'], 'Non-Color')
            if opacity_node:
                # Connect to Alpha input of Principled BSDF
                links.new(opacity_node.outputs['Color'], bsdf.inputs['Alpha'])
                # Enable alpha blending for the material
                mat.blend_method = 'BLEND'
                print(f"    ✅ Enabled alpha blending for material")
        
        # Assign material to selected objects if any are selected
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if selected_objects:
            for obj in selected_objects:
                # Assign material to object
                if len(obj.data.materials) == 0:
                    obj.data.materials.append(mat)
                else:
                    obj.data.materials[0] = mat
                print(f"    ✅ Assigned material to selected object: {obj.name}")
        else:
            print(f"  ℹ️  No mesh objects selected - material created but not assigned")
        
        print(f"  🎨 Created surface material: {material_name}")
        return True
    
    def _create_materials_for_asset(self, asset_dir, base_name, world_root_name, import_groups, all_objects_to_parent, context):
        """Create materials and assign textures for each LOD level"""
        import re
        
        # Find all texture files in the asset directory
        texture_extensions = ['.png', '.jpg', '.jpeg', '.tga', '.tif', '.tiff', '.exr']
        texture_files = []
        for ext in texture_extensions:
            texture_files.extend(asset_dir.glob(f"**/*{ext}"))
            texture_files.extend(asset_dir.glob(f"**/*{ext.upper()}"))
        
        if not texture_files:
            print(f"  ⚠️ No texture files found in {asset_dir}")
            return
        
        # Pattern to extract LOD level from texture filename
        lod_pattern = re.compile(r'_?LOD(\d+)', re.IGNORECASE)
        
        # Group textures by LOD level and type
        # Structure: {lod_level: {'albedo': path, 'roughness': path, 'normal': path, 'metallic': path}}
        lod_textures = {}
        
        for tex_file in texture_files:
            filename_lower = tex_file.stem.lower()
            
            # Extract LOD level
            lod_match = lod_pattern.search(tex_file.stem)
            lod_level = lod_match.group(1) if lod_match else "0"
            
            if lod_level not in lod_textures:
                lod_textures[lod_level] = {}
            
            # Identify texture type by filename
            if 'albedo' in filename_lower or 'diffuse' in filename_lower or 'color' in filename_lower:
                lod_textures[lod_level]['albedo'] = tex_file
            elif 'roughness' in filename_lower or 'rough' in filename_lower:
                lod_textures[lod_level]['roughness'] = tex_file
            elif 'normal' in filename_lower and 'gl' not in filename_lower:
                lod_textures[lod_level]['normal'] = tex_file
            elif 'metallic' in filename_lower or 'metalness' in filename_lower:
                lod_textures[lod_level]['metallic'] = tex_file
            elif 'opacity' in filename_lower or 'alpha' in filename_lower or 'mask' in filename_lower:
                lod_textures[lod_level]['opacity'] = tex_file
        
        # Get all LOD levels that have objects (from FBX imports)
        lod_levels_with_objects = set()
        for import_group in import_groups:
            fbx_file = import_group['fbx_file']
            lod_match = lod_pattern.search(fbx_file.stem)
            lod_level = lod_match.group(1) if lod_match else "0"
            lod_levels_with_objects.add(lod_level)
        
        # Fill in missing LOD levels with textures from previous available LOD
        # Sort LOD levels numerically
        all_lod_levels = sorted(lod_levels_with_objects, key=lambda x: int(x))
        texture_types = ['albedo', 'roughness', 'normal', 'metallic', 'opacity']
        
        # For each LOD level that has objects, ensure it has textures
        # Use textures from the most recent previous LOD level that has that texture type
        for lod_level in all_lod_levels:
            if lod_level not in lod_textures:
                lod_textures[lod_level] = {}
            
            # For each texture type, find the most recent previous LOD that has it
            for tex_type in texture_types:
                if tex_type not in lod_textures[lod_level]:
                    # Look backwards through LOD levels to find the most recent one with this texture
                    current_lod_num = int(lod_level)
                    for prev_lod_num in range(current_lod_num - 1, -1, -1):
                        prev_lod_str = str(prev_lod_num)
                        if prev_lod_str in lod_textures and tex_type in lod_textures[prev_lod_str]:
                            lod_textures[lod_level][tex_type] = lod_textures[prev_lod_str][tex_type]
                            print(f"    📋 Using {tex_type} from LOD{prev_lod_str} for LOD{lod_level}")
                            break
        
        # Create a mapping of objects to their LOD levels based on which FBX file they came from
        # Structure: {lod_level: [list of objects]}
        lod_objects = {}
        for import_group in import_groups:
            fbx_file = import_group['fbx_file']
            objects = import_group['objects']
            
            # Extract LOD level from FBX filename
            lod_match = lod_pattern.search(fbx_file.stem)
            lod_level = lod_match.group(1) if lod_match else "0"
            
            if lod_level not in lod_objects:
                lod_objects[lod_level] = []
            
            # Add mesh objects from this import
            for obj in objects:
                if obj.type == 'MESH' and obj.data:
                    lod_objects[lod_level].append(obj)
        
        # Create materials for each LOD level that has objects
        # Use the sorted list of LOD levels with objects to ensure we process them in order
        for lod_level in all_lod_levels:
            # Get textures for this LOD level (may be filled from previous LODs)
            textures = lod_textures.get(lod_level, {})
            # Material name: same as world root name with LOD suffix
            material_name = f"{world_root_name}_LOD{lod_level}"
            
            # Check if material already exists
            if material_name in bpy.data.materials:
                mat = bpy.data.materials[material_name]
                bpy.data.materials.remove(mat, do_unlink=True)
            
            # Create new material
            mat = bpy.data.materials.new(name=material_name)
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            
            # Get or create Principled BSDF
            bsdf = nodes.get("Principled BSDF")
            if not bsdf:
                bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
            
            # Load Albedo texture
            if 'albedo' in textures:
                albedo_node = load_texture(nodes, 'Albedo', textures['albedo'], 'sRGB')
                if albedo_node:
                    links.new(albedo_node.outputs['Color'], bsdf.inputs['Base Color'])
            
            # Load Roughness texture
            if 'roughness' in textures:
                roughness_node = load_texture(nodes, 'Roughness', textures['roughness'], 'Non-Color')
                if roughness_node:
                    links.new(roughness_node.outputs['Color'], bsdf.inputs['Roughness'])
            
            # Load Normal texture
            if 'normal' in textures:
                normal_node = load_texture(nodes, 'Normal', textures['normal'], 'Non-Color')
                if normal_node:
                    # Create normal map node
                    normal_map_node = nodes.new(type='ShaderNodeNormalMap')
                    normal_map_node.location = (-300, -400)
                    links.new(normal_node.outputs['Color'], normal_map_node.inputs['Color'])
                    links.new(normal_map_node.outputs['Normal'], bsdf.inputs['Normal'])
            
            # Load Metallic texture
            if 'metallic' in textures:
                metallic_node = load_texture(nodes, 'Metallic', textures['metallic'], 'Non-Color')
                if metallic_node:
                    links.new(metallic_node.outputs['Color'], bsdf.inputs['Metallic'])
            
            # Load Opacity/Alpha/Mask texture
            if 'opacity' in textures:
                opacity_node = load_texture(nodes, 'Opacity', textures['opacity'], 'Non-Color')
                if opacity_node:
                    # Connect to Alpha input of Principled BSDF
                    links.new(opacity_node.outputs['Color'], bsdf.inputs['Alpha'])
                    # Enable alpha blending for the material
                    mat.blend_method = 'BLEND'
                    print(f"    ✅ Enabled alpha blending for material")
            
            print(f"  🎨 Created material: {material_name}")
            
            # Assign material to mesh objects from this LOD level
            if lod_level in lod_objects:
                for obj in lod_objects[lod_level]:
                    # Assign material to object
                    if len(obj.data.materials) == 0:
                        obj.data.materials.append(mat)
                    else:
                        obj.data.materials[0] = mat
                    print(f"    ✅ Assigned material to: {obj.name}")

    def execute(self, context):
        import re
        
        asset_dir = Path(self.directory)

        if not asset_dir.exists():
            self.report({'ERROR'}, f"Asset directory not found: {asset_dir}")
            return {'CANCELLED'}

        # Find all FBX files in the directory (including subdirectories)
        fbx_files = list(asset_dir.glob("**/*.fbx"))

        # Check if this is a surface material (no FBX files, but has textures and JSON)
        if not fbx_files:
            # Check if it's a surface material
            json_file = self._find_json_file(asset_dir)
            texture_extensions = ['.png', '.jpg', '.jpeg', '.tga', '.tif', '.tiff', '.exr']
            texture_files = []
            for ext in texture_extensions:
                texture_files.extend(asset_dir.glob(f"**/*{ext}"))
            
            if json_file and texture_files:
                # This is a surface material, create it
                if self._create_surface_material(asset_dir, context):
                    self.report({'INFO'}, f"Surface material imported from {asset_dir.name}")

                    # Notify Electron that import is complete
                    self._notify_import_complete(asset_dir)

                    return {'FINISHED'}
                else:
                    self.report({'ERROR'}, "Failed to create surface material")
                    return {'CANCELLED'}
            else:
                self.report({'WARNING'}, f"No FBX files or surface materials found in {asset_dir}")
                return {'CANCELLED'}

        # Pattern to match LOD suffixes like _LOD0, _LOD1, LOD5, etc. at the END of the name
        # This ensures we only remove the LOD suffix and nothing else
        lod_pattern = re.compile(r'_?LOD\d+$', re.IGNORECASE)
        
        def get_base_name(name):
            """Extract base name from object name, removing only the LOD suffix at the end"""
            # Remove LOD suffix if present (only at the very end)
            match = lod_pattern.search(name)
            if match:
                # Verify the match is at the very end of the string
                if match.end() == len(name):
                    # Only remove if the match is at the very end
                    base_name = name[:match.start()]
                    print(f"  📝 Extracted base name: '{name}' -> '{base_name}' (removed '{match.group()}')")
                    return base_name
            return name
        
        # Import all FBX files first to get the actual object names
        imported_count = 0
        all_imported_objects = {}  # Maps base_name -> list of (fbx_file, imported_objects)
        
        for fbx_file in fbx_files:
            try:
                # Store current selection and existing objects
                selected_objects = list(context.selected_objects)
                active_object = context.active_object
                existing_objects = set(context.scene.objects)
                
                # Clear selection
                bpy.ops.object.select_all(action='DESELECT')
                
                # Import the FBX file
                bpy.ops.import_scene.fbx(filepath=str(fbx_file))
                
                # Find all newly imported objects (objects that didn't exist before)
                imported_objects = [obj for obj in context.scene.objects if obj not in existing_objects]
                
                if not imported_objects:
                    print(f"  ⚠️ No objects imported from: {fbx_file.name}")
                    continue
                
                # Get the base name from the imported object names (not the filename)
                # Use the first imported object's name to determine the base name
                # Typically, the main object will be the first one or have the most relevant name
                object_names = [obj.name for obj in imported_objects]
                # Try to find a name that looks like the main asset (not a child or helper object)
                main_object_name = object_names[0]  # Start with first object
                for obj_name in object_names:
                    # Prefer names that don't contain common child object indicators
                    if not any(indicator in obj_name.lower() for indicator in ['_child', '_helper', '_bone', '_armature']):
                        main_object_name = obj_name
                        break
                
                base_name = get_base_name(main_object_name)
                
                # Group by base name
                if base_name not in all_imported_objects:
                    all_imported_objects[base_name] = []
                
                all_imported_objects[base_name].append({
                    'fbx_file': fbx_file,
                    'objects': imported_objects
                })
                
                imported_count += 1
                print(f"  ✅ Imported {len(imported_objects)} object(s) from: {fbx_file.name} (base name: {base_name})")
                
                # Restore previous selection
                bpy.ops.object.select_all(action='DESELECT')
                for obj in selected_objects:
                    obj.select_set(True)
                if active_object:
                    context.view_layer.objects.active = active_object
                    
            except Exception as e:
                print(f"  ❌ Failed to import {fbx_file.name}: {e}")
        
        # Now create world roots and parent objects based on the actual imported object names
        for base_name, import_groups in all_imported_objects.items():
            # Try to get the proper name from JSON file (for 3D models)
            json_name, json_file = self._get_name_from_json(asset_dir)
            if json_name:
                # Use JSON-based name for world root instead of base_name
                world_root_base_name = json_name
                print(f"  📋 Using JSON name for world root: {world_root_base_name}")
            else:
                # Fallback to base_name with quixel_ prefix
                world_root_base_name = f"quixel_{base_name}"
            
            # First, collect all objects from all LOD imports for this asset
            all_objects_to_parent = []
            detected_scale = None
            detected_rotation = None
            
            # Process all LOD imports to collect objects and detect scale/rotation
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
                
                # Detect rotation from old world roots before removing them
                # The old world roots typically have the correct rotation (e.g., X rotation of 90)
                for old_root in old_world_roots:
                    # Get the rotation from the old world root
                    rotation_euler = old_root.rotation_euler
                    if detected_rotation is None:
                        detected_rotation = rotation_euler.copy()
                        print(f"  🔄 Detected rotation from old world root: X={math.degrees(rotation_euler.x):.1f}°, Y={math.degrees(rotation_euler.y):.1f}°, Z={math.degrees(rotation_euler.z):.1f}°")
                    break  # Use the first old world root's rotation
                
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
                
                # Collect all children of old world roots before removing them
                children_to_reparent = []
                for old_root in old_world_roots:
                    children_to_reparent.extend(old_root.children)
                    # Unparent children before deleting the old root
                    for child in old_root.children:
                        child.parent = None
                
                # Remove old world root objects
                for old_root in old_world_roots:
                    bpy.data.objects.remove(old_root, do_unlink=True)
                    imported_objects.remove(old_root)
                
                # Add the children to our list of objects to parent
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
                
                all_objects_to_parent.extend(imported_objects)
                
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
            
            # Create a single world root (empty object) for this asset
            # Use the JSON-based name if available, otherwise use base_name with quixel_ prefix
            world_root_name = world_root_base_name
            world_root = bpy.data.objects.new(world_root_name, None)
            world_root.empty_display_type = 'ARROWS'
            world_root.empty_display_size = 1.0
            # Set the world root scale to the detected scale
            world_root.scale = (detected_scale, detected_scale, detected_scale)
            # Set the world root rotation to the detected rotation
            world_root.rotation_euler = detected_rotation
            context.collection.objects.link(world_root)
            
            print(f"📦 Created world root: {world_root_name} with scale {detected_scale} and rotation X={math.degrees(detected_rotation.x):.1f}°")
            
            # Now parent all objects to the world root
            # Strategy: Apply scale to objects first (bake into mesh), then parent
            # This way objects have scale (1,1,1) and the world root's scale controls the final size
            
            # Apply scale and reset rotation for all objects before parenting
            # This ensures objects have scale (1,1,1) and rotation (0,0,0) relative to world root
            for obj in all_objects_to_parent:
                # Store world matrix to preserve position
                world_matrix = obj.matrix_world.copy()
                
                # Apply scale - this bakes scale into mesh and sets object scale to (1,1,1)
                obj.select_set(True)
                context.view_layer.objects.active = obj
                bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
                obj.select_set(False)
                
                # Reset rotation to (0,0,0) - the world root will have the rotation
                # We need to adjust the location to compensate for rotation change
                obj.rotation_euler = (0.0, 0.0, 0.0)
                
                # Restore world position (rotation reset might have changed it)
                # Calculate what the location should be to maintain world position
                obj.location = world_matrix.translation
            
            # Clear selection
            bpy.ops.object.select_all(action='DESELECT')
            
            # Now parent all objects - Blender will automatically preserve world transforms
            for obj in all_objects_to_parent:
                obj.parent = world_root
            
            print(f"  ✅ Parented {len(all_objects_to_parent)} object(s) to world root")
            
            # Create materials and assign textures for each LOD level
            self._create_materials_for_asset(asset_dir, base_name, world_root_name, import_groups, all_objects_to_parent, context)
            
            # Set the world root as active and selected for convenience
            bpy.ops.object.select_all(action='DESELECT')
            world_root.select_set(True)
            context.view_layer.objects.active = world_root

        if imported_count > 0:
            self.report({'INFO'}, f"Imported {imported_count} FBX file(s) into {len(all_imported_objects)} asset group(s)")

            # Notify Electron that import is complete
            self._notify_import_complete(asset_dir)

            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Failed to import any FBX files")
            return {'CANCELLED'}

    def _notify_import_complete(self, asset_dir):
        """Write completion file to notify Electron app"""
        import tempfile
        try:
            temp_dir = Path(tempfile.gettempdir()) / "quixel_portal"
            completion_file = temp_dir / "import_complete.json"

            # Use thumbnail path from property if provided, otherwise fallback to searching
            thumbnail_path = self.thumbnail_path if self.thumbnail_path else None

            # Use asset name override if provided, otherwise get from JSON
            asset_name = self.asset_name_override if self.asset_name_override else None
            if not asset_name:
                asset_name = asset_dir.name
                json_name, _ = self._get_name_from_json(asset_dir)
                if json_name:
                    asset_name = json_name

            completion_data = {
                "asset_path": str(asset_dir),
                "asset_name": asset_name,
                "thumbnail": thumbnail_path,
                "timestamp": bpy.context.scene.frame_current  # Use frame as simple timestamp
            }

            with open(completion_file, 'w') as f:
                json.dump(completion_data, f, indent=2)

            print(f"✅ Quixel Portal: Notified Electron of import completion")
            print(f"   Asset: {asset_name}")
            print(f"   Thumbnail: {thumbnail_path}")
        except Exception as e:
            print(f"⚠️ Quixel Portal: Failed to notify import completion: {e}")


def check_import_requests():
    """Background timer function to check for import requests from Electron"""
    # Get the temp directory for communication
    import tempfile
    temp_dir = Path(tempfile.gettempdir()) / "quixel_portal"
    request_file = temp_dir / "import_request.json"

    if request_file.exists():
        try:
            # Read the import request
            with open(request_file, 'r') as f:
                request_data = json.load(f)

            asset_path = request_data.get('asset_path')
            thumbnail_path = request_data.get('thumbnail')
            asset_name = request_data.get('asset_name')

            print(f"📥 Quixel Portal: Import request received:")
            print(f"   Asset path: {asset_path}")
            print(f"   Thumbnail: {thumbnail_path}")
            print(f"   Asset name: {asset_name}")

            if asset_path and Path(asset_path).exists():
                # Import the asset
                bpy.ops.quixel.import_fbx(
                    directory=asset_path,
                    thumbnail_path=thumbnail_path or '',
                    asset_name_override=asset_name or ''
                )
                print(f"📥 Quixel Portal: Auto-imported asset from {asset_path}")

            # Delete the request file after processing
            request_file.unlink()

        except Exception as e:
            print(f"❌ Quixel Portal: Error processing import request: {e}")
            # Try to delete the file anyway to prevent repeated errors
            try:
                request_file.unlink()
            except:
                pass

    # Continue the timer
    return 1.0  # Check every 1 second


def _is_already_registered():
    """Check if our draw function is already registered by checking a persistent marker"""
    # Store a marker on the header type itself to track registration
    # This marker persists across module reloads (as long as Blender is running)
    marker_name = '_quixel_portal_button_registered'
    
    try:
        # Check if we've set a marker indicating registration
        if hasattr(bpy.types.TOPBAR_HT_upper_bar, marker_name):
            return getattr(bpy.types.TOPBAR_HT_upper_bar, marker_name) == True
    except:
        pass
    
    return False


def _mark_as_registered(registered=True):
    """Mark the header type to indicate our function is registered"""
    marker_name = '_quixel_portal_button_registered'
    try:
        setattr(bpy.types.TOPBAR_HT_upper_bar, marker_name, registered)
    except:
        pass


def register():
    global custom_icons, _draw_function_registered, _import_timer

    # Register custom icons
    custom_icons = bpy.utils.previews.new()

    # Load the Quixel logo icon
    addon_dir = Path(__file__).parent
    icon_path = addon_dir / "electron_app" / "assets" / "icons" / "logo_48.png"

    if icon_path.exists():
        try:
            custom_icons.load("quixel_logo", str(icon_path), 'IMAGE')
            # Verify the icon was loaded successfully
            if "quixel_logo" in custom_icons:
                icon_item = custom_icons["quixel_logo"]
                if hasattr(icon_item, 'icon_id'):
                    print(f"✅ Quixel Portal: Icon loaded successfully from {icon_path} (ID: {icon_item.icon_id})")
                else:
                    print(f"⚠️ Quixel Portal: Icon loaded but icon_id not available")
            else:
                print(f"⚠️ Quixel Portal: Icon load failed - not in collection")
        except Exception as e:
            print(f"⚠️ Quixel Portal: Error loading icon: {e}")
    else:
        print(f"⚠️ Quixel Portal: Icon not found at {icon_path}")

    # Register the operators
    bpy.utils.register_class(QUIXEL_OT_open_portal)
    bpy.utils.register_class(QUIXEL_OT_import_fbx)

    # Register draw function to topbar
    # Use a persistent marker on the header type to track registration across module reloads
    # This marker persists as long as Blender is running, even if the module reloads

    # Check if already registered using the persistent marker
    if not _is_already_registered() and not _draw_function_registered:
        try:
            bpy.types.TOPBAR_HT_upper_bar.append(draw_quixel_button)
            _draw_function_registered = True
            _mark_as_registered(True)
            print("✅ Quixel Portal: Button added to topbar")
        except Exception as e:
            print(f"⚠️ Quixel Portal: Error adding button to topbar: {e}")
    else:
        if _is_already_registered():
            # If marker says registered but our flag doesn't, sync the flag
            _draw_function_registered = True
            print("ℹ️ Quixel Portal: Button already registered (detected from previous session)")
        else:
            print("ℹ️ Quixel Portal: Button already registered in this session (skipping)")

    # Start the background timer to check for import requests
    if not bpy.app.timers.is_registered(check_import_requests):
        bpy.app.timers.register(check_import_requests)
        print("✅ Quixel Portal: Import request monitor started")


def unregister():
    global custom_icons, _draw_function_registered, _import_timer

    # Stop the background timer
    if bpy.app.timers.is_registered(check_import_requests):
        bpy.app.timers.unregister(check_import_requests)
        print("✅ Quixel Portal: Import request monitor stopped")

    # Remove draw function from topbar
    # Check both the session flag and the persistent marker
    if _draw_function_registered or _is_already_registered():
        try:
            bpy.types.TOPBAR_HT_upper_bar.remove(draw_quixel_button)
            _draw_function_registered = False
            _mark_as_registered(False)
        except:
            # If removal fails (e.g., function wasn't actually registered or was already removed),
            # reset both flags anyway
            _draw_function_registered = False
            _mark_as_registered(False)

    # Unregister the operators
    try:
        bpy.utils.unregister_class(QUIXEL_OT_open_portal)
    except:
        pass

    try:
        bpy.utils.unregister_class(QUIXEL_OT_import_fbx)
    except:
        pass

    # Remove custom icons
    if custom_icons:
        try:
            bpy.utils.previews.remove(custom_icons)
            custom_icons = None
        except:
            pass

    print("✅ Quixel Portal: Addon unregistered")


if __name__ == "__main__":
    register()
