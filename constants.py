import os, math, adsk.core, adsk.fusion

app = adsk.core.Application.get()
measureManager = app.measureManager

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

defaultMinStoneSizeCm = 0.07
defaultMaxStoneSizeCm = 0.2
minStoneSizeLimitCm = 0.05
maxStoneSizeLimitCm = 1.0

channelInset = 0.005
channelJunctionSphereScale = 1.1

patternAlongPathDefaultSpacingCm = 0.5
patternAlongPathPlacementOnSurfaceIndex = 0
patternAlongPathPlacementOnCurveIndex = 1


class DeformationsConstants:
    """Constants for the Deformations command."""

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

    defaultBendAngleDeg = 45
    minBendAngleDeg = -360
    maxBendAngleDeg = 360
    minimumBendAngle = 1e-10
    perpendicularDirectionThreshold = 0.9

    bodyNurbsConversionOptions = (
        adsk.fusion.BRepConvertOptions.ProceduralToNURBSConversion | 
        adsk.fusion.BRepConvertOptions.AnalyticsToNURBSConversion | 
        adsk.fusion.BRepConvertOptions.PlanesToNURBSConversion | 
        adsk.fusion.BRepConvertOptions.SplitPeriodicFacesConversion
		)


Deformations = DeformationsConstants()
Deform = Deformations


class FFDConstants:
    """Constants for the FFD (Free Form Deformation) command."""

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


FFDConst = FFDConstants()