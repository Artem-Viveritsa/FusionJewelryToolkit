from dataclasses import dataclass

import adsk.core
import adsk.fusion

from ... import constants
from . import acvd as meshAcvd
from . import core as meshCore
from . import remesh as meshRemesh
from . import topology


@dataclass
class IsotropicRemeshSettings:
    """Store runtime settings for the isotropic remeshing pipeline.

    Attributes:
        surfaceTolerance: Source BRep tessellation tolerance forwarded to Fusion mesh generation.
        maxNormalDeviation: Source BRep tessellation angular deviation forwarded to Fusion.
        maxAspectRatio: Source BRep tessellation aspect-ratio limit forwarded to Fusion.
        iterationCount: Number of isotropic remeshing iterations to execute.
        smoothingBlend: Blend factor used by Laplacian smoothing.
    """

    surfaceTolerance: float
    maxNormalDeviation: float
    maxAspectRatio: float
    iterationCount: int
    smoothingBlend: float

    @classmethod
    def fromDefaults(cls) -> 'IsotropicRemeshSettings':
        """Build default isotropic remesh settings from constants."""
        return cls(
            constants.MeshRemesh.surfaceTolerance,
            constants.MeshRemesh.maxNormalDeviation,
            constants.MeshRemesh.maxAspectRatio,
            constants.MeshRemesh.isotropicIterationCount,
            constants.MeshRemesh.isotropicSmoothingBlend
        )


def createIsotropicTessellationResult(
    faces: list[adsk.fusion.BRepFace],
    accuracy: float,
    settings: IsotropicRemeshSettings | None = None
) -> meshAcvd.AcvdTessellationResult | None:
    """Run isotropic remeshing using accuracy as the ideal edge length."""
    effectiveSettings = settings or IsotropicRemeshSettings.fromDefaults()
    meshResult = topology.meshFaces(
        faces,
        accuracy,
        effectiveSettings.surfaceTolerance,
        effectiveSettings.maxNormalDeviation,
        effectiveSettings.maxAspectRatio
    )
    if meshResult is None:
        return None

    sourcePoints, sourceTriangles = meshResult
    remeshedPoints = meshRemesh.projectMeshPointsToFaces(sourcePoints, faces)
    remeshedPoints, remeshedTriangles = compactMesh(remeshedPoints, sourceTriangles)
    if not remeshedTriangles:
        return None

    sourceBoundaryVertexPoints = topology.getBoundaryVertexPointsFromFaces(faces)
    protectedCornerVertexIndices = getProtectedCornerVertexIndices(remeshedPoints, sourceBoundaryVertexPoints)

    targetEdgeLength = accuracy
    if targetEdgeLength <= constants.MeshRemesh.acvdMinTriangleArea:
        return None

    for _ in range(effectiveSettings.iterationCount):
        remeshedPoints, remeshedTriangles, protectedCornerVertexIndices, splitPerformed = splitLongEdges(
            remeshedPoints,
            remeshedTriangles,
            faces,
            targetEdgeLength * constants.MeshRemesh.isotropicSplitEdgeFactor,
            protectedCornerVertexIndices
        )
        remeshedPoints, remeshedTriangles, protectedCornerVertexIndices, collapsePerformed = collapseShortEdges(
            remeshedPoints,
            remeshedTriangles,
            faces,
            targetEdgeLength * constants.MeshRemesh.isotropicCollapseEdgeFactor,
            protectedCornerVertexIndices
        )
        remeshedTriangles, flipPerformed = flipEdgesForValence(
            remeshedPoints,
            remeshedTriangles
        )
        remeshedPoints, smoothingPerformed = smoothPoints(
            remeshedPoints,
            remeshedTriangles,
            faces,
            effectiveSettings.smoothingBlend
        )
        remeshedPoints = projectInteriorPointsToFaces(remeshedPoints, remeshedTriangles, faces)
        remeshedPoints, remeshedTriangles, protectedCornerVertexIndices = compactMeshWithProtectedVertices(
            remeshedPoints,
            remeshedTriangles,
            protectedCornerVertexIndices
        )

        if not remeshedTriangles:
            return None

        if not splitPerformed and not collapsePerformed and not flipPerformed and not smoothingPerformed:
            break

    remeshedPoints = projectInteriorPointsToFaces(remeshedPoints, remeshedTriangles, faces)
    remeshedPoints, remeshedTriangles, protectedCornerVertexIndices = compactMeshWithProtectedVertices(
        remeshedPoints,
        remeshedTriangles,
        protectedCornerVertexIndices
    )
    if not remeshedTriangles:
        return None

    lockedVertexIndices = getBoundaryVertexIndices(remeshedTriangles) | protectedCornerVertexIndices
    if constants.MeshRemesh.surfaceCurvatureCompensationEnabled:
        remeshedPoints = meshRemesh.compensatePointsForSurfaceCurvature(
            remeshedPoints,
            remeshedTriangles,
            faces,
            lockedVertexIndices,
            constants.MeshRemesh.midpointSurfaceCompensationIterations,
            constants.MeshRemesh.midpointSurfaceCompensationBlend
        )
        remeshedPoints, remeshedTriangles, protectedCornerVertexIndices = compactMeshWithProtectedVertices(
            remeshedPoints,
            remeshedTriangles,
            protectedCornerVertexIndices
        )
        if not remeshedTriangles:
            return None

    pointAreas, _ = meshCore.buildPointAreas(remeshedPoints, remeshedTriangles)
    clusterCount = len(remeshedPoints)
    assignments = list(range(clusterCount))
    usedClusterIndices = list(range(clusterCount))
    clusterNormals = meshAcvd.computeClusterNormals(
        remeshedPoints,
        remeshedTriangles,
        pointAreas,
        assignments,
        clusterCount
    )

    return meshAcvd.AcvdTessellationResult(
        topology.toFlatMeshData(remeshedPoints, remeshedTriangles),
        clusterNormals,
        usedClusterIndices
    )

