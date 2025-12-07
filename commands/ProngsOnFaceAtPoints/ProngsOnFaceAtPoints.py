import os
import adsk.core, adsk.fusion, traceback

from ... import strings, constants
from ...helpers.showMessage import showMessage
from ...helpers.Prongs import createProng, updateProngAndNormalize, setProngAttributes, updateProngFeature
from ...helpers.Bodies import placeBody
from ...helpers.Surface import getDataFromPointAndFace


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

COMMAND_ID = strings.PREFIX + strings.PRONGS_ON_FACE_AT_POINTS
CREATE_COMMAND_ID = COMMAND_ID + 'Create'
EDIT_COMMAND_ID = COMMAND_ID + 'Edit'

createCommandInputDef = strings.InputDef(CREATE_COMMAND_ID, 'Create Prongs at Points', 'Creates prongs at selected points on a face.')
editCommandInputDef = strings.InputDef(EDIT_COMMAND_ID, 'Edit Prongs', 'Edits the parameters of existing prongs.')

selectFaceInputDef = strings.InputDef(
    'selectFace',
    'Select Face or Plane',
    'Select the face or construction plane where the prongs will be placed.'
    )

selectPointsInputDef = strings.InputDef(
    'selectPoint',
    'Select Points',
    'Select the points on the face for the prong centers.'
    )

sizeInputDef = strings.InputDef(
    'size', 
    'Size', 
    "Prong base diameter.\nDetermines the width of the prong at its base."
    )

heightInputDef = strings.InputDef(
    'height', 
    'Height', 
    "Prong height above the surface.\nControls how tall the prong extends."
    )


def run(panel: adsk.core.ToolbarPanel):
    """Initialize the prongs command when the add-in is loaded.
    
    Sets up command definitions, UI elements, and event handlers.
    
    Args:
        panel: The toolbar panel to add the command to
    """
    try:
        global _app, _ui, _customFeatureDefinition
        _app = adsk.core.Application.get()
        _ui  = _app.userInterface

        createCommandDefinition = _ui.commandDefinitions.addButtonDefinition(createCommandInputDef.id, 
                                                                createCommandInputDef.name, 
                                                                createCommandInputDef.tooltip, 
                                                                RESOURCES_FOLDER)
        control = panel.controls.addCommand(createCommandDefinition, '', False)     
        control.isPromoted = True

        editCommandDefinition = _ui.commandDefinitions.addButtonDefinition(editCommandInputDef.id, 
                                                            editCommandInputDef.name, 
                                                            editCommandInputDef.tooltip, 
                                                            RESOURCES_FOLDER)        

        createCommandCreated = CreateCommandCreatedHandler()
        createCommandDefinition.commandCreated.add(createCommandCreated)
        _handlers.append(createCommandCreated)

        editCommandCreated = EditCommandCreatedHandler()
        editCommandDefinition.commandCreated.add(editCommandCreated)
        _handlers.append(editCommandCreated)

        _customFeatureDefinition = adsk.fusion.CustomFeatureDefinition.create(COMMAND_ID, strings.PRONGS_ON_FACE_AT_POINTS, RESOURCES_FOLDER)
        _customFeatureDefinition.editCommandId = EDIT_COMMAND_ID

        computeCustomFeature = ComputeCustomFeature()
        _customFeatureDefinition.customFeatureCompute.add(computeCustomFeature)
        _handlers.append(computeCustomFeature)
    except:
        showMessage(f'Run failed:\n{traceback.format_exc()}', True)


def stop(panel: adsk.core.ToolbarPanel):
    """Clean up the prongs command when the add-in is unloaded.
    
    Removes command definitions and UI elements.
    
    Args:
        panel: The toolbar panel to remove the command from
    """
    try:
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


class CreateCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Handles the creation of the command dialog for creating new prongs at points.
    
    Sets up all necessary input controls, including selections for face and points, 
    value inputs for size and height. Connects event handlers for validation, 
    preview, and execution.
    """
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _faceSelectionInput, _pointSelectionInput, _sizeValueInput, _heightValueInput
            
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs
            defaultLengthUnits = _app.activeProduct.unitsManager.defaultLengthUnits

            _pointSelectionInput = inputs.addSelectionInput(selectPointsInputDef.id, selectPointsInputDef.name, selectPointsInputDef.tooltip)
            _pointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchPoints)
            _pointSelectionInput.tooltip = selectPointsInputDef.tooltip
            _pointSelectionInput.setSelectionLimits(1)

            _faceSelectionInput = inputs.addSelectionInput(selectFaceInputDef.id, selectFaceInputDef.name, selectFaceInputDef.tooltip)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.ConstructionPlanes)
            _faceSelectionInput.tooltip = selectFaceInputDef.tooltip
            _faceSelectionInput.setSelectionLimits(1, 1)

            inputs.addSeparatorCommandInput('separatorAfterPoints')

            size = adsk.core.ValueInput.createByReal(0.04)
            _sizeValueInput = inputs.addValueInput(sizeInputDef.id, sizeInputDef.name, defaultLengthUnits, size)
            _sizeValueInput.tooltip = sizeInputDef.tooltip

            height = adsk.core.ValueInput.createByReal(0.04)
            _heightValueInput = inputs.addValueInput(heightInputDef.id, heightInputDef.name, defaultLengthUnits, height)
            _heightValueInput.tooltip = heightInputDef.tooltip

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


class EditCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Handles the creation of the command dialog for editing existing prongs custom feature.
    
    Retrieves the selected custom feature, populates inputs with existing parameter values and dependencies,
    and connects event handlers for editing operations, including activation, validation, preview, and execution.
    """
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _editedCustomFeature, _faceSelectionInput, _pointSelectionInput, _sizeValueInput, _heightValueInput
            
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs
            defaultLengthUnits = _app.activeProduct.unitsManager.defaultLengthUnits

            _editedCustomFeature = _ui.activeSelections.item(0).entity
            if _editedCustomFeature is None:
                return

            _pointSelectionInput = inputs.addSelectionInput(selectPointsInputDef.id, selectPointsInputDef.name, selectPointsInputDef.tooltip)
            _pointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchPoints)
            _pointSelectionInput.tooltip = selectPointsInputDef.tooltip
            _pointSelectionInput.setSelectionLimits(1)

            _faceSelectionInput = inputs.addSelectionInput(selectFaceInputDef.id, selectFaceInputDef.name, selectFaceInputDef.tooltip)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.ConstructionPlanes)
            _faceSelectionInput.tooltip = selectFaceInputDef.tooltip
            _faceSelectionInput.setSelectionLimits(1, 1)

            inputs.addSeparatorCommandInput('separatorAfterPoints')

            parameters = _editedCustomFeature.parameters

            size = adsk.core.ValueInput.createByString(parameters.itemById(sizeInputDef.id).expression)
            _sizeValueInput = inputs.addValueInput(sizeInputDef.id, sizeInputDef.name, defaultLengthUnits, size)
            _sizeValueInput.tooltip = sizeInputDef.tooltip

            heightValue = adsk.core.ValueInput.createByString(parameters.itemById(heightInputDef.id).expression)
            _heightValueInput = inputs.addValueInput(heightInputDef.id, heightInputDef.name, defaultLengthUnits, heightValue)
            _heightValueInput.tooltip = heightInputDef.tooltip

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


