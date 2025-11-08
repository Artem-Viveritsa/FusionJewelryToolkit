import adsk

_ui  = adsk.core.Application.get().userInterface

def showMessage(message, error = False):
    """Displays a message to the user.
    
    Shows the message in the text command palette and optionally in a message box.
    
    Args:
        message: The message text to display
        error: If True, shows the message as an error in a message box
    """
    textPalette: adsk.core.TextCommandPalette = _ui.palettes.itemById('TextCommands')
    textPalette.writeText(message)

    if error:
        _ui.messageBox(f"Error: {message}")
    else:
        _ui.messageBox(message)