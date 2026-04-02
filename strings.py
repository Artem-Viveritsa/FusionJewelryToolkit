from enum import Enum


COMPANY_NAME = 'Viveritsa'
ADDIN_NAME = 'FusionJewelryToolkit'

PREFIX = COMPANY_NAME + ADDIN_NAME

TAB_ID = PREFIX + 'Tab'
PANEL_ID = PREFIX + 'Panel'

PROPERTIES = 'properties'
ENTITY = 'entity'

GEMSTONE = 'gemstone'
GEMSTONE_IS_FLIPPED = 'gemstoneIsFlipped'
GEMSTONE_FLIP_FACE_NORMAL = 'gemstoneFlipFaceNormal'
GEMSTONE_RELATIVE_DEPTH_OFFSET = 'gemstoneRelativeDepthOffset'
GEMSTONE_ABSOLUTE_DEPTH_OFFSET = 'gemstoneAbsoluteDepthOffset'
GEMSTONE_CUT = 'gemstoneCut'
GEMSTONE_ROUND_CUT = 'round'

PRONG = 'prong'
PRONG_SIZE = 'prongSize'
PRONG_HEIGHT = 'prongHeight'



class CommandStrings:
    """Base class for command string constants."""

    def __init__(self, name: str, id: str):
        self.name = name
        self.id = id
        self.commandId = PREFIX + id
        self.createCommandId = self.commandId + 'Create'
        self.editCommandId = self.commandId + 'Edit'


class InputDef:
    def __init__(self, id: str, name: str, tooltip: str):
        self.id: str = id
        self.name: str = name
        self.tooltip: str = tooltip


class CutterBottomType(Enum):
    Hole = 0
    Cone = 1
    Hemisphere = 2


class UnfoldAlgorithm(Enum):
    Mesh = 0
    NURBS = 1


class UnfoldSourceType(Enum):
    Face = 0
    Mesh = 1


class PatternPlacementMode(Enum):
    OnSurface = 0
    OnCurve = 1


class GemstonesAtPointsStrings(CommandStrings):
    """String constants for the Gemstones on Face at Points command."""

    def __init__(self):
        super().__init__('gemstonesAtPoints', 'GemstonesOnFaceAtPoints')

    selectFaceInputId = 'selectFace'
    selectPointsInputId = 'selectPoints'
    sizeInputId = 'size'
    flipInputId = 'flip'
    flipFaceNormalInputId = 'flipFaceNormal'
    absoluteDepthOffsetInputId = 'absoluteDepthOffset'
    relativeDepthOffsetInputId = 'relativeDepthOffset'

GemstonesAtPoints = GemstonesAtPointsStrings()


class GemstonesAtCirclesStrings(CommandStrings):
    """String constants for the Gemstones on Face at Circles command."""

    def __init__(self):
        super().__init__('gemstonesAtCircles', 'GemstonesOnFaceAtCircles')

    selectFaceInputId = 'selectFace'
    selectCirclesInputId = 'selectCircles'
    flipInputId = 'flip'
    flipFaceNormalInputId = 'flipFaceNormal'
    absoluteDepthOffsetInputId = 'absoluteDepthOffset'
    relativeDepthOffsetInputId = 'relativeDepthOffset'

GemstonesAtCircles = GemstonesAtCirclesStrings()


class GemstonesAtCurveStrings(CommandStrings):
    """String constants for the Gemstones on Face at Curve command."""

    def __init__(self):
        super().__init__('gemstonesAtCurve', 'GemstonesOnFaceAtCurve')

    selectFaceInputId = 'selectFace'
    selectCurveInputId = 'selectCurve'
    startOffsetInputId = 'startOffset'
    endOffsetInputId = 'endOffset'
    startSizeInputId = 'startSize'
    endSizeInputId = 'endSize'
    sizeStepInputId = 'sizeStep'
    targetGapInputId = 'targetGap'
    flipInputId = 'flip'
    flipFaceNormalInputId = 'flipFaceNormal'
    flipDirectionInputId = 'flipDirection'
    uniformDistributionInputId = 'uniformDistribution'
    snapToCornersInputId = 'snapToCorners'
    absoluteDepthOffsetInputId = 'absoluteDepthOffset'
    relativeDepthOffsetInputId = 'relativeDepthOffset'
    nonlinearInputId = 'nonlinear'
    nonlinearSizeInputId = 'nonlinearSize'
    nonlinearPositionInputId = 'nonlinearPosition'

GemstonesAtCurve = GemstonesAtCurveStrings()


class GemstonesBetweenCurvesStrings(CommandStrings):
    """String constants for the Gemstones on Face Between Curves command."""

    def __init__(self):
        super().__init__('gemstonesBetweenCurves', 'GemstonesOnFaceBetweenCurves')

    selectFaceInputId = 'selectFace'
    selectRail1InputId = 'selectRail1'
    selectRail2InputId = 'selectRail2'
    flipDirectionInputId = 'flipDirection'
    uniformDistributionInputId = 'uniformDistribution'
    snapToCornersInputId = 'snapToCorners'
    startOffsetInputId = 'startOffset'
    endOffsetInputId = 'endOffset'
    sizeStepInputId = 'sizeStep'
    targetGapInputId = 'targetGap'
    sizeRatioInputId = 'sizeRatio'
    minStoneSizeInputId = 'minStoneSize'
    maxStoneSizeInputId = 'maxStoneSize'
    flipInputId = 'flip'
    flipFaceNormalInputId = 'flipFaceNormal'
    absoluteDepthOffsetInputId = 'absoluteDepthOffset'
    relativeDepthOffsetInputId = 'relativeDepthOffset'

GemstonesBetweenCurves = GemstonesBetweenCurvesStrings()


