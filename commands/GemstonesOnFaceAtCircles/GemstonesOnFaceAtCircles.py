import os
import adsk.core, adsk.fusion, traceback

from ... import strings
from ...helpers.showMessage import showMessage
from ...helpers.Gemstones import createGemstone, updateGemstone

_app: adsk.core.Application = None
_ui: adsk.core.UserInterface = None
_panel: adsk.core.ToolbarPanel = None

_customFeatureDefinition: adsk.fusion.CustomFeature = None

_faceSelectionInput: adsk.core.SelectionCommandInput = None
_circleSelectionInput: adsk.core.SelectionCommandInput = None
_flipValueInput: adsk.core.BoolValueCommandInput = None
_absoluteDepthOffsetValueInput: adsk.core.ValueCommandInput = None
_relativeDepthOffsetValueInput: adsk.core.ValueCommandInput = None

_editedCustomFeature: adsk.fusion.CustomFeature = None
_restoreTimelineObject: adsk.fusion.TimelineObject = None
_isRolledForEdit: bool = False

_handlers = []

_diamondMaterial: adsk.core.Material = None

COMMAND_ID = strings.PREFIX + strings.GEMSTONES_ON_FACE_AT_CIRCLES
CREATE_COMMAND_ID = COMMAND_ID + 'Create'
EDIT_COMMAND_ID = COMMAND_ID + 'Edit'

createCommandInputDef = strings.InputDef(CREATE_COMMAND_ID, 'Gemstones at Circles', 'Creates gemstones at selected sketch circles on a face. The gemstone size matches the circle diameter.')
editCommandInputDef = strings.InputDef(EDIT_COMMAND_ID, 'Edit Gemstones', 'Edits the parameters of existing gemstones created from circles.')

selectFaceInputDef = strings.InputDef(
    'selectFace',
    'Select Face',
    'Select the face where the gemstones will be placed.'
    )

