import math
import os
from enum import Enum

import adsk.core
import adsk.fusion


app = adsk.core.Application.get()
measureManager = app.measureManager

COMPANY_NAME = 'Viveritsa'
ADDIN_NAME = 'FusionJewelryToolkit'

PREFIX = COMPANY_NAME + ADDIN_NAME

TAB_ID = PREFIX + 'Tab'
PANEL_ID = PREFIX + 'Panel'

PROPERTIES = 'properties'
ENTITY = 'entity'

GEMSTONE = 'gemstone'
PRONG = 'prong'
CUTTER = 'cutter'
GEMSTONE_IS_FLIPPED = 'gemstoneIsFlipped'
GEMSTONE_FLIP_FACE_NORMAL = 'gemstoneFlipFaceNormal'
GEMSTONE_RELATIVE_DEPTH_OFFSET = 'gemstoneRelativeDepthOffset'
GEMSTONE_ABSOLUTE_DEPTH_OFFSET = 'gemstoneAbsoluteDepthOffset'
GEMSTONE_CUT = 'gemstoneCut'
GEMSTONE_ROUND_CUT = 'round'

PRONG_SIZE = 'prongSize'
PRONG_HEIGHT = 'prongHeight'

zeroPoint = adsk.core.Point3D.create(0, 0, 0)
xVector = adsk.core.Vector3D.create(1, 0, 0)
yVector = adsk.core.Vector3D.create(0, 1, 0)
zVector = adsk.core.Vector3D.create(0, 0, 1)

ASSETS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', '')

materialLibrary = adsk.core.Application.get().materialLibraries.load(ASSETS_FOLDER + 'Jewelry Material Library.adsklib')

minimumGemstoneSize = 0.05
gemstoneOverlapMergeThreshold = 0.05
cornerAngleThresholdDegrees = 10
cornerAngleThresholdRadians = math.radians(cornerAngleThresholdDegrees)
chainConnectionTolerance = 0.001

prongChainMaxConnections = 2
prongChainCurvatureShiftFactor = 0.5
prongChainCurvatureSizeFactor = 0.2

defaultBendAngleDeg = 45
minBendAngleDeg = -360
maxBendAngleDeg = 360
minimumBendAngle = 1e-10
perpendicularDirectionThreshold = 0.9


class CommandStrings:
    """Base class for command string constants."""

    def __init__(self, id: str):
        self.id = id
        self.commandId = PREFIX + id
        self.createCommandId = self.commandId + 'Create'
        self.editCommandId = self.commandId + 'Edit'


class InputDef:
    """Describe a command input shown in the Fusion UI."""

    def __init__(self, id: str, name: str, tooltip: str):
        self.id = id
        self.name = name
        self.tooltip = tooltip


class CutterBottomType(Enum):
    """Supported cutter bottom shapes."""

    Hole = 0
    Cone = 1
    Hemisphere = 2


class UnfoldAlgorithm(Enum):
    """Supported surface unfolding algorithms."""

    Mesh = 0
    NURBS = 1


class UnfoldSourceType(Enum):
    """Supported unfold source kinds."""

    Face = 0
    Mesh = 1


class PatternPlacementMode(Enum):
    """Placement modes for pattern along path."""

    OnSurface = 0
    OnCurve = 1


class RemeshAlgorithm(Enum):
    """Supported remeshing algorithms for mesh-based workflows."""

    Isotropic = 0
    Acvd = 1


class GemstonesAtPointsStrings(CommandStrings):
    """Constants for the Gemstones on Face at Points command."""

    def __init__(self):
        super().__init__('GemstonesOnFaceAtPoints')

    selectFaceInputId = 'selectFace'
    selectPointsInputId = 'selectPoints'
    sizeInputId = 'size'
    flipInputId = 'flip'
    flipFaceNormalInputId = 'flipFaceNormal'
    absoluteDepthOffsetInputId = 'absoluteDepthOffset'
    relativeDepthOffsetInputId = 'relativeDepthOffset'


GemstonesAtPoints = GemstonesAtPointsStrings()


class GemstonesAtCirclesStrings(CommandStrings):
    """Constants for the Gemstones on Face at Circles command."""

    def __init__(self):
        super().__init__('GemstonesOnFaceAtCircles')

    selectFaceInputId = 'selectFace'
    selectCirclesInputId = 'selectCircles'
    flipInputId = 'flip'
    flipFaceNormalInputId = 'flipFaceNormal'
    absoluteDepthOffsetInputId = 'absoluteDepthOffset'
    relativeDepthOffsetInputId = 'relativeDepthOffset'


