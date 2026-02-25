import os
import json
import adsk.core, adsk.fusion, traceback

from ... import strings
from ... import constants
from ...helpers.showMessage import showMessage
from ...helpers.Curves import calculatePointsAlongCurve, getCurve3D
from ...helpers.Surface import getDataFromPointAndFace
from ...helpers import Bodies
from ...helpers.Points import getPointGeometry

_app: adsk.core.Application = None
_ui: adsk.core.UserInterface = None

_customFeatureDefinition: adsk.fusion.CustomFeature = None

_bodiesSelectionInput: adsk.core.SelectionCommandInput = None
_basePointSelectionInput: adsk.core.SelectionCommandInput = None
_baseSurfaceSelectionInput: adsk.core.SelectionCommandInput = None
_curveSelectionInput: adsk.core.SelectionCommandInput = None
_targetSurfaceSelectionInput: adsk.core.SelectionCommandInput = None
_placementModeDropdownInput: adsk.core.DropDownCommandInput = None
_flipDirectionValueInput: adsk.core.BoolValueCommandInput = None
_uniformDistributionValueInput: adsk.core.BoolValueCommandInput = None
_startOffsetValueInput: adsk.core.ValueCommandInput = None
_endOffsetValueInput: adsk.core.ValueCommandInput = None
_startRotateValueInput: adsk.core.ValueCommandInput = None
_endRotateValueInput: adsk.core.ValueCommandInput = None
_spacingValueInput: adsk.core.ValueCommandInput = None
_countValueInput: adsk.core.IntegerSpinnerCommandInput = None
_flipFaceNormalValueInput: adsk.core.BoolValueCommandInput = None
_absoluteDepthOffsetValueInput: adsk.core.ValueCommandInput = None
_relativeDepthOffsetValueInput: adsk.core.ValueCommandInput = None

_editedCustomFeature: adsk.fusion.CustomFeature = None
_restoreTimelineObject: adsk.fusion.TimelineObject = None
_isRolledForEdit: bool = False

PRESERVE_BODIES: bool = False

_handlers = []

COMMAND_ID, CREATE_COMMAND_ID, EDIT_COMMAND_ID = strings.getCommandIds(strings.PATTERN_ALONG_PATH_ON_SURFACE)

createCommandInputDef = strings.InputDef(CREATE_COMMAND_ID, 'Pattern Along Path', 'Distributes bodies along a curve on a surface.')
editCommandInputDef = strings.InputDef(EDIT_COMMAND_ID, 'Edit Pattern', 'Edits the parameters of existing pattern.')

selectBodiesInputDef = strings.InputDef(
    'selectBodies',
    'Select Bodies',
    'Select the bodies (solid or surface) to distribute along the curve.'
    )

selectBasePointInputDef = strings.InputDef(
    'selectBasePoint',
    'Base Point',
    'Select the base point (origin) of the pattern element.'
    )

selectBaseSurfaceInputDef = strings.InputDef(
    'selectBaseSurface',
    'Base Surface',
    'Select the base surface for the pattern element orientation.'
    )

selectCurveInputDef = strings.InputDef(
    'selectCurve',
    'Target Curve',
    'Select the curve along which to distribute the bodies.'
    )

selectTargetSurfaceInputDef = strings.InputDef(
    'selectTargetSurface',
    'Target Surface',
    'Select the surface for orienting the bodies.\nIf not selected, the orientation remains unchanged.'
    )

placementModeInputDef = strings.InputDef(
    strings.PatternAlongPath.placementModeInputId,
    'Placement Mode',
    'Choose where to place bodies: projected onto target surface or on the curve.'
    )

flipDirectionInputDef = strings.InputDef(
    'flipDirection',
    'Flip Direction',
    "Flip placement direction.\nStarts placing elements from the opposite end of the curve."
    )

uniformDistributionInputDef = strings.InputDef(
    'uniformDistribution',
    'Uniform Distribution',
    "Distribute elements uniformly along the curve.\nAdjusts spacing to fill the entire available length."
    )

startOffsetInputDef = strings.InputDef(
    'startOffset',
    'Start Offset',
    "Offset from the start of the curve.\nDistance from the beginning of the curve to the first element."
    )

endOffsetInputDef = strings.InputDef(
    'endOffset',
    'End Offset',
    "Offset from the end of the curve.\nDistance from the end of the curve to the last element."
    )

startRotateInputDef = strings.InputDef(
    'startRotate',
    'Start Rotate',
    "Rotation angle for the first element around the surface normal."
    )

endRotateInputDef = strings.InputDef(
    'endRotate',
    'End Rotate',
    "Rotation angle for the last element around the surface normal."
    )

spacingInputDef = strings.InputDef(
    'spacing',
    'Spacing',
    "Distance between base points of adjacent elements along the curve."
    )

countInputDef = strings.InputDef(
    'count',
    'Count',
    "Maximum number of elements to place.\nSet to 0 for unlimited (fill the entire curve).\nWith uniform distribution, fewer elements are centered within the available length."
    )

flipFaceNormalInputDef = strings.InputDef(
    'flipFaceNormal',
    'Flip Face Normal',
    "Flip face normal direction.\nReverses the normal direction used for orientation."
    )

absoluteDepthOffsetInputDef = strings.InputDef(
    'absoluteDepthOffset',
    'Absolute Depth Offset',
    "Additional depth offset along the surface normal in absolute units."
    )

relativeDepthOffsetInputDef = strings.InputDef(
    'relativeDepthOffset',
    'Relative Depth Offset',
    "Depth offset as a fraction of the spacing distance."
    )

RESOURCES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')


def run(panel: adsk.core.ToolbarPanel):
    """Initialize the pattern along path command by setting up command definitions and UI elements."""
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
        _customFeatureDefinition = adsk.fusion.CustomFeatureDefinition.create(COMMAND_ID, strings.PATTERN_ALONG_PATH_ON_SURFACE, RESOURCES_FOLDER)
        _customFeatureDefinition.editCommandId = EDIT_COMMAND_ID

        computeCustomFeature = ComputeCustomFeature()
        _customFeatureDefinition.customFeatureCompute.add(computeCustomFeature)
        _handlers.append(computeCustomFeature)
    except:
        showMessage(f'Run failed:\n{traceback.format_exc()}', True)