def splitLongEdges(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices],
    faces: list[adsk.fusion.BRepFace],
    maximumLength: float,
    protectedCornerVertexIndices: set[int]
) -> tuple[list[adsk.core.Point3D], list[meshCore.TriangleIndices], set[int], bool]:
    """Split all edges longer than the requested threshold."""
    if maximumLength <= 0.0:
        return points, triangles, protectedCornerVertexIndices, False

    splitEdgeIndices: dict[tuple[int, int], int] = {}
    nextPoints: list[adsk.core.Point3D] | None = None

    for startIndex, endIndex in meshCore.buildUniqueEdges(triangles):
        startPoint = points[startIndex]
        endPoint = points[endIndex]
        if startPoint.distanceTo(endPoint) <= maximumLength:
            continue

        if nextPoints is None:
            nextPoints = points[:]

        midpoint = adsk.core.Point3D.create(
            (startPoint.x + endPoint.x) * 0.5,
            (startPoint.y + endPoint.y) * 0.5,
            (startPoint.z + endPoint.z) * 0.5
        )
        splitEdgeIndices[(min(startIndex, endIndex), max(startIndex, endIndex))] = len(nextPoints)
        nextPoints.append(meshRemesh.getSnappedPointOrCopy(faces, midpoint))

    if not splitEdgeIndices:
        return points, triangles, protectedCornerVertexIndices, False

    nextTriangles: list[meshCore.TriangleIndices] = []

    for triangle in triangles:
        polygonIndices = buildSplitPolygonIndices(triangle, splitEdgeIndices)
        if len(polygonIndices) == 3:
            nextTriangles.append(triangle)
            continue

        referenceNormal = getTriangleNormal(points, triangle)
        polygonTriangles = triangulatePolygonByQuality(nextPoints or points, polygonIndices, referenceNormal)
        if not polygonTriangles:
            nextTriangles.append(triangle)
            continue

        nextTriangles.extend(polygonTriangles)

    compactPoints, compactTriangles, compactProtectedCornerVertexIndices = compactMeshWithProtectedVertices(
        nextPoints or points,
        nextTriangles,
        protectedCornerVertexIndices
    )
    return compactPoints, compactTriangles, compactProtectedCornerVertexIndices, True


def buildSplitPolygonIndices(
    triangle: meshCore.TriangleIndices,
    splitEdgeIndices: dict[tuple[int, int], int]
) -> list[int]:
    """Build a triangle boundary sequence with inserted split vertices."""
    index0, index1, index2 = triangle
    polygonIndices = [index0]
    midpoint01 = splitEdgeIndices.get((min(index0, index1), max(index0, index1)))
    if midpoint01 is not None:
        polygonIndices.append(midpoint01)

    polygonIndices.append(index1)
    midpoint12 = splitEdgeIndices.get((min(index1, index2), max(index1, index2)))
    if midpoint12 is not None:
        polygonIndices.append(midpoint12)

    polygonIndices.append(index2)
    midpoint20 = splitEdgeIndices.get((min(index2, index0), max(index2, index0)))
    if midpoint20 is not None:
        polygonIndices.append(midpoint20)

    return polygonIndices


