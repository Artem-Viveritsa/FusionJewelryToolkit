import math
import json
import traceback
from typing import List, Dict, Tuple, Set
import adsk.core
import adsk.fusion
from .. import strings, constants
from .showMessage import showMessage
from .Points import point3dToStr, strToPoint3d, averagePosition, findClosestPointIndex, triangleArea, isPointInTriangle, trianglesOverlap, toPlaneSpace, projectToPlane
from .Vectors import vector3dToStr, strToVector3d, averageVector


def getDataFromPointAndFace(face: adsk.fusion.BRepFace | adsk.fusion.ConstructionPlane, point: adsk.core.Point3D) -> tuple[adsk.core.Point3D, adsk.core.Vector3D, adsk.core.Vector3D, adsk.core.Vector3D]:
    """Get the surface point and orientation vectors (normal, length direction, width direction) at a given point on a face or construction plane.

    This function evaluates the face or construction plane geometry at the specified point to obtain:
    - The actual point on the face surface or projected point on the construction plane
    - The surface normal vector
    - The length direction (first derivative or U direction)
    - The width direction (cross product of normal and length direction or V direction)

    All vectors are normalized.

    Args:
        face: The BRepFace or ConstructionPlane to evaluate
        point: The 3D point to project onto the face or construction plane

    Returns:
        A tuple containing:
        - pointOnFace: The point on the face surface or construction plane
        - lengthDirection: Normalized first derivative vector or U direction
        - widthDirection: Normalized cross product vector (normal × lengthDirection) or V direction
        - normal: Normalized surface normal vector

    Returns (None, None, None, None) if evaluation fails.
    """
    try:
        if face is None or point is None:
            return None, None, None, None
        
        if face.objectType == adsk.fusion.ConstructionPlane.classType():
            constructionPlane: adsk.fusion.ConstructionPlane = face
            point = projectToPlane(point, constructionPlane)
            evaluator = constructionPlane.geometry.evaluator
        else:
            brepFace: adsk.fusion.BRepFace = face
            evaluator = brepFace.evaluator

        _, parameter = evaluator.getParameterAtPoint(point)
        _, pointOnFace = evaluator.getPointAtParameter(parameter)
        _, normal = evaluator.getNormalAtParameter(parameter)
        _, lengthDirection, _ = evaluator.getFirstDerivative(parameter)

        widthDirection = normal.crossProduct(lengthDirection)

        lengthDirection.normalize()
        widthDirection.normalize()
        normal.normalize()

        return pointOnFace, lengthDirection, widthDirection, normal

    except:
        showMessage(f'getDataFromPointAndFace: {traceback.format_exc()}\n', True)
        return None, None, None, None


def calculateThirdPointOrdered(pointStart: adsk.core.Point2D, pointEnd: adsk.core.Point2D, 
                               distanceStart: float, distanceEnd: float, 
                               minHeight: float = 0.01) -> adsk.core.Point2D:
    """
    Calculate the position of the third point of a triangle given two points and distances.
    
    Args:
        pointStart: First point of the edge
        pointEnd: Second point of the edge
        distanceStart: Distance from pointStart to the third point
        distanceEnd: Distance from pointEnd to the third point
        minHeight: Minimum height to prevent degenerate triangles
        
    Returns:
        Position of the third point
    """
    x1, y1 = pointStart.x, pointStart.y
    x2, y2 = pointEnd.x, pointEnd.y
    
    distance = pointStart.distanceTo(pointEnd)
    
    if distance == 0:
        return pointStart

    dx, dy = x2 - x1, y2 - y1
    a = (distanceStart * distanceStart - distanceEnd * distanceEnd + distance * distance) / (2 * distance)
    hSq = distanceStart * distanceStart - a * a
    
    if hSq < minHeight * minHeight:
        h = minHeight
    else:
        h = math.sqrt(hSq)
    
    x2Proj = x1 + a * dx / distance
    y2Proj = y1 + a * dy / distance
    
    return adsk.core.Point2D.create(x2Proj - h * dy / distance, y2Proj + h * dx / distance)


