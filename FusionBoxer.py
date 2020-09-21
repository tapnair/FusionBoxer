import adsk.core
import traceback

from.startup import setup_app, cleanup_app, get_app_path
setup_app(__file__)

try:
    import config
    import apper

    # Basic Fusion 360 Command Base samples
    from commands.SampleCommand1 import SampleCommand1
    from commands.SampleCommand2 import SampleCommand2

    # Palette Command Base samples
    from commands.SamplePaletteCommand import SamplePaletteSendCommand, SamplePaletteShowCommand

    # Various Application event samples
    from commands.SampleCustomEvent import SampleCustomEvent
    from commands.SampleDocumentEvents import SampleDocumentEvent1, SampleDocumentEvent2
    from commands.SampleWorkspaceEvents import SampleWorkspaceEvent
    from commands.SampleWebRequestEvent import SampleWebRequestOpened
    from commands.SampleCommandEvents import SampleCommandEvent
    from commands.SampleActiveSelectionEvents import SampleActiveSelectionEvent


# Create our addin definition object
    my_addin = apper.FusionApp(config.app_name, config.company_name, False)
    my_addin.root_path = get_app_path(__file__)

    # Creates a basic Hello World message box on execute
    my_addin.add_command(
        'Sample Command 1',
        SampleCommand1,
        {
            'cmd_description': 'Hello World!',
            'cmd_id': 'sample_cmd_1',
            'workspace': 'FusionSolidEnvironment',
            'toolbar_panel_id': 'Commands',
            'cmd_resources': 'command_icons',
            'command_visible': True,
            'command_promoted': True,
        }
    )

    # General command showing inputs and user interaction
    my_addin.add_command(
        'Sample Command 2',
        SampleCommand2,
        {
            'cmd_description': 'A simple example of a Fusion 360 Command with various inputs',
            'cmd_id': 'sample_cmd_2',
            'workspace': 'FusionSolidEnvironment',
            'toolbar_panel_id': 'Commands',
            'cmd_resources': 'command_icons',
            'command_visible': True,
            'command_promoted': False,
        }
    )

    # Create an html palette to as an alternative UI
    my_addin.add_command(
        'Sample Palette Command - Show',
        SamplePaletteShowCommand,
        {
            'cmd_description': 'Shows the Fusion 360 Demo Palette',
            'cmd_id': 'sample_palette_show',
            'workspace': 'FusionSolidEnvironment',
            'toolbar_panel_id': 'Palette',
            'cmd_resources': 'palette_icons',
            'command_visible': True,
            'command_promoted': True,
            'palette_id': 'sample_palette',
            'palette_name': 'Sample Fusion 360 HTML Palette',
            'palette_html_file_url': 'commands/palette_html/FusionBoxer.html',
            'palette_use_new_browser': True,
            'palette_is_visible': True,
            'palette_show_close_button': True,
            'palette_is_resizable': True,
            'palette_width': 500,
            'palette_height': 600,
        }
    )

    # Send data from Fusion 360 to the palette
    my_addin.add_command(
        'Send Info to Palette',
        SamplePaletteSendCommand,
        {
            'cmd_description': 'Send data from a regular Fusion 360 command to a palette',
            'cmd_id': 'sample_palette_send',
            'workspace': 'FusionSolidEnvironment',
            'toolbar_panel_id': 'Palette',
            'cmd_resources': 'palette_icons',
            'command_visible': True,
            'command_promoted': False,
            'palette_id': 'sample_palette',
        }
    )

    app = adsk.core.Application.cast(adsk.core.Application.get())
    ui = app.userInterface

    # Uncomment as necessary.  Running all at once can be overwhelming :)
    # my_addin.add_custom_event("FusionBoxer_message_system", SampleCustomEvent1)

    # my_addin.add_document_event("FusionBoxer_open_event", app.documentActivated, SampleDocumentEvent1)
    # my_addin.add_document_event("FusionBoxer_close_event", app.documentClosed, SampleDocumentEvent2)

    # my_addin.add_workspace_event("FusionBoxer_workspace_event", ui.workspaceActivated, SampleWorkspaceEvent1)

    # my_addin.add_web_request_event("FusionBoxer_web_request_event", app.openedFromURL, SampleWebRequestOpened)

    # my_addin.add_command_event("FusionBoxer_command_event", app.userInterface.commandStarting, SampleCommandEvent)

    # my_addin.add_command_event("FusionBoxer_active_selection_event", ui.activeSelectionChanged, SampleActiveSelectionEvent)

except:
    app = adsk.core.Application.get()
    ui = app.userInterface
    if ui:
        ui.messageBox('Initialization: {}'.format(traceback.format_exc()))

# Set to True to display various useful messages when debugging your app
debug = False


def run(context):
    my_addin.run_app()


def stop(context):
    my_addin.stop_app()
    cleanup_app(__file__)