def collapseShortEdges(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices],
    faces: list[adsk.fusion.BRepFace],
    minimumLength: float,
    protectedBoundaryVertexIndices: set[int]
) -> tuple[list[adsk.core.Point3D], list[meshCore.TriangleIndices], set[int], bool]:
    """Collapse edges shorter than the requested threshold."""
    if minimumLength <= 0.0:
        return points, triangles, protectedBoundaryVertexIndices, False

    collapsedPoints = points[:]
    collapsedTriangles = triangles[:]
    anyCollapsePerformed = False

    while True:
        boundaryEdges = set(topology.getBoundaryEdges(collapsedTriangles))
        boundaryVertexIndices = {vertexIndex for edge in boundaryEdges for vertexIndex in edge}
        edgeCandidatesWithLengths: list[tuple[tuple[int, int], float]] = []

        for edge in meshCore.buildUniqueEdges(collapsedTriangles):
            edgeLength = collapsedPoints[edge[0]].distanceTo(collapsedPoints[edge[1]])
            if edgeLength < minimumLength:
                edgeCandidatesWithLengths.append((edge, edgeLength))

        edgeCandidatesWithLengths.sort(key=lambda item: item[1])
        collapsePerformed = False

        for (startIndex, endIndex), _ in edgeCandidatesWithLengths:
            if startIndex in protectedBoundaryVertexIndices or endIndex in protectedBoundaryVertexIndices:
                continue

            edgeKey = (min(startIndex, endIndex), max(startIndex, endIndex))
            if startIndex in boundaryVertexIndices or endIndex in boundaryVertexIndices:
                if edgeKey not in boundaryEdges:
                    continue

            candidatePoints, candidateTriangles = collapseEdge(
                collapsedPoints,
                collapsedTriangles,
                faces,
                startIndex,
                endIndex,
                edgeKey in boundaryEdges
            )
            if not candidateTriangles:
                continue

            if not isCollapseImprovingQuality(
                collapsedPoints,
                collapsedTriangles,
                candidatePoints,
                candidateTriangles,
                startIndex,
                endIndex
            ):
                continue

            collapsedPoints, collapsedTriangles, protectedBoundaryVertexIndices = compactMeshWithProtectedVertices(
                candidatePoints,
                candidateTriangles,
                protectedBoundaryVertexIndices
            )
            collapsePerformed = True
            anyCollapsePerformed = True
            break

        if not collapsePerformed:
            return collapsedPoints, collapsedTriangles, protectedBoundaryVertexIndices, anyCollapsePerformed


def collapseEdge(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices],
    faces: list[adsk.fusion.BRepFace],
    startIndex: int,
    endIndex: int,
    boundaryEdgeCollapsed: bool
) -> tuple[list[adsk.core.Point3D], list[meshCore.TriangleIndices]]:
    """Collapse one edge to its midpoint and update all incident triangles."""
    keepIndex = min(startIndex, endIndex)
    removeIndex = max(startIndex, endIndex)
    midpoint = adsk.core.Point3D.create(
        (points[keepIndex].x + points[removeIndex].x) * 0.5,
        (points[keepIndex].y + points[removeIndex].y) * 0.5,
        (points[keepIndex].z + points[removeIndex].z) * 0.5
    )
    nextPoints = points[:]
    nextPoints[keepIndex] = midpoint if boundaryEdgeCollapsed else meshRemesh.getSnappedPointOrCopy(faces, midpoint)
    nextTriangles: list[meshCore.TriangleIndices] = []

    for triangle in triangles:
        remappedTriangle = tuple(
            keepIndex if vertexIndex == removeIndex else vertexIndex
            for vertexIndex in triangle
        )
        if len(set(remappedTriangle)) < 3:
            continue

        nextTriangles.append(remappedTriangle)

    return nextPoints, nextTriangles


def flipEdgesForValence(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices]
) -> tuple[list[meshCore.TriangleIndices], bool]:
    """Flip interior edges when doing so improves local valence deviation."""
    flippedTriangles = triangles[:]
    boundaryEdges = set(topology.getBoundaryEdges(flippedTriangles))
    boundaryVertexIndices = {vertexIndex for edge in boundaryEdges for vertexIndex in edge}
    edgeToTriangleIndices = buildEdgeToTriangleIndices(flippedTriangles)
    vertexNeighbors = meshCore.buildVertexNeighbors(flippedTriangles)
    blockedTriangleIndices: set[int] = set()
    flipPerformed = False

    for edge, triangleIndices in edgeToTriangleIndices.items():
        if len(triangleIndices) != 2 or edge in boundaryEdges:
            continue

        firstTriangleIndex, secondTriangleIndex = triangleIndices
        if firstTriangleIndex in blockedTriangleIndices or secondTriangleIndex in blockedTriangleIndices:
            continue

        firstTriangle = flippedTriangles[firstTriangleIndex]
        secondTriangle = flippedTriangles[secondTriangleIndex]
        firstOppositeIndex = getOppositeVertexIndex(firstTriangle, edge)
        secondOppositeIndex = getOppositeVertexIndex(secondTriangle, edge)
        if firstOppositeIndex is None or secondOppositeIndex is None or firstOppositeIndex == secondOppositeIndex:
            continue

        if secondOppositeIndex in vertexNeighbors.get(firstOppositeIndex, set()):
            continue

        currentDeviation = getValenceDeviation(
            edge[0],
            edge[1],
            firstOppositeIndex,
            secondOppositeIndex,
            vertexNeighbors,
            boundaryVertexIndices
        )
        proposedDeviation = getFlippedValenceDeviation(
            edge[0],
            edge[1],
            firstOppositeIndex,
            secondOppositeIndex,
            vertexNeighbors,
            boundaryVertexIndices
        )
        if proposedDeviation >= currentDeviation:
            continue

        currentMinimumQuality = min(
            computeTriangleQuality(points, firstTriangle),
            computeTriangleQuality(points, secondTriangle)
        )

        normalReference = getTriangleNormal(points, firstTriangle)
        normalReference.add(getTriangleNormal(points, secondTriangle))
        firstReplacement = orientTriangle(
            points,
            (firstOppositeIndex, secondOppositeIndex, edge[1]),
            normalReference
        )
        secondReplacement = orientTriangle(
            points,
            (secondOppositeIndex, firstOppositeIndex, edge[0]),
            normalReference
        )
        if firstReplacement is None or secondReplacement is None:
            continue

        proposedMinimumQuality = min(
            computeTriangleQuality(points, firstReplacement),
            computeTriangleQuality(points, secondReplacement)
        )
        if proposedMinimumQuality + constants.MeshRemesh.acvdMinTriangleArea < currentMinimumQuality:
            continue

        flippedTriangles[firstTriangleIndex] = firstReplacement
        flippedTriangles[secondTriangleIndex] = secondReplacement
        blockedTriangleIndices.add(firstTriangleIndex)
        blockedTriangleIndices.add(secondTriangleIndex)
        flipPerformed = True

    if not flipPerformed:
        return triangles, False

    return compactMesh(points, flippedTriangles)[1], True


