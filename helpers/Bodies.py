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

        transformation = adsk.core.Matrix3D.create()
        transformation.setWithCoordinateSystem(newOriginPoint, newLengthDirection, newWidthDirection, newNormal)
        temporaryBRep.transform(body, transformation)

    except:
        showMessage(f'placeBody: {traceback.format_exc()}\n', True)


def copyAttributes(sourceBody: adsk.fusion.BRepBody, targetBody: adsk.fusion.BRepBody) -> None:
    """Copy attributes, appearance, material, and name from sourceBody to targetBody.

    Args:
        sourceBody: The body to copy attributes from.
        targetBody: The body to copy attributes to.
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


def copyBodyAttributes(customFeature: adsk.fusion.CustomFeature) -> None:
    """Copy attributes from source bodies to all output bodies of a custom feature.

    Source bodies are retrieved from the custom feature's dependencies using the
    'firstBodyFace{i}' naming convention. Output bodies are mapped cyclically to
    source bodies, so this works both for 1:1 mappings and for patterns where
    multiple output bodies are generated from each source body.

    Args:
        customFeature: The custom feature whose output bodies should be updated.
    """
    try:
        baseFeature: adsk.fusion.BaseFeature = None

        for feature in customFeature.features:
            if feature.objectType == adsk.fusion.BaseFeature.classType():
                baseFeature = feature
                break
        if baseFeature is None:
            return

        sourceBodies: list[adsk.fusion.BRepBody] = []
        i = 0
        while True:
            faceDep = customFeature.dependencies.itemById(f'firstBodyFace{i}')
            if faceDep is None:
                break
            face = adsk.fusion.BRepFace.cast(faceDep.entity)
            if face is None or face.body is None:
                break
            sourceBodies.append(face.body)
            i += 1

        if len(sourceBodies) == 0:
            return

        numSourceBodies = len(sourceBodies)
        for i in range(baseFeature.bodies.count):
            sourceIndex = i % numSourceBodies
            copyAttributes(sourceBodies[sourceIndex], baseFeature.bodies.item(i))

    except:
        showMessage(f'copyBodyAttributes: {traceback.format_exc()}\n', True)
