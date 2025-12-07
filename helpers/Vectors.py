import adsk.core


def vector3dToStr(vector: adsk.core.Vector3D) -> str:
    """Convert Vector3D to string representation.
    
    Args:
        vector: The Vector3D to convert.
    
    Returns:
        String in format 'x;y;z'.
    """
    if vector is None:
        return ''
    return f'{vector.x};{vector.y};{vector.z}'


def strToVector3d(vectorStr: str) -> adsk.core.Vector3D | None:
    """Convert string to Vector3D.
    
    Args:
        vectorStr: String in format 'x;y;z'.
    
    Returns:
        Vector3D object or None if parsing fails.
    """
    if not vectorStr:
        return None
    try:
        parts = vectorStr.split(';')
        if len(parts) != 3:
            return None
        x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
        return adsk.core.Vector3D.create(x, y, z)
    except:
        return None


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
