import adsk.core, adsk.fusion, traceback
from collections import defaultdict

from .. import constants
from .showMessage import showMessage
from .Gemstones import GemstoneInfo
from .Bodies import placeBody
from .Utilities import averageVector, averagePosition

class ProngInfo:
    """Class to store all information needed to create or update a single prong.
    
    Attributes:
        position: The 3D position where the prong should be placed.
        normal: The normal vector for prong orientation (height direction).
        lengthDirection: The length direction vector for prong orientation.
        widthDirection: The width direction vector for prong orientation.
        size: The size of the prong (ratio * average diameter).
        height: The height of the prong (ratio * average diameter).
    """
    def __init__(self, position: adsk.core.Point3D, normal: adsk.core.Vector3D, 
                 lengthDirection: adsk.core.Vector3D, widthDirection: adsk.core.Vector3D,
                 size: float, height: float):
        self.position = position
        self.normal = normal
        self.lengthDirection = lengthDirection
        self.widthDirection = widthDirection
        self.size = size
        self.height = height


def createProng(size: float, height: float) -> adsk.fusion.BRepBody | None:
    """Creates a prong body geometry at the origin without positioning.
    
    Returns the prong as a BRepBody with specified size and height.
    
    Args:
        size: The diameter of the prong base
        height: The height of the prong
        
    Returns:
        The created prong body or None if creation failed
    """
    try:
        temporaryBRep: adsk.fusion.TemporaryBRepManager = adsk.fusion.TemporaryBRepManager.get()
        bodies = []

        radius = size / 2

        bottomPoint = adsk.core.Point3D.create(0, 0, -height)
        topPoint = adsk.core.Point3D.create(0, 0, height)

        bodies.append(temporaryBRep.createCylinderOrCone(topPoint, radius, bottomPoint, radius))

        prong: adsk.fusion.BRepBody = None
        for body in bodies:
            if prong is None:
                prong = body
            else:
                temporaryBRep.booleanOperation(prong, body, adsk.fusion.BooleanTypes.UnionBooleanType)

        return prong

    except:
        showMessage(f'createProng: {traceback.format_exc()}\n', True)
        return None


def updateProngAndNormalize(body: adsk.fusion.BRepBody, size: float, height: float) -> adsk.fusion.BRepBody | None:
    """Updates a prong body to new size and places it at the origin coordinate system.
    
    Returns the updated prong as a BRepBody positioned at constants.zeroPoint with the specified size and height.
    
    Args:
        body: The existing prong body to update
        size: The new diameter of the prong base
        height: The new height of the prong
        
    Returns:
        The updated prong body positioned at origin or None if update failed
    """
    try:
        if body is None: return None

        temporaryBRep = adsk.fusion.TemporaryBRepManager.get()
        tempBody = temporaryBRep.copy(body)

        planarFaces = list(filter(lambda x: x.geometry.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType, tempBody.faces))
        cylindricalFaces = list(filter(lambda x: x.geometry.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType, tempBody.faces))
        
        # Validate that required faces exist
        if not cylindricalFaces or len(planarFaces) < 2:
            showMessage(f'updateProngAndNormalize: Body geometry corrupted - found {len(cylindricalFaces)} cylindrical faces and {len(planarFaces)} planar faces\n', True)
            return None
        
        cylindricalFace = cylindricalFaces[0]

        plane = adsk.core.Plane.cast(planarFaces[0].geometry)
        cylinder = adsk.core.Cylinder.cast(cylindricalFace.geometry)
        oldOriginPoint = cylindricalFace.centroid

        oldHeight = planarFaces[0].centroid.distanceTo(planarFaces[1].centroid) / 2
        oldSize = cylinder.radius * 2

        sizeScale = size / oldSize
        heightScale = height / oldHeight

        oldNormal = plane.normal
        oldLengthDirection = plane.uDirection
        oldWidthDirection = plane.vDirection

        transformation = adsk.core.Matrix3D.create()

        transformation.setToAlignCoordinateSystems(
            oldOriginPoint, oldLengthDirection, oldWidthDirection, oldNormal,
            constants.zeroPoint, constants.xVector, constants.yVector, constants.zVector
            )
        temporaryBRep.transform(tempBody, transformation)

        # Create scaled coordinate vectors more efficiently
        scaledXVector = adsk.core.Vector3D.create(sizeScale, 0, 0)
        scaledYVector = adsk.core.Vector3D.create(0, sizeScale, 0)
        scaledZVector = adsk.core.Vector3D.create(0, 0, heightScale)

        transformation.setToIdentity()
        transformation.setToAlignCoordinateSystems(
            constants.zeroPoint, constants.xVector, constants.yVector, constants.zVector,
            constants.zeroPoint, scaledXVector, scaledYVector, scaledZVector
            )
        temporaryBRep.transform(tempBody, transformation)

        return tempBody
    
    except:
        showMessage(f'updateProngAndNormalize: {traceback.format_exc()}\n', True)
        return None