selectCirclesInputDef = strings.InputDef(
    'selectCircles',
    'Select Circles',
    'Select sketch circles. The gemstone will be centered at each circle center with diameter matching the circle diameter.'
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
        global _app, _ui, _panel, _diamondMaterial
        _app = adsk.core.Application.get()
        _ui  = _app.userInterface

        
        MaterialLib = _app.materialLibraries.itemByName('Fusion Material Library')
        _diamondMaterial = MaterialLib.materials.itemByName('Mirror')

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
        _customFeatureDefinition = adsk.fusion.CustomFeatureDefinition.create(COMMAND_ID, strings.GEMSTONES_ON_FACE_AT_CIRCLES, RESOURCES_FOLDER)
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

            global _faceSelectionInput, _circleSelectionInput, _flipValueInput, _absoluteDepthOffsetValueInput, _relativeDepthOffsetValueInput

            _faceSelectionInput = inputs.addSelectionInput(selectFaceInputDef.id, selectFaceInputDef.name, selectFaceInputDef.tooltip)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _faceSelectionInput.tooltip = selectFaceInputDef.tooltip
            _faceSelectionInput.setSelectionLimits(1, 1)

            _circleSelectionInput = inputs.addSelectionInput(selectCirclesInputDef.id, selectCirclesInputDef.name, selectCirclesInputDef.tooltip)
            _circleSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchCircles)
            _circleSelectionInput.tooltip = selectCirclesInputDef.tooltip
            _circleSelectionInput.setSelectionLimits(1)

            
            flip = False
            _flipValueInput = inputs.addBoolValueInput(flipInputDef.id, flipInputDef.name, True, '', flip)
            _flipValueInput.tooltip = flipInputDef.tooltip

            
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

            global _editedCustomFeature, _faceSelectionInput, _circleSelectionInput
            _editedCustomFeature = _ui.activeSelections.item(0).entity
            if _editedCustomFeature is None:
                return

            global _flipValueInput, _absoluteDepthOffsetValueInput, _relativeDepthOffsetValueInput

            _faceSelectionInput = inputs.addSelectionInput(selectFaceInputDef.id, selectFaceInputDef.name, selectFaceInputDef.tooltip)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _faceSelectionInput.tooltip = selectFaceInputDef.tooltip
            _faceSelectionInput.setSelectionLimits(1, 1)

            _circleSelectionInput = inputs.addSelectionInput(selectCirclesInputDef.id, selectCirclesInputDef.name, selectCirclesInputDef.tooltip)
            _circleSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchCircles)
            _circleSelectionInput.tooltip = selectCirclesInputDef.tooltip
            _circleSelectionInput.setSelectionLimits(1)  

            params = _editedCustomFeature.parameters

            try:
                flipParam = params.itemById(flipInputDef.id)
                flip = flipParam.expression.lower() == 'true'
            except:
                flip = False
            _flipValueInput = inputs.addBoolValueInput(flipInputDef.id, flipInputDef.name, True, '', flip)
            _flipValueInput.tooltip = flipInputDef.tooltip

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
    
    This handler checks to ensure the circle is on a planar face and the body 
    the circle belongs to is not an external reference.
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

            if type == adsk.fusion.SketchCircle.classType():
                preSelectCircle: adsk.fusion.SketchCircle = eventArgs.selection.entity

                
                if preSelectCircle.assemblyContext:
                    occ = preSelectCircle.assemblyContext
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

            if _faceSelectionInput.selectionCount != 1 or _circleSelectionInput.selectionCount < 1:
                eventArgs.areInputsValid = False
                return

            # Check minimum circle diameter (0.5 mm)
            for i in range(_circleSelectionInput.selectionCount):
                sketchCircle: adsk.fusion.SketchCircle = _circleSelectionInput.selection(i).entity
                diameter = sketchCircle.radius * 2
                if diameter < 0.05:
                    eventArgs.areInputsValid = False
                    return

            if not all( [_flipValueInput.isValid, _absoluteDepthOffsetValueInput.isValidExpression, _relativeDepthOffsetValueInput.isValidExpression] ):
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
            
            flip = _flipValueInput.value
            absoluteDepthOffset = _absoluteDepthOffsetValueInput.value
            relativeDepthOffset = _relativeDepthOffsetValueInput.value

            component = face.body.parentComponent
            baseFeat = component.features.baseFeatures.add()
            baseFeat.startEdit()

            for i in range(_circleSelectionInput.selectionCount):
                sketchCircle: adsk.fusion.SketchCircle = _circleSelectionInput.selection(i).entity
                size = sketchCircle.radius * 2
                gemstone = createGemstone(face, sketchCircle.worldGeometry.center, size, RESOURCES_FOLDER, flip, absoluteDepthOffset, relativeDepthOffset)
                if gemstone is not None:
                    body = component.bRepBodies.add(gemstone, baseFeat)
                    handleNewBody(body)
                    body.material = _diamondMaterial

            baseFeat.finishEdit()
            

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
            circleEntities: list[adsk.fusion.SketchCircle] = []
            for i in range(_circleSelectionInput.selectionCount):
                circleEntities.append(_circleSelectionInput.selection(i).entity)

            baseFeat = comp.features.baseFeatures.add()
            baseFeat.startEdit()

            for i in range(len(circleEntities)):
                sketchCircle = circleEntities[i]
                size = sketchCircle.radius * 2
                gemstone = createGemstone(face, sketchCircle.worldGeometry.center, size, RESOURCES_FOLDER, _flipValueInput.value, _absoluteDepthOffsetValueInput.value, _relativeDepthOffsetValueInput.value)
                if gemstone is None:
                    eventArgs.executeFailed = True
                    return
                
                body = comp.bRepBodies.add(gemstone, baseFeat)
                handleNewBody(body)
                body.material = _diamondMaterial

            baseFeat.finishEdit()

            
            design: adsk.fusion.Design = _app.activeProduct
            defLengthUnits = design.unitsManager.defaultLengthUnits
            customFeatureInput = comp.features.customFeatures.createInput(_customFeatureDefinition)
                         
            flipInput = adsk.core.ValueInput.createByString(str(_flipValueInput.value).lower())
            customFeatureInput.addCustomParameter(flipInputDef.id, flipInputDef.name, flipInput, '', True)

            absoluteDepthOffsetInput = adsk.core.ValueInput.createByString(_absoluteDepthOffsetValueInput.expression)
            customFeatureInput.addCustomParameter(absoluteDepthOffsetInputDef.id, absoluteDepthOffsetInputDef.name, absoluteDepthOffsetInput,
                                              defLengthUnits, True)

            relativeDepthOffsetInput = adsk.core.ValueInput.createByString(_relativeDepthOffsetValueInput.expression)
            customFeatureInput.addCustomParameter(relativeDepthOffsetInputDef.id, relativeDepthOffsetInputDef.name, relativeDepthOffsetInput,
                                              '', True)

            customFeatureInput.addDependency('face', face)
            
            for i in range(len(circleEntities)):
                customFeatureInput.addDependency(f'circle{i}', circleEntities[i])

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
                    dependency = _editedCustomFeature.dependencies.itemById(f'circle{i}')
                    if dependency is None: break
                    sketchCircle = dependency.entity
                    if sketchCircle is not None: _circleSelectionInput.addSelection(sketchCircle)
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
        global _editedCustomFeature, _isRolledForEdit

        try:
            eventArgs = adsk.core.CommandEventArgs.cast(args)    

            faceEntity = _faceSelectionInput.selection(0).entity
            circleCount = _circleSelectionInput.selectionCount
            circleEntities = []
            for i in range(circleCount):
                circleEntities.append(_circleSelectionInput.selection(i).entity)

            _editedCustomFeature.dependencies.deleteAll()
            _editedCustomFeature.dependencies.add('face', faceEntity)

            for i in range(circleCount):
                _editedCustomFeature.dependencies.add(f'circle{i}', circleEntities[i])

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
        if baseFeature is None: return False

        faceEntity: adsk.fusion.BRepFace = customFeature.dependencies.itemById('face').entity
        if faceEntity is None: return False

        
        circles: list[adsk.fusion.SketchCircle] = []
        i = 0
        while True:
            dependency = customFeature.dependencies.itemById(f'circle{i}')
            if dependency is None: break
            sketchCircle = dependency.entity
            if sketchCircle is None: break
            circles.append(sketchCircle)
            i += 1
        if len(circles) == 0: return False

        
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
        for i in range(len(circles)):
            circle = circles[i]
            size = circle.radius * 2

            if i < baseFeature.bodies.count:
                currentBody = baseFeature.bodies.item(i)
                newBody = updateGemstone(currentBody, faceEntity, circle.worldGeometry.center, size, flip, absoluteDepthOffset, relativeDepthOffset)
                if newBody is not None:
                    baseFeature.updateBody(currentBody, newBody)
                else:
                    success = False
            else:
                gemstone = createGemstone(faceEntity, circle.worldGeometry.center, size, RESOURCES_FOLDER, flip, absoluteDepthOffset, relativeDepthOffset)
                if gemstone is not None:
                    body = component.bRepBodies.add(gemstone, baseFeature)
                    body.material = _diamondMaterial
                else:
                    success = False

        
        while baseFeature.bodies.count > len(circles):
            baseFeature.bodies.item(baseFeature.bodies.count - 1).deleteMe()

        baseFeature.finishEdit()
        
        return success
    
    except:
        showMessage(f'updateFeature: {traceback.format_exc()}\n', True)
        return False
    
