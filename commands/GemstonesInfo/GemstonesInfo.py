import json
import os
import traceback

import adsk.core
import adsk.fusion

from ... import strings
from ...helpers import Gemstones
from ...helpers.showMessage import showMessage

_app: adsk.core.Application = None
_ui: adsk.core.UserInterface = None
_handlers: list = []
_cgGroup: adsk.fusion.CustomGraphicsGroup = None
_gemstonesList: list[tuple[float, int]] = []

COMMAND_ID: str = strings.PREFIX + strings.GEMSTONES_INFO

RESOURCES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

def run(panel: adsk.core.ToolbarPanel) -> None:
    try:
        global _app, _ui
        _app = adsk.core.Application.get()
        _ui  = _app.userInterface

        cmdDef = _ui.commandDefinitions.itemById(COMMAND_ID)
        if not cmdDef:
            cmdDef = _ui.commandDefinitions.addButtonDefinition(COMMAND_ID, 'Gemstones Info', 'Show info about gemstones', RESOURCES_FOLDER)

        control = panel.controls.addCommand(cmdDef, '', False)
        control.isPromoted = True

        onCommandCreated = CommandCreatedHandler()
        cmdDef.commandCreated.add(onCommandCreated)
        _handlers.append(onCommandCreated)

    except:
        showMessage('Failed:\n{}'.format(traceback.format_exc()), True)

def stop(panel: adsk.core.ToolbarPanel) -> None:
    try:
        control = panel.controls.itemById(COMMAND_ID)
        if control:
            control.deleteMe()
            
        commandDefinition = _ui.commandDefinitions.itemById(COMMAND_ID)
        if commandDefinition:
            commandDefinition.deleteMe()
    except:
        showMessage('Stop Failed:\n{}'.format(traceback.format_exc()), True)

class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args) -> None:
        try:
            args = adsk.core.CommandCreatedEventArgs.cast(args)
            
            cmd = args.command
            onDestroy = CommandDestroyHandler()
            cmd.destroy.add(onDestroy)
            _handlers.append(onDestroy)

            showGemstonesInfo()
            
            inputs = cmd.commandInputs
            gemstoneText = '\n'.join([f"<b>{diameter:.2f}</b> – {count}<br>" for diameter, count in _gemstonesList]) if _gemstonesList else 'No gemstones found'
            numRows = max(len(_gemstonesList), 1)
            inputs.addTextBoxCommandInput('info', 'Info', gemstoneText, numRows, True)
            
        except:
            showMessage('Failed:\n{}'.format(traceback.format_exc()), True)
            
class CommandDestroyHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args) -> None:
        try:
            global _cgGroup
            if _cgGroup:
                _cgGroup.deleteMe()
                _cgGroup = None
                
            _handlers.pop()
            
        except:
            showMessage('Failed:\n{}'.format(traceback.format_exc()), True)


def showGemstonesInfo() -> None:
    """Search for gemstone bodies and display their diameter as overlay text.

    Bodies are detected as gemstones by reading the JSON stored under the
    attribute key (`strings.PREFIX`, `strings.PROPERTIES`). For each detected
    gemstone the function computes a position slightly offset along the
    gemstone's normal and adds a Custom Graphics text label showing the
    diameter.
    """

    global _cgGroup, _app, _gemstonesList
    
    design = adsk.fusion.Design.cast(_app.activeProduct)

    if not _cgGroup: _cgGroup = design.rootComponent.customGraphicsGroups.add()

    def is_gemstone(body: adsk.fusion.BRepBody) -> bool:
        attr = body.attributes.itemByName(strings.PREFIX, strings.PROPERTIES)
        if attr:
            try:
                props = json.loads(attr.value)
                if props.get(strings.ENTITY) == strings.GEMSTONE:
                    return True
            except:
                pass
        return False

    gemstoneInfos: list[Gemstones.GemstoneInfo] = []
    if design:
        root = design.rootComponent
        for body in root.bRepBodies:
            if body.isLightBulbOn and is_gemstone(body):
                gemInfo = Gemstones.GemstoneInfo(body)
                gemstoneInfos.append(gemInfo)
        
        for occ in root.allOccurrences:
            if occ.isLightBulbOn:
                for body in occ.bRepBodies:
                    if body.isLightBulbOn and is_gemstone(body):
                        gemInfo = Gemstones.GemstoneInfo(body)
                        gemstoneInfos.append(gemInfo)
    
    gemstoneDict: dict[float, int] = {}
    for gemInfo in gemstoneInfos:
        diameterMm = round(gemInfo.diameter * 10, 2)
        gemstoneDict[diameterMm] = gemstoneDict.get(diameterMm, 0) + 1
    
    sorted_items = sorted(gemstoneDict.items(), key=lambda x: x[0])
    _gemstonesList = [(diameter, count) for diameter, count in sorted_items]
    
    if not gemstoneInfos:
        return

    try:
        for gemInfo in gemstoneInfos:
            centroid = gemInfo.centroid.copy()
            
            text = f"{gemInfo.diameter * 10:.2f}" # in mm

            normalOffset = gemInfo.getNormalizedNormal()
            normalOffset.scaleBy(gemInfo.radius)
            centroid.translateBy(normalOffset)
            
            transform = adsk.core.Matrix3D.create()
            transform.translation = centroid.asVector()
            
            cgText = _cgGroup.addText(text, 'Arial', 0.03, transform)
                        
            cgText.billBoarding = adsk.fusion.CustomGraphicsBillBoard.create(centroid)
            
            solidColor = adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(0, 0, 0, 255))
            cgText.color = solidColor
            
    except Exception as e:
        showMessage(f'Error processing gemstone: {str(e)}\n', False)

