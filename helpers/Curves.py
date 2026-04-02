import math
import adsk.core, adsk.fusion, traceback

from .showMessage import showMessage
from ..constants import measureManager, minimumGemstoneSize, gemstoneOverlapMergeThreshold, cornerAngleThresholdRadians, chainConnectionTolerance
from .Points import averagePosition


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


def getCurveEndpoints(entity) -> tuple[adsk.core.Point3D, adsk.core.Point3D] | None:
    """Get start and end points of a curve entity.

    Args:
        entity: A SketchCurve or BRepEdge.

    Returns:
        Tuple of (startPoint, endPoint) or None if extraction fails.
    """
    curve = getCurve3D(entity)
    if curve is None:
        return None

    ev = curve.evaluator
    success, sp, ep = ev.getParameterExtents()
    if not success:
        return None

    _, startPt = ev.getPointAtParameter(sp)
    _, endPt = ev.getPointAtParameter(ep)
    return (startPt, endPt)


def canConnectToChain(existingEntities: list, candidateEntity) -> bool:
    """Check if a candidate curve can connect to an existing chain of curves.

    Args:
        existingEntities: List of already-selected curve entities.
        candidateEntity: The candidate curve entity to check.

    Returns:
        True if the candidate can extend the chain, False otherwise.
    """
    if len(existingEntities) == 0:
        return True

    candidateEndpoints = getCurveEndpoints(candidateEntity)
    if candidateEndpoints is None:
        return False

    candidateStart, candidateEnd = candidateEndpoints

    allEntities = list(existingEntities) + [candidateEntity]
    curves = [getCurve3D(e) for e in allEntities]
    if any(c is None for c in curves):
        return False

    endpoints: list[tuple[adsk.core.Point3D, adsk.core.Point3D]] = []
    for curve in curves:
        ev = curve.evaluator
        _, sp, ep = ev.getParameterExtents()
        _, startPt = ev.getPointAtParameter(sp)
        _, endPt = ev.getPointAtParameter(ep)
        endpoints.append((startPt, endPt))

    used = [False] * len(curves)
    ordered = [0]
    used[0] = True
    chainEndPoint = endpoints[0][1]
    chainStartPoint = endpoints[0][0]

    changed = True
    while changed:
        changed = False
        for i in range(len(curves)):
            if used[i]:
                continue

            startPt, endPt = endpoints[i]

            if (chainEndPoint.distanceTo(startPt) < chainConnectionTolerance or
                chainEndPoint.distanceTo(endPt) < chainConnectionTolerance):
                ordered.append(i)
                used[i] = True
                chainEndPoint = endPt if chainEndPoint.distanceTo(startPt) < chainConnectionTolerance else startPt
                changed = True
                break

            if (chainStartPoint.distanceTo(endPt) < chainConnectionTolerance or
                chainStartPoint.distanceTo(startPt) < chainConnectionTolerance):
                ordered.insert(0, i)
                used[i] = True
                chainStartPoint = startPt if chainStartPoint.distanceTo(endPt) < chainConnectionTolerance else endPt
                changed = True
                break

    return all(used)


def buildOrderedCurveChain(curveEntities: list) -> tuple[list[adsk.core.Curve3D], list[bool]]:
    """Order curve entities into a connected chain.

    Args:
        curveEntities: List of SketchCurve or BRepEdge entities.

    Returns:
        Tuple of (ordered Curve3D list, reversed flags indicating traversal direction).
        Empty lists if curves don't form a valid chain.
    """
    if len(curveEntities) == 0:
        return [], []

    if len(curveEntities) == 1:
        curve = getCurve3D(curveEntities[0])
        if curve is None:
            return [], []
        return [curve], [False]

    curves = [getCurve3D(e) for e in curveEntities]
    if any(c is None for c in curves):
        return [], []

    endpoints: list[tuple[adsk.core.Point3D, adsk.core.Point3D]] = []
    for curve in curves:
        ev = curve.evaluator
        _, sp, ep = ev.getParameterExtents()
        _, startPt = ev.getPointAtParameter(sp)
        _, endPt = ev.getPointAtParameter(ep)
        endpoints.append((startPt, endPt))

    used = [False] * len(curves)
    ordered = [0]
    reversedFlags = [False]
    used[0] = True

    chainEndPoint = endpoints[0][1]
    chainStartPoint = endpoints[0][0]

    changed = True
    while changed:
        changed = False
        for i in range(len(curves)):
            if used[i]:
                continue

            startPt, endPt = endpoints[i]

            if chainEndPoint.distanceTo(startPt) < chainConnectionTolerance:
                ordered.append(i)
                reversedFlags.append(False)
                used[i] = True
                chainEndPoint = endPt
                changed = True
                break

            if chainEndPoint.distanceTo(endPt) < chainConnectionTolerance:
                ordered.append(i)
                reversedFlags.append(True)
                used[i] = True
                chainEndPoint = startPt
                changed = True
                break

            if chainStartPoint.distanceTo(endPt) < chainConnectionTolerance:
                ordered.insert(0, i)
                reversedFlags.insert(0, False)
                used[i] = True
                chainStartPoint = startPt
                changed = True
                break

            if chainStartPoint.distanceTo(startPt) < chainConnectionTolerance:
                ordered.insert(0, i)
                reversedFlags.insert(0, True)
                used[i] = True
                chainStartPoint = endPt
                changed = True
                break

    if not all(used):
        return [], []

    return [curves[i] for i in ordered], reversedFlags