def smoothPoints(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices],
    faces: list[adsk.fusion.BRepFace],
    blendFactor: float
) -> tuple[list[adsk.core.Point3D], bool]:
    """Apply one Laplacian smoothing pass and project moved vertices back to the faces."""
    if blendFactor <= 0.0:
        return points[:], False

    clampedBlendFactor = max(0.0, min(1.0, blendFactor))
    vertexNeighbors = meshCore.buildVertexNeighbors(triangles)
    boundaryVertexIndices = getBoundaryVertexIndices(triangles)
    incidentTriangleIndices = buildIncidentTriangleIndices(triangles)
    smoothedPoints = points[:]
    smoothingPerformed = False

    for pointIndex, point in enumerate(points):
        if pointIndex in boundaryVertexIndices:
            continue

        neighborIndices = vertexNeighbors.get(pointIndex, set())
        if len(neighborIndices) < 2:
            continue

        averageX = 0.0
        averageY = 0.0
        averageZ = 0.0

        for neighborIndex in neighborIndices:
            neighborPoint = points[neighborIndex]
            averageX += neighborPoint.x
            averageY += neighborPoint.y
            averageZ += neighborPoint.z

        neighborCount = len(neighborIndices)
        averagePoint = adsk.core.Point3D.create(
            averageX / neighborCount,
            averageY / neighborCount,
            averageZ / neighborCount
        )
        blendedPoint = adsk.core.Point3D.create(
            point.x + (averagePoint.x - point.x) * clampedBlendFactor,
            point.y + (averagePoint.y - point.y) * clampedBlendFactor,
            point.z + (averagePoint.z - point.z) * clampedBlendFactor
        )
        candidatePoint = meshRemesh.getSnappedPointOrCopy(faces, blendedPoint)
        if not isPointMoveImprovingQuality(
            points,
            triangles,
            incidentTriangleIndices.get(pointIndex, []),
            pointIndex,
            candidatePoint
        ):
            continue

        smoothedPoints[pointIndex] = candidatePoint
        if point.distanceTo(candidatePoint) > constants.MeshRemesh.acvdMinTriangleArea:
            smoothingPerformed = True

    return smoothedPoints, smoothingPerformed


def projectInteriorPointsToFaces(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices],
    faces: list[adsk.fusion.BRepFace] | None
) -> list[adsk.core.Point3D]:
    """Project only interior mesh vertices back to faces while keeping the open boundary fixed."""
    if not faces or not points:
        return points

    boundaryVertexIndices = getBoundaryVertexIndices(triangles)
    projectedPoints = [point.copy() for point in points]

    for pointIndex, point in enumerate(projectedPoints):
        if pointIndex in boundaryVertexIndices:
            continue

        projectedPoints[pointIndex] = meshRemesh.getSnappedPointOrCopy(faces, point)

    return projectedPoints


