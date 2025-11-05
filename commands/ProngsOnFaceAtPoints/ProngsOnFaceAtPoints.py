import os
import adsk.core, adsk.fusion, traceback

from ... import strings
from ...helpers.showMessage import showMessage


_handlers = []

_app: adsk.core.Application = None
_ui: adsk.core.UserInterface = None

_customFeatureDefinition: adsk.fusion.CustomFeature = None

_editedCustomFeature: adsk.fusion.CustomFeature = None
_restoreTimelineObject: adsk.fusion.TimelineObject = None
_isRolledForEdit: bool = False

_faceSelectionInput: adsk.core.SelectionCommandInput = None
_pointSelectionInput: adsk.core.SelectionCommandInput = None

_sizeValueInput: adsk.core.ValueCommandInput = None
_heightValueInput: adsk.core.ValueCommandInput = None

RESOURCES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

COMMAND_ID = strings.PREFIX + strings.PRONGS_COMMAND_NAME
CREATE_COMMAND_ID = COMMAND_ID + 'Create'
EDIT_COMMAND_ID = COMMAND_ID + 'Edit'

CREATE_COMMAND_NAME = 'Create Prongs at Points'
CREATE_COMMAND_DESCRIPTION = 'Creates prongs at selected points on a face.'

EDIT_COMMAND_NAME = 'Edit Prongs'
EDIT_COMMAND_DESCRIPTION = 'Edits the parameters of existing prongs.'

SELECT_FACE_NAME = 'Select Face'
SELECT_FACE_PROMPT = 'Select the face where the prongs will be placed.'

SELECT_POINT_NAME = 'Select Points'
SELECT_POINT_PROMPT = 'Select the points on the face for the prong centers.'


def run(context):
    try:
        global _app, _ui, _customFeatureDefinition
        _app = adsk.core.Application.get()
        _ui  = _app.userInterface

        createCommandDefinition = _ui.commandDefinitions.addButtonDefinition(CREATE_COMMAND_ID, 
                                                                CREATE_COMMAND_NAME, 
                                                                CREATE_COMMAND_DESCRIPTION, 
                                                                RESOURCES_FOLDER)        

        solidWorkspace = _ui.workspaces.itemById('FusionSolidEnvironment')
        panel = solidWorkspace.toolbarPanels.itemById('SolidCreatePanel')
        control = panel.controls.addCommand(createCommandDefinition, '', False)     
        control.isPromoted = True

        editCommandDefinition = _ui.commandDefinitions.addButtonDefinition(EDIT_COMMAND_ID, 
                                                            EDIT_COMMAND_NAME, 
                                                            EDIT_COMMAND_DESCRIPTION, 
                                                            RESOURCES_FOLDER)        

        createCommandCreated = CreateCommandCreatedHandler()
        createCommandDefinition.commandCreated.add(createCommandCreated)
        _handlers.append(createCommandCreated)

        editCommandCreated = EditCommandCreatedHandler()
        editCommandDefinition.commandCreated.add(editCommandCreated)
        _handlers.append(editCommandCreated)

        _customFeatureDefinition = adsk.fusion.CustomFeatureDefinition.create(COMMAND_ID, strings.PRONGS_COMMAND_NAME, RESOURCES_FOLDER)
        _customFeatureDefinition.editCommandId = EDIT_COMMAND_ID

        computeCustomFeature = ComputeCustomFeature()
        _customFeatureDefinition.customFeatureCompute.add(computeCustomFeature)
        _handlers.append(computeCustomFeature)
    except:
        showMessage(f'Run Failed:\n{traceback.format_exc()}', True)