def calculateThirdPointWithCollisionCheck(
    pointStart: adsk.core.Point2D, 
    pointEnd: adsk.core.Point2D, 
    distanceStart: float, 
    distanceEnd: float,
    positions2D: Dict[int, adsk.core.Point2D],
    triangles: List[List[int]],
    visitedTriangles: Set[int],
    edgeToTriangles: Dict[Tuple[int, int], List[int]],
    u: int,
    v: int
) -> adsk.core.Point2D:
    """
    Calculate third point position, choosing the side that doesn't cause overlaps with triangles sharing the edge.
    
    Checks if the new triangle would overlap with triangles that share the edge (pointStart, pointEnd).
    """
    x1, y1 = pointStart.x, pointStart.y
    x2, y2 = pointEnd.x, pointEnd.y
    
    distance = pointStart.distanceTo(pointEnd)
    
    if distance == 0:
        return pointStart

    dx, dy = x2 - x1, y2 - y1
    a = (distanceStart * distanceStart - distanceEnd * distanceEnd + distance * distance) / (2 * distance)
    hSq = distanceStart * distanceStart - a * a
    h = math.sqrt(hSq) if hSq > 0 else 0
    
    x2Proj = x1 + a * dx / distance
    y2Proj = y1 + a * dy / distance
    
    point1 = adsk.core.Point2D.create(x2Proj - h * dy / distance, y2Proj + h * dx / distance)
    point2 = adsk.core.Point2D.create(x2Proj + h * dy / distance, y2Proj - h * dx / distance)
    
    newTriangle1 = (pointStart, pointEnd, point1)
    newTriangle2 = (pointStart, pointEnd, point2)
    
    # Find triangles that share the edge (u, v)
    edge = tuple(sorted((u, v)))
    neighborTriangles = edgeToTriangles.get(edge, [])
    
    overlaps1 = 0
    overlaps2 = 0
    
    for triangleIndex in neighborTriangles:
        if triangleIndex not in visitedTriangles:
            continue
        triangle = triangles[triangleIndex]
        if triangle[0] not in positions2D or triangle[1] not in positions2D or triangle[2] not in positions2D:
            continue
        
        existingTriangle = (
            positions2D[triangle[0]],
            positions2D[triangle[1]],
            positions2D[triangle[2]]
        )
        
        if trianglesOverlap(newTriangle1, existingTriangle):
            overlaps1 += 1
        if trianglesOverlap(newTriangle2, existingTriangle):
            overlaps2 += 1
    
    if overlaps1 > overlaps2:
        return point2
    else:
        return point1


def buildEdgeToTrianglesMap(triangles: List[List[int]]) -> Dict[Tuple[int, int], List[int]]:
    """Build adjacency map from edges to triangle indices."""
    edgeToTriangles = {}
    for triangleIndex, triangle in enumerate(triangles):
        for index in range(3):
            edge = tuple(sorted((triangle[index], triangle[(index + 1) % 3])))
            edgeToTriangles.setdefault(edge, []).append(triangleIndex)
    return edgeToTriangles


def unfoldTrianglesToPositions2D(
    triangles: List[List[int]], 
    points3D: List[adsk.core.Point3D], 
    originIndex: int,
    edgeToTriangles: Dict[Tuple[int, int], List[int]],
) -> Tuple[Dict[int, adsk.core.Point2D], Set[int]]:
    """
    Unfold triangles to 2D positions using BFS traversal.
    
    Args:
        triangles: List of triangles, each triangle is a list of 3 vertex indices.
        points3D: List of 3D points.
        originIndex: Index of the origin point (will be at 0,0).
        edgeToTriangles: Map from edge to triangle indices.
        relaxationIterations: Number of relaxation iterations.
        relaxationFactor: How much to move vertices towards their ideal positions (0-1).
    """
    startTriangle = next((triangleIndex for triangleIndex, triangle in enumerate(triangles) if originIndex in triangle), 0)
    
    positions2D = {}
    visitedTriangles = {startTriangle}
    queue = [startTriangle]
    
    triangleNodes = triangles[startTriangle]
    if originIndex in triangleNodes:
        index0 = originIndex
        index1 = triangleNodes[(triangleNodes.index(index0) + 1) % 3]
        index2 = triangleNodes[(triangleNodes.index(index0) + 2) % 3]
    else:
        index0, index1, index2 = triangleNodes[0], triangleNodes[1], triangleNodes[2]
    
    point0_3D, point1_3D, point2_3D = points3D[index0], points3D[index1], points3D[index2]
    
    positions2D[index0] = adsk.core.Point2D.create(0, 0)
    positions2D[index1] = adsk.core.Point2D.create(point0_3D.distanceTo(point1_3D), 0)
    positions2D[index2] = calculateThirdPointOrdered(
        positions2D[index0], positions2D[index1], 
        point0_3D.distanceTo(point2_3D), point1_3D.distanceTo(point2_3D)
    )
    
    while queue:
        currentTriangle = triangles[queue.pop(0)]
        
        for index in range(3):
            u, v = currentTriangle[index], currentTriangle[(index + 1) % 3]
            edgeKey = tuple(sorted((u, v)))
            
            for nextTriangleIndex in edgeToTriangles.get(edgeKey, []):
                if nextTriangleIndex in visitedTriangles:
                    continue
                
                visitedTriangles.add(nextTriangleIndex)
                queue.append(nextTriangleIndex)
                
                nextTriangle = triangles[nextTriangleIndex]
                w = next((vertexIndex for vertexIndex in nextTriangle if vertexIndex != u and vertexIndex != v), -1)
                
                if w == -1 or w in positions2D:
                    continue
                
                indexU, indexV = nextTriangle.index(u), nextTriangle.index(v)
                
                if (indexU + 1) % 3 == indexV:
                    pointStart, pointEnd = positions2D[u], positions2D[v]
                    pointStart3D, pointEnd3D = points3D[u], points3D[v]
                else:
                    pointStart, pointEnd = positions2D[v], positions2D[u]
                    pointStart3D, pointEnd3D = points3D[v], points3D[u]

                positions2D[w] = calculateThirdPointWithCollisionCheck(
                    pointStart, pointEnd,
                    pointStart3D.distanceTo(points3D[w]),
                    pointEnd3D.distanceTo(points3D[w]),
                    positions2D, triangles, visitedTriangles, edgeToTriangles, u, v
                )
    
    positions2D = edgeLengthRelaxation(
        positions2D, triangles, points3D, visitedTriangles, originIndex,
        iterations=100, stiffness=0.3
    )

    return positions2D, visitedTriangles


