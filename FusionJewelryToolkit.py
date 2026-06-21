import adsk.core, adsk.fusion
from .commands.GemstonesOnFaceAtPoints import GemstonesOnFaceAtPoints
from .commands.GemstonesOnFaceAtCircles import GemstonesOnFaceAtCircles
from .commands.GemstonesOnFaceAtCurve import GemstonesOnFaceAtCurve
from .commands.GemstonesOnFaceBetweenCurves import GemstonesOnFaceBetweenCurves

from .commands.ProngsOnFaceAtPoints import ProngsOnFaceAtPoints
from .commands.ProngsBetweenGemstones import ProngsBetweenGemstones
from .commands.ScallopSettingCutters import ScallopSettingCutters

from .commands.ChannelsBetweenGemstones import ChannelsBetweenGemstones
from .commands.CuttersForGemstones import CuttersForGemstones

from .commands.SurfaceUnfold import SurfaceUnfold
from .commands.ObjectsRefold import ObjectsRefold

from .commands.PatternAlongPathOnSurface import PatternAlongPathOnSurface

from .commands.FFD import FFD
from .commands.Taper import Taper

from .commands.GemstonesInfo import GemstonesInfo

try:
    from .commands.TessellateInfo import TessellateInfo
except ModuleNotFoundError:
    TessellateInfo = None

try:
    from .commands.PaveOnFaces import PaveOnFaces
except ModuleNotFoundError:
    PaveOnFaces = None

commands = [
    GemstonesOnFaceAtPoints,
    GemstonesOnFaceAtCircles,
    GemstonesOnFaceAtCurve,
    GemstonesOnFaceBetweenCurves,
    
    ProngsOnFaceAtPoints,
    ProngsBetweenGemstones,
    
    ChannelsBetweenGemstones,
    CuttersForGemstones,
    ScallopSettingCutters,
    
    SurfaceUnfold,
    ObjectsRefold,

    PatternAlongPathOnSurface,

    FFD,
    Taper,

    GemstonesInfo,
    ]

if PaveOnFaces is not None:
    commands.insert(4, PaveOnFaces)
if TessellateInfo is not None:
    commands.append(TessellateInfo)



from . import constants

_app: adsk.core.Application = None
_ui: adsk.core.UserInterface = None
_tab: adsk.core.ToolbarTab = None
_panel: adsk.core.ToolbarPanel = None


def run(context):
    global _app, _ui, _tab, _panel
    _app = adsk.core.Application.get()
    _ui  = _app.userInterface

    solidWorkspace = _ui.workspaces.itemById('FusionSolidEnvironment')
    _panel = solidWorkspace.toolbarPanels.add(constants.PANEL_ID, 'Jewelry Toolkit')
    # _panel = solidWorkspace.toolbarPanels.itemById('SolidCreatePanel')

    if not _panel: return
    
    for command in commands:
        command.run(_panel)


def stop(context):
    global _app, _ui, _tab, _panel

    if not _panel: return
    
    for command in commands:
        command.stop(_panel)
        
    _panel.deleteMe()
