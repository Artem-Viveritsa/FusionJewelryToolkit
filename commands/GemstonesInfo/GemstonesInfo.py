import os
import traceback

import adsk.core
import adsk.fusion

from ... import strings
from ...helpers import Gemstones
from ...helpers.Gemstones import isGemstone
from ...helpers.showMessage import showMessage


_app: adsk.core.Application = None
_ui: adsk.core.UserInterface = None
_handlers: list = []

_gemstonesSelectionInput: adsk.core.SelectionCommandInput = None
_infoTextInput: adsk.core.TextBoxCommandInput = None

COMMAND_ID: str = strings.PREFIX + strings.GEMSTONES_INFO
RESOURCES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')


def run(panel: adsk.core.ToolbarPanel) -> None:
    try:
        global _app, _ui
        _app = adsk.core.Application.get()
        _ui = _app.userInterface

        cmdDef = _ui.commandDefinitions.itemById(COMMAND_ID)
        if not cmdDef:
            cmdDef = _ui.commandDefinitions.addButtonDefinition(
                COMMAND_ID, 'Gemstones Info', 'Show info about gemstones', RESOURCES_FOLDER
            )

        control = panel.controls.addCommand(cmdDef, '', False)
        control.isPromoted = True

        onCommandCreated = CommandCreatedHandler()
        cmdDef.commandCreated.add(onCommandCreated)
        _handlers.append(onCommandCreated)

    except:
        showMessage(f'Failed:\n{traceback.format_exc()}', True)


def stop(panel: adsk.core.ToolbarPanel) -> None:
    try:
        control = panel.controls.itemById(COMMAND_ID)
        if control:
            control.deleteMe()

        commandDefinition = _ui.commandDefinitions.itemById(COMMAND_ID)
        if commandDefinition:
            commandDefinition.deleteMe()
    except:
        showMessage(f'Stop Failed:\n{traceback.format_exc()}', True)


class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args: adsk.core.CommandCreatedEventArgs) -> None:
        try:
            global _gemstonesSelectionInput, _infoTextInput

            cmd = args.command
            inputs = cmd.commandInputs

            handlers = [
                (cmd.preSelect, PreSelectHandler()),
                (cmd.executePreview, ExecutePreviewHandler()),
                (cmd.destroy, CommandDestroyHandler()),
            ]
            for event, handler in handlers:
                event.add(handler)
                _handlers.append(handler)

            _gemstonesSelectionInput = inputs.addSelectionInput(
                'selectGemstones', 'Select Gemstones',
                'Select gemstones to show info (leave empty to show all)'
            )
            _gemstonesSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Bodies)
            _gemstonesSelectionInput.setSelectionLimits(0)

            inputs.addSeparatorCommandInput('separatorAfterSelection')

            _infoTextInput = inputs.addTextBoxCommandInput('info', 'Info', '', 1, True)

            updateGemstonesDisplay()

        except:
            showMessage(f'Failed:\n{traceback.format_exc()}', True)


class ExecutePreviewHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args: adsk.core.CommandEventArgs) -> None:
        try:
            updateGemstonesDisplay()
        except:
            showMessage(f'ExecutePreviewHandler Failed:\n{traceback.format_exc()}', True)


class PreSelectHandler(adsk.core.SelectionEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args: adsk.core.SelectionEventArgs) -> None:
        try:
            entity = args.selection.entity

            if entity.objectType != adsk.fusion.BRepBody.classType():
                return

            body: adsk.fusion.BRepBody = entity

            if body.assemblyContext and body.assemblyContext.isReferencedComponent:
                args.isSelectable = False
                return

            if not isGemstone(body):
                args.isSelectable = False

        except:
            showMessage(f'PreSelectHandler Failed:\n{traceback.format_exc()}', True)


class CommandDestroyHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args: adsk.core.CommandEventArgs) -> None:
        try:
            global _gemstonesSelectionInput, _infoTextInput

            clearCustomGraphics()

            _gemstonesSelectionInput = None
            _infoTextInput = None

        except:
            showMessage(f'Failed:\n{traceback.format_exc()}', True)


