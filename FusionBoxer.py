import adsk.core
import traceback


try:
    from . import config
    from .apper import apper

    from .commands.OffsetBoundingBoxCommand import OffsetBoundingBoxCommand, BoxCustomFeature

    # Create our addin definition object
    my_addin = apper.FusionApp(config.app_name, config.company_name, False)
    my_addin.root_path = config.app_path

    my_addin.add_command(
        'Cage',
        OffsetBoundingBoxCommand,
        {
            'cmd_description': 'Cage Generator for 3D Printing with MJF and SLS',
            'cmd_id': 'offset_b_box',
            'workspace': 'FusionSolidEnvironment',
            'toolbar_panel_id': 'Commands',
            'cmd_resources': 'command_icons',
            'command_visible': True,
            'command_promoted': True,
            'create_feature': True,
        }
    )

    my_addin.add_command(
        'Edit Cage',
        OffsetBoundingBoxCommand,
        {
            'cmd_description': 'Cage Generator for 3D Printing with MJF and SLS',
            'cmd_id': 'offset_b_box_edit',
            'workspace': 'FusionSolidEnvironment',
            'toolbar_panel_id': 'Commands',
            'cmd_resources': 'command_icons',
            'command_visible': False,
            'command_promoted': False,
            'create_feature': False,
        }
    )

    my_addin.add_custom_feature(
        'Cage',
        BoxCustomFeature,
        {
            'feature_id': 'offset_b_box_custom_feature',
            'edit_cmd_id': 'offset_b_box_edit',
            'feature_icons': 'command_icons',
            'roll_timeline': True,
        }
    )

except:
    app = adsk.core.Application.get()
    ui = app.userInterface
    if ui:
        ui.messageBox('Initialization: {}'.format(traceback.format_exc()))


def run(context):
    my_addin.run_app()


def stop(context):
    my_addin.stop_app()