class CurveChainEvaluator:
    """Evaluates points and tangents along an ordered chain of connected curves."""

    def __init__(self, curves: list[adsk.core.Curve3D], reversedFlags: list[bool]):
        self.curves = curves
        self.reversedFlags = reversedFlags
        self.evaluators: list[adsk.core.CurveEvaluator3D] = []
        self.startParams: list[float] = []
        self.endParams: list[float] = []
        self.segmentLengths: list[float] = []
        self.cumulativeLengths: list[float] = []
        self.totalLength: float = 0.0
        self.cornerPositions: list[float] = []

        cumLen = 0.0
        for curve in curves:
            ev = curve.evaluator
            _, sp, ep = ev.getParameterExtents()
            _, segLen = ev.getLengthAtParameter(sp, ep)

            self.evaluators.append(ev)
            self.startParams.append(sp)
            self.endParams.append(ep)
            self.segmentLengths.append(segLen)
            self.cumulativeLengths.append(cumLen)
            cumLen += segLen

        self.totalLength = cumLen

        self.chainStartPoint = self._getSegmentPoint(0, 0.0)
        self.chainEndPoint = self._getSegmentPoint(len(curves) - 1, self.segmentLengths[-1])
        self.chainStartTangent = self._getSegmentTangent(0, 0.0)
        self.chainEndTangent = self._getSegmentTangent(len(curves) - 1, self.segmentLengths[-1])
        if self.chainStartTangent:
            self.chainStartTangent.normalize()
        if self.chainEndTangent:
            self.chainEndTangent.normalize()

        self._detectCorners()

    def _getSegmentPoint(self, segIndex: int, localLength: float) -> adsk.core.Point3D:
        """Get point at a local length position within a segment."""
        ev = self.evaluators[segIndex]
        effectiveLength = self.segmentLengths[segIndex] - localLength if self.reversedFlags[segIndex] else localLength
        effectiveLength = max(0.0, min(effectiveLength, self.segmentLengths[segIndex]))
        _, param = ev.getParameterAtLength(self.startParams[segIndex], effectiveLength)
        _, point = ev.getPointAtParameter(param)
        return point

    def _getSegmentTangent(self, segIndex: int, localLength: float) -> adsk.core.Vector3D:
        """Get tangent at a local length position within a segment, in chain direction."""
        ev = self.evaluators[segIndex]
        effectiveLength = self.segmentLengths[segIndex] - localLength if self.reversedFlags[segIndex] else localLength
        effectiveLength = max(0.0, min(effectiveLength, self.segmentLengths[segIndex]))
        _, param = ev.getParameterAtLength(self.startParams[segIndex], effectiveLength)
        _, tangent = ev.getTangent(param)
        if self.reversedFlags[segIndex]:
            tangent.scaleBy(-1)
        return tangent

    def _detectCorners(self):
        """Detect corners at junctions between curves in the chain."""
        for i in range(len(self.curves) - 1):
            endTangent = self._getSegmentTangent(i, self.segmentLengths[i])
            startTangent = self._getSegmentTangent(i + 1, 0.0)

            if endTangent is None or startTangent is None:
                continue

            endTangent.normalize()
            startTangent.normalize()

            dotProduct = endTangent.dotProduct(startTangent)
            dotProduct = max(-1.0, min(1.0, dotProduct))
            angle = math.acos(dotProduct)

            if angle > cornerAngleThresholdRadians:
                self.cornerPositions.append(self.cumulativeLengths[i] + self.segmentLengths[i])

    def getPointAtLength(self, length: float) -> adsk.core.Point3D:
        """Get point at a given length along the chain, with extrapolation beyond bounds."""
        if length < 0:
            overshoot = -length
            if self.chainStartPoint and self.chainStartTangent:
                return adsk.core.Point3D.create(
                    self.chainStartPoint.x - self.chainStartTangent.x * overshoot,
                    self.chainStartPoint.y - self.chainStartTangent.y * overshoot,
                    self.chainStartPoint.z - self.chainStartTangent.z * overshoot
                )
            return self.chainStartPoint

        if length > self.totalLength:
            overshoot = length - self.totalLength
            if self.chainEndPoint and self.chainEndTangent:
                return adsk.core.Point3D.create(
                    self.chainEndPoint.x + self.chainEndTangent.x * overshoot,
                    self.chainEndPoint.y + self.chainEndTangent.y * overshoot,
                    self.chainEndPoint.z + self.chainEndTangent.z * overshoot
                )
            return self.chainEndPoint

        for i in range(len(self.segmentLengths)):
            segStart = self.cumulativeLengths[i]
            segEnd = segStart + self.segmentLengths[i]

            if length <= segEnd + 1e-10 or i == len(self.segmentLengths) - 1:
                localLen = length - segStart
                return self._getSegmentPoint(i, localLen)

        return None