def createProngFromInfo(prongInfo: ProngInfo) -> adsk.fusion.BRepBody | None:
    """Create a single prong body from ProngInfo data.
    
    Args:
        prongInfo: The prong information containing position, orientation, and dimensions.
    
    Returns:
        Created prong body or None if creation failed.
    """
    try:
        # Create the prong geometry at the origin
        prong = createProng(prongInfo.size, prongInfo.height)
        if prong is None:
            return None
        
        # Place the prong at the specified position with proper orientation
        placeBody(prong, prongInfo.position, prongInfo.lengthDirection, prongInfo.widthDirection, prongInfo.normal)
        
        return prong
    
    except:
        showMessage(f'createProngFromInfo: {traceback.format_exc()}\n', True)
        return None


def updateProngFromInfo(body: adsk.fusion.BRepBody, prongInfo: ProngInfo) -> adsk.fusion.BRepBody | None:
    """Update an existing prong body from ProngInfo data.
    
    Args:
        body: The existing prong body to update.
        prongInfo: The prong information containing position, orientation, and dimensions.
    
    Returns:
        Updated prong body or None if update failed.
    """
    try:
        # First try to update the existing body
        tempBody = updateProngAndNormalize(body, prongInfo.size, prongInfo.height)
        
        # If update failed (body geometry corrupted), create a fresh prong instead
        if tempBody is None:
            tempBody = createProng(prongInfo.size, prongInfo.height)
            if tempBody is None:
                return None
        
        # Place the prong at the specified position with proper orientation
        placeBody(tempBody, prongInfo.position, prongInfo.lengthDirection, prongInfo.widthDirection, prongInfo.normal)
        
        return tempBody
    
    except:
        showMessage(f'updateProngFromInfo: {traceback.format_exc()}\n', True)
        return None


# Helper function to create ProngInfo objects from connections
def createProngInfosFromConnections(connections: list[tuple[GemstoneInfo, GemstoneInfo]], gemstoneInfos: list[GemstoneInfo], 
                                     sizeRatio: float, heightRatio: float, widthBetweenProngsRatio: float, weldDistance: float = 0.3) -> list[ProngInfo]:
    """Create a list of ProngInfo objects from gemstone connections.
    
    For each connection between two gemstones, this function creates two ProngInfo objects
    positioned perpendicular to the axis between the gemstones. Prongs that are closer
    than weldDistance are merged into a single prong with averaged properties.
    
    Args:
        connections: List of tuples containing GemstoneInfo pairs to connect.
        gemstoneInfos: List of gemstone information objects.
        sizeRatio: The ratio of the prong size to the average diameter.
        heightRatio: The ratio of the prong height to the average diameter.
        widthBetweenProngsRatio: The ratio of the distance between two prongs to the average diameter.
        weldDistance: Distance threshold for merging nearby prongs (default 0.03 cm = 3.0 mm).

    Returns:
        List of ProngInfo objects with nearby prongs merged.
    """
    prongInfos = []
    
    try:
        for info1, info2 in connections:
            # Calculate average diameter and prong dimensions
            avgDiameter = info1.radius + info2.radius
            size = avgDiameter * sizeRatio
            height = avgDiameter * heightRatio
            
            # Calculate placement data for both prongs
            offsetPoints, avgNormal, lengthDirection, widthDirection = calculateProngsPlacement(info1, info2, widthBetweenProngsRatio)
            if offsetPoints is None or avgNormal is None or lengthDirection is None or widthDirection is None:
                continue
            
            # Create ProngInfo for each offset position
            for offsetPoint in offsetPoints:
                prongInfo = ProngInfo(
                    position=offsetPoint,
                    normal=avgNormal,
                    lengthDirection=lengthDirection,
                    widthDirection=widthDirection,
                    size=size,
                    height=height
                )
                prongInfos.append(prongInfo)
        
        # Merge nearby prongs based on weldDistance
        if weldDistance > 0 and len(prongInfos) > 1:
            prongInfos = mergeNearbyProngs(prongInfos, weldDistance)
        
        return prongInfos
    
    except:
        showMessage(f'createProngInfosFromConnections: {traceback.format_exc()}\n', True)
        return []


