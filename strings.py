from enum import Enum


COMPANY_NAME = 'Viveritsa'
ADDIN_NAME = 'FusionJewelryToolkit'

PREFIX = COMPANY_NAME + ADDIN_NAME

TAB_ID = PREFIX + 'Tab'
PANEL_ID = PREFIX + 'Panel'

PROPERTIES = 'properties'

GEMSTONES_ON_FACE_AT_POINTS = 'GemstonesOnFaceAtPoints'
GEMSTONES_ON_FACE_AT_CIRCLES = 'GemstonesOnFaceAtCircles'
GEMSTONES_ON_FACE_AT_CURVE = 'GemstonesOnFaceAtCurve'
GEMSTONES_ON_FACE_BETWEEN_CURVES = 'GemstonesOnFaceBetweenCurves'
GEMSTONES_INFO = 'GemstonesInfo'

PRONGS_ON_FACE_AT_POINTS = 'ProngsOnFaceAtPoints'
PRONGS_BETWEEN_GEMSTONES = 'ProngsBetweenGemstones'


CHANNELS_BETWEEN_GEMSTONES = 'ChannelsBetweenGemstones'

ENTITY = 'entity'

GEMSTONE = 'gemstone'
GEMSTONE_IS_FLIPPED = 'gemstoneIsFlipped'
GEMSTONE_RELATIVE_DEPTH_OFFSET = 'gemstoneRelativeDepthOffset'
GEMSTONE_ABSOLUTE_DEPTH_OFFSET = 'gemstoneAbsoluteDepthOffset'
GEMSTONE_CUT = 'gemstoneCut'
GEMSTONE_ROUND_CUT = 'round'

PRONG = 'prong'
PRONG_SIZE = 'prongSize'
PRONG_HEIGHT = 'prongHeight'

class CutterBottomType(Enum):
    Hole = 0
    Cone = 1
    Hemisphere = 2

class CutterStrings:
    name = 'cutter'
    cutterForGemstonesCommandId = 'CuttersForGemstones'
    selectGemstonesInputId = 'selectGemstones'
    bottomTypeInputId = 'cutterBottomType'
    bottomTypes = [member.name for member in CutterBottomType]
    heightValueInputId = 'height'
    depthValueInputId = 'depth'
    sizeRatioValueInputId = 'sizeRatio'
    holeRatioValueInputId = 'holeRatio'
    coneAngleValueInputId = 'coneAngle'

Cutter = CutterStrings()

CHANNEL = 'channel'

class UnfoldAlgorithm(Enum):
    Mesh = 0
    NURBS = 1

class UnfoldSourceType(Enum):
    Face = 0
    Mesh = 1
    
class UnfoldStrings:
    name = 'unfold'
    surfaceUnfoldCommandId = 'SurfaceUnfold'
    selectSourceInputId = 'selectSource'
    originVertexInputId = 'originVertex'
    xDirectionVertexInputId = 'xDirectionVertex'
    yDirectionVertexInputId = 'yDirectionVertex'
    accuracyValueInputId = 'accuracy'
    algorithmInputId = 'algorithm'
    algorithms = [member.name for member in UnfoldAlgorithm]
    constructionPlaneInputId = 'constructionPlane'
    xOffsetValueInputId = 'xOffset'
    yOffsetValueInputId = 'yOffset'

    sourceDependencyId = 'source'
    originVertexDependencyId = 'originVertex'
    xDirectionVertexDependencyId = 'xDirVertex'
    yDirectionVertexDependencyId = 'yDirVertex'
    constructionPlaneDependencyId = 'constructionPlane'
    
    sourcePoint3D = 'sourcePoint3D'
    sourceNormal = 'sourceNormal'
    sourceData = 'sourceData'
    
Unfold = UnfoldStrings()


class ObjectsRefoldStrings:
    name = 'objectsRefold'
    objectsRefoldCommandId = 'ObjectsRefold'
    selectSketchInputId = 'selectSketch'
    selectBodiesInputId = 'selectBodies'

ObjectsRefold = ObjectsRefoldStrings()

class InputDef:
    def __init__(self, id: str, name: str, tooltip: str):
        self.id: str = id
        self.name: str = name
        self.tooltip: str = tooltip