import adsk.core
import adsk.fusion

from ... import constants
from . import core as meshCore


def projectPointAndNormalToFaces(
    faces: list[adsk.fusion.BRepFace] | None,
    point: adsk.core.Point3D
) -> tuple[adsk.core.Point3D, adsk.core.Vector3D] | None:
    """Project a point onto the closest source face and return its local surface normal."""
    if not faces:
        return None

    closestFace = faces[0]
    minimumDistance = float('inf')

    if len(faces) > 1:
        for face in faces:
            measurement = constants.measureManager.measureMinimumDistance(point, face)
            if measurement is None:
                continue

            if measurement.value < minimumDistance:
                minimumDistance = measurement.value
                closestFace = face

    measurement = constants.measureManager.measureMinimumDistance(point, closestFace)
    evaluator = closestFace.evaluator
    if evaluator is not None:
        try:
            success, parameter = evaluator.getParameterAtPoint(point)
            if not success and measurement is not None and measurement.positionTwo is not None:
                success, parameter = evaluator.getParameterAtPoint(measurement.positionTwo)
            if success:
                success, projectedPoint = evaluator.getPointAtParameter(parameter)
                if success and projectedPoint is not None:
                    success, normal = evaluator.getNormalAtParameter(parameter)
                    if success and normal is not None:
                        detachedNormal = normal.copy()
                        if detachedNormal.length > constants.MeshRemesh.acvdMinTriangleArea:
                            detachedNormal.normalize()
                        else:
                            detachedNormal = adsk.core.Vector3D.create(0.0, 0.0, 1.0)

                        return projectedPoint.copy(), detachedNormal
        except:
            pass

    if measurement is None or measurement.positionTwo is None:
        return None

    return measurement.positionTwo.copy(), adsk.core.Vector3D.create(0.0, 0.0, 1.0)


def projectPointToFaces(
    faces: list[adsk.fusion.BRepFace] | None,
    point: adsk.core.Point3D
) -> adsk.core.Point3D | None:
    """Project a point onto the closest source face."""
    projectionData = projectPointAndNormalToFaces(faces, point)
    if projectionData is None:
        return None

    projectedPoint, _ = projectionData
    return projectedPoint


def getProjectedPointAndNormalOrFallback(
    faces: list[adsk.fusion.BRepFace] | None,
    point: adsk.core.Point3D
) -> tuple[adsk.core.Point3D, adsk.core.Vector3D]:
    """Return projected point and normal, or detached fallback data when projection fails."""
    projectionData = projectPointAndNormalToFaces(faces, point)
    if projectionData is not None:
        projectedPoint, normal = projectionData
        return projectedPoint, normal

    return point.copy(), adsk.core.Vector3D.create(0.0, 0.0, 1.0)


def getSnappedPointOrCopy(
    faces: list[adsk.fusion.BRepFace] | None,
    point: adsk.core.Point3D
) -> adsk.core.Point3D:
    """Project a point to the source faces when possible, otherwise return a detached copy."""
    projectedPoint = projectPointToFaces(faces, point)
    if projectedPoint is not None:
        return projectedPoint

    return point.copy()


def projectMeshPointsToFaces(
    points: list[adsk.core.Point3D],
    faces: list[adsk.fusion.BRepFace] | None,
    startIndex: int = 0
) -> list[adsk.core.Point3D]:
    """Project mesh points to the source faces starting from the given index."""
    if not faces or startIndex >= len(points):
        return points

    projectedPoints = points[:]
    for pointIndex in range(max(0, startIndex), len(projectedPoints)):
        projectedPoints[pointIndex] = getSnappedPointOrCopy(faces, projectedPoints[pointIndex])

    return projectedPoints


def compensatePointsForSurfaceCurvature(
    points: list[adsk.core.Point3D],
    triangles: list[meshCore.TriangleIndices],
    faces: list[adsk.fusion.BRepFace] | None,
    lockedVertexIndices: set[int],
    iterationCount: int,
    blendFactor: float
) -> list[adsk.core.Point3D]:
    """Offset final vertices along face normals so edge midpoints better fit the surface."""
    if not faces or not points or not triangles or iterationCount <= 0 or blendFactor <= 0.0:
        return [point.copy() for point in points]

    clampedBlendFactor = max(0.0, min(1.0, blendFactor))
    compensatedPoints = [point.copy() for point in points]
    uniqueEdges = meshCore.buildUniqueEdges(triangles)

    for _ in range(iterationCount):
        projectionData = [getProjectedPointAndNormalOrFallback(faces, point) for point in compensatedPoints]
        offsetDeltaSums = [0.0] * len(compensatedPoints)
        offsetDeltaCounts = [0] * len(compensatedPoints)

        for startIndex, endIndex in uniqueEdges:
            midpoint = adsk.core.Point3D.create(
                (compensatedPoints[startIndex].x + compensatedPoints[endIndex].x) * 0.5,
                (compensatedPoints[startIndex].y + compensatedPoints[endIndex].y) * 0.5,
                (compensatedPoints[startIndex].z + compensatedPoints[endIndex].z) * 0.5
            )
            midpointOnSurface = projectPointToFaces(faces, midpoint)
            if midpointOnSurface is None:
                continue

            midpointDeviation = midpoint.vectorTo(midpointOnSurface)
            _, startNormal = projectionData[startIndex]
            _, endNormal = projectionData[endIndex]
            offsetDeltaSums[startIndex] += midpointDeviation.dotProduct(startNormal) * 2.0
            offsetDeltaCounts[startIndex] += 1
            offsetDeltaSums[endIndex] += midpointDeviation.dotProduct(endNormal) * 2.0
            offsetDeltaCounts[endIndex] += 1

        nextPoints = [point.copy() for point in compensatedPoints]

        for pointIndex, point in enumerate(compensatedPoints):
            if pointIndex in lockedVertexIndices:
                continue

            surfacePoint, surfaceNormal = projectionData[pointIndex]
            currentOffset = surfacePoint.vectorTo(point).dotProduct(surfaceNormal)
            if offsetDeltaCounts[pointIndex] == 0:
                nextPoints[pointIndex] = point.copy()
                continue

            averageOffsetDelta = offsetDeltaSums[pointIndex] / offsetDeltaCounts[pointIndex]
            nextOffset = currentOffset + averageOffsetDelta * clampedBlendFactor
            nextPoints[pointIndex] = adsk.core.Point3D.create(
                surfacePoint.x + surfaceNormal.x * nextOffset,
                surfacePoint.y + surfaceNormal.y * nextOffset,
                surfacePoint.z + surfaceNormal.z * nextOffset
            )

        compensatedPoints = nextPoints

    return compensatedPoints
