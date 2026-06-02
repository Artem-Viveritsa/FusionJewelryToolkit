import adsk.core
import adsk.fusion

from ... import constants
from . import core as meshCore


def getPointMergeKey(point: adsk.core.Point3D, tolerance: float) -> tuple[int, int, int]:
    """Build a stable grid key for welding close vertices."""
    inverseTolerance = 1.0 / tolerance

    return (
        int(round(point.x * inverseTolerance)),
        int(round(point.y * inverseTolerance)),
        int(round(point.z * inverseTolerance))
    )


def getOrCreateMergedPointIndex(
    point: adsk.core.Point3D,
    tolerance: float,
    points: list[adsk.core.Point3D],
    pointsByKey: dict[tuple[int, int, int], list[int]]
) -> int:
    """Reuse an existing welded vertex when it is within tolerance."""
    key = getPointMergeKey(point, tolerance)

    for offsetX in range(-1, 2):
        for offsetY in range(-1, 2):
            for offsetZ in range(-1, 2):
                neighborKey = (key[0] + offsetX, key[1] + offsetY, key[2] + offsetZ)

                for existingIndex in pointsByKey.get(neighborKey, []):
                    if points[existingIndex].distanceTo(point) <= tolerance:
                        return existingIndex

    pointIndex = len(points)
    points.append(point.copy())
    pointsByKey.setdefault(key, []).append(pointIndex)
    return pointIndex


def meshFaces(
    faces: list[adsk.fusion.BRepFace],
    accuracy: float,
    surfaceTolerance: float = constants.MeshRemesh.surfaceTolerance,
    maxNormalDeviation: float = constants.MeshRemesh.maxNormalDeviation,
    maxAspectRatio: float = constants.MeshRemesh.maxAspectRatio
) -> tuple[list[adsk.core.Point3D], list[meshCore.TriangleIndices]] | None:
    """Tessellate faces separately and weld shared boundary vertices."""
    if not faces:
        return None

    mergeTolerance = constants.MeshRemesh.acvdMinimumSamplingDistanceCm
    points: list[adsk.core.Point3D] = []
    triangles: list[meshCore.TriangleIndices] = []
    pointsByKey: dict[tuple[int, int, int], list[int]] = {}

    for face in faces:
        mesh = meshCore.createFaceMesh(
            face,
            accuracy,
            surfaceTolerance,
            maxNormalDeviation,
            maxAspectRatio
        )
        if mesh is None or mesh.triangleCount == 0:
            continue

        facePoints = list(mesh.nodeCoordinates)
        faceIndices = mesh.nodeIndices
        localToGlobal: dict[int, int] = {}

        for localIndex, point in enumerate(facePoints):
            localToGlobal[localIndex] = getOrCreateMergedPointIndex(point, mergeTolerance, points, pointsByKey)

        for triangleIndex in range(mesh.triangleCount):
            indexOffset = triangleIndex * 3
            index0 = localToGlobal[faceIndices[indexOffset]]
            index1 = localToGlobal[faceIndices[indexOffset + 1]]
            index2 = localToGlobal[faceIndices[indexOffset + 2]]

            if len({index0, index1, index2}) < 3:
                continue

            triangles.append((index0, index1, index2))

    if len(points) < 3 or not triangles:
        return None

    return points, triangles


def toFlatMeshData(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices]
) -> meshCore.TriangleMeshData:
    """Convert point and triangle lists to flat mesh arrays."""
    coordinates: list[float] = []
    coordinateIndices: list[int] = []

    for point in points:
        coordinates.extend((point.x, point.y, point.z))

    for index0, index1, index2 in triangles:
        coordinateIndices.extend((index0, index1, index2))

    return meshCore.TriangleMeshData(coordinates, coordinateIndices)


def getBoundaryEdges(triangles: list[meshCore.TriangleIndices]) -> list[tuple[int, int]]:
    """Return all edges that belong to a single triangle."""
    edgeUseCounts: dict[tuple[int, int], int] = {}

    for index0, index1, index2 in triangles:
        for startIndex, endIndex in ((index0, index1), (index1, index2), (index2, index0)):
            edgeKey = (min(startIndex, endIndex), max(startIndex, endIndex))
            edgeUseCounts[edgeKey] = edgeUseCounts.get(edgeKey, 0) + 1

    return [edgeKey for edgeKey, useCount in edgeUseCounts.items() if useCount == 1]