def stop(panel: adsk.core.ToolbarPanel):
    """Clean up the pattern along path command by removing UI elements and handlers."""
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
    """Event handler for creating the command dialog for new pattern along path.
    
    Sets up all necessary input controls including selections for bodies, base point, base surface,
    target curve, target surface, and value inputs for spacing, offsets, rotation, etc.
    """
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs
            defaultLengthUnits = _app.activeProduct.unitsManager.defaultLengthUnits

            global _bodiesSelectionInput, _basePointSelectionInput, _baseSurfaceSelectionInput
            global _curveSelectionInput, _targetSurfaceSelectionInput, _placementModeDropdownInput
            global _flipDirectionValueInput, _uniformDistributionValueInput
            global _startOffsetValueInput, _endOffsetValueInput
            global _startRotateValueInput, _endRotateValueInput
            global _spacingValueInput, _countValueInput
            global _flipFaceNormalValueInput
            global _absoluteDepthOffsetValueInput, _relativeDepthOffsetValueInput

            _bodiesSelectionInput = inputs.addSelectionInput(selectBodiesInputDef.id, selectBodiesInputDef.name, selectBodiesInputDef.tooltip)
            _bodiesSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SolidBodies)
            _bodiesSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SurfaceBodies)
            _bodiesSelectionInput.tooltip = selectBodiesInputDef.tooltip
            _bodiesSelectionInput.setSelectionLimits(1, 0)

            _basePointSelectionInput = inputs.addSelectionInput(selectBasePointInputDef.id, selectBasePointInputDef.name, selectBasePointInputDef.tooltip)
            _basePointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchPoints)
            _basePointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.ConstructionPoints)
            _basePointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Vertices)
            _basePointSelectionInput.tooltip = selectBasePointInputDef.tooltip
            _basePointSelectionInput.setSelectionLimits(1, 1)

            _baseSurfaceSelectionInput = inputs.addSelectionInput(selectBaseSurfaceInputDef.id, selectBaseSurfaceInputDef.name, selectBaseSurfaceInputDef.tooltip)
            _baseSurfaceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _baseSurfaceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.ConstructionPlanes)
            _baseSurfaceSelectionInput.tooltip = selectBaseSurfaceInputDef.tooltip
            _baseSurfaceSelectionInput.setSelectionLimits(1, 1)

            inputs.addSeparatorCommandInput('separatorAfterBaseSurface')

            _curveSelectionInput = inputs.addSelectionInput(selectCurveInputDef.id, selectCurveInputDef.name, selectCurveInputDef.tooltip)
            _curveSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchCurves)
            _curveSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Edges)
            _curveSelectionInput.tooltip = selectCurveInputDef.tooltip
            _curveSelectionInput.setSelectionLimits(1, 1)

            _targetSurfaceSelectionInput = inputs.addSelectionInput(selectTargetSurfaceInputDef.id, selectTargetSurfaceInputDef.name, selectTargetSurfaceInputDef.tooltip)
            _targetSurfaceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _targetSurfaceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.ConstructionPlanes)
            _targetSurfaceSelectionInput.tooltip = selectTargetSurfaceInputDef.tooltip
            _targetSurfaceSelectionInput.setSelectionLimits(0, 1)

            _placementModeDropdownInput = inputs.addDropDownCommandInput(placementModeInputDef.id, placementModeInputDef.name, adsk.core.DropDownStyles.TextListDropDownStyle)
            _placementModeDropdownInput.tooltip = placementModeInputDef.tooltip
            for i, modeName in enumerate(strings.PatternAlongPath.placementModes):
                _placementModeDropdownInput.listItems.add(modeName, i == constants.patternAlongPathPlacementOnSurfaceIndex)

            inputs.addSeparatorCommandInput('separatorAfterTargetSurface')

            flipDirection = False
            _flipDirectionValueInput = inputs.addBoolValueInput(flipDirectionInputDef.id, flipDirectionInputDef.name, True, '', flipDirection)
            _flipDirectionValueInput.tooltip = flipDirectionInputDef.tooltip

            uniformDistribution = False
            _uniformDistributionValueInput = inputs.addBoolValueInput(uniformDistributionInputDef.id, uniformDistributionInputDef.name, True, '', uniformDistribution)
            _uniformDistributionValueInput.tooltip = uniformDistributionInputDef.tooltip

            startOffset = adsk.core.ValueInput.createByReal(0.0)
            _startOffsetValueInput = inputs.addValueInput(startOffsetInputDef.id, startOffsetInputDef.name, defaultLengthUnits, startOffset)
            _startOffsetValueInput.tooltip = startOffsetInputDef.tooltip

            endOffset = adsk.core.ValueInput.createByReal(0.0)
            _endOffsetValueInput = inputs.addValueInput(endOffsetInputDef.id, endOffsetInputDef.name, defaultLengthUnits, endOffset)
            _endOffsetValueInput.tooltip = endOffsetInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterOffsets')

            startRotate = adsk.core.ValueInput.createByReal(0.0)
            _startRotateValueInput = inputs.addValueInput(startRotateInputDef.id, startRotateInputDef.name, 'deg', startRotate)
            _startRotateValueInput.tooltip = startRotateInputDef.tooltip

            endRotate = adsk.core.ValueInput.createByReal(0.0)
            _endRotateValueInput = inputs.addValueInput(endRotateInputDef.id, endRotateInputDef.name, 'deg', endRotate)
            _endRotateValueInput.tooltip = endRotateInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterRotation')

            _countValueInput = inputs.addIntegerSpinnerCommandInput(countInputDef.id, countInputDef.name, 0, 10000, 1, 0)
            _countValueInput.tooltip = countInputDef.tooltip

            spacing = adsk.core.ValueInput.createByReal(constants.patternAlongPathDefaultSpacingCm)
            _spacingValueInput = inputs.addValueInput(spacingInputDef.id, spacingInputDef.name, defaultLengthUnits, spacing)
            _spacingValueInput.tooltip = spacingInputDef.tooltip

            flipFaceNormal = False
            _flipFaceNormalValueInput = inputs.addBoolValueInput(flipFaceNormalInputDef.id, flipFaceNormalInputDef.name, True, '', flipFaceNormal)
            _flipFaceNormalValueInput.tooltip = flipFaceNormalInputDef.tooltip

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
    """Event handler for creating the command dialog for editing existing pattern along path.
    
    Retrieves the selected custom feature, populates inputs with existing parameter values
    and dependencies, and connects event handlers for editing operations.
    """
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs
            defaultLengthUnits = _app.activeProduct.unitsManager.defaultLengthUnits

            global _editedCustomFeature, _bodiesSelectionInput, _basePointSelectionInput, _baseSurfaceSelectionInput
            global _curveSelectionInput, _targetSurfaceSelectionInput, _placementModeDropdownInput
            _editedCustomFeature = _ui.activeSelections.item(0).entity
            if _editedCustomFeature is None:
                return

            global _flipDirectionValueInput, _uniformDistributionValueInput
            global _startOffsetValueInput, _endOffsetValueInput
            global _startRotateValueInput, _endRotateValueInput
            global _spacingValueInput, _countValueInput
            global _flipFaceNormalValueInput
            global _absoluteDepthOffsetValueInput, _relativeDepthOffsetValueInput

            _bodiesSelectionInput = inputs.addSelectionInput(selectBodiesInputDef.id, selectBodiesInputDef.name, selectBodiesInputDef.tooltip)
            _bodiesSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SolidBodies)
            _bodiesSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SurfaceBodies)
            _bodiesSelectionInput.tooltip = selectBodiesInputDef.tooltip
            _bodiesSelectionInput.setSelectionLimits(1, 0)

            _basePointSelectionInput = inputs.addSelectionInput(selectBasePointInputDef.id, selectBasePointInputDef.name, selectBasePointInputDef.tooltip)
            _basePointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchPoints)
            _basePointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.ConstructionPoints)
            _basePointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Vertices)
            _basePointSelectionInput.tooltip = selectBasePointInputDef.tooltip
            _basePointSelectionInput.setSelectionLimits(1, 1)

            _baseSurfaceSelectionInput = inputs.addSelectionInput(selectBaseSurfaceInputDef.id, selectBaseSurfaceInputDef.name, selectBaseSurfaceInputDef.tooltip)
            _baseSurfaceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _baseSurfaceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.ConstructionPlanes)
            _baseSurfaceSelectionInput.tooltip = selectBaseSurfaceInputDef.tooltip
            _baseSurfaceSelectionInput.setSelectionLimits(1, 1)

            inputs.addSeparatorCommandInput('separatorAfterBaseSurface')

            _curveSelectionInput = inputs.addSelectionInput(selectCurveInputDef.id, selectCurveInputDef.name, selectCurveInputDef.tooltip)
            _curveSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchCurves)
            _curveSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Edges)
            _curveSelectionInput.tooltip = selectCurveInputDef.tooltip
            _curveSelectionInput.setSelectionLimits(1, 1)

            _targetSurfaceSelectionInput = inputs.addSelectionInput(selectTargetSurfaceInputDef.id, selectTargetSurfaceInputDef.name, selectTargetSurfaceInputDef.tooltip)
            _targetSurfaceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _targetSurfaceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.ConstructionPlanes)
            _targetSurfaceSelectionInput.tooltip = selectTargetSurfaceInputDef.tooltip
            _targetSurfaceSelectionInput.setSelectionLimits(0, 1)

            _placementModeDropdownInput = inputs.addDropDownCommandInput(placementModeInputDef.id, placementModeInputDef.name, adsk.core.DropDownStyles.TextListDropDownStyle)
            _placementModeDropdownInput.tooltip = placementModeInputDef.tooltip
            for modeName in strings.PatternAlongPath.placementModes:
                _placementModeDropdownInput.listItems.add(modeName, False)

            placementModeIndex = getPlacementModeIndexFromParameters(_editedCustomFeature.parameters)
            if 0 <= placementModeIndex < _placementModeDropdownInput.listItems.count:
                _placementModeDropdownInput.listItems.item(placementModeIndex).isSelected = True
            else:
                _placementModeDropdownInput.listItems.item(constants.patternAlongPathPlacementOnSurfaceIndex).isSelected = True

            inputs.addSeparatorCommandInput('separatorAfterTargetSurface')

            params = _editedCustomFeature.parameters

            try:
                flipDirectionParam = params.itemById(flipDirectionInputDef.id)
                flipDirection = flipDirectionParam.expression.lower() == 'true'
            except:
                flipDirection = False
            _flipDirectionValueInput = inputs.addBoolValueInput(flipDirectionInputDef.id, flipDirectionInputDef.name, True, '', flipDirection)
            _flipDirectionValueInput.tooltip = flipDirectionInputDef.tooltip

            try:
                uniformDistributionParam = params.itemById(uniformDistributionInputDef.id)
                uniformDistribution = uniformDistributionParam.expression.lower() == 'true'
            except:
                uniformDistribution = False
            _uniformDistributionValueInput = inputs.addBoolValueInput(uniformDistributionInputDef.id, uniformDistributionInputDef.name, True, '', uniformDistribution)
            _uniformDistributionValueInput.tooltip = uniformDistributionInputDef.tooltip

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

            inputs.addSeparatorCommandInput('separatorAfterOffsets')

            try:
                startRotateParam = params.itemById(startRotateInputDef.id)
                startRotate = adsk.core.ValueInput.createByString(startRotateParam.expression)
            except:
                startRotate = adsk.core.ValueInput.createByReal(0.0)
            _startRotateValueInput = inputs.addValueInput(startRotateInputDef.id, startRotateInputDef.name, 'deg', startRotate)
            _startRotateValueInput.tooltip = startRotateInputDef.tooltip

            try:
                endRotateParam = params.itemById(endRotateInputDef.id)
                endRotate = adsk.core.ValueInput.createByString(endRotateParam.expression)
            except:
                endRotate = adsk.core.ValueInput.createByReal(0.0)
            _endRotateValueInput = inputs.addValueInput(endRotateInputDef.id, endRotateInputDef.name, 'deg', endRotate)
            _endRotateValueInput.tooltip = endRotateInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterRotation')

            try:
                spacingParam = params.itemById(spacingInputDef.id)
                spacing = adsk.core.ValueInput.createByString(spacingParam.expression)
            except:
                spacing = adsk.core.ValueInput.createByReal(constants.patternAlongPathDefaultSpacingCm)
            try:
                countParam = params.itemById(countInputDef.id)
                countValue = int(countParam.value)
            except:
                countValue = 0
            _countValueInput = inputs.addIntegerSpinnerCommandInput(countInputDef.id, countInputDef.name, 0, 10000, 1, countValue)
            _countValueInput.tooltip = countInputDef.tooltip

            _spacingValueInput = inputs.addValueInput(spacingInputDef.id, spacingInputDef.name, defaultLengthUnits, spacing)
            _spacingValueInput.tooltip = spacingInputDef.tooltip

            try:
                flipFaceNormalParam = params.itemById(flipFaceNormalInputDef.id)
                flipFaceNormal = flipFaceNormalParam.expression.lower() == 'true'
            except:
                flipFaceNormal = False
            _flipFaceNormalValueInput = inputs.addBoolValueInput(flipFaceNormalInputDef.id, flipFaceNormalInputDef.name, True, '', flipFaceNormal)
            _flipFaceNormalValueInput.tooltip = flipFaceNormalInputDef.tooltip

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
    """Event handler for controlling user selection during command execution."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.SelectionEventArgs.cast(args)
            entity = eventArgs.selection.entity
            entityType = entity.objectType

            if entityType == adsk.fusion.BRepBody.classType():
                targetSurfaceBody = getTargetSurfaceBody()
                if targetSurfaceBody is not None and entity == targetSurfaceBody:
                    eventArgs.isSelectable = False
                    return

            if entityType in [adsk.fusion.BRepFace.classType(), adsk.fusion.ConstructionPlane.classType()]:
                if hasattr(entity, 'geometry') and entity.geometry is None:
                    eventArgs.isSelectable = False
                    return

            if entityType in [adsk.fusion.SketchCurve.classType(), adsk.fusion.BRepEdge.classType()]:
                if hasattr(entity, 'geometry') and entity.geometry is None:
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

            if _bodiesSelectionInput.selectionCount < 1:
                eventArgs.areInputsValid = False
                return

            if _basePointSelectionInput.selectionCount != 1:
                eventArgs.areInputsValid = False
                return

            if _baseSurfaceSelectionInput.selectionCount != 1:
                eventArgs.areInputsValid = False
                return

            if _curveSelectionInput.selectionCount != 1:
                eventArgs.areInputsValid = False
                return

            if _placementModeDropdownInput.selectedItem is None:
                eventArgs.areInputsValid = False
                return

            if not all([_startOffsetValueInput.isValidExpression, _endOffsetValueInput.isValidExpression,
                        _startRotateValueInput.isValidExpression, _endRotateValueInput.isValidExpression,
                        _spacingValueInput.isValidExpression,
                        _flipDirectionValueInput.isValid, _uniformDistributionValueInput.isValid,
                        _flipFaceNormalValueInput.isValid,
                        _absoluteDepthOffsetValueInput.isValidExpression,
                        _relativeDepthOffsetValueInput.isValidExpression]):
                eventArgs.areInputsValid = False
                return

            spacing = _spacingValueInput.value
            if spacing <= 0:
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
            sourceBodies: list[adsk.fusion.BRepBody] = []
            for i in range(_bodiesSelectionInput.selectionCount):
                sourceBodies.append(_bodiesSelectionInput.selection(i).entity)

            basePointEntity = _basePointSelectionInput.selection(0).entity
            baseSurface = _baseSurfaceSelectionInput.selection(0).entity
            curveEntity = _curveSelectionInput.selection(0).entity

            hasTargetSurface = _targetSurfaceSelectionInput.selectionCount > 0
            targetSurface = _targetSurfaceSelectionInput.selection(0).entity if hasTargetSurface else None
            placementModeIndex = getSelectedPlacementModeIndex()

            curve = getCurve3D(curveEntity)
            if curve is None:
                return

            basePoint = getPointGeometry(basePointEntity)
            if basePoint is None:
                return

            spacing = _spacingValueInput.value
            count = _countValueInput.value
            startOffset = _startOffsetValueInput.value
            endOffset = _endOffsetValueInput.value
            startRotate = _startRotateValueInput.value
            endRotate = _endRotateValueInput.value
            flipDirection = _flipDirectionValueInput.value
            uniformDistribution = _uniformDistributionValueInput.value
            flipFaceNormal = _flipFaceNormalValueInput.value
            absoluteDepthOffset = _absoluteDepthOffsetValueInput.value
            relativeDepthOffset = _relativeDepthOffsetValueInput.value

            curvePoints = calculatePointsAlongCurve(curve, spacing, startOffset, endOffset, flipDirection, uniformDistribution, count)
            if len(curvePoints) == 0:
                return

            basePointOnSurface, baseLengthDir, baseWidthDir, baseNormal = getDataFromPointAndFace(baseSurface, basePoint)
            if basePointOnSurface is None:
                return

            component = getComponentFromEntity(baseSurface)
            if component is None:
                return

            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()

            numberOfPositions = len(curvePoints)
            newTransforms: list[adsk.core.Matrix3D] = []

            for posIndex, (curvePoint, curveTangent) in enumerate(curvePoints):
                normalizedT = posIndex / (numberOfPositions - 1) if numberOfPositions > 1 else 0.0
                rotationAngle = startRotate + (endRotate - startRotate) * normalizedT
                totalDepthOffset = absoluteDepthOffset + relativeDepthOffset * spacing

                transform = computeTransform(
                    basePointOnSurface, baseLengthDir, baseWidthDir, baseNormal,
                    curvePoint, curveTangent, targetSurface, flipFaceNormal,
                    rotationAngle, totalDepthOffset, placementModeIndex
                )

                for sourceBody in sourceBodies:
                    bodyCopy = transformBody(sourceBody, transform)
                    if bodyCopy is not None:
                        newBody = component.bRepBodies.add(bodyCopy, baseFeature)
                        Bodies.copyAttributes(sourceBody, newBody)
                        newTransforms.append(transform)

            saveTransformsToFeature(baseFeature, newTransforms)
            baseFeature.finishEdit()

        except:
            if baseFeature:
                baseFeature.finishEdit()
            showMessage(f'ExecutePreviewHandler: {traceback.format_exc()}\n', True)


class CreateExecuteHandler(adsk.core.CommandEventHandler):
    """Event handler for the execute event of the create command."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.CommandEventArgs.cast(args)

            sourceBodies: list[adsk.fusion.BRepBody] = []
            for i in range(_bodiesSelectionInput.selectionCount):
                sourceBodies.append(_bodiesSelectionInput.selection(i).entity)

            basePointEntity = _basePointSelectionInput.selection(0).entity
            baseSurface = _baseSurfaceSelectionInput.selection(0).entity
            curveEntity = _curveSelectionInput.selection(0).entity

            hasTargetSurface = _targetSurfaceSelectionInput.selectionCount > 0
            targetSurface = _targetSurfaceSelectionInput.selection(0).entity if hasTargetSurface else None
            placementModeIndex = getSelectedPlacementModeIndex()

            curve = getCurve3D(curveEntity)
            if curve is None:
                eventArgs.executeFailed = True
                return

            basePoint = getPointGeometry(basePointEntity)
            if basePoint is None:
                eventArgs.executeFailed = True
                return

            spacing = _spacingValueInput.value
            count = _countValueInput.value
            startOffset = _startOffsetValueInput.value
            endOffset = _endOffsetValueInput.value
            startRotate = _startRotateValueInput.value
            endRotate = _endRotateValueInput.value
            flipDirection = _flipDirectionValueInput.value
            uniformDistribution = _uniformDistributionValueInput.value
            flipFaceNormal = _flipFaceNormalValueInput.value
            absoluteDepthOffset = _absoluteDepthOffsetValueInput.value
            relativeDepthOffset = _relativeDepthOffsetValueInput.value

            curvePoints = calculatePointsAlongCurve(curve, spacing, startOffset, endOffset, flipDirection, uniformDistribution, count)
            if len(curvePoints) == 0:
                eventArgs.executeFailed = True
                return

            basePointOnSurface, baseLengthDir, baseWidthDir, baseNormal = getDataFromPointAndFace(baseSurface, basePoint)
            if basePointOnSurface is None:
                eventArgs.executeFailed = True
                return

            component = getComponentFromEntity(baseSurface)
            if component is None:
                eventArgs.executeFailed = True
                return

            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()

            numberOfPositions = len(curvePoints)
            newTransforms: list[adsk.core.Matrix3D] = []

            for posIndex, (curvePoint, curveTangent) in enumerate(curvePoints):
                normalizedT = posIndex / (numberOfPositions - 1) if numberOfPositions > 1 else 0.0
                rotationAngle = startRotate + (endRotate - startRotate) * normalizedT
                totalDepthOffset = absoluteDepthOffset + relativeDepthOffset * spacing

                transform = computeTransform(
                    basePointOnSurface, baseLengthDir, baseWidthDir, baseNormal,
                    curvePoint, curveTangent, targetSurface, flipFaceNormal,
                    rotationAngle, totalDepthOffset, placementModeIndex
                )

                for sourceBody in sourceBodies:
                    bodyCopy = transformBody(sourceBody, transform)
                    if bodyCopy is not None:
                        newBody = component.bRepBodies.add(bodyCopy, baseFeature)
                        Bodies.copyAttributes(sourceBody, newBody)
                        newTransforms.append(transform)

            saveTransformsToFeature(baseFeature, newTransforms)
            baseFeature.finishEdit()

            design: adsk.fusion.Design = _app.activeProduct
            defLengthUnits = design.unitsManager.defaultLengthUnits
            customFeatureInput = component.features.customFeatures.createInput(_customFeatureDefinition)

            spacingInput = adsk.core.ValueInput.createByString(_spacingValueInput.expression)
            customFeatureInput.addCustomParameter(spacingInputDef.id, spacingInputDef.name, spacingInput,
                                              defLengthUnits, True)

            startOffsetInput = adsk.core.ValueInput.createByString(_startOffsetValueInput.expression)
            customFeatureInput.addCustomParameter(startOffsetInputDef.id, startOffsetInputDef.name, startOffsetInput,
                                              defLengthUnits, True)

            endOffsetInput = adsk.core.ValueInput.createByString(_endOffsetValueInput.expression)
            customFeatureInput.addCustomParameter(endOffsetInputDef.id, endOffsetInputDef.name, endOffsetInput,
                                              defLengthUnits, True)

            startRotateInput = adsk.core.ValueInput.createByString(_startRotateValueInput.expression)
            customFeatureInput.addCustomParameter(startRotateInputDef.id, startRotateInputDef.name, startRotateInput,
                                              'deg', True)

            endRotateInput = adsk.core.ValueInput.createByString(_endRotateValueInput.expression)
            customFeatureInput.addCustomParameter(endRotateInputDef.id, endRotateInputDef.name, endRotateInput,
                                              'deg', True)

            flipDirectionInput = adsk.core.ValueInput.createByString(str(_flipDirectionValueInput.value).lower())
            customFeatureInput.addCustomParameter(flipDirectionInputDef.id, flipDirectionInputDef.name, flipDirectionInput, '', True)

            uniformDistributionInput = adsk.core.ValueInput.createByString(str(_uniformDistributionValueInput.value).lower())
            customFeatureInput.addCustomParameter(uniformDistributionInputDef.id, uniformDistributionInputDef.name, uniformDistributionInput, '', True)

            flipFaceNormalInput = adsk.core.ValueInput.createByString(str(_flipFaceNormalValueInput.value).lower())
            customFeatureInput.addCustomParameter(flipFaceNormalInputDef.id, flipFaceNormalInputDef.name, flipFaceNormalInput, '', True)

            absoluteDepthOffsetInput = adsk.core.ValueInput.createByString(_absoluteDepthOffsetValueInput.expression)
            customFeatureInput.addCustomParameter(absoluteDepthOffsetInputDef.id, absoluteDepthOffsetInputDef.name, absoluteDepthOffsetInput,
                                              defLengthUnits, True)

            relativeDepthOffsetInput = adsk.core.ValueInput.createByString(_relativeDepthOffsetValueInput.expression)
            customFeatureInput.addCustomParameter(relativeDepthOffsetInputDef.id, relativeDepthOffsetInputDef.name, relativeDepthOffsetInput,
                                              '', True)

            placementModeInput = adsk.core.ValueInput.createByString(str(getSelectedPlacementModeIndex()))
            customFeatureInput.addCustomParameter(placementModeInputDef.id, placementModeInputDef.name, placementModeInput,
                                              '', True)

            countInput = adsk.core.ValueInput.createByReal(float(_countValueInput.value))
            customFeatureInput.addCustomParameter(countInputDef.id, countInputDef.name, countInput, '', True)

            # sourceBodies.sort(key=lambda b: b.entityToken)
            for i, body in enumerate(sourceBodies):
                customFeatureInput.addDependency(f'firstBodyFace{i}', body.faces[0])

            customFeatureInput.addDependency('basePoint', basePointEntity)
            customFeatureInput.addDependency('baseSurface', baseSurface)
            customFeatureInput.addDependency('targetCurve', curveEntity)
            if targetSurface is not None:
                customFeatureInput.addDependency('targetSurface', targetSurface)

            customFeatureInput.setStartAndEndFeatures(baseFeature, baseFeature)
            component.features.customFeatures.add(customFeatureInput)

        except:
            baseFeature.finishEdit()
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

            # targetSurfaceBodyToExclude: adsk.fusion.BRepBody = None
            # try:
            #     targetSurfaceDep = _editedCustomFeature.dependencies.itemById('targetSurface')
            #     if targetSurfaceDep is not None and targetSurfaceDep.entity is not None:
            #         targetSurfaceEntity = targetSurfaceDep.entity
            #         if targetSurfaceEntity.objectType == adsk.fusion.BRepFace.classType():
            #             targetSurfaceBodyToExclude = targetSurfaceEntity.body
            # except:
            #     pass

            validSourceBodies: list[adsk.fusion.BRepBody] = []
            idx = 0
            while True:
                faceDep = _editedCustomFeature.dependencies.itemById(f'firstBodyFace{idx}')
                if faceDep is None:
                    break
                face = adsk.fusion.BRepFace.cast(faceDep.entity)
                if face is None or face.body is None:
                    break
                validSourceBodies.append(face.body)
                idx += 1

            command = eventArgs.command
            command.beginStep()

            try:
                basePointDep = _editedCustomFeature.dependencies.itemById('basePoint')
                if basePointDep is not None and basePointDep.entity is not None:
                    _basePointSelectionInput.addSelection(basePointDep.entity)
            except:
                pass

            try:
                baseSurfaceDep = _editedCustomFeature.dependencies.itemById('baseSurface')
                if baseSurfaceDep is not None and baseSurfaceDep.entity is not None:
                    _baseSurfaceSelectionInput.addSelection(baseSurfaceDep.entity)
            except:
                pass

            try:
                curveDep = _editedCustomFeature.dependencies.itemById('targetCurve')
                if curveDep is not None and curveDep.entity is not None:
                    _curveSelectionInput.addSelection(curveDep.entity)
            except:
                pass

            try:
                targetSurfaceDep = _editedCustomFeature.dependencies.itemById('targetSurface')
                if targetSurfaceDep is not None and targetSurfaceDep.entity is not None:
                    _targetSurfaceSelectionInput.addSelection(targetSurfaceDep.entity)
            except:
                pass

            _bodiesSelectionInput.clearSelection()
            for body in validSourceBodies:
                _bodiesSelectionInput.addSelection(body)

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

            sourceBodies: list[adsk.fusion.BRepBody] = []
            for i in range(_bodiesSelectionInput.selectionCount):
                sourceBodies.append(_bodiesSelectionInput.selection(i).entity)

            basePointEntity = _basePointSelectionInput.selection(0).entity
            baseSurfaceEntity = _baseSurfaceSelectionInput.selection(0).entity
            curveEntity = _curveSelectionInput.selection(0).entity

            targetSurfaceEntity = None
            if _targetSurfaceSelectionInput.selectionCount > 0:
                targetSurfaceEntity = _targetSurfaceSelectionInput.selection(0).entity

            _editedCustomFeature.dependencies.deleteAll()

            # sourceBodies.sort(key=lambda b: b.entityToken)
            for i, body in enumerate(sourceBodies):
                _editedCustomFeature.dependencies.add(f'firstBodyFace{i}', body.faces[0])

            _editedCustomFeature.dependencies.add('basePoint', basePointEntity)
            _editedCustomFeature.dependencies.add('baseSurface', baseSurfaceEntity)
            _editedCustomFeature.dependencies.add('targetCurve', curveEntity)

            if targetSurfaceEntity is not None:
                _editedCustomFeature.dependencies.add('targetSurface', targetSurfaceEntity)

            _editedCustomFeature.parameters.itemById(spacingInputDef.id).expression = _spacingValueInput.expression
            _editedCustomFeature.parameters.itemById(startOffsetInputDef.id).expression = _startOffsetValueInput.expression
            _editedCustomFeature.parameters.itemById(endOffsetInputDef.id).expression = _endOffsetValueInput.expression
            _editedCustomFeature.parameters.itemById(startRotateInputDef.id).expression = _startRotateValueInput.expression
            _editedCustomFeature.parameters.itemById(endRotateInputDef.id).expression = _endRotateValueInput.expression
            _editedCustomFeature.parameters.itemById(flipDirectionInputDef.id).expression = str(_flipDirectionValueInput.value).lower()
            _editedCustomFeature.parameters.itemById(uniformDistributionInputDef.id).expression = str(_uniformDistributionValueInput.value).lower()
            _editedCustomFeature.parameters.itemById(flipFaceNormalInputDef.id).expression = str(_flipFaceNormalValueInput.value).lower()
            _editedCustomFeature.parameters.itemById(absoluteDepthOffsetInputDef.id).expression = _absoluteDepthOffsetValueInput.expression
            _editedCustomFeature.parameters.itemById(relativeDepthOffsetInputDef.id).expression = _relativeDepthOffsetValueInput.expression
            _editedCustomFeature.parameters.itemById(placementModeInputDef.id).expression = str(getSelectedPlacementModeIndex())
            try:
                _editedCustomFeature.parameters.itemById(countInputDef.id).expression = str(_countValueInput.value)
            except:
                pass

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


def computeTransform(basePoint: adsk.core.Point3D, baseLengthDir: adsk.core.Vector3D,
                     baseWidthDir: adsk.core.Vector3D, baseNormal: adsk.core.Vector3D,
                     curvePoint: adsk.core.Point3D, curveTangent: adsk.core.Vector3D,
                     targetSurface: adsk.core.Base, flipFaceNormal: bool,
                     rotationAngle: float, depthOffset: float, placementModeIndex: int) -> adsk.core.Matrix3D:
    """Compute the transformation matrix for placing a body at a curve point.

    The element is always positioned on the curve. The orientation follows
    the curve tangent (length direction) projected onto the tangent plane
    of the reference surface. The surface normal defines the "up" direction.

    When a target surface is selected, its normal is used for orientation.
    Otherwise, the base surface normal is used. In both cases, the curve
    tangent drives the forward direction.

    Args:
        basePoint: The base point on the base surface.
        baseLengthDir: Length direction at the base point.
        baseWidthDir: Width direction at the base point.
        baseNormal: Normal at the base point.
        curvePoint: The target point on the curve.
        curveTangent: The tangent vector at the curve point.
        targetSurface: Optional target surface for orientation. None = use base surface normal.
        flipFaceNormal: Whether to flip the surface normal.
        rotationAngle: Additional rotation angle around the normal axis (in radians).
        depthOffset: Depth offset along the normal direction.
        placementModeIndex: Placement mode index (0 = On Surface, 1 = On Curve).

    Returns:
        The combined transformation matrix.
    """
    targetNormal = baseNormal.copy()
    projectedSurfacePoint = None
    if targetSurface is not None:
        projectedSurfacePoint, _, _, surfaceNormal = getDataFromPointAndFace(targetSurface, curvePoint)
        if surfaceNormal is not None:
            targetNormal = surfaceNormal

    if flipFaceNormal:
        targetNormal.scaleBy(-1)

    dot = curveTangent.dotProduct(targetNormal)
    targetLengthDir = adsk.core.Vector3D.create(
        curveTangent.x - dot * targetNormal.x,
        curveTangent.y - dot * targetNormal.y,
        curveTangent.z - dot * targetNormal.z
    )

    if targetLengthDir.length < 1e-6:
        targetLengthDir = baseLengthDir.copy()
    else:
        targetLengthDir.normalize()

    targetWidthDir = targetNormal.crossProduct(targetLengthDir)
    targetWidthDir.normalize()

    if placementModeIndex == constants.patternAlongPathPlacementOnSurfaceIndex and projectedSurfacePoint is not None:
        positionPoint = projectedSurfacePoint
    else:
        positionPoint = curvePoint

    targetPoint = adsk.core.Point3D.create(
        positionPoint.x + targetNormal.x * depthOffset,
        positionPoint.y + targetNormal.y * depthOffset,
        positionPoint.z + targetNormal.z * depthOffset
    )

    baseMatrix = adsk.core.Matrix3D.create()
    baseMatrix.setWithCoordinateSystem(basePoint, baseLengthDir, baseWidthDir, baseNormal)

    baseMatrixInverse = baseMatrix.copy()
    baseMatrixInverse.invert()

    rotationMatrix = adsk.core.Matrix3D.create()
    rotationMatrix.setToRotation(rotationAngle, adsk.core.Vector3D.create(0, 0, 1), adsk.core.Point3D.create(0, 0, 0))

    targetMatrix = adsk.core.Matrix3D.create()
    targetMatrix.setWithCoordinateSystem(targetPoint, targetLengthDir, targetWidthDir, targetNormal)

    combined = baseMatrixInverse.copy()
    combined.transformBy(rotationMatrix)
    combined.transformBy(targetMatrix)

    return combined


def transformBody(body: adsk.fusion.BRepBody,
              transform: adsk.core.Matrix3D,
              previousTransform: adsk.core.Matrix3D | None = None) -> adsk.fusion.BRepBody | None:
    """Apply a placement transform to a body, optionally normalizing it first.

    Creates a temporary copy of the body. If previousTransform is provided,
    first undoes it (normalizes the body back to base position), then applies
    the new transform. This prevents transform accumulation on repeated updates.

    Args:
        body: The body to transform.
        transform: The new placement transform computed by computeTransform().
        previousTransform: The transform that was previously applied to this body.
            If provided, its inverse is applied first to normalize the body.

    Returns:
        The transformed temporary BRep body, or None if the operation fails.
    """
    try:
        temporaryBRep = adsk.fusion.TemporaryBRepManager.get()
        bodyCopy = temporaryBRep.copy(body)

        if previousTransform is not None:
            inverseTransform = previousTransform.copy()
            inverseTransform.invert()
            temporaryBRep.transform(bodyCopy, inverseTransform)

        temporaryBRep.transform(bodyCopy, transform)
        return bodyCopy
    except:
        return None


def saveTransformsToFeature(baseFeature: adsk.fusion.BaseFeature, transforms: list[adsk.core.Matrix3D]) -> None:
    """Save all placement transforms as a single JSON attribute on the base feature.

    Args:
        baseFeature: The base feature to store transforms on.
        transforms: Ordered list of transforms matching baseFeature.bodies order.
    """
    allData: list[list[float]] = []
    for transform in transforms:
        origin, xAxis, yAxis, zAxis = transform.getAsCoordinateSystem()
        allData.append([
            origin.x, origin.y, origin.z,
            xAxis.x, xAxis.y, xAxis.z,
            yAxis.x, yAxis.y, yAxis.z,
            zAxis.x, zAxis.y, zAxis.z
        ])
    baseFeature.attributes.add(strings.PREFIX, strings.APPLIED_TRANSFORM, json.dumps(allData))


def readTransformsFromFeature(baseFeature: adsk.fusion.BaseFeature) -> list[adsk.core.Matrix3D]:
    """Read all placement transforms from the base feature attribute.

    Args:
        baseFeature: The base feature to read transforms from.

    Returns:
        Ordered list of Matrix3D objects, empty list if not found or on error.
    """
    try:
        attr = baseFeature.attributes.itemByName(strings.PREFIX, strings.APPLIED_TRANSFORM)
        if attr is None:
            return []

        allData: list[list[float]] = json.loads(attr.value)
        transforms: list[adsk.core.Matrix3D] = []
        for data in allData:
            origin = adsk.core.Point3D.create(data[0], data[1], data[2])
            xAxis = adsk.core.Vector3D.create(data[3], data[4], data[5])
            yAxis = adsk.core.Vector3D.create(data[6], data[7], data[8])
            zAxis = adsk.core.Vector3D.create(data[9], data[10], data[11])
            matrix = adsk.core.Matrix3D.create()
            matrix.setWithCoordinateSystem(origin, xAxis, yAxis, zAxis)
            transforms.append(matrix)
        return transforms
    except:
        return []


def getComponentFromEntity(entity: adsk.core.Base) -> adsk.fusion.Component:
    """Get the parent component from a face, construction plane, or body entity.

    Args:
        entity: The entity to get the component from.

    Returns:
        The parent Component, or None if not found.
    """
    if entity is None:
        return None

    if entity.objectType == adsk.fusion.ConstructionPlane.classType():
        return entity.component

    if entity.objectType == adsk.fusion.BRepFace.classType():
        return entity.body.parentComponent

    if entity.objectType == adsk.fusion.BRepBody.classType():
        return entity.parentComponent

    if hasattr(entity, 'component'):
        return entity.component

    return None


def getSelectedPlacementModeIndex() -> int:
    """Get the currently selected placement mode index from the command input."""
    if _placementModeDropdownInput is None or _placementModeDropdownInput.selectedItem is None:
        return constants.patternAlongPathPlacementOnSurfaceIndex

    return _placementModeDropdownInput.selectedItem.index


def getTargetSurfaceBody() -> adsk.fusion.BRepBody | None:
    """Get the parent body of the currently selected target surface.

    Returns:
        The parent BRepBody of the target surface face, or None if not available.
    """
    if _targetSurfaceSelectionInput is None or _targetSurfaceSelectionInput.selectionCount == 0:
        return None

    entity = _targetSurfaceSelectionInput.selection(0).entity
    if entity is not None and entity.objectType == adsk.fusion.BRepFace.classType():
        return entity.body

    return None


def getPlacementModeIndexFromParameters(parameters: adsk.fusion.CustomFeatureParameters) -> int:
    """Read placement mode index from custom feature parameters with backward compatibility."""
    try:
        placementModeParam = parameters.itemById(placementModeInputDef.id)
        placementModeValue = int(placementModeParam.value)
    except:
        placementModeValue = constants.patternAlongPathPlacementOnSurfaceIndex

    if placementModeValue not in [constants.patternAlongPathPlacementOnSurfaceIndex, constants.patternAlongPathPlacementOnCurveIndex]:
        placementModeValue = constants.patternAlongPathPlacementOnSurfaceIndex

    return placementModeValue


def updateFeature(customFeature: adsk.fusion.CustomFeature) -> bool:
    """Update the bodies of an existing custom pattern feature.

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

        params = customFeature.parameters

        sourceBodies: list[adsk.fusion.BRepBody] = []
        idx = 0
        while True:
            faceDep = customFeature.dependencies.itemById(f'firstBodyFace{idx}')
            if faceDep is None:
                break
            face = adsk.fusion.BRepFace.cast(faceDep.entity)
            if face is None or face.body is None:
                break
            sourceBodies.append(face.body)
            idx += 1

        if len(sourceBodies) == 0: return False

        try:
            basePointDep = customFeature.dependencies.itemById('basePoint')
            basePointEntity = basePointDep.entity if basePointDep else None
        except:
            basePointEntity = None
        if basePointEntity is None: return False

        basePoint = getPointGeometry(basePointEntity)
        if basePoint is None: return False

        try:
            baseSurfaceDep = customFeature.dependencies.itemById('baseSurface')
            baseSurface = baseSurfaceDep.entity if baseSurfaceDep else None
        except:
            baseSurface = None
        if baseSurface is None: return False

        try:
            curveDep = customFeature.dependencies.itemById('targetCurve')
            curveEntity = curveDep.entity if curveDep else None
        except:
            curveEntity = None
        if curveEntity is None: return False

        targetSurface = None
        try:
            targetSurfaceDep = customFeature.dependencies.itemById('targetSurface')
            if targetSurfaceDep is not None:
                targetSurface = targetSurfaceDep.entity
        except:
            pass

        curveGeometry = getCurve3D(curveEntity)
        if curveGeometry is None:
            return True

        spacing = params.itemById(spacingInputDef.id).value
        startOffset = params.itemById(startOffsetInputDef.id).value
        endOffset = params.itemById(endOffsetInputDef.id).value
        startRotate = params.itemById(startRotateInputDef.id).value
        endRotate = params.itemById(endRotateInputDef.id).value
        absoluteDepthOffset = params.itemById(absoluteDepthOffsetInputDef.id).value
        relativeDepthOffset = params.itemById(relativeDepthOffsetInputDef.id).value
        placementModeIndex = getPlacementModeIndexFromParameters(params)

        try:
            flipDirection = params.itemById(flipDirectionInputDef.id).expression.lower() == 'true'
        except:
            flipDirection = False

        try:
            uniformDistribution = params.itemById(uniformDistributionInputDef.id).expression.lower() == 'true'
        except:
            uniformDistribution = False

        try:
            flipFaceNormal = params.itemById(flipFaceNormalInputDef.id).expression.lower() == 'true'
        except:
            flipFaceNormal = False

        try:
            count = int(params.itemById(countInputDef.id).value)
        except:
            count = 0

        curvePoints = calculatePointsAlongCurve(curveGeometry, spacing, startOffset, endOffset, flipDirection, uniformDistribution, count)
        if len(curvePoints) == 0: return True

        basePointOnSurface, baseLengthDir, baseWidthDir, baseNormal = getDataFromPointAndFace(baseSurface, basePoint)
        if basePointOnSurface is None: return False

        component = getComponentFromEntity(baseSurface)
        if component is None: return False

        numberOfPositions = len(curvePoints)
        totalOutputBodies = numberOfPositions * len(sourceBodies)

        baseFeature.startEdit()

        previousTransforms = readTransformsFromFeature(baseFeature)

        success = True
        outputIndex = 0
        newTransforms: list[adsk.core.Matrix3D] = []

        for posIndex, (curvePoint, curveTangent) in enumerate(curvePoints):
            normalizedT = posIndex / (numberOfPositions - 1) if numberOfPositions > 1 else 0.0
            rotationAngle = startRotate + (endRotate - startRotate) * normalizedT
            totalDepthOffset = absoluteDepthOffset + relativeDepthOffset * spacing

            transform = computeTransform(
                basePointOnSurface, baseLengthDir, baseWidthDir, baseNormal,
                curvePoint, curveTangent, targetSurface, flipFaceNormal,
                rotationAngle, totalDepthOffset, placementModeIndex
            )

            for sourceBody in sourceBodies:
                if outputIndex < baseFeature.bodies.count:
                    currentBody = baseFeature.bodies.item(outputIndex)
                    if PRESERVE_BODIES:
                        previousTransform = previousTransforms[outputIndex] if outputIndex < len(previousTransforms) else None
                        transformedCopy = transformBody(currentBody, transform, previousTransform)
                    else:
                        transformedCopy = transformBody(sourceBody, transform)
                    baseFeature.updateBody(currentBody, transformedCopy)
                else:
                    bodyCopy = transformBody(sourceBody, transform)
                    if bodyCopy is not None:
                        newBody = component.bRepBodies.add(bodyCopy, baseFeature)
                        if not _isRolledForEdit: Bodies.copyAttributes(sourceBody, newBody)

                newTransforms.append(transform)
                outputIndex += 1

        while baseFeature.bodies.count > totalOutputBodies:
            baseFeature.bodies.item(baseFeature.bodies.count - 1).deleteMe()

        saveTransformsToFeature(baseFeature, newTransforms)
        baseFeature.finishEdit()

        return success

    except:
        baseFeature.finishEdit()
        showMessage(f'updateFeature: {traceback.format_exc()}\n', True)
        return False
    
def rollBack():
    """Roll back the timeline to the state before editing."""
    global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature
    
    if _isRolledForEdit:
        _editedCustomFeature.timelineObject.rollTo(False)
        Bodies.copyBodyAttributes(_editedCustomFeature)
        _restoreTimelineObject.rollTo(False)
        _isRolledForEdit = False

    _editedCustomFeature = None