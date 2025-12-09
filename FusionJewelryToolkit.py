import adsk.core, adsk.fusion
from .commands.GemstonesOnFaceAtPoints import GemstonesOnFaceAtPoints
from .commands.GemstonesOnFaceAtCircles import GemstonesOnFaceAtCircles
from .commands.GemstonesOnFaceAtCurve import GemstonesOnFaceAtCurve
from .commands.GemstonesOnFaceBetweenCurves import GemstonesOnFaceBetweenCurves

from .commands.ProngsOnFaceAtPoints import ProngsOnFaceAtPoints
from .commands.ProngsBetweenGemstones import ProngsBetweenGemstones

from .commands.ChannelsBetweenGemstones import ChannelsBetweenGemstones
from .commands.CuttersForGemstones import CuttersForGemstones

from .commands.SurfaceUnfold import SurfaceUnfold
from .commands.ObjectsRefold import ObjectsRefold

commands = [
    GemstonesOnFaceAtPoints,
    GemstonesOnFaceAtCircles,
    GemstonesOnFaceAtCurve,
    GemstonesOnFaceBetweenCurves,
    
    ProngsOnFaceAtPoints,
    ProngsBetweenGemstones,
    
    ChannelsBetweenGemstones,
    CuttersForGemstones,
    SurfaceUnfold,
    ObjectsRefold,
    ]


# from . import strings

_app: adsk.core.Application = None
_ui: adsk.core.UserInterface = None
_tab: adsk.core.ToolbarTab = None
_panel: adsk.core.ToolbarPanel = None


def run(context):
    global _app, _ui, _tab, _panel
    _app = adsk.core.Application.get()
    _ui  = _app.userInterface

    solidWorkspace = _ui.workspaces.itemById('FusionSolidEnvironment')
    # _panel = solidWorkspace.toolbarPanels.add(strings.PANEL_ID, 'Jewelry Toolkit')
    _panel = solidWorkspace.toolbarPanels.itemById('SolidCreatePanel')

    if not _panel: return
    
    for command in commands:
        command.run(_panel)


def stop(context):
    global _app, _ui, _tab, _panel

    if not _panel: return
    
    for command in commands:
        command.stop(_panel)
        
    # _panel.deleteMe()