def edgeLengthRelaxation(
    positions2D: Dict[int, adsk.core.Point2D],
    triangles: List[List[int]],
    points3D: List[adsk.core.Point3D],
    visitedTriangles: Set[int],
    fixedIndex: int,
    iterations: int = 50,
    stiffness: float = 0.5
) -> Dict[int, adsk.core.Point2D]:
    """
    Apply edge-length preserving relaxation to all mesh vertices.
    
    Args:
        positions2D: 2D positions of vertices.
        triangles: List of triangles.
        points3D: Original 3D positions for target edge lengths.
        visitedTriangles: Set of valid triangle indices.
        fixedIndex: Index of vertex to keep fixed (origin).
        iterations: Number of relaxation iterations.
        stiffness: Correction factor per iteration (0-1).
        
    Returns:
        Dictionary of relaxed 2D positions.
    """
    if not positions2D:
        return positions2D
    
    edges: List[Tuple[int, int, float]] = []
    seenEdges: Set[Tuple[int, int]] = set()
    
    for triangleIndex in visitedTriangles:
        triangle = triangles[triangleIndex]
        for k in range(3):
            indexA, indexB = triangle[k], triangle[(k + 1) % 3]
            if indexA > indexB:
                indexA, indexB = indexB, indexA
            
            if (indexA, indexB) in seenEdges:
                continue
            
            if indexA in positions2D and indexB in positions2D:
                targetLength = points3D[indexA].distanceTo(points3D[indexB])
                edges.append((indexA, indexB, targetLength))
                seenEdges.add((indexA, indexB))
    
    posX = {idx: pos.x for idx, pos in positions2D.items()}
    posY = {idx: pos.y for idx, pos in positions2D.items()}
    
    for _ in range(iterations):
        for indexA, indexB, targetLength in edges:
            x1, y1 = posX[indexA], posY[indexA]
            x2, y2 = posX[indexB], posY[indexB]
            
            dx = x2 - x1
            dy = y2 - y1
            currentLength = math.sqrt(dx * dx + dy * dy)
            
            if currentLength < 1e-9:
                continue
            
            error = currentLength - targetLength
            correction = error * stiffness / currentLength
            
            correctionX = dx * correction
            correctionY = dy * correction
            
            weightA = 0.0 if indexA == fixedIndex else 1.0
            weightB = 0.0 if indexB == fixedIndex else 1.0
            weightTotal = weightA + weightB
            
            if weightTotal > 0:
                ratioA = weightA / weightTotal
                ratioB = weightB / weightTotal
                
                posX[indexA] += correctionX * ratioA
                posY[indexA] += correctionY * ratioA
                posX[indexB] -= correctionX * ratioB
                posY[indexB] -= correctionY * ratioB
    
    result = {idx: adsk.core.Point2D.create(posX[idx], posY[idx]) for idx in positions2D}
    return result


def calculateVertexNormals(
    triangles: List[List[int]],
    points3D: List[adsk.core.Point3D],
    visitedTriangles: Set[int]
) -> Dict[int, adsk.core.Vector3D]:
    """Calculate normal vectors for each vertex based on adjacent triangles.
    
    Args:
        triangles: List of triangles (each is a list of 3 vertex indices).
        points3D: List of 3D points.
        visitedTriangles: Set of triangle indices that were visited during unfolding.
    
    Returns:
        Dictionary mapping vertex index to its normal vector.
    """
    vertexToTriangles: Dict[int, List[int]] = {}
    
    for triangleIndex in visitedTriangles:
        triangle = triangles[triangleIndex]
        for vertexIndex in triangle:
            if vertexIndex not in vertexToTriangles:
                vertexToTriangles[vertexIndex] = []
            vertexToTriangles[vertexIndex].append(triangleIndex)
    
    vertexNormals: Dict[int, adsk.core.Vector3D] = {}
    
    for vertexIndex, triangleIndices in vertexToTriangles.items():
        triangleNormals = []
        
        for triangleIndex in triangleIndices:
            triangle = triangles[triangleIndex]
            if triangle[0] >= len(points3D) or triangle[1] >= len(points3D) or triangle[2] >= len(points3D):
                continue
                
            point0 = points3D[triangle[0]]
            point1 = points3D[triangle[1]]
            point2 = points3D[triangle[2]]
            
            vector1 = point0.vectorTo(point1)
            vector2 = point0.vectorTo(point2)
            
            normal = vector1.crossProduct(vector2)
            if normal.length > 1e-9:
                normal.normalize()
                triangleNormals.append(normal)
        
        if triangleNormals:
            averageNormal = averageVector(triangleNormals, normalize=True)
            if averageNormal:
                vertexNormals[vertexIndex] = averageNormal
    
    return vertexNormals