class GemstonesInfoStrings(CommandStrings):
    """String constants for the Gemstones Info command."""

    def __init__(self):
        super().__init__('gemstonesInfo', 'GemstonesInfo')

    selectGemstonesInputId = 'selectGemstones'
    infoInputId = 'info'

GemstonesInfo = GemstonesInfoStrings()


class ProngsAtPointsStrings(CommandStrings):
    """String constants for the Prongs on Face at Points command."""

    def __init__(self):
        super().__init__('prongsAtPoints', 'ProngsOnFaceAtPoints')

    selectFaceInputId = 'selectFace'
    selectPointsInputId = 'selectPoint'
    sizeInputId = 'size'
    heightInputId = 'height'

ProngsAtPoints = ProngsAtPointsStrings()


class ProngsBetweenGemstonesStrings(CommandStrings):
    """String constants for the Prongs Between Gemstones command."""

    def __init__(self):
        super().__init__('prongsBetweenGemstones', 'ProngsBetweenGemstones')

    selectGemstonesInputId = 'selectGemstones'
    sizeRatioInputId = 'sizeRatio'
    heightRatioInputId = 'heightRatio'
    widthBetweenProngsRatioInputId = 'widthBetweenProngsRatio'
    maxGapInputId = 'maxGap'
    weldDistanceInputId = 'weldDistance'

ProngsBetweenGemstones = ProngsBetweenGemstonesStrings()


class ChannelsBetweenGemstonesStrings(CommandStrings):
    """String constants for the Channels Between Gemstones command."""

    def __init__(self):
        super().__init__('channelsBetweenGemstones', 'ChannelsBetweenGemstones')

    selectGemstonesInputId = 'selectGemstones'
    ratioInputId = 'ratio'
    maxGapInputId = 'maxGap'
    channelEntity = 'channel'

ChannelsBetweenGemstones = ChannelsBetweenGemstonesStrings()


class CutterStrings(CommandStrings):

    def __init__(self):
        super().__init__('cutter', 'CuttersForGemstones')

    selectGemstonesInputId = 'selectGemstones'
    bottomTypeInputId = 'cutterBottomType'
    bottomTypes = [member.name for member in CutterBottomType]
    heightValueInputId = 'height'
    depthValueInputId = 'depth'
    sizeRatioValueInputId = 'sizeRatio'
    holeRatioValueInputId = 'holeRatio'
    coneAngleValueInputId = 'coneAngle'

Cutter = CutterStrings()


class UnfoldStrings(CommandStrings):

    def __init__(self):
        super().__init__('unfold', 'SurfaceUnfold')

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


class ObjectsRefoldStrings(CommandStrings):

    def __init__(self):
        super().__init__('objectsRefold', 'ObjectsRefold')

    selectSketchInputId = 'selectSketch'
    selectBodiesInputId = 'selectBodies'

ObjectsRefold = ObjectsRefoldStrings()


class PatternAlongPathStrings(CommandStrings):
    """String constants for the Pattern Along Path on Surface command."""

    def __init__(self):
        super().__init__('patternAlongPath', 'PatternAlongPathOnSurface')

    selectBodiesInputId = 'selectBodies'
    selectBasePointInputId = 'selectBasePoint'
    selectBaseSurfaceInputId = 'selectBaseSurface'
    selectCurveInputId = 'selectCurve'
    selectTargetSurfaceInputId = 'selectTargetSurface'
    placementModeInputId = 'placementMode'
    placementModes = ['On Surface', 'On Curve']
    flipDirectionInputId = 'flipDirection'
    uniformDistributionInputId = 'uniformDistribution'
    startOffsetInputId = 'startOffset'
    endOffsetInputId = 'endOffset'
    startRotateInputId = 'startRotate'
    endRotateInputId = 'endRotate'
    spacingInputId = 'spacing'
    countInputId = 'count'
    flipFaceNormalInputId = 'flipFaceNormal'
    absoluteDepthOffsetInputId = 'absoluteDepthOffset'
    relativeDepthOffsetInputId = 'relativeDepthOffset'
    appliedTransformAttributeKey = 'appliedTransform'

PatternAlongPath = PatternAlongPathStrings()


class TaperStrings(CommandStrings):

    def __init__(self):
        super().__init__('taper', 'Taper')

    selectBodyInputId = 'selectBody'
    selectAxisInputId = 'selectAxis'
    selectPivotPointInputId = 'selectPivotPoint'
    angleInputId = 'taperAngle'
    sourceBodyFaceDependencyId = 'firstBodyFace'
    axisDependencyId = 'axisDependency'
    pivotPointDependencyId = 'pivotPointDependency'
    bodyNameTemplate = '{bodyName} (Taper)'

Taper = TaperStrings()


class FFDStrings(CommandStrings):

    def __init__(self):
        super().__init__('ffd', 'FFD')

    selectBodyInputId = 'ffdSelectBody'
    offsetXInputId = 'ffdOffsetX'
    offsetYInputId = 'ffdOffsetY'
    offsetZInputId = 'ffdOffsetZ'
    resolutionXInputId = 'ffdResolutionX'
    resolutionYInputId = 'ffdResolutionY'
    resolutionZInputId = 'ffdResolutionZ'
    resetButtonInputId = 'ffdResetAll'
    sourceBodyFaceDependencyId = 'firstBodyFace'
    offsetsAttributeGroup = 'FFD'
    offsetsAttributeName = 'offsets'
    gridSizeAttributeName = 'gridSizes'
    bodyNameTemplate = '{bodyName} (FFD)'
    resetConfirmationTitle = 'Reset FFD'
    resetConfirmationMessage = 'Reset all control points to zero?'

FFD = FFDStrings()