def triangulatePolygonByQuality(
    points: list[adsk.core.Point3D],
    polygonIndices: list[int],
    referenceNormal: adsk.core.Vector3D
) -> list[meshCore.TriangleIndices]:
    """Triangulate an ordered polygon by maximizing the minimum triangle quality."""
    if len(polygonIndices) < 3:
        return []

    if len(polygonIndices) == 3:
        orientedTriangle = orientTriangle(points, tuple(polygonIndices), referenceNormal)
        if orientedTriangle is None:
            return []

        return [orientedTriangle]

    if len(polygonIndices) == 4:
        return triangulateQuadByQuality(points, polygonIndices, referenceNormal)

    if len(polygonIndices) == 5:
        return triangulatePentagonByQuality(points, polygonIndices, referenceNormal)

    if len(polygonIndices) == 6:
        return triangulateHexagonByQuality(points, polygonIndices, referenceNormal)

    bestTriangles: list[meshCore.TriangleIndices] = []
    bestScore = -1.0

    for vertexOffset in range(len(polygonIndices)):
        previousIndex = polygonIndices[(vertexOffset - 1) % len(polygonIndices)]
        currentIndex = polygonIndices[vertexOffset]
        nextIndex = polygonIndices[(vertexOffset + 1) % len(polygonIndices)]
        earTriangle = orientTriangle(points, (previousIndex, currentIndex, nextIndex), referenceNormal)
        if earTriangle is None:
            continue

        reducedPolygon = polygonIndices[:vertexOffset] + polygonIndices[vertexOffset + 1:]
        remainingTriangles = triangulatePolygonByQuality(points, reducedPolygon, referenceNormal)
        if len(remainingTriangles) != len(reducedPolygon) - 2:
            continue

        candidateTriangles = [earTriangle] + remainingTriangles
        candidateScore = min(computeTriangleQuality(points, triangle) for triangle in candidateTriangles)
        if candidateScore > bestScore:
            bestScore = candidateScore
            bestTriangles = candidateTriangles

    return bestTriangles


def buildEdgeToTriangleIndices(
    triangles: list[meshCore.TriangleIndices]
) -> dict[tuple[int, int], list[int]]:
    """Map each undirected edge to the indices of incident triangles."""
    edgeToTriangleIndices: dict[tuple[int, int], list[int]] = {}

    for triangleIndex, triangle in enumerate(triangles):
        index0, index1, index2 = triangle
        for startIndex, endIndex in ((index0, index1), (index1, index2), (index2, index0)):
            edge = (min(startIndex, endIndex), max(startIndex, endIndex))
            edgeToTriangleIndices.setdefault(edge, []).append(triangleIndex)

    return edgeToTriangleIndices


def triangulateQuadByQuality(
    points: list[adsk.core.Point3D],
    polygonIndices: list[int],
    referenceNormal: adsk.core.Vector3D
) -> list[meshCore.TriangleIndices]:
    """Triangulate a quad by evaluating both diagonals."""
    candidateIndexOrders = [
        [(polygonIndices[0], polygonIndices[1], polygonIndices[2]), (polygonIndices[0], polygonIndices[2], polygonIndices[3])],
        [(polygonIndices[1], polygonIndices[2], polygonIndices[3]), (polygonIndices[1], polygonIndices[3], polygonIndices[0])]
    ]
    return getBestTriangleSet(points, candidateIndexOrders, referenceNormal)


def triangulatePentagonByQuality(
    points: list[adsk.core.Point3D],
    polygonIndices: list[int],
    referenceNormal: adsk.core.Vector3D
) -> list[meshCore.TriangleIndices]:
    """Triangulate a pentagon by testing every ear plus the best remaining quad split."""
    candidateIndexOrders: list[list[meshCore.TriangleIndices]] = []

    for vertexOffset in range(len(polygonIndices)):
        previousIndex = polygonIndices[(vertexOffset - 1) % len(polygonIndices)]
        currentIndex = polygonIndices[vertexOffset]
        nextIndex = polygonIndices[(vertexOffset + 1) % len(polygonIndices)]
        reducedPolygon = polygonIndices[:vertexOffset] + polygonIndices[vertexOffset + 1:]

        for quadTriangles in (
            [
                (reducedPolygon[0], reducedPolygon[1], reducedPolygon[2]),
                (reducedPolygon[0], reducedPolygon[2], reducedPolygon[3])
            ],
            [
                (reducedPolygon[1], reducedPolygon[2], reducedPolygon[3]),
                (reducedPolygon[1], reducedPolygon[3], reducedPolygon[0])
            ]
        ):
            candidateIndexOrders.append([
                (previousIndex, currentIndex, nextIndex),
                quadTriangles[0],
                quadTriangles[1]
            ])

    return getBestTriangleSet(points, candidateIndexOrders, referenceNormal)