def _mergeOverlappingGemstones(gemstones: list[tuple[adsk.core.Point3D, float]]) -> list[tuple[adsk.core.Point3D, float]]:
    """Merge consecutive gemstones whose centers are closer than the sum of their radii.

    Two gemstones overlap when the distance between their centers is less than the sum of their
    radii (size1 + size2) / 2. Overlapping pairs are merged into a single gemstone at the
    average position with the average size. Also handles closed-curve wrap-around.

    Args:
        gemstones: List of (Point3D, size) tuples.

    Returns:
        List with overlapping consecutive gemstones merged.
    """
    if len(gemstones) < 2:
        return gemstones

    merged = [gemstones[0]]
    for i in range(1, len(gemstones)):
        prevPoint, prevSize = merged[-1]
        currPoint, currSize = gemstones[i]
        if prevPoint.distanceTo(currPoint) < (prevSize + currSize) / 3:
            mergedPoint = adsk.core.Point3D.create(
                (prevPoint.x + currPoint.x) / 2.0,
                (prevPoint.y + currPoint.y) / 2.0,
                (prevPoint.z + currPoint.z) / 2.0
            )
            merged[-1] = (mergedPoint, (prevSize + currSize) / 2.0)
        else:
            merged.append(gemstones[i])

    if len(merged) > 1:
        firstPoint, firstSize = merged[0]
        lastPoint, lastSize = merged[-1]
        if firstPoint.distanceTo(lastPoint) < (firstSize + lastSize) / 2.0:
            merged.pop()

    return merged


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
        
        return _mergeOverlappingGemstones(result)
    
    except:
        showMessage(f'calculatePointsAndSizesAlongCurve: {traceback.format_exc()}\n', True)
        return []


def calculatePointsAlongCurve(curve: adsk.core.Curve3D, spacing: float, startOffset: float, endOffset: float,
                              flipDirection: bool, uniformDistribution: bool = False, count: int = 0) -> list[tuple[adsk.core.Point3D, adsk.core.Vector3D]]:
    """Calculate evenly-spaced points and tangent vectors along a curve.

    Args:
        curve: The curve along which to distribute points.
        spacing: Distance between consecutive points.
        startOffset: Offset from the start of the curve.
        endOffset: Offset from the end of the curve.
        flipDirection: If True, reverses the placement direction.
        uniformDistribution: If True, adjusts spacing to fill the entire available length.
        count: Maximum number of elements to place. 0 means unlimited.
            With uniform distribution, if count is less than what would naturally fit,
            the elements are centered within the available length using the original spacing.

    Returns:
        A list of tuples (Point3D, Vector3D) representing positions and tangent vectors along the curve.
    """
    try:
        result: list[tuple[adsk.core.Point3D, adsk.core.Vector3D]] = []

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

        if availableLength <= 0 or spacing <= 0:
            return result

        numberOfPositions = max(1, int(availableLength / spacing) + 1)

        if count > 0 and count < numberOfPositions:
            if uniformDistribution:
                # Center the limited group within the available length using original spacing
                occupiedLength = spacing * (count - 1)
                centeringOffset = (availableLength - occupiedLength) / 2
                effectiveStartPosition += centeringOffset
                effectiveEndPosition = effectiveStartPosition + occupiedLength
            numberOfPositions = count
            actualSpacing = spacing
        elif uniformDistribution and numberOfPositions > 1:
            actualSpacing = availableLength / (numberOfPositions - 1)
        else:
            actualSpacing = spacing

        _, curveStartPoint = curveEvaluator.getPointAtParameter(startParameter)
        _, curveEndPoint = curveEvaluator.getPointAtParameter(endParameter)
        _, curveStartTangent = curveEvaluator.getTangent(startParameter)
        _, curveEndTangent = curveEvaluator.getTangent(endParameter)
        curveStartTangent.normalize()
        curveEndTangent.normalize()

        for i in range(numberOfPositions):
            positionAlongCurve = effectiveStartPosition + i * actualSpacing

            if positionAlongCurve > effectiveEndPosition + 1e-5:
                break

            actualPosition = totalCurveLength - positionAlongCurve if flipDirection else positionAlongCurve

            if actualPosition < 0:
                overshoot = -actualPosition
                point = adsk.core.Point3D.create(
                    curveStartPoint.x - curveStartTangent.x * overshoot,
                    curveStartPoint.y - curveStartTangent.y * overshoot,
                    curveStartPoint.z - curveStartTangent.z * overshoot
                )
                tangent = curveStartTangent.copy()
            elif actualPosition > totalCurveLength:
                overshoot = actualPosition - totalCurveLength
                point = adsk.core.Point3D.create(
                    curveEndPoint.x + curveEndTangent.x * overshoot,
                    curveEndPoint.y + curveEndTangent.y * overshoot,
                    curveEndPoint.z + curveEndTangent.z * overshoot
                )
                tangent = curveEndTangent.copy()
            else:
                success, param = curveEvaluator.getParameterAtLength(startParameter, actualPosition)
                if not success:
                    continue
                success, point = curveEvaluator.getPointAtParameter(param)
                if not success:
                    continue
                _, tangent = curveEvaluator.getTangent(param)
                tangent.normalize()

            if flipDirection:
                tangent.scaleBy(-1)

            result.append((point, tangent))

        return result

    except:
        showMessage(f'calculatePointsAlongCurve: {traceback.format_exc()}\n', True)
        return []


