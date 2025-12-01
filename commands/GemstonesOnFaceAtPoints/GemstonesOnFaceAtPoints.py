import os
import adsk.core, adsk.fusion, traceback

from ... import strings
from ...constants import minimumGemstoneSize
from ...helpers.showMessage import showMessage
from ...helpers.Gemstones import createGemstone, updateGemstone, setGemstoneAttributes, updateGemstoneFeature, diamondMaterial
from ...helpers.Utilities import getPointGeometry

_app: adsk.core.Application = None
_ui: adsk.core.UserInterface = None
_panel: adsk.core.ToolbarPanel = None

_customFeatureDefinition: adsk.fusion.CustomFeature = None

_faceSelectionInput: adsk.core.SelectionCommandInput = None
_pointSelectionInput: adsk.core.SelectionCommandInput = None
_sizeValueInput: adsk.core.ValueCommandInput = None
_flipValueInput: adsk.core.BoolValueCommandInput = None
_absoluteDepthOffsetValueInput: adsk.core.ValueCommandInput = None
_relativeDepthOffsetValueInput: adsk.core.ValueCommandInput = None

_editedCustomFeature: adsk.fusion.CustomFeature = None
_restoreTimelineObject: adsk.fusion.TimelineObject = None
_isRolledForEdit: bool = False

_handlers = []

COMMAND_ID = strings.PREFIX + strings.GEMSTONES_ON_FACE_AT_POINTS
CREATE_COMMAND_ID = COMMAND_ID + 'Create'
EDIT_COMMAND_ID = COMMAND_ID + 'Edit'

createCommandInputDef = strings.InputDef(CREATE_COMMAND_ID, 'Gemstones at Points', 'Creates gemstones at selected points on a face.')
editCommandInputDef = strings.InputDef(EDIT_COMMAND_ID, 'Edit Gemstones', 'Edits the parameters of existing gemstones.')

selectFaceInputDef = strings.InputDef(
    'selectFace',
    'Select Face',
    'Select the face where the gemstone will be placed.'
    )

selectPointsInputDef = strings.InputDef(
    'selectPoints',
    'Select Points',
    'Select points on the face for the gemstone centers.'
    )

sizeInputDef = strings.InputDef(
    'size', 
    'Size', 
    "Gemstone diameter.\nDetermines the overall size of the gemstone."
    )

flipInputDef = strings.InputDef(
    'flip', 
    'Flip', 
    "Flip gemstone orientation.\nReverses the direction the gemstone faces relative to the surface."
    )

absoluteDepthOffsetInputDef = strings.InputDef(
    'absoluteDepthOffset', 
    'Absolute Depth Offset', 
    "Additional depth offset in absolute units.\nAdds a fixed depth to the gemstone beyond the relative offset."
    )

relativeDepthOffsetInputDef = strings.InputDef(
    'relativeDepthOffset', 
    'Relative Depth Offset', 
    "Depth offset as a fraction of gemstone size.\nControls how deep the gemstone sits (0.1 = 10% of diameter)."
    )

RESOURCES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

def run(context):
    """Initialize the gemstones command by setting up command definitions and UI elements."""
    try:
        global _app, _ui, _panel
        _app = adsk.core.Application.get()
        _ui  = _app.userInterface

        createCommandDefinition = _ui.commandDefinitions.addButtonDefinition(createCommandInputDef.id, 
                                                                createCommandInputDef.name, 
                                                                createCommandInputDef.tooltip, 
                                                                RESOURCES_FOLDER)        

        solidWorkspace = _ui.workspaces.itemById('FusionSolidEnvironment')
        _panel = solidWorkspace.toolbarPanels.itemById('SolidCreatePanel')
        control = _panel.controls.addCommand(createCommandDefinition, '', False)     
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

        global _customFeatureDefinition
        _customFeatureDefinition = adsk.fusion.CustomFeatureDefinition.create(COMMAND_ID, strings.GEMSTONES_ON_FACE_AT_POINTS, RESOURCES_FOLDER)
        _customFeatureDefinition.editCommandId = EDIT_COMMAND_ID

        computeCustomFeature = ComputeCustomFeature()
        _customFeatureDefinition.customFeatureCompute.add(computeCustomFeature)
        _handlers.append(computeCustomFeature)
    except:
        showMessage(f'Run failed:\n{traceback.format_exc()}', True)