# Helper function to merge nearby prongs
def mergeNearbyProngs(prongInfos: list[ProngInfo], weldDistance: float) -> list[ProngInfo]:
    """Merge prongs that are closer than weldDistance into single prongs with averaged properties.
    
    Args:
        prongInfos: List of prong information objects.
        weldDistance: Distance threshold for merging prongs.
    
    Returns:
        List of ProngInfo objects with nearby prongs merged.
    """
    try:
        count = len(prongInfos)
        if count <= 1:
            return prongInfos

        parent = list(range(count))

        def find(idx: int) -> int:
            while parent[idx] != idx:
                parent[idx] = parent[parent[idx]]
                idx = parent[idx]
            return idx

        def union(a: int, b: int) -> None:
            rootA = find(a)
            rootB = find(b)
            if rootA != rootB:
                parent[rootB] = rootA

        for i in range(count):
            baseProng = prongInfos[i]
            for j in range(i + 1, count):
                if baseProng.position.distanceTo(prongInfos[j].position) < weldDistance:
                    union(i, j)

        groups: dict[int, list[int]] = defaultdict(list)
        for idx in range(count):
            groups[find(idx)].append(idx)

        mergedProngInfos: list[ProngInfo] = []
        for group in groups.values():
            if len(group) == 1:
                mergedProngInfos.append(prongInfos[group[0]])
                continue

            groupSize = len(group)

            positions = [prongInfos[idx].position for idx in group]
            avgPosition = averagePosition(positions)

            sumSize = sum(prongInfos[idx].size for idx in group)
            sumHeight = sum(prongInfos[idx].height for idx in group)

            avgSize = sumSize / groupSize
            avgHeight = sumHeight / groupSize

            normals = [prongInfos[idx].normal for idx in group]
            lengthDirections = [prongInfos[idx].lengthDirection for idx in group]
            widthDirections = [prongInfos[idx].widthDirection for idx in group]

            reference = prongInfos[group[0]]
            avgNormal = averageVector(normals, normalize=True) or reference.normal.copy()
            avgLengthDirection = averageVector(lengthDirections, normalize=True) or reference.lengthDirection.copy()
            avgWidthDirection = averageVector(widthDirections, normalize=True) or reference.widthDirection.copy()

            mergedProngInfos.append(ProngInfo(
                position=avgPosition,
                normal=avgNormal,
                lengthDirection=avgLengthDirection,
                widthDirection=avgWidthDirection,
                size=avgSize,
                height=avgHeight
            ))

        return mergedProngInfos
    
    except:
        showMessage(f'mergeNearbyProngs: {traceback.format_exc()}\n', True)
        return prongInfos


# Helper function to calculate prong placement data for both prongs
def calculateProngsPlacement(info1: GemstoneInfo, info2: GemstoneInfo, widthBetweenProngsRatio: float) -> tuple[list[adsk.core.Point3D], adsk.core.Vector3D, adsk.core.Vector3D, adsk.core.Vector3D]:
    """Calculate the placement data for two prongs between two gemstones.

    Args:
        info1: First gemstone information.
        info2: Second gemstone information.
        widthBetweenProngsRatio: The ratio of the distance between two prongs to the average diameter.

    Returns:
        Tuple of (offsetPoints, avgNormal, lengthDirection, widthDirection) for prong placement and orientation.
        offsetPoints is a list of 2 Point3D objects (for offset -1 and +1).
        Returns (None, None, None, None) if calculation fails.
    """
    try:
        centroid1 = info1.centroid.copy()
        centroid2 = info2.centroid.copy()

        axisDirection = adsk.core.Vector3D.create(
            centroid2.x - centroid1.x,
            centroid2.y - centroid1.y,
            centroid2.z - centroid1.z
        )
        axisDirection.normalize()

        firstGirdlePoint = adsk.core.Point3D.create(
            centroid1.x + axisDirection.x * info1.radius,
            centroid1.y + axisDirection.y * info1.radius,
            centroid1.z + axisDirection.z * info1.radius
        )
        secondGirdlePoint = adsk.core.Point3D.create(
            centroid2.x - axisDirection.x * info2.radius,
            centroid2.y - axisDirection.y * info2.radius,
            centroid2.z - axisDirection.z * info2.radius
        )
        midpoint = adsk.core.Point3D.create(
            (firstGirdlePoint.x + secondGirdlePoint.x) * 0.5,
            (firstGirdlePoint.y + secondGirdlePoint.y) * 0.5,
            (firstGirdlePoint.z + secondGirdlePoint.z) * 0.5
        )

        avgNormal = averageVector([info1.getNormalizedNormal(), info2.getNormalizedNormal()], normalize=True)

        perpendicularDirection = axisDirection.crossProduct(avgNormal)
        perpendicularDirection.normalize()

        avgDiameter = info1.radius + info2.radius
        halfWidth = (avgDiameter * widthBetweenProngsRatio) * 0.5

        offsetPoints: list[adsk.core.Point3D] = []
        baseOffset = perpendicularDirection.copy()
        baseOffset.scaleBy(halfWidth)
        for direction in (-1, 1):
            prongOffset = baseOffset.copy()
            prongOffset.scaleBy(direction)
            offsetPoint = midpoint.copy()
            offsetPoint.translateBy(prongOffset)
            offsetPoints.append(offsetPoint)

        return offsetPoints, avgNormal, axisDirection, perpendicularDirection
    
    except:
        showMessage(f'calculateProngsPlacement: {traceback.format_exc()}\n', True)
        return None, None, None, None