def stop(context):
    try:
        solidWorkspace = _ui.workspaces.itemById('FusionSolidEnvironment')
        panel = solidWorkspace.toolbarPanels.itemById('SolidCreatePanel')
        control = panel.controls.itemById(CREATE_COMMAND_ID)
        if control:
            control.deleteMe()
            
        commandDefinition = _ui.commandDefinitions.itemById(CREATE_COMMAND_ID)
        if commandDefinition:
            commandDefinition.deleteMe()

        commandDefinition = _ui.commandDefinitions.itemById(EDIT_COMMAND_ID)
        if commandDefinition:
            commandDefinition.deleteMe()
    except:
        showMessage(f'Stop Failed:\n{traceback.format_exc()}', True)


# This class handles the creation of the command dialog for creating new prongs at points.
# It sets up all necessary input controls, including selections for face and points, value inputs for size and height.
# It also connects event handlers for validation, preview, and execution.
class CreateCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _faceSelectionInput, _pointSelectionInput, _sizeValueInput, _heightValueInput
            
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs
            defaultLengthUnits = _app.activeProduct.unitsManager.defaultLengthUnits

            _faceSelectionInput = inputs.addSelectionInput('selectFace', SELECT_FACE_NAME, SELECT_FACE_PROMPT)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _faceSelectionInput.tooltip = SELECT_FACE_PROMPT
            _faceSelectionInput.setSelectionLimits(1, 1)

            _pointSelectionInput = inputs.addSelectionInput('selectPoint', SELECT_POINT_NAME, SELECT_POINT_PROMPT)
            _pointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchPoints)
            _pointSelectionInput.tooltip = SELECT_POINT_PROMPT
            _pointSelectionInput.setSelectionLimits(1)

            # Create value input for the prong size.
            size = adsk.core.ValueInput.createByReal(0.04)
            _sizeValueInput = inputs.addValueInput('size', 'Size', defaultLengthUnits, size)
            _sizeValueInput.tooltip = "The diameter of the prong base.\nThis determines the overall size of the prong at its base."

            # Create value input for the prong height.
            height = adsk.core.ValueInput.createByReal(0.04)
            _heightValueInput = inputs.addValueInput('height', 'Height', defaultLengthUnits, height)
            _heightValueInput.tooltip = "The height of the prong extending from the face.\nThis controls how tall the prong is above the surface."

            # Connect to the needed command related events.
            onPreSelect = PreSelectHandler()
            command.preSelect.add(onPreSelect)
            _handlers.append(onPreSelect)

            onValidate = ValidateInputsHandler()
            command.validateInputs.add(onValidate)
            _handlers.append(onValidate)

            onExecutePreview = ExecutePreviewHandler()
            command.executePreview.add(onExecutePreview)
            _handlers.append(onExecutePreview)

            onExecute = CreateExecuteHandler()
            command.execute.add(onExecute)
            _handlers.append(onExecute)  

        except:
            showMessage(f'CreateCommandCreatedHandler: {traceback.format_exc()}\n', True)