GemstonesAtCircles = GemstonesAtCirclesStrings()


class GemstonesAtCurveStrings(CommandStrings):
    """Constants for the Gemstones on Face at Curve command."""

    def __init__(self):
        super().__init__('GemstonesOnFaceAtCurve')

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
    """Constants for the Gemstones on Face Between Curves command."""

    def __init__(self):
        super().__init__('GemstonesOnFaceBetweenCurves')

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
    defaultMinStoneSizeCm = 0.07
    defaultMaxStoneSizeCm = 0.2
    minStoneSizeLimitCm = 0.05
    maxStoneSizeLimitCm = 1.0


GemstonesBetweenCurves = GemstonesBetweenCurvesStrings()


class GemstonesInfoStrings(CommandStrings):
    """Constants for the Gemstones Info command."""

    def __init__(self):
        super().__init__('GemstonesInfo')

    selectGemstonesInputId = 'selectGemstones'
    infoInputId = 'info'


GemstonesInfo = GemstonesInfoStrings()


class ProngsAtPointsStrings(CommandStrings):
    """Constants for the Prongs on Face at Points command."""

    def __init__(self):
        super().__init__('ProngsOnFaceAtPoints')

    selectFaceInputId = 'selectFace'
    selectPointsInputId = 'selectPoint'
    sizeInputId = 'size'
    heightInputId = 'height'


ProngsAtPoints = ProngsAtPointsStrings()


class ProngsBetweenGemstonesStrings(CommandStrings):
    """Constants for the Prongs Between Gemstones command."""

    def __init__(self):
        super().__init__('ProngsBetweenGemstones')

    selectGemstonesInputId = 'selectGemstones'
    sizeRatioInputId = 'sizeRatio'
    heightRatioInputId = 'heightRatio'
    uniformityInputId = 'uniformity'
    widthBetweenProngsRatioInputId = 'widthBetweenProngsRatio'
    maxGapInputId = 'maxGap'
    weldDistanceInputId = 'weldDistance'


ProngsBetweenGemstones = ProngsBetweenGemstonesStrings()


class ChannelsBetweenGemstonesStrings(CommandStrings):
    """Constants for the Channels Between Gemstones command."""

    def __init__(self):
        super().__init__('ChannelsBetweenGemstones')

    selectGemstonesInputId = 'selectGemstones'
    ratioInputId = 'ratio'
    maxGapInputId = 'maxGap'
    channelEntity = 'channel'
    channelInset = 0.005
    channelJunctionSphereScale = 1.1


ChannelsBetweenGemstones = ChannelsBetweenGemstonesStrings()


class CutterStrings(CommandStrings):
    """Constants for the Cutters for Gemstones command."""

    def __init__(self):
        super().__init__('CuttersForGemstones')

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
    """Constants for the Surface Unfold command."""

    def __init__(self):
        super().__init__('SurfaceUnfold')

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
    meshIsotropicIterationCount = 10
    meshIsotropicSmoothingBlend = 0.8


Unfold = UnfoldStrings()


class ObjectsRefoldStrings(CommandStrings):
    """Constants for the Objects Refold command."""

    def __init__(self):
        super().__init__('ObjectsRefold')

    selectSketchInputId = 'selectSketch'
    selectBodiesInputId = 'selectBodies'


ObjectsRefold = ObjectsRefoldStrings()


class PatternAlongPathStrings(CommandStrings):
    """Constants for the Pattern Along Path on Surface command."""

    def __init__(self):
        super().__init__('PatternAlongPathOnSurface')

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
    defaultSpacingCm = 0.5
    placementOnSurfaceIndex = 0
    placementOnCurveIndex = 1


PatternAlongPath = PatternAlongPathStrings()