class PreSelectHandler(adsk.core.SelectionEventHandler):
    """Controls what the user can select when the command is running.
    
    Checks to make sure the points are on a planar face and the
    body the points are on is not an external reference.
    """
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
            
            if type == adsk.fusion.ConstructionPlane.classType():
                if eventArgs.selection.entity is None:
                    eventArgs.isSelectable = False
                    return

            if type == adsk.fusion.SketchPoint.classType():
                preSelectPoint: adsk.fusion.SketchPoint = eventArgs.selection.entity

                
                if preSelectPoint.assemblyContext:
                    occurrence = preSelectPoint.assemblyContext
                    if occurrence.isReferencedComponent:
                        eventArgs.isSelectable = False
                        return
                                
        except:
            showMessage(f'PreSelectHandler: {traceback.format_exc()}\n', True)


class ValidateInputsHandler(adsk.core.ValidateInputsEventHandler):
    """Event handler for the validateInputs event."""
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

            
            if not _faceSelectionInput.selection(0).isValid:
                eventArgs.areInputsValid = False
                return

            for i in range(_pointSelectionInput.selectionCount):
                if not _pointSelectionInput.selection(i).isValid:
                    eventArgs.areInputsValid = False
                    return

            
            if not all([_sizeValueInput.isValidExpression, _heightValueInput.isValidExpression]):
                eventArgs.areInputsValid = False
                return

            
            if _sizeValueInput.value < 0.01:
                eventArgs.areInputsValid = False
                return
            
            if _heightValueInput.value < 0.01:
                eventArgs.areInputsValid = False
                return
            
        except:
            showMessage(f'ValidateInputsHandler: {traceback.format_exc()}\n', True)

class ExecutePreviewHandler(adsk.core.CommandEventHandler):
    """Event handler for the executePreview event."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            if _faceSelectionInput.selectionCount < 1 or _pointSelectionInput.selectionCount < 1:
                return

            
            faceEntity = _faceSelectionInput.selection(0).entity
            if faceEntity is None:
                return

            
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

            
            if faceEntity.objectType == adsk.fusion.ConstructionPlane.classType():
                component = faceEntity.component
            else:
                parametricBody = faceEntity.body
                component = parametricBody.parentComponent

            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()
            for i in range(len(prongs)):
                body = component.bRepBodies.add(prongs[i], baseFeature)
                setProngAttributes(body)
            baseFeature.finishEdit()

        except:
            showMessage(f'ExecutePreviewHandler: {traceback.format_exc()}\n', True)

class CreateExecuteHandler(adsk.core.CommandEventHandler):
    """Event handler for the execute event of the create command."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.CommandEventArgs.cast(args)

            
            faceEntity = _faceSelectionInput.selection(0).entity
            if faceEntity.objectType == adsk.fusion.ConstructionPlane.classType():
                component = faceEntity.component
            else:
                parametricBody = faceEntity.body
                component = parametricBody.parentComponent

            
            pointEntities: list[adsk.fusion.SketchPoint] = []
            for i in range(_pointSelectionInput.selectionCount):
                pointEntities.append(_pointSelectionInput.selection(i).entity)

            
            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()
            for i in range(len(pointEntities)):
                prong = createBody(faceEntity, pointEntities[i].worldGeometry, _sizeValueInput.value, _heightValueInput.value)
                if prong is None:
                    eventArgs.executeFailed = True
                    return
                body = component.bRepBodies.add(prong, baseFeature)
                setProngAttributes(body)
            baseFeature.finishEdit()

            design: adsk.fusion.Design = _app.activeProduct
            defaultLengthUnits = design.unitsManager.defaultLengthUnits
            
            customFeatureInput = component.features.customFeatures.createInput(_customFeatureDefinition)

            
            customFeatureInput.addDependency('face', faceEntity)
            for i in range(len(pointEntities)):
                customFeatureInput.addDependency(f'point{i}', pointEntities[i])

            
            sizeInput = adsk.core.ValueInput.createByString(_sizeValueInput.expression)
            customFeatureInput.addCustomParameter(sizeInputDef.id, sizeInputDef.name, sizeInput,
                                              defaultLengthUnits, True)
            
            depthInput = adsk.core.ValueInput.createByString(_heightValueInput.expression)             
            customFeatureInput.addCustomParameter(heightInputDef.id, heightInputDef.name, depthInput,
                                              defaultLengthUnits, True) 

            customFeatureInput.setStartAndEndFeatures(baseFeature, baseFeature)
            
            component.features.customFeatures.add(customFeatureInput)

        except:
            eventArgs.executeFailed = True
            showMessage(f'CreateExecuteHandler: {traceback.format_exc()}\n', True)