# This class handles the creation of the command dialog for editing existing prongs custom feature.
# It retrieves the selected custom feature, populates inputs with existing parameter values and dependencies,
# and connects event handlers for editing operations, including activation, validation, preview, and execution.
class EditCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _editedCustomFeature, _faceSelectionInput, _pointSelectionInput, _sizeValueInput, _heightValueInput
            
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs
            defaultLengthUnits = _app.activeProduct.unitsManager.defaultLengthUnits

            # Get the currently selected custom feature from the timeline.
            _editedCustomFeature = _ui.activeSelections.item(0).entity
            if _editedCustomFeature is None:
                return

            _faceSelectionInput = inputs.addSelectionInput('selectFace', SELECT_FACE_NAME, SELECT_FACE_PROMPT)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _faceSelectionInput.tooltip = SELECT_FACE_PROMPT
            _faceSelectionInput.setSelectionLimits(1, 1)

            _pointSelectionInput = inputs.addSelectionInput('selectPoint', SELECT_POINT_NAME, SELECT_POINT_PROMPT)
            _pointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchPoints)
            _pointSelectionInput.tooltip = SELECT_POINT_PROMPT
            _pointSelectionInput.setSelectionLimits(1)

            # Get the collection of custom parameters for this custom feature.
            parameters = _editedCustomFeature.parameters

            # Create value inputs using existing parameter expressions to preserve user-defined values and equations.
            size = adsk.core.ValueInput.createByString(parameters.itemById('size').expression)
            _sizeValueInput = inputs.addValueInput('size', 'Size', defaultLengthUnits, size)
            _sizeValueInput.tooltip = "The diameter of the prong base.\nThis determines the overall size of the prong at its base."

            heightValue = adsk.core.ValueInput.createByString(parameters.itemById('height').expression)
            _heightValueInput = inputs.addValueInput('height', 'Height', defaultLengthUnits, heightValue)
            _heightValueInput.tooltip = "The height of the prong extending from the face.\nThis controls how tall the prong is above the surface."

            # Connect to the needed command related events.
            onPreSelect = PreSelectHandler()
            command.preSelect.add(onPreSelect)
            _handlers.append(onPreSelect)

            onValidate = ValidateInputsHandler()
            command.validateInputs.add(onValidate)
            _handlers.append(onValidate)

            onExecutePreview = ExecutePreviewHandler()
            command.executePreview.add(onExecutePreview)
            _handlers.append(onExecutePreview)

            onActivate = EditActivateHandler()
            command.activate.add(onActivate)
            _handlers.append(onActivate)

            onDestroy = EditDestroyHandler()
            command.destroy.add(onDestroy)
            _handlers.append(onDestroy)

            onExecute = EditExecuteHandler()
            command.execute.add(onExecute)
            _handlers.append(onExecute)  

        except:
            showMessage(f'EditCommandCreatedHandler: {traceback.format_exc()}\n', True)