def triangulateHexagonByQuality(
    points: list[adsk.core.Point3D],
    polygonIndices: list[int],
    referenceNormal: adsk.core.Vector3D
) -> list[meshCore.TriangleIndices]:
    """Triangulate a hexagon by testing every ear and the two diagonal choices of the remaining pentagon."""
    candidateIndexOrders: list[list[meshCore.TriangleIndices]] = []

    for vertexOffset in range(len(polygonIndices)):
        previousIndex = polygonIndices[(vertexOffset - 1) % len(polygonIndices)]
        currentIndex = polygonIndices[vertexOffset]
        nextIndex = polygonIndices[(vertexOffset + 1) % len(polygonIndices)]
        reducedPolygon = polygonIndices[:vertexOffset] + polygonIndices[vertexOffset + 1:]

        for reducedVertexOffset in range(len(reducedPolygon)):
            reducedPreviousIndex = reducedPolygon[(reducedVertexOffset - 1) % len(reducedPolygon)]
            reducedCurrentIndex = reducedPolygon[reducedVertexOffset]
            reducedNextIndex = reducedPolygon[(reducedVertexOffset + 1) % len(reducedPolygon)]
            quadPolygon = reducedPolygon[:reducedVertexOffset] + reducedPolygon[reducedVertexOffset + 1:]

            for quadTriangles in (
                [
                    (quadPolygon[0], quadPolygon[1], quadPolygon[2]),
                    (quadPolygon[0], quadPolygon[2], quadPolygon[3])
                ],
                [
                    (quadPolygon[1], quadPolygon[2], quadPolygon[3]),
                    (quadPolygon[1], quadPolygon[3], quadPolygon[0])
                ]
            ):
                candidateIndexOrders.append([
                    (previousIndex, currentIndex, nextIndex),
                    (reducedPreviousIndex, reducedCurrentIndex, reducedNextIndex),
                    quadTriangles[0],
                    quadTriangles[1]
                ])

    return getBestTriangleSet(points, candidateIndexOrders, referenceNormal)


def getBestTriangleSet(
    points: list[adsk.core.Point3D],
    candidateIndexOrders: list[list[meshCore.TriangleIndices]],
    referenceNormal: adsk.core.Vector3D
) -> list[meshCore.TriangleIndices]:
    """Return the valid candidate triangle set with the best minimum quality."""
    bestTriangles: list[meshCore.TriangleIndices] = []
    bestScore = -1.0

    for candidateIndexOrder in candidateIndexOrders:
        candidateTriangles: list[meshCore.TriangleIndices] = []
        candidateScore = 1.0

        for candidateTriangle in candidateIndexOrder:
            orientedTriangle = orientTriangle(points, candidateTriangle, referenceNormal)
            if orientedTriangle is None:
                candidateTriangles = []
                break

            candidateTriangles.append(orientedTriangle)
            candidateScore = min(candidateScore, computeTriangleQuality(points, orientedTriangle))

        if candidateTriangles and candidateScore > bestScore:
            bestScore = candidateScore
            bestTriangles = candidateTriangles

    return bestTriangles


def buildIncidentTriangleIndices(
    triangles: list[meshCore.TriangleIndices]
) -> dict[int, list[int]]:
    """Map each vertex index to incident triangle indices."""
    incidentTriangleIndices: dict[int, list[int]] = {}

    for triangleIndex, triangle in enumerate(triangles):
        for vertexIndex in triangle:
            incidentTriangleIndices.setdefault(vertexIndex, []).append(triangleIndex)

    return incidentTriangleIndices


def getOppositeVertexIndex(
    triangle: meshCore.TriangleIndices,
    edge: tuple[int, int]
) -> int | None:
    """Return the vertex of a triangle that does not belong to the given edge."""
    for vertexIndex in triangle:
        if vertexIndex not in edge:
            return vertexIndex

    return None


def getValenceDeviation(
    startIndex: int,
    endIndex: int,
    firstOppositeIndex: int,
    secondOppositeIndex: int,
    vertexNeighbors: dict[int, set[int]],
    boundaryVertexIndices: set[int]
) -> int:
    """Compute current valence deviation for the four vertices around one edge."""
    return sum(
        abs(len(vertexNeighbors.get(vertexIndex, set())) - getIdealValence(vertexIndex, boundaryVertexIndices))
        for vertexIndex in (startIndex, endIndex, firstOppositeIndex, secondOppositeIndex)
    )


def getFlippedValenceDeviation(
    startIndex: int,
    endIndex: int,
    firstOppositeIndex: int,
    secondOppositeIndex: int,
    vertexNeighbors: dict[int, set[int]],
    boundaryVertexIndices: set[int]
) -> int:
    """Compute valence deviation after a hypothetical edge flip."""
    currentValences = {
        startIndex: len(vertexNeighbors.get(startIndex, set())),
        endIndex: len(vertexNeighbors.get(endIndex, set())),
        firstOppositeIndex: len(vertexNeighbors.get(firstOppositeIndex, set())),
        secondOppositeIndex: len(vertexNeighbors.get(secondOppositeIndex, set()))
    }
    proposedValences = {
        startIndex: currentValences[startIndex] - 1,
        endIndex: currentValences[endIndex] - 1,
        firstOppositeIndex: currentValences[firstOppositeIndex] + 1,
        secondOppositeIndex: currentValences[secondOppositeIndex] + 1
    }

    return sum(
        abs(proposedValences[vertexIndex] - getIdealValence(vertexIndex, boundaryVertexIndices))
        for vertexIndex in proposedValences
    )


def getIdealValence(vertexIndex: int, boundaryVertexIndices: set[int]) -> int:
    """Return the ideal isotropic valence for one vertex."""
    if vertexIndex in boundaryVertexIndices:
        return constants.MeshRemesh.isotropicBoundaryValence

    return constants.MeshRemesh.isotropicInteriorValence


