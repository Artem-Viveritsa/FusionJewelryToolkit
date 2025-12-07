import os
import adsk.core, adsk.fusion, traceback

from ... import strings
from ...constants import minimumGemstoneSize
from ...helpers.showMessage import showMessage
from ...helpers.Gemstones import createGemstone, updateGemstone, setGemstoneAttributes, updateGemstoneFeature, diamondMaterial
from ...helpers.Curves import calculatePointsAndSizesAlongCurve, getCurve3D

_app: adsk.core.Application = None
_ui: adsk.core.UserInterface = None

_customFeatureDefinition: adsk.fusion.CustomFeature = None

_faceSelectionInput: adsk.core.SelectionCommandInput = None
_curveSelectionInput: adsk.core.SelectionCommandInput = None
_startOffsetValueInput: adsk.core.ValueCommandInput = None
_endOffsetValueInput: adsk.core.ValueCommandInput = None
_startSizeValueInput: adsk.core.ValueCommandInput = None
_endSizeValueInput: adsk.core.ValueCommandInput = None
_sizeStepValueInput: adsk.core.ValueCommandInput = None
_targetGapValueInput: adsk.core.ValueCommandInput = None
_flipValueInput: adsk.core.BoolValueCommandInput = None
_flipDirectionValueInput: adsk.core.BoolValueCommandInput = None
_absoluteDepthOffsetValueInput: adsk.core.ValueCommandInput = None
_relativeDepthOffsetValueInput: adsk.core.ValueCommandInput = None
_nonlinearValueInput: adsk.core.BoolValueCommandInput = None
_nonlinearSizeValueInput: adsk.core.ValueCommandInput = None
_nonlinearPositionValueInput: adsk.core.ValueCommandInput = None

_editedCustomFeature: adsk.fusion.CustomFeature = None
_restoreTimelineObject: adsk.fusion.TimelineObject = None
_isRolledForEdit: bool = False

_handlers = []

COMMAND_ID = strings.PREFIX + strings.GEMSTONES_ON_FACE_AT_CURVE
CREATE_COMMAND_ID = COMMAND_ID + 'Create'
EDIT_COMMAND_ID = COMMAND_ID + 'Edit'

createCommandInputDef = strings.InputDef(CREATE_COMMAND_ID, 'Gemstones at Curves', 'Creates gemstones at selected curves on a face.')
editCommandInputDef = strings.InputDef(EDIT_COMMAND_ID, 'Edit Gemstones', 'Edits the parameters of existing gemstones.')

selectFaceInputDef = strings.InputDef(
    'selectFace',
    'Select Face or Plane',
    'Select the face or construction plane where the gemstones will be placed.'
    )

selectCurveInputDef = strings.InputDef(
    'selectCurve',
    'Curve',
    'Select a sketch curve or edge along which gemstones will be placed.'
    )

startOffsetInputDef = strings.InputDef(
    'startOffset',
    'Start Offset',
    "Offset from the start of the curve.\nDistance from the beginning of the curve to the first gemstone."
    )

endOffsetInputDef = strings.InputDef(
    'endOffset',
    'End Offset',
    "Offset from the end of the curve.\nDistance from the end of the curve to the last gemstone."
    )

startSizeInputDef = strings.InputDef(
    'startSize',
    'Start Size',
    "Gemstone diameter at the start.\nDetermines the size of the first gemstone."
    )

endSizeInputDef = strings.InputDef(
    'endSize',
    'End Size',
    "Gemstone diameter at the end.\nDetermines the size of the last gemstone."
    )

sizeStepInputDef = strings.InputDef(
    'sizeStep',
    'Size Step',
    "Size discretization step.\nGemstone sizes will be rounded to multiples of this value."
    )

targetGapInputDef = strings.InputDef(
    'targetGap',
    'Target Gap',
    "Target gap between gemstones.\nTarget distance between adjacent gemstones along the curve."
    )