def calculatePointsAndSizesBetweenCurves(
    curve1Geometry: adsk.core.Curve3D, 
    curve2Geometry: adsk.core.Curve3D, 
    startOffset: float, 
    endOffset: float,
    sizeStep: float, 
    targetGap: float, 
    sizeRatio: float,
    flipDirection: bool = False,
    uniformDistribution: bool = False,
    minStoneSize: float = 0.0,
    maxStoneSize: float = 0.0
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
        minStoneSize: Minimum gemstone size. Gemstones smaller than this are skipped. 0 means no limit.
        maxStoneSize: Maximum gemstone size. Gemstones larger are clamped. 0 means no limit.

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
                gemstoneSize = max(minimumGemstoneSize, round(gemstoneSize / sizeStep) * sizeStep)
            else:
                gemstoneSize = max(minimumGemstoneSize, gemstoneSize)

            if minStoneSize > 0:
                gemstoneSize = max(gemstoneSize, minStoneSize)
            if maxStoneSize > 0:
                gemstoneSize = min(gemstoneSize, maxStoneSize)

            return gemstoneSize
        
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
        
        return _mergeOverlappingGemstones(result)
    
    except:
        showMessage(f'calculatePointsAndSizesBetweenCurves: {traceback.format_exc()}\n', True)
        return []


def calculatePointsAndSizesAlongCurveChain(
    curveEntities: list,
    startOffset: float, endOffset: float,
    startSize: float, endSize: float, sizeStep: float, targetGap: float,
    flipDirection: bool, uniformDistribution: bool = False,
    snapToCorners: bool = False,
    nonlinear: bool = False, nonlinearSize: float = 0.1, nonlinearPosition: float = 0.5
) -> list[tuple[adsk.core.Point3D, float]]:
    """Calculate points and sizes along a chain of connected curves.

    For a single curve without snap-to-corners, delegates to calculatePointsAndSizesAlongCurve
    for full backward compatibility.

    Args:
        curveEntities: List of SketchCurve or BRepEdge entities forming a connected chain.
        startOffset: Offset from the start of the chain.
        endOffset: Offset from the end of the chain.
        startSize: Gemstone diameter at the start.
        endSize: Gemstone diameter at the end.
        sizeStep: Size discretization step.
        targetGap: Target gap between adjacent gemstones.
        flipDirection: If True, reverses placement direction.
        uniformDistribution: If True, distributes gemstones uniformly.
        snapToCorners: If True, ensures gemstones are placed at chain corner points.
        nonlinear: If True, use nonlinear size interpolation.
        nonlinearSize: Size at the nonlinear position.
        nonlinearPosition: Position of nonlinearity peak (0.0 to 1.0).

    Returns:
        A list of tuples (Point3D, size) representing gemstone positions and sizes.
    """
    try:
        curves, reversedFlags = buildOrderedCurveChain(curveEntities)
        if len(curves) == 0:
            return []

        if len(curves) == 1 and not snapToCorners:
            curve = curves[0]
            actualFlip = not flipDirection if reversedFlags[0] else flipDirection
            return calculatePointsAndSizesAlongCurve(
                curve, startOffset, endOffset, startSize, endSize,
                sizeStep, targetGap, actualFlip, uniformDistribution,
                nonlinear, nonlinearSize, nonlinearPosition)

        chainEval = CurveChainEvaluator(curves, reversedFlags)
        totalLength = chainEval.totalLength

        effectiveStartPosition = startOffset
        effectiveEndPosition = totalLength - endOffset
        availableLength = effectiveEndPosition - effectiveStartPosition
        if availableLength <= 0:
            return []

        isConstantSize = abs(startSize - endSize) < 1e-5 and not nonlinear

        def getSizeAtLength(positionAlongChain: float) -> float:
            if isConstantSize:
                return startSize

            normalizedPosition = (positionAlongChain - effectiveStartPosition) / availableLength if availableLength > 0 else 0.0
            normalizedPosition = max(0.0, min(1.0, normalizedPosition))

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

        def getPointAtCalcPos(calcPos: float) -> adsk.core.Point3D:
            positionOnChain = totalLength - calcPos if flipDirection else calcPos
            return chainEval.getPointAtLength(positionOnChain)

        def placeGemstonesInRange(rangeStart: float, rangeEnd: float) -> tuple[list[float], list[float]]:
            """Place gemstones using standard algorithm within a range."""
            positions: list[float] = []
            sizes: list[float] = []
            currentCenterPosition = rangeStart

            while currentCenterPosition <= rangeEnd + 1e-5:
                currentGemstoneSize = getSizeAtLength(currentCenterPosition)
                positions.append(currentCenterPosition)
                sizes.append(currentGemstoneSize)

                currentRadius = currentGemstoneSize / 2.0
                nextCenterPosition = currentCenterPosition + currentGemstoneSize + targetGap
                currentPoint = getPointAtCalcPos(currentCenterPosition)

                for _ in range(3):
                    nextGemstoneSize = getSizeAtLength(nextCenterPosition)
                    nextRadius = nextGemstoneSize / 2.0
                    targetDistance = currentRadius + nextRadius + targetGap
                    nextPoint = getPointAtCalcPos(nextCenterPosition)

                    if currentPoint is None or nextPoint is None:
                        break

                    actualDistance = currentPoint.distanceTo(nextPoint)
                    if abs(actualDistance - targetDistance) < 1e-5:
                        break

                    scaleFactor = targetDistance / actualDistance if actualDistance > 1e-5 else 1.0
                    lengthDelta = nextCenterPosition - currentCenterPosition
                    nextCenterPosition = currentCenterPosition + lengthDelta * scaleFactor

                currentCenterPosition = nextCenterPosition

            return positions, sizes

        def applyUniformDistribution(positions: list[float], sizes: list[float], rangeStart: float, rangeEnd: float) -> list[float]:
            """Apply uniform distribution to positions within a range."""
            if len(positions) == 0:
                return positions

            if len(positions) == 1:
                positions[0] = (rangeStart + rangeEnd) / 2.0
                return positions

            firstRadius = sizes[0] / 2.0
            lastRadius = sizes[-1] / 2.0
            middleSizesSum = sum(sizes[1:-1]) if len(sizes) > 2 else 0.0
            occupiedLength = firstRadius + middleSizesSum + lastRadius
            totalGapSpace = (rangeEnd - rangeStart) - occupiedLength
            uniformGap = totalGapSpace / (len(positions) - 1)

            newPositions: list[float] = []
            currentPos = rangeStart
            for i in range(len(sizes)):
                newPositions.append(currentPos)
                if i < len(sizes) - 1:
                    currentRadius = sizes[i] / 2.0
                    nextRadius = sizes[i + 1] / 2.0
                    currentPos += currentRadius + uniformGap + nextRadius

            return newPositions

        centerPositions: list[float] = []
        gemstoneSizes: list[float] = []

        if snapToCorners:
            if flipDirection:
                cornerCalcPositions = sorted([totalLength - cp for cp in chainEval.cornerPositions])
            else:
                cornerCalcPositions = list(chainEval.cornerPositions)

            validCorners = [cp for cp in cornerCalcPositions
                           if effectiveStartPosition < cp < effectiveEndPosition]

            boundaries = [effectiveStartPosition] + validCorners + [effectiveEndPosition]
            isCornerFlags = [False] + [True] * len(validCorners) + [False]

            for segIdx in range(len(boundaries) - 1):
                segStart = boundaries[segIdx]
                segEnd = boundaries[segIdx + 1]
                startIsCorner = isCornerFlags[segIdx]
                endIsCorner = isCornerFlags[segIdx + 1]

                if startIsCorner:
                    cornerSize = getSizeAtLength(segStart)
                    centerPositions.append(segStart)
                    gemstoneSizes.append(cornerSize)

                cornerStartSize = getSizeAtLength(segStart) if startIsCorner else 0.0
                cornerEndSize = getSizeAtLength(segEnd) if endIsCorner else 0.0

                if startIsCorner:
                    cornerStartRadius = cornerStartSize / 2.0
                    estimatePos = min(segStart + cornerStartSize + targetGap, segEnd)
                    estimateFirstGemSize = getSizeAtLength(estimatePos)
                    innerStart = segStart + cornerStartRadius + targetGap + estimateFirstGemSize / 2.0
                else:
                    innerStart = segStart

                if endIsCorner:
                    cornerEndRadius = cornerEndSize / 2.0
                    estimatePos = max(segEnd - cornerEndSize - targetGap, segStart)
                    estimateLastGemSize = getSizeAtLength(estimatePos)
                    innerEnd = segEnd - cornerEndRadius - targetGap - estimateLastGemSize / 2.0
                else:
                    innerEnd = segEnd

                if innerStart < innerEnd:
                    segPositions, segSizes = placeGemstonesInRange(innerStart, innerEnd)

                    if uniformDistribution and len(segPositions) > 0:
                        segPositions = applyUniformDistribution(segPositions, segSizes, innerStart, innerEnd)

                    centerPositions.extend(segPositions)
                    gemstoneSizes.extend(segSizes)

            if isCornerFlags[-1]:
                cornerSize = getSizeAtLength(boundaries[-1])
                centerPositions.append(boundaries[-1])
                gemstoneSizes.append(cornerSize)
        else:
            centerPositions, gemstoneSizes = placeGemstonesInRange(effectiveStartPosition, effectiveEndPosition)

            if uniformDistribution and len(centerPositions) > 0:
                centerPositions = applyUniformDistribution(centerPositions, gemstoneSizes, effectiveStartPosition, effectiveEndPosition)

        result: list[tuple[adsk.core.Point3D, float]] = []
        for i in range(len(centerPositions)):
            point = getPointAtCalcPos(centerPositions[i])
            if point is not None:
                result.append((point, gemstoneSizes[i]))

        return _mergeOverlappingGemstones(result)

    except:
        showMessage(f'calculatePointsAndSizesAlongCurveChain: {traceback.format_exc()}\n', True)
        return []


def calculatePointsAndSizesBetweenCurveChains(
    rail1Entities: list,
    rail2Entities: list,
    startOffset: float, endOffset: float,
    sizeStep: float, targetGap: float,
    sizeRatio: float,
    flipDirection: bool = False,
    uniformDistribution: bool = False,
    snapToCorners: bool = False,
    minStoneSize: float = 0.0,
    maxStoneSize: float = 0.0
) -> list[tuple[adsk.core.Point3D, float]]:
    """Calculate points and sizes between two curve chains.

    For single-curve rails without snapToCorners, delegates to calculatePointsAndSizesBetweenCurves.

    Args:
        rail1Entities: List of entities forming the first rail chain.
        rail2Entities: List of entities forming the second rail chain.
        startOffset: Offset from the start.
        endOffset: Offset from the end.
        sizeStep: Size discretization step.
        targetGap: Target gap between adjacent gemstones.
        sizeRatio: Ratio of gemstone size to distance between rails.
        flipDirection: If True, reverses placement direction.
        uniformDistribution: If True, distributes gemstones uniformly.
        snapToCorners: If True, ensures gemstones are placed at chain corner points.
        minStoneSize: Minimum gemstone size. Gemstones smaller than this are skipped. 0 means no limit.
        maxStoneSize: Maximum gemstone size. Gemstones larger are clamped. 0 means no limit.

    Returns:
        A list of tuples (Point3D, size) representing gemstone positions and sizes.
    """
    try:
        curves1, reversed1 = buildOrderedCurveChain(rail1Entities)
        curves2, reversed2 = buildOrderedCurveChain(rail2Entities)
        if len(curves1) == 0 or len(curves2) == 0:
            return []

        if len(curves1) == 1 and len(curves2) == 1 and not snapToCorners:
            return calculatePointsAndSizesBetweenCurves(
                curves1[0], curves2[0],
                startOffset, endOffset, sizeStep, targetGap,
                sizeRatio, flipDirection, uniformDistribution,
                minStoneSize, maxStoneSize)

        chain1 = CurveChainEvaluator(curves1, reversed1)
        chain2 = CurveChainEvaluator(curves2, reversed2)

        p1Start = chain1.getPointAtLength(0.0)
        p1End = chain1.getPointAtLength(chain1.totalLength)
        p2Start = chain2.getPointAtLength(0.0)
        p2End = chain2.getPointAtLength(chain2.totalLength)

        distParallel = p1Start.distanceTo(p2Start) + p1End.distanceTo(p2End)
        distAntiParallel = p1Start.distanceTo(p2End) + p1End.distanceTo(p2Start)
        chainsOpposed = distAntiParallel < distParallel

        chain1Length = chain1.totalLength
        chain2Length = chain2.totalLength
        averageLength = (chain1Length + chain2Length) / 2.0
        maxLength = max(chain1Length, chain2Length)
        stepSize = minimumGemstoneSize
        numPoints = max(2, int(maxLength / stepSize) + 1)

        averagePolyline: list[tuple[float, adsk.core.Point3D]] = []

        for i in range(numPoints):
            ratio = i / (numPoints - 1) if numPoints > 1 else 0.0
            position = ratio * averageLength

            curveRatio1 = 1.0 - ratio if flipDirection else ratio
            curveRatio2 = 1.0 - curveRatio1 if chainsOpposed else curveRatio1

            point1 = chain1.getPointAtLength(curveRatio1 * chain1Length)
            point2 = chain2.getPointAtLength(curveRatio2 * chain2Length)

            midpoint = averagePosition([point1, point2])
            if midpoint is None:
                continue

            averagePolyline.append((position, midpoint))

        if len(averagePolyline) < 2:
            return []

        def getPointAtLength(positionAlongPolyline: float) -> adsk.core.Point3D | None:
            if len(averagePolyline) == 0:
                return None
            if len(averagePolyline) < 2:
                return averagePolyline[0][1]

            if positionAlongPolyline < averagePolyline[0][0]:
                pos1, pt1 = averagePolyline[0]
                pos2, pt2 = averagePolyline[1]
                segLen = pos2 - pos1
                if segLen < 1e-10:
                    return pt1
                overshoot = pos1 - positionAlongPolyline
                dx = (pt2.x - pt1.x) / segLen
                dy = (pt2.y - pt1.y) / segLen
                dz = (pt2.z - pt1.z) / segLen
                return adsk.core.Point3D.create(pt1.x - dx * overshoot, pt1.y - dy * overshoot, pt1.z - dz * overshoot)

            if positionAlongPolyline > averagePolyline[-1][0]:
                pos1, pt1 = averagePolyline[-2]
                pos2, pt2 = averagePolyline[-1]
                segLen = pos2 - pos1
                if segLen < 1e-10:
                    return pt2
                overshoot = positionAlongPolyline - pos2
                dx = (pt2.x - pt1.x) / segLen
                dy = (pt2.y - pt1.y) / segLen
                dz = (pt2.z - pt1.z) / segLen
                return adsk.core.Point3D.create(pt2.x + dx * overshoot, pt2.y + dy * overshoot, pt2.z + dz * overshoot)

            for idx in range(len(averagePolyline) - 1):
                pos1, pt1 = averagePolyline[idx]
                pos2, pt2 = averagePolyline[idx + 1]
                if pos1 <= positionAlongPolyline <= pos2:
                    segLen = pos2 - pos1
                    if segLen < 1e-10:
                        return pt1
                    t = (positionAlongPolyline - pos1) / segLen
                    return adsk.core.Point3D.create(
                        pt1.x + t * (pt2.x - pt1.x),
                        pt1.y + t * (pt2.y - pt1.y),
                        pt1.z + t * (pt2.z - pt1.z))
            return None

        def getAverageDistanceToChains(point: adsk.core.Point3D) -> float:
            if point is None:
                return 0.0
            dist1 = min(measureManager.measureMinimumDistance(point, c).value for c in curves1)
            dist2 = min(measureManager.measureMinimumDistance(point, c).value for c in curves2)
            return (dist1 + dist2) / 2.0

        def getSizeAtLength(positionAlongPolyline: float) -> float:
            clampedPosition = positionAlongPolyline
            if len(averagePolyline) >= 2:
                clampedPosition = max(averagePolyline[0][0], min(averagePolyline[-1][0], positionAlongPolyline))

            point = getPointAtLength(clampedPosition)
            if point is None:
                return minimumGemstoneSize

            avgDist = getAverageDistanceToChains(point)
            gemstoneSize = 2.0 * avgDist * sizeRatio

            if sizeStep > 0:
                gemstoneSize = max(minimumGemstoneSize, round(gemstoneSize / sizeStep) * sizeStep)
            else:
                gemstoneSize = max(minimumGemstoneSize, gemstoneSize)

            if minStoneSize > 0:
                gemstoneSize = max(gemstoneSize, minStoneSize)
            if maxStoneSize > 0:
                gemstoneSize = min(gemstoneSize, maxStoneSize)

            return gemstoneSize

        effectiveStartPosition = startOffset
        effectiveEndPosition = averageLength - endOffset

        if effectiveEndPosition < effectiveStartPosition:
            return []

        def placeGemstonesInRange(rangeStart: float, rangeEnd: float) -> tuple[list[float], list[float]]:
            """Place gemstones using standard algorithm within a range."""
            positions: list[float] = []
            sizes: list[float] = []
            currentCenterPosition = rangeStart

            while currentCenterPosition <= rangeEnd + 1e-5:
                currentGemstoneSize = getSizeAtLength(currentCenterPosition)
                positions.append(currentCenterPosition)
                sizes.append(currentGemstoneSize)

                currentRadius = currentGemstoneSize / 2.0
                nextCenterPosition = currentCenterPosition + currentGemstoneSize + targetGap
                currentPoint = getPointAtLength(currentCenterPosition)

                for _ in range(3):
                    nextGemstoneSize = getSizeAtLength(nextCenterPosition)
                    nextRadius = nextGemstoneSize / 2.0
                    targetDistance = currentRadius + nextRadius + targetGap
                    nextPoint = getPointAtLength(nextCenterPosition)

                    if currentPoint is None or nextPoint is None:
                        break

                    actualDistance = currentPoint.distanceTo(nextPoint)
                    if abs(actualDistance - targetDistance) < 1e-5:
                        break

                    scaleFactor = targetDistance / actualDistance if actualDistance > 1e-5 else 1.0
                    lengthDelta = nextCenterPosition - currentCenterPosition
                    nextCenterPosition = currentCenterPosition + lengthDelta * scaleFactor

                currentCenterPosition = nextCenterPosition

            return positions, sizes

        def applyUniformDistribution(positions: list[float], sizes: list[float], rangeStart: float, rangeEnd: float) -> list[float]:
            """Apply uniform distribution to positions within a range."""
            if len(positions) == 0:
                return positions

            if len(positions) == 1:
                positions[0] = (rangeStart + rangeEnd) / 2.0
                return positions

            firstRadius = sizes[0] / 2.0
            lastRadius = sizes[-1] / 2.0
            middleSizesSum = sum(sizes[1:-1]) if len(sizes) > 2 else 0.0
            occupiedLength = firstRadius + middleSizesSum + lastRadius
            totalGapSpace = (rangeEnd - rangeStart) - occupiedLength
            uniformGap = totalGapSpace / (len(positions) - 1)

            newPositions: list[float] = []
            currentPos = rangeStart
            for i in range(len(sizes)):
                newPositions.append(currentPos)
                if i < len(sizes) - 1:
                    currentRadius = sizes[i] / 2.0
                    nextRadius = sizes[i + 1] / 2.0
                    currentPos += currentRadius + uniformGap + nextRadius

            return newPositions

        centerPositions: list[float] = []
        gemstoneSizes: list[float] = []

        if snapToCorners:
            corner1Positions = list(chain1.cornerPositions)
            corner2Positions = list(chain2.cornerPositions)

            cornerAvgPositions: list[float] = []
            for cp in corner1Positions:
                ratio1 = cp / chain1Length if chain1Length > 0 else 0.0
                if flipDirection:
                    ratio1 = 1.0 - ratio1
                cornerAvgPositions.append(ratio1 * averageLength)

            for cp in corner2Positions:
                ratio2 = cp / chain2Length if chain2Length > 0 else 0.0
                if chainsOpposed:
                    ratio2 = 1.0 - ratio2
                if flipDirection:
                    ratio2 = 1.0 - ratio2
                cornerAvgPositions.append(ratio2 * averageLength)

            cornerAvgPositions = sorted(set(
                round(p / minimumGemstoneSize) * minimumGemstoneSize for p in cornerAvgPositions))

            mergedCornerPositions: list[float] = []
            for p in cornerAvgPositions:
                if mergedCornerPositions and abs(p - mergedCornerPositions[-1]) < gemstoneOverlapMergeThreshold:
                    mergedCornerPositions[-1] = (mergedCornerPositions[-1] + p) / 2.0
                else:
                    mergedCornerPositions.append(p)
            cornerAvgPositions = mergedCornerPositions

            validCorners = [cp for cp in cornerAvgPositions
                           if effectiveStartPosition < cp < effectiveEndPosition]

            boundaries = [effectiveStartPosition] + validCorners + [effectiveEndPosition]
            isCornerFlags = [False] + [True] * len(validCorners) + [False]

            for segIdx in range(len(boundaries) - 1):
                segStart = boundaries[segIdx]
                segEnd = boundaries[segIdx + 1]
                startIsCorner = isCornerFlags[segIdx]
                endIsCorner = isCornerFlags[segIdx + 1]

                if startIsCorner:
                    cornerSize = getSizeAtLength(segStart)
                    centerPositions.append(segStart)
                    gemstoneSizes.append(cornerSize)

                cornerStartSize = getSizeAtLength(segStart) if startIsCorner else 0.0
                cornerEndSize = getSizeAtLength(segEnd) if endIsCorner else 0.0

                if startIsCorner:
                    cornerStartRadius = cornerStartSize / 2.0
                    estimatePos = min(segStart + cornerStartSize + targetGap, segEnd)
                    estimateFirstGemSize = getSizeAtLength(estimatePos)
                    innerStart = segStart + cornerStartRadius + targetGap + estimateFirstGemSize / 2.0
                else:
                    innerStart = segStart

                if endIsCorner:
                    cornerEndRadius = cornerEndSize / 2.0
                    estimatePos = max(segEnd - cornerEndSize - targetGap, segStart)
                    estimateLastGemSize = getSizeAtLength(estimatePos)
                    innerEnd = segEnd - cornerEndRadius - targetGap - estimateLastGemSize / 2.0
                else:
                    innerEnd = segEnd

                if innerStart < innerEnd:
                    segPositions, segSizes = placeGemstonesInRange(innerStart, innerEnd)

                    if uniformDistribution and len(segPositions) > 0:
                        segPositions = applyUniformDistribution(segPositions, segSizes, innerStart, innerEnd)

                    centerPositions.extend(segPositions)
                    gemstoneSizes.extend(segSizes)

            if isCornerFlags[-1]:
                cornerSize = getSizeAtLength(boundaries[-1])
                centerPositions.append(boundaries[-1])
                gemstoneSizes.append(cornerSize)
        else:
            centerPositions, gemstoneSizes = placeGemstonesInRange(effectiveStartPosition, effectiveEndPosition)

            if uniformDistribution and len(centerPositions) > 0:
                centerPositions = applyUniformDistribution(centerPositions, gemstoneSizes, effectiveStartPosition, effectiveEndPosition)

        result: list[tuple[adsk.core.Point3D, float]] = []
        for i in range(len(centerPositions)):
            point = getPointAtLength(centerPositions[i])
            if point is not None:
                result.append((point, gemstoneSizes[i]))

        return _mergeOverlappingGemstones(result)

    except:
        showMessage(f'calculatePointsAndSizesBetweenCurveChains: {traceback.format_exc()}\n', True)
        return []
