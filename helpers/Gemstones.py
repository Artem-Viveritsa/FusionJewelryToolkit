import adsk.core, adsk.fusion
import os
import traceback

from .. import constants
from .. import strings
from .showMessage import showMessage
from .Utilities import getDataFromPointAndFace


class GemstoneInfo:
    """Stores pre-computed geometric data for a gemstone."""
    def __init__(self, body: adsk.fusion.BRepBody):
        """Initialize gemstone info by extracting geometry from the body.
        
        Args:
            body: The BRepBody representing the gemstone
        """
        self.body = body
        self.topFace = None
        self.topPlane = None
        self.cylindricalFace = None
        self.cylinder = None
        self.centroid = None
        self.radius = 0.0
        self.flip = False
        self.absoluteDepthOffset = 0.0
        self.relativeDepthOffset = 0.0
        
        self._extractGeometryFromBody()
        self._extractParametersFromAttributes()
    
    def _extractGeometryFromBody(self) -> None:
        """Extract geometric information (faces, planes, centroid) from the body."""
        try:
            # Find top face (largest planar face)
            self.topFace = sorted(self.body.faces, key=lambda x: x.area, reverse=True)[0]
            self.topPlane = adsk.core.Plane.cast(self.topFace.geometry)
            
            # Find the cylindrical girdle face
            normal = self.topPlane.normal
            for face in self.body.faces:
                if face.geometry.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType:
                    tempCylinder = adsk.core.Cylinder.cast(face.geometry)
                    cylinderAxis = tempCylinder.axis
                    if cylinderAxis.isParallelTo(normal):
                        self.cylindricalFace = face
                        self.cylinder = tempCylinder
                        self.centroid = face.centroid
                        self.radius = tempCylinder.radius
                        break
            
            # Fallback to bounding box if no cylindrical face found
            if self.cylindricalFace is None or self.cylinder is None:
                bbox = self.body.boundingBox
                self.centroid = bbox.minPoint.copy()
                self.centroid.translateBy(adsk.core.Vector3D.create(
                    (bbox.maxPoint.x - bbox.minPoint.x) / 2,
                    (bbox.maxPoint.y - bbox.minPoint.y) / 2,
                    (bbox.maxPoint.z - bbox.minPoint.z) / 2
                ))
                # Create a fake cylinder for fallback
                radius = max(bbox.maxPoint.x - bbox.minPoint.x, bbox.maxPoint.y - bbox.minPoint.y) / 2
                class FakeCylinder:
                    def __init__(self, r):
                        self.radius = r
                self.cylinder = FakeCylinder(radius)
                self.radius = radius

        except Exception as e:
            showMessage(f'_extractGeometryFromBody error: {str(e)}\n', False)
    
    def _extractParametersFromFeature(self) -> None:
        """Extract flip, absoluteDepthOffset, and relativeDepthOffset from the parent feature."""
        try:
            for feature in self.body.parentComponent.features.customFeatures:
                if feature.name.startswith(strings.GEMSTONES_ON_FACE_AT_POINTS):
                    for subFeature in feature.features:
                        if subFeature.objectType == adsk.fusion.BaseFeature.classType():
                            baseFeature = adsk.fusion.BaseFeature.cast(subFeature)
                            for body in baseFeature.bodies:
                                if body.entityToken == self.body.entityToken:
                                    # Found the matching feature, extract parameters
                                    try:
                                        flipParam = feature.parameters.itemById('flip')
                                        self.flip = flipParam.expression.lower() == 'true' if flipParam else False
                                    except:
                                        self.flip = False
                                    
                                    try:
                                        absoluteDepthOffsetParam = feature.parameters.itemById('absoluteDepthOffset')
                                        self.absoluteDepthOffset = absoluteDepthOffsetParam.value if absoluteDepthOffsetParam else 0.0
                                    except:
                                        self.absoluteDepthOffset = 0.0
                                    
                                    try:
                                        relativeDepthOffsetParam = feature.parameters.itemById('relativeDepthOffset')
                                        self.relativeDepthOffset = relativeDepthOffsetParam.value if relativeDepthOffsetParam else 0.0
                                    except:
                                        self.relativeDepthOffset = 0.0
                                    return
        except Exception as e:
            showMessage(f'_extractParametersFromFeature error: {str(e)}\n', False)
    
    def _extractParametersFromAttributes(self) -> None:
        """Extract flip, absoluteDepthOffset, and relativeDepthOffset from the body attributes."""
        try:
            attr = self.body.attributes.itemByName(strings.PREFIX, strings.GEMSTONE_IS_FLIPPED)
            if attr: self.flip = attr.value.lower() == 'true'
            
            attr = self.body.attributes.itemByName(strings.PREFIX, strings.GEMSTONE_ABSOLUTE_DEPTH_OFFSET)
            if attr: self.absoluteDepthOffset = float(attr.value)
            
            attr = self.body.attributes.itemByName(strings.PREFIX, strings.GEMSTONE_RELATIVE_DEPTH_OFFSET)
            if attr: self.relativeDepthOffset = float(attr.value)

        except Exception as e:
            showMessage(f'_extractParametersFromAttributes error: {str(e)}\n', False)
    
    def getNormalizedNormal(self) -> adsk.core.Vector3D:
        """Get the normalized normal vector from topPlane, accounting for flip state."""
        if self.topPlane is None:
            return None
        
        normal = self.topPlane.normal.copy()
        normal.normalize()
        
        if self.flip:
            normal.scaleBy(-1)
        
        return normal
    
    def getTotalDepthOffset(self) -> float:
        """Get the total depth offset: absolute + relative (relative is multiplied by gemstone size)."""
        return self.absoluteDepthOffset + (self.relativeDepthOffset * self.radius * 2)