def handleNewBody(body: adsk.fusion.BRepBody):
    """Handle the creation of a new gemstone body by setting its name and attributes.

    Args:
        body: The new gemstone body to handle.
    """
    body.name = strings.GEMSTONE_ROUND_CUT

    body.attributes.add(strings.PREFIX, strings.ENTITY, strings.GEMSTONE)
    body.attributes.add(strings.PREFIX, strings.GEMSTONE_CUT, strings.GEMSTONE_ROUND_CUT)
    body.attributes.add(strings.PREFIX, strings.GEMSTONE_IS_FLIPPED, str(_flipValueInput.value).lower())
    body.attributes.add(strings.PREFIX, strings.GEMSTONE_ABSOLUTE_DEPTH_OFFSET, str(_absoluteDepthOffsetValueInput.value))
    body.attributes.add(strings.PREFIX, strings.GEMSTONE_RELATIVE_DEPTH_OFFSET, str(_relativeDepthOffsetValueInput.value))

def updateAttributes():
    """Update the attributes of all gemstone bodies in the edited custom feature."""
    for feature in _editedCustomFeature.features:
        if feature.objectType == adsk.fusion.BaseFeature.classType():
            baseFeature: adsk.fusion.BaseFeature = feature
            for body in baseFeature.bodies:
                handleNewBody(body)

def rollBack():
    """Roll back the timeline to the state before editing."""
    global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature
    
    if _isRolledForEdit:
        _editedCustomFeature.timelineObject.rollTo(False)
        updateAttributes()
        _restoreTimelineObject.rollTo(False)
        _isRolledForEdit = False


    _editedCustomFeature = None