class EditActivateHandler(adsk.core.CommandEventHandler):
    """Event handler for the activation of the edit command for a custom feature.
    
    This handler rolls back the timeline to the state before the feature, sets up transaction markers 
    to preserve changes, and pre-selects the original face and point dependencies for editing.
    """
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature, _faceSelectionInput, _pointSelectionInput
            
            eventArgs = adsk.core.CommandEventArgs.cast(args)

            if _isRolledForEdit: return
            
            
            design: adsk.fusion.Design = _app.activeProduct
            timeline = design.timeline
            markerPosition = timeline.markerPosition
            _restoreTimelineObject = timeline.item(markerPosition - 1)

            
            _editedCustomFeature.timelineObject.rollTo(True)
            _isRolledForEdit = True

            command = eventArgs.command
            
            command.beginStep()

            
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
            
            faceEntity = _editedCustomFeature.dependencies.itemById('face').entity
            _faceSelectionInput.addSelection(faceEntity)

        except:
            showMessage(f'EditActivateHandler: {traceback.format_exc()}\n', True)
            pass


class EditDestroyHandler(adsk.core.CommandEventHandler):
    """Event handler for the destroy event of the edit command."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.CommandEventArgs.cast(args)
            if eventArgs.terminationReason != adsk.core.CommandTerminationReason.CompletedTerminationReason:
                rollBack()
        except:
            showMessage(f'EditDeactivateHandler: {traceback.format_exc()}\n', True)


class EditExecuteHandler(adsk.core.CommandEventHandler):
    """Event handler for the execute event of the edit command."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        global _editedCustomFeature, _isRolledForEdit, _restoreTimelineObject
        
        try:
            
            eventArgs = adsk.core.CommandEventArgs.cast(args)    

            faceEntity = _faceSelectionInput.selection(0).entity
            pointCount = _pointSelectionInput.selectionCount
            pointEntities = []
            for i in range(pointCount):
                pointEntities.append(_pointSelectionInput.selection(i).entity)

            _editedCustomFeature.dependencies.deleteAll()
            _editedCustomFeature.dependencies.add('face', faceEntity)

            for i in range(pointCount):
                _editedCustomFeature.dependencies.add(f'point{i}', pointEntities[i])

            _editedCustomFeature.parameters.itemById(sizeInputDef.id).expression = _sizeValueInput.expression
            _editedCustomFeature.parameters.itemById(heightInputDef.id).expression = _heightValueInput.expression

            updateFeature(_editedCustomFeature)

        except:
            showMessage(f'EditExecuteHandler: {traceback.format_exc()}\n', True)
        
        finally: rollBack()


class ComputeCustomFeature(adsk.fusion.CustomFeatureEventHandler):
    """Event handler for the recomputation of the custom feature.
    
    This handler updates the prong bodies within the base feature to reflect new values or geometry,
    ensuring the custom feature remains parametric and up-to-date.
    """
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs: adsk.fusion.CustomFeatureEventArgs = args
            customFeature = eventArgs.customFeature
            updateFeature(customFeature)

        except:
            showMessage(f'ComputeCustomFeature: {traceback.format_exc()}\n', True)