def interpolateDataInPointTriangles(
    centroidPosition: adsk.core.Point3D,
    pointDataList: List[Tuple[adsk.core.Point3D, adsk.core.Point3D, adsk.core.Vector3D, float]]
) -> Tuple[adsk.core.Point3D | None, adsk.core.Vector3D | None]:
    """
    Interpolate position and normal from surrounding point triangle.
    
    Args:
        centroidPosition: The centroid position to interpolate for.
        pointDataList: List of (point2D, sourcePoint3D, sourceNormal, distance) tuples.
    
    Returns:
        Tuple of (interpolatedPosition, interpolatedNormal) or (None, None) if no valid triangle found.
    """
    interpolatedPosition = None
    interpolatedNormal = None
    
    for i in range(len(pointDataList) - 2):
        point1, sourcePoint1, normal1, _ = pointDataList[i]
        point2, sourcePoint2, normal2, _ = pointDataList[i + 1]
        point3, sourcePoint3, normal3, _ = pointDataList[i + 2]

        if isPointInTriangle(centroidPosition.x, centroidPosition.y, point1.x, point1.y, point2.x, point2.y, point3.x, point3.y):
            areaTotal = triangleArea(point1.x, point1.y, point2.x, point2.y, point3.x, point3.y)
            if areaTotal > 0:
                a = triangleArea(centroidPosition.x, centroidPosition.y, point2.x, point2.y, point3.x, point3.y) / areaTotal
                b = triangleArea(centroidPosition.x, centroidPosition.y, point3.x, point3.y, point1.x, point1.y) / areaTotal
                c = triangleArea(centroidPosition.x, centroidPosition.y, point1.x, point1.y, point2.x, point2.y) / areaTotal

                interpolatedPosition = adsk.core.Point3D.create(
                    a * sourcePoint1.x + b * sourcePoint2.x + c * sourcePoint3.x,
                    a * sourcePoint1.y + b * sourcePoint2.y + c * sourcePoint3.y,
                    a * sourcePoint1.z + b * sourcePoint2.z + c * sourcePoint3.z
                )
                
                if normal1 and normal2 and normal3:
                    interpolatedNormal = adsk.core.Vector3D.create(
                        a * normal1.x + b * normal2.x + c * normal3.x,
                        a * normal1.y + b * normal2.y + c * normal3.y,
                        a * normal1.z + b * normal2.z + c * normal3.z
                    )
                    interpolatedNormal.normalize()
                
                break

    if interpolatedPosition is None:
        if len(pointDataList) >= 2:
            interpolatedPosition = averagePosition([pointDataList[0][1], pointDataList[1][1]])
            if pointDataList[0][2] and pointDataList[1][2]:
                interpolatedNormal = averageVector([pointDataList[0][2], pointDataList[1][2]], normalize=True)
        elif len(pointDataList) == 1:
            interpolatedPosition = pointDataList[0][1]
            interpolatedNormal = pointDataList[0][2]
    
    return interpolatedPosition, interpolatedNormal


