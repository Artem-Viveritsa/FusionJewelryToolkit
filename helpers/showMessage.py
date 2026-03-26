import adsk.core

_ui = adsk.core.Application.get().userInterface


def showConfirmationDialog(message: str, title: str = '') -> bool:
    """Display a Yes/No confirmation dialog and return True if user confirms."""
    result = _ui.messageBox(
        message, title,
        adsk.core.MessageBoxButtonTypes.YesNoButtonType,
        adsk.core.MessageBoxIconTypes.QuestionIconType
    )
    return result == adsk.core.DialogResults.DialogYes


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