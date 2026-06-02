import adsk.core, adsk.fusion
import math


def findClosestPointIndex(targetPoint: adsk.core.Point3D, points: list[adsk.core.Point3D]) -> int:
    """Find index of the closest point to targetPoint in the points list."""
    if not points:
        return 0
    minimumDistance = float('inf')
    closestIndex = 0
    for index, point in enumerate(points):
        distance = targetPoint.distanceTo(point)
        if distance < minimumDistance:
            minimumDistance = distance
            closestIndex = index
    return closestIndex


def minDistanceToPoints(point: adsk.core.Point3D, points: list[adsk.core.Point3D]) -> float:
    """Calculate the minimum distance from a point to a list of points.

    Args:
        point: The query point.
        points: The target points.

    Returns:
        The minimum distance, or infinity when the list is empty.
    """
    if not points:
        return float('inf')

    minimumDistance = float('inf')

    for targetPoint in points:
        distance = point.distanceTo(targetPoint)
        if distance < minimumDistance:
            minimumDistance = distance

    return minimumDistance


def closestPointAndDistance(
    point: adsk.core.Point3D,
    points: list[adsk.core.Point3D]
) -> tuple[adsk.core.Point3D | None, float]:
    """Find the closest point in a list and return it with the distance.

    Args:
        point: The query point.
        points: The target points.

    Returns:
        Tuple of (closestPoint, minimumDistance). Returns (None, infinity)
        when the list is empty.
    """
    if not points:
        return None, float('inf')

    closestPoint = None
    minimumDistance = float('inf')

    for targetPoint in points:
        distance = point.distanceTo(targetPoint)
        if distance < minimumDistance:
            minimumDistance = distance
            closestPoint = targetPoint

    return closestPoint, minimumDistance


def triangleArea(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
    """Calculate the area of a triangle given three points."""
    return abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay)) / 2


def isPointInTriangle(pointX: float, pointY: float, 
                      point0X: float, point0Y: float, 
                      point1X: float, point1Y: float, 
                      point2X: float, point2Y: float) -> bool:
    """Check if point (pointX, pointY) is inside triangle defined by three vertices."""
    denom = (point1Y - point2Y) * (point0X - point2X) + (point2X - point1X) * (point0Y - point2Y)
    if abs(denom) < 1e-12:
        return False
    
    a = ((point1Y - point2Y) * (pointX - point2X) + (point2X - point1X) * (pointY - point2Y)) / denom
    b = ((point2Y - point0Y) * (pointX - point2X) + (point0X - point2X) * (pointY - point2Y)) / denom
    c = 1 - a - b
    
    margin = 0.01
    return a >= -margin and b >= -margin and c >= -margin and a <= 1 + margin and b <= 1 + margin and c <= 1 + margin


def countPointInTriangles(
    point: adsk.core.Point2D,
    positions2D: dict[int, adsk.core.Point2D],
    triangles: list[list[int]],
    visitedTriangles: set[int]
) -> int:
    """Count how many existing triangles contain this point."""
    count = 0
    
    for triangleIndex in visitedTriangles:
        triangle = triangles[triangleIndex]
        if triangle[0] not in positions2D or triangle[1] not in positions2D or triangle[2] not in positions2D:
            continue
        
        point0, point1, point2 = positions2D[triangle[0]], positions2D[triangle[1]], positions2D[triangle[2]]
        
        if isPointInTriangle(point.x, point.y, point0.x, point0.y, point1.x, point1.y, point2.x, point2.y):
            count += 1
    
    return count


def averagePosition(points: list[adsk.core.Point3D]) -> adsk.core.Point3D | None:
    """Calculate the average position from a list of Point3D objects.

    The function computes component-wise average of the input points and
    returns a new Point3D. Returns None for empty input or on error.

    Args:
        points: List of Point3D objects to average.

    Returns:
        The averaged Point3D or None if the list is empty or an error occurs.
    """

    if not points:
        return None

    sumX = sum(p.x for p in points)
    sumY = sum(p.y for p in points)
    sumZ = sum(p.z for p in points)

    count = len(points)
    avgX = sumX / count
    avgY = sumY / count
    avgZ = sumZ / count

    return adsk.core.Point3D.create(avgX, avgY, avgZ)


