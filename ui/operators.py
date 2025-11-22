"""Blender operators for Quixel Portal addon.

These operators serve as thin wrappers around the main application flow,
providing the Blender UI interface while delegating actual work to the
main module.
"""

import bpy
from pathlib import Path

from ..main import open_quixel_portal, import_asset
from ..communication.electron_bridge import get_temp_dir


class QUIXEL_OT_cleanup_requests(bpy.types.Operator):
    """Force cleanup of stuck import request files"""
    bl_idname = "quixel.cleanup_requests"
    bl_label = "Clear Stuck Import Requests"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            temp_dir = get_temp_dir()
            request_file = temp_dir / "import_request.json"

            if request_file.exists():
                request_file.unlink()
                self.report({'INFO'}, "✅ Deleted stuck import request file")
                print(f"✅ Quixel Portal: Manually deleted import request file")
            else:
                self.report({'INFO'}, "No stuck request files found")
                print(f"ℹ️  Quixel Portal: No import request file found")

        except Exception as e:
            self.report({'ERROR'}, f"Failed to cleanup: {e}")
            print(f"❌ Quixel Portal: Manual cleanup failed: {e}")

        return {'FINISHED'}


class QUIXEL_OT_open_portal(bpy.types.Operator):
    """Open Quixel Portal in dedicated browser"""
    bl_idname = "quixel.open_portal"
    bl_label = "Open Quixel Portal"
    bl_options = {'REGISTER'}

    def execute(self, context):
        """Execute the open portal operation."""
        result = open_quixel_portal(context)
        
        if result == {'FINISHED'}:
            self.report({'INFO'}, "Quixel Portal launched!")
        elif result == {'CANCELLED'}:
            # Error message already reported by open_quixel_portal
            pass
        
        return result


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
    
    def execute(self, context):
        """Execute the import operation."""
        asset_path = self.directory
        thumbnail_path = self.thumbnail_path if self.thumbnail_path else None
        asset_name = self.asset_name_override if self.asset_name_override else None
        
        result = import_asset(
            asset_path=asset_path,
            thumbnail_path=thumbnail_path,
            asset_name=asset_name
        )
        
        if result == {'FINISHED'}:
            asset_dir = Path(asset_path)
            self.report({'INFO'}, f"Asset imported from {asset_dir.name}")
        elif result == {'CANCELLED'}:
            self.report({'ERROR'}, "Import failed")
        
        return result