def collectGemstoneInfos() -> list[Gemstones.GemstoneInfo]:
    """Collect gemstone infos from selection or all visible gemstones."""
    global _gemstonesSelectionInput, _app

    if _gemstonesSelectionInput and _gemstonesSelectionInput.selectionCount > 0:
        return [
            Gemstones.GemstoneInfo(adsk.fusion.BRepBody.cast(
                _gemstonesSelectionInput.selection(i).entity
            ))
            for i in range(_gemstonesSelectionInput.selectionCount)
            if isGemstone(_gemstonesSelectionInput.selection(i).entity)
        ]

    design = adsk.fusion.Design.cast(_app.activeProduct)
    if not design:
        return []

    gemstoneInfos: list[Gemstones.GemstoneInfo] = []
    root = design.rootComponent

    for body in root.bRepBodies:
        if body.isLightBulbOn and isGemstone(body):
            gemstoneInfos.append(Gemstones.GemstoneInfo(body))

    for occ in root.allOccurrences:
        if occ.isLightBulbOn:
            for body in occ.bRepBodies:
                if body.isLightBulbOn and isGemstone(body):
                    gemstoneInfos.append(Gemstones.GemstoneInfo(body))

    return gemstoneInfos


def formatGemstonesText(gemstoneInfos: list[Gemstones.GemstoneInfo]) -> tuple[str, int]:
    """Format gemstones info as text for display.

    Returns:
        Tuple of (formatted text, number of rows).
    """
    if not gemstoneInfos:
        return 'No gemstones found', 2

    gemstoneDict: dict[float, int] = {}
    for gemInfo in gemstoneInfos:
        diameterMm = round(gemInfo.diameter * 10, 2)
        gemstoneDict[diameterMm] = gemstoneDict.get(diameterMm, 0) + 1

    sortedItems = sorted(gemstoneDict.items(), key=lambda x: x[0])
    text = ''.join([f"<b>{diameter:.2f}</b> – {count}<br>" for diameter, count in sortedItems])

    return text, len(sortedItems) + 1


def updateGemstonesDisplay() -> None:
    """Update gemstones data, info display, and custom graphics."""
    global _infoTextInput

    gemstoneInfos = collectGemstoneInfos()

    text, numRows = formatGemstonesText(gemstoneInfos)
    if _infoTextInput:
        _infoTextInput.formattedText = text
        _infoTextInput.numRows = numRows

    updateCustomGraphics(gemstoneInfos)


def clearCustomGraphics() -> None:
    """Clear all custom graphics groups from the design."""
    global _app

    design = adsk.fusion.Design.cast(_app.activeProduct)
    if not design:
        return

    groups = design.rootComponent.customGraphicsGroups
    for i in range(groups.count - 1, -1, -1):
        try:
            groups.item(i).deleteMe()
        except:
            pass


def updateCustomGraphics(gemstoneInfos: list[Gemstones.GemstoneInfo]) -> None:
    """Update custom graphics overlay for gemstones."""
    global _app

    design = adsk.fusion.Design.cast(_app.activeProduct)
    if not design:
        return

    clearCustomGraphics()

    if not gemstoneInfos:
        return

    cgGroup = design.rootComponent.customGraphicsGroups.add()
    solidColor = adsk.fusion.CustomGraphicsSolidColorEffect.create(
        adsk.core.Color.create(0, 0, 0, 255)
    )

    for gemInfo in gemstoneInfos:
        centroid = gemInfo.centroid.copy()

        normalOffset = gemInfo.getNormalizedNormal()
        normalOffset.scaleBy(gemInfo.radius)
        centroid.translateBy(normalOffset)

        transform = adsk.core.Matrix3D.create()
        transform.translation = centroid.asVector()

        cgText = cgGroup.addText(f"{gemInfo.diameter * 10:.2f}", 'Arial', 0.03, transform)
        cgText.billBoarding = adsk.fusion.CustomGraphicsBillBoard.create(None)
        cgText.color = solidColor