def getPointGeometry(entity: adsk.core.Base) -> adsk.core.Point3D | None:
    """Extract Point3D geometry from different point entity types.

    Args:
        entity: The entity (SketchPoint, BRepVertex, or ConstructionPoint)

    Returns:
        Point3D geometry or None if unsupported type
    """
    if entity.objectType == adsk.fusion.SketchPoint.classType():
        return entity.worldGeometry
    elif entity.objectType == adsk.fusion.BRepVertex.classType():
        return entity.geometry
    elif entity.objectType == adsk.fusion.ConstructionPoint.classType():
        return entity.geometry
    return None


def toPlaneSpace(point: adsk.core.Point3D, constructionPlane: adsk.fusion.ConstructionPlane) -> adsk.core.Point3D:
    """Project a 3D point onto a construction plane and return its coordinates in the plane's local coordinate system.

    Args:
        point: The 3D point to project
        constructionPlane: The construction plane to project onto

    Returns:
        Point3D with coordinates (u, v, 0) representing the point's position in the plane's coordinate system
    """
    if not constructionPlane:
        return adsk.core.Point3D.create(point.x, point.y, 0)
    
    planeGeometry = constructionPlane.geometry
    vec = planeGeometry.origin.vectorTo(point)
    u = vec.dotProduct(planeGeometry.uDirection)
    v = vec.dotProduct(planeGeometry.vDirection)
    return adsk.core.Point3D.create(u, v, 0)


def projectToPlane(point: adsk.core.Point3D, constructionPlane: adsk.fusion.ConstructionPlane) -> adsk.core.Point3D:
    """Project a 3D point onto a construction plane in global space.

    Args:
        point: The 3D point to project
        constructionPlane: The construction plane to project onto

    Returns:
        The projected Point3D on the plane
    """
    plane = constructionPlane.geometry
    normal = plane.normal
    origin = plane.origin
    vec = origin.vectorTo(point)
    dist = vec.dotProduct(normal)
    translation = normal.copy()
    translation.scaleBy(-dist)
    projectedPoint = point.copy()
    projectedPoint.translateBy(translation)
    return projectedPoint


def point3dToStr(point: adsk.core.Point3D, precision: int = 4) -> str:
    """Convert a Point3D to a string representation.
    
    Args:
        point: The Point3D to convert
        precision: Number of decimal places to include. If 0, no limit.
        
    Returns:
        String representation in format "x,y,z"
    """
    if point is None:
        return ""
    if precision == 0:
        return f"{point.x},{point.y},{point.z}"
    else:
        return f"{point.x:.{precision}f},{point.y:.{precision}f},{point.z:.{precision}f}"


def strToPoint3d(pointStr: str) -> adsk.core.Point3D | None:
    """Convert a string representation back to a Point3D.
    
    Args:
        pointStr: String in format "x,y,z"
        
    Returns:
        Point3D object or None if parsing fails
    """
    if not pointStr or not isinstance(pointStr, str):
        return None
    
    try:
        parts = pointStr.split(',')
        if len(parts) != 3:
            return None
        
        x = float(parts[0])
        y = float(parts[1])
        z = float(parts[2])
        
        return adsk.core.Point3D.create(x, y, z)
    except (ValueError, IndexError):
        return None