def getTriangleNormal(
    points: list[adsk.core.Point3D],
    triangle: meshCore.TriangleIndices
) -> adsk.core.Vector3D:
    """Compute an unnormalized triangle normal."""
    index0, index1, index2 = triangle
    return points[index0].vectorTo(points[index1]).crossProduct(points[index0].vectorTo(points[index2]))


def orientTriangle(
    points: list[adsk.core.Point3D],
    triangle: meshCore.TriangleIndices,
    normalReference: adsk.core.Vector3D
) -> meshCore.TriangleIndices | None:
    """Orient a triangle so that it agrees with the provided normal reference."""
    triangleNormal = getTriangleNormal(points, triangle)
    if triangleNormal.length <= constants.MeshRemesh.acvdMinTriangleArea:
        return None

    if normalReference.length > constants.MeshRemesh.acvdMinTriangleArea and triangleNormal.dotProduct(normalReference) < 0.0:
        return triangle[0], triangle[2], triangle[1]

    return triangle


def getBoundaryVertexIndices(triangles: list[meshCore.TriangleIndices]) -> set[int]:
    """Return the set of vertices that lie on the open mesh boundary."""
    return {vertexIndex for edge in topology.getBoundaryEdges(triangles) for vertexIndex in edge}


def getProtectedCornerVertexIndices(
    points: list[adsk.core.Point3D],
    sourceBoundaryVertexPoints: list[adsk.core.Point3D]
) -> set[int]:
    """Match original source boundary corner vertices to mesh vertices once and mark them as protected."""
    return topology.getMatchedVertexIndices(
        points,
        sourceBoundaryVertexPoints,
        constants.MeshRemesh.acvdMinimumSamplingDistanceCm
    )


def compactMeshWithProtectedVertices(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices],
    protectedVertexIndices: set[int]
) -> tuple[list[adsk.core.Point3D], list[meshCore.TriangleIndices], set[int]]:
    """Compact a mesh and remap protected vertex indices to the compacted indexing."""
    validTriangles: list[meshCore.TriangleIndices] = []
    usedVertexIndices: set[int] = set()
    triangleKeys: set[tuple[int, int, int]] = set()

    for triangle in triangles:
        if len(set(triangle)) < 3:
            continue

        triangleNormal = getTriangleNormal(points, triangle)
        if triangleNormal.length <= constants.MeshRemesh.acvdMinTriangleArea:
            continue

        triangleKey = tuple(sorted(triangle))
        if triangleKey in triangleKeys:
            continue

        triangleKeys.add(triangleKey)
        validTriangles.append(triangle)
        usedVertexIndices.update(triangle)

    if not validTriangles:
        return [point.copy() for point in points], [], set()

    sortedVertexIndices = sorted(usedVertexIndices)
    indexMap = {
        sourceIndex: targetIndex
        for targetIndex, sourceIndex in enumerate(sortedVertexIndices)
    }
    compactPoints = [points[sourceIndex].copy() for sourceIndex in sortedVertexIndices]
    compactTriangles = [
        (indexMap[index0], indexMap[index1], indexMap[index2])
        for index0, index1, index2 in validTriangles
    ]
    compactProtectedVertexIndices = {
        indexMap[sourceIndex]
        for sourceIndex in protectedVertexIndices
        if sourceIndex in indexMap
    }

    return compactPoints, compactTriangles, compactProtectedVertexIndices


def isCollapseImprovingQuality(
    previousPoints: list[adsk.core.Point3D],
    previousTriangles: list[meshCore.TriangleIndices],
    candidatePoints: list[adsk.core.Point3D],
    candidateTriangles: list[meshCore.TriangleIndices],
    startIndex: int,
    endIndex: int
) -> bool:
    """Accept an edge collapse only when local triangle quality does not get worse."""
    affectedPreviousTriangles = [
        triangle
        for triangle in previousTriangles
        if startIndex in triangle or endIndex in triangle
    ]
    previousMinimumQuality = getMinimumTriangleQuality(previousPoints, affectedPreviousTriangles)
    remappedIndex = min(startIndex, endIndex)
    affectedCandidateTriangles = [
        triangle
        for triangle in candidateTriangles
        if remappedIndex in triangle
    ]
    candidateMinimumQuality = getMinimumTriangleQuality(candidatePoints, affectedCandidateTriangles)
    if candidateMinimumQuality <= constants.MeshRemesh.acvdMinTriangleArea:
        return False

    if previousMinimumQuality <= constants.MeshRemesh.acvdMinTriangleArea:
        return True

    return candidateMinimumQuality + constants.MeshRemesh.acvdMinTriangleArea >= previousMinimumQuality * 0.85