def preprocess(
    positions2D: Dict[int, adsk.core.Point2D],
    xDirectionIndex: int = None,
    yDirectionIndex: int = None,
    points3D: List[adsk.core.Point3D] = None,
    normals: Dict[int, adsk.core.Vector3D] = None,
    sketch: adsk.fusion.Sketch = None,
    constructionPlane: adsk.fusion.ConstructionPlane = None,
    xOffset: float = 0.0,
    yOffset: float = 0.0
) -> Dict[int, adsk.core.Point3D]:
    """Apply rotation to align xDirectionIndex with X axis and transform to 3D construction plane coordinates.
    
    Args:
        positions2D: Dictionary mapping point indices to 2D positions.
        xDirectionIndex: Index of the point defining X direction.
        yDirectionIndex: Index of the point defining Y direction.
        points3D: Optional list of 3D points for attribute generation.
        normals: Optional dictionary of normal vectors for each point.
        sketch: Optional sketch to save attributes to.
        constructionPlane: Construction plane for 3D transformation.
        xOffset: Offset along the X axis of the construction plane in cm.
        yOffset: Offset along the Y axis of the construction plane in cm.
    
    Returns:
        Dictionary mapping point indices to transformed Point3D in construction plane space.
    """
    rotationAngle = 0.0
    reflectX = False
    if xDirectionIndex is not None and xDirectionIndex in positions2D:
        xDirectionPosition = positions2D[xDirectionIndex]
        rotationAngle = -math.atan2(xDirectionPosition.y, xDirectionPosition.x)
        
        if yDirectionIndex is not None and yDirectionIndex in positions2D:
            yDirectionPosition = positions2D[yDirectionIndex]
            rotatedYDirectionY = yDirectionPosition.x * math.sin(rotationAngle) + yDirectionPosition.y * math.cos(rotationAngle)
            if rotatedYDirectionY < 0:
                reflectX = True
    
    cosA, sinA = math.cos(rotationAngle), math.sin(rotationAngle)
    mappedPoints: Dict[int, adsk.core.Point3D] = {}
    unfoldDataAttributes: Dict[str, Dict[str, str]] = {}
    
    planeGeometry = constructionPlane.geometry if constructionPlane else None
    if planeGeometry:
        planeOrigin = planeGeometry.origin
        planeXAxis = planeGeometry.uDirection
        planeYAxis = planeGeometry.vDirection
    else:
        planeOrigin = constants.zeroPoint
        planeXAxis = constants.xVector
        planeYAxis = constants.yVector
    
    for index, position in positions2D.items():
        rotatedX = position.x * cosA - position.y * sinA
        rotatedY = position.x * sinA + position.y * cosA
        if reflectX:
            rotatedY = -rotatedY
        
        totalX = rotatedX + xOffset
        totalY = rotatedY + yOffset
        
        point3D = planeOrigin.copy()
        xVec = planeXAxis.copy()
        xVec.scaleBy(totalX)
        point3D.translateBy(xVec)
        yVec = planeYAxis.copy()
        yVec.scaleBy(totalY)
        point3D.translateBy(yVec)
        
        mappedPoints[index] = point3D
        
        point3dStr = point3dToStr(point3D)
        pointData: Dict[str, str] = {}
        
        if points3D and index < len(points3D):
            pointData[strings.Unfold.sourcePoint3D] = point3dToStr(points3D[index])
        
        if normals and index in normals:
            pointData[strings.Unfold.sourceNormal] = vector3dToStr(normals[index])
        
        if pointData:
            unfoldDataAttributes[point3dStr] = pointData

    sketch.attributes.add(strings.PREFIX, strings.Unfold.sourceData, json.dumps(unfoldDataAttributes))

    return mappedPoints


def drawEdgesToSketch(
    triangles: List[List[int]],
    visitedTriangles: Set[int],
    mappedPoints: Dict[int, adsk.core.Point3D],
    edgeToTriangles: Dict[Tuple[int, int], List[int]],
    sketch: adsk.fusion.Sketch,
    skipDiagonalFunction = None,
    drawOnlyBoundaryEdges: bool = True
):
    """Draw triangle edges to sketch, marking boundary edges as non-construction."""
    try:
        boundaryEdges = {edge for edge, triangles in edgeToTriangles.items() if len(triangles) == 1}
        drawnEdges = set()
        sketchLines = sketch.sketchCurves.sketchLines
        sketchPoints = sketch.sketchPoints
        createdSketchPoints: Dict[int, adsk.fusion.SketchPoint] = {}
        
        if drawOnlyBoundaryEdges:
            for edgeKey in boundaryEdges:
                indexA, indexB = edgeKey
                if indexA in mappedPoints and indexB in mappedPoints:
                    if indexA not in createdSketchPoints:
                        createdSketchPoints[indexA] = sketchPoints.add(mappedPoints[indexA])
                    if indexB not in createdSketchPoints:
                        createdSketchPoints[indexB] = sketchPoints.add(mappedPoints[indexB])
                    
                    point1, point2 = createdSketchPoints[indexA], createdSketchPoints[indexB]
                    newLine = sketchLines.addByTwoPoints(point1, point2)
                    newLine.isFixed = True
                    drawnEdges.add(edgeKey)

        else:
            for triangleIndex in visitedTriangles:
                triangle = triangles[triangleIndex]
                
                for k in range(3):
                    indexA, indexB = triangle[k], triangle[(k + 1) % 3]
                    edgeKey = tuple(sorted((indexA, indexB)))
                    
                    if edgeKey in drawnEdges:
                        continue
                    
                    if skipDiagonalFunction and skipDiagonalFunction(indexA, indexB):
                        continue
                    
                    if indexA in mappedPoints and indexB in mappedPoints:
                        if indexA not in createdSketchPoints:
                            createdSketchPoints[indexA] = sketchPoints.add(mappedPoints[indexA])
                        if indexB not in createdSketchPoints:
                            createdSketchPoints[indexB] = sketchPoints.add(mappedPoints[indexB])
                        
                        point1, point2 = createdSketchPoints[indexA], createdSketchPoints[indexB]
                        newLine = sketchLines.addByTwoPoints(point1, point2)
                        if edgeKey not in boundaryEdges:
                            newLine.isConstruction = True
                        newLine.isFixed = True
                        drawnEdges.add(edgeKey)
    except:
        showMessage(f'drawEdgesToSketch: {traceback.format_exc()}\n', True)


