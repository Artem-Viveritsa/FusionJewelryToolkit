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


def calculatePointsAlongCurve(curve: adsk.fusion.SketchCurve, size: float, gap: float) -> list[adsk.core.Point3D]:
    """Calculate points along a curve based on gemstone size and gap.

    Args:
        curve: The sketch curve along which to place gemstones.
        size: The diameter of each gemstone.
        gap: The gap between adjacent gemstones.

    Returns:
        A list of Point3D objects representing gemstone positions.
    """
    try:
        points: list[adsk.core.Point3D] = []
        
        geometry: adsk.core.Curve3D = curve.worldGeometry
        evaluator = geometry.evaluator
        
        success, startParam, endParam = evaluator.getParameterExtents()
        if not success:
            return points
        
        success, curveLength = evaluator.getLengthAtParameter(startParam, endParam)
        if not success:
            return points
        
        spacing = size + gap
        if spacing <= 0:
            return points
        
        numGemstones = int(curveLength / spacing)
        if numGemstones == 0:
            return points
        
        actualSpacing = curveLength / numGemstones
        
        for i in range(numGemstones):
            length = (i + 0.5) * actualSpacing
            
            success, param = evaluator.getParameterAtLength(startParam, length)
            if success:
                success, point = evaluator.getPointAtParameter(param)
                if success:
                    points.append(point)
        
        return points
    
    except:
        showMessage(f'calculatePointsAlongCurve: {traceback.format_exc()}\n', True)
        return []


def calculatePointsAndSizesAlongCurve(curve: adsk.fusion.SketchCurve, startOffset: float, endOffset: float,
                                      startSize: float, endSize: float, sizeStep: float, targetGap: float, flipDirection: bool) -> list[tuple[adsk.core.Point3D, float]]:
    """Calculate points and sizes along a curve with variable gemstone sizes.

    Args:
        curve: The sketch curve along which to place gemstones.
        startOffset: Offset from the start of the curve.
        endOffset: Offset from the end of the curve.
        startSize: Gemstone diameter at the start.
        endSize: Gemstone diameter at the end.
        sizeStep: Size discretization step (sizes rounded to multiples of this value).
        targetGap: Target gap between adjacent gemstones.
        flipDirection: If True, reverses the direction (swaps start/end offsets and sizes).

    Returns:
        A list of tuples (Point3D, size) representing gemstone positions and sizes.
    """
    try:
        result: list[tuple[adsk.core.Point3D, float]] = []
        
        curveGeometry: adsk.core.Curve3D = curve.worldGeometry
        curveEvaluator = curveGeometry.evaluator
        
        success, startParameter, endParameter = curveEvaluator.getParameterExtents()
        if not success:
            return result
        
        success, totalCurveLength = curveEvaluator.getLengthAtParameter(startParameter, endParameter)
        if not success:
            return result
         
        effectiveStartPosition = startOffset
        effectiveEndPosition = totalCurveLength - endOffset
        
        availableLength = effectiveEndPosition - effectiveStartPosition
        if availableLength <= 0:
            return result
        
        isConstantSize = abs(startSize - endSize) < 1e-5

        def getSizeAtLength(positionAlongCurve):
            if isConstantSize: return startSize

            interpolationFactor = (positionAlongCurve - effectiveStartPosition) / availableLength if availableLength > 0 else 0.0
            interpolationFactor = max(0.0, min(1.0, interpolationFactor))
            
            interpolatedSize = startSize + (endSize - startSize) * interpolationFactor
            
            if sizeStep > 0:
                return round(interpolatedSize / sizeStep) * sizeStep
            else:
                return interpolatedSize

        centerPositions = []
        gemstoneSizes = []
        
        currentCenterPosition = startOffset
        
        while currentCenterPosition <= effectiveEndPosition + 1e-5:
            currentGemstoneSize = getSizeAtLength(currentCenterPosition)
            
            centerPositions.append(currentCenterPosition)
            gemstoneSizes.append(currentGemstoneSize)
            
            if isConstantSize:
                currentCenterPosition += currentGemstoneSize + targetGap
                continue

            currentRadius = currentGemstoneSize / 2.0
            nextCenterPosition = currentCenterPosition + currentGemstoneSize + targetGap
            
            for _ in range(2):
                nextGemstoneSize = getSizeAtLength(nextCenterPosition)
                nextRadius = nextGemstoneSize / 2.0
                targetDistance = currentRadius + nextRadius + targetGap
                targetPosition = currentCenterPosition + targetDistance
                
                if abs(targetPosition - nextCenterPosition) < 1e-5:
                    nextCenterPosition = targetPosition
                    break
                nextCenterPosition = targetPosition
            
            currentCenterPosition = nextCenterPosition
        
        if len(centerPositions) == 0:
            return result
        
        for i in range(len(centerPositions)):
            positionOnCurve = totalCurveLength - centerPositions[i] if flipDirection else centerPositions[i]
            
            success, curveParameter = curveEvaluator.getParameterAtLength(startParameter, positionOnCurve)
            if success:
                success, pointOnCurve = curveEvaluator.getPointAtParameter(curveParameter)
                if success:
                    result.append((pointOnCurve, gemstoneSizes[i]))
        
        return result
    
    except:
        showMessage(f'calculatePointsAndSizesAlongCurve: {traceback.format_exc()}\n', True)
        return []