def buildBoundaryAdjacency(boundaryEdges: list[tuple[int, int]]) -> dict[int, set[int]]:
    """Build adjacency for boundary vertices."""
    adjacency: dict[int, set[int]] = {}

    for startIndex, endIndex in boundaryEdges:
        adjacency.setdefault(startIndex, set()).add(endIndex)
        adjacency.setdefault(endIndex, set()).add(startIndex)

    return adjacency


def buildBoundaryChains(boundaryEdges: list[tuple[int, int]]) -> list[list[int]]:
    """Build ordered boundary chains from boundary edges."""
    adjacency = buildBoundaryAdjacency(boundaryEdges)
    visitedEdges: set[tuple[int, int]] = set()
    boundaryChains: list[list[int]] = []

    def edgeKey(startIndex: int, endIndex: int) -> tuple[int, int]:
        return min(startIndex, endIndex), max(startIndex, endIndex)

    def walkChain(startIndex: int, nextIndex: int) -> list[int]:
        chain = [startIndex, nextIndex]
        visitedEdges.add(edgeKey(startIndex, nextIndex))
        previousIndex = startIndex
        currentIndex = nextIndex

        while True:
            nextCandidates = [
                neighborIndex
                for neighborIndex in adjacency[currentIndex]
                if neighborIndex != previousIndex and edgeKey(currentIndex, neighborIndex) not in visitedEdges
            ]
            if not nextCandidates:
                break

            nextVertexIndex = nextCandidates[0]
            visitedEdges.add(edgeKey(currentIndex, nextVertexIndex))
            previousIndex = currentIndex
            currentIndex = nextVertexIndex

            if currentIndex == chain[0]:
                break

            chain.append(currentIndex)

        return chain

    startVertices = sorted(
        vertexIndex
        for vertexIndex, neighborIndices in adjacency.items()
        if len(neighborIndices) == 1
    )

    for startIndex in startVertices:
        for neighborIndex in sorted(adjacency[startIndex]):
            if edgeKey(startIndex, neighborIndex) in visitedEdges:
                continue

            boundaryChains.append(walkChain(startIndex, neighborIndex))

    for startIndex in sorted(adjacency):
        for neighborIndex in sorted(adjacency[startIndex]):
            if edgeKey(startIndex, neighborIndex) in visitedEdges:
                continue

            boundaryChains.append(walkChain(startIndex, neighborIndex))

    return boundaryChains


def isClosedBoundaryChain(
    chain: list[int],
    adjacency: dict[int, set[int]]
) -> bool:
    """Check whether a boundary chain forms a loop."""
    if len(chain) < 3:
        return False

    return chain[0] in adjacency.get(chain[-1], set()) and len(adjacency.get(chain[0], set())) > 1


def getEdgesFromFaces(
    faces: list[adsk.fusion.BRepFace],
    onlyOpenBoundaryEdges: bool = False
) -> list[adsk.fusion.BRepEdge]:
    """Return unique BRep edges from the selected faces."""
    if not faces:
        return []

    selectedFaceTokens = {face.entityToken for face in faces if face is not None}
    edgesByToken: dict[str, adsk.fusion.BRepEdge] = {}

    for face in faces:
        if face is None:
            continue

        for faceEdge in face.edges:
            edge = adsk.fusion.BRepEdge.cast(faceEdge)
            if edge is None:
                continue

            if onlyOpenBoundaryEdges:
                selectedAdjacentFaceCount = sum(
                    1
                    for adjacentFace in edge.faces
                    if adjacentFace is not None and adjacentFace.entityToken in selectedFaceTokens
                )
                if selectedAdjacentFaceCount != 1:
                    continue

            edgesByToken[edge.entityToken] = edge

    return list(edgesByToken.values())