def unfoldFaceToSketch(face: adsk.fusion.BRepFace, accuracy: float, sketch: adsk.fusion.Sketch, 
                       originPoint: adsk.core.Point3D, xDirPoint: adsk.core.Point3D, yDirPoint: adsk.core.Point3D, 
                       constructionPlane: adsk.fusion.ConstructionPlane, xOffset: float, yOffset: float,
                       algorithm: strings.UnfoldAlgorithm = strings.UnfoldAlgorithm.Mesh):
    """
    Unfold a face to a flat sketch representation.
    
    Supports two algorithms:
    - Mesh: Uses mesh triangulation (fastest, less accurate)
    - NURBS: Uses SurfaceEvaluator with uniform grid (balanced)
    """
    if algorithm == strings.UnfoldAlgorithm.Mesh:
        unfoldFaceToSketchWithMesh(face, accuracy, sketch, originPoint, xDirPoint, yDirPoint, constructionPlane, xOffset, yOffset)
    else:
        unfoldFaceToSketchWithNurbs(face, accuracy, sketch, originPoint, xDirPoint, yDirPoint, constructionPlane, xOffset, yOffset)


def unfoldMeshToSketch(mesh: adsk.fusion.TriangleMesh, sketch: adsk.fusion.Sketch, 
                       originPoint: adsk.core.Point3D, xDirPoint: adsk.core.Point3D, yDirPoint: adsk.core.Point3D,
                       constructionPlane: adsk.fusion.ConstructionPlane, xOffset: float, yOffset: float):
    """Unfold a mesh body to a flat sketch representation.
    
    Args:
        mesh: The mesh to unfold.
        sketch: The sketch to draw the unfolded mesh to.
        originPoint: The point to use as the origin (0,0) in the sketch.
        xDirPoint: The point to define the +X direction from origin.
        yDirPoint: The point to define the +Y direction from origin.
        constructionPlane: The construction plane for 3D transformation.
        xOffset: Offset along the X axis of the construction plane.
        yOffset: Offset along the Y axis of the construction plane.
    """
    try:
        sketch.isComputeDeferred = True
        
        nodes = mesh.nodeCoordinates
        normalVectorsArray = mesh.normalVectors
        indices = mesh.nodeIndices
        triangleCount = mesh.triangleCount

        # nodes, normalVectorsArray, indices, triangleCount = remeshMesh(mesh, targetEdgeLength=0.5, iterations=10)
                
        triangles = [[indices[t * 3], indices[t * 3 + 1], indices[t * 3 + 2]] for t in range(triangleCount)]
        
        edgeToTriangles = buildEdgeToTrianglesMap(triangles)
        
        originIndex = findClosestPointIndex(originPoint, nodes)
        xDirectionIndex = findClosestPointIndex(xDirPoint, nodes)
        yDirectionIndex = findClosestPointIndex(yDirPoint, nodes)
        
        positions2D, visitedTriangles = unfoldTrianglesToPositions2D(triangles, nodes, originIndex, edgeToTriangles)
        
        normals = {index: normalVectorsArray[index] for index in range(len(normalVectorsArray)) if index in positions2D}
        
        mappedPoints = preprocess(positions2D, xDirectionIndex, yDirectionIndex, nodes, normals, sketch, constructionPlane, xOffset, yOffset)
        
        drawEdgesToSketch(triangles, visitedTriangles, mappedPoints, edgeToTriangles, sketch)

    except:
        showMessage(f'unfoldMeshToSketch: {traceback.format_exc()}\n', True)

    finally:
        sketch.isComputeDeferred = False



def unfoldFaceToSketchWithMesh(face: adsk.fusion.BRepFace, accuracy: float, sketch: adsk.fusion.Sketch, 
                           originPoint: adsk.core.Point3D, xDirPoint: adsk.core.Point3D, yDirPoint: adsk.core.Point3D,
                           constructionPlane: adsk.fusion.ConstructionPlane, xOffset: float, yOffset: float):
    """Unfold a face to a flat sketch representation using mesh triangulation."""
    try:
        calc = face.meshManager.createMeshCalculator()
        calc.surfaceTolerance = 5
        calc.maxNormalDeviation = 30
        calc.maxAspectRatio = 10
        calc.maxSideLength = accuracy
        mesh = calc.calculate()

        if mesh is None:
            return

        unfoldMeshToSketch(mesh, sketch, originPoint, xDirPoint, yDirPoint, constructionPlane, xOffset, yOffset)

    except:
        showMessage(f'unfoldFaceToSketchMesh: {traceback.format_exc()}\n', True)