def stop(context):
    """Clean up the gemstones command by removing UI elements and handlers."""
    try:
        global _panel

        control = _panel.controls.itemById(CREATE_COMMAND_ID)
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
    """Event handler for creating the command dialog for new gemstones.
    
    This handler sets up all necessary input controls including selections for face and points,
    value inputs for size, flip, and depth offset, and connects event handlers for validation,
    preview, and execution.
    """
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs
            defaultLengthUnits = _app.activeProduct.unitsManager.defaultLengthUnits

            global _faceSelectionInput, _pointSelectionInput, _sizeValueInput, _flipValueInput, _absoluteDepthOffsetValueInput, _relativeDepthOffsetValueInput

            _faceSelectionInput = inputs.addSelectionInput(selectFaceInputDef.id, selectFaceInputDef.name, selectFaceInputDef.tooltip)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _faceSelectionInput.tooltip = selectFaceInputDef.tooltip
            _faceSelectionInput.setSelectionLimits(1, 1)

            _pointSelectionInput = inputs.addSelectionInput(selectPointsInputDef.id, selectPointsInputDef.name, selectPointsInputDef.tooltip)
            _pointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchPoints)
            _pointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Vertices)
            _pointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.ConstructionPoints)
            _pointSelectionInput.tooltip = selectPointsInputDef.tooltip
            _pointSelectionInput.setSelectionLimits(1)  

            inputs.addSeparatorCommandInput('separatorAfterPoints')

            size = adsk.core.ValueInput.createByReal(0.15)
            _sizeValueInput = inputs.addValueInput(sizeInputDef.id, sizeInputDef.name, defaultLengthUnits, size)
            _sizeValueInput.tooltip = sizeInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterSize')

            
            flip = False
            _flipValueInput = inputs.addBoolValueInput(flipInputDef.id, flipInputDef.name, True, '', flip)
            _flipValueInput.tooltip = flipInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterFlip')

            
            absoluteDepthOffset = adsk.core.ValueInput.createByReal(0.0)
            _absoluteDepthOffsetValueInput = inputs.addValueInput(absoluteDepthOffsetInputDef.id, absoluteDepthOffsetInputDef.name, defaultLengthUnits, absoluteDepthOffset)
            _absoluteDepthOffsetValueInput.tooltip = absoluteDepthOffsetInputDef.tooltip

            
            relativeDepthOffset = adsk.core.ValueInput.createByReal(0.0)
            _relativeDepthOffsetValueInput = inputs.addValueInput(relativeDepthOffsetInputDef.id, relativeDepthOffsetInputDef.name, '', relativeDepthOffset)
            _relativeDepthOffsetValueInput.tooltip = relativeDepthOffsetInputDef.tooltip

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
    """Event handler for creating the command dialog for editing existing gemstones.
    
    This handler retrieves the selected custom feature, populates inputs with existing parameter 
    values and dependencies, and connects event handlers for editing operations including 
    activation, validation, preview, and execution.
    """
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs
            defaultLengthUnits = _app.activeProduct.unitsManager.defaultLengthUnits

            global _editedCustomFeature, _faceSelectionInput, _pointSelectionInput
            _editedCustomFeature = _ui.activeSelections.item(0).entity
            if _editedCustomFeature is None:
                return

            global _sizeValueInput, _flipValueInput, _absoluteDepthOffsetValueInput, _relativeDepthOffsetValueInput

            _faceSelectionInput = inputs.addSelectionInput(selectFaceInputDef.id, selectFaceInputDef.name, selectFaceInputDef.tooltip)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _faceSelectionInput.tooltip = selectFaceInputDef.tooltip
            _faceSelectionInput.setSelectionLimits(1, 1)

            _pointSelectionInput = inputs.addSelectionInput(selectPointsInputDef.id, selectPointsInputDef.name, selectPointsInputDef.tooltip)
            _pointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchPoints)
            _pointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Vertices)
            _pointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.ConstructionPoints)
            _pointSelectionInput.tooltip = selectPointsInputDef.tooltip
            _pointSelectionInput.setSelectionLimits(1)  

            inputs.addSeparatorCommandInput('separatorAfterPoints')

            params = _editedCustomFeature.parameters

            try:
                sizeParam = params.itemById(sizeInputDef.id)
                size = adsk.core.ValueInput.createByString(sizeParam.expression)
            except:
                size = adsk.core.ValueInput.createByReal(0.15)
            _sizeValueInput = inputs.addValueInput(sizeInputDef.id, sizeInputDef.name, defaultLengthUnits, size)
            _sizeValueInput.tooltip = sizeInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterSize')

            try:
                flipParam = params.itemById(flipInputDef.id)
                flip = flipParam.expression.lower() == 'true'
            except:
                flip = False
            _flipValueInput = inputs.addBoolValueInput(flipInputDef.id, flipInputDef.name, True, '', flip)
            _flipValueInput.tooltip = flipInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterFlip')

            try:
                absoluteDepthOffsetParam = params.itemById(absoluteDepthOffsetInputDef.id)
                absoluteDepthOffset = adsk.core.ValueInput.createByString(absoluteDepthOffsetParam.expression)
            except:
                absoluteDepthOffset = adsk.core.ValueInput.createByReal(0.0)
            _absoluteDepthOffsetValueInput = inputs.addValueInput(absoluteDepthOffsetInputDef.id, absoluteDepthOffsetInputDef.name, defaultLengthUnits, absoluteDepthOffset)
            _absoluteDepthOffsetValueInput.tooltip = absoluteDepthOffsetInputDef.tooltip

            try:
                relativeDepthOffsetParam = params.itemById(relativeDepthOffsetInputDef.id)
                relativeDepthOffset = adsk.core.ValueInput.createByString(relativeDepthOffsetParam.expression)
            except:
                relativeDepthOffset = adsk.core.ValueInput.createByReal(0.0)
            _relativeDepthOffsetValueInput = inputs.addValueInput(relativeDepthOffsetInputDef.id, relativeDepthOffsetInputDef.name, '', relativeDepthOffset)
            _relativeDepthOffsetValueInput.tooltip = relativeDepthOffsetInputDef.tooltip

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
    """Event handler for controlling user selection during command execution.
    
    This handler checks to ensure the point is on a planar face and the body 
    the point is on is not an external reference.
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

            if type == adsk.fusion.SketchPoint.classType() or type == adsk.fusion.BRepVertex.classType() or type == adsk.fusion.ConstructionPoint.classType():
                preSelectEntity = eventArgs.selection.entity

                
                if preSelectEntity.assemblyContext:
                    occ = preSelectEntity.assemblyContext
                    if occ.isReferencedComponent:
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

            if _faceSelectionInput.selectionCount != 1 or _pointSelectionInput.selectionCount < 1:
                eventArgs.areInputsValid = False
                return

            if not all( [_sizeValueInput.isValidExpression, _flipValueInput.isValid, _absoluteDepthOffsetValueInput.isValidExpression, _relativeDepthOffsetValueInput.isValidExpression] ):
                eventArgs.areInputsValid = False
                return

            size = _sizeValueInput.value
            if size < minimumGemstoneSize:
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
            face: adsk.fusion.BRepFace = _faceSelectionInput.selection(0).entity
            
            size = _sizeValueInput.value
            flip = _flipValueInput.value
            absoluteDepthOffset = _absoluteDepthOffsetValueInput.value
            relativeDepthOffset = _relativeDepthOffsetValueInput.value

            component = face.body.parentComponent
            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()

            for i in range(_pointSelectionInput.selectionCount):
                pointEntity = _pointSelectionInput.selection(i).entity
                pointGeometry = getPointGeometry(pointEntity)
                if pointGeometry is None: continue
                gemstone = createGemstone(face, pointGeometry, size, flip, absoluteDepthOffset, relativeDepthOffset)
                if gemstone is not None:
                    body = component.bRepBodies.add(gemstone, baseFeature)
                    setGemstoneAttributes(body, flip, absoluteDepthOffset, relativeDepthOffset)
                    body.material = diamondMaterial

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

            face: adsk.fusion.BRepFace = _faceSelectionInput.selection(0).entity
            comp = face.body.parentComponent
            pointEntities = []
            for i in range(_pointSelectionInput.selectionCount):
                pointEntities.append(_pointSelectionInput.selection(i).entity)

            baseFeat = comp.features.baseFeatures.add()
            baseFeat.startEdit()

            for i in range(len(pointEntities)):
                pointEntity = pointEntities[i]
                pointGeometry = getPointGeometry(pointEntity)
                if pointGeometry is None: continue
                gemstone = createGemstone(face, pointGeometry, _sizeValueInput.value, _flipValueInput.value, _absoluteDepthOffsetValueInput.value, _relativeDepthOffsetValueInput.value)
                if gemstone is None:
                    eventArgs.executeFailed = True
                    return
                
                body = comp.bRepBodies.add(gemstone, baseFeat)
                setGemstoneAttributes(body, _flipValueInput.value, _absoluteDepthOffsetValueInput.value, _relativeDepthOffsetValueInput.value)
                body.material = diamondMaterial

            baseFeat.finishEdit()

            
            design: adsk.fusion.Design = _app.activeProduct
            defLengthUnits = design.unitsManager.defaultLengthUnits
            customFeatureInput = comp.features.customFeatures.createInput(_customFeatureDefinition)

            sizeInput = adsk.core.ValueInput.createByString(_sizeValueInput.expression)
            customFeatureInput.addCustomParameter(sizeInputDef.id, sizeInputDef.name, sizeInput,
                                              defLengthUnits, True)
                         
            flipInput = adsk.core.ValueInput.createByString(str(_flipValueInput.value).lower())
            customFeatureInput.addCustomParameter(flipInputDef.id, flipInputDef.name, flipInput, '', True)

            absoluteDepthOffsetInput = adsk.core.ValueInput.createByString(_absoluteDepthOffsetValueInput.expression)
            customFeatureInput.addCustomParameter(absoluteDepthOffsetInputDef.id, absoluteDepthOffsetInputDef.name, absoluteDepthOffsetInput,
                                              defLengthUnits, True)

            relativeDepthOffsetInput = adsk.core.ValueInput.createByString(_relativeDepthOffsetValueInput.expression)
            customFeatureInput.addCustomParameter(relativeDepthOffsetInputDef.id, relativeDepthOffsetInputDef.name, relativeDepthOffsetInput,
                                              '', True)

            customFeatureInput.addDependency('face', face)
            
            for i in range(len(pointEntities)):
                customFeatureInput.addDependency(f'point{i}', pointEntities[i])

            customFeatureInput.setStartAndEndFeatures(baseFeat, baseFeat)
            comp.features.customFeatures.add(customFeatureInput)
        except:
            eventArgs.executeFailed = True
            showMessage(f'CreateExecuteHandler: {traceback.format_exc()}\n', True)


class EditActivateHandler(adsk.core.CommandEventHandler):
    """Event handler for the activate event."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature

            if _isRolledForEdit: return

            eventArgs = adsk.core.CommandEventArgs.cast(args)
            
            design: adsk.fusion.Design = _app.activeProduct
            timeline = design.timeline
            markerPosition = timeline.markerPosition
            _restoreTimelineObject = timeline.item(markerPosition - 1)
            
            _editedCustomFeature.timelineObject.rollTo(True)
            _isRolledForEdit = True
            
            command = eventArgs.command
            command.beginStep()

            face = _editedCustomFeature.dependencies.itemById('face').entity
            _faceSelectionInput.addSelection(face)
            
            i = 0
            while True:
                try:
                    dependency = _editedCustomFeature.dependencies.itemById(f'point{i}')
                    if dependency is None: break
                    pointEntity = dependency.entity
                    if pointEntity is not None: _pointSelectionInput.addSelection(pointEntity)
                    i += 1
                except:
                    break
                
        except:
            showMessage(f'EditActivateHandler: {traceback.format_exc()}\n', True)


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

        try:
            eventArgs = adsk.core.CommandEventArgs.cast(args)    

            global _editedCustomFeature, _isRolledForEdit

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
            _editedCustomFeature.parameters.itemById(flipInputDef.id).expression = str(_flipValueInput.value).lower()
            _editedCustomFeature.parameters.itemById(absoluteDepthOffsetInputDef.id).expression = _absoluteDepthOffsetValueInput.expression
            _editedCustomFeature.parameters.itemById(relativeDepthOffsetInputDef.id).expression = _relativeDepthOffsetValueInput.expression

            updateFeature(_editedCustomFeature)

        except:
            showMessage(f'EditExecuteHandler: {traceback.format_exc()}\n', True)

        finally: rollBack()


