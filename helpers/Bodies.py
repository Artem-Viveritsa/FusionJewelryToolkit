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