# Controls what the user can select when the command is running.
# This checks to make sure the points are on a planar face and the
# body the points are on is not an external reference.
class PreSelectHandler(adsk.core.SelectionEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.SelectionEventArgs.cast(args)
            type = eventArgs.selection.entity.objectType

            if type == adsk.fusion.BRepFace.classType():
                if eventArgs.selection.entity is None:
                    eventArgs.isSelectable = False
                    return

            if type == adsk.fusion.SketchPoint.classType():
                preSelectPoint: adsk.fusion.SketchPoint = eventArgs.selection.entity

                # Prevent selection of sketch points from external references (XRef) as they cannot be reliably tracked across assemblies.
                if preSelectPoint.assemblyContext:
                    occurrence = preSelectPoint.assemblyContext
                    if occurrence.isReferencedComponent:
                        eventArgs.isSelectable = False
                        return
                                
        except:
            showMessage(f'PreSelectHandler: {traceback.format_exc()}\n', True)


# Event handler for the validateInputs event.
class ValidateInputsHandler(adsk.core.ValidateInputsEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.ValidateInputsEventArgs.cast(args)

            if _faceSelectionInput.selectionCount != 1:
                eventArgs.areInputsValid = False
                return

            if _pointSelectionInput.selectionCount < 1:
                eventArgs.areInputsValid = False
                return

            # Verify all selections are valid
            if not _faceSelectionInput.selection(0).isValid:
                eventArgs.areInputsValid = False
                return

            for i in range(_pointSelectionInput.selectionCount):
                if not _pointSelectionInput.selection(i).isValid:
                    eventArgs.areInputsValid = False
                    return

            # Verify the inputs have valid expressions.
            if not all([_sizeValueInput.isValidExpression, _heightValueInput.isValidExpression]):
                eventArgs.areInputsValid = False
                return

            # Enforce minimum size constraints to prevent degenerate geometry.
            if _sizeValueInput.value < 0.01:
                eventArgs.areInputsValid = False
                return
            
            if _heightValueInput.value < 0.01:
                eventArgs.areInputsValid = False
                return
            
        except:
            showMessage(f'ValidateInputsHandler: {traceback.format_exc()}\n', True)

# Event handler for the executePreview event.
class ExecutePreviewHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            if _faceSelectionInput.selectionCount < 1 or _pointSelectionInput.selectionCount < 1:
                return

            # Cache face entity
            faceEntity: adsk.fusion.BRepFace = _faceSelectionInput.selection(0).entity
            if faceEntity is None:
                return

            # Cache all point entities before creating bodies to ensure consistent references throughout the operation.
            pointEntities = []
            for i in range(_pointSelectionInput.selectionCount):
                point = _pointSelectionInput.selection(i).entity
                if point is None:
                    return
                pointEntities.append(point)

            size = _sizeValueInput.value
            depth = _heightValueInput.value

            prongs = []
            for pointEntity in pointEntities:
                prong = createBody(faceEntity, pointEntity.worldGeometry, size, depth)
                if prong is None:
                    return
                prongs.append(prong)

            # Create a base feature to contain the prong bodies, allowing them to be grouped and managed as a single unit.
            parametricBody = faceEntity.body
            component = parametricBody.parentComponent

            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()
            for i in range(len(prongs)):
                body = component.bRepBodies.add(prongs[i], baseFeature)
                handleNewBody(body)
            baseFeature.finishEdit()

        except:
            showMessage(f'ExecutePreviewHandler: {traceback.format_exc()}\n', True)

# Event handler for the execute event of the create command.
class CreateExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.CommandEventArgs.cast(args)

            # Cache face entity
            faceEntity: adsk.fusion.BRepFace = _faceSelectionInput.selection(0).entity
            parametricBody = faceEntity.body
            component = parametricBody.parentComponent

            # Cache all points at the beginning to prevent selection invalidation during body creation.
            pointEntities: list[adsk.fusion.SketchPoint] = []
            for i in range(_pointSelectionInput.selectionCount):
                pointEntities.append(_pointSelectionInput.selection(i).entity)

            # Create a base feature and add the bodies.
            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()
            for i in range(len(pointEntities)):
                prong = createBody(faceEntity, pointEntities[i].worldGeometry, _sizeValueInput.value, _heightValueInput.value)
                if prong is None:
                    eventArgs.executeFailed = True
                    return
                body = component.bRepBodies.add(prong, baseFeature)
                handleNewBody(body)
                body.attributes.add(strings.PREFIX, 'PointEntityToken', pointEntities[i].entityToken)
            baseFeature.finishEdit()

            design: adsk.fusion.Design = _app.activeProduct
            defaultLengthUnits = design.unitsManager.defaultLengthUnits
            
            customFeatureInput = component.features.customFeatures.createInput(_customFeatureDefinition)

            # Add all dependencies first using cached points to establish the feature's geometric relationships.
            customFeatureInput.addDependency('face', faceEntity)
            for i in range(len(pointEntities)):
                customFeatureInput.addDependency(f'point{i}', pointEntities[i])

            # Add all parameters with their expressions to support user-defined equations and parametric updates.
            sizeInput = adsk.core.ValueInput.createByString(_sizeValueInput.expression)
            customFeatureInput.addCustomParameter('size', 'Size', sizeInput,
                                              defaultLengthUnits, True)
            
            depthInput = adsk.core.ValueInput.createByString(_heightValueInput.expression)             
            customFeatureInput.addCustomParameter('height', 'Height', depthInput,
                                              defaultLengthUnits, True) 

            customFeatureInput.setStartAndEndFeatures(baseFeature, baseFeature)
            
            component.features.customFeatures.add(customFeatureInput)

        except:
            eventArgs.executeFailed = True
            showMessage(f'CreateExecuteHandler: {traceback.format_exc()}\n', True)


# This class handles the activation of the edit command for a custom feature.
# It rolls back the timeline to the state before the feature, sets up transaction markers to preserve changes,
# and pre-selects the original face and point dependencies for editing.
class EditActivateHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature, _faceSelectionInput, _pointSelectionInput
            
            eventArgs = adsk.core.CommandEventArgs.cast(args)

            if _isRolledForEdit: return
            
            # Save the current timeline position to restore it after editing, ensuring the model state is preserved.
            design: adsk.fusion.Design = _app.activeProduct
            timeline = design.timeline
            markerPosition = timeline.markerPosition
            _restoreTimelineObject = timeline.item(markerPosition - 1)

            # Roll the timeline to just before the custom feature being edited to access the original geometry dependencies.
            _editedCustomFeature.timelineObject.rollTo(True)
            _isRolledForEdit = True

            command = eventArgs.command
            # Define a transaction marker so the timeline rollback is not aborted when preview updates occur.
            command.beginStep()

            # Get the face and points and add them to the selection inputs.
            faceEntity = _editedCustomFeature.dependencies.itemById('face').entity
            _faceSelectionInput.addSelection(faceEntity)
            
            # Iterate through all point dependencies and add them to the selection input for editing.
            i = 0
            while True:
                try:
                    dependency = _editedCustomFeature.dependencies.itemById(f'point{i}')
                    if dependency is None: break
                    sketchPoint = dependency.entity
                    if sketchPoint is not None: _pointSelectionInput.addSelection(sketchPoint)
                    i += 1
                except:
                    break

        except:
            showMessage(f'EditActivateHandler: {traceback.format_exc()}\n', True)
            pass


class EditDestroyHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _editedCustomFeature, _isRolledForEdit
            eventArgs = adsk.core.CommandEventArgs.cast(args)
            if eventArgs.terminationReason != adsk.core.CommandTerminationReason.CompletedTerminationReason:
                rollBack()
        except:
            showMessage(f'EditDeactivateHandler: {traceback.format_exc()}\n', True)


# Event handler for the execute event of the edit command.
class EditExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        global _editedCustomFeature, _isRolledForEdit, _restoreTimelineObject
        
        try:
            
            eventArgs = adsk.core.CommandEventArgs.cast(args)    

            # Cache face entity
            faceEntity = _faceSelectionInput.selection(0).entity
            pointCount = _pointSelectionInput.selectionCount
            pointEntities = []
            for i in range(pointCount):
                pointEntities.append(_pointSelectionInput.selection(i).entity)

            # Clear and rebuild dependencies to handle cases where the user selects different geometry during edit.
            _editedCustomFeature.dependencies.deleteAll()
            _editedCustomFeature.dependencies.add('face', faceEntity)

            for i in range(pointCount):
                _editedCustomFeature.dependencies.add(f'point{i}', pointEntities[i])

            # Update the parameters.
            _editedCustomFeature.parameters.itemById('size').expression = _sizeValueInput.expression
            _editedCustomFeature.parameters.itemById('height').expression = _heightValueInput.expression

            # Update the feature to recompute geometry and handle changes in point count or parameter values.
            updateFeature(_editedCustomFeature)

        except:
            showMessage(f'EditExecuteHandler: {traceback.format_exc()}\n', True)
        
        finally: rollBack()


# This class handles the recomputation of the custom feature when dependencies or parameters change.
# It updates the prong bodies within the base feature to reflect new values or geometry,
# ensuring the custom feature remains parametric and up-to-date.
class ComputeCustomFeature(adsk.fusion.CustomFeatureEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.fusion.CustomFeatureEventArgs.cast(args)
            customFeature = eventArgs.customFeature
            updateFeature(customFeature)

        except:
            showMessage(f'ComputeCustomFeature: {traceback.format_exc()}\n', True)



# Utility function that creates the prong body based on the face, point, size, and height.
def createBody(face: adsk.fusion.BRepFace, point: adsk.core.Point3D, size: float, height: float, flat: bool = True) -> adsk.fusion.BRepBody | None:
    try:
        if face is None or point is None: return None

        temporaryBRep: adsk.fusion.TemporaryBRepManager = adsk.fusion.TemporaryBRepManager.get()
        bodies = []

        radius = size / 2

        bottomPoint = adsk.core.Point3D.create(0, 0, -height)

        if flat:
            topPoint = adsk.core.Point3D.create(0, 0, height)
        else:
            topPoint = adsk.core.Point3D.create(0, 0, height - radius)
            bodies.append(temporaryBRep.createSphere(topPoint, radius))

        bodies.append(temporaryBRep.createCylinderOrCone(topPoint, radius, bottomPoint, radius))

        # Combine all bodies using Boolean union to create a single solid prong geometry.
        prong: adsk.fusion.BRepBody = None
        for body in bodies:
            if prong is None:
                prong = body
            else:
                temporaryBRep.booleanOperation(prong, body, adsk.fusion.BooleanTypes.UnionBooleanType)

        # Evaluate the face at the specified point to obtain the surface normal and tangent directions for proper orientation.
        evaluator = face.evaluator
        _, parameter = evaluator.getParameterAtPoint(point)
        _, pointOnFace = evaluator.getPointAtParameter(parameter)
        _, normal = evaluator.getNormalAtParameter(parameter)
        _, lengthDirection, _ = evaluator.getFirstDerivative(parameter)
        widthDirection = normal.crossProduct(lengthDirection)

        lengthDirection.normalize()
        widthDirection.normalize()
        normal.normalize()

        # Create a transformation matrix that aligns the prong with the face's local coordinate system.
        transformation = adsk.core.Matrix3D.create()
        transformation.setWithCoordinateSystem(pointOnFace, lengthDirection, widthDirection, normal)
        temporaryBRep.transform(prong, transformation)

        return prong
    
    except:
        showMessage(f'CreateBodies: {traceback.format_exc()}\n', True)
        return None
    
def updateBody(body: adsk.fusion.BRepBody, face: adsk.fusion.BRepFace, point: adsk.core.Point3D, size: float, height: float) -> adsk.fusion.BRepBody | None:
    try:
        if face is None or point is None: return None

        temporaryBRep = adsk.fusion.TemporaryBRepManager.get()
        tempBody = temporaryBRep.copy(body)

        planarFaces = list(filter(lambda x: x.geometry.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType, tempBody.faces))
        cylindricalFace = list(filter(lambda x: x.geometry.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType, tempBody.faces))[0]

        # if planarFaces.count == 0 or cylindricalFace == None: return None

        cylinder = adsk.core.Cylinder.cast(cylindricalFace.geometry)
        oldOriginPoint = cylindricalFace.centroid
        oldNormal = cylinder.axis

        oldHeight = planarFaces[0].centroid.distanceTo(planarFaces[1].centroid) / 2
        oldSize = cylinder.radius * 2

        sizeScale = size / oldSize
        heightScale = height / oldHeight

        oldEvaluator = cylindricalFace.evaluator
        _, oldParameter = oldEvaluator.getParameterAtPoint(oldOriginPoint)
        _, _, oldLengthDirection = oldEvaluator.getFirstDerivative(oldParameter)
        oldWidthDirection = oldLengthDirection.crossProduct(oldNormal)
        oldNormal.scaleBy(-1)

        oldLengthDirection.normalize()
        oldWidthDirection.normalize()
        oldNormal.normalize()

        zeroPoint = adsk.core.Point3D.create(0, 0, 0)
        xVector = adsk.core.Vector3D.create(1, 0, 0)
        yVector = adsk.core.Vector3D.create(0, 1, 0)
        zVector = adsk.core.Vector3D.create(0, 0, 1)

        transformation = adsk.core.Matrix3D.create()
        transformation.setToAlignCoordinateSystems(
            oldOriginPoint, oldLengthDirection, oldWidthDirection, oldNormal,
            zeroPoint, xVector, yVector, zVector
            )
        temporaryBRep.transform(tempBody, transformation)

        evaluator = face.evaluator
        _, parameter = evaluator.getParameterAtPoint(point)
        _, newOriginPoint = evaluator.getPointAtParameter(parameter)
        _, newNormal = evaluator.getNormalAtParameter(parameter)
        _, newLengthDirection, _ = evaluator.getFirstDerivative(parameter)
        newWidthDirection = newNormal.crossProduct(newLengthDirection)

        newLengthDirection.normalize()
        newWidthDirection.normalize()
        newNormal.normalize()

        newLengthDirection.scaleBy(sizeScale)
        newWidthDirection.scaleBy(sizeScale)
        newNormal.scaleBy(heightScale)
        
        transformation = adsk.core.Matrix3D.create()
        transformation.setToAlignCoordinateSystems(
            zeroPoint, xVector, yVector, zVector,
            newOriginPoint, newLengthDirection, newWidthDirection, newNormal
            )
        temporaryBRep.transform(tempBody, transformation)

        return tempBody
    
    except:
        showMessage(f'updateBody: {traceback.format_exc()}\n', True)


# Updates the bodies of an existing custom prongs feature.
def updateFeature(customFeature: adsk.fusion.CustomFeature) -> bool:
    try:
        # Locate the base feature that contains the prong bodies within the custom feature's feature collection.
        baseFeature: adsk.fusion.BaseFeature = None

        for feature in customFeature.features:
            if feature.objectType == adsk.fusion.BaseFeature.classType():
                baseFeature = feature
        if baseFeature is None: return False

        faceEntity: adsk.fusion.BRepFace = customFeature.dependencies.itemById('face').entity
        if faceEntity is None: return False

        # Collect all point dependencies in order to regenerate prongs for each point.
        points: list[adsk.fusion.SketchPoint] = []
        i = 0
        while True:
            dependency = customFeature.dependencies.itemById(f'point{i}')
            if dependency is None: break
            sketchPoint = dependency.entity
            if sketchPoint is None: break
            points.append(sketchPoint)
            i += 1
        if len(points) == 0: return False

        size = customFeature.parameters.itemById('size').value
        depth = customFeature.parameters.itemById('height').value

        component = faceEntity.body.parentComponent

        baseFeature.startEdit()
        
        # Update existing bodies or add new ones to handle parameter changes and point count modifications.
        for i in range(len(points)):
            point = points[i]

            if i < baseFeature.bodies.count:
                currentBody = baseFeature.bodies.item(i)
                newBody = updateBody(currentBody, faceEntity, point.worldGeometry, size, depth)
                if newBody is not None:
                    baseFeature.updateBody(currentBody, newBody)
                else:
                    baseFeature.finishEdit()
                    return False
            else:
                prong = createBody(faceEntity, point.worldGeometry, size, depth)
                if prong is None:
                    baseFeature.finishEdit()
                    return False
                body = component.bRepBodies.add(prong, baseFeature)
                handleNewBody(body)
                body.attributes.add(strings.PREFIX, 'PointEntityToken', point.entityToken)

        # Remove extra bodies if the point count has decreased during editing.
        while baseFeature.bodies.count > len(points):
            baseFeature.bodies.item(baseFeature.bodies.count - 1).deleteMe()

        baseFeature.finishEdit()

        return True
    
    except:
        showMessage(f'UpdateBody: {traceback.format_exc()}\n', True)
        return False
    

def handleNewBody(body: adsk.fusion.BRepBody) -> bool:
    try:
        body.name = strings.PRONG
        body.attributes.add(strings.PREFIX, strings.ENTITY, strings.PRONG)
    except:
        showMessage(f'handleNewBody: {traceback.format_exc()}\n', True)
        return False

def rollBack():
    global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature
    if _isRolledForEdit:
        _restoreTimelineObject.rollTo(False)
        _isRolledForEdit = False
    _editedCustomFeature = None