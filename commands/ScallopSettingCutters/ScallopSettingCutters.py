import math
import os
import traceback

import adsk.core
import adsk.fusion

from ... import constants

from ...helpers.Bodies import placeBody
from ...helpers.Gemstones import GemstoneInfo, extractGemstonesInfo, findValidConnections, isGemstone
from ...helpers.showMessage import showMessage


_handlers = []

_app: adsk.core.Application = None
_ui: adsk.core.UserInterface = None

_customFeatureDefinition: adsk.fusion.CustomFeature = None

_editedCustomFeature: adsk.fusion.CustomFeature = None
_restoreTimelineObject: adsk.fusion.TimelineObject = None
_isRolledForEdit: bool = False

_gemstonesSelectionInput: adsk.core.SelectionCommandInput = None

_separatorWidthValueInput: adsk.core.ValueCommandInput = None
_separatorDepthValueInput: adsk.core.ValueCommandInput = None
_scallopDiameterValueInput: adsk.core.ValueCommandInput = None
_separatorOffsetRatioValueInput: adsk.core.ValueCommandInput = None
_scallopOffsetRatioValueInput: adsk.core.ValueCommandInput = None


COMMAND = constants.ScallopSettingCutters
RESOURCES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')


class CutterBodyInfo:
    """Generated cutter body with its display name."""
    def __init__(
        self,
        body: adsk.fusion.BRepBody,
        name: str,
        position: adsk.core.Point3D = None,
        axis: adsk.core.Vector3D = None,
        normal: adsk.core.Vector3D = None,
        width: float = 0.0,
        depth: float = 0.0,
        length: float = 0.0
    ):
        self.body = body
        self.name = name
        self.position = position
        self.axis = axis
        self.normal = normal
        self.width = width
        self.depth = depth
        self.length = length


createCommandInputDef = constants.InputDef(
    COMMAND.createCommandId,
    'Create Scallop Setting Cutters',
    'Creates separator triangular cutters and scallop cylinder cutters for selected gemstones.'
    )
editCommandInputDef = constants.InputDef(
    COMMAND.editCommandId,
    'Edit Scallop Setting Cutters',
    'Edits separator triangular cutter and scallop cylinder cutter parameters.'
    )

selectGemstonesInputDef = constants.InputDef(
    COMMAND.selectGemstonesInputId,
    'Select Gemstones',
    'Select at least 2 gemstones to create scallop setting cutters.'
    )

separatorWidthInputDef = constants.InputDef(
    COMMAND.separatorWidthInputId,
    'Separator Width',
    'Width ratio of the separator triangle at table level relative to average gemstone diameter.\nFrom 0.01 to 0.50 (0.10 default).'
    )

separatorDepthInputDef = constants.InputDef(
    COMMAND.separatorDepthInputId,
    'Separator Depth',
    'Depth ratio of the separator triangle relative to average gemstone diameter.\nFrom 0.01 to 0.80 (0.20 default).'
    )

scallopDiameterInputDef = constants.InputDef(
    COMMAND.scallopDiameterInputId,
    'Scallop Diameter',
    'Diameter ratio of the large U cutters relative to gemstone diameter.\nFrom 0.20 to 0.80 (0.60 default).'
    )

separatorOffsetRatioInputDef = constants.InputDef(
    COMMAND.separatorOffsetRatioInputId,
    'Separator Offset',
    'Separator height offset from table alignment, relative to average neighboring gemstone diameter.\nFrom -0.50 to 0.50 (0.00 default).'
    )

scallopOffsetRatioInputDef = constants.InputDef(
    COMMAND.scallopOffsetRatioInputId,
    'Scallop Offset',
    'Scallop cutter height offset from table alignment, relative to gemstone diameter.\nFrom -0.50 to 0.50 (0.00 default).'
    )


def run(panel: adsk.core.ToolbarPanel):
    """Initialize the scallop setting cutters command."""
    try:
        global _app, _ui, _customFeatureDefinition
        _app = adsk.core.Application.get()
        _ui = _app.userInterface

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

        _customFeatureDefinition = adsk.fusion.CustomFeatureDefinition.create(
            COMMAND.commandId,
            COMMAND.id,
            RESOURCES_FOLDER
            )
        _customFeatureDefinition.editCommandId = COMMAND.editCommandId

        computeCustomFeature = ComputeCustomFeature()
        _customFeatureDefinition.customFeatureCompute.add(computeCustomFeature)
        _handlers.append(computeCustomFeature)
    except:
        showMessage(f'Run failed:\n{traceback.format_exc()}', True)


def stop(panel: adsk.core.ToolbarPanel):
    """Clean up the scallop setting cutters command."""
    try:
        control = panel.controls.itemById(COMMAND.createCommandId)
        if control:
            control.deleteMe()

        commandDefinition = _ui.commandDefinitions.itemById(COMMAND.createCommandId)
        if commandDefinition:
            commandDefinition.deleteMe()

        commandDefinition = _ui.commandDefinitions.itemById(COMMAND.editCommandId)
        if commandDefinition:
            commandDefinition.deleteMe()
    except:
        showMessage(f'Stop Failed:\n{traceback.format_exc()}', True)


class CreateCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Event handler for creating the command dialog for new scallop cutters."""
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            global _gemstonesSelectionInput, _separatorWidthValueInput, _separatorDepthValueInput, _scallopDiameterValueInput, _separatorOffsetRatioValueInput, _scallopOffsetRatioValueInput

            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs

            _gemstonesSelectionInput = inputs.addSelectionInput(selectGemstonesInputDef.id, selectGemstonesInputDef.name, selectGemstonesInputDef.tooltip)
            _gemstonesSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Bodies)
            _gemstonesSelectionInput.tooltip = selectGemstonesInputDef.tooltip
            _gemstonesSelectionInput.setSelectionLimits(2)

            inputs.addSeparatorCommandInput('separatorAfterGemstones')

            separatorWidth = adsk.core.ValueInput.createByReal(COMMAND.defaultSeparatorWidth)
            _separatorWidthValueInput = inputs.addValueInput(separatorWidthInputDef.id, separatorWidthInputDef.name, '', separatorWidth)
            _separatorWidthValueInput.tooltip = separatorWidthInputDef.tooltip

            separatorDepth = adsk.core.ValueInput.createByReal(COMMAND.defaultSeparatorDepth)
            _separatorDepthValueInput = inputs.addValueInput(separatorDepthInputDef.id, separatorDepthInputDef.name, '', separatorDepth)
            _separatorDepthValueInput.tooltip = separatorDepthInputDef.tooltip

            scallopDiameter = adsk.core.ValueInput.createByReal(COMMAND.defaultScallopDiameter)
            _scallopDiameterValueInput = inputs.addValueInput(scallopDiameterInputDef.id, scallopDiameterInputDef.name, '', scallopDiameter)
            _scallopDiameterValueInput.tooltip = scallopDiameterInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterRatios')

            separatorOffsetRatio = adsk.core.ValueInput.createByReal(COMMAND.defaultSeparatorOffsetRatio)
            _separatorOffsetRatioValueInput = inputs.addValueInput(separatorOffsetRatioInputDef.id, separatorOffsetRatioInputDef.name, '', separatorOffsetRatio)
            _separatorOffsetRatioValueInput.tooltip = separatorOffsetRatioInputDef.tooltip

            scallopOffsetRatio = adsk.core.ValueInput.createByReal(COMMAND.defaultScallopOffsetRatio)
            _scallopOffsetRatioValueInput = inputs.addValueInput(scallopOffsetRatioInputDef.id, scallopOffsetRatioInputDef.name, '', scallopOffsetRatio)
            _scallopOffsetRatioValueInput.tooltip = scallopOffsetRatioInputDef.tooltip

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
    """Event handler for creating the command dialog for editing scallop cutters."""
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            global _editedCustomFeature, _gemstonesSelectionInput, _separatorWidthValueInput, _separatorDepthValueInput, _scallopDiameterValueInput, _separatorOffsetRatioValueInput, _scallopOffsetRatioValueInput

            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs

            _editedCustomFeature = _ui.activeSelections.item(0).entity
            if _editedCustomFeature is None:
                return

            _gemstonesSelectionInput = inputs.addSelectionInput(selectGemstonesInputDef.id, selectGemstonesInputDef.name, selectGemstonesInputDef.tooltip)
            _gemstonesSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Bodies)
            _gemstonesSelectionInput.tooltip = selectGemstonesInputDef.tooltip
            _gemstonesSelectionInput.setSelectionLimits(2)

            inputs.addSeparatorCommandInput('separatorAfterGemstones')

            parameters = _editedCustomFeature.parameters

            separatorWidth = adsk.core.ValueInput.createByString(parameters.itemById(separatorWidthInputDef.id).expression)
            _separatorWidthValueInput = inputs.addValueInput(separatorWidthInputDef.id, separatorWidthInputDef.name, '', separatorWidth)
            _separatorWidthValueInput.tooltip = separatorWidthInputDef.tooltip

            separatorDepth = adsk.core.ValueInput.createByString(parameters.itemById(separatorDepthInputDef.id).expression)
            _separatorDepthValueInput = inputs.addValueInput(separatorDepthInputDef.id, separatorDepthInputDef.name, '', separatorDepth)
            _separatorDepthValueInput.tooltip = separatorDepthInputDef.tooltip

            scallopDiameter = adsk.core.ValueInput.createByString(parameters.itemById(scallopDiameterInputDef.id).expression)
            _scallopDiameterValueInput = inputs.addValueInput(scallopDiameterInputDef.id, scallopDiameterInputDef.name, '', scallopDiameter)
            _scallopDiameterValueInput.tooltip = scallopDiameterInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterRatios')

            separatorOffsetRatio = adsk.core.ValueInput.createByString(parameters.itemById(separatorOffsetRatioInputDef.id).expression)
            _separatorOffsetRatioValueInput = inputs.addValueInput(separatorOffsetRatioInputDef.id, separatorOffsetRatioInputDef.name, '', separatorOffsetRatio)
            _separatorOffsetRatioValueInput.tooltip = separatorOffsetRatioInputDef.tooltip

            scallopOffsetRatio = adsk.core.ValueInput.createByString(parameters.itemById(scallopOffsetRatioInputDef.id).expression)
            _scallopOffsetRatioValueInput = inputs.addValueInput(scallopOffsetRatioInputDef.id, scallopOffsetRatioInputDef.name, '', scallopOffsetRatio)
            _scallopOffsetRatioValueInput.tooltip = scallopOffsetRatioInputDef.tooltip

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
            type = entity.objectType

            if type == adsk.fusion.BRepBody.classType():
                preSelectBody: adsk.fusion.BRepBody = entity

                if preSelectBody.assemblyContext:
                    occurrence = preSelectBody.assemblyContext
                    if occurrence.isReferencedComponent:
                        eventArgs.isSelectable = False
                        return

                if not isGemstone(preSelectBody):
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

            if _gemstonesSelectionInput.selectionCount < 2:
                eventArgs.areInputsValid = False
                return

            for i in range(_gemstonesSelectionInput.selectionCount):
                body = _gemstonesSelectionInput.selection(i)

                if not body.isValid:
                    eventArgs.areInputsValid = False
                    return

            if not isValueInRange(_separatorWidthValueInput, COMMAND.minSeparatorWidth, COMMAND.maxSeparatorWidth):
                eventArgs.areInputsValid = False
                return

            if not isValueInRange(_separatorDepthValueInput, COMMAND.minSeparatorDepth, COMMAND.maxSeparatorDepth):
                eventArgs.areInputsValid = False
                return

            if not isValueInRange(_scallopDiameterValueInput, COMMAND.minScallopDiameter, COMMAND.maxScallopDiameter):
                eventArgs.areInputsValid = False
                return

            if not isValueInRange(_separatorOffsetRatioValueInput, COMMAND.minOffsetRatio, COMMAND.maxOffsetRatio):
                eventArgs.areInputsValid = False
                return

            if not isValueInRange(_scallopOffsetRatioValueInput, COMMAND.minOffsetRatio, COMMAND.maxOffsetRatio):
                eventArgs.areInputsValid = False
                return

        except:
            showMessage(f'ValidateInputsHandler: {traceback.format_exc()}\n', True)


def isValueInRange(valueInput: adsk.core.ValueCommandInput, minValue: float, maxValue: float) -> bool:
    return valueInput.isValidExpression and minValue <= valueInput.value <= maxValue


class ExecutePreviewHandler(adsk.core.CommandEventHandler):
    """Event handler for the executePreview event."""
    def __init__(self):
        super().__init__()

    def notify(self, args):
        baseFeature = None
        try:
            gemstones = getSelectedGemstones()
            if not gemstones:
                return

            cutters = createBodies(
                gemstones,
                _separatorWidthValueInput.value,
                _separatorDepthValueInput.value,
                _scallopDiameterValueInput.value,
                _separatorOffsetRatioValueInput.value,
                _scallopOffsetRatioValueInput.value
                )
            if not cutters:
                return

            component = gemstones[0].parentComponent

            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()
            for cutterInfo in cutters:
                body = component.bRepBodies.add(cutterInfo.body, baseFeature)
                handleNewBody(body, cutterInfo.name)
            baseFeature.finishEdit()

        except:
            if baseFeature is not None:
                baseFeature.finishEdit()
            showMessage(f'ExecutePreviewHandler: {traceback.format_exc()}\n', True)


class CreateExecuteHandler(adsk.core.CommandEventHandler):
    """Event handler for the execute event of the create command."""
    def __init__(self):
        super().__init__()

    def notify(self, args):
        baseFeature = None
        eventArgs = None
        try:
            eventArgs = adsk.core.CommandEventArgs.cast(args)

            gemstones = getSelectedGemstones()
            if not gemstones:
                eventArgs.executeFailed = True
                showMessage('Please select at least 2 gemstones.\n', True)
                return

            cutters = createBodies(
                gemstones,
                _separatorWidthValueInput.value,
                _separatorDepthValueInput.value,
                _scallopDiameterValueInput.value,
                _separatorOffsetRatioValueInput.value,
                _scallopOffsetRatioValueInput.value
                )
            if not cutters:
                eventArgs.executeFailed = True
                showMessage('Failed to create scallop setting cutters.\n', True)
                return

            component = gemstones[0].parentComponent
            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()
            for cutterInfo in cutters:
                body = component.bRepBodies.add(cutterInfo.body, baseFeature)
                handleNewBody(body, cutterInfo.name)
            baseFeature.finishEdit()

            customFeatureInput = component.features.customFeatures.createInput(_customFeatureDefinition)

            for i in range(len(gemstones)):
                gemstone = gemstones[i]

                if gemstone.faces.count == 0:
                    eventArgs.executeFailed = True
                    return
                firstGemstoneFace = gemstone.faces[0]
                customFeatureInput.addDependency(f'firstGemstoneFace{i}', firstGemstoneFace)

            separatorWidth = adsk.core.ValueInput.createByString(_separatorWidthValueInput.expression)
            customFeatureInput.addCustomParameter(separatorWidthInputDef.id, separatorWidthInputDef.name, separatorWidth, '', True)

            separatorDepth = adsk.core.ValueInput.createByString(_separatorDepthValueInput.expression)
            customFeatureInput.addCustomParameter(separatorDepthInputDef.id, separatorDepthInputDef.name, separatorDepth, '', True)

            scallopDiameter = adsk.core.ValueInput.createByString(_scallopDiameterValueInput.expression)
            customFeatureInput.addCustomParameter(scallopDiameterInputDef.id, scallopDiameterInputDef.name, scallopDiameter, '', True)

            separatorOffsetRatio = adsk.core.ValueInput.createByString(_separatorOffsetRatioValueInput.expression)
            customFeatureInput.addCustomParameter(separatorOffsetRatioInputDef.id, separatorOffsetRatioInputDef.name, separatorOffsetRatio, '', True)

            scallopOffsetRatio = adsk.core.ValueInput.createByString(_scallopOffsetRatioValueInput.expression)
            customFeatureInput.addCustomParameter(scallopOffsetRatioInputDef.id, scallopOffsetRatioInputDef.name, scallopOffsetRatio, '', True)

            customFeatureInput.setStartAndEndFeatures(baseFeature, baseFeature)
            component.features.customFeatures.add(customFeatureInput)

        except:
            if baseFeature is not None:
                baseFeature.finishEdit()
            if eventArgs is not None:
                eventArgs.executeFailed = True
            showMessage(f'CreateExecuteHandler: {traceback.format_exc()}\n', True)


class EditActivateHandler(adsk.core.CommandEventHandler):
    """Event handler for the activation of the edit command."""
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature, _gemstonesSelectionInput

            eventArgs = adsk.core.CommandEventArgs.cast(args)

            if _isRolledForEdit:
                return

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
                dependency = _editedCustomFeature.dependencies.itemById(f'firstGemstoneFace{i}')
                if dependency is None:
                    break
                firstGemstoneFace = dependency.entity
                if firstGemstoneFace is not None and firstGemstoneFace.body is not None:
                    _gemstonesSelectionInput.addSelection(firstGemstoneFace.body)
                i += 1

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
        global _editedCustomFeature

        eventArgs = None
        try:
            eventArgs = adsk.core.CommandEventArgs.cast(args)

            gemstoneEntities = getSelectedGemstones()
            if not gemstoneEntities:
                eventArgs.executeFailed = True
                showMessage('Please select at least 2 gemstones.\n', True)
                return

            _editedCustomFeature.dependencies.deleteAll()

            for i in range(len(gemstoneEntities)):
                gemstone = gemstoneEntities[i]

                if gemstone.faces.count == 0:
                    eventArgs.executeFailed = True
                    return
                firstGemstoneFace = gemstone.faces[0]
                _editedCustomFeature.dependencies.add(f'firstGemstoneFace{i}', firstGemstoneFace)

            _editedCustomFeature.parameters.itemById(separatorWidthInputDef.id).expression = _separatorWidthValueInput.expression
            _editedCustomFeature.parameters.itemById(separatorDepthInputDef.id).expression = _separatorDepthValueInput.expression
            _editedCustomFeature.parameters.itemById(scallopDiameterInputDef.id).expression = _scallopDiameterValueInput.expression
            _editedCustomFeature.parameters.itemById(separatorOffsetRatioInputDef.id).expression = _separatorOffsetRatioValueInput.expression
            _editedCustomFeature.parameters.itemById(scallopOffsetRatioInputDef.id).expression = _scallopOffsetRatioValueInput.expression

        except:
            showMessage(f'EditExecuteHandler: {traceback.format_exc()}\n', True)

        finally:
            rollBack()


class ComputeCustomFeature(adsk.fusion.CustomFeatureEventHandler):
    """Event handler for the recomputation of the custom feature."""
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            eventArgs = adsk.fusion.CustomFeatureEventArgs.cast(args)
            customFeature = eventArgs.customFeature
            updateFeature(customFeature)

        except:
            showMessage(f'ComputeCustomFeature: {traceback.format_exc()}\n', True)


def createBodies(gemstones: list[adsk.fusion.BRepBody], separatorWidth: float, separatorDepth: float, scallopDiameter: float, separatorOffsetRatio: float, scallopOffsetRatio: float, includeBodies: bool = True) -> list[CutterBodyInfo] | None:
    """Create separator triangle cutters and scallop cylinder cutters for nearby gemstones."""
    try:
        if not gemstones or len(gemstones) < 2:
            return None

        gemstoneInfos = extractGemstonesInfo(gemstones)
        if gemstoneInfos is None or len(gemstoneInfos) < 2:
            return None

        connections = findValidConnections(gemstoneInfos, COMMAND.defaultConnectionGap)
        if not connections:
            return None

        cutters: list[CutterBodyInfo] = []

        for info1, info2 in connections:
            cutterInfo = createSeparatorCutterInfo(info1, info2, separatorWidth, separatorDepth, separatorOffsetRatio, includeBodies)
            if cutterInfo is not None:
                cutters.append(cutterInfo)

        neighborMap = createNeighborMap(gemstoneInfos, connections)
        for info in gemstoneInfos:
            cutterInfo = createScallopCutterInfo(info, gemstoneInfos, neighborMap, scallopDiameter, scallopOffsetRatio, includeBodies)
            if cutterInfo is not None:
                cutters.append(cutterInfo)

        return cutters if len(cutters) > 0 else None

    except:
        showMessage(f'createBodies: {traceback.format_exc()}\n', True)
        return None


def createSeparatorCutterInfo(info1: GemstoneInfo, info2: GemstoneInfo, separatorWidth: float, separatorDepth: float, separatorOffsetRatio: float, includeBody: bool = True) -> CutterBodyInfo | None:
    """Create separator cutter data exactly between two gemstone girdles."""
    try:
        normal = averageNormal(info1, info2)
        if normal is None:
            return None

        tangent = tangentBetween(info1, info2, normal)
        if tangent is None:
            return None

        cutterAxis = cutterAxisFromTangent(tangent, normal)
        if cutterAxis is None:
            return None

        firstGirdlePoint = pointAlongVector(info1.centroid, tangent, info1.radius)
        secondGirdlePoint = pointAlongVector(info2.centroid, tangent, -info2.radius)
        position = midpoint(firstGirdlePoint, secondGirdlePoint)

        avgDiameter = info1.radius + info2.radius
        position = tableAlignedPoint(position, normal, [info1, info2], avgDiameter, separatorOffsetRatio)

        width = avgDiameter * separatorWidth
        depth = avgDiameter * separatorDepth
        length = avgDiameter * COMMAND.cutterWidthRatio

        cutter = createTrianglePrismCutter(position, cutterAxis, normal, width, depth, length) if includeBody else None
        if includeBody and cutter is None:
            return None

        return CutterBodyInfo(cutter, COMMAND.separatorCutterName, position, cutterAxis, normal, width, depth, length)

    except:
        showMessage(f'createSeparatorCutterInfo: {traceback.format_exc()}\n', True)
        return None


def createScallopCutterInfo(info: GemstoneInfo, gemstoneInfos: list[GemstoneInfo], neighborMap: dict[int, list[GemstoneInfo]], scallopDiameter: float, scallopOffsetRatio: float, includeBody: bool = True) -> CutterBodyInfo | None:
    """Create scallop cutter data centered on one gemstone."""
    try:
        normal = info.getNormalizedNormal()
        if normal is None:
            return None
        normal.normalize()

        tangent = tangentForGemstone(info, gemstoneInfos, neighborMap, normal)
        if tangent is None:
            return None

        cutterAxis = cutterAxisFromTangent(tangent, normal)
        if cutterAxis is None:
            return None

        position = tableAlignedPoint(info.centroid.copy(), normal, [info], info.diameter, scallopOffsetRatio)

        diameter = info.diameter * scallopDiameter
        length = info.diameter * COMMAND.cutterWidthRatio

        cutter = createCylinderCutter(position, cutterAxis, normal, diameter, length) if includeBody else None
        if includeBody and cutter is None:
            return None

        return CutterBodyInfo(cutter, COMMAND.scallopCutterName, position, cutterAxis, normal, diameter, diameter, length)

    except:
        showMessage(f'createScallopCutterInfo: {traceback.format_exc()}\n', True)
        return None


def createCylinderCutter(position: adsk.core.Point3D, axis: adsk.core.Vector3D, normal: adsk.core.Vector3D, diameter: float, length: float) -> adsk.fusion.BRepBody | None:
    """Create a cylinder at the origin and place it into the requested coordinate system."""
    try:
        if diameter <= 0 or length <= 0:
            return None

        axis = normalized(axis)
        normal = normalized(normal)
        if axis is None or normal is None:
            return None

        widthDirection = normal.crossProduct(axis)
        widthDirection = normalized(widthDirection)
        if widthDirection is None:
            return None

        cutter = createCylinderAtOrigin(diameter, length)
        if cutter is None:
            return None

        placeBody(cutter, position, axis, widthDirection, normal)

        return cutter

    except:
        showMessage(f'createCylinderCutter: {traceback.format_exc()}\n', True)
        return None


def createCylinderAtOrigin(diameter: float, length: float) -> adsk.fusion.BRepBody | None:
    """Create a cylinder on local X axis centered at origin."""
    try:
        if diameter <= 0 or length <= 0:
            return None

        temporaryBRep: adsk.fusion.TemporaryBRepManager = adsk.fusion.TemporaryBRepManager.get()
        radius = diameter * 0.5
        halfLength = length * 0.5
        startPoint = adsk.core.Point3D.create(-halfLength, 0, 0)
        endPoint = adsk.core.Point3D.create(halfLength, 0, 0)
        return temporaryBRep.createCylinderOrCone(startPoint, radius, endPoint, radius)

    except:
        showMessage(f'createCylinderAtOrigin: {traceback.format_exc()}\n', True)
        return None


def createTrianglePrismCutter(position: adsk.core.Point3D, axis: adsk.core.Vector3D, normal: adsk.core.Vector3D, width: float, depth: float, length: float) -> adsk.fusion.BRepBody | None:
    """Create a triangular prism with its base up and tip down."""
    try:
        if width <= 0 or depth <= 0 or length <= 0:
            return None

        axis = normalized(axis)
        normal = normalized(normal)
        if axis is None or normal is None:
            return None

        widthDirection = normal.crossProduct(axis)
        widthDirection = normalized(widthDirection)
        if widthDirection is None:
            return None

        prism = createTrianglePrismAtOrigin(width, depth, length)
        if prism is None:
            return None

        placeBody(prism, position, axis, widthDirection, normal)

        return prism

    except:
        showMessage(f'createTrianglePrismCutter: {traceback.format_exc()}\n', True)
        return None


def createTrianglePrismAtOrigin(widthAtTable: float, depth: float, length: float) -> adsk.fusion.BRepBody | None:
    """Create a local triangular prism from the SAT asset."""
    try:
        temporaryBRep: adsk.fusion.TemporaryBRepManager = adsk.fusion.TemporaryBRepManager.get()
        prism = temporaryBRep.createFromFile(COMMAND.prismAssetFile).item(0)
        normalizedPrism, sourceWidth, sourceDepth, sourceLength = normalizeTrianglePrismBody(prism)
        if normalizedPrism is None:
            return None
        if sourceWidth <= COMMAND.minVectorLength or sourceDepth <= COMMAND.minVectorLength or sourceLength <= COMMAND.minVectorLength:
            return None

        if not scaleLocalBody(normalizedPrism, length / sourceLength, widthAtTable / sourceWidth, depth / sourceDepth):
            return None

        return normalizedPrism

    except:
        showMessage(f'createTrianglePrismAtOrigin: {traceback.format_exc()}\n', True)
        return None


def normalizeTrianglePrismBody(body: adsk.fusion.BRepBody) -> tuple[adsk.fusion.BRepBody, float, float, float] | tuple[None, None, None, None]:
    """Normalize a triangular prism so table center is at origin and tip points down."""
    try:
        if body is None:
            return None, None, None, None

        temporaryBRep: adsk.fusion.TemporaryBRepManager = adsk.fusion.TemporaryBRepManager.get()
        tempBody = temporaryBRep.copy(body)

        triangularFaces = []
        for face in tempBody.faces:
            try:
                if face.edges.count == 3:
                    triangularFaces.append(face)
            except:
                continue

        if len(triangularFaces) < 2:
            return None, None, None, None

        triFace1 = triangularFaces[0]
        triFace2 = triangularFaces[1]
        lengthDirection = vectorBetween(triFace1.centroid, triFace2.centroid)
        sourceLength = lengthDirection.length
        lengthDirection = normalized(lengthDirection)
        if lengthDirection is None or sourceLength <= COMMAND.minVectorLength:
            return None, None, None, None

        vertices = []
        for vertex in triFace1.vertices:
            vertices.append(vertex.geometry)
        if len(vertices) != 3:
            return None, None, None, None

        baseStart, baseEnd, tip = findTriangleBaseAndTip(vertices)
        if baseStart is None:
            return None, None, None, None

        baseCenter = midpoint(baseStart, baseEnd)
        widthDirection = vectorBetween(baseStart, baseEnd)
        baseWidth = widthDirection.length
        widthDirection = normalized(widthDirection)

        normal = vectorBetween(tip, baseCenter)
        prismHeight = normal.length
        normal = normalized(normal)
        if widthDirection is None or normal is None or baseWidth <= COMMAND.minVectorLength or prismHeight <= COMMAND.minVectorLength:
            return None, None, None, None

        if lengthDirection.crossProduct(widthDirection).dotProduct(normal) < 0:
            widthDirection.scaleBy(-1)

        sourceDepth = prismHeight * (2.0 / 3.0)
        sourceWidthAtTable = baseWidth * (2.0 / 3.0)
        originPoint = tip.copy()
        originOffset = normal.copy()
        originOffset.scaleBy(sourceDepth)
        originPoint.translateBy(originOffset)
        lengthOffset = lengthDirection.copy()
        lengthOffset.scaleBy(sourceLength * 0.5)
        originPoint.translateBy(lengthOffset)

        transformation = adsk.core.Matrix3D.create()
        transformation.setToAlignCoordinateSystems(
            originPoint, lengthDirection, widthDirection, normal,
            constants.zeroPoint, constants.xVector, constants.yVector, constants.zVector
            )
        temporaryBRep.transform(tempBody, transformation)

        return tempBody, sourceWidthAtTable, sourceDepth, sourceLength

    except:
        showMessage(f'normalizeTrianglePrismBody: {traceback.format_exc()}\n', True)
        return None, None, None, None


def findTriangleBaseAndTip(vertices: list[adsk.core.Point3D]) -> tuple[adsk.core.Point3D, adsk.core.Point3D, adsk.core.Point3D] | tuple[None, None, None]:
    """Find the triangle base edge and opposite tip."""
    try:
        best = None
        for i in range(3):
            startPoint = vertices[i]
            endPoint = vertices[(i + 1) % 3]
            tipPoint = vertices[(i + 2) % 3]
            edge = vectorBetween(startPoint, endPoint)
            edge = normalized(edge)
            if edge is None:
                continue

            baseCenter = midpoint(startPoint, endPoint)
            depthVector = vectorBetween(tipPoint, baseCenter)
            depthVector = normalized(depthVector)
            if depthVector is None:
                continue

            perpendicularScore = abs(edge.dotProduct(depthVector))
            if best is None or perpendicularScore < best[0]:
                best = (perpendicularScore, startPoint, endPoint, tipPoint)

        if best is None:
            return None, None, None

        return best[1], best[2], best[3]

    except:
        showMessage(f'findTriangleBaseAndTip: {traceback.format_exc()}\n', True)
        return None, None, None


def updateCutterBodyFromInfo(body: adsk.fusion.BRepBody, cutterInfo: CutterBodyInfo) -> adsk.fusion.BRepBody | None:
    """Update an existing cutter body by normalizing, scaling, and placing it."""
    if cutterInfo.name == COMMAND.separatorCutterName:
        return updateTrianglePrismFromInfo(body, cutterInfo)

    if cutterInfo.name == COMMAND.scallopCutterName:
        return updateCylinderCutterFromInfo(body, cutterInfo)

    return None


def createFreshCutterBodyFromInfo(cutterInfo: CutterBodyInfo) -> adsk.fusion.BRepBody | None:
    """Create a fresh cutter body only when no existing body can be updated."""
    try:
        if cutterInfo.body is not None:
            return cutterInfo.body

        if cutterInfo.name == COMMAND.separatorCutterName:
            return createTrianglePrismCutter(
                cutterInfo.position,
                cutterInfo.axis,
                cutterInfo.normal,
                cutterInfo.width,
                cutterInfo.depth,
                cutterInfo.length
                )

        if cutterInfo.name == COMMAND.scallopCutterName:
            return createCylinderCutter(
                cutterInfo.position,
                cutterInfo.axis,
                cutterInfo.normal,
                cutterInfo.width,
                cutterInfo.length
                )

        return None

    except:
        showMessage(f'createFreshCutterBodyFromInfo: {traceback.format_exc()}\n', True)
        return None


def updateTrianglePrismFromInfo(body: adsk.fusion.BRepBody, cutterInfo: CutterBodyInfo) -> adsk.fusion.BRepBody | None:
    """Update an existing triangular prism cutter using the existing body as source."""
    try:
        tempBody, sourceWidth, sourceDepth, sourceLength = normalizeTrianglePrismBody(body)
        if tempBody is None:
            tempBody = createTrianglePrismAtOrigin(cutterInfo.width, cutterInfo.depth, cutterInfo.length)
            if tempBody is None:
                return None
        else:
            if not scaleLocalBody(tempBody, cutterInfo.length / sourceLength, cutterInfo.width / sourceWidth, cutterInfo.depth / sourceDepth):
                return None

        if not placeCutterBody(tempBody, cutterInfo):
            return None

        return tempBody

    except:
        showMessage(f'updateTrianglePrismFromInfo: {traceback.format_exc()}\n', True)
        return None


def updateCylinderCutterFromInfo(body: adsk.fusion.BRepBody, cutterInfo: CutterBodyInfo) -> adsk.fusion.BRepBody | None:
    """Update an existing cylinder cutter using the existing body as source."""
    try:
        tempBody, sourceDiameter, sourceLength = normalizeCylinderCutterBody(body)
        if tempBody is None:
            tempBody = createCylinderAtOrigin(cutterInfo.width, cutterInfo.length)
            if tempBody is None:
                return None
        else:
            if not scaleLocalBody(tempBody, cutterInfo.length / sourceLength, cutterInfo.width / sourceDiameter, cutterInfo.width / sourceDiameter):
                return None

        if not placeCutterBody(tempBody, cutterInfo):
            return None

        return tempBody

    except:
        showMessage(f'updateCylinderCutterFromInfo: {traceback.format_exc()}\n', True)
        return None


def normalizeCylinderCutterBody(body: adsk.fusion.BRepBody) -> tuple[adsk.fusion.BRepBody, float, float] | tuple[None, None, None]:
    """Normalize a cylinder cutter so its axis is local X and centroid is origin."""
    try:
        if body is None:
            return None, None, None

        temporaryBRep: adsk.fusion.TemporaryBRepManager = adsk.fusion.TemporaryBRepManager.get()
        tempBody = temporaryBRep.copy(body)

        cylindricalFaces = []
        planarFaces = []
        for face in tempBody.faces:
            surfaceType = face.geometry.surfaceType
            if surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType:
                cylindricalFaces.append(face)
            elif surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
                planarFaces.append(face)

        if not cylindricalFaces:
            return None, None, None

        cylindricalFace = cylindricalFaces[0]
        cylinder = adsk.core.Cylinder.cast(cylindricalFace.geometry)
        originPoint = cylindricalFace.centroid
        lengthDirection = normalized(cylinder.axis)
        if lengthDirection is None:
            return None, None, None

        widthDirection = perpendicularVector(lengthDirection)
        normal = lengthDirection.crossProduct(widthDirection)
        normal = normalized(normal)
        if widthDirection is None or normal is None:
            return None, None, None

        transformation = adsk.core.Matrix3D.create()
        transformation.setToAlignCoordinateSystems(
            originPoint, lengthDirection, widthDirection, normal,
            constants.zeroPoint, constants.xVector, constants.yVector, constants.zVector
            )
        temporaryBRep.transform(tempBody, transformation)

        bbox = tempBody.boundingBox
        sourceLength = bbox.maxPoint.x - bbox.minPoint.x
        if len(planarFaces) >= 2:
            try:
                sourceLength = planarFaces[0].centroid.distanceTo(planarFaces[1].centroid)
            except:
                pass

        sourceDiameter = cylinder.radius * 2
        if sourceLength <= COMMAND.minVectorLength or sourceDiameter <= COMMAND.minVectorLength:
            return None, None, None

        return tempBody, sourceDiameter, sourceLength

    except:
        showMessage(f'normalizeCylinderCutterBody: {traceback.format_exc()}\n', True)
        return None, None, None


def scaleLocalBody(body: adsk.fusion.BRepBody, xScale: float, yScale: float, zScale: float) -> bool:
    """Scale a normalized body around origin."""
    try:
        if body is None:
            return False

        temporaryBRep: adsk.fusion.TemporaryBRepManager = adsk.fusion.TemporaryBRepManager.get()
        transformation = adsk.core.Matrix3D.create()
        transformation.setToAlignCoordinateSystems(
            constants.zeroPoint, constants.xVector, constants.yVector, constants.zVector,
            constants.zeroPoint,
            adsk.core.Vector3D.create(xScale, 0, 0),
            adsk.core.Vector3D.create(0, yScale, 0),
            adsk.core.Vector3D.create(0, 0, zScale)
            )
        temporaryBRep.transform(body, transformation)
        return True

    except:
        showMessage(f'scaleLocalBody: {traceback.format_exc()}\n', True)
        return False


def placeCutterBody(body: adsk.fusion.BRepBody, cutterInfo: CutterBodyInfo) -> bool:
    """Place a normalized cutter body using CutterBodyInfo orientation."""
    try:
        axis = normalized(cutterInfo.axis)
        normal = normalized(cutterInfo.normal)
        if axis is None or normal is None:
            return False

        widthDirection = normal.crossProduct(axis)
        widthDirection = normalized(widthDirection)
        if widthDirection is None:
            return False

        placeBody(body, cutterInfo.position, axis, widthDirection, normal)
        return True

    except:
        showMessage(f'placeCutterBody: {traceback.format_exc()}\n', True)
        return False


def perpendicularVector(vector: adsk.core.Vector3D) -> adsk.core.Vector3D | None:
    """Create a stable vector perpendicular to the provided vector."""
    try:
        candidate = constants.zVector
        if abs(vector.dotProduct(candidate)) > 0.9:
            candidate = constants.yVector

        perpendicular = vector.crossProduct(candidate)
        return normalized(perpendicular)

    except:
        showMessage(f'perpendicularVector: {traceback.format_exc()}\n', True)
        return None


def updateFeature(customFeature: adsk.fusion.CustomFeature) -> bool:
    """Update the bodies of an existing custom scallop cutters feature."""
    baseFeature = None
    try:
        for feature in customFeature.features:
            if feature.objectType == adsk.fusion.BaseFeature.classType():
                baseFeature = feature
        if baseFeature is None:
            return False

        firstGemstoneFaces: list[adsk.fusion.BRepFace] = []
        i = 0
        while True:
            dependency = customFeature.dependencies.itemById(f'firstGemstoneFace{i}')
            if dependency is None:
                break
            firstGemstoneFace = dependency.entity
            if firstGemstoneFace is None:
                break
            firstGemstoneFaces.append(firstGemstoneFace)
            i += 1
        if len(firstGemstoneFaces) < 2:
            return False

        gemstones: list[adsk.fusion.BRepBody] = [face.body for face in firstGemstoneFaces]

        separatorWidth = customFeature.parameters.itemById(separatorWidthInputDef.id).value
        separatorDepth = customFeature.parameters.itemById(separatorDepthInputDef.id).value
        scallopDiameter = customFeature.parameters.itemById(scallopDiameterInputDef.id).value
        separatorOffsetRatio = customFeature.parameters.itemById(separatorOffsetRatioInputDef.id).value
        scallopOffsetRatio = customFeature.parameters.itemById(scallopOffsetRatioInputDef.id).value

        cutters = createBodies(gemstones, separatorWidth, separatorDepth, scallopDiameter, separatorOffsetRatio, scallopOffsetRatio, False)

        baseFeature.startEdit()

        if not cutters:
            while baseFeature.bodies.count > 0:
                baseFeature.bodies.item(0).deleteMe()
            baseFeature.finishEdit()
            return True

        component = customFeature.parentComponent

        for i, cutterInfo in enumerate(cutters):
            if i < baseFeature.bodies.count:
                currentBody = baseFeature.bodies.item(i)
                updatedBody = updateCutterBodyFromInfo(currentBody, cutterInfo)
                if updatedBody is None:
                    updatedBody = createFreshCutterBodyFromInfo(cutterInfo)
                if updatedBody is None:
                    continue
                baseFeature.updateBody(currentBody, updatedBody)
                handleNewBody(currentBody, cutterInfo.name)
            else:
                newBodySource = createFreshCutterBodyFromInfo(cutterInfo)
                if newBodySource is None:
                    continue
                newBody = component.bRepBodies.add(newBodySource, baseFeature)
                handleNewBody(newBody, cutterInfo.name)

        while baseFeature.bodies.count > len(cutters):
            baseFeature.bodies.item(baseFeature.bodies.count - 1).deleteMe()

        baseFeature.finishEdit()

        return True

    except:
        if baseFeature is not None:
            baseFeature.finishEdit()
        showMessage(f'UpdateFeature: {traceback.format_exc()}\n', True)
        return False


def createNeighborMap(gemstoneInfos: list[GemstoneInfo], connections: list[tuple[GemstoneInfo, GemstoneInfo]]) -> dict[int, list[GemstoneInfo]]:
    """Create a neighbor map from gemstone connections."""
    neighborMap: dict[int, list[GemstoneInfo]] = {}
    for info in gemstoneInfos:
        neighborMap[id(info)] = []

    for info1, info2 in connections:
        neighborMap[id(info1)].append(info2)
        neighborMap[id(info2)].append(info1)

    return neighborMap


def tableAlignedPoint(point: adsk.core.Point3D, normal: adsk.core.Vector3D, gemstoneInfos: list[GemstoneInfo], diameter: float, offsetRatio: float) -> adsk.core.Point3D:
    """Move a point onto the average table plane, then apply relative offset."""
    result = point.copy()
    normal = normalized(normal)
    if normal is None:
        return result

    distances: list[float] = []
    for info in gemstoneInfos:
        planePoint = tablePlanePoint(info)
        if planePoint is None:
            continue

        toPlane = vectorBetween(result, planePoint)
        distances.append(toPlane.dotProduct(normal))

    if len(distances) > 0:
        tableOffset = normal.copy()
        tableOffset.scaleBy(sum(distances) / len(distances))
        result.translateBy(tableOffset)

    userOffset = normal.copy()
    userOffset.scaleBy(diameter * offsetRatio)
    result.translateBy(userOffset)

    return result


def tablePlanePoint(info: GemstoneInfo) -> adsk.core.Point3D | None:
    """Return a stable point on the gemstone table plane."""
    try:
        if info.topPlane is not None and hasattr(info.topPlane, 'origin'):
            return info.topPlane.origin

        if info.topFace is not None:
            return info.topFace.centroid

    except:
        return None

    return None


def tangentForGemstone(info: GemstoneInfo, gemstoneInfos: list[GemstoneInfo], neighborMap: dict[int, list[GemstoneInfo]], normal: adsk.core.Vector3D) -> adsk.core.Vector3D | None:
    """Get the row tangent for one gemstone from its neighbors."""
    neighbors = neighborMap.get(id(info), [])

    if len(neighbors) == 1:
        return tangentBetween(info, neighbors[0], normal)

    if len(neighbors) >= 2:
        neighbors = sorted(neighbors, key=lambda neighbor: info.centroid.distanceTo(neighbor.centroid))
        tangent = vectorBetween(neighbors[0].centroid, neighbors[1].centroid)
        tangent = projectToPlane(tangent, normal)
        tangent = normalized(tangent)
        if tangent is not None:
            return tangent

    closest = closestGemstone(info, gemstoneInfos)
    if closest is None:
        return None

    return tangentBetween(info, closest, normal)


def closestGemstone(info: GemstoneInfo, gemstoneInfos: list[GemstoneInfo]) -> GemstoneInfo | None:
    """Find the nearest gemstone to the provided gemstone info."""
    closest = None
    closestDistance = None

    for other in gemstoneInfos:
        if other is info:
            continue

        distance = info.centroid.distanceTo(other.centroid)
        if closest is None or distance < closestDistance:
            closest = other
            closestDistance = distance

    return closest


def averageNormal(info1: GemstoneInfo, info2: GemstoneInfo) -> adsk.core.Vector3D | None:
    """Average two gemstone normals."""
    normal1 = info1.getNormalizedNormal()
    normal2 = info2.getNormalizedNormal()
    if normal1 is None or normal2 is None:
        return None

    normal = adsk.core.Vector3D.create(
        normal1.x + normal2.x,
        normal1.y + normal2.y,
        normal1.z + normal2.z
        )
    normal = normalized(normal)
    if normal is not None:
        return normal

    return normalized(normal1)


def tangentBetween(info1: GemstoneInfo, info2: GemstoneInfo, normal: adsk.core.Vector3D) -> adsk.core.Vector3D | None:
    """Create a projected tangent vector between two gemstone centers."""
    tangent = vectorBetween(info1.centroid, info2.centroid)
    tangent = projectToPlane(tangent, normal)
    return normalized(tangent)


def cutterAxisFromTangent(tangent: adsk.core.Vector3D, normal: adsk.core.Vector3D) -> adsk.core.Vector3D | None:
    """Get the cutter cylinder axis perpendicular to the gemstone-to-gemstone tangent."""
    axis = tangent.crossProduct(normal)
    return normalized(axis)


def vectorBetween(startPoint: adsk.core.Point3D, endPoint: adsk.core.Point3D) -> adsk.core.Vector3D:
    """Create a vector from start point to end point."""
    return adsk.core.Vector3D.create(
        endPoint.x - startPoint.x,
        endPoint.y - startPoint.y,
        endPoint.z - startPoint.z
        )


def projectToPlane(vector: adsk.core.Vector3D, normal: adsk.core.Vector3D) -> adsk.core.Vector3D:
    """Project a vector onto the plane defined by normal."""
    normal = normalized(normal)
    if normal is None:
        return vector

    dot = vector.dotProduct(normal)
    return adsk.core.Vector3D.create(
        vector.x - normal.x * dot,
        vector.y - normal.y * dot,
        vector.z - normal.z * dot
        )


def normalized(vector: adsk.core.Vector3D) -> adsk.core.Vector3D | None:
    """Return a normalized copy of a vector or None if it is too short."""
    if vector is None:
        return None

    length = math.sqrt(vector.x * vector.x + vector.y * vector.y + vector.z * vector.z)
    if length <= COMMAND.minVectorLength:
        return None

    result = adsk.core.Vector3D.create(vector.x, vector.y, vector.z)
    result.normalize()
    return result


def pointAlongVector(point: adsk.core.Point3D, vector: adsk.core.Vector3D, distance: float) -> adsk.core.Point3D:
    """Create a point offset along a vector."""
    result = point.copy()
    offset = vector.copy()
    offset.scaleBy(distance)
    result.translateBy(offset)
    return result


def midpoint(point1: adsk.core.Point3D, point2: adsk.core.Point3D) -> adsk.core.Point3D:
    """Create a midpoint between two points."""
    return adsk.core.Point3D.create(
        (point1.x + point2.x) * 0.5,
        (point1.y + point2.y) * 0.5,
        (point1.z + point2.z) * 0.5
        )


def handleNewBody(body: adsk.fusion.BRepBody, bodyName: str = None):
    """Set cutter name and attributes."""
    body.name = bodyName if bodyName else body.name
    body.attributes.add(constants.PREFIX, constants.ENTITY, constants.CUTTER)


def updateAttributes():
    """Update attributes of all cutter bodies in the edited custom feature."""
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


def getSelectedGemstones() -> list[adsk.fusion.BRepBody]:
    """Get list of selected gemstone bodies from the selection input."""
    gemstones: list[adsk.fusion.BRepBody] = []
    for i in range(_gemstonesSelectionInput.selectionCount):
        gemstone = _gemstonesSelectionInput.selection(i).entity
        if gemstone is not None:
            gemstones.append(gemstone)
    return gemstones if len(gemstones) >= 2 else []
