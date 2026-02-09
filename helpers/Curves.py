import adsk.core, adsk.fusion, traceback

from .showMessage import showMessage
from ..constants import measureManager, minimumGemstoneSize, gemstoneOverlapMergeThreshold
from .Points import averagePosition


def calculatePointsAndSizesAlongCurve(curve: adsk.core.Curve3D, startOffset: float, endOffset: float,
                                      startSize: float, endSize: float, sizeStep: float, targetGap: float, flipDirection: bool,
                                      uniformDistribution: bool = False,
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
        uniformDistribution: If True, distributes gemstones uniformly to fill the entire available length.
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
        
        _, curveStartPoint = curveEvaluator.getPointAtParameter(startParameter)
        _, curveEndPoint = curveEvaluator.getPointAtParameter(endParameter)
        _, curveStartTangent = curveEvaluator.getTangent(startParameter)
        _, curveEndTangent = curveEvaluator.getTangent(endParameter)
        curveStartTangent.normalize()
        curveEndTangent.normalize()
        
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
            
            if positionOnCurve < 0:
                overshoot = -positionOnCurve
                return adsk.core.Point3D.create(
                    curveStartPoint.x - curveStartTangent.x * overshoot,
                    curveStartPoint.y - curveStartTangent.y * overshoot,
                    curveStartPoint.z - curveStartTangent.z * overshoot
                )
            
            if positionOnCurve > totalCurveLength:
                overshoot = positionOnCurve - totalCurveLength
                return adsk.core.Point3D.create(
                    curveEndPoint.x + curveEndTangent.x * overshoot,
                    curveEndPoint.y + curveEndTangent.y * overshoot,
                    curveEndPoint.z + curveEndTangent.z * overshoot
                )
            
            success, param = curveEvaluator.getParameterAtLength(startParameter, positionOnCurve)
            if success:
                success, point = curveEvaluator.getPointAtParameter(param)
                if success:
                    return point
            return None

        centerPositions: list[float] = []
        gemstoneSizes: list[float] = []
        
        currentCenterPosition = effectiveStartPosition
        
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

        if uniformDistribution and len(centerPositions) > 0:
            if len(centerPositions) == 1:
                centerPositions[0] = (effectiveStartPosition + effectiveEndPosition) / 2.0
            else:
                firstRadius = gemstoneSizes[0] / 2.0
                lastRadius = gemstoneSizes[-1] / 2.0
                middleSizesSum = sum(gemstoneSizes[1:-1]) if len(gemstoneSizes) > 2 else 0.0
                
                occupiedLength = firstRadius + middleSizesSum + lastRadius
                totalGapSpace = availableLength - occupiedLength
                uniformGap = totalGapSpace / (len(centerPositions) - 1)
                
                newCenterPositions = []
                currentPos = effectiveStartPosition
                
                for i in range(len(gemstoneSizes)):
                    newCenterPositions.append(currentPos)
                    if i < len(gemstoneSizes) - 1:
                        currentRadius = gemstoneSizes[i] / 2.0
                        nextRadius = gemstoneSizes[i + 1] / 2.0
                        currentPos += currentRadius + uniformGap + nextRadius
                
                centerPositions = newCenterPositions
        
        for i in range(len(centerPositions)):
            point = getPointAtCalculationPosition(centerPositions[i])
            if point is not None:
                result.append((point, gemstoneSizes[i]))
        
        if len(result) > 1:
            firstPoint = result[0][0]
            lastPoint = result[-1][0]
            if firstPoint.distanceTo(lastPoint) < gemstoneOverlapMergeThreshold:
                result.pop()
        
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

    if hasattr(entity, 'worldGeometry'):
        return entity.worldGeometry
    
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
    flipDirection: bool = False,
    uniformDistribution: bool = False
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
        uniformDistribution: If True, distributes gemstones uniformly to fill the entire available length.

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
            """Get interpolated or extrapolated point on the average polyline at a given position."""
            if len(averagePolyline) == 0:
                return None
            
            if len(averagePolyline) < 2:
                return averagePolyline[0][1]
            
            if positionAlongPolyline < averagePolyline[0][0]:
                pos1, point1 = averagePolyline[0]
                pos2, point2 = averagePolyline[1]
                segmentLength = pos2 - pos1
                if segmentLength < 1e-10:
                    return point1
                overshoot = pos1 - positionAlongPolyline
                dx = (point2.x - point1.x) / segmentLength
                dy = (point2.y - point1.y) / segmentLength
                dz = (point2.z - point1.z) / segmentLength
                return adsk.core.Point3D.create(
                    point1.x - dx * overshoot,
                    point1.y - dy * overshoot,
                    point1.z - dz * overshoot
                )
            
            if positionAlongPolyline > averagePolyline[-1][0]:
                pos1, point1 = averagePolyline[-2]
                pos2, point2 = averagePolyline[-1]
                segmentLength = pos2 - pos1
                if segmentLength < 1e-10:
                    return point2
                overshoot = positionAlongPolyline - pos2
                dx = (point2.x - point1.x) / segmentLength
                dy = (point2.y - point1.y) / segmentLength
                dz = (point2.z - point1.z) / segmentLength
                return adsk.core.Point3D.create(
                    point2.x + dx * overshoot,
                    point2.y + dy * overshoot,
                    point2.z + dz * overshoot
                )
            
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
            For positions outside the polyline bounds, the size of the nearest edge gemstone is used.
            """
            clampedPosition = positionAlongPolyline
            if len(averagePolyline) >= 2:
                clampedPosition = max(averagePolyline[0][0], min(averagePolyline[-1][0], positionAlongPolyline))
            
            point = getPointAtLength(clampedPosition)
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
        
        if uniformDistribution and len(result) > 0:
            if len(result) == 1:
                centerPosition = (effectiveStartPosition + effectiveEndPosition) / 2.0
                point = getPointAtLength(centerPosition)
                if point:
                    result[0] = (point, result[0][1])
            else:
                firstRadius = result[0][1] / 2.0
                lastRadius = result[-1][1] / 2.0
                middleSizesSum = sum(size for _, size in result[1:-1]) if len(result) > 2 else 0.0
                
                occupiedLength = firstRadius + middleSizesSum + lastRadius
                totalGapSpace = (effectiveEndPosition - effectiveStartPosition) - occupiedLength
                uniformGap = totalGapSpace / (len(result) - 1)
                
                newResult = []
                currentPos = effectiveStartPosition
                
                for i, (_, size) in enumerate(result):
                    point = getPointAtLength(currentPos)
                    if point:
                        newResult.append((point, size))
                    if i < len(result) - 1:
                        currentRadius = size / 2.0
                        nextRadius = result[i + 1][1] / 2.0
                        currentPos += currentRadius + uniformGap + nextRadius
                
                result = newResult
        
        if len(result) > 1:
            firstPoint = result[0][0]
            lastPoint = result[-1][0]
            if firstPoint.distanceTo(lastPoint) < gemstoneOverlapMergeThreshold:
                result.pop()
        
        return result
    
    except:
        showMessage(f'calculatePointsAndSizesBetweenCurves: {traceback.format_exc()}\n', True)
        return []