def unfoldFaceToSketchWithNurbs(face: adsk.fusion.BRepFace, stepSize: float, sketch: adsk.fusion.Sketch, 
                            originPoint: adsk.core.Point3D, xDirPoint: adsk.core.Point3D, yDirPoint: adsk.core.Point3D,
                            constructionPlane: adsk.fusion.ConstructionPlane, xOffset: float, yOffset: float):
    """Unfold a face to a flat sketch representation using SurfaceEvaluator."""
    try:
        sketch.isComputeDeferred = True

        evaluator = face.evaluator
        stepSize = max(0.05, stepSize or 0.1)
        
        rangeBox = evaluator.parametricRange()
        if rangeBox is None:
            return
        
        uMin, uMax = rangeBox.minPoint.x, rangeBox.maxPoint.x
        vMin, vMax = rangeBox.minPoint.y, rangeBox.maxPoint.y
        
        cornerParams = [
            adsk.core.Point2D.create(uMin, vMin), adsk.core.Point2D.create(uMax, vMin),
            adsk.core.Point2D.create(uMin, vMax), adsk.core.Point2D.create(uMax, vMax)
        ]
        
        success, cornerPoints = evaluator.getPointsAtParameters(cornerParams)
        if not success or len(cornerPoints) < 4:
            return
        
        uDist = (cornerPoints[0].distanceTo(cornerPoints[1]) + cornerPoints[2].distanceTo(cornerPoints[3])) / 2
        vDist = (cornerPoints[0].distanceTo(cornerPoints[2]) + cornerPoints[1].distanceTo(cornerPoints[3])) / 2
        
        numStepsU = min(max(3, int(uDist / stepSize) + 1), 200)
        numStepsV = min(max(3, int(vDist / stepSize) + 1), 200)
        
        uStep = (uMax - uMin) / (numStepsU - 1) if numStepsU > 1 else 0
        vStep = (vMax - vMin) / (numStepsV - 1) if numStepsV > 1 else 0
        
        paramGrid = [adsk.core.Point2D.create(uMin + i * uStep, vMin + j * vStep) 
                     for j in range(numStepsV) for i in range(numStepsU)]
        
        success, points3D = evaluator.getPointsAtParameters(paramGrid)
        if not success:
            return
        
        validData = [(idx, param, points3D[idx]) for idx, param in enumerate(paramGrid) 
                     if evaluator.isParameterOnFace(param)]
        
        if len(validData) < 3:
            return
        
        validIndices = [d[0] for d in validData]
        validParams = [d[1] for d in validData]
        validPoints3D = [d[2] for d in validData]
        
        validToGridPosition = {}
        gridPositionToValid = {}
        for validIndex, originalIndex in enumerate(validIndices):
            i, j = originalIndex % numStepsU, originalIndex // numStepsU
            validToGridPosition[validIndex] = (i, j)
            gridPositionToValid[(i, j)] = validIndex
        
        triangles = []
        for j in range(numStepsV - 1):
            for i in range(numStepsU - 1):
                index00, index10 = gridPositionToValid.get((i, j)), gridPositionToValid.get((i + 1, j))
                index01, index11 = gridPositionToValid.get((i, j + 1)), gridPositionToValid.get((i + 1, j + 1))
                
                if index00 is not None and index10 is not None and index01 is not None:
                    triangles.append([index00, index10, index01])
                if index10 is not None and index11 is not None and index01 is not None:
                    triangles.append([index10, index11, index01])

        if not triangles:
            return

        edgeToTriangles = buildEdgeToTrianglesMap(triangles)

        originIndex = findClosestPointIndex(originPoint, validPoints3D)
        xDirectionIndex = findClosestPointIndex(xDirPoint, validPoints3D)
        yDirectionIndex = findClosestPointIndex(yDirPoint, validPoints3D)

        positions2D, visitedTriangles = unfoldTrianglesToPositions2D(triangles, validPoints3D, originIndex, edgeToTriangles)
        
        success, normalVectorsArray = evaluator.getNormalsAtParameters(validParams)
        if success:
            normals = {index: normalVectorsArray[index] for index in range(len(normalVectorsArray))}
        else:
            normals = calculateVertexNormals(triangles, validPoints3D, visitedTriangles)
        
        mappedPoints = preprocess(positions2D, xDirectionIndex, yDirectionIndex, validPoints3D, normals, sketch, constructionPlane, xOffset, yOffset)

        def skipDiagonal(iA, iB):
            if iA in validToGridPosition and iB in validToGridPosition:
                uA, vA = validToGridPosition[iA]
                uB, vB = validToGridPosition[iB]
                return abs(uA - uB) == 1 and abs(vA - vB) == 1
            return False
        
        drawEdgesToSketch(triangles, visitedTriangles, mappedPoints, edgeToTriangles, sketch, skipDiagonal)

        
    except:
        showMessage(f'unfoldFaceToSketchNurbs: {traceback.format_exc()}\n', True)
    
    finally:
        sketch.isComputeDeferred = False


