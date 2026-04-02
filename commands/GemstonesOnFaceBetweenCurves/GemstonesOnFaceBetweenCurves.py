import os
import adsk.core, adsk.fusion, traceback

from ... import strings, constants
from ...helpers.showMessage import showMessage
from ...helpers.Gemstones import createGemstone, updateGemstone, setGemstoneAttributes, updateGemstoneFeature, diamondMaterial
from ...helpers.Curves import calculatePointsAndSizesBetweenCurveChains, getCurve3D, getCurveEndpoints, canConnectToChain
from ...helpers.Surface import getClosestFace

_app: adsk.core.Application = None
_ui: adsk.core.UserInterface = None

_customFeatureDefinition: adsk.fusion.CustomFeature = None

_faceSelectionInput: adsk.core.SelectionCommandInput = None
_rail1SelectionInput: adsk.core.SelectionCommandInput = None
_rail2SelectionInput: adsk.core.SelectionCommandInput = None
_flipDirectionValueInput: adsk.core.BoolValueCommandInput = None
_uniformDistributionValueInput: adsk.core.BoolValueCommandInput = None
_snapToCornersValueInput: adsk.core.BoolValueCommandInput = None
_startOffsetValueInput: adsk.core.ValueCommandInput = None
_endOffsetValueInput: adsk.core.ValueCommandInput = None
_sizeStepValueInput: adsk.core.ValueCommandInput = None
_targetGapValueInput: adsk.core.ValueCommandInput = None
_sizeRatioValueInput: adsk.core.ValueCommandInput = None
_minStoneSizeValueInput: adsk.core.ValueCommandInput = None
_maxStoneSizeValueInput: adsk.core.ValueCommandInput = None
_flipValueInput: adsk.core.BoolValueCommandInput = None
_flipFaceNormalValueInput: adsk.core.BoolValueCommandInput = None
_absoluteDepthOffsetValueInput: adsk.core.ValueCommandInput = None
_relativeDepthOffsetValueInput: adsk.core.ValueCommandInput = None

_editedCustomFeature: adsk.fusion.CustomFeature = None
_restoreTimelineObject: adsk.fusion.TimelineObject = None
_isRolledForEdit: bool = False
_isEditActivating: bool = False

_handlers = []

createCommandInputDef = strings.InputDef(strings.GemstonesBetweenCurves.createCommandId, 'Gemstones between Curves', 'Creates gemstones between two selected curves on a face.')
editCommandInputDef = strings.InputDef(strings.GemstonesBetweenCurves.editCommandId, 'Edit Gemstones', 'Edits the parameters of existing gemstones.')

selectFaceInputDef = strings.InputDef(
    strings.GemstonesBetweenCurves.selectFaceInputId,
    'Select Faces or Planes',
    'Select one or more faces or construction planes where the gemstones will be placed.\nThe closest face to each gemstone point will be used.'
    )

selectRail1InputDef = strings.InputDef(
    strings.GemstonesBetweenCurves.selectRail1InputId,
    'Rail 1',
    'Select one or more sketch curves or edges forming the first rail chain.\nCurves must form a connected chain.'
    )

selectRail2InputDef = strings.InputDef(
    strings.GemstonesBetweenCurves.selectRail2InputId,
    'Rail 2',
    'Select one or more sketch curves or edges forming the second rail chain.\nCurves must form a connected chain.'
    )

flipDirectionInputDef = strings.InputDef(
    strings.GemstonesBetweenCurves.flipDirectionInputId,
    'Flip Direction',
    "Flip the direction of gemstone placement.\nIf checked, gemstones will start from the opposite end of the curves."
    )

uniformDistributionInputDef = strings.InputDef(
    strings.GemstonesBetweenCurves.uniformDistributionInputId,
    'Uniform Distribution',
    "Distribute gemstones uniformly along the curves.\nEnsures gemstones fill the entire available length\nfrom start offset to end offset without gaps at the ends."
    )

snapToCornersInputDef = strings.InputDef(
    strings.GemstonesBetweenCurves.snapToCornersInputId,
    'Snap to Corners',
    "Place gemstones at chain corner points.\nEnsures gemstones are positioned where curves meet at an angle.\nSmooth junctions are not treated as corners."
    )

startOffsetInputDef = strings.InputDef(
    strings.GemstonesBetweenCurves.startOffsetInputId,
    'Start Offset',
    "Offset from the start of the curve.\nDistance from the beginning of the curve to the first gemstone."
    )

endOffsetInputDef = strings.InputDef(
    strings.GemstonesBetweenCurves.endOffsetInputId,
    'End Offset',
    "Offset from the end of the curve.\nDistance from the end of the curve to the last gemstone."
    )

sizeStepInputDef = strings.InputDef(
    strings.GemstonesBetweenCurves.sizeStepInputId,
    'Size Step',
    "Size discretization step.\nGemstone sizes will be rounded to multiples of this value."
    )

targetGapInputDef = strings.InputDef(
    strings.GemstonesBetweenCurves.targetGapInputId,
    'Target Gap',
    "Target gap between gemstones.\nTarget distance between adjacent gemstones along the curve."
    )

minStoneSizeInputDef = strings.InputDef(
    strings.GemstonesBetweenCurves.minStoneSizeInputId,
    'Min Stone Size',
    "Minimum gemstone size.\nGemstone sizes will be clamped to at least this value."
    )

maxStoneSizeInputDef = strings.InputDef(
    strings.GemstonesBetweenCurves.maxStoneSizeInputId,
    'Max Stone Size',
    "Maximum gemstone size.\nGemstones larger than this value will be clamped to this size."
    )

sizeRatioInputDef = strings.InputDef(
    strings.GemstonesBetweenCurves.sizeRatioInputId,
    'Size Ratio',
    "Ratio of gemstone size to the distance between curves.\nValue from 0.5 to 2.0, where 1 means gemstone diameter equals the distance between curves."
    )

flipInputDef = strings.InputDef(
    strings.GemstonesBetweenCurves.flipInputId, 
    'Flip Gemstones', 
    "Flip gemstone orientation.\nReverses the direction the gemstone faces relative to the surface."
    )

flipFaceNormalInputDef = strings.InputDef(
    strings.GemstonesBetweenCurves.flipFaceNormalInputId,
    'Flip Face Normal',
    "Flip gemstone relative to face normal.\nRotates the gemstone 180 degrees around the face normal."
    )

absoluteDepthOffsetInputDef = strings.InputDef(
    strings.GemstonesBetweenCurves.absoluteDepthOffsetInputId, 
    'Absolute Depth Offset', 
    "Additional depth offset in absolute units.\nAdds a fixed depth to the gemstone beyond the relative offset."
    )

relativeDepthOffsetInputDef = strings.InputDef(
    strings.GemstonesBetweenCurves.relativeDepthOffsetInputId, 
    'Relative Depth Offset', 
    "Depth offset as a fraction of gemstone size.\nControls how deep the gemstone sits (0.1 = 10% of diameter)."
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
        _customFeatureDefinition = adsk.fusion.CustomFeatureDefinition.create(strings.GemstonesBetweenCurves.commandId, strings.GemstonesAtCurve.id, RESOURCES_FOLDER)
        _customFeatureDefinition.editCommandId = strings.GemstonesBetweenCurves.editCommandId

        computeCustomFeature = ComputeCustomFeature()
        _customFeatureDefinition.customFeatureCompute.add(computeCustomFeature)
        _handlers.append(computeCustomFeature)
    except:
        showMessage(f'Run failed:\n{traceback.format_exc()}', True)


def stop(panel: adsk.core.ToolbarPanel):
    """Clean up the gemstones command by removing UI elements and handlers."""
    try:
        control = panel.controls.itemById(strings.GemstonesBetweenCurves.createCommandId)
        if control:
            control.deleteMe()
            
        commandDefinition = _ui.commandDefinitions.itemById(strings.GemstonesBetweenCurves.createCommandId)
        if commandDefinition:
            commandDefinition.deleteMe()

        commandDefinition = _ui.commandDefinitions.itemById(strings.GemstonesBetweenCurves.editCommandId)
        if commandDefinition:
            commandDefinition.deleteMe()
    except:
        showMessage(f'Stop Failed:\n{traceback.format_exc()}', True)


class CreateCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Event handler for creating the command dialog for new gemstones.
    
    This handler sets up all necessary input controls including selections for face and two curves,
    value inputs for size ratio, gap, flip, and depth offset, and connects event handlers for validation,
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

            global _faceSelectionInput, _rail1SelectionInput, _rail2SelectionInput, _startOffsetValueInput, _endOffsetValueInput
            global _sizeStepValueInput, _targetGapValueInput, _minStoneSizeValueInput, _maxStoneSizeValueInput, _sizeRatioValueInput
            global _flipValueInput, _flipFaceNormalValueInput, _flipDirectionValueInput, _uniformDistributionValueInput, _snapToCornersValueInput, _absoluteDepthOffsetValueInput, _relativeDepthOffsetValueInput

            _rail1SelectionInput = inputs.addSelectionInput(selectRail1InputDef.id, selectRail1InputDef.name, selectRail1InputDef.tooltip)
            _rail1SelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchCurves)
            _rail1SelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Edges)
            _rail1SelectionInput.tooltip = selectRail1InputDef.tooltip
            _rail1SelectionInput.setSelectionLimits(1, 0)

            _rail2SelectionInput = inputs.addSelectionInput(selectRail2InputDef.id, selectRail2InputDef.name, selectRail2InputDef.tooltip)
            _rail2SelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchCurves)
            _rail2SelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Edges)
            _rail2SelectionInput.tooltip = selectRail2InputDef.tooltip
            _rail2SelectionInput.setSelectionLimits(1, 0)

            _faceSelectionInput = inputs.addSelectionInput(selectFaceInputDef.id, selectFaceInputDef.name, selectFaceInputDef.tooltip)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.ConstructionPlanes)
            _faceSelectionInput.tooltip = selectFaceInputDef.tooltip
            _faceSelectionInput.setSelectionLimits(1, 0)

            inputs.addSeparatorCommandInput('separatorAfterSecondCurve')

            flipDirection = False
            _flipDirectionValueInput = inputs.addBoolValueInput(flipDirectionInputDef.id, flipDirectionInputDef.name, True, '', flipDirection)
            _flipDirectionValueInput.tooltip = flipDirectionInputDef.tooltip

            uniformDistribution = False
            _uniformDistributionValueInput = inputs.addBoolValueInput(uniformDistributionInputDef.id, uniformDistributionInputDef.name, True, '', uniformDistribution)
            _uniformDistributionValueInput.tooltip = uniformDistributionInputDef.tooltip

            snapToCorners = False
            _snapToCornersValueInput = inputs.addBoolValueInput(snapToCornersInputDef.id, snapToCornersInputDef.name, True, '', snapToCorners)
            _snapToCornersValueInput.tooltip = snapToCornersInputDef.tooltip

            startOffset = adsk.core.ValueInput.createByReal(0.0)
            _startOffsetValueInput = inputs.addValueInput(startOffsetInputDef.id, startOffsetInputDef.name, defaultLengthUnits, startOffset)
            _startOffsetValueInput.tooltip = startOffsetInputDef.tooltip

            endOffset = adsk.core.ValueInput.createByReal(0.0)
            _endOffsetValueInput = inputs.addValueInput(endOffsetInputDef.id, endOffsetInputDef.name, defaultLengthUnits, endOffset)
            _endOffsetValueInput.tooltip = endOffsetInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterEndOffset')

            sizeRatio = adsk.core.ValueInput.createByReal(1.0)
            _sizeRatioValueInput = inputs.addValueInput(sizeRatioInputDef.id, sizeRatioInputDef.name, '', sizeRatio)
            _sizeRatioValueInput.tooltip = sizeRatioInputDef.tooltip

            sizeStep = adsk.core.ValueInput.createByReal(0.005)
            _sizeStepValueInput = inputs.addValueInput(sizeStepInputDef.id, sizeStepInputDef.name, defaultLengthUnits, sizeStep)
            _sizeStepValueInput.tooltip = sizeStepInputDef.tooltip

            targetGap = adsk.core.ValueInput.createByReal(0.01)
            _targetGapValueInput = inputs.addValueInput(targetGapInputDef.id, targetGapInputDef.name, defaultLengthUnits, targetGap)
            _targetGapValueInput.tooltip = targetGapInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterTargetGap')

            minStoneSize = adsk.core.ValueInput.createByReal(constants.defaultMinStoneSizeCm)
            _minStoneSizeValueInput = inputs.addValueInput(minStoneSizeInputDef.id, minStoneSizeInputDef.name, defaultLengthUnits, minStoneSize)
            _minStoneSizeValueInput.tooltip = minStoneSizeInputDef.tooltip

            maxStoneSize = adsk.core.ValueInput.createByReal(constants.defaultMaxStoneSizeCm)
            _maxStoneSizeValueInput = inputs.addValueInput(maxStoneSizeInputDef.id, maxStoneSizeInputDef.name, defaultLengthUnits, maxStoneSize)
            _maxStoneSizeValueInput.tooltip = maxStoneSizeInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterStoneSizeLimits')

            flip = False
            _flipValueInput = inputs.addBoolValueInput(flipInputDef.id, flipInputDef.name, True, '', flip)
            _flipValueInput.tooltip = flipInputDef.tooltip

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

            global _editedCustomFeature, _faceSelectionInput, _rail1SelectionInput, _rail2SelectionInput
            _editedCustomFeature = _ui.activeSelections.item(0).entity
            if _editedCustomFeature is None:
                return

            global _startOffsetValueInput, _endOffsetValueInput, _sizeStepValueInput, _targetGapValueInput
            global _minStoneSizeValueInput, _maxStoneSizeValueInput, _sizeRatioValueInput
            global _flipValueInput, _flipFaceNormalValueInput, _flipDirectionValueInput, _uniformDistributionValueInput, _snapToCornersValueInput
            global _absoluteDepthOffsetValueInput, _relativeDepthOffsetValueInput

            _rail1SelectionInput = inputs.addSelectionInput(selectRail1InputDef.id, selectRail1InputDef.name, selectRail1InputDef.tooltip)
            _rail1SelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchCurves)
            _rail1SelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Edges)
            _rail1SelectionInput.tooltip = selectRail1InputDef.tooltip
            _rail1SelectionInput.setSelectionLimits(1, 0)

            _rail2SelectionInput = inputs.addSelectionInput(selectRail2InputDef.id, selectRail2InputDef.name, selectRail2InputDef.tooltip)
            _rail2SelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchCurves)
            _rail2SelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Edges)
            _rail2SelectionInput.tooltip = selectRail2InputDef.tooltip
            _rail2SelectionInput.setSelectionLimits(1, 0)

            _faceSelectionInput = inputs.addSelectionInput(selectFaceInputDef.id, selectFaceInputDef.name, selectFaceInputDef.tooltip)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.ConstructionPlanes)
            _faceSelectionInput.tooltip = selectFaceInputDef.tooltip
            _faceSelectionInput.setSelectionLimits(1, 0)

            inputs.addSeparatorCommandInput('separatorAfterSecondCurve')

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
                snapToCornersParam = params.itemById(snapToCornersInputDef.id)
                snapToCorners = snapToCornersParam.expression.lower() == 'true'
            except:
                snapToCorners = False
            _snapToCornersValueInput = inputs.addBoolValueInput(snapToCornersInputDef.id, snapToCornersInputDef.name, True, '', snapToCorners)
            _snapToCornersValueInput.tooltip = snapToCornersInputDef.tooltip

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
                sizeRatioParam = params.itemById(sizeRatioInputDef.id)
                sizeRatio = adsk.core.ValueInput.createByString(sizeRatioParam.expression)
            except:
                sizeRatio = adsk.core.ValueInput.createByReal(1.0)
            _sizeRatioValueInput = inputs.addValueInput(sizeRatioInputDef.id, sizeRatioInputDef.name, '', sizeRatio)
            _sizeRatioValueInput.tooltip = sizeRatioInputDef.tooltip

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
                minStoneSizeParam = params.itemById(minStoneSizeInputDef.id)
                minStoneSize = adsk.core.ValueInput.createByString(minStoneSizeParam.expression)
            except:
                minStoneSize = adsk.core.ValueInput.createByReal(constants.defaultMinStoneSizeCm)
            _minStoneSizeValueInput = inputs.addValueInput(minStoneSizeInputDef.id, minStoneSizeInputDef.name, defaultLengthUnits, minStoneSize)
            _minStoneSizeValueInput.tooltip = minStoneSizeInputDef.tooltip

            try:
                maxStoneSizeParam = params.itemById(maxStoneSizeInputDef.id)
                maxStoneSize = adsk.core.ValueInput.createByString(maxStoneSizeParam.expression)
            except:
                maxStoneSize = adsk.core.ValueInput.createByReal(constants.defaultMaxStoneSizeCm)
            _maxStoneSizeValueInput = inputs.addValueInput(maxStoneSizeInputDef.id, maxStoneSizeInputDef.name, defaultLengthUnits, maxStoneSize)
            _maxStoneSizeValueInput.tooltip = maxStoneSizeInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterStoneSizeLimits')

            try:
                flipParam = params.itemById(flipInputDef.id)
                flip = flipParam.expression.lower() == 'true'
            except:
                flip = False
            _flipValueInput = inputs.addBoolValueInput(flipInputDef.id, flipInputDef.name, True, '', flip)
            _flipValueInput.tooltip = flipInputDef.tooltip

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
    """Event handler for controlling user selection during command execution.
    
    This handler validates geometry availability, chain connectivity for rail curves,
    and prevents the same entity from being selected in both rail inputs.
    """
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _isEditActivating
            if _isEditActivating:
                return

            eventArgs = adsk.core.SelectionEventArgs.cast(args)
            entity = eventArgs.selection.entity
            entityType = entity.objectType
        
            if entityType in [adsk.core.Plane.classType(), adsk.fusion.BRepFace.classType(), adsk.fusion.SketchCurve.classType(), adsk.fusion.BRepEdge.classType()]:
                if entity.geometry is None:
                    eventArgs.isSelectable = False
                    return

            if entityType in [adsk.fusion.SketchCurve.classType(), adsk.fusion.BRepEdge.classType(),
                              adsk.fusion.SketchLine.classType(), adsk.fusion.SketchArc.classType(),
                              adsk.fusion.SketchFittedSpline.classType(), adsk.fusion.SketchFixedSpline.classType(),
                              adsk.fusion.SketchConicCurve.classType(), adsk.fusion.SketchEllipse.classType(),
                              adsk.fusion.SketchEllipticalArc.classType(), adsk.fusion.SketchCircle.classType()]:
                activeInput = eventArgs.activeInput
                if activeInput is not None and activeInput.id in [selectRail1InputDef.id, selectRail2InputDef.id]:
                    otherInput = _rail2SelectionInput if activeInput.id == selectRail1InputDef.id else _rail1SelectionInput
                    for i in range(otherInput.selectionCount):
                        if otherInput.selection(i).entity == entity:
                            eventArgs.isSelectable = False
                            return

                    selectionInput = adsk.core.SelectionCommandInput.cast(activeInput)
                    if selectionInput is not None and selectionInput.selectionCount > 0:
                        existingEntities = [selectionInput.selection(i).entity for i in range(selectionInput.selectionCount)]
                        if not canConnectToChain(existingEntities, entity):
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

            if _faceSelectionInput.selectionCount < 1 or _rail1SelectionInput.selectionCount < 1 or _rail2SelectionInput.selectionCount < 1:
                eventArgs.areInputsValid = False
                return

            if not all( [_startOffsetValueInput.isValidExpression, _endOffsetValueInput.isValidExpression,
                         _sizeStepValueInput.isValidExpression, _targetGapValueInput.isValidExpression,
                         _sizeRatioValueInput.isValidExpression,
                         _minStoneSizeValueInput.isValidExpression, _maxStoneSizeValueInput.isValidExpression,
                         _flipValueInput.isValid, _flipFaceNormalValueInput.isValid,
                         _flipDirectionValueInput.isValid,
                         _uniformDistributionValueInput.isValid,
                         _snapToCornersValueInput.isValid,
                         _absoluteDepthOffsetValueInput.isValidExpression,
                         _relativeDepthOffsetValueInput.isValidExpression] ):
                eventArgs.areInputsValid = False
                return

            startOffset = _startOffsetValueInput.value
            endOffset = _endOffsetValueInput.value

            sizeStep = _sizeStepValueInput.value
            if sizeStep < 0 or sizeStep > 0.1:
                eventArgs.areInputsValid = False
                return
            
            targetGap = _targetGapValueInput.value
            if targetGap < 0:
                eventArgs.areInputsValid = False
                return

            sizeRatio = _sizeRatioValueInput.value
            if sizeRatio < 0.5 or sizeRatio > 2.0:
                eventArgs.areInputsValid = False
                return

            minStoneSize = _minStoneSizeValueInput.value
            maxStoneSize = _maxStoneSizeValueInput.value
            if minStoneSize < constants.minStoneSizeLimitCm or minStoneSize > constants.maxStoneSizeLimitCm:
                eventArgs.areInputsValid = False
                return
            if maxStoneSize < constants.minStoneSizeLimitCm or maxStoneSize > constants.maxStoneSizeLimitCm:
                eventArgs.areInputsValid = False
                return
            if minStoneSize > maxStoneSize:
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
            faces = getSelectedFaces(_faceSelectionInput)
            rail1Entities = [_rail1SelectionInput.selection(i).entity for i in range(_rail1SelectionInput.selectionCount)]
            rail2Entities = [_rail2SelectionInput.selection(i).entity for i in range(_rail2SelectionInput.selectionCount)]
            
            startOffset = _startOffsetValueInput.value
            endOffset = _endOffsetValueInput.value
            sizeStep = _sizeStepValueInput.value
            targetGap = _targetGapValueInput.value
            sizeRatio = _sizeRatioValueInput.value
            flip = _flipValueInput.value
            flipFaceNormal = _flipFaceNormalValueInput.value
            flipDirection = _flipDirectionValueInput.value
            uniformDistribution = _uniformDistributionValueInput.value
            absoluteDepthOffset = _absoluteDepthOffsetValueInput.value
            relativeDepthOffset = _relativeDepthOffsetValueInput.value
            minStoneSize = _minStoneSizeValueInput.value
            maxStoneSize = _maxStoneSizeValueInput.value

            snapToCorners = _snapToCornersValueInput.value

            pointsAndSizes = calculatePointsAndSizesBetweenCurveChains(rail1Entities, rail2Entities, startOffset, endOffset, sizeStep, targetGap, sizeRatio, flipDirection, uniformDistribution, snapToCorners, minStoneSize, maxStoneSize)
            if len(pointsAndSizes) == 0:
                return

            firstFace = faces[0]
            if firstFace.objectType == adsk.fusion.ConstructionPlane.classType():
                component = firstFace.component
            else:
                component = firstFace.body.parentComponent
            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()

            for point, size in pointsAndSizes:
                face = getClosestFace(faces, point)
                gemstone = createGemstone(face, point, size, flip, absoluteDepthOffset, relativeDepthOffset, flipFaceNormal)
                if gemstone is not None:
                    body = component.bRepBodies.add(gemstone, baseFeature)
                    setGemstoneAttributes(body, flip, absoluteDepthOffset, relativeDepthOffset, flipFaceNormal)
                    body.material = diamondMaterial

            baseFeature.finishEdit()
            
        except:
            baseFeature.finishEdit()
            showMessage(f'ExecutePreviewHandler: {traceback.format_exc()}\n', True)


class CreateExecuteHandler(adsk.core.CommandEventHandler):
    """Event handler for the execute event of the create command."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.CommandEventArgs.cast(args)        

            faces = getSelectedFaces(_faceSelectionInput)
            rail1Entities = [_rail1SelectionInput.selection(i).entity for i in range(_rail1SelectionInput.selectionCount)]
            rail2Entities = [_rail2SelectionInput.selection(i).entity for i in range(_rail2SelectionInput.selectionCount)]

            firstFace = faces[0]
            if firstFace.objectType == adsk.fusion.ConstructionPlane.classType():
                comp = firstFace.component
            else:
                comp = firstFace.body.parentComponent

            pointsAndSizes = calculatePointsAndSizesBetweenCurveChains(rail1Entities, rail2Entities,
                                                                   _startOffsetValueInput.value, _endOffsetValueInput.value,
                                                                   _sizeStepValueInput.value, _targetGapValueInput.value,
                                                                   _sizeRatioValueInput.value, _flipDirectionValueInput.value,
                                                                   _uniformDistributionValueInput.value, _snapToCornersValueInput.value,
                                                                   _minStoneSizeValueInput.value, _maxStoneSizeValueInput.value)
            if len(pointsAndSizes) == 0:
                eventArgs.executeFailed = True
                return

            baseFeature = comp.features.baseFeatures.add()
            baseFeature.startEdit()

            for point, size in pointsAndSizes:
                face = getClosestFace(faces, point)
                gemstone = createGemstone(face, point, size, _flipValueInput.value, _absoluteDepthOffsetValueInput.value, _relativeDepthOffsetValueInput.value, _flipFaceNormalValueInput.value)
                if gemstone is None:
                    eventArgs.executeFailed = True
                    return
                
                body = comp.bRepBodies.add(gemstone, baseFeature)
                setGemstoneAttributes(body, _flipValueInput.value, _absoluteDepthOffsetValueInput.value, _relativeDepthOffsetValueInput.value, _flipFaceNormalValueInput.value)
                body.material = diamondMaterial

            baseFeature.finishEdit()

            
            design: adsk.fusion.Design = _app.activeProduct
            defLengthUnits = design.unitsManager.defaultLengthUnits
            customFeatureInput = comp.features.customFeatures.createInput(_customFeatureDefinition)

            flipDirectionInput = adsk.core.ValueInput.createByString(str(_flipDirectionValueInput.value).lower())
            customFeatureInput.addCustomParameter(flipDirectionInputDef.id, flipDirectionInputDef.name, flipDirectionInput, '', True)

            uniformDistributionInput = adsk.core.ValueInput.createByString(str(_uniformDistributionValueInput.value).lower())
            customFeatureInput.addCustomParameter(uniformDistributionInputDef.id, uniformDistributionInputDef.name, uniformDistributionInput, '', True)

            snapToCornersInput = adsk.core.ValueInput.createByString(str(_snapToCornersValueInput.value).lower())
            customFeatureInput.addCustomParameter(snapToCornersInputDef.id, snapToCornersInputDef.name, snapToCornersInput, '', True)

            startOffsetInput = adsk.core.ValueInput.createByString(_startOffsetValueInput.expression)
            customFeatureInput.addCustomParameter(startOffsetInputDef.id, startOffsetInputDef.name, startOffsetInput,
                                              defLengthUnits, True)

            endOffsetInput = adsk.core.ValueInput.createByString(_endOffsetValueInput.expression)
            customFeatureInput.addCustomParameter(endOffsetInputDef.id, endOffsetInputDef.name, endOffsetInput,
                                              defLengthUnits, True)

            sizeStepInput = adsk.core.ValueInput.createByString(_sizeStepValueInput.expression)
            customFeatureInput.addCustomParameter(sizeStepInputDef.id, sizeStepInputDef.name, sizeStepInput,
                                              defLengthUnits, True)

            targetGapInput = adsk.core.ValueInput.createByString(_targetGapValueInput.expression)
            customFeatureInput.addCustomParameter(targetGapInputDef.id, targetGapInputDef.name, targetGapInput,
                                              defLengthUnits, True)

            sizeRatioInput = adsk.core.ValueInput.createByString(_sizeRatioValueInput.expression)
            customFeatureInput.addCustomParameter(sizeRatioInputDef.id, sizeRatioInputDef.name, sizeRatioInput,
                                              '', True)

            minStoneSizeInput = adsk.core.ValueInput.createByString(_minStoneSizeValueInput.expression)
            customFeatureInput.addCustomParameter(minStoneSizeInputDef.id, minStoneSizeInputDef.name, minStoneSizeInput,
                                              defLengthUnits, True)

            maxStoneSizeInput = adsk.core.ValueInput.createByString(_maxStoneSizeValueInput.expression)
            customFeatureInput.addCustomParameter(maxStoneSizeInputDef.id, maxStoneSizeInputDef.name, maxStoneSizeInput,
                                              defLengthUnits, True)
                         
            flipInput = adsk.core.ValueInput.createByString(str(_flipValueInput.value).lower())
            customFeatureInput.addCustomParameter(flipInputDef.id, flipInputDef.name, flipInput, '', True)

            flipFaceNormalInput = adsk.core.ValueInput.createByString(str(_flipFaceNormalValueInput.value).lower())
            customFeatureInput.addCustomParameter(flipFaceNormalInputDef.id, flipFaceNormalInputDef.name, flipFaceNormalInput, '', True)

            absoluteDepthOffsetInput = adsk.core.ValueInput.createByString(_absoluteDepthOffsetValueInput.expression)
            customFeatureInput.addCustomParameter(absoluteDepthOffsetInputDef.id, absoluteDepthOffsetInputDef.name, absoluteDepthOffsetInput,
                                              defLengthUnits, True)

            relativeDepthOffsetInput = adsk.core.ValueInput.createByString(_relativeDepthOffsetValueInput.expression)
            customFeatureInput.addCustomParameter(relativeDepthOffsetInputDef.id, relativeDepthOffsetInputDef.name, relativeDepthOffsetInput,
                                              '', True)

            for i, faceEntity in enumerate(faces):
                customFeatureInput.addDependency(f'face{i}', faceEntity)
            for i, railEntity in enumerate(rail1Entities):
                customFeatureInput.addDependency(f'rail1_{i}', railEntity)
            for i, railEntity in enumerate(rail2Entities):
                customFeatureInput.addDependency(f'rail2_{i}', railEntity)

            customFeatureInput.setStartAndEndFeatures(baseFeature, baseFeature)
            comp.features.customFeatures.add(customFeatureInput)

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
            global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature, _isEditActivating

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

            _isEditActivating = True

            rail1Entities = getRailDependencies(_editedCustomFeature, 'rail1_')
            for entity in rail1Entities:
                _rail1SelectionInput.addSelection(entity)

            rail2Entities = getRailDependencies(_editedCustomFeature, 'rail2_')
            for entity in rail2Entities:
                _rail2SelectionInput.addSelection(entity)

            faces = getFaceDependencies(_editedCustomFeature)
            for face in faces:
                _faceSelectionInput.addSelection(face)

            _isEditActivating = False
                
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

            faces = getSelectedFaces(_faceSelectionInput)
            rail1Entities = [_rail1SelectionInput.selection(i).entity for i in range(_rail1SelectionInput.selectionCount)]
            rail2Entities = [_rail2SelectionInput.selection(i).entity for i in range(_rail2SelectionInput.selectionCount)]

            _editedCustomFeature.dependencies.deleteAll()
            for i, faceEntity in enumerate(faces):
                _editedCustomFeature.dependencies.add(f'face{i}', faceEntity)
            for i, railEntity in enumerate(rail1Entities):
                _editedCustomFeature.dependencies.add(f'rail1_{i}', railEntity)
            for i, railEntity in enumerate(rail2Entities):
                _editedCustomFeature.dependencies.add(f'rail2_{i}', railEntity)

            _editedCustomFeature.parameters.itemById(flipDirectionInputDef.id).expression = str(_flipDirectionValueInput.value).lower()
            _editedCustomFeature.parameters.itemById(uniformDistributionInputDef.id).expression = str(_uniformDistributionValueInput.value).lower()
            try:
                _editedCustomFeature.parameters.itemById(snapToCornersInputDef.id).expression = str(_snapToCornersValueInput.value).lower()
            except:
                pass
            _editedCustomFeature.parameters.itemById(startOffsetInputDef.id).expression = _startOffsetValueInput.expression
            _editedCustomFeature.parameters.itemById(endOffsetInputDef.id).expression = _endOffsetValueInput.expression
            _editedCustomFeature.parameters.itemById(sizeStepInputDef.id).expression = _sizeStepValueInput.expression
            _editedCustomFeature.parameters.itemById(targetGapInputDef.id).expression = _targetGapValueInput.expression
            _editedCustomFeature.parameters.itemById(sizeRatioInputDef.id).expression = _sizeRatioValueInput.expression
            try:
                _editedCustomFeature.parameters.itemById(minStoneSizeInputDef.id).expression = _minStoneSizeValueInput.expression
            except:
                pass
            try:
                _editedCustomFeature.parameters.itemById(maxStoneSizeInputDef.id).expression = _maxStoneSizeValueInput.expression
            except:
                pass
            _editedCustomFeature.parameters.itemById(flipInputDef.id).expression = str(_flipValueInput.value).lower()
            _editedCustomFeature.parameters.itemById(absoluteDepthOffsetInputDef.id).expression = _absoluteDepthOffsetValueInput.expression
            _editedCustomFeature.parameters.itemById(relativeDepthOffsetInputDef.id).expression = _relativeDepthOffsetValueInput.expression
            
            try:
                _editedCustomFeature.parameters.itemById(flipFaceNormalInputDef.id).expression = str(_flipFaceNormalValueInput.value).lower()
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

        faces = getFaceDependencies(customFeature)
        if len(faces) == 0: return False

        rail1Entities = getRailDependencies(customFeature, 'rail1_')
        rail2Entities = getRailDependencies(customFeature, 'rail2_')
        if len(rail1Entities) == 0 or len(rail2Entities) == 0: return False

        firstFace = faces[0]
        if firstFace.objectType == adsk.fusion.ConstructionPlane.classType():
            component = firstFace.component
        else:
            component = firstFace.body.parentComponent

        try:
            flipDirection = customFeature.parameters.itemById(flipDirectionInputDef.id).expression.lower() == 'true'
        except:
            flipDirection = False

        try:
            uniformDistribution = customFeature.parameters.itemById(uniformDistributionInputDef.id).expression.lower() == 'true'
        except:
            uniformDistribution = False

        try:
            snapToCorners = customFeature.parameters.itemById(snapToCornersInputDef.id).expression.lower() == 'true'
        except:
            snapToCorners = False
        
        startOffset = customFeature.parameters.itemById(startOffsetInputDef.id).value
        endOffset = customFeature.parameters.itemById(endOffsetInputDef.id).value

        sizeStep = customFeature.parameters.itemById(sizeStepInputDef.id).value
        targetGap = customFeature.parameters.itemById(targetGapInputDef.id).value

        try:
            sizeRatio = customFeature.parameters.itemById(sizeRatioInputDef.id).value
        except:
            sizeRatio = 1.0

        try:
            minStoneSize = customFeature.parameters.itemById(minStoneSizeInputDef.id).value
        except:
            minStoneSize = 0.0

        try:
            maxStoneSize = customFeature.parameters.itemById(maxStoneSizeInputDef.id).value
        except:
            maxStoneSize = 0.0
        
        flip = customFeature.parameters.itemById(flipInputDef.id).expression.lower() == 'true'
        
        try:
            flipFaceNormal = customFeature.parameters.itemById(flipFaceNormalInputDef.id).expression.lower() == 'true'
        except:
            flipFaceNormal = False
        
        absoluteDepthOffset = customFeature.parameters.itemById(absoluteDepthOffsetInputDef.id).value
        relativeDepthOffset = customFeature.parameters.itemById(relativeDepthOffsetInputDef.id).value

        pointsAndSizes = calculatePointsAndSizesBetweenCurveChains(rail1Entities, rail2Entities, startOffset, endOffset, sizeStep, targetGap, sizeRatio, flipDirection, uniformDistribution, snapToCorners, minStoneSize, maxStoneSize)
        if len(pointsAndSizes) == 0: return False

        baseFeature.startEdit()
        
        success = True
        for i in range(len(pointsAndSizes)):
            point, size = pointsAndSizes[i]
            faceEntity = getClosestFace(faces, point)

            if i < baseFeature.bodies.count:
                currentBody = baseFeature.bodies.item(i)
                newBody = updateGemstone(currentBody, faceEntity, point, size, flip, absoluteDepthOffset, relativeDepthOffset, flipFaceNormal)
                if newBody is not None:
                    baseFeature.updateBody(currentBody, newBody)
                else:
                    success = False
            else:
                gemstone = createGemstone(faceEntity, point, size, flip, absoluteDepthOffset, relativeDepthOffset, flipFaceNormal)
                if gemstone is not None:
                    body = component.bRepBodies.add(gemstone, baseFeature)
                    body.material = diamondMaterial
                    
                    if not _isRolledForEdit: setGemstoneAttributes(body, flip, absoluteDepthOffset, relativeDepthOffset, flipFaceNormal)
                    
                else:
                    success = False

        
        while baseFeature.bodies.count > len(pointsAndSizes):
            baseFeature.bodies.item(baseFeature.bodies.count - 1).deleteMe()

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
        updateGemstoneFeature(_editedCustomFeature)
        _restoreTimelineObject.rollTo(False)
        _isRolledForEdit = False


    _editedCustomFeature = None


def getSelectedFaces(selectionInput: adsk.core.SelectionCommandInput) -> list[adsk.fusion.BRepFace]:
    """Collect all selected face entities from a selection input.

    Args:
        selectionInput: The selection command input containing faces.

    Returns:
        List of selected face entities.
    """
    return [selectionInput.selection(i).entity for i in range(selectionInput.selectionCount)]


def getFaceDependencies(customFeature: adsk.fusion.CustomFeature) -> list[adsk.fusion.BRepFace]:
    """Retrieve face dependencies from a custom feature with backward compatibility.

    Tries indexed format (face0, face1, ...) first, then falls back to single 'face' dependency.

    Args:
        customFeature: The custom feature to read dependencies from.

    Returns:
        List of face entities.
    """
    faces = []
    i = 0
    while True:
        dep = customFeature.dependencies.itemById(f'face{i}')
        if dep is None or dep.entity is None:
            break
        faces.append(dep.entity)
        i += 1

    if len(faces) == 0:
        dep = customFeature.dependencies.itemById('face')
        if dep is not None and dep.entity is not None:
            faces.append(dep.entity)

    return faces


def getRailDependencies(customFeature: adsk.fusion.CustomFeature, prefix: str) -> list:
    """Retrieve rail curve dependencies from a custom feature with backward compatibility.

    Tries indexed format (prefix0, prefix1, ...) first, then falls back to old
    'curve1'/'curve2' format for backward compatibility.

    Args:
        customFeature: The custom feature to read dependencies from.
        prefix: The dependency prefix ('rail1_' or 'rail2_').

    Returns:
        List of curve entities.
    """
    curves = []
    i = 0
    while True:
        dep = customFeature.dependencies.itemById(f'{prefix}{i}')
        if dep is None or dep.entity is None:
            break
        curves.append(dep.entity)
        i += 1

    if len(curves) == 0:
        oldKey = 'curve1' if prefix == 'rail1_' else 'curve2'
        dep = customFeature.dependencies.itemById(oldKey)
        if dep is not None and dep.entity is not None:
            curves.append(dep.entity)

    return curves