flipInputDef = strings.InputDef(
    'flip', 
    'Flip Gemstone', 
    "Flip gemstone orientation.\nReverses the direction the gemstone faces relative to the surface."
    )

flipDirectionInputDef = strings.InputDef(
    'flipDirection',
    'Flip Direction',
    "Flip gemstone placement direction.\nStarts placing gemstones from the opposite end of the curve."
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

nonlinearInputDef = strings.InputDef(
    'nonlinear',
    'Nonlinear',
    "Use nonlinear size interpolation."
    )

nonlinearSizeInputDef = strings.InputDef(
    'nonlinearSize',
    'Nonlinear Size',
    "Size of the gemstone at the nonlinear position."
    )

nonlinearPositionInputDef = strings.InputDef(
    'nonlinearPosition',
    'Nonlinear Position',
    "Position of the nonlinearity peak (0.0 to 1.0)."
    )

RESOURCES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

def run(panel: adsk.core.ToolbarPanel):
    """Initialize the gemstones command by setting up command definitions and UI elements."""
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

        global _customFeatureDefinition
        _customFeatureDefinition = adsk.fusion.CustomFeatureDefinition.create(COMMAND_ID, strings.GEMSTONES_ON_FACE_AT_CURVE, RESOURCES_FOLDER)
        _customFeatureDefinition.editCommandId = EDIT_COMMAND_ID

        computeCustomFeature = ComputeCustomFeature()
        _customFeatureDefinition.customFeatureCompute.add(computeCustomFeature)
        _handlers.append(computeCustomFeature)
    except:
        showMessage(f'Run failed:\n{traceback.format_exc()}', True)


def stop(panel: adsk.core.ToolbarPanel):
    """Clean up the gemstones command by removing UI elements and handlers."""
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

            global _faceSelectionInput, _curveSelectionInput, _startOffsetValueInput, _endOffsetValueInput
            global _startSizeValueInput, _endSizeValueInput, _sizeStepValueInput, _targetGapValueInput
            global _flipValueInput, _flipDirectionValueInput, _absoluteDepthOffsetValueInput, _relativeDepthOffsetValueInput
            global _nonlinearValueInput, _nonlinearSizeValueInput, _nonlinearPositionValueInput

            _curveSelectionInput = inputs.addSelectionInput(selectCurveInputDef.id, selectCurveInputDef.name, selectCurveInputDef.tooltip)
            _curveSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchCurves)
            _curveSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Edges)
            _curveSelectionInput.tooltip = selectCurveInputDef.tooltip
            _curveSelectionInput.setSelectionLimits(1, 1)

            _faceSelectionInput = inputs.addSelectionInput(selectFaceInputDef.id, selectFaceInputDef.name, selectFaceInputDef.tooltip)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.ConstructionPlanes)
            _faceSelectionInput.tooltip = selectFaceInputDef.tooltip
            _faceSelectionInput.setSelectionLimits(1, 1)

            inputs.addSeparatorCommandInput('separatorAfterCurve')

            flipDirection = False
            _flipDirectionValueInput = inputs.addBoolValueInput(flipDirectionInputDef.id, flipDirectionInputDef.name, True, '', flipDirection)
            _flipDirectionValueInput.tooltip = flipDirectionInputDef.tooltip
            
            startOffset = adsk.core.ValueInput.createByReal(0.0)
            _startOffsetValueInput = inputs.addValueInput(startOffsetInputDef.id, startOffsetInputDef.name, defaultLengthUnits, startOffset)
            _startOffsetValueInput.tooltip = startOffsetInputDef.tooltip

            endOffset = adsk.core.ValueInput.createByReal(0.0)
            _endOffsetValueInput = inputs.addValueInput(endOffsetInputDef.id, endOffsetInputDef.name, defaultLengthUnits, endOffset)
            _endOffsetValueInput.tooltip = endOffsetInputDef.tooltip
            
            inputs.addSeparatorCommandInput('separatorAfterEndOffset')

            startSize = adsk.core.ValueInput.createByReal(0.1)
            _startSizeValueInput = inputs.addValueInput(startSizeInputDef.id, startSizeInputDef.name, defaultLengthUnits, startSize)
            _startSizeValueInput.tooltip = startSizeInputDef.tooltip

            endSize = adsk.core.ValueInput.createByReal(0.07)
            _endSizeValueInput = inputs.addValueInput(endSizeInputDef.id, endSizeInputDef.name, defaultLengthUnits, endSize)
            _endSizeValueInput.tooltip = endSizeInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterEndSize')

            nonlinear = False
            _nonlinearValueInput = inputs.addBoolValueInput(nonlinearInputDef.id, nonlinearInputDef.name, True, '', nonlinear)
            _nonlinearValueInput.tooltip = nonlinearInputDef.tooltip

            nonlinearSize = adsk.core.ValueInput.createByReal(0.1)
            _nonlinearSizeValueInput = inputs.addValueInput(nonlinearSizeInputDef.id, nonlinearSizeInputDef.name, defaultLengthUnits, nonlinearSize)
            _nonlinearSizeValueInput.tooltip = nonlinearSizeInputDef.tooltip

            nonlinearPosition = adsk.core.ValueInput.createByReal(0.5)
            _nonlinearPositionValueInput = inputs.addValueInput(nonlinearPositionInputDef.id, nonlinearPositionInputDef.name, '', nonlinearPosition)
            _nonlinearPositionValueInput.tooltip = nonlinearPositionInputDef.tooltip
            
            inputs.addSeparatorCommandInput('separatorAfterNonlinearPosition')

            sizeStep = adsk.core.ValueInput.createByReal(0.005)
            _sizeStepValueInput = inputs.addValueInput(sizeStepInputDef.id, sizeStepInputDef.name, defaultLengthUnits, sizeStep)
            _sizeStepValueInput.tooltip = sizeStepInputDef.tooltip

            targetGap = adsk.core.ValueInput.createByReal(0.01)
            _targetGapValueInput = inputs.addValueInput(targetGapInputDef.id, targetGapInputDef.name, defaultLengthUnits, targetGap)
            _targetGapValueInput.tooltip = targetGapInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterTargetGap')
            
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

            global _editedCustomFeature, _faceSelectionInput, _curveSelectionInput
            _editedCustomFeature = _ui.activeSelections.item(0).entity
            if _editedCustomFeature is None:
                return

            global _startOffsetValueInput, _endOffsetValueInput, _startSizeValueInput, _endSizeValueInput
            global _sizeStepValueInput, _targetGapValueInput, _flipValueInput, _flipDirectionValueInput
            global _absoluteDepthOffsetValueInput, _relativeDepthOffsetValueInput
            global _nonlinearValueInput, _nonlinearSizeValueInput, _nonlinearPositionValueInput

            _curveSelectionInput = inputs.addSelectionInput(selectCurveInputDef.id, selectCurveInputDef.name, selectCurveInputDef.tooltip)
            _curveSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchCurves)
            _curveSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Edges)
            _curveSelectionInput.tooltip = selectCurveInputDef.tooltip
            _curveSelectionInput.setSelectionLimits(1, 1)

            _faceSelectionInput = inputs.addSelectionInput(selectFaceInputDef.id, selectFaceInputDef.name, selectFaceInputDef.tooltip)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.ConstructionPlanes)
            _faceSelectionInput.tooltip = selectFaceInputDef.tooltip
            _faceSelectionInput.setSelectionLimits(1, 1)
            
            inputs.addSeparatorCommandInput('separatorAfterCurve')

            params = _editedCustomFeature.parameters

            try:
                flipDirectionParam = params.itemById(flipDirectionInputDef.id)
                flipDirection = flipDirectionParam.expression.lower() == 'true'
            except:
                flipDirection = False
            _flipDirectionValueInput = inputs.addBoolValueInput(flipDirectionInputDef.id, flipDirectionInputDef.name, True, '', flipDirection)
            _flipDirectionValueInput.tooltip = flipDirectionInputDef.tooltip

            try:
                startOffsetParam = params.itemById(startOffsetInputDef.id)
                startOffset = adsk.core.ValueInput.createByString(startOffsetParam.expression)
            except:
                startOffset = adsk.core.ValueInput.createByReal(0.0)
            _startOffsetValueInput = inputs.addValueInput(startOffsetInputDef.id, startOffsetInputDef.name, defaultLengthUnits, startOffset)
            _startOffsetValueInput.tooltip = startOffsetInputDef.tooltip

            try:
                endOffsetParam = params.itemById(endOffsetInputDef.id)
                endOffset = adsk.core.ValueInput.createByString(endOffsetParam.expression)
            except:
                endOffset = adsk.core.ValueInput.createByReal(0.0)
            _endOffsetValueInput = inputs.addValueInput(endOffsetInputDef.id, endOffsetInputDef.name, defaultLengthUnits, endOffset)
            _endOffsetValueInput.tooltip = endOffsetInputDef.tooltip
            
            inputs.addSeparatorCommandInput('separatorAfterEndOffset')

            try:
                startSizeParam = params.itemById(startSizeInputDef.id)
                startSize = adsk.core.ValueInput.createByString(startSizeParam.expression)
            except:
                startSize = adsk.core.ValueInput.createByReal(0.15)
            _startSizeValueInput = inputs.addValueInput(startSizeInputDef.id, startSizeInputDef.name, defaultLengthUnits, startSize)
            _startSizeValueInput.tooltip = startSizeInputDef.tooltip

            try:
                endSizeParam = params.itemById(endSizeInputDef.id)
                endSize = adsk.core.ValueInput.createByString(endSizeParam.expression)
            except:
                endSize = adsk.core.ValueInput.createByReal(0.15)
            _endSizeValueInput = inputs.addValueInput(endSizeInputDef.id, endSizeInputDef.name, defaultLengthUnits, endSize)
            _endSizeValueInput.tooltip = endSizeInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterEndSize')

            try:
                nonlinearParam = params.itemById(nonlinearInputDef.id)
                nonlinear = nonlinearParam.expression.lower() == 'true'
            except:
                nonlinear = False
            _nonlinearValueInput = inputs.addBoolValueInput(nonlinearInputDef.id, nonlinearInputDef.name, True, '', nonlinear)
            _nonlinearValueInput.tooltip = nonlinearInputDef.tooltip

            try:
                nonlinearSizeParam = params.itemById(nonlinearSizeInputDef.id)
                nonlinearSize = adsk.core.ValueInput.createByString(nonlinearSizeParam.expression)
            except:
                nonlinearSize = adsk.core.ValueInput.createByReal(0.1)
            _nonlinearSizeValueInput = inputs.addValueInput(nonlinearSizeInputDef.id, nonlinearSizeInputDef.name, defaultLengthUnits, nonlinearSize)
            _nonlinearSizeValueInput.tooltip = nonlinearSizeInputDef.tooltip

            try:
                nonlinearPositionParam = params.itemById(nonlinearPositionInputDef.id)
                nonlinearPosition = adsk.core.ValueInput.createByString(nonlinearPositionParam.expression)
            except:
                nonlinearPosition = adsk.core.ValueInput.createByReal(0.5)
            _nonlinearPositionValueInput = inputs.addValueInput(nonlinearPositionInputDef.id, nonlinearPositionInputDef.name, '', nonlinearPosition)
            _nonlinearPositionValueInput.tooltip = nonlinearPositionInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterNonlinearPosition')

            try:
                sizeStepParam = params.itemById(sizeStepInputDef.id)
                sizeStep = adsk.core.ValueInput.createByString(sizeStepParam.expression)
            except:
                sizeStep = adsk.core.ValueInput.createByReal(0.005)
            _sizeStepValueInput = inputs.addValueInput(sizeStepInputDef.id, sizeStepInputDef.name, defaultLengthUnits, sizeStep)
            _sizeStepValueInput.tooltip = sizeStepInputDef.tooltip

            try:
                targetGapParam = params.itemById(targetGapInputDef.id)
                targetGap = adsk.core.ValueInput.createByString(targetGapParam.expression)
            except:
                targetGap = adsk.core.ValueInput.createByReal(0.01)
            _targetGapValueInput = inputs.addValueInput(targetGapInputDef.id, targetGapInputDef.name, defaultLengthUnits, targetGap)
            _targetGapValueInput.tooltip = targetGapInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterTargetGap')

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
    
    This handler checks to ensure the point is on a planar face and the body 
    the point is on is not an external reference.
    """
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.SelectionEventArgs.cast(args)
            entity = eventArgs.selection.entity
            entityType = entity.objectType
        
            if entityType in [adsk.core.Plane.classType(), adsk.fusion.BRepFace.classType(), adsk.fusion.SketchCurve.classType(), adsk.fusion.BRepEdge.classType()]:
                if entity.geometry is None:
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

            if _faceSelectionInput.selectionCount != 1 or _curveSelectionInput.selectionCount != 1:
                eventArgs.areInputsValid = False
                return

            if not all( [_startOffsetValueInput.isValidExpression, _endOffsetValueInput.isValidExpression,
                         _startSizeValueInput.isValidExpression, _endSizeValueInput.isValidExpression,
                         _sizeStepValueInput.isValidExpression, _targetGapValueInput.isValidExpression,
                         _flipValueInput.isValid, _flipDirectionValueInput.isValid,
                         _absoluteDepthOffsetValueInput.isValidExpression,
                         _relativeDepthOffsetValueInput.isValidExpression,
                         _nonlinearValueInput.isValid,
                         _nonlinearSizeValueInput.isValidExpression,
                         _nonlinearPositionValueInput.isValidExpression] ):
                eventArgs.areInputsValid = False
                return

            startOffset = _startOffsetValueInput.value
            if startOffset < 0:
                eventArgs.areInputsValid = False
                return

            endOffset = _endOffsetValueInput.value
            if endOffset < 0:
                eventArgs.areInputsValid = False
                return

            startSize = _startSizeValueInput.value
            if startSize < minimumGemstoneSize:
                eventArgs.areInputsValid = False
                return

            endSize = _endSizeValueInput.value
            if endSize < minimumGemstoneSize:
                eventArgs.areInputsValid = False
                return

            sizeStep = _sizeStepValueInput.value
            if sizeStep < 0 or sizeStep > 0.1:
                eventArgs.areInputsValid = False
                return
            
            targetGap = _targetGapValueInput.value
            if targetGap < 0:
                eventArgs.areInputsValid = False
                return
            
            nonlinearSize = _nonlinearSizeValueInput.value
            if nonlinearSize < minimumGemstoneSize:
                eventArgs.areInputsValid = False
                return

            nonlinearPosition = _nonlinearPositionValueInput.value
            if nonlinearPosition < 0.0 or nonlinearPosition > 1.0:
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
            face = _faceSelectionInput.selection(0).entity
            curveEntity = _curveSelectionInput.selection(0).entity
            
            curve = getCurve3D(curveEntity)
            if curve is None:
                return
            
            startOffset = _startOffsetValueInput.value
            endOffset = _endOffsetValueInput.value
            startSize = _startSizeValueInput.value
            endSize = _endSizeValueInput.value
            sizeStep = _sizeStepValueInput.value
            targetGap = _targetGapValueInput.value
            flip = _flipValueInput.value
            flipDirection = _flipDirectionValueInput.value
            absoluteDepthOffset = _absoluteDepthOffsetValueInput.value
            relativeDepthOffset = _relativeDepthOffsetValueInput.value
            nonlinear = _nonlinearValueInput.value
            nonlinearSize = _nonlinearSizeValueInput.value
            nonlinearPosition = _nonlinearPositionValueInput.value

            pointsAndSizes = calculatePointsAndSizesAlongCurve(curve, startOffset, endOffset, startSize, endSize, sizeStep, targetGap, flipDirection, nonlinear, nonlinearSize, nonlinearPosition)
            if len(pointsAndSizes) == 0:
                return

            if face.objectType == adsk.fusion.ConstructionPlane.classType():
                component = face.component
            else:
                component = face.body.parentComponent
            baseFeat = component.features.baseFeatures.add()
            baseFeat.startEdit()

            for point, size in pointsAndSizes:
                gemstone = createGemstone(face, point, size, flip, absoluteDepthOffset, relativeDepthOffset)
                if gemstone is not None:
                    body = component.bRepBodies.add(gemstone, baseFeat)
                    setGemstoneAttributes(body, flip, absoluteDepthOffset, relativeDepthOffset)
                    body.material = diamondMaterial

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

            face = _faceSelectionInput.selection(0).entity
            curveEntity = _curveSelectionInput.selection(0).entity
            if face.objectType == adsk.fusion.ConstructionPlane.classType():
                comp = face.component
            else:
                comp = face.body.parentComponent

            curve = getCurve3D(curveEntity)
            if curve is None:
                eventArgs.executeFailed = True
                return

            pointsAndSizes = calculatePointsAndSizesAlongCurve(curve, _startOffsetValueInput.value, _endOffsetValueInput.value,
                                                               _startSizeValueInput.value, _endSizeValueInput.value,
                                                               _sizeStepValueInput.value, _targetGapValueInput.value,
                                                               _flipDirectionValueInput.value,
                                                               _nonlinearValueInput.value, _nonlinearSizeValueInput.value, _nonlinearPositionValueInput.value)
            if len(pointsAndSizes) == 0:
                eventArgs.executeFailed = True
                return

            baseFeat = comp.features.baseFeatures.add()
            baseFeat.startEdit()

            for point, size in pointsAndSizes:
                gemstone = createGemstone(face, point, size, _flipValueInput.value, _absoluteDepthOffsetValueInput.value, _relativeDepthOffsetValueInput.value)
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

            startOffsetInput = adsk.core.ValueInput.createByString(_startOffsetValueInput.expression)
            customFeatureInput.addCustomParameter(startOffsetInputDef.id, startOffsetInputDef.name, startOffsetInput,
                                              defLengthUnits, True)

            endOffsetInput = adsk.core.ValueInput.createByString(_endOffsetValueInput.expression)
            customFeatureInput.addCustomParameter(endOffsetInputDef.id, endOffsetInputDef.name, endOffsetInput,
                                              defLengthUnits, True)

            startSizeInput = adsk.core.ValueInput.createByString(_startSizeValueInput.expression)
            customFeatureInput.addCustomParameter(startSizeInputDef.id, startSizeInputDef.name, startSizeInput,
                                              defLengthUnits, True)

            endSizeInput = adsk.core.ValueInput.createByString(_endSizeValueInput.expression)
            customFeatureInput.addCustomParameter(endSizeInputDef.id, endSizeInputDef.name, endSizeInput,
                                              defLengthUnits, True)

            sizeStepInput = adsk.core.ValueInput.createByString(_sizeStepValueInput.expression)
            customFeatureInput.addCustomParameter(sizeStepInputDef.id, sizeStepInputDef.name, sizeStepInput,
                                              defLengthUnits, True)

            targetGapInput = adsk.core.ValueInput.createByString(_targetGapValueInput.expression)
            customFeatureInput.addCustomParameter(targetGapInputDef.id, targetGapInputDef.name, targetGapInput,
                                              defLengthUnits, True)
                         
            flipInput = adsk.core.ValueInput.createByString(str(_flipValueInput.value).lower())
            customFeatureInput.addCustomParameter(flipInputDef.id, flipInputDef.name, flipInput, '', True)

            flipDirectionInput = adsk.core.ValueInput.createByString(str(_flipDirectionValueInput.value).lower())
            customFeatureInput.addCustomParameter(flipDirectionInputDef.id, flipDirectionInputDef.name, flipDirectionInput, '', True)

            absoluteDepthOffsetInput = adsk.core.ValueInput.createByString(_absoluteDepthOffsetValueInput.expression)
            customFeatureInput.addCustomParameter(absoluteDepthOffsetInputDef.id, absoluteDepthOffsetInputDef.name, absoluteDepthOffsetInput,
                                              defLengthUnits, True)

            relativeDepthOffsetInput = adsk.core.ValueInput.createByString(_relativeDepthOffsetValueInput.expression)
            customFeatureInput.addCustomParameter(relativeDepthOffsetInputDef.id, relativeDepthOffsetInputDef.name, relativeDepthOffsetInput,
                                              '', True)

            nonlinearInput = adsk.core.ValueInput.createByString(str(_nonlinearValueInput.value).lower())
            customFeatureInput.addCustomParameter(nonlinearInputDef.id, nonlinearInputDef.name, nonlinearInput, '', True)

            nonlinearSizeInput = adsk.core.ValueInput.createByString(_nonlinearSizeValueInput.expression)
            customFeatureInput.addCustomParameter(nonlinearSizeInputDef.id, nonlinearSizeInputDef.name, nonlinearSizeInput,
                                              defLengthUnits, True)

            nonlinearPositionInput = adsk.core.ValueInput.createByString(_nonlinearPositionValueInput.expression)
            customFeatureInput.addCustomParameter(nonlinearPositionInputDef.id, nonlinearPositionInputDef.name, nonlinearPositionInput,
                                              '', True)

            customFeatureInput.addDependency('face', face)
            customFeatureInput.addDependency('curve', curveEntity)

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

            curve = _editedCustomFeature.dependencies.itemById('curve').entity
            if curve is not None:
                _curveSelectionInput.addSelection(curve)

            face = _editedCustomFeature.dependencies.itemById('face').entity
            _faceSelectionInput.addSelection(face)
                
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
            curveEntity = _curveSelectionInput.selection(0).entity

            _editedCustomFeature.dependencies.deleteAll()
            _editedCustomFeature.dependencies.add('face', faceEntity)
            _editedCustomFeature.dependencies.add('curve', curveEntity)

            _editedCustomFeature.parameters.itemById(startOffsetInputDef.id).expression = _startOffsetValueInput.expression
            _editedCustomFeature.parameters.itemById(endOffsetInputDef.id).expression = _endOffsetValueInput.expression
            _editedCustomFeature.parameters.itemById(startSizeInputDef.id).expression = _startSizeValueInput.expression
            _editedCustomFeature.parameters.itemById(endSizeInputDef.id).expression = _endSizeValueInput.expression
            _editedCustomFeature.parameters.itemById(sizeStepInputDef.id).expression = _sizeStepValueInput.expression
            _editedCustomFeature.parameters.itemById(targetGapInputDef.id).expression = _targetGapValueInput.expression
            _editedCustomFeature.parameters.itemById(flipInputDef.id).expression = str(_flipValueInput.value).lower()
            _editedCustomFeature.parameters.itemById(flipDirectionInputDef.id).expression = str(_flipDirectionValueInput.value).lower()
            _editedCustomFeature.parameters.itemById(absoluteDepthOffsetInputDef.id).expression = _absoluteDepthOffsetValueInput.expression
            _editedCustomFeature.parameters.itemById(relativeDepthOffsetInputDef.id).expression = _relativeDepthOffsetValueInput.expression

            try:
                _editedCustomFeature.parameters.itemById(nonlinearInputDef.id).expression = str(_nonlinearValueInput.value).lower()
            except:
                _editedCustomFeature.parameters.add(nonlinearInputDef.id, nonlinearInputDef.name, adsk.core.ValueInput.createByString(str(_nonlinearValueInput.value).lower()), '', True)

            try:
                _editedCustomFeature.parameters.itemById(nonlinearSizeInputDef.id).expression = _nonlinearSizeValueInput.expression
            except:
                _editedCustomFeature.parameters.add(nonlinearSizeInputDef.id, nonlinearSizeInputDef.name, adsk.core.ValueInput.createByString(_nonlinearSizeValueInput.expression), _app.activeProduct.unitsManager.defaultLengthUnits, True)

            try:
                _editedCustomFeature.parameters.itemById(nonlinearPositionInputDef.id).expression = _nonlinearPositionValueInput.expression
            except:
                _editedCustomFeature.parameters.add(nonlinearPositionInputDef.id, nonlinearPositionInputDef.name, adsk.core.ValueInput.createByString(_nonlinearPositionValueInput.expression), '', True)

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
            customFeature = eventArgs.customFeature
            updateFeature(customFeature)

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

        curveEntity: adsk.fusion.SketchCurve = customFeature.dependencies.itemById('curve').entity
        if curveEntity is None: return False

        
        startOffset = customFeature.parameters.itemById(startOffsetInputDef.id).value
        endOffset = customFeature.parameters.itemById(endOffsetInputDef.id).value
        
        startSize = customFeature.parameters.itemById(startSizeInputDef.id).value
        endSize = customFeature.parameters.itemById(endSizeInputDef.id).value

        sizeStep = customFeature.parameters.itemById(sizeStepInputDef.id).value
        targetGap = customFeature.parameters.itemById(targetGapInputDef.id).value
        
        flip = customFeature.parameters.itemById(flipInputDef.id).expression.lower() == 'true'
        
        try:
            flipDirection = customFeature.parameters.itemById(flipDirectionInputDef.id).expression.lower() == 'true'
        except:
            flipDirection = False
        
        absoluteDepthOffset = customFeature.parameters.itemById(absoluteDepthOffsetInputDef.id).value
        relativeDepthOffset = customFeature.parameters.itemById(relativeDepthOffsetInputDef.id).value

        try:
            nonlinear = customFeature.parameters.itemById(nonlinearInputDef.id).expression.lower() == 'true'
        except:
            nonlinear = False

        try:
            nonlinearSize = customFeature.parameters.itemById(nonlinearSizeInputDef.id).value
        except:
            nonlinearSize = 0.1

        try:
            nonlinearPosition = customFeature.parameters.itemById(nonlinearPositionInputDef.id).value
        except:
            nonlinearPosition = 0.5

        curveGeometry = getCurve3D(curveEntity)
        if curveGeometry is None:
            return True

        pointsAndSizes = calculatePointsAndSizesAlongCurve(curveGeometry, startOffset, endOffset, startSize, endSize, sizeStep, targetGap, flipDirection, nonlinear, nonlinearSize, nonlinearPosition)
        if len(pointsAndSizes) == 0: return True

        if faceEntity.objectType == adsk.fusion.ConstructionPlane.classType():
            component = faceEntity.component
        else:
            component = faceEntity.body.parentComponent

        baseFeature.startEdit()
        
        
        success = True
        for i in range(len(pointsAndSizes)):
            point, size = pointsAndSizes[i]

            if i < baseFeature.bodies.count:
                currentBody = baseFeature.bodies.item(i)
                newBody = updateGemstone(currentBody, faceEntity, point, size, flip, absoluteDepthOffset, relativeDepthOffset)
                if newBody is not None:
                    baseFeature.updateBody(currentBody, newBody)
                else:
                    success = False
            else:
                gemstone = createGemstone(faceEntity, point, size, flip, absoluteDepthOffset, relativeDepthOffset)
                if gemstone is not None:
                    body = component.bRepBodies.add(gemstone, baseFeature)
                    body.material = diamondMaterial
                    
                    if not _isRolledForEdit: setGemstoneAttributes(body, flip, absoluteDepthOffset, relativeDepthOffset)
                    
                else:
                    success = False

        
        while baseFeature.bodies.count > len(pointsAndSizes):
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