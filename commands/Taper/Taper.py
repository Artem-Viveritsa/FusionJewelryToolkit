
import math
import os
import traceback
from typing import Optional

import adsk.core
import adsk.fusion

from ... import constants
from ... import strings
from ...helpers import Bodies
from ...helpers import CustomFeatures
from ...helpers import Deformations
from ...helpers import Points
from ...helpers import Vectors
from ...helpers import showMessage

_app: Optional[adsk.core.Application] = None
_ui: Optional[adsk.core.UserInterface] = None

_customFeatureDefinition: Optional[adsk.fusion.CustomFeatureDefinition] = None

_bodySelectionInput: Optional[adsk.core.SelectionCommandInput] = None
_axisSelectionInput: Optional[adsk.core.SelectionCommandInput] = None
_pivotPointSelectionInput: Optional[adsk.core.SelectionCommandInput] = None
_angleValueInput: Optional[adsk.core.ValueCommandInput] = None

_editedCustomFeature: Optional[adsk.fusion.CustomFeature] = None
_restoreTimelineObject: Optional[adsk.fusion.TimelineObject] = None
_isRolledForEdit: bool = False
_hiddenSourceBody: Optional[adsk.fusion.BRepBody] = None

_handlers: list[object] = []

COMMAND_ID, CREATE_COMMAND_ID, EDIT_COMMAND_ID = strings.getCommandIds(strings.Taper.taperCommandId)

createCommandInputDef = strings.InputDef(CREATE_COMMAND_ID, 'Taper', 'Creates a tapered copy of a solid body.')
editCommandInputDef = strings.InputDef(EDIT_COMMAND_ID, 'Edit Taper', 'Edits the parameters of the taper feature.')

selectBodyInputDef = strings.InputDef(
    strings.Taper.selectBodyInputId,
    'Select Body',
    'Select the solid body to taper.'
)

selectAxisInputDef = strings.InputDef(
    strings.Taper.selectAxisInputId,
    'Axis',
    'Select a straight edge, construction axis, or sketch line as the taper axis.'
)

selectPivotPointInputDef = strings.InputDef(
    strings.Taper.selectPivotPointInputId,
    'Pivot Point',
    'Select the point on the axis where the scale is neutral. Cross-sections before it expand, after it contract.'
)

angleInputDef = strings.InputDef(
    strings.Taper.angleInputId,
    'Angle',
    'The taper angle in degrees.'
)

RESOURCES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')


def run(panel: adsk.core.ToolbarPanel) -> None:
    """Initialize the taper command definitions and UI elements."""
    try:
        global _app, _ui, _customFeatureDefinition

        _app = adsk.core.Application.get()
        _ui = _app.userInterface

        createCommandDefinition = _ui.commandDefinitions.addButtonDefinition(
            createCommandInputDef.id,
            createCommandInputDef.name,
            createCommandInputDef.tooltip,
            RESOURCES_FOLDER
        )

        control = panel.controls.addCommand(createCommandDefinition, '', False)
        control.isPromoted = True

        editCommandDefinition = _ui.commandDefinitions.addButtonDefinition(
            editCommandInputDef.id,
            editCommandInputDef.name,
            editCommandInputDef.tooltip,
            RESOURCES_FOLDER
        )

        createCommandCreated = CreateCommandCreatedHandler()
        createCommandDefinition.commandCreated.add(createCommandCreated)
        _handlers.append(createCommandCreated)

        editCommandCreated = EditCommandCreatedHandler()
        editCommandDefinition.commandCreated.add(editCommandCreated)
        _handlers.append(editCommandCreated)

        _customFeatureDefinition = adsk.fusion.CustomFeatureDefinition.create(
            COMMAND_ID,
            createCommandInputDef.name,
            RESOURCES_FOLDER
        )
        _customFeatureDefinition.editCommandId = EDIT_COMMAND_ID

        computeCustomFeature = ComputeCustomFeature()
        _customFeatureDefinition.customFeatureCompute.add(computeCustomFeature)
        _handlers.append(computeCustomFeature)

    except:
        showMessage.showMessage(f'Run failed:\n{traceback.format_exc()}', True)


