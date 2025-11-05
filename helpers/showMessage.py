import adsk

_ui  = adsk.core.Application.get().userInterface

def showMessage(message, error = False):
    textPalette: adsk.core.TextCommandPalette = _ui.palettes.itemById('TextCommands')
    textPalette.writeText(message)

    if error:
        _ui.messageBox(f"Error: {message}")
    else:
        _ui.messageBox(message)