def extractGemstonesInfo(gemstones: list[adsk.fusion.BRepBody]) -> list[GemstoneInfo]:
    """
    Extract geometric information from each gemstone.
    Each GemstoneInfo object computes its own geometry and parameters.
    Returns a list of GemStoneInfo objects, or None if any gemstone is invalid.
    """
    
    if not gemstones or len(gemstones) == 0:
        return None
    
    gemstoneInfos = []

    for gemstone in gemstones:
        try:
            gemstoneInfo = GemstoneInfo(gemstone)
            gemstoneInfos.append(gemstoneInfo)
        except Exception as e:
            showMessage(f'extractGemstonesInfo failed for gemstone: {str(e)}\n', True)
            return None
        
    return gemstoneInfos


def findValidConnections(gemstoneInfos: list[GemstoneInfo], maxGap: float) -> list[tuple[GemstoneInfo, GemstoneInfo]]:
    """Find all valid connections between gemstones based on distance constraints.

    Args:
        gemstoneInfos: List of gemstone information objects.
        maxGap: Maximum gap between gemstones to create a connection.

    Returns:
        List of tuples containing GemstoneInfo pairs that should be connected.
    """
    connections = []
    
    for i in range(len(gemstoneInfos)):
        for j in range(i + 1, len(gemstoneInfos)):
            info1 = gemstoneInfos[i]
            info2 = gemstoneInfos[j]
            
            distance = info1.centroid.distanceTo(info2.centroid)
            maxAllowedDistance = info1.radius + maxGap + info2.radius
            
            if distance <= maxAllowedDistance:
                connections.append((info1, info2))
    
    return connections


def createGemstone(face: adsk.fusion.BRepFace, point: adsk.core.Point3D, size: float, resourcesFolder: str, flip: bool = False, absoluteDepthOffset: float = 0.0, relativeDepthOffset: float = 0.0):
    """Create a gemstone body based on the face, point, size, and flip.

    Args:
        face: The face where the gemstone will be placed.
        point: The point on the face where the gemstone will be created.
        size: The size of the gemstone.
        resourcesFolder: Path to the resources folder containing gemstone models.
        flip: Whether to flip the gemstone orientation.
        absoluteDepthOffset: The absolute depth offset.
        relativeDepthOffset: The relative depth offset.

    Returns:
        The created gemstone body or None if creation failed.
    """
    try:
        if face is None or point is None: return None

        temporaryBRep: adsk.fusion.TemporaryBRepManager = adsk.fusion.TemporaryBRepManager.get()

        
        pointOnFace, normal, lengthDir, widthDir = getDataFromPointAndFace(face, point)
        if pointOnFace is None:
            return None

        
        filePath = os.path.join(resourcesFolder, strings.GEMSTONE_ROUND_CUT + '.sat')
        gemstone = temporaryBRep.createFromFile(filePath).item(0)
        
        cylindricalFace = list(filter(lambda x: x.geometry.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType, gemstone.faces))[0]
        originPoint = cylindricalFace.centroid

        girdleThickness = abs(cylindricalFace.boundingBox.minPoint.z - cylindricalFace.boundingBox.maxPoint.z)

        lengthDir.scaleBy(size)
        widthDir.scaleBy(size)
        normal.scaleBy(size)

        translate = normal.copy()
        translate.scaleBy(girdleThickness / 2)
        pointOnFace.translateBy(translate)

        
        
        originalNormal = normal.copy()
        originalNormal.normalize()
        
        totalDepthOffset = absoluteDepthOffset + (relativeDepthOffset * size)
        offsetVector = originalNormal.copy()
        offsetVector.scaleBy(totalDepthOffset)
        pointOnFace.translateBy(offsetVector)

        if flip: normal.scaleBy(-1)

        transformation = adsk.core.Matrix3D.create()
        transformation.setToAlignCoordinateSystems(
            originPoint, constants.xVector, constants.yVector, constants.zVector,
            pointOnFace, lengthDir, widthDir, normal
            )
        temporaryBRep.transform(gemstone, transformation)

        return gemstone
    
    except:
        showMessage(f'createGemstone: {traceback.format_exc()}\n', True)


def updateGemstone(body: adsk.fusion.BRepBody, face: adsk.fusion.BRepFace, point: adsk.core.Point3D, size: float = 1.5, flip: bool = False, absoluteDepthOffset: float = 0.0, relativeDepthOffset: float = 0.0) -> adsk.fusion.BRepBody | None:
    """Update an existing gemstone body with new parameters.

    Args:
        body: The existing gemstone body to update.
        face: The face where the gemstone is placed.
        point: The point on the face where the gemstone should be.
        size: The new size of the gemstone.
        flip: Whether to flip the gemstone orientation.
        absoluteDepthOffset: The absolute depth offset.
        relativeDepthOffset: The relative depth offset.

    Returns:
        The updated gemstone body or None if update failed.
    """
    try:
        if body is None or face is None or point is None: return None

        temporaryBRep = adsk.fusion.TemporaryBRepManager.get()
        tempBody = temporaryBRep.copy(body)

        topFace = sorted(tempBody.faces, key = lambda x: x.area, reverse = True)[0]
        topPlane = adsk.core.Plane.cast(topFace.geometry)
        cylindricalFace = list(filter(lambda x: x.geometry.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType, tempBody.faces))[0]
        cylinder = adsk.core.Cylinder.cast(cylindricalFace.geometry)
        gridleCentroid = cylindricalFace.centroid

        oldSize = cylinder.radius * 2
        sizeScale = size / oldSize
        

        oldNormal = topPlane.normal
        if flip: oldNormal.scaleBy(-1)

        transformation = adsk.core.Matrix3D.create()
        transformation.setToAlignCoordinateSystems(
            gridleCentroid, topPlane.uDirection, topPlane.vDirection, oldNormal,
            constants.zeroPoint, constants.xVector, constants.yVector, constants.zVector
            )
        temporaryBRep.transform(tempBody, transformation)

        girdleThickness = abs(cylindricalFace.boundingBox.minPoint.z - cylindricalFace.boundingBox.maxPoint.z)

        
        newFacePoint, newFaceNormal, newLengthDirection, newWidthDirection = getDataFromPointAndFace(face, point)
        if newFacePoint is None:
            return None

        newLengthDirection.scaleBy(sizeScale)
        newWidthDirection.scaleBy(sizeScale)
        newFaceNormal.scaleBy(sizeScale)

        translate = newFaceNormal.copy()
        translate.scaleBy(girdleThickness / 2)
        newFacePoint.translateBy(translate)

        originalNormal = newFaceNormal.copy()
        originalNormal.normalize()
        
        totalDepthOffset = absoluteDepthOffset + (relativeDepthOffset * size)
        offsetVector = originalNormal.copy()
        offsetVector.scaleBy(totalDepthOffset)
        newFacePoint.translateBy(offsetVector)
        
        transformation.setToIdentity()
        transformation.setToAlignCoordinateSystems(
            constants.zeroPoint, constants.xVector, constants.yVector, constants.zVector,
            newFacePoint, newLengthDirection, newWidthDirection, newFaceNormal
            )
        temporaryBRep.transform(tempBody, transformation)

        return tempBody
    
    except:
        showMessage(f'updateGemstone: {traceback.format_exc()}\n', True)
        

def setGemstoneAttributes(body: adsk.fusion.BRepBody, flip: bool = None, absoluteDepthOffset: float = None, relativeDepthOffset: float = None):
    """Set the name and attributes for a gemstone body.

    Args:
        body: The gemstone body to set attributes on.
        flip: Whether the gemstone is flipped. If None, attribute is not set.
        absoluteDepthOffset: The absolute depth offset. If None, attribute is not set.
        relativeDepthOffset: The relative depth offset. If None, attribute is not set.
    """
    body.name = strings.GEMSTONE_ROUND_CUT
    body.attributes.add(strings.PREFIX, strings.ENTITY, strings.GEMSTONE)
    body.attributes.add(strings.PREFIX, strings.GEMSTONE_CUT, strings.GEMSTONE_ROUND_CUT)
    
    if flip is not None:
        body.attributes.add(strings.PREFIX, strings.GEMSTONE_IS_FLIPPED, str(flip).lower())
    if absoluteDepthOffset is not None:
        body.attributes.add(strings.PREFIX, strings.GEMSTONE_ABSOLUTE_DEPTH_OFFSET, str(absoluteDepthOffset))
    if relativeDepthOffset is not None:
        body.attributes.add(strings.PREFIX, strings.GEMSTONE_RELATIVE_DEPTH_OFFSET, str(relativeDepthOffset))



def updateGemstoneFeature(customFeature: adsk.fusion.CustomFeature):
    """Update the attributes of all gemstone bodies in the custom feature.

    Args:
        customFeature: The custom feature containing the gemstone bodies.
    """
    try:
        flip = customFeature.parameters.itemById('flip').expression.lower() == 'true'
    except:
        flip = None
    
    try:
        absoluteDepthOffset = customFeature.parameters.itemById('absoluteDepthOffset').value
    except:
        absoluteDepthOffset = None
    
    try:
        relativeDepthOffset = customFeature.parameters.itemById('relativeDepthOffset').value
    except:
        relativeDepthOffset = None
    
    for feature in customFeature.features:
        if feature.objectType == adsk.fusion.BaseFeature.classType():
            baseFeature: adsk.fusion.BaseFeature = feature
            for body in baseFeature.bodies:
                setGemstoneAttributes(body, flip, absoluteDepthOffset, relativeDepthOffset)


diamondMaterial = constants.materialLibrary.materials.itemByName('Diamond') 