def createBody(face: adsk.fusion.BRepFace, point: adsk.core.Point3D, size: float, height: float, flat: bool = True) -> adsk.fusion.BRepBody | None:
    """Create a prong body based on the face, point, size, and height.

    Args:
        face: The face where the prong will be placed.
        point: The point on the face where the prong will be created.
        size: The size of the prong.
        height: The height of the prong.
        flat: Whether the prong should be flat (default True).

    Returns:
        The created prong body or None if creation failed.
    """
    try:
        if face is None or point is None: return None

        
        prong = createProng(size, height)
        if prong is None:
            return None
        
        pointOnFace, lengthDirection, widthDirection, normal = getDataFromPointAndFace(face, point)
        if pointOnFace is None:
            return None
        
        placeBody(prong, pointOnFace, lengthDirection, widthDirection, normal)

        return prong
    
    except:
        showMessage(f'CreateBodies: {traceback.format_exc()}\n', True)
        return None
    
def updateBody(body: adsk.fusion.BRepBody, face: adsk.fusion.BRepFace, point: adsk.core.Point3D, size: float, height: float) -> adsk.fusion.BRepBody | None:
    """Update an existing prong body with new parameters.

    Args:
        body: The existing prong body to update.
        face: The face where the prong is placed.
        point: The point on the face where the prong should be.
        size: The new size of the prong.
        height: The new height of the prong.

    Returns:
        The updated prong body or None if update failed.
    """
    try:
        if face is None or point is None: return None

        
        tempBody = updateProngAndNormalize(body, size, height)
        if tempBody is None:
            return None
        
        pointOnFace, lengthDirection, widthDirection, normal = getDataFromPointAndFace(face, point)
        if pointOnFace is None:
            return None
        
        placeBody(tempBody, pointOnFace, lengthDirection, widthDirection, normal)

        return tempBody
    
    except:
        showMessage(f'updateBody: {traceback.format_exc()}\n', True)


def updateFeature(customFeature: adsk.fusion.CustomFeature) -> bool:
    """Update the bodies of an existing custom prongs feature.

    Args:
        customFeature: The custom feature to update.

    Returns:
        True if the update was successful, False otherwise.
    """
    try:
        
        baseFeature: adsk.fusion.BaseFeature = None

        for feature in customFeature.features:
            if feature.objectType == adsk.fusion.BaseFeature.classType():
                baseFeature = feature
        if baseFeature is None: return False

        faceEntity = customFeature.dependencies.itemById('face').entity
        if faceEntity is None: return False

        
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

        size = customFeature.parameters.itemById(sizeInputDef.id).value
        height = customFeature.parameters.itemById(heightInputDef.id).value

        if faceEntity.objectType == adsk.fusion.ConstructionPlane.classType():
            component = faceEntity.component
        else:
            component = faceEntity.body.parentComponent

        baseFeature.startEdit()
        
        
        for i in range(len(points)):
            point = points[i]

            if i < baseFeature.bodies.count:
                currentBody = baseFeature.bodies.item(i)
                newBody = updateBody(currentBody, faceEntity, point.worldGeometry, size, height)
                if newBody is not None:
                    baseFeature.updateBody(currentBody, newBody)
                else:
                    baseFeature.finishEdit()
                    return False
            else:
                prong = createBody(faceEntity, point.worldGeometry, size, height)
                if prong is None:
                    baseFeature.finishEdit()
                    return False
                body = component.bRepBodies.add(prong, baseFeature)
                if not _isRolledForEdit:
                    setProngAttributes(body, size, height)
        
        while baseFeature.bodies.count > len(points):
            baseFeature.bodies.item(baseFeature.bodies.count - 1).deleteMe()

        baseFeature.finishEdit()

        return True
    
    except:
        showMessage(f'UpdateBody: {traceback.format_exc()}\n', True)
        return False
    

def rollBack():
    """Roll back the timeline to the state before editing."""
    global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature
    
    if _isRolledForEdit:
        _editedCustomFeature.timelineObject.rollTo(False)
        updateProngFeature(_editedCustomFeature)
        _restoreTimelineObject.rollTo(False)
        _isRolledForEdit = False

    _editedCustomFeature = None