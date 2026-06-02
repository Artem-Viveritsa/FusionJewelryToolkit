import math
import random
from typing import NamedTuple

import adsk.core
import adsk.fusion

from ... import constants


class TriangleMeshData(NamedTuple):
    """Flat triangle mesh representation shared across all mesh workflows."""

    coordinates: list[float]
    indices: list[int]


TriangleIndices = tuple[int, int, int]


def triangleMeshToMeshData(mesh: adsk.fusion.TriangleMesh) -> 'TriangleMeshData':
    """Convert a Fusion TriangleMesh to the internal flat mesh representation."""
    coordinates: list[float] = []
    for point in mesh.nodeCoordinates:
        coordinates.extend([point.x, point.y, point.z])
    return TriangleMeshData(coordinates, list(mesh.nodeIndices))


def createFaceMesh(
    face: adsk.fusion.BRepFace,
    maxSideLength: float,
    surfaceTolerance: float = constants.MeshRemesh.surfaceTolerance,
    maxNormalDeviation: float = constants.MeshRemesh.maxNormalDeviation,
    maxAspectRatio: float = constants.MeshRemesh.maxAspectRatio
) -> adsk.fusion.TriangleMesh | None:
    """Create a triangle mesh from a BRep face."""
    meshCalculator = face.meshManager.createMeshCalculator()
    meshCalculator.surfaceTolerance = surfaceTolerance
    meshCalculator.maxNormalDeviation = maxNormalDeviation
    meshCalculator.maxAspectRatio = maxAspectRatio
    meshCalculator.maxSideLength = maxSideLength
    return meshCalculator.calculate()


def getMeshDataPoints(meshData: TriangleMeshData | None) -> list[adsk.core.Point3D]:
    """Convert flat mesh coordinates to point objects."""
    if meshData is None:
        return []

    coordinates, _ = meshData
    points: list[adsk.core.Point3D] = []

    for coordinateIndex in range(0, len(coordinates) - len(coordinates) % 3, 3):
        points.append(adsk.core.Point3D.create(
            coordinates[coordinateIndex],
            coordinates[coordinateIndex + 1],
            coordinates[coordinateIndex + 2]
        ))

    return points


def getTriangleIndicesFromMeshData(meshData: TriangleMeshData | None) -> list[TriangleIndices]:
    """Convert flat mesh indices to triangle tuples."""
    if meshData is None:
        return []

    _, coordinateIndices = meshData
    triangles: list[TriangleIndices] = []

    for triangleIndex in range(0, len(coordinateIndices) - len(coordinateIndices) % 3, 3):
        triangles.append((
            coordinateIndices[triangleIndex],
            coordinateIndices[triangleIndex + 1],
            coordinateIndices[triangleIndex + 2]
        ))

    return triangles


def getMeshDataTriangles(
    meshData: TriangleMeshData | None
) -> list[tuple[adsk.core.Point3D, adsk.core.Point3D, adsk.core.Point3D]]:
    """Convert flat mesh data to triangle point triplets."""
    points = getMeshDataPoints(meshData)
    triangles = getTriangleIndicesFromMeshData(meshData)
    trianglePoints: list[tuple[adsk.core.Point3D, adsk.core.Point3D, adsk.core.Point3D]] = []

    for index0, index1, index2 in triangles:
        if index0 >= len(points) or index1 >= len(points) or index2 >= len(points):
            continue

        trianglePoints.append((points[index0], points[index1], points[index2]))

    return trianglePoints


def buildVertexNeighbors(triangles: list[TriangleIndices]) -> dict[int, set[int]]:
    """Build vertex adjacency from triangle connectivity."""
    neighbors: dict[int, set[int]] = {}

    for index0, index1, index2 in triangles:
        neighbors.setdefault(index0, set()).update((index1, index2))
        neighbors.setdefault(index1, set()).update((index0, index2))
        neighbors.setdefault(index2, set()).update((index0, index1))

    return neighbors


def buildUniqueEdges(triangles: list[TriangleIndices]) -> list[tuple[int, int]]:
    """Build the unique undirected edge list of a triangle mesh."""
    uniqueEdges: set[tuple[int, int]] = set()

    for index0, index1, index2 in triangles:
        uniqueEdges.add((min(index0, index1), max(index0, index1)))
        uniqueEdges.add((min(index1, index2), max(index1, index2)))
        uniqueEdges.add((min(index2, index0), max(index2, index0)))

    return sorted(uniqueEdges)