def getPolygonCentroid(points: list[adsk.core.Point3D]) -> adsk.core.Point3D:
    """Calculate the area-weighted centroid of a polygon defined by 3D points.

    Projects points onto a local 2D plane, sorts them by angle to form a polygon,
    then applies the standard polygon centroid formula (shoelace). Falls back to
    the arithmetic mean if the polygon is degenerate.

    Args:
        points: List of 3D points forming the polygon vertices (order does not matter).

    Returns:
        The centroid point.
    """
    count = len(points)
    if count == 0:
        return adsk.core.Point3D.create(0, 0, 0)
    if count == 1:
        return points[0].copy()
    if count == 2:
        return adsk.core.Point3D.create(
            (points[0].x + points[1].x) * 0.5,
            (points[0].y + points[1].y) * 0.5,
            (points[0].z + points[1].z) * 0.5,
        )

    meanX = sum(p.x for p in points) / count
    meanY = sum(p.y for p in points) / count
    meanZ = sum(p.z for p in points) / count

    dx0 = points[0].x - meanX
    dy0 = points[0].y - meanY
    dz0 = points[0].z - meanZ
    uLen = math.sqrt(dx0 * dx0 + dy0 * dy0 + dz0 * dz0)

    if uLen < 1e-10:
        return adsk.core.Point3D.create(meanX, meanY, meanZ)

    ux, uy, uz = dx0 / uLen, dy0 / uLen, dz0 / uLen

    vx, vy, vz = 0.0, 0.0, 0.0
    for p in points[1:]:
        dx = p.x - meanX
        dy = p.y - meanY
        dz = p.z - meanZ
        cx = uy * dz - uz * dy
        cy = uz * dx - ux * dz
        cz = ux * dy - uy * dx
        cLen = math.sqrt(cx * cx + cy * cy + cz * cz)
        if cLen > 1e-10:
            vx, vy, vz = cx / cLen, cy / cLen, cz / cLen
            break

    if vx == 0.0 and vy == 0.0 and vz == 0.0:
        return adsk.core.Point3D.create(meanX, meanY, meanZ)

    pts2D = []
    for p in points:
        dx = p.x - meanX
        dy = p.y - meanY
        dz = p.z - meanZ
        pts2D.append((dx * ux + dy * uy + dz * uz, dx * vx + dy * vy + dz * vz))

    pts2D.sort(key=lambda p: math.atan2(p[1], p[0]))

    n = len(pts2D)
    area = 0.0
    cx2D = 0.0
    cy2D = 0.0

    for i in range(n):
        xi, yi = pts2D[i]
        xj, yj = pts2D[(i + 1) % n]
        cross = xi * yj - xj * yi
        area += cross
        cx2D += (xi + xj) * cross
        cy2D += (yi + yj) * cross

    area *= 0.5

    if abs(area) < 1e-12:
        return adsk.core.Point3D.create(meanX, meanY, meanZ)

    cx2D /= 6.0 * area
    cy2D /= 6.0 * area

    return adsk.core.Point3D.create(
        meanX + cx2D * ux + cy2D * vx,
        meanY + cx2D * uy + cy2D * vy,
        meanZ + cx2D * uz + cy2D * vz,
    )


def trianglesOverlap(triangle1Points: tuple[adsk.core.Point2D, adsk.core.Point2D, adsk.core.Point2D], 
                     triangle2Points: tuple[adsk.core.Point2D, adsk.core.Point2D, adsk.core.Point2D]) -> bool:
    """
    Check if two triangles overlap in 2D space.
    
    Uses SAT (Separating Axis Theorem) to detect overlap.
    """
    def projectTriangleOnAxis(triangle: tuple, axis: tuple[float, float]) -> tuple[float, float]:
        projections = [
            p.x * axis[0] + p.y * axis[1] for p in triangle
        ]
        return min(projections), max(projections)
    
    def axisFromEdge(p1: adsk.core.Point2D, p2: adsk.core.Point2D) -> tuple[float, float]:
        dx = p2.x - p1.x
        dy = p2.y - p1.y
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1e-9:
            return 1.0, 0.0
        return -dy / length, dx / length
    
    for i in range(3):
        axis = axisFromEdge(triangle1Points[i], triangle1Points[(i + 1) % 3])
        min1, max1 = projectTriangleOnAxis(triangle1Points, axis)
        min2, max2 = projectTriangleOnAxis(triangle2Points, axis)
        if max1 < min2 - 1e-9 or max2 < min1 - 1e-9:
            return False
    
    for i in range(3):
        axis = axisFromEdge(triangle2Points[i], triangle2Points[(i + 1) % 3])
        min1, max1 = projectTriangleOnAxis(triangle1Points, axis)
        min2, max2 = projectTriangleOnAxis(triangle2Points, axis)
        if max1 < min2 - 1e-9 or max2 < min1 - 1e-9:
            return False
    
    return True