import adsk.core, adsk.fusion, traceback

from .showMessage import showMessage


def getDataFromPointAndFace(face: adsk.fusion.BRepFace, point: adsk.core.Point3D) -> tuple[adsk.core.Point3D, adsk.core.Vector3D, adsk.core.Vector3D, adsk.core.Vector3D]:
    """Get the surface point and orientation vectors (normal, length direction, width direction) at a given point on a face.

    This function evaluates the face geometry at the specified point to obtain:
    - The actual point on the face surface
    - The surface normal vector
    - The length direction (first derivative)
    - The width direction (cross product of normal and length direction)

    All vectors are normalized.

    Args:
        face: The BRepFace to evaluate
        point: The 3D point to project onto the face

    Returns:
        A tuple containing:
        - pointOnFace: The point on the face surface
        - normal: Normalized surface normal vector
        - lengthDirection: Normalized first derivative vector
        - widthDirection: Normalized cross product vector (normal × lengthDirection)

    Returns (None, None, None, None) if evaluation fails.
    """
    try:
        if face is None or point is None:
            return None, None, None, None

        # Evaluate the face at the specified point to obtain surface parameters
        evaluator = face.evaluator
        _, parameter = evaluator.getParameterAtPoint(point)
        _, pointOnFace = evaluator.getPointAtParameter(parameter)
        _, normal = evaluator.getNormalAtParameter(parameter)
        _, lengthDirection, _ = evaluator.getFirstDerivative(parameter)

        # Calculate width direction as cross product of normal and length direction
        widthDirection = normal.crossProduct(lengthDirection)

        # Normalize all vectors
        lengthDirection.normalize()
        widthDirection.normalize()
        normal.normalize()

        return pointOnFace, normal, lengthDirection, widthDirection

    except:
        showMessage(f'getDataFromPointAndFace: {traceback.format_exc()}\n', True)
        return None, None, None, None


def averageVector(vectors: list[adsk.core.Vector3D], normalize: bool = False) -> adsk.core.Vector3D | None:
    """Calculate the average vector from a list of Vector3D objects.
    
    This function computes the component-wise average of the input vectors.
    Optionally normalizes the result if its length is greater than a small threshold.
    
    Args:
        vectors: List of Vector3D objects to average.
        normalize: If True, normalize the result vector if possible.
    
    Returns:
        The average Vector3D (normalized if requested and possible), or None if the list is empty or averaging fails.
    """
  
    if not vectors:
        return None
    
    sumX = sum(v.x for v in vectors)
    sumY = sum(v.y for v in vectors)
    sumZ = sum(v.z for v in vectors)
    
    count = len(vectors)
    avgX = sumX / count
    avgY = sumY / count
    avgZ = sumZ / count
    
    result = adsk.core.Vector3D.create(avgX, avgY, avgZ)
    
    if normalize and result.length > 1e-6:
        result.normalize()
        return result
    elif not normalize:
        return result
    else:
        return None


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
  