def getBoundaryEdgesFromFaces(
    faces: list[adsk.fusion.BRepFace]
) -> list[adsk.fusion.BRepEdge]:
    """Return BRep edges that belong to the open boundary of the selected faces."""
    return getEdgesFromFaces(faces, True)


def getBoundaryVertexPointsFromFaces(
    faces: list[adsk.fusion.BRepFace]
) -> list[adsk.core.Point3D]:
    """Return unique BRep boundary vertex points for the selected faces."""
    mergeTolerance = constants.MeshRemesh.acvdMinimumSamplingDistanceCm
    boundaryPoints: list[adsk.core.Point3D] = []
    pointsByKey: dict[tuple[int, int, int], list[int]] = {}

    for edge in getBoundaryEdgesFromFaces(faces):
        for vertex in (edge.startVertex, edge.endVertex):
            if vertex is None:
                continue

            getOrCreateMergedPointIndex(vertex.geometry, mergeTolerance, boundaryPoints, pointsByKey)

    return boundaryPoints


def getMatchedVertexIndices(
    points: list[adsk.core.Point3D],
    targetPoints: list[adsk.core.Point3D],
    tolerance: float
) -> set[int]:
    """Match target points to existing mesh vertices within the given tolerance."""
    return set(getMatchedTargetPointsByVertexIndex(points, targetPoints, tolerance).keys())


def getMatchedTargetPointsByVertexIndex(
    points: list[adsk.core.Point3D],
    targetPoints: list[adsk.core.Point3D],
    tolerance: float
) -> dict[int, adsk.core.Point3D]:
    """Match target points to mesh vertices and return the exact target point for each match."""
    if not points or not targetPoints:
        return {}

    pointIndicesByKey: dict[tuple[int, int, int], list[int]] = {}
    matchedTargetPointsByVertexIndex: dict[int, adsk.core.Point3D] = {}

    for pointIndex, point in enumerate(points):
        pointKey = getPointMergeKey(point, tolerance)
        pointIndicesByKey.setdefault(pointKey, []).append(pointIndex)

    for targetPoint in targetPoints:
        targetKey = getPointMergeKey(targetPoint, tolerance)
        nearestVertexIndex: int | None = None
        nearestDistance = tolerance

        for offsetX in range(-1, 2):
            for offsetY in range(-1, 2):
                for offsetZ in range(-1, 2):
                    neighborKey = (targetKey[0] + offsetX, targetKey[1] + offsetY, targetKey[2] + offsetZ)

                    for pointIndex in pointIndicesByKey.get(neighborKey, []):
                        distance = points[pointIndex].distanceTo(targetPoint)
                        if distance > nearestDistance:
                            continue

                        nearestDistance = distance
                        nearestVertexIndex = pointIndex

        if nearestVertexIndex is None:
            continue

        existingPoint = matchedTargetPointsByVertexIndex.get(nearestVertexIndex)
        if existingPoint is None or points[nearestVertexIndex].distanceTo(targetPoint) < points[nearestVertexIndex].distanceTo(existingPoint):
            matchedTargetPointsByVertexIndex[nearestVertexIndex] = adsk.core.Point3D.create(
                targetPoint.x,
                targetPoint.y,
                targetPoint.z
            )

    return matchedTargetPointsByVertexIndex


