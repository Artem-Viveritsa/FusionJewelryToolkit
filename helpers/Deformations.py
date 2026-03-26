import math
from typing import Optional

import adsk.core
import adsk.fusion

from .. import constants
from . import Bodies


def createTaperBody(
    body: adsk.fusion.BRepBody,
    axisDir: adsk.core.Vector3D,
    pivotPoint: adsk.core.Point3D,
    angle: float
) -> Optional[adsk.fusion.BRepBody]:
    """Create a tapered temporary body along an arbitrary axis.

    The pivot point is the neutral cross-section (scale = 1). Cross-sections
    before the pivot along the axis expand, cross-sections after contract.
    """
    nurbsBody = Bodies.convertBodyToNurbs(body)
    if nurbsBody is None:
        return None

    axisX = axisDir.x
    axisY = axisDir.y
    axisZ = axisDir.z
    pivotX = pivotPoint.x
    pivotY = pivotPoint.y
    pivotZ = pivotPoint.z
    pivotProjection = pivotX * axisX + pivotY * axisY + pivotZ * axisZ

    minProjection: Optional[float] = None
    maxProjection: Optional[float] = None

    for vertex in nurbsBody.vertices:
        projection = vertex.geometry.x * axisX + vertex.geometry.y * axisY + vertex.geometry.z * axisZ
        if minProjection is None or projection < minProjection:
            minProjection = projection
        if maxProjection is None or projection > maxProjection:
            maxProjection = projection

    if minProjection is None or maxProjection is None:
        return None

    height = maxProjection - minProjection
    if height == 0:
        return None

    tanAngle = math.tan(angle)

    def transformPoint(point: adsk.core.Point3D) -> adsk.core.Point3D:
        dx = point.x - pivotX
        dy = point.y - pivotY
        dz = point.z - pivotZ
        t = point.x * axisX + point.y * axisY + point.z * axisZ - pivotProjection
        scale = max(constants.Deformations.minimumTaperScale, 1.0 - (t / height) * tanAngle)
        return adsk.core.Point3D.create(
            pivotX + t * axisX + (dx - t * axisX) * scale,
            pivotY + t * axisY + (dy - t * axisY) * scale,
            pivotZ + t * axisZ + (dz - t * axisZ) * scale
        )

    bodyDefinition = adsk.fusion.BRepBodyDefinition.create()

    deformedVertexPoints: dict[int, adsk.core.Point3D] = {}
    vertexMap: dict[int, adsk.fusion.BRepVertexDefinition] = {}

    for vertex in nurbsBody.vertices:
        deformedPoint = transformPoint(vertex.geometry)
        deformedVertexPoints[vertex.tempId] = deformedPoint
        vertexMap[vertex.tempId] = bodyDefinition.createVertexDefinition(deformedPoint)

    edgeMap: dict[int, adsk.fusion.BRepEdgeDefinition] = {}

    for edge in nurbsBody.edges:
        nurbsCurve = adsk.core.NurbsCurve3D.cast(edge.geometry) or getattr(edge.geometry, 'asNurbsCurve', None)
        if nurbsCurve is None:
            return None

        success, controlPoints, degree, knots, isRational, weights, isPeriodic = nurbsCurve.getData()
        if not success:
            return None

        newPoints = [transformPoint(p) for p in controlPoints]
        if not isPeriodic and len(newPoints) >= 2:
            newPoints[0] = deformedVertexPoints[edge.startVertex.tempId].copy()
            newPoints[-1] = deformedVertexPoints[edge.endVertex.tempId].copy()

        if isRational:
            deformedCurve = adsk.core.NurbsCurve3D.createRational(newPoints, degree, knots, weights, isPeriodic)
        else:
            deformedCurve = adsk.core.NurbsCurve3D.createNonRational(newPoints, degree, knots, isPeriodic)

        edgeMap[edge.tempId] = bodyDefinition.createEdgeDefinitionByCurve(
            vertexMap[edge.startVertex.tempId],
            vertexMap[edge.endVertex.tempId],
            deformedCurve
        )

    for lump in nurbsBody.lumps:
        lumpDefinition = bodyDefinition.lumpDefinitions.add()
        for shell in lump.shells:
            shellDefinition = lumpDefinition.shellDefinitions.add()
            for face in shell.faces:
                nurbsSurface = adsk.core.NurbsSurface.cast(face.geometry)
                if nurbsSurface is None:
                    return None

                success, degreeU, degreeV, countU, countV, controlPoints, knotsU, knotsV, weights, propsU, propsV = nurbsSurface.getData()
                if not success:
                    return None

                deformedSurface = adsk.core.NurbsSurface.create(
                    degreeU, degreeV, countU, countV,
                    [transformPoint(p) for p in controlPoints],
                    knotsU, knotsV, weights, propsU, propsV
                )
                if deformedSurface is None:
                    return None

                faceDefinition = shellDefinition.faceDefinitions.add(deformedSurface, face.isParamReversed)

                for loop in sorted(face.loops, key=lambda l: not l.isOuter):
                    loopDefinition = faceDefinition.loopDefinitions.add()
                    for coEdge in loop.coEdges:
                        loopDefinition.bRepCoEdgeDefinitions.add(edgeMap[coEdge.edge.tempId], coEdge.isOpposedToEdge)

    return bodyDefinition.createBody()