def getMeshTriangles(
    mesh: adsk.fusion.TriangleMesh | None
) -> list[tuple[adsk.core.Point3D, adsk.core.Point3D, adsk.core.Point3D]]:
    """Extract triangle point triplets from a Fusion triangle mesh."""
    if mesh is None:
        return []

    nodes = mesh.nodeCoordinates
    indices = mesh.nodeIndices
    triangles: list[tuple[adsk.core.Point3D, adsk.core.Point3D, adsk.core.Point3D]] = []

    for triangleIndex in range(mesh.triangleCount):
        indexOffset = triangleIndex * 3
        triangles.append((
            nodes[indices[indexOffset]],
            nodes[indices[indexOffset + 1]],
            nodes[indices[indexOffset + 2]]
        ))

    return triangles


def buildTriangleSamplingData(
    triangles: list[tuple[adsk.core.Point3D, adsk.core.Point3D, adsk.core.Point3D]]
) -> tuple[list[float], float]:
    """Build cumulative triangle areas for weighted random sampling."""
    cumulativeAreas: list[float] = []
    totalArea = 0.0

    for point0, point1, point2 in triangles:
        triangleArea = point0.vectorTo(point1).crossProduct(point0.vectorTo(point2)).length * 0.5
        totalArea += triangleArea
        cumulativeAreas.append(totalArea)

    return cumulativeAreas, totalArea


def samplePointOnTriangles(
    triangles: list[tuple[adsk.core.Point3D, adsk.core.Point3D, adsk.core.Point3D]],
    cumulativeAreas: list[float],
    totalArea: float,
    rng: random.Random
) -> adsk.core.Point3D | None:
    """Sample a random point on a triangle set."""
    if not triangles or not cumulativeAreas or totalArea <= 0.0:
        return None

    randomArea = rng.random() * totalArea
    leftIndex = 0
    rightIndex = len(cumulativeAreas) - 1

    while leftIndex < rightIndex:
        middleIndex = (leftIndex + rightIndex) // 2
        if randomArea <= cumulativeAreas[middleIndex]:
            rightIndex = middleIndex
        else:
            leftIndex = middleIndex + 1

    point0, point1, point2 = triangles[leftIndex]
    radius0 = math.sqrt(rng.random())
    radius1 = rng.random()
    weight0 = 1.0 - radius0
    weight1 = radius0 * (1.0 - radius1)
    weight2 = radius0 * radius1

    return adsk.core.Point3D.create(
        point0.x * weight0 + point1.x * weight1 + point2.x * weight2,
        point0.y * weight0 + point1.y * weight1 + point2.y * weight2,
        point0.z * weight0 + point1.z * weight1 + point2.z * weight2
    )


def subdivideTriangleMesh(
    points: list[adsk.core.Point3D],
    triangles: list[TriangleIndices]
) -> tuple[list[adsk.core.Point3D], list[TriangleIndices]]:
    """Perform one linear subdivision step on a triangle mesh."""
    subdividedPoints = points[:]
    midpointIndices: dict[tuple[int, int], int] = {}
    subdividedTriangles: list[TriangleIndices] = []

    def getMidpointIndex(startIndex: int, endIndex: int) -> int:
        edgeKey = (min(startIndex, endIndex), max(startIndex, endIndex))
        midpointIndex = midpointIndices.get(edgeKey)
        if midpointIndex is not None:
            return midpointIndex

        startPoint = subdividedPoints[startIndex]
        endPoint = subdividedPoints[endIndex]
        midpointIndex = len(subdividedPoints)
        midpointIndices[edgeKey] = midpointIndex
        subdividedPoints.append(adsk.core.Point3D.create(
            (startPoint.x + endPoint.x) * 0.5,
            (startPoint.y + endPoint.y) * 0.5,
            (startPoint.z + endPoint.z) * 0.5
        ))
        return midpointIndex

    for index0, index1, index2 in triangles:
        midpoint01 = getMidpointIndex(index0, index1)
        midpoint12 = getMidpointIndex(index1, index2)
        midpoint20 = getMidpointIndex(index2, index0)
        subdividedTriangles.extend([
            (index0, midpoint01, midpoint20),
            (midpoint01, index1, midpoint12),
            (midpoint20, midpoint12, index2),
            (midpoint01, midpoint12, midpoint20)
        ])

    return subdividedPoints, subdividedTriangles


def buildPointAreas(
    points: list[adsk.core.Point3D],
    triangles: list[TriangleIndices]
) -> tuple[list[float], float]:
    """Accumulate one-third of each triangle area onto its vertices."""
    pointAreas = [0.0] * len(points)
    totalArea = 0.0

    for index0, index1, index2 in triangles:
        triangleArea = points[index0].vectorTo(points[index1]).crossProduct(
            points[index0].vectorTo(points[index2])
        ).length * 0.5
        totalArea += triangleArea
        sharedArea = triangleArea / 3.0
        pointAreas[index0] += sharedArea
        pointAreas[index1] += sharedArea
        pointAreas[index2] += sharedArea

    return pointAreas, totalArea