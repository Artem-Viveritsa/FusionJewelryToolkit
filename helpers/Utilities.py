import adsk.core, adsk.fusion, traceback

from .showMessage import showMessage
from ..constants import measureManager, minimumGemstoneSize


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


def calculatePointsAndSizesAlongCurve(curve: adsk.core.Curve3D, startOffset: float, endOffset: float,
                                      startSize: float, endSize: float, sizeStep: float, targetGap: float, flipDirection: bool,
                                      nonlinear: bool = False, nonlinearSize: float = 0.1, nonlinearPosition: float = 0.5) -> list[tuple[adsk.core.Point3D, float]]:
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
        nonlinear: If True, use nonlinear interpolation passing through nonlinearSize at nonlinearPosition.
        nonlinearSize: The size of the gemstone at the nonlinearPosition (in internal units, cm).
        nonlinearPosition: Absolute position of the nonlinearity peak along the curve (in cm, from 0 to total curve length).

    Returns:
        A list of tuples (Point3D, size) representing gemstone positions and sizes.
    """
    try:
        result: list[tuple[adsk.core.Point3D, float]] = []
        
        curveEvaluator = curve.evaluator
        
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
        
        isConstantSize = abs(startSize - endSize) < 1e-5 and not nonlinear

        def getSizeAtLength(positionAlongCurve):
            if isConstantSize: return startSize

            normalizedPosition = (positionAlongCurve - effectiveStartPosition) / availableLength if availableLength > 0 else 0.0
            normalizedPosition = max(0.0, min(1.0, normalizedPosition))
            
            interpolatedSize = 0.0
            
            if not nonlinear:
                interpolatedSize = startSize + (endSize - startSize) * normalizedPosition
                
            else:
                clampedNonlinearPosition = max(0.01, min(0.99, nonlinearPosition))
                denominator = clampedNonlinearPosition * (clampedNonlinearPosition - 1)
                
                if abs(denominator) < 1e-5:
                    interpolatedSize = startSize + (endSize - startSize) * normalizedPosition
                else:
                    numerator = (nonlinearSize - startSize) - (endSize - startSize) * clampedNonlinearPosition
                    quadraticCoeffA = numerator / denominator
                    linearCoeffB = (endSize - startSize) - quadraticCoeffA

                    interpolatedSize = quadraticCoeffA * normalizedPosition * normalizedPosition + linearCoeffB * normalizedPosition + startSize
            
            interpolatedSize = max(0.001, interpolatedSize)

            if sizeStep > 0:
                return max(minimumGemstoneSize, round(interpolatedSize / sizeStep) * sizeStep)
            else:
                return interpolatedSize

        def getPointAtCalculationPosition(calcPos):
            positionOnCurve = totalCurveLength - calcPos if flipDirection else calcPos
            if positionOnCurve < 0: positionOnCurve = 0
            if positionOnCurve > totalCurveLength: positionOnCurve = totalCurveLength
            
            success, param = curveEvaluator.getParameterAtLength(startParameter, positionOnCurve)
            if success:
                success, point = curveEvaluator.getPointAtParameter(param)
                if success:
                    return point
            return None

        centerPositions = []
        gemstoneSizes = []
        
        currentCenterPosition = startOffset
        
        while currentCenterPosition <= effectiveEndPosition + 1e-5:
            currentGemstoneSize = getSizeAtLength(currentCenterPosition)
            
            centerPositions.append(currentCenterPosition)
            gemstoneSizes.append(currentGemstoneSize)
            
            currentRadius = currentGemstoneSize / 2.0
            nextCenterPosition = currentCenterPosition + currentGemstoneSize + targetGap
            
            currentPoint = getPointAtCalculationPosition(currentCenterPosition)

            for _ in range(3):
                nextGemstoneSize = getSizeAtLength(nextCenterPosition)
                nextRadius = nextGemstoneSize / 2.0
                targetDistance = currentRadius + nextRadius + targetGap
                
                nextPoint = getPointAtCalculationPosition(nextCenterPosition)
                
                if currentPoint is None or nextPoint is None:
                    break
                
                actualDistance = currentPoint.distanceTo(nextPoint)
                
                if abs(actualDistance - targetDistance) < 1e-5:
                    break
                
                scaleFactor = targetDistance / actualDistance if actualDistance > 1e-5 else 1.0
                lengthDelta = nextCenterPosition - currentCenterPosition
                nextCenterPosition = currentCenterPosition + lengthDelta * scaleFactor
            
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


def getCurve3D(entity: adsk.core.Base) -> adsk.core.Curve3D | None:
    """Extract Curve3D geometry from SketchCurve or BRepEdge.

    Args:
        entity: A SketchCurve or BRepEdge object.

    Returns:
        The Curve3D geometry, or None if extraction fails.
    """
    if entity is None:
        return None

    if hasattr(entity, 'geometry'):
        return entity.geometry
    
    return None


def calculatePointsAndSizesBetweenCurves(
    curve1Geometry: adsk.core.Curve3D, 
    curve2Geometry: adsk.core.Curve3D, 
    startOffset: float, 
    endOffset: float,
    sizeStep: float, 
    targetGap: float, 
    sizeRatio: float,
    flipDirection: bool = False
) -> list[tuple[adsk.core.Point3D, float]]:
    """Calculate points and sizes between two curves based on the distance between them.

    The gemstone positions are calculated along a polyline that is the average of the two curves.
    The size is determined by the distance between the two curves at each position, multiplied by the sizeRatio.

    Args:
        curve1Geometry: The first Curve3D geometry.
        curve2Geometry: The second Curve3D geometry.
        startOffset: Offset from the start of the curve.
        endOffset: Offset from the end of the curve.
        sizeStep: Size discretization step (sizes rounded to multiples of this value).
        targetGap: Target gap between adjacent gemstones.
        sizeRatio: Ratio of gemstone size to the distance between curves (0.5-2.0).
        flipDirection: If True, gemstones start from the opposite side.

    Returns:
        A list of tuples (Point3D, size) representing gemstone positions and sizes.
    """
    try:
        result: list[tuple[adsk.core.Point3D, float]] = []
        
        if curve1Geometry is None or curve2Geometry is None:
            return result
        
        curve1Evaluator = curve1Geometry.evaluator
        curve2Evaluator = curve2Geometry.evaluator
        
        success, startParam1, endParam1 = curve1Evaluator.getParameterExtents()
        if not success: return result
        
        success, curve1Length = curve1Evaluator.getLengthAtParameter(startParam1, endParam1)
        if not success: return result
        
        success, startParam2, endParam2 = curve2Evaluator.getParameterExtents()
        if not success: return result
        
        success, curve2Length = curve2Evaluator.getLengthAtParameter(startParam2, endParam2)
        if not success: return result
        
        _, p1Start = curve1Evaluator.getPointAtParameter(startParam1)
        _, p1End = curve1Evaluator.getPointAtParameter(endParam1)
        _, p2Start = curve2Evaluator.getPointAtParameter(startParam2)
        _, p2End = curve2Evaluator.getPointAtParameter(endParam2)
        
        distParallel = p1Start.distanceTo(p2Start) + p1End.distanceTo(p2End)
        distAntiParallel = p1Start.distanceTo(p2End) + p1End.distanceTo(p2Start)
        
        curvesOpposed = distAntiParallel < distParallel
        
        averageLength = (curve1Length + curve2Length) / 2.0
        maxLength = max(curve1Length, curve2Length)
        stepSize = minimumGemstoneSize
        numPoints = max(2, int(maxLength / stepSize) + 1)
        
        averagePolyline: list[tuple[float, adsk.core.Point3D]] = []
        
        for i in range(numPoints):
            ratio = i / (numPoints - 1) if numPoints > 1 else 0.0
            
            position = ratio * averageLength
            
            curveRatio1 = 1.0 - ratio if flipDirection else ratio
            curveRatio2 = 1.0 - curveRatio1 if curvesOpposed else curveRatio1
            
            length1 = curveRatio1 * curve1Length
            _, param1 = curve1Evaluator.getParameterAtLength(startParam1, length1)
            _, point1 = curve1Evaluator.getPointAtParameter(param1)
            
            length2 = curveRatio2 * curve2Length
            _, param2 = curve2Evaluator.getParameterAtLength(startParam2, length2)
            _, point2 = curve2Evaluator.getPointAtParameter(param2)

            midpoint = averagePosition([point1, point2])
            if midpoint is None: continue
            
            if i != 0 and i != numPoints - 1:
                firstClosest = measureManager.measureMinimumDistance(midpoint, curve1Geometry).positionOne
                secondClosest = measureManager.measureMinimumDistance(midpoint, curve2Geometry).positionOne
            
                midpoint = averagePosition([firstClosest, secondClosest])
                if midpoint is None: continue

            averagePolyline.append((position, midpoint))
                
        def getPointAtLength(positionAlongPolyline: float) -> adsk.core.Point3D | None:
            """Get interpolated point on the average polyline at a given position."""
            if len(averagePolyline) == 0:
                return None
            
            if positionAlongPolyline <= averagePolyline[0][0]:
                return averagePolyline[0][1]
            
            if positionAlongPolyline >= averagePolyline[-1][0]:
                return averagePolyline[-1][1]
            
            for i in range(len(averagePolyline) - 1):
                pos1, point1 = averagePolyline[i]
                pos2, point2 = averagePolyline[i + 1]
                
                if pos1 <= positionAlongPolyline <= pos2:
                    segmentLength = pos2 - pos1
                    if segmentLength < 1e-10:
                        return point1
                    
                    t = (positionAlongPolyline - pos1) / segmentLength
                    
                    interpolatedPoint = adsk.core.Point3D.create(
                        point1.x + t * (point2.x - point1.x),
                        point1.y + t * (point2.y - point1.y),
                        point1.z + t * (point2.z - point1.z)
                    )
                    return interpolatedPoint
            
            return None
        
            
        def getMinDistanceToCurves(point: adsk.core.Point3D) -> float:
            """Get the minimum distance from a point to either curve."""
            if point is None:
                return 0.0
            
            dist1 = measureManager.measureMinimumDistance(point, curve1Geometry).value
            dist2 = measureManager.measureMinimumDistance(point, curve2Geometry).value
            
            return min(dist1, dist2)
        
        def getAverageDistanceToCurves(point: adsk.core.Point3D) -> float:
            """Get the minimum distance from a point to either curve."""
            if point is None:
                return 0.0
            
            dist1 = measureManager.measureMinimumDistance(point, curve1Geometry).value
            dist2 = measureManager.measureMinimumDistance(point, curve2Geometry).value
            
            return (dist1 + dist2) / 2.0
        
        def getSizeAtLength(positionAlongPolyline: float) -> float:
            """Get gemstone size at a given position along the average polyline.
            
            The size is calculated as 2 * minDistance * sizeRatio, where minDistance
            is the minimum distance from the polyline point to either curve.
            """
            point = getPointAtLength(positionAlongPolyline)
            if point is None:
                return minimumGemstoneSize
            
            avgDist = getAverageDistanceToCurves(point)
            gemstoneSize = 2.0 * avgDist * sizeRatio
            
            if sizeStep > 0:
                return max(minimumGemstoneSize, round(gemstoneSize / sizeStep) * sizeStep)
            else:
                return max(minimumGemstoneSize, gemstoneSize)
        
        effectiveStartPosition = startOffset
        effectiveEndPosition = averageLength - endOffset
        
        if effectiveEndPosition < effectiveStartPosition:
            return result

        currentCenterPosition = effectiveStartPosition
        
        while currentCenterPosition <= effectiveEndPosition + 1e-5:
            currentGemstoneSize = getSizeAtLength(currentCenterPosition)
            
            point = getPointAtLength(currentCenterPosition)
            if point: result.append((point, currentGemstoneSize))
            
            currentRadius = currentGemstoneSize / 2.0
            nextCenterPosition = currentCenterPosition + currentGemstoneSize + targetGap
            
            for _ in range(3):
                nextGemstoneSize = getSizeAtLength(nextCenterPosition)
                nextRadius = nextGemstoneSize / 2.0
                targetDistance = currentRadius + nextRadius + targetGap
                
                nextPoint = getPointAtLength(nextCenterPosition)
                if point is None or nextPoint is None: break
                
                actualDistance = point.distanceTo(nextPoint)
                if abs(actualDistance - targetDistance) < 1e-5: break
                
                scaleFactor = targetDistance / actualDistance if actualDistance > 1e-5 else 1.0
                lengthDelta = nextCenterPosition - currentCenterPosition
                nextCenterPosition = currentCenterPosition + lengthDelta * scaleFactor
            
            currentCenterPosition = nextCenterPosition
        
        return result
    
    except:
        showMessage(f'calculatePointsAndSizesBetweenCurves2: {traceback.format_exc()}\n', True)
        return []


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