class TaperStrings(CommandStrings):
    """Constants for the Taper command."""

    def __init__(self):
        super().__init__('Taper')

    selectBodyInputId = 'selectBody'
    selectAxisInputId = 'selectAxis'
    selectPivotPointInputId = 'selectPivotPoint'
    angleInputId = 'taperAngle'
    sourceBodyFaceDependencyId = 'firstBodyFace'
    axisDependencyId = 'axisDependency'
    pivotPointDependencyId = 'pivotPointDependency'
    bodyNameTemplate = '{bodyName} (Taper)'
    defaultTaperAngleDeg = 10
    minTaperAngleDeg = -45
    maxTaperAngleDeg = 45
    minimumTaperScale = 0.001
    taperPreviewLineWeight = 1.0
    taperPreviewLineColorRGBA = (128, 128, 128, 255)
    taperPreviewEdgeSegments = 8
    taperBoundingBoxEdgeIndices = (
        (0, 1), (0, 2), (1, 3), (2, 3),
        (4, 5), (4, 6), (5, 7), (6, 7),
        (0, 4), (1, 5), (2, 6), (3, 7)
    )
    bodyNurbsConversionOptions = (
        adsk.fusion.BRepConvertOptions.ProceduralToNURBSConversion |
        adsk.fusion.BRepConvertOptions.AnalyticsToNURBSConversion |
        adsk.fusion.BRepConvertOptions.PlanesToNURBSConversion |
        adsk.fusion.BRepConvertOptions.SplitPeriodicFacesConversion
    )


Taper = TaperStrings()


class FFDStrings(CommandStrings):
    """Constants for the FFD command."""

    def __init__(self):
        super().__init__('FFD')

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
    defaultGridSize = 3
    minGridSize = 2
    maxGridSize = 5
    defaultOffsetCm = 0.0
    controlPointMarkerFraction = 0.02
    selectedPointMarkerFraction = 0.035
    latticeLineWeight = 1.0
    controlPointLineWeight = 2.0
    selectedPointLineWeight = 4.0
    latticeLineColorRGBA = (128, 128, 128, 255)
    normalPointColorRGB = (0, 120, 255)
    selectedPointColorRGB = (255, 165, 0)
    showPointLabels = False
    labelSizeFraction = 0.025
    labelColorRGB = (0, 0, 0)
    pointClickThreshold = 30.0


FFD = FFDStrings()


class MeshRemeshStrings:
    """Shared remeshing defaults used by mesh helpers and commands."""

    previewClusterLineColorRGBA = (255, 140, 0, 255)
    previewClusterLineWeight = 1.1
    previewLineColorRGBA = (0, 120, 255, 255)
    previewLineWeight = 1
    previewBoundaryLineColorRGBA = (0, 120, 255, 255)
    previewBoundaryLineWeight = 3
    surfaceTolerance = 10.0
    maxNormalDeviation = 40.0
    maxAspectRatio = 2.0
    isotropicIterationCount = 20
    isotropicSmoothingBlend = 0.8
    isotropicSplitEdgeFactor = 5.0 / 4.0
    isotropicCollapseEdgeFactor = 4.0 / 5.0
    isotropicInteriorValence = 6
    isotropicBoundaryValence = 4
    surfaceCurvatureCompensationEnabled = True
    midpointSurfaceCompensationEnabled = False
    midpointSurfaceCompensationIterations = 2
    midpointSurfaceCompensationBlend = 0.5
    # Numerical tolerance used when welding close vertices and matching boundary samples.
    acvdMinimumSamplingDistanceCm = 1e-4
    # Refined support-mesh density relative to the requested final cluster count.
    acvdSubdivisionTargetRatio = 6
    # Hard cap for support-mesh subdivision passes before clustering starts.
    acvdMaxSubdivisionIterations = 2
    # Maximum number of ACVD local energy-minimization iterations.
    acvdMaxClusteringIterations = 12
    # Preserve and constrain the open boundary when tessellating non-closed face sets.
    acvdPreserveOpenBoundaryEnabled = True
    # Optional post-pass that evens out local ACVD edge lengths on the final mesh.
    acvdEdgeLengthEqualizationEnabled = True
    # Number of relaxation iterations for the final ACVD edge equalization pass.
    acvdEdgeLengthEqualizationIterations = 12
    # Blend factor used by the final ACVD edge equalization pass.
    acvdEdgeLengthEqualizationBlend = 0.7
    # Optional post-pass that offsets vertices along face normals so edge midpoints better fit the surface.
    acvdMidpointSurfaceCompensationEnabled = surfaceCurvatureCompensationEnabled
    # Number of iterations for the midpoint-based surface compensation pass.
    acvdMidpointSurfaceCompensationIterations = midpointSurfaceCompensationIterations
    # Blend factor for the midpoint-based surface compensation pass.
    acvdMidpointSurfaceCompensationBlend = midpointSurfaceCompensationBlend
    # Stop clustering only when almost no vertices change their cluster assignment.
    acvdMinimumMovedFraction = 0.01
    acvdMinTriangleArea = 1e-12


MeshRemesh = MeshRemeshStrings()