def getBoundarySeedIndices(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices],
    spacing: float,
    protectedVertexIndices: set[int]
) -> list[int]:
    """Sample boundary seed vertices while preserving protected vertices and uniform open-edge spacing."""
    boundaryEdges = getBoundaryEdges(triangles)
    if not boundaryEdges:
        return []

    adjacency = buildBoundaryAdjacency(boundaryEdges)
    boundaryChains = buildBoundaryChains(boundaryEdges)
    selectedSeedIndices: list[int] = []
    selectedSeedSet: set[int] = set()
    effectiveSpacing = max(spacing, constants.MeshRemesh.acvdMinimumSamplingDistanceCm)

    def addSeed(vertexIndex: int) -> None:
        if vertexIndex in selectedSeedSet:
            return

        selectedSeedIndices.append(vertexIndex)
        selectedSeedSet.add(vertexIndex)

    def getSegmentVertexIndices(
        chainIndices: list[int],
        startListIndex: int,
        endListIndex: int,
        closedChain: bool
    ) -> list[int]:
        if not chainIndices:
            return []

        if not closedChain or startListIndex <= endListIndex:
            return chainIndices[startListIndex:endListIndex + 1]

        return chainIndices[startListIndex:] + chainIndices[:endListIndex + 1]

    def addUniformSeedsOnSegment(segmentVertexIndices: list[int]) -> None:
        if len(segmentVertexIndices) < 2:
            return

        cumulativeDistances = [0.0]
        for vertexListIndex in range(1, len(segmentVertexIndices)):
            cumulativeDistances.append(
                cumulativeDistances[-1]
                + points[segmentVertexIndices[vertexListIndex - 1]].distanceTo(points[segmentVertexIndices[vertexListIndex]])
            )

        segmentLength = cumulativeDistances[-1]
        if segmentLength <= constants.MeshRemesh.acvdMinimumSamplingDistanceCm:
            addSeed(segmentVertexIndices[0])
            addSeed(segmentVertexIndices[-1])
            return

        intervalCount = max(1, int(round(segmentLength / effectiveSpacing)))
        addSeed(segmentVertexIndices[0])
        lastChosenVertexListIndex = 0

        for intervalIndex in range(1, intervalCount):
            targetDistance = segmentLength * intervalIndex / intervalCount
            candidateVertexListIndex = min(
                range(lastChosenVertexListIndex + 1, len(segmentVertexIndices) - 1),
                key=lambda vertexListIndex: abs(cumulativeDistances[vertexListIndex] - targetDistance),
                default=None
            )
            if candidateVertexListIndex is None or candidateVertexListIndex <= lastChosenVertexListIndex:
                continue

            addSeed(segmentVertexIndices[candidateVertexListIndex])
            lastChosenVertexListIndex = candidateVertexListIndex

        addSeed(segmentVertexIndices[-1])

    for chain in boundaryChains:
        if not chain:
            continue

        isClosedChain = isClosedBoundaryChain(chain, adjacency)
        chainProtectedVertices = {vertexIndex for vertexIndex in chain if vertexIndex in protectedVertexIndices}
        if not isClosedChain:
            chainProtectedVertices.add(chain[0])
            chainProtectedVertices.add(chain[-1])

        if isClosedChain:
            anchorVertexIndices = [vertexIndex for vertexIndex in chain if vertexIndex in chainProtectedVertices]
            if not anchorVertexIndices:
                anchorVertexIndices = [chain[0]]
        else:
            anchorVertexIndices = [vertexIndex for vertexIndex in chain if vertexIndex in chainProtectedVertices]

        if not anchorVertexIndices:
            continue

        anchorListIndices = [chain.index(vertexIndex) for vertexIndex in anchorVertexIndices]
        if isClosedChain:
            anchorListIndices = sorted(set(anchorListIndices))
            for anchorIndex in range(len(anchorListIndices)):
                startListIndex = anchorListIndices[anchorIndex]
                endListIndex = anchorListIndices[(anchorIndex + 1) % len(anchorListIndices)]
                segmentVertexIndices = getSegmentVertexIndices(chain, startListIndex, endListIndex, True)
                addUniformSeedsOnSegment(segmentVertexIndices)
        else:
            anchorListIndices = sorted(set(anchorListIndices))
            for anchorIndex in range(len(anchorListIndices) - 1):
                startListIndex = anchorListIndices[anchorIndex]
                endListIndex = anchorListIndices[anchorIndex + 1]
                segmentVertexIndices = getSegmentVertexIndices(chain, startListIndex, endListIndex, False)
                addUniformSeedsOnSegment(segmentVertexIndices)

    protectedSeeds = [vertexIndex for vertexIndex in selectedSeedIndices if vertexIndex in protectedVertexIndices]
    regularSeeds = [vertexIndex for vertexIndex in selectedSeedIndices if vertexIndex not in protectedVertexIndices]
    return protectedSeeds + regularSeeds