class ComputeCustomFeature(adsk.fusion.CustomFeatureEventHandler):
    """Event handler for computing the custom feature."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs: adsk.fusion.CustomFeatureEventArgs = args
            custFeature = eventArgs.customFeature
            updateFeature(custFeature)

        except:
            showMessage(f'ComputeCustomFeature: {traceback.format_exc()}\n', True)


def updateFeature(customFeature: adsk.fusion.CustomFeature) -> bool:
    """Update the bodies of an existing custom gemstones feature.

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
                break
        if baseFeature is None: return False

        faceEntity: adsk.fusion.BRepFace = customFeature.dependencies.itemById('face').entity
        if faceEntity is None: return False
        
        points = []
        i = 0
        while True:
            dependency = customFeature.dependencies.itemById(f'point{i}')
            if dependency is None: break
            pointEntity = dependency.entity
            if pointEntity is None: break
            points.append(pointEntity)
            i += 1
        if len(points) == 0: return False

        
        try:
            size = customFeature.parameters.itemById(sizeInputDef.id).value
        except:
            size = 0.15
        
        try:
            flip = customFeature.parameters.itemById(flipInputDef.id).expression.lower() == 'true'
        except:
            flip = False
        
        try:
            absoluteDepthOffset = customFeature.parameters.itemById(absoluteDepthOffsetInputDef.id).value
        except:
            absoluteDepthOffset = 0.0
        
        try:
            relativeDepthOffset = customFeature.parameters.itemById(relativeDepthOffsetInputDef.id).value
        except:
            relativeDepthOffset = 0.0

        component = faceEntity.body.parentComponent

        baseFeature.startEdit()
        
        success = True
        for i in range(len(points)):
            pointEntity = points[i]
            pointGeometry = getPointGeometry(pointEntity)
            if pointGeometry is None: continue

            if i < baseFeature.bodies.count:
                currentBody = baseFeature.bodies.item(i)
                newBody = updateGemstone(currentBody, faceEntity, pointGeometry, size, flip, absoluteDepthOffset, relativeDepthOffset)
                if newBody is not None:
                    baseFeature.updateBody(currentBody, newBody)
                else:
                    success = False
            else:
                gemstone = createGemstone(faceEntity, pointGeometry, size, flip, absoluteDepthOffset, relativeDepthOffset)
                if gemstone is not None:
                    body = component.bRepBodies.add(gemstone, baseFeature)
                    body.material = diamondMaterial
                    if not _isRolledForEdit: setGemstoneAttributes(body, flip, absoluteDepthOffset, relativeDepthOffset)
                else:
                    success = False
        
        while baseFeature.bodies.count > len(points):
            baseFeature.bodies.item(baseFeature.bodies.count - 1).deleteMe()

        baseFeature.finishEdit()
        
        return success
    
    except:
        showMessage(f'updateFeature: {traceback.format_exc()}\n', True)
        return False
    
def rollBack():
    """Roll back the timeline to the state before editing."""
    global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature
    
    if _isRolledForEdit:
        _editedCustomFeature.timelineObject.rollTo(False)
        updateGemstoneFeature(_editedCustomFeature)
        _restoreTimelineObject.rollTo(False)
        _isRolledForEdit = False


    _editedCustomFeature = None