def isPointMoveImprovingQuality(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices],
    incidentTriangleIndices: list[int],
    pointIndex: int,
    candidatePoint: adsk.core.Point3D
) -> bool:
    """Accept a smoothing move only when the one-ring quality stays stable."""
    if not incidentTriangleIndices:
        return False

    previousTriangles = [triangles[triangleIndex] for triangleIndex in incidentTriangleIndices]
    previousMinimumQuality = getMinimumTriangleQuality(points, previousTriangles)
    candidateMinimumQuality = getMinimumTriangleQualityWithMovedPoint(
        points,
        previousTriangles,
        pointIndex,
        candidatePoint
    )
    if candidateMinimumQuality <= constants.MeshRemesh.acvdMinTriangleArea:
        return False

    if previousMinimumQuality <= constants.MeshRemesh.acvdMinTriangleArea:
        return True

    return candidateMinimumQuality + constants.MeshRemesh.acvdMinTriangleArea >= previousMinimumQuality * 0.9


def getMinimumTriangleQuality(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices]
) -> float:
    """Return the minimum normalized quality of the provided triangles."""
    if not triangles:
        return 0.0

    return min(computeTriangleQuality(points, triangle) for triangle in triangles)


def getMinimumTriangleQualityWithMovedPoint(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices],
    movedPointIndex: int,
    movedPoint: adsk.core.Point3D
) -> float:
    """Return the minimum triangle quality after replacing one vertex position."""
    if not triangles:
        return 0.0

    return min(
        computeTriangleQualityWithMovedPoint(points, triangle, movedPointIndex, movedPoint)
        for triangle in triangles
    )


def computeTriangleQualityWithMovedPoint(
    points: list[adsk.core.Point3D],
    triangle: meshCore.TriangleIndices,
    movedPointIndex: int,
    movedPoint: adsk.core.Point3D
) -> float:
    """Compute triangle quality after substituting one vertex position without copying the whole mesh."""
    index0, index1, index2 = triangle
    point0 = movedPoint if index0 == movedPointIndex else points[index0]
    point1 = movedPoint if index1 == movedPointIndex else points[index1]
    point2 = movedPoint if index2 == movedPointIndex else points[index2]
    edgeLength01 = point0.distanceTo(point1)
    edgeLength12 = point1.distanceTo(point2)
    edgeLength20 = point2.distanceTo(point0)
    edgeLengthSquaredSum = (
        edgeLength01 * edgeLength01
        + edgeLength12 * edgeLength12
        + edgeLength20 * edgeLength20
    )
    if edgeLengthSquaredSum <= constants.MeshRemesh.acvdMinTriangleArea:
        return 0.0

    area = point0.vectorTo(point1).crossProduct(point0.vectorTo(point2)).length * 0.5
    if area <= constants.MeshRemesh.acvdMinTriangleArea:
        return 0.0

    return min(1.0, (4.0 * 1.7320508075688772 * area) / edgeLengthSquaredSum)


def computeTriangleQuality(
    points: list[adsk.core.Point3D],
    triangle: meshCore.TriangleIndices
) -> float:
    """Compute a normalized triangle quality in the range [0, 1]."""
    index0, index1, index2 = triangle
    edgeLength01 = points[index0].distanceTo(points[index1])
    edgeLength12 = points[index1].distanceTo(points[index2])
    edgeLength20 = points[index2].distanceTo(points[index0])
    edgeLengthSquaredSum = (
        edgeLength01 * edgeLength01
        + edgeLength12 * edgeLength12
        + edgeLength20 * edgeLength20
    )
    if edgeLengthSquaredSum <= constants.MeshRemesh.acvdMinTriangleArea:
        return 0.0

    area = getTriangleNormal(points, triangle).length * 0.5
    if area <= constants.MeshRemesh.acvdMinTriangleArea:
        return 0.0

    return min(1.0, (4.0 * 1.7320508075688772 * area) / edgeLengthSquaredSum)


def compactMesh(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices]
) -> tuple[list[adsk.core.Point3D], list[meshCore.TriangleIndices]]:
    """Remove degenerate triangles, deduplicate faces, and compact vertex indices."""
    validTriangles: list[meshCore.TriangleIndices] = []
    usedVertexIndices: set[int] = set()
    triangleKeys: set[tuple[int, int, int]] = set()

    for triangle in triangles:
        if len(set(triangle)) < 3:
            continue

        triangleNormal = getTriangleNormal(points, triangle)
        if triangleNormal.length <= constants.MeshRemesh.acvdMinTriangleArea:
            continue

        triangleKey = tuple(sorted(triangle))
        if triangleKey in triangleKeys:
            continue

        triangleKeys.add(triangleKey)
        validTriangles.append(triangle)
        usedVertexIndices.update(triangle)

    if not validTriangles:
        return [point.copy() for point in points], []

    sortedVertexIndices = sorted(usedVertexIndices)
    indexMap = {
        sourceIndex: targetIndex
        for targetIndex, sourceIndex in enumerate(sortedVertexIndices)
    }
    compactPoints = [points[sourceIndex].copy() for sourceIndex in sortedVertexIndices]
    compactTriangles = [
        (indexMap[index0], indexMap[index1], indexMap[index2])
        for index0, index1, index2 in validTriangles
    ]

    return compactPoints, compactTriangles
