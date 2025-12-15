import adsk.core, adsk.fusion, traceback

from .showMessage import showMessage


def placeBody(body: adsk.fusion.BRepBody, newOriginPoint: adsk.core.Point3D, 
              newLengthDirection: adsk.core.Vector3D, newWidthDirection: adsk.core.Vector3D, 
              newNormal: adsk.core.Vector3D) -> None:
    """Places a body at a specific location with the given coordinate system.
    
    Transforms the body to align with the surface normal and tangent directions.
    
    Args:
        body: The BRepBody to transform
        newOriginPoint: The new origin point for the body
        newLengthDirection: The new length direction vector
        newWidthDirection: The new width direction vector
        newNormal: The new normal direction vector
    """
    try:
        if body is None:
            return

        temporaryBRep = adsk.fusion.TemporaryBRepManager.get()

        # Create a transformation matrix that aligns the body with the face's local coordinate system.
        transformation = adsk.core.Matrix3D.create()
        transformation.setWithCoordinateSystem(newOriginPoint, newLengthDirection, newWidthDirection, newNormal)
        temporaryBRep.transform(body, transformation)

    except:
        showMessage(f'placeBody: {traceback.format_exc()}\n', True)

def copyAttributes(sourceBody: adsk.fusion.BRepBody, targetBody: adsk.fusion.BRepBody) -> None:
    """
    Copies attributes, appearance, material, and name from sourceBody to targetBody.
    
    Args:
        sourceBody: The body to copy attributes from
        targetBody: The body to copy attributes to
    """
    try:
        if sourceBody.appearance:
            targetBody.appearance = sourceBody.appearance
        
        if sourceBody.material:
            targetBody.material = sourceBody.material
        
        targetBody.name = sourceBody.name
        
        for attr in sourceBody.attributes:
            targetBody.attributes.add(attr.groupName, attr.name, attr.value)
    
    except:
        showMessage(f'copyAttributes: {traceback.format_exc()}\n', True)