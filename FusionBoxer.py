import adsk.core
import traceback


try:
    from . import config
    from .apper import apper

    from .commands.OffsetBoundingBoxCommand import OffsetBoundingBoxCommand

    # Create our addin definition object
    my_addin = apper.FusionApp(config.app_name, config.company_name, False)
    my_addin.root_path = config.app_path

    my_addin.add_command(
        'Offset Bounding Box',
        OffsetBoundingBoxCommand,
        {
            'cmd_description': 'Create a bounding box feature with custom offsets',
            'cmd_id': 'offset_b_box',
            'workspace': 'FusionSolidEnvironment',
            'toolbar_panel_id': 'Commands',
            'cmd_resources': 'command_icons',
            'command_visible': True,
            'command_promoted': True,
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
    cleanup_app(__file__)