def refoldBodiesToSurface(
    bodies: adsk.core.ObjectCollection,
    face: adsk.fusion.BRepFace | None,
    sketch: adsk.fusion.Sketch,
    originPoint: adsk.core.Point3D = None,
    xDirPoint: adsk.core.Point3D = None,
    yDirPoint: adsk.core.Point3D = None,
    constructionPlane: adsk.fusion.ConstructionPlane = None
) -> Tuple[adsk.core.ObjectCollection, adsk.core.ObjectCollection, List[adsk.core.Matrix3D]]:
    """
    Transfer bodies from the sketch plane to the original surface.

    Args:
        bodies: ObjectCollection of bodies to transfer to the surface.
        face: The original face from SurfaceUnfold command.
        sketch: The sketch created by SurfaceUnfold command.
        constructionPlane: The construction plane used for the unfold.
    
    Returns:
        Tuple of (resultBodies, originalBodies, transformations):
        - resultBodies: ObjectCollection of temporary BRepBody copies positioned on the surface.
        - originalBodies: The input bodies collection.
        - transformations: List of Matrix3D transformations applied to each result body.
    """
    resultBodies = adsk.core.ObjectCollection.create()
    validOldBodies = adsk.core.ObjectCollection.create()
    transformations: List[adsk.core.Matrix3D] = []
    
    if bodies.count == 0 or sketch is None: return resultBodies, validOldBodies, transformations

    try:
        temporaryManager = adsk.fusion.TemporaryBRepManager.get()

        unfoldDataAttr = sketch.attributes.itemByName(strings.PREFIX, strings.Unfold.sourceData)
        unfoldDataAttributes: Dict[str, Dict[str, str]] = json.loads(unfoldDataAttr.value) if unfoldDataAttr else {}

        basePointDataList: List[Tuple[adsk.core.Point3D, adsk.core.Point3D, adsk.core.Vector3D]] = []

        for point2dStr, pointData in unfoldDataAttributes.items():
            point2D = strToPoint3d(point2dStr)
            if point2D is None: continue
            
            sourcePoint3dStr = pointData.get(strings.Unfold.sourcePoint3D, "")
            if not sourcePoint3dStr: continue
                
            sourcePoint3D = strToPoint3d(sourcePoint3dStr)
            if sourcePoint3D is None: continue

            normalStr = pointData.get(strings.Unfold.sourceNormal, "")
            sourceNormal = strToVector3d(normalStr) if normalStr else None

            basePointDataList.append((point2D, sourcePoint3D, sourceNormal))

        for body in bodies:
            temporaryBody = temporaryManager.copy(body)
            if temporaryBody is None: continue

            centroidPosition = temporaryBody.orientedMinimumBoundingBox.centerPoint
            centroidPositionOnPlane = projectToPlane(centroidPosition, constructionPlane)

            pointDataList: List[Tuple[adsk.core.Point3D, adsk.core.Point3D, adsk.core.Vector3D, float]] = []

            for point2D, sourcePoint3D, sourceNormal in basePointDataList:
                pointPlaneSpace = projectToPlane(point2D, constructionPlane)
                pointDataList.append((pointPlaneSpace, sourcePoint3D, sourceNormal, 0.0))

            for i, item in enumerate(pointDataList):
                distance = centroidPositionOnPlane.distanceTo(item[0])
                pointDataList[i] = (item[0], item[1], item[2], distance)
            pointDataList.sort(key=lambda p: p[3])

            interpolatedPosition, interpolatedNormal = interpolateDataInPointTriangles(centroidPositionOnPlane, pointDataList)

            if interpolatedPosition is None: continue

            if face is not None:
                targetPointOnFace, targetXDirection, targetYDirection, targetNormal = getDataFromPointAndFace(face, interpolatedPosition)
                if targetPointOnFace is None: continue
            else:
                targetPointOnFace = interpolatedPosition
                targetXDirection = constants.xVector
                targetYDirection = constants.yVector
                targetNormal = interpolatedNormal if interpolatedNormal is not None else constants.zVector

            transformation = adsk.core.Matrix3D.create()

            planeGeometry = constructionPlane.geometry if constructionPlane else None
            if planeGeometry:
                sketchX = planeGeometry.uDirection
                sketchY = planeGeometry.vDirection
                sketchNormal = planeGeometry.normal
            else:
                sketchX = sketch.xDirection
                sketchY = sketch.yDirection
                sketchNormal = sketchX.crossProduct(sketchY)

            globalXDirection = originPoint.vectorTo(xDirPoint)
            projectedXDirection = globalXDirection.copy()
            temp = targetNormal.copy()
            temp.scaleBy(globalXDirection.dotProduct(targetNormal))
            projectedXDirection.subtract(temp)
            projectedXDirection.normalize()

            targetXDirection = projectedXDirection
            targetYDirection = targetNormal.crossProduct(targetXDirection)
            targetYDirection.normalize()

            globalYDirection = originPoint.vectorTo(yDirPoint)
            if globalYDirection.dotProduct(targetYDirection) < 0:
                targetYDirection.scaleBy(-1)
                targetXDirection = targetYDirection.crossProduct(targetNormal)
                targetXDirection.normalize()

            targetXDirection.normalize()
            targetYDirection.normalize()

            transformation.setToAlignCoordinateSystems(
                centroidPositionOnPlane, sketchX, sketchY, sketchNormal,
                targetPointOnFace, targetXDirection, targetYDirection, targetNormal
            )
            
            temporaryManager.transform(temporaryBody, transformation)

            resultBodies.add(temporaryBody)
            validOldBodies.add(body)
            transformations.append(transformation)
        
    except:
        showMessage(f'refoldBodiesToSurface: {traceback.format_exc()}\n', True)
        return resultBodies, validOldBodies, transformations

    return resultBodies, validOldBodies, transformations