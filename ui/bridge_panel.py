"""Bridge Panel - Permanent UI panel in 3D viewport sidebar.

This module provides a permanent panel in the Blender 3D viewport N-panel
for launching Quixel Bridge and managing multi-instance coordination.
"""

import bpy


class QUIXEL_PT_bridge_panel(bpy.types.Panel):
    """Quixel Bridge panel in the 3D viewport sidebar"""

    bl_label = "Quixel Bridge"
    bl_idname = "QUIXEL_PT_bridge_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Quixel'  # Tab name in N-panel

    def draw(self, context):
        layout = self.layout

        # Bridge launcher section
        box = layout.box()
        box.label(text="Multi-Instance Control", icon='WORLD')

        # Bridge button (large and prominent)
        row = box.row()
        row.scale_y = 2.0  # Make button taller

        # Use custom icon if available
        from ..utils import icon_loader
        bridge_icon = icon_loader.get_icon_id("bridge_24")
        if bridge_icon:
            row.operator("quixel.launch_bridge", text="Launch Bridge & Claim Active", icon_value=bridge_icon)
        else:
            row.operator("quixel.launch_bridge", text="Launch Bridge & Claim Active", icon='PLAY')

        # Status information
        box.separator()

        # Get coordinator status
        try:
            from ..communication.bridge_coordinator import get_coordinator

            coordinator = get_coordinator()

            if coordinator:
                # Show mode (Hub or Client)
                row = box.row()
                if coordinator.mode == 'hub':
                    row.label(text="Mode: Hub (Primary)", icon='STICKY_UVS_LOC')
                elif coordinator.mode == 'client':
                    row.label(text="Mode: Client (Secondary)", icon='CONSTRAINT')
                else:
                    row.label(text="Mode: Unknown", icon='ERROR')

                # Show active status
                row = box.row()
                if coordinator.is_active():
                    row.label(text="Status: Active (Receiving Imports)", icon='CHECKMARK')
                else:
                    row.label(text="Status: Inactive", icon='BLANK1')

                # Show instance info
                instance_name = coordinator._get_instance_name()
                row = box.row()
                row.label(text=f"Instance: {instance_name}", icon='BLENDER')

            else:
                row = box.row()
                row.label(text="Coordinator not initialized", icon='ERROR')

        except Exception as e:
            row = box.row()
            row.label(text=f"Error: {str(e)}", icon='ERROR')

        # Import section
        layout.separator()
        box = layout.box()
        box.label(text="Manual Import", icon='IMPORT')

        # Manual FBX import button
        row = box.row()
        row.operator("quixel.import_fbx", text="Import FBX Manually", icon='MESH_DATA')

        # Help section
        layout.separator()
        box = layout.box()
        box.label(text="How It Works", icon='QUESTION')

        col = box.column(align=True)
        col.scale_y = 0.8
        col.label(text="1. Click 'Launch Bridge & Claim Active'")
        col.label(text="2. This instance receives Bridge imports")
        col.label(text="3. Export from Quixel Bridge")
        col.label(text="4. Assets appear in this Blender")


def register():
    """Register the panel."""
    bpy.utils.register_class(QUIXEL_PT_bridge_panel)


def unregister():
    """Unregister the panel."""
    try:
        bpy.utils.unregister_class(QUIXEL_PT_bridge_panel)
    except:
        pass