def createFFDBody(
    body: adsk.fusion.BRepBody,
    controlPointOffsets: list[list[float]],
    gridSizeX: int = 3,
    gridSizeY: int = 3,
    gridSizeZ: int = 3
) -> Optional[adsk.fusion.BRepBody]:
    """Create a free-form deformed body using a variable-resolution Bernstein control lattice.

    The bounding box of the source body defines the neutral lattice. Each control
    point may be displaced by the corresponding offset triplet. Points on the body
    are deformed via trivariate Bernstein polynomials of degree (gridSize - 1) per axis.
    Args:
        body: The source body to deform.
        controlPointOffsets: Flat list of gridSizeX*gridSizeY*gridSizeZ offset triplets
            ``[dx, dy, dz]``. Index: ``i*gridSizeY*gridSizeZ + j*gridSizeZ + k``.
        gridSizeX: Number of control points along the X axis (2..5).
        gridSizeY: Number of control points along the Y axis (2..5).
        gridSizeZ: Number of control points along the Z axis (2..5).

    Returns:
        The deformed temporary BRep body or ``None`` on failure.
    """
    nurbsBody = Bodies.convertBodyToNurbs(body)
    if nurbsBody is None:
        return None

    bbox = body.boundingBox
    bboxMinX = bbox.minPoint.x
    bboxMinY = bbox.minPoint.y
    bboxMinZ = bbox.minPoint.z

    epsilon = 1e-6
    sizeX = max(bbox.maxPoint.x - bboxMinX, epsilon)
    sizeY = max(bbox.maxPoint.y - bboxMinY, epsilon)
    sizeZ = max(bbox.maxPoint.z - bboxMinZ, epsilon)

    degreeX = gridSizeX - 1
    degreeY = gridSizeY - 1
    degreeZ = gridSizeZ - 1

    def bernstein(index: int, degree: int, t: float) -> float:
        """Evaluate the Bernstein basis polynomial B(index, degree, t)."""
        result = 1.0
        for j in range(1, degree + 1):
            if j <= index:
                result *= t * (degree - j + 1) / j
            else:
                result *= (1.0 - t)
        return result

    def peakBernstein(index: int, degree: int) -> float:
        """Peak value of B(index, degree) used for amplification correction."""
        if degree == 0:
            return 1.0
        if index == 0 or index == degree:
            return 1.0
        tPeak = index / degree
        return bernstein(index, degree, tPeak)

    lattice: list[list[list[adsk.core.Point3D]]] = [
        [[None for _ in range(gridSizeZ)] for _ in range(gridSizeY)]
        for _ in range(gridSizeX)
    ]

    for i in range(gridSizeX):
        for j in range(gridSizeY):
            for k in range(gridSizeZ):
                idx = i * gridSizeY * gridSizeZ + j * gridSizeZ + k
                dx, dy, dz = controlPointOffsets[idx]
                amp = 1.0 / (peakBernstein(i, degreeX) * peakBernstein(j, degreeY) * peakBernstein(k, degreeZ))
                lattice[i][j][k] = adsk.core.Point3D.create(
                    bboxMinX + (i / degreeX) * sizeX + dx * amp,
                    bboxMinY + (j / degreeY) * sizeY + dy * amp,
                    bboxMinZ + (k / degreeZ) * sizeZ + dz * amp,
                )

    def transformPoint(point: adsk.core.Point3D) -> adsk.core.Point3D:
        s = max(0.0, min(1.0, (point.x - bboxMinX) / sizeX))
        t = max(0.0, min(1.0, (point.y - bboxMinY) / sizeY))
        u = max(0.0, min(1.0, (point.z - bboxMinZ) / sizeZ))

        x, y, z = 0.0, 0.0, 0.0
        for i in range(gridSizeX):
            bi = bernstein(i, degreeX, s)
            for j in range(gridSizeY):
                bj = bernstein(j, degreeY, t)
                bij = bi * bj
                for k in range(gridSizeZ):
                    bk = bernstein(k, degreeZ, u)
                    weight = bij * bk
                    cp = lattice[i][j][k]
                    x += weight * cp.x
                    y += weight * cp.y
                    z += weight * cp.z

        return adsk.core.Point3D.create(x, y, z)

    bodyDefinition = adsk.fusion.BRepBodyDefinition.create()

    deformedVertexPoints: dict[int, adsk.core.Point3D] = {}
    vertexMap: dict[int, adsk.fusion.BRepVertexDefinition] = {}

    for vertex in nurbsBody.vertices:
        deformedPoint = transformPoint(vertex.geometry)
        deformedVertexPoints[vertex.tempId] = deformedPoint
        vertexMap[vertex.tempId] = bodyDefinition.createVertexDefinition(deformedPoint)

    edgeMap: dict[int, adsk.fusion.BRepEdgeDefinition] = {}

    for edge in nurbsBody.edges:
        nurbsCurve = adsk.core.NurbsCurve3D.cast(edge.geometry) or getattr(edge.geometry, 'asNurbsCurve', None)
        if nurbsCurve is None:
            return None

        success, controlPoints, degree, knots, isRational, weights, isPeriodic = nurbsCurve.getData()
        if not success:
            return None

        newPoints = [transformPoint(p) for p in controlPoints]
        if not isPeriodic and len(newPoints) >= 2:
            newPoints[0] = deformedVertexPoints[edge.startVertex.tempId].copy()
            newPoints[-1] = deformedVertexPoints[edge.endVertex.tempId].copy()

        if isRational:
            deformedCurve = adsk.core.NurbsCurve3D.createRational(newPoints, degree, knots, weights, isPeriodic)
        else:
            deformedCurve = adsk.core.NurbsCurve3D.createNonRational(newPoints, degree, knots, isPeriodic)

        edgeMap[edge.tempId] = bodyDefinition.createEdgeDefinitionByCurve(
            vertexMap[edge.startVertex.tempId],
            vertexMap[edge.endVertex.tempId],
            deformedCurve
        )

    for lump in nurbsBody.lumps:
        lumpDefinition = bodyDefinition.lumpDefinitions.add()
        for shell in lump.shells:
            shellDefinition = lumpDefinition.shellDefinitions.add()
            for face in shell.faces:
                nurbsSurface = adsk.core.NurbsSurface.cast(face.geometry)
                if nurbsSurface is None:
                    return None

                success, degreeU, degreeV, countU, countV, controlPoints, knotsU, knotsV, weights, propsU, propsV = nurbsSurface.getData()
                if not success:
                    return None

                deformedSurface = adsk.core.NurbsSurface.create(
                    degreeU, degreeV, countU, countV,
                    [transformPoint(p) for p in controlPoints],
                    knotsU, knotsV, weights, propsU, propsV
                )
                if deformedSurface is None:
                    return None

                faceDefinition = shellDefinition.faceDefinitions.add(deformedSurface, face.isParamReversed)

                for loop in sorted(face.loops, key=lambda l: not l.isOuter):
                    loopDefinition = faceDefinition.loopDefinitions.add()
                    for coEdge in loop.coEdges:
                        loopDefinition.bRepCoEdgeDefinitions.add(edgeMap[coEdge.edge.tempId], coEdge.isOpposedToEdge)

    return bodyDefinition.createBody()