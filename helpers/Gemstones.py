import adsk.core, adsk.fusion

from .. import strings
from .showMessage import showMessage


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
        # self._extractParametersFromFeature()
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
    
    # flip_statuses = []
    # design: adsk.fusion.Design = adsk.core.Application.get().activeProduct
    for gemstone in gemstones:
        
        # designBody = design.findEntityByToken(gemstone.entityToken)[0]
        # attr = designBody.attributes.itemByName(strings.PREFIX, strings.GEMSTONE_IS_FLIPPED)
        # flip_statuses.append(attr.value)

        try:
            gemstoneInfo = GemstoneInfo(gemstone)
            gemstoneInfos.append(gemstoneInfo)
        except Exception as e:
            showMessage(f'extractGemstonesInfo failed for gemstone: {str(e)}\n', True)
            return None
    
    # showMessage(f'Gemstone flip statuses: {flip_statuses}\n', False)
    
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