def stop(panel: adsk.core.ToolbarPanel) -> None:
    """Clean up the taper command UI elements."""
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
        showMessage.showMessage(f'Stop failed:\n{traceback.format_exc()}', True)


def getSourceBodyFromFeature(customFeature: adsk.fusion.CustomFeature) -> Optional[adsk.fusion.BRepBody]:
    """Return the source body stored in a custom feature."""
    sourceFaceDependency = customFeature.dependencies.itemById(strings.Taper.sourceBodyFaceDependencyId)
    if sourceFaceDependency is None or sourceFaceDependency.entity is None:
        return None

    sourceFace = adsk.fusion.BRepFace.cast(sourceFaceDependency.entity)
    if sourceFace is None:
        return None

    return sourceFace.body


def getAxisEntityFromFeature(customFeature: adsk.fusion.CustomFeature) -> Optional[adsk.core.Base]:
    """Return the axis entity stored in a custom feature."""
    dependency = customFeature.dependencies.itemById(strings.Taper.axisDependencyId)
    if dependency is None:
        return None

    return dependency.entity


def getPivotEntityFromFeature(customFeature: adsk.fusion.CustomFeature) -> Optional[adsk.core.Base]:
    """Return the pivot point entity stored in a custom feature."""
    dependency = customFeature.dependencies.itemById(strings.Taper.pivotPointDependencyId)
    if dependency is None:
        return None

    return dependency.entity


def initializeCommandInputs(inputs: adsk.core.CommandInputs, angleExpression: str) -> None:
    """Create all command inputs for the taper command."""
    global _bodySelectionInput, _axisSelectionInput, _pivotPointSelectionInput, _angleValueInput

    _bodySelectionInput = inputs.addSelectionInput(
        selectBodyInputDef.id,
        selectBodyInputDef.name,
        selectBodyInputDef.tooltip
    )
    _bodySelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SolidBodies)
    _bodySelectionInput.setSelectionLimits(1, 1)
    _bodySelectionInput.tooltip = selectBodyInputDef.tooltip

    _axisSelectionInput = inputs.addSelectionInput(
        selectAxisInputDef.id,
        selectAxisInputDef.name,
        selectAxisInputDef.tooltip
    )
    _axisSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Edges)
    _axisSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.ConstructionLines)
    _axisSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchLines)
    _axisSelectionInput.setSelectionLimits(1, 1)
    _axisSelectionInput.tooltip = selectAxisInputDef.tooltip

    _pivotPointSelectionInput = inputs.addSelectionInput(
        selectPivotPointInputDef.id,
        selectPivotPointInputDef.name,
        selectPivotPointInputDef.tooltip
    )
    _pivotPointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Vertices)
    _pivotPointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.ConstructionPoints)
    _pivotPointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchPoints)
    _pivotPointSelectionInput.setSelectionLimits(1, 1)
    _pivotPointSelectionInput.tooltip = selectPivotPointInputDef.tooltip

    angleValue = adsk.core.ValueInput.createByString(angleExpression)
    _angleValueInput = inputs.addValueInput(
        angleInputDef.id,
        angleInputDef.name,
        'deg',
        angleValue
    )
    _angleValueInput.tooltip = angleInputDef.tooltip


class PreSelectHandler(adsk.core.SelectionEventHandler):
    """Event handler for filtering unsupported axis and pivot selections."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.SelectionEventArgs) -> None:
        try:
            eventArgs = adsk.core.SelectionEventArgs.cast(args)
            entity = eventArgs.selection.entity

            if entity.objectType in (adsk.fusion.BRepEdge.classType(),
                                     adsk.fusion.ConstructionAxis.classType(),
                                     adsk.fusion.SketchLine.classType()):
                if Vectors.getAxisDirection(entity) is None:
                    eventArgs.isSelectable = False
                    return

            if entity.objectType in (adsk.fusion.BRepVertex.classType(),
                                     adsk.fusion.ConstructionPoint.classType(),
                                     adsk.fusion.SketchPoint.classType()):
                if Points.getPointGeometry(entity) is None:
                    eventArgs.isSelectable = False

        except:
            showMessage.showMessage(f'PreSelectHandler: {traceback.format_exc()}\n', True)


def createTaperPreviewBody() -> Optional[adsk.fusion.BRepBody]:
    """Create a preview body from the current command inputs."""
    previewData = getTaperPreviewData()
    if previewData is None:
        return None

    sourceBody, axisDirection, pivotPoint, angleValue = previewData
    return Deformations.createTaperBody(sourceBody, axisDirection, pivotPoint, angleValue)


def getTaperPreviewData() -> Optional[tuple[adsk.fusion.BRepBody, adsk.core.Vector3D, adsk.core.Point3D, float]]:
    """Return validated taper preview inputs from the active command."""
    global _bodySelectionInput, _axisSelectionInput, _pivotPointSelectionInput, _angleValueInput

    if _bodySelectionInput is None or _bodySelectionInput.selectionCount != 1:
        return None

    if _axisSelectionInput is None or _axisSelectionInput.selectionCount != 1:
        return None

    if _pivotPointSelectionInput is None or _pivotPointSelectionInput.selectionCount != 1:
        return None

    if _angleValueInput is None or not _angleValueInput.isValidExpression:
        return None

    sourceBody = adsk.fusion.BRepBody.cast(_bodySelectionInput.selection(0).entity)
    if sourceBody is None:
        return None

    axisDirection = Vectors.getAxisDirection(_axisSelectionInput.selection(0).entity)
    if axisDirection is None:
        return None

    pivotPoint = Points.getPointGeometry(_pivotPointSelectionInput.selection(0).entity)
    if pivotPoint is None:
        return None

    return sourceBody, axisDirection, pivotPoint, _angleValueInput.value


def clearTaperGraphics() -> None:
    """Remove all custom graphics groups from the root component."""
    design = adsk.fusion.Design.cast(_app.activeProduct)
    if design is None:
        return

    groups = design.rootComponent.customGraphicsGroups
    for i in range(groups.count - 1, -1, -1):
        try:
            groups.item(i).deleteMe()
        except:
            pass


def getTaperHeight(body: adsk.fusion.BRepBody, axisDirection: adsk.core.Vector3D) -> Optional[float]:
    """Return the projection height of the source body along the taper axis."""
    nurbsBody = Bodies.convertBodyToNurbs(body)
    if nurbsBody is None:
        return None

    minProjection: Optional[float] = None
    maxProjection: Optional[float] = None

    for vertex in nurbsBody.vertices:
        point = vertex.geometry
        projection = point.x * axisDirection.x + point.y * axisDirection.y + point.z * axisDirection.z
        if minProjection is None or projection < minProjection:
            minProjection = projection
        if maxProjection is None or projection > maxProjection:
            maxProjection = projection

    if minProjection is None or maxProjection is None:
        return None

    height = maxProjection - minProjection
    if height <= 0:
        return None

    return height


def interpolatePoint(
    startPoint: adsk.core.Point3D,
    endPoint: adsk.core.Point3D,
    factor: float
) -> adsk.core.Point3D:
    """Interpolate a point between two 3D points."""
    return adsk.core.Point3D.create(
        startPoint.x + (endPoint.x - startPoint.x) * factor,
        startPoint.y + (endPoint.y - startPoint.y) * factor,
        startPoint.z + (endPoint.z - startPoint.z) * factor
    )


def transformTaperPreviewPoint(
    point: adsk.core.Point3D,
    axisDirection: adsk.core.Vector3D,
    pivotPoint: adsk.core.Point3D,
    angleValue: float,
    height: float
) -> adsk.core.Point3D:
    """Transform a point using the same taper formula as the body deformation."""
    axisX = axisDirection.x
    axisY = axisDirection.y
    axisZ = axisDirection.z
    pivotX = pivotPoint.x
    pivotY = pivotPoint.y
    pivotZ = pivotPoint.z
    pivotProjection = pivotX * axisX + pivotY * axisY + pivotZ * axisZ
    tanAngle = math.tan(angleValue)

    dx = point.x - pivotX
    dy = point.y - pivotY
    dz = point.z - pivotZ
    projection = point.x * axisX + point.y * axisY + point.z * axisZ - pivotProjection
    scale = max(constants.Deformations.minimumTaperScale, 1.0 - (projection / height) * tanAngle)

    return adsk.core.Point3D.create(
        pivotX + projection * axisX + (dx - projection * axisX) * scale,
        pivotY + projection * axisY + (dy - projection * axisY) * scale,
        pivotZ + projection * axisZ + (dz - projection * axisZ) * scale
    )


def getBoundingBoxCorners(body: adsk.fusion.BRepBody) -> list[adsk.core.Point3D]:
    """Return the eight corner points of the body's axis-aligned bounding box."""
    bbox = body.boundingBox
    minPoint = bbox.minPoint
    maxPoint = bbox.maxPoint

    return [
        adsk.core.Point3D.create(minPoint.x, minPoint.y, minPoint.z),
        adsk.core.Point3D.create(maxPoint.x, minPoint.y, minPoint.z),
        adsk.core.Point3D.create(minPoint.x, maxPoint.y, minPoint.z),
        adsk.core.Point3D.create(maxPoint.x, maxPoint.y, minPoint.z),
        adsk.core.Point3D.create(minPoint.x, minPoint.y, maxPoint.z),
        adsk.core.Point3D.create(maxPoint.x, minPoint.y, maxPoint.z),
        adsk.core.Point3D.create(minPoint.x, maxPoint.y, maxPoint.z),
        adsk.core.Point3D.create(maxPoint.x, maxPoint.y, maxPoint.z)
    ]


def buildTaperBoundingBoxLineCoordinates(
    body: adsk.fusion.BRepBody,
    axisDirection: adsk.core.Vector3D,
    pivotPoint: adsk.core.Point3D,
    angleValue: float
) -> list[float]:
    """Build segmented line coordinates for the tapered bounding box preview."""
    height = getTaperHeight(body, axisDirection)
    if height is None:
        return []

    corners = getBoundingBoxCorners(body)
    lineCoordinates: list[float] = []
    edgeSegments = max(constants.Deformations.taperPreviewEdgeSegments, 1)

    for startIndex, endIndex in constants.Deformations.taperBoundingBoxEdgeIndices:
        edgeStart = corners[startIndex]
        edgeEnd = corners[endIndex]
        previousPoint = transformTaperPreviewPoint(edgeStart, axisDirection, pivotPoint, angleValue, height)

        for segmentIndex in range(1, edgeSegments + 1):
            factor = segmentIndex / edgeSegments
            currentPoint = transformTaperPreviewPoint(
                interpolatePoint(edgeStart, edgeEnd, factor),
                axisDirection,
                pivotPoint,
                angleValue,
                height
            )
            lineCoordinates.extend([
                previousPoint.x, previousPoint.y, previousPoint.z,
                currentPoint.x, currentPoint.y, currentPoint.z
            ])
            previousPoint = currentPoint

    return lineCoordinates


def drawTaperGraphics(lineCoordinates: list[float], refreshViewport: bool = True) -> None:
    """Draw the tapered bounding box preview as custom graphics."""
    clearTaperGraphics()

    if not lineCoordinates:
        return

    design = adsk.fusion.Design.cast(_app.activeProduct)
    if design is None:
        return

    cgGroup = design.rootComponent.customGraphicsGroups.add()
    coords = adsk.fusion.CustomGraphicsCoordinates.create(lineCoordinates)
    cgLines = cgGroup.addLines(coords, [], False, [])
    red, green, blue, alpha = constants.Deformations.taperPreviewLineColorRGBA
    cgLines.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(
        adsk.core.Color.create(red, green, blue, alpha)
    )
    cgLines.weight = constants.Deformations.taperPreviewLineWeight

    if refreshViewport:
        _app.activeViewport.refresh()


def updateTaperDisplay(refreshViewport: bool = True) -> None:
    """Redraw the tapered bounding box preview from the current inputs."""
    previewData = getTaperPreviewData()
    if previewData is None:
        clearTaperGraphics()
        return

    sourceBody, axisDirection, pivotPoint, angleValue = previewData
    lineCoordinates = buildTaperBoundingBoxLineCoordinates(sourceBody, axisDirection, pivotPoint, angleValue)
    drawTaperGraphics(lineCoordinates, refreshViewport)


class CreateCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Event handler for creating a new taper command dialog."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.CommandCreatedEventArgs) -> None:
        try:
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs

            angleExpression = f'{constants.Deformations.defaultTaperAngleDeg} deg'
            initializeCommandInputs(inputs, angleExpression)

            onPreSelect = PreSelectHandler()
            command.preSelect.add(onPreSelect)
            _handlers.append(onPreSelect)

            onValidate = ValidateInputsHandler()
            command.validateInputs.add(onValidate)
            _handlers.append(onValidate)

            onInputChanged = InputChangedHandler()
            command.inputChanged.add(onInputChanged)
            _handlers.append(onInputChanged)

            onExecutePreview = ExecutePreviewHandler()
            command.executePreview.add(onExecutePreview)
            _handlers.append(onExecutePreview)

            onExecute = CreateExecuteHandler()
            command.execute.add(onExecute)
            _handlers.append(onExecute)

            onDestroy = DestroyHandler()
            command.destroy.add(onDestroy)
            _handlers.append(onDestroy)

        except:
            showMessage.showMessage(f'CreateCommandCreatedHandler: {traceback.format_exc()}\n', True)


class EditCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Event handler for creating the edit dialog of an existing taper feature."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.CommandCreatedEventArgs) -> None:
        try:
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs

            global _editedCustomFeature

            _editedCustomFeature = adsk.fusion.CustomFeature.cast(_ui.activeSelections.item(0).entity)
            if _editedCustomFeature is None:
                return

            angleExpression = f'{constants.Deformations.defaultTaperAngleDeg} deg'
            angleParameter = _editedCustomFeature.parameters.itemById(angleInputDef.id)
            if angleParameter is not None:
                angleExpression = angleParameter.expression

            initializeCommandInputs(inputs, angleExpression)

            onPreSelect = PreSelectHandler()
            command.preSelect.add(onPreSelect)
            _handlers.append(onPreSelect)

            onValidate = ValidateInputsHandler()
            command.validateInputs.add(onValidate)
            _handlers.append(onValidate)

            onInputChanged = InputChangedHandler()
            command.inputChanged.add(onInputChanged)
            _handlers.append(onInputChanged)

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
            showMessage.showMessage(f'EditCommandCreatedHandler: {traceback.format_exc()}\n', True)


class ValidateInputsHandler(adsk.core.ValidateInputsEventHandler):
    """Event handler for validating taper command inputs."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.ValidateInputsEventArgs) -> None:
        global _bodySelectionInput, _axisSelectionInput, _pivotPointSelectionInput, _angleValueInput

        try:
            eventArgs = adsk.core.ValidateInputsEventArgs.cast(args)

            if _bodySelectionInput.selectionCount != 1:
                eventArgs.areInputsValid = False
                return

            if _axisSelectionInput.selectionCount != 1:
                eventArgs.areInputsValid = False
                return

            if Vectors.getAxisDirection(_axisSelectionInput.selection(0).entity) is None:
                eventArgs.areInputsValid = False
                return

            if _pivotPointSelectionInput.selectionCount != 1:
                eventArgs.areInputsValid = False
                return

            if Points.getPointGeometry(_pivotPointSelectionInput.selection(0).entity) is None:
                eventArgs.areInputsValid = False
                return

            if not _angleValueInput.isValidExpression:
                eventArgs.areInputsValid = False
                return

            minAngle = math.radians(constants.Deformations.minTaperAngleDeg)
            maxAngle = math.radians(constants.Deformations.maxTaperAngleDeg)

            if _angleValueInput.value < minAngle or _angleValueInput.value > maxAngle:
                eventArgs.areInputsValid = False
                return

            eventArgs.areInputsValid = True

        except:
            showMessage.showMessage(f'ValidateInputsHandler: {traceback.format_exc()}\n', True)


class InputChangedHandler(adsk.core.InputChangedEventHandler):
    """Event handler for taper input changes."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.InputChangedEventArgs) -> None:
        try:
            updateTaperDisplay()

        except:
            showMessage.showMessage(f'InputChangedHandler: {traceback.format_exc()}\n', True)


class ExecutePreviewHandler(adsk.core.CommandEventHandler):
    """Event handler for taper command preview execution."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.CommandEventArgs) -> None:
        global _hiddenSourceBody

        baseFeature: Optional[adsk.fusion.BaseFeature] = None
        isBaseFeatureEditing = False

        try:
            if _bodySelectionInput.selectionCount != 1:
                clearTaperGraphics()
                return

            sourceBody = adsk.fusion.BRepBody.cast(_bodySelectionInput.selection(0).entity)
            if sourceBody is None:
                clearTaperGraphics()
                return

            resultBody = createTaperPreviewBody()
            if resultBody is None:
                updateTaperDisplay(False)
                return

            component = sourceBody.parentComponent
            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()
            isBaseFeatureEditing = True

            outputBody = component.bRepBodies.add(resultBody, baseFeature)
            Bodies.copyAttributes(sourceBody, outputBody)
            outputBody.name = strings.Taper.bodyNameTemplate.format(bodyName=sourceBody.name)

            baseFeature.finishEdit()
            isBaseFeatureEditing = False

            sourceBody.isLightBulbOn = False
            _hiddenSourceBody = sourceBody
            updateTaperDisplay(False)

        except:
            if baseFeature is not None and isBaseFeatureEditing:
                baseFeature.finishEdit()

            updateTaperDisplay(False)

            showMessage.showMessage(f'ExecutePreviewHandler: {traceback.format_exc()}\n', True)


class CreateExecuteHandler(adsk.core.CommandEventHandler):
    """Event handler for creating a taper custom feature."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.CommandEventArgs) -> None:
        global _bodySelectionInput, _axisSelectionInput, _pivotPointSelectionInput
        global _angleValueInput, _customFeatureDefinition, _app, _hiddenSourceBody

        eventArgs: Optional[adsk.core.CommandEventArgs] = None
        baseFeature: Optional[adsk.fusion.BaseFeature] = None
        isBaseFeatureEditing = False

        try:
            eventArgs = adsk.core.CommandEventArgs.cast(args)

            sourceBody = adsk.fusion.BRepBody.cast(_bodySelectionInput.selection(0).entity)
            if sourceBody is None:
                eventArgs.executeFailed = True
                return

            axisEntity = _axisSelectionInput.selection(0).entity
            axisDirection = Vectors.getAxisDirection(axisEntity)
            if axisDirection is None:
                eventArgs.executeFailed = True
                return

            pivotEntity = _pivotPointSelectionInput.selection(0).entity
            pivotPoint = Points.getPointGeometry(pivotEntity)
            if pivotPoint is None:
                eventArgs.executeFailed = True
                return

            resultBody = Deformations.createTaperBody(
                sourceBody, axisDirection, pivotPoint, _angleValueInput.value
            )
            if resultBody is None:
                showMessage.showMessage(
                    'Failed to create tapered body. The geometry may be too complex or the angle too extreme.', True
                )
                eventArgs.executeFailed = True
                return

            component = sourceBody.parentComponent
            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()
            isBaseFeatureEditing = True

            outputBody = component.bRepBodies.add(resultBody, baseFeature)
            Bodies.copyAttributes(sourceBody, outputBody)
            outputBody.name = strings.Taper.bodyNameTemplate.format(bodyName=sourceBody.name)

            baseFeature.finishEdit()
            isBaseFeatureEditing = False

            if sourceBody.faces.count == 0:
                eventArgs.executeFailed = True
                return

            customFeatureInput = component.features.customFeatures.createInput(_customFeatureDefinition)
            customFeatureInput.addDependency(strings.Taper.sourceBodyFaceDependencyId, sourceBody.faces.item(0))
            customFeatureInput.addDependency(strings.Taper.axisDependencyId, axisEntity)
            customFeatureInput.addDependency(strings.Taper.pivotPointDependencyId, pivotEntity)

            angleInput = adsk.core.ValueInput.createByString(_angleValueInput.expression)
            customFeatureInput.addCustomParameter(
                angleInputDef.id,
                angleInputDef.name,
                angleInput,
                'deg',
                True
            )

            customFeatureInput.setStartAndEndFeatures(baseFeature, baseFeature)
            component.features.customFeatures.add(customFeatureInput)

            sourceBody.isLightBulbOn = False
            _hiddenSourceBody = None

        except:
            if baseFeature is not None and isBaseFeatureEditing:
                baseFeature.finishEdit()

            if eventArgs is not None:
                eventArgs.executeFailed = True
            showMessage.showMessage(f'CreateExecuteHandler: {traceback.format_exc()}\n', True)


class DestroyHandler(adsk.core.CommandEventHandler):
    """Event handler for cleaning up when the taper create command ends."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.CommandEventArgs) -> None:
        global _hiddenSourceBody

        try:
            clearTaperGraphics()

            if _hiddenSourceBody is not None:
                _hiddenSourceBody.isLightBulbOn = True
                _hiddenSourceBody = None

        except:
            showMessage.showMessage(f'DestroyHandler: {traceback.format_exc()}\n', True)


class EditActivateHandler(adsk.core.CommandEventHandler):
    """Event handler for activating taper feature editing."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.CommandEventArgs) -> None:
        try:
            global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature, _hiddenSourceBody
            global _bodySelectionInput, _axisSelectionInput, _pivotPointSelectionInput

            if _isRolledForEdit:
                return

            eventArgs = adsk.core.CommandEventArgs.cast(args)

            design = adsk.fusion.Design.cast(_app.activeProduct)
            timeline = design.timeline
            markerPosition = timeline.markerPosition
            _restoreTimelineObject = timeline.item(markerPosition - 1) if markerPosition > 0 else None

            _editedCustomFeature.timelineObject.rollTo(True)
            _isRolledForEdit = True

            command = eventArgs.command
            command.beginStep()

            _hiddenSourceBody = None

            sourceBody = getSourceBodyFromFeature(_editedCustomFeature)
            if sourceBody is not None:
                sourceBody.isLightBulbOn = True
                _bodySelectionInput.addSelection(sourceBody)

            axisEntity = getAxisEntityFromFeature(_editedCustomFeature)
            if axisEntity is not None:
                _axisSelectionInput.addSelection(axisEntity)

            pivotEntity = getPivotEntityFromFeature(_editedCustomFeature)
            if pivotEntity is not None:
                _pivotPointSelectionInput.addSelection(pivotEntity)

            updateTaperDisplay()

        except:
            showMessage.showMessage(f'EditActivateHandler: {traceback.format_exc()}\n', True)


class EditDestroyHandler(adsk.core.CommandEventHandler):
    """Event handler for finishing taper feature editing."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.CommandEventArgs) -> None:
        try:
            clearTaperGraphics()

            eventArgs = adsk.core.CommandEventArgs.cast(args)
            if eventArgs.terminationReason != adsk.core.CommandTerminationReason.CompletedTerminationReason:
                sourceBody = getSourceBodyFromFeature(_editedCustomFeature)
                if sourceBody is not None:
                    sourceBody.isLightBulbOn = False

                rollBack()

        except:
            showMessage.showMessage(f'EditDestroyHandler: {traceback.format_exc()}\n', True)


class EditExecuteHandler(adsk.core.CommandEventHandler):
    """Event handler for applying edited taper feature parameters."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.CommandEventArgs) -> None:
        global _editedCustomFeature, _bodySelectionInput
        global _axisSelectionInput, _pivotPointSelectionInput, _angleValueInput

        try:
            eventArgs = adsk.core.CommandEventArgs.cast(args)

            if _editedCustomFeature is None:
                eventArgs.executeFailed = True
                return

            sourceBody: Optional[adsk.fusion.BRepBody] = None
            if _bodySelectionInput.selectionCount == 1:
                sourceBody = adsk.fusion.BRepBody.cast(_bodySelectionInput.selection(0).entity)

            if sourceBody is None:
                sourceBody = getSourceBodyFromFeature(_editedCustomFeature)

            if sourceBody is None:
                eventArgs.executeFailed = True
                return

            axisEntity: Optional[adsk.core.Base] = None
            if _axisSelectionInput.selectionCount == 1:
                axisEntity = _axisSelectionInput.selection(0).entity

            if axisEntity is None:
                axisEntity = getAxisEntityFromFeature(_editedCustomFeature)

            if axisEntity is None:
                eventArgs.executeFailed = True
                return

            pivotEntity: Optional[adsk.core.Base] = None
            if _pivotPointSelectionInput.selectionCount == 1:
                pivotEntity = _pivotPointSelectionInput.selection(0).entity

            if pivotEntity is None:
                pivotEntity = getPivotEntityFromFeature(_editedCustomFeature)

            if pivotEntity is None or Points.getPointGeometry(pivotEntity) is None:
                eventArgs.executeFailed = True
                return

            if sourceBody.faces.count == 0:
                eventArgs.executeFailed = True
                return

            _editedCustomFeature.dependencies.deleteAll()
            _editedCustomFeature.dependencies.add(strings.Taper.sourceBodyFaceDependencyId, sourceBody.faces.item(0))
            _editedCustomFeature.dependencies.add(strings.Taper.axisDependencyId, axisEntity)
            _editedCustomFeature.dependencies.add(strings.Taper.pivotPointDependencyId, pivotEntity)

            _editedCustomFeature.parameters.itemById(angleInputDef.id).expression = _angleValueInput.expression

            if not updateFeature(_editedCustomFeature):
                eventArgs.executeFailed = True

        except:
            showMessage.showMessage(f'EditExecuteHandler: {traceback.format_exc()}\n', True)

        finally:
            rollBack()


class ComputeCustomFeature(adsk.fusion.CustomFeatureEventHandler):
    """Event handler for computing taper custom features."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.fusion.CustomFeatureEventArgs) -> None:
        try:
            eventArgs = adsk.fusion.CustomFeatureEventArgs.cast(args)
            customFeature = eventArgs.customFeature
            updateFeature(customFeature)

        except:
            showMessage.showMessage(f'ComputeCustomFeature: {traceback.format_exc()}\n', True)


def updateFeature(customFeature: adsk.fusion.CustomFeature) -> bool:
    """Recompute the taper feature output body."""
    baseFeature = CustomFeatures.getBaseFeature(customFeature)
    isBaseFeatureEditing = False

    try:
        if baseFeature is None:
            return False

        component = customFeature.parentComponent
        sourceBody = getSourceBodyFromFeature(customFeature)
        if sourceBody is None:
            return False

        axisEntity = getAxisEntityFromFeature(customFeature)
        axisDirection = Vectors.getAxisDirection(axisEntity)
        if axisDirection is None:
            return False

        pivotEntity = getPivotEntityFromFeature(customFeature)
        pivotPoint = Points.getPointGeometry(pivotEntity)
        if pivotPoint is None:
            return False

        angleParameter = customFeature.parameters.itemById(angleInputDef.id)
        if angleParameter is None:
            return False

        resultBody = Deformations.createTaperBody(
            sourceBody, axisDirection, pivotPoint, angleParameter.value
        )
        if resultBody is None:
            return False

        baseFeature.startEdit()
        isBaseFeatureEditing = True

        if baseFeature.bodies.count > 0:
            outputBody = baseFeature.bodies.item(0)
            baseFeature.updateBody(outputBody, resultBody)
        else:
            outputBody = component.bRepBodies.add(resultBody, baseFeature)

        while baseFeature.bodies.count > 1:
            baseFeature.bodies.item(baseFeature.bodies.count - 1).deleteMe()

        Bodies.copyAttributes(sourceBody, outputBody)
        outputBody.name = strings.Taper.bodyNameTemplate.format(bodyName=sourceBody.name)

        baseFeature.finishEdit()
        isBaseFeatureEditing = False

        sourceBody.isLightBulbOn = False

        return True

    except:
        if baseFeature is not None and isBaseFeatureEditing:
            baseFeature.finishEdit()

        showMessage.showMessage(f'updateFeature: {traceback.format_exc()}\n', True)
        return False


def rollBack() -> None:
    """Restore the timeline after editing a taper custom feature."""
    global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature, _hiddenSourceBody

    if _isRolledForEdit:
        if _restoreTimelineObject is not None:
            _restoreTimelineObject.rollTo(False)

        _isRolledForEdit = False

    _restoreTimelineObject = None
    _editedCustomFeature = None
    _hiddenSourceBody = None
