import math

import adsk.core
import adsk.fusion

from ... import constants
from . import acvd as meshAcvd
from . import core as meshCore


def clearPreviewGraphics(previewGraphicsGroup: adsk.fusion.CustomGraphicsGroup | None) -> None:
    """Remove a previously created preview graphics group."""
    if previewGraphicsGroup is None:
        return

    try:
        previewGraphicsGroup.deleteMe()
    except:
        pass


def addPreviewLines(
    previewGraphicsGroup: adsk.fusion.CustomGraphicsGroup | None,
    lineCoordinates: list[float],
    colorRgba: tuple[int, int, int, int],
    lineWeight: float
) -> None:
    """Add one colored line set to a preview graphics group."""
    if previewGraphicsGroup is None or not lineCoordinates:
        return

    graphicsCoordinates = adsk.fusion.CustomGraphicsCoordinates.create(lineCoordinates)
    graphicsLines = previewGraphicsGroup.addLines(graphicsCoordinates, [], False, [])
    redValue, greenValue, blueValue, alphaValue = colorRgba
    graphicsLines.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(
        adsk.core.Color.create(redValue, greenValue, blueValue, alphaValue)
    )
    graphicsLines.weight = lineWeight


def buildPreviewLineCoordinates(meshData: meshCore.TriangleMeshData) -> tuple[list[float], list[float]]:
    """Build preview lines for all mesh edges and open-boundary edges."""
    coordinates, coordinateIndices = meshData
    edgeUseCounts: dict[tuple[int, int], int] = {}

    for triangleIndex in range(0, len(coordinateIndices), 3):
        index0 = coordinateIndices[triangleIndex]
        index1 = coordinateIndices[triangleIndex + 1]
        index2 = coordinateIndices[triangleIndex + 2]

        for startIndex, endIndex in ((index0, index1), (index1, index2), (index2, index0)):
            edgeKey = (min(startIndex, endIndex), max(startIndex, endIndex))
            edgeUseCounts[edgeKey] = edgeUseCounts.get(edgeKey, 0) + 1

    lineCoordinates: list[float] = []
    boundaryLineCoordinates: list[float] = []

    for startIndex, endIndex in edgeUseCounts:
        startOffset = startIndex * 3
        endOffset = endIndex * 3
        edgeCoordinates = [
            coordinates[startOffset],
            coordinates[startOffset + 1],
            coordinates[startOffset + 2],
            coordinates[endOffset],
            coordinates[endOffset + 1],
            coordinates[endOffset + 2]
        ]
        lineCoordinates.extend(edgeCoordinates)

        if edgeUseCounts[(startIndex, endIndex)] == 1:
            boundaryLineCoordinates.extend(edgeCoordinates)

    return lineCoordinates, boundaryLineCoordinates


def createPreviewPoint(xValue: float, yValue: float, zValue: float) -> adsk.core.Point3D:
    """Create a preview point from flat coordinate values."""
    return adsk.core.Point3D.create(xValue, yValue, zValue)


def createPreviewVector(xValue: float, yValue: float, zValue: float) -> adsk.core.Vector3D:
    """Create and normalize a preview vector when possible."""
    vector = adsk.core.Vector3D.create(xValue, yValue, zValue)
    if vector.length > constants.MeshRemesh.acvdMinTriangleArea:
        vector.normalize()

    return vector


def _buildClusterPolygonBasis(normalVector: adsk.core.Vector3D) -> tuple[adsk.core.Vector3D, adsk.core.Vector3D] | None:
    """Build a stable tangent basis for sorting polygon points around a cluster center."""
    if normalVector.length <= constants.MeshRemesh.acvdMinTriangleArea:
        normalVector = adsk.core.Vector3D.create(0.0, 0.0, 1.0)

    referenceVector = adsk.core.Vector3D.create(1.0, 0.0, 0.0)
    if abs(normalVector.dotProduct(referenceVector)) > 0.9:
        referenceVector = adsk.core.Vector3D.create(0.0, 1.0, 0.0)

    tangentX = normalVector.crossProduct(referenceVector)
    if tangentX.length <= constants.MeshRemesh.acvdMinTriangleArea:
        return None

    tangentX.normalize()
    tangentY = normalVector.crossProduct(tangentX)
    if tangentY.length <= constants.MeshRemesh.acvdMinTriangleArea:
        return None

    tangentY.normalize()
    return tangentX, tangentY


def buildClusterPolygonPointsByIndex(
    tessellationResult: meshAcvd.AcvdTessellationResult
) -> dict[int, list[adsk.core.Point3D]]:
    """Build ordered polygon points for each ACVD cluster vertex."""
    coordinates, coordinateIndices = tessellationResult.finalMeshData
    if not coordinates or not coordinateIndices:
        return {}

    pointCount = len(coordinates) // 3
    if pointCount != len(tessellationResult.usedClusterIndices):
        return {}

    points = [
        createPreviewPoint(
            coordinates[coordinateIndex],
            coordinates[coordinateIndex + 1],
            coordinates[coordinateIndex + 2]
        )
        for coordinateIndex in range(0, len(coordinates), 3)
    ]
    triangles = [
        (
            coordinateIndices[triangleIndex],
            coordinateIndices[triangleIndex + 1],
            coordinateIndices[triangleIndex + 2]
        )
        for triangleIndex in range(0, len(coordinateIndices), 3)
    ]
    triangleCentroids = [
        createPreviewPoint(
            (points[index0].x + points[index1].x + points[index2].x) / 3.0,
            (points[index0].y + points[index1].y + points[index2].y) / 3.0,
            (points[index0].z + points[index1].z + points[index2].z) / 3.0
        )
        for index0, index1, index2 in triangles
    ]
    edgeUseCounts: dict[tuple[int, int], int] = {}
    incidentTriangleIndices: list[list[int]] = [[] for _ in range(pointCount)]
    boundaryNeighborIndices: list[set[int]] = [set() for _ in range(pointCount)]

    for triangleIndex, (index0, index1, index2) in enumerate(triangles):
        incidentTriangleIndices[index0].append(triangleIndex)
        incidentTriangleIndices[index1].append(triangleIndex)
        incidentTriangleIndices[index2].append(triangleIndex)

        for startIndex, endIndex in ((index0, index1), (index1, index2), (index2, index0)):
            edgeKey = (min(startIndex, endIndex), max(startIndex, endIndex))
            edgeUseCounts[edgeKey] = edgeUseCounts.get(edgeKey, 0) + 1

    for startIndex, endIndex in edgeUseCounts:
        if edgeUseCounts[(startIndex, endIndex)] != 1:
            continue

        boundaryNeighborIndices[startIndex].add(endIndex)
        boundaryNeighborIndices[endIndex].add(startIndex)

    polygonPointsByIndex: dict[int, list[adsk.core.Point3D]] = {}

    for pointIndex, clusterCenter in enumerate(points):
        clusterTriangleIndices = incidentTriangleIndices[pointIndex]
        if not clusterTriangleIndices:
            continue

        sourceClusterIndex = tessellationResult.usedClusterIndices[pointIndex]
        if sourceClusterIndex >= len(tessellationResult.clusterNormals):
            continue

        clusterNormal = tessellationResult.clusterNormals[sourceClusterIndex]
        normalVector = createPreviewVector(clusterNormal.x, clusterNormal.y, clusterNormal.z)
        basis = _buildClusterPolygonBasis(normalVector)
        if basis is None:
            continue

        tangentX, tangentY = basis

        polygonPoints = [triangleCentroids[triangleIndex] for triangleIndex in clusterTriangleIndices]

        for neighborIndex in sorted(boundaryNeighborIndices[pointIndex]):
            neighborPoint = points[neighborIndex]
            polygonPoints.append(createPreviewPoint(
                (clusterCenter.x + neighborPoint.x) * 0.5,
                (clusterCenter.y + neighborPoint.y) * 0.5,
                (clusterCenter.z + neighborPoint.z) * 0.5
            ))

        if len(boundaryNeighborIndices[pointIndex]) > 0:
            polygonPoints.append(clusterCenter)

        uniquePolygonPoints: list[adsk.core.Point3D] = []
        for polygonPoint in polygonPoints:
            if any(
                existingPoint.distanceTo(polygonPoint) <= constants.MeshRemesh.acvdMinimumSamplingDistanceCm
                for existingPoint in uniquePolygonPoints
            ):
                continue

            uniquePolygonPoints.append(polygonPoint)

        if len(uniquePolygonPoints) < 3:
            continue

        polygonPointsByIndex[pointIndex] = sorted(
            uniquePolygonPoints,
            key=lambda polygonPoint: math.atan2(
                clusterCenter.vectorTo(polygonPoint).dotProduct(tangentY),
                clusterCenter.vectorTo(polygonPoint).dotProduct(tangentX)
            )
        )

    return polygonPointsByIndex


def buildClusterPolygonLineCoordinates(
    tessellationResult: meshAcvd.AcvdTessellationResult
) -> list[float]:
    """Build preview lines for ACVD dual cluster polygons."""
    polygonPointsByIndex = buildClusterPolygonPointsByIndex(tessellationResult)
    lineCoordinates: list[float] = []

    for orderedPolygonPoints in polygonPointsByIndex.values():
        for polygonIndex, startPoint in enumerate(orderedPolygonPoints):
            endPoint = orderedPolygonPoints[(polygonIndex + 1) % len(orderedPolygonPoints)]
            lineCoordinates.extend([
                startPoint.x,
                startPoint.y,
                startPoint.z,
                endPoint.x,
                endPoint.y,
                endPoint.z
            ])

    return lineCoordinates


def updatePreviewGraphics(
    app: adsk.core.Application,
    previewGraphicsGroup: adsk.fusion.CustomGraphicsGroup | None,
    tessellationResult: meshAcvd.AcvdTessellationResult | None
) -> adsk.fusion.CustomGraphicsGroup | None:
    """Draw the remeshed wireframe together with cluster boundaries."""
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        clearPreviewGraphics(previewGraphicsGroup)
        return None

    clearPreviewGraphics(previewGraphicsGroup)
    if tessellationResult is None:
        return None

    finalMeshCoordinates, boundaryMeshCoordinates = buildPreviewLineCoordinates(tessellationResult.finalMeshData)
    clusterPolygonCoordinates = buildClusterPolygonLineCoordinates(tessellationResult)

    if not finalMeshCoordinates and not clusterPolygonCoordinates:
        return None

    newPreviewGraphicsGroup = design.rootComponent.customGraphicsGroups.add()
    addPreviewLines(
        newPreviewGraphicsGroup,
        clusterPolygonCoordinates,
        constants.MeshRemesh.previewClusterLineColorRGBA,
        constants.MeshRemesh.previewClusterLineWeight
    )
    addPreviewLines(
        newPreviewGraphicsGroup,
        finalMeshCoordinates,
        constants.MeshRemesh.previewLineColorRGBA,
        constants.MeshRemesh.previewLineWeight
    )
    addPreviewLines(
        newPreviewGraphicsGroup,
        boundaryMeshCoordinates,
        constants.MeshRemesh.previewBoundaryLineColorRGBA,
        constants.MeshRemesh.previewBoundaryLineWeight
    )
    return newPreviewGraphicsGroup


def updateSimpleMeshPreviewGraphics(
    app: adsk.core.Application,
    previewGraphicsGroup: adsk.fusion.CustomGraphicsGroup | None,
    meshData: meshCore.TriangleMeshData | None
) -> adsk.fusion.CustomGraphicsGroup | None:
    """Draw a plain wireframe for raw triangle mesh data without cluster information."""
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        clearPreviewGraphics(previewGraphicsGroup)
        return None

    clearPreviewGraphics(previewGraphicsGroup)
    if meshData is None:
        return None

    lineCoordinates, boundaryLineCoordinates = buildPreviewLineCoordinates(meshData)
    if not lineCoordinates:
        return None

    newPreviewGraphicsGroup = design.rootComponent.customGraphicsGroups.add()
    addPreviewLines(
        newPreviewGraphicsGroup,
        lineCoordinates,
        constants.MeshRemesh.previewLineColorRGBA,
        constants.MeshRemesh.previewLineWeight
    )
    addPreviewLines(
        newPreviewGraphicsGroup,
        boundaryLineCoordinates,
        constants.MeshRemesh.previewBoundaryLineColorRGBA,
        constants.MeshRemesh.previewBoundaryLineWeight
    )
    return newPreviewGraphicsGroup