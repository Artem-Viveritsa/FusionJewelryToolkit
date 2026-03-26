
import json
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
from ...helpers import showMessage

_app: Optional[adsk.core.Application] = None
_ui: Optional[adsk.core.UserInterface] = None

_customFeatureDefinition: Optional[adsk.fusion.CustomFeatureDefinition] = None

_bodySelectionInput: Optional[adsk.core.SelectionCommandInput] = None
_resolutionXInput: Optional[adsk.core.IntegerSpinnerCommandInput] = None
_resolutionYInput: Optional[adsk.core.IntegerSpinnerCommandInput] = None
_resolutionZInput: Optional[adsk.core.IntegerSpinnerCommandInput] = None
_offsetXInput: Optional[adsk.core.DistanceValueCommandInput] = None
_offsetYInput: Optional[adsk.core.DistanceValueCommandInput] = None
_offsetZInput: Optional[adsk.core.DistanceValueCommandInput] = None
_resetButtonInput: Optional[adsk.core.BoolValueCommandInput] = None

_editedCustomFeature: Optional[adsk.fusion.CustomFeature] = None
_restoreTimelineObject: Optional[adsk.fusion.TimelineObject] = None
_isRolledForEdit: bool = False
_hiddenSourceBody: Optional[adsk.fusion.BRepBody] = None

_handlers: list[object] = []

_controlPointOffsets: list[list[float]] = []
_selectedPointIndex: int = 0
_isUpdatingInputs: bool = False
_skipCompute: bool = False
_gridSizeX: int = constants.FFDConst.defaultGridSize
_gridSizeY: int = constants.FFDConst.defaultGridSize
_gridSizeZ: int = constants.FFDConst.defaultGridSize

COMMAND_ID, CREATE_COMMAND_ID, EDIT_COMMAND_ID = strings.getCommandIds(strings.FFD.ffdCommandId)

createCommandInputDef = strings.InputDef(CREATE_COMMAND_ID, 'FFD', 'Creates a free-form deformed copy of a solid body.')
editCommandInputDef = strings.InputDef(EDIT_COMMAND_ID, 'Edit FFD', 'Edits the parameters of the FFD feature.')

selectBodyInputDef = strings.InputDef(
    strings.FFD.selectBodyInputId,
    'Select Body',
    'Select the solid body to deform.'
)

resolutionXInputDef = strings.InputDef(
    strings.FFD.resolutionXInputId,
    'Resolution X',
    'Number of control points along the X axis.'
)

resolutionYInputDef = strings.InputDef(
    strings.FFD.resolutionYInputId,
    'Resolution Y',
    'Number of control points along the Y axis.'
)

resolutionZInputDef = strings.InputDef(
    strings.FFD.resolutionZInputId,
    'Resolution Z',
    'Number of control points along the Z axis.'
)

offsetXInputDef = strings.InputDef(
    strings.FFD.offsetXInputId,
    'Offset X',
    'X-axis displacement of the selected control point.'
)

offsetYInputDef = strings.InputDef(
    strings.FFD.offsetYInputId,
    'Offset Y',
    'Y-axis displacement of the selected control point.'
)

offsetZInputDef = strings.InputDef(
    strings.FFD.offsetZInputId,
    'Offset Z',
    'Z-axis displacement of the selected control point.'
)

resetButtonInputDef = strings.InputDef(
    strings.FFD.resetButtonInputId,
    'Reset All',
    'Reset all control points to zero.'
)

RESOURCES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')


def run(panel: adsk.core.ToolbarPanel) -> None:
    """Initialize the FFD command definitions and UI elements."""
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
    """Clean up the FFD command UI elements."""
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
    sourceFaceDependency = customFeature.dependencies.itemById(strings.FFD.sourceBodyFaceDependencyId)
    if sourceFaceDependency is None or sourceFaceDependency.entity is None:
        return None

    sourceFace = adsk.fusion.BRepFace.cast(sourceFaceDependency.entity)
    if sourceFace is None:
        return None

    return sourceFace.body


def getOffsetsFromFeature(customFeature: adsk.fusion.CustomFeature) -> list[list[float]]:
    """Return the control point offsets stored in a custom feature's attributes."""
    gridSizes = getGridSizesFromFeature(customFeature)
    totalPoints = gridSizes[0] * gridSizes[1] * gridSizes[2]

    attr = customFeature.attributes.itemByName(strings.FFD.offsetsAttributeGroup, strings.FFD.offsetsAttributeName)
    if attr is not None:
        try:
            return json.loads(attr.value)
        except:
            pass

    return [[0.0, 0.0, 0.0] for _ in range(totalPoints)]


def getGridSizesFromFeature(customFeature: adsk.fusion.CustomFeature) -> list[int]:
    """Return the [gridSizeX, gridSizeY, gridSizeZ] from a custom feature."""
    attr = customFeature.attributes.itemByName(strings.FFD.offsetsAttributeGroup, strings.FFD.gridSizeAttributeName)
    if attr is not None:
        try:
            return json.loads(attr.value)
        except:
            pass

    default = constants.FFDConst.defaultGridSize
    return [default, default, default]


def initializeOffsets() -> None:
    """Initialize control point offsets to zero."""
    global _controlPointOffsets, _gridSizeX, _gridSizeY, _gridSizeZ
    totalPoints = _gridSizeX * _gridSizeY * _gridSizeZ
    _controlPointOffsets = [[0.0, 0.0, 0.0] for _ in range(totalPoints)]


def initializeCommandInputs(inputs: adsk.core.CommandInputs) -> None:
    """Create all command inputs for the FFD command."""
    global _bodySelectionInput
    global _resolutionXInput, _resolutionYInput, _resolutionZInput
    global _offsetXInput, _offsetYInput, _offsetZInput, _resetButtonInput

    _bodySelectionInput = inputs.addSelectionInput(
        selectBodyInputDef.id,
        selectBodyInputDef.name,
        selectBodyInputDef.tooltip
    )
    _bodySelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SolidBodies)
    _bodySelectionInput.setSelectionLimits(1, 1)
    _bodySelectionInput.tooltip = selectBodyInputDef.tooltip

    minGrid = constants.FFDConst.minGridSize
    maxGrid = constants.FFDConst.maxGridSize

    _resolutionXInput = inputs.addIntegerSpinnerCommandInput(
        resolutionXInputDef.id,
        resolutionXInputDef.name,
        minGrid, maxGrid, 1, _gridSizeX
    )
    _resolutionXInput.tooltip = resolutionXInputDef.tooltip
    _resolutionXInput.isVisible = False

    _resolutionYInput = inputs.addIntegerSpinnerCommandInput(
        resolutionYInputDef.id,
        resolutionYInputDef.name,
        minGrid, maxGrid, 1, _gridSizeY
    )
    _resolutionYInput.tooltip = resolutionYInputDef.tooltip
    _resolutionYInput.isVisible = False

    _resolutionZInput = inputs.addIntegerSpinnerCommandInput(
        resolutionZInputDef.id,
        resolutionZInputDef.name,
        minGrid, maxGrid, 1, _gridSizeZ
    )
    _resolutionZInput.tooltip = resolutionZInputDef.tooltip
    _resolutionZInput.isVisible = False

    zeroValue = adsk.core.ValueInput.createByReal(constants.FFDConst.defaultOffsetCm)

    _offsetXInput = inputs.addDistanceValueCommandInput(
        offsetXInputDef.id,
        offsetXInputDef.name,
        zeroValue
    )
    _offsetXInput.setManipulator(
        adsk.core.Point3D.create(0, 0, 0),
        adsk.core.Vector3D.create(1, 0, 0)
    )
    _offsetXInput.tooltip = offsetXInputDef.tooltip
    _offsetXInput.isVisible = False

    _offsetYInput = inputs.addDistanceValueCommandInput(
        offsetYInputDef.id,
        offsetYInputDef.name,
        adsk.core.ValueInput.createByReal(constants.FFDConst.defaultOffsetCm)
    )
    _offsetYInput.setManipulator(
        adsk.core.Point3D.create(0, 0, 0),
        adsk.core.Vector3D.create(0, 1, 0)
    )
    _offsetYInput.tooltip = offsetYInputDef.tooltip
    _offsetYInput.isVisible = False

    _offsetZInput = inputs.addDistanceValueCommandInput(
        offsetZInputDef.id,
        offsetZInputDef.name,
        adsk.core.ValueInput.createByReal(constants.FFDConst.defaultOffsetCm)
    )
    _offsetZInput.setManipulator(
        adsk.core.Point3D.create(0, 0, 0),
        adsk.core.Vector3D.create(0, 0, 1)
    )
    _offsetZInput.tooltip = offsetZInputDef.tooltip
    _offsetZInput.isVisible = False

    _resetButtonInput = inputs.addBoolValueInput(
        resetButtonInputDef.id,
        resetButtonInputDef.name,
        False,
        '',
        True
    )
    _resetButtonInput.tooltip = resetButtonInputDef.tooltip
    _resetButtonInput.isVisible = False


def getNeutralLatticePoint(
    body: adsk.fusion.BRepBody,
    pointIndex: int
) -> adsk.core.Point3D:
    """Compute the neutral (undeformed) position of a lattice control point."""
    global _gridSizeX, _gridSizeY, _gridSizeZ

    bbox = body.boundingBox

    i = pointIndex // (_gridSizeY * _gridSizeZ)
    j = (pointIndex // _gridSizeZ) % _gridSizeY
    k = pointIndex % _gridSizeZ

    epsilon = 1e-6
    sizeX = max(bbox.maxPoint.x - bbox.minPoint.x, epsilon)
    sizeY = max(bbox.maxPoint.y - bbox.minPoint.y, epsilon)
    sizeZ = max(bbox.maxPoint.z - bbox.minPoint.z, epsilon)

    divisorX = max(_gridSizeX - 1, 1)
    divisorY = max(_gridSizeY - 1, 1)
    divisorZ = max(_gridSizeZ - 1, 1)

    return adsk.core.Point3D.create(
        bbox.minPoint.x + (i / divisorX) * sizeX,
        bbox.minPoint.y + (j / divisorY) * sizeY,
        bbox.minPoint.z + (k / divisorZ) * sizeZ,
    )


def updateManipulatorOrigins() -> None:
    """Reposition the offset manipulators to the selected control point's displaced position."""
    global _bodySelectionInput, _selectedPointIndex, _controlPointOffsets
    global _offsetXInput, _offsetYInput, _offsetZInput, _isUpdatingInputs

    if _bodySelectionInput is None or _bodySelectionInput.selectionCount != 1:
        return

    body = adsk.fusion.BRepBody.cast(_bodySelectionInput.selection(0).entity)
    if body is None:
        return

    neutral = getNeutralLatticePoint(body, _selectedPointIndex)

    offsets = [0.0, 0.0, 0.0]
    if _selectedPointIndex < len(_controlPointOffsets):
        offsets = _controlPointOffsets[_selectedPointIndex]

    xOrigin = adsk.core.Point3D.create(neutral.x, neutral.y + offsets[1], neutral.z + offsets[2])
    yOrigin = adsk.core.Point3D.create(neutral.x + offsets[0], neutral.y, neutral.z + offsets[2])
    zOrigin = adsk.core.Point3D.create(neutral.x + offsets[0], neutral.y + offsets[1], neutral.z)

    wasUpdating = _isUpdatingInputs
    _isUpdatingInputs = True
    try:
        _offsetXInput.setManipulator(xOrigin, adsk.core.Vector3D.create(1, 0, 0))
        _offsetYInput.setManipulator(yOrigin, adsk.core.Vector3D.create(0, 1, 0))
        _offsetZInput.setManipulator(zOrigin, adsk.core.Vector3D.create(0, 0, 1))
    finally:
        _isUpdatingInputs = wasUpdating


def buildLatticePoints(
    body: adsk.fusion.BRepBody,
    offsets: list[list[float]]
) -> list[adsk.core.Point3D]:
    """Compute the lattice world positions given a body and offsets."""
    global _gridSizeX, _gridSizeY, _gridSizeZ

    bbox = body.boundingBox
    bboxMinX = bbox.minPoint.x
    bboxMinY = bbox.minPoint.y
    bboxMinZ = bbox.minPoint.z

    epsilon = 1e-6
    sizeX = max(bbox.maxPoint.x - bboxMinX, epsilon)
    sizeY = max(bbox.maxPoint.y - bboxMinY, epsilon)
    sizeZ = max(bbox.maxPoint.z - bboxMinZ, epsilon)

    divisorX = max(_gridSizeX - 1, 1)
    divisorY = max(_gridSizeY - 1, 1)
    divisorZ = max(_gridSizeZ - 1, 1)

    points: list[adsk.core.Point3D] = []

    for i in range(_gridSizeX):
        for j in range(_gridSizeY):
            for k in range(_gridSizeZ):
                idx = i * _gridSizeY * _gridSizeZ + j * _gridSizeZ + k
                if idx < len(offsets):
                    dx, dy, dz = offsets[idx]
                else:
                    dx, dy, dz = 0.0, 0.0, 0.0
                points.append(adsk.core.Point3D.create(
                    bboxMinX + (i / divisorX) * sizeX + dx,
                    bboxMinY + (j / divisorY) * sizeY + dy,
                    bboxMinZ + (k / divisorZ) * sizeZ + dz,
                ))

    return points


def getDefaultLengthUnits() -> str:
    """Return the active design's default length units."""
    design = adsk.fusion.Design.cast(_app.activeProduct)
    if design is not None:
        return design.unitsManager.defaultLengthUnits
    return 'cm'


def formatInternalValue(value: float) -> str:
    """Format an internal (cm) value as an expression in the user's default length units."""
    design = adsk.fusion.Design.cast(_app.activeProduct)
    if design is not None:
        return design.unitsManager.formatInternalValue(value, design.unitsManager.defaultLengthUnits, True)
    return str(value)


def clearLatticeGraphics() -> None:
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


def drawLatticeGraphics(
    latticePoints: list[adsk.core.Point3D],
    selectedIndex: int,
    refreshViewport: bool = True
) -> None:
    """Draw the lattice wireframe and control points as custom graphics."""
    global _gridSizeX, _gridSizeY, _gridSizeZ

    clearLatticeGraphics()

    design = adsk.fusion.Design.cast(_app.activeProduct)
    if design is None:
        return

    cgGroup = design.rootComponent.customGraphicsGroups.add()

    diagonal = latticePoints[0].distanceTo(latticePoints[-1])
    if diagonal < 1e-6:
        diagonal = 1.0

    markerSize = diagonal * constants.FFDConst.controlPointMarkerFraction
    selectedMarkerSize = diagonal * constants.FFDConst.selectedPointMarkerFraction
    labelSize = diagonal * constants.FFDConst.labelSizeFraction

    lineCoords: list[float] = []
    for i in range(_gridSizeX):
        for j in range(_gridSizeY):
            for k in range(_gridSizeZ):
                idx = i * _gridSizeY * _gridSizeZ + j * _gridSizeZ + k
                pt = latticePoints[idx]

                if i < _gridSizeX - 1:
                    nb = latticePoints[(i + 1) * _gridSizeY * _gridSizeZ + j * _gridSizeZ + k]
                    lineCoords.extend([pt.x, pt.y, pt.z, nb.x, nb.y, nb.z])

                if j < _gridSizeY - 1:
                    nb = latticePoints[i * _gridSizeY * _gridSizeZ + (j + 1) * _gridSizeZ + k]
                    lineCoords.extend([pt.x, pt.y, pt.z, nb.x, nb.y, nb.z])

                if k < _gridSizeZ - 1:
                    nb = latticePoints[i * _gridSizeY * _gridSizeZ + j * _gridSizeZ + (k + 1)]
                    lineCoords.extend([pt.x, pt.y, pt.z, nb.x, nb.y, nb.z])

    if lineCoords:
        coords = adsk.fusion.CustomGraphicsCoordinates.create(lineCoords)
        cgLines = cgGroup.addLines(coords, [], False, [])
        r, g, b, a = constants.FFDConst.latticeLineColorRGBA
        cgLines.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(
            adsk.core.Color.create(r, g, b, a)
        )
        cgLines.weight = constants.FFDConst.latticeLineWeight

    normalCoords: list[float] = []
    selectedCoords: list[float] = []

    for idx, pt in enumerate(latticePoints):
        if idx == selectedIndex:
            s = selectedMarkerSize
            selectedCoords.extend([
                pt.x - s, pt.y, pt.z, pt.x + s, pt.y, pt.z,
                pt.x, pt.y - s, pt.z, pt.x, pt.y + s, pt.z,
                pt.x, pt.y, pt.z - s, pt.x, pt.y, pt.z + s,
            ])
        else:
            s = markerSize
            normalCoords.extend([
                pt.x - s, pt.y, pt.z, pt.x + s, pt.y, pt.z,
                pt.x, pt.y - s, pt.z, pt.x, pt.y + s, pt.z,
                pt.x, pt.y, pt.z - s, pt.x, pt.y, pt.z + s,
            ])

    if normalCoords:
        coords = adsk.fusion.CustomGraphicsCoordinates.create(normalCoords)
        markers = cgGroup.addLines(coords, [], False, [])
        r, g, b = constants.FFDConst.normalPointColorRGB
        markers.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(
            adsk.core.Color.create(r, g, b, 255)
        )
        markers.weight = constants.FFDConst.controlPointLineWeight

    if selectedCoords:
        coords = adsk.fusion.CustomGraphicsCoordinates.create(selectedCoords)
        markers = cgGroup.addLines(coords, [], False, [])
        r, g, b = constants.FFDConst.selectedPointColorRGB
        markers.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(
            adsk.core.Color.create(r, g, b, 255)
        )
        markers.weight = constants.FFDConst.selectedPointLineWeight

    if constants.FFDConst.showPointLabels:
        normalLabelColor = adsk.fusion.CustomGraphicsSolidColorEffect.create(
            adsk.core.Color.create(*constants.FFDConst.labelColorRGB, 255)
        )
        billboard = adsk.fusion.CustomGraphicsBillBoard.create(None)

        for idx, pt in enumerate(latticePoints):
            transform = adsk.core.Matrix3D.create()
            transform.translation = pt.asVector()
            cgText = cgGroup.addText(str(idx), 'Arial', labelSize, transform)
            cgText.billBoarding = billboard
            cgText.color = normalLabelColor

    if refreshViewport:
        _app.activeViewport.refresh()


def updateLatticeDisplay(refreshViewport: bool = True) -> None:
    """Recompute lattice positions and redraw custom graphics."""
    global _bodySelectionInput, _controlPointOffsets, _selectedPointIndex

    if _bodySelectionInput is None or _bodySelectionInput.selectionCount != 1:
        clearLatticeGraphics()
        return

    body = adsk.fusion.BRepBody.cast(_bodySelectionInput.selection(0).entity)
    if body is None:
        clearLatticeGraphics()
        return

    latticePoints = buildLatticePoints(body, _controlPointOffsets)
    drawLatticeGraphics(latticePoints, _selectedPointIndex, refreshViewport)


def createFFDPreviewBody() -> Optional[adsk.fusion.BRepBody]:
    """Create a preview body from the current command inputs."""
    global _bodySelectionInput, _controlPointOffsets, _gridSizeX, _gridSizeY, _gridSizeZ

    if _bodySelectionInput.selectionCount != 1:
        return None

    sourceBody = adsk.fusion.BRepBody.cast(_bodySelectionInput.selection(0).entity)
    if sourceBody is None:
        return None

    return Deformations.createFFDBody(sourceBody, _controlPointOffsets, _gridSizeX, _gridSizeY, _gridSizeZ)


class CreateCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Event handler for creating a new FFD command dialog."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.CommandCreatedEventArgs) -> None:
        try:
            global _gridSizeX, _gridSizeY, _gridSizeZ

            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs

            _gridSizeX = constants.FFDConst.defaultGridSize
            _gridSizeY = constants.FFDConst.defaultGridSize
            _gridSizeZ = constants.FFDConst.defaultGridSize

            initializeOffsets()
            initializeCommandInputs(inputs)

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

            onMouseClick = MouseClickHandler()
            command.mouseClick.add(onMouseClick)
            _handlers.append(onMouseClick)

        except:
            showMessage.showMessage(f'CreateCommandCreatedHandler: {traceback.format_exc()}\n', True)


class EditCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Event handler for creating the edit dialog of an existing FFD feature."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.CommandCreatedEventArgs) -> None:
        try:
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs

            global _editedCustomFeature, _controlPointOffsets
            global _gridSizeX, _gridSizeY, _gridSizeZ

            _editedCustomFeature = adsk.fusion.CustomFeature.cast(_ui.activeSelections.item(0).entity)
            if _editedCustomFeature is None:
                return

            gridSizes = getGridSizesFromFeature(_editedCustomFeature)
            _gridSizeX = gridSizes[0]
            _gridSizeY = gridSizes[1]
            _gridSizeZ = gridSizes[2]

            _controlPointOffsets = getOffsetsFromFeature(_editedCustomFeature)

            initializeCommandInputs(inputs)

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

            onMouseClick = MouseClickHandler()
            command.mouseClick.add(onMouseClick)
            _handlers.append(onMouseClick)

        except:
            showMessage.showMessage(f'EditCommandCreatedHandler: {traceback.format_exc()}\n', True)


class ValidateInputsHandler(adsk.core.ValidateInputsEventHandler):
    """Event handler for validating FFD command inputs."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.ValidateInputsEventArgs) -> None:
        global _bodySelectionInput, _offsetXInput, _offsetYInput, _offsetZInput

        try:
            eventArgs = adsk.core.ValidateInputsEventArgs.cast(args)

            if _bodySelectionInput.selectionCount != 1:
                eventArgs.areInputsValid = False
                return

            if not _offsetXInput.isValidExpression:
                eventArgs.areInputsValid = False
                return

            if not _offsetYInput.isValidExpression:
                eventArgs.areInputsValid = False
                return

            if not _offsetZInput.isValidExpression:
                eventArgs.areInputsValid = False
                return

            eventArgs.areInputsValid = True

        except:
            showMessage.showMessage(f'ValidateInputsHandler: {traceback.format_exc()}\n', True)


class InputChangedHandler(adsk.core.InputChangedEventHandler):
    """Event handler for FFD input changes."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.InputChangedEventArgs) -> None:
        global _controlPointOffsets, _selectedPointIndex, _isUpdatingInputs
        global _bodySelectionInput
        global _resolutionXInput, _resolutionYInput, _resolutionZInput
        global _offsetXInput, _offsetYInput, _offsetZInput
        global _gridSizeX, _gridSizeY, _gridSizeZ

        if _isUpdatingInputs:
            return

        try:
            eventArgs = adsk.core.InputChangedEventArgs.cast(args)
            changedInput = eventArgs.input

            if changedInput.id == selectBodyInputDef.id:
                hasBody = _bodySelectionInput.selectionCount == 1
                _resolutionXInput.isVisible = hasBody
                _resolutionYInput.isVisible = hasBody
                _resolutionZInput.isVisible = hasBody
                _offsetXInput.isVisible = hasBody
                _offsetYInput.isVisible = hasBody
                _offsetZInput.isVisible = hasBody
                _resetButtonInput.isVisible = hasBody

                if hasBody:
                    updateManipulatorOrigins()
                    updateLatticeDisplay()
                else:
                    clearLatticeGraphics()

            elif changedInput.id in (offsetXInputDef.id, offsetYInputDef.id, offsetZInputDef.id):
                if (_selectedPointIndex < len(_controlPointOffsets) and
                        _offsetXInput.isValidExpression and
                        _offsetYInput.isValidExpression and
                        _offsetZInput.isValidExpression):
                    newOffsets = [
                        _offsetXInput.value,
                        _offsetYInput.value,
                        _offsetZInput.value,
                    ]
                    if newOffsets != _controlPointOffsets[_selectedPointIndex]:
                        _controlPointOffsets[_selectedPointIndex] = newOffsets
                        updateManipulatorOrigins()
                        updateLatticeDisplay()

            elif changedInput.id in (resolutionXInputDef.id, resolutionYInputDef.id, resolutionZInputDef.id):
                newX = _resolutionXInput.value
                newY = _resolutionYInput.value
                newZ = _resolutionZInput.value

                if newX != _gridSizeX or newY != _gridSizeY or newZ != _gridSizeZ:
                    _gridSizeX = newX
                    _gridSizeY = newY
                    _gridSizeZ = newZ

                    initializeOffsets()
                    _selectedPointIndex = 0

                    _isUpdatingInputs = True
                    try:
                        _offsetXInput.value = 0.0
                        _offsetYInput.value = 0.0
                        _offsetZInput.value = 0.0
                        updateManipulatorOrigins()
                    finally:
                        _isUpdatingInputs = False

                    updateLatticeDisplay()

            elif changedInput.id == resetButtonInputDef.id:
                if showMessage.showConfirmationDialog(
                    strings.FFD.resetConfirmationMessage,
                    strings.FFD.resetConfirmationTitle
                ):
                    initializeOffsets()
                    _selectedPointIndex = 0

                    _isUpdatingInputs = True
                    try:
                        _offsetXInput.value = 0.0
                        _offsetYInput.value = 0.0
                        _offsetZInput.value = 0.0
                        updateManipulatorOrigins()
                    finally:
                        _isUpdatingInputs = False

                    updateLatticeDisplay()

        except:
            showMessage.showMessage(f'InputChangedHandler: {traceback.format_exc()}\n', True)


class ExecutePreviewHandler(adsk.core.CommandEventHandler):
    """Event handler for FFD command preview execution."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.CommandEventArgs) -> None:
        global _hiddenSourceBody

        if _isUpdatingInputs:
            return

        baseFeature: Optional[adsk.fusion.BaseFeature] = None
        isBaseFeatureEditing = False

        try:
            if _bodySelectionInput.selectionCount != 1:
                return

            sourceBody = adsk.fusion.BRepBody.cast(_bodySelectionInput.selection(0).entity)
            if sourceBody is None:
                return

            hasNonZeroOffset = any(
                o[0] != 0.0 or o[1] != 0.0 or o[2] != 0.0 for o in _controlPointOffsets
            )
            if not hasNonZeroOffset:
                updateLatticeDisplay(False)
                return

            resultBody = createFFDPreviewBody()
            if resultBody is None:
                updateLatticeDisplay(False)
                return

            component = sourceBody.parentComponent
            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()
            isBaseFeatureEditing = True

            outputBody = component.bRepBodies.add(resultBody, baseFeature)
            Bodies.copyAttributes(sourceBody, outputBody)
            outputBody.name = strings.FFD.bodyNameTemplate.format(bodyName=sourceBody.name)

            baseFeature.finishEdit()
            isBaseFeatureEditing = False

            sourceBody.isLightBulbOn = False
            _hiddenSourceBody = sourceBody

            updateLatticeDisplay(False)

        except:
            if baseFeature is not None and isBaseFeatureEditing:
                baseFeature.finishEdit()
            updateLatticeDisplay(False)
            showMessage.showMessage(f'ExecutePreviewHandler: {traceback.format_exc()}\n', True)


class CreateExecuteHandler(adsk.core.CommandEventHandler):
    """Event handler for creating an FFD custom feature."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.CommandEventArgs) -> None:
        global _bodySelectionInput, _controlPointOffsets, _customFeatureDefinition, _app, _skipCompute
        global _gridSizeX, _gridSizeY, _gridSizeZ, _hiddenSourceBody

        eventArgs: Optional[adsk.core.CommandEventArgs] = None
        baseFeature: Optional[adsk.fusion.BaseFeature] = None
        isBaseFeatureEditing = False

        try:
            eventArgs = adsk.core.CommandEventArgs.cast(args)

            sourceBody = adsk.fusion.BRepBody.cast(_bodySelectionInput.selection(0).entity)
            if sourceBody is None:
                eventArgs.executeFailed = True
                return

            resultBody = Deformations.createFFDBody(sourceBody, _controlPointOffsets, _gridSizeX, _gridSizeY, _gridSizeZ)
            if resultBody is None:
                showMessage.showMessage(
                    'Failed to create FFD body. The geometry may be too complex.', True
                )
                eventArgs.executeFailed = True
                return

            component = sourceBody.parentComponent
            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()
            isBaseFeatureEditing = True

            outputBody = component.bRepBodies.add(resultBody, baseFeature)
            Bodies.copyAttributes(sourceBody, outputBody)
            outputBody.name = strings.FFD.bodyNameTemplate.format(bodyName=sourceBody.name)

            baseFeature.finishEdit()
            isBaseFeatureEditing = False

            if sourceBody.faces.count == 0:
                eventArgs.executeFailed = True
                return

            customFeatureInput = component.features.customFeatures.createInput(_customFeatureDefinition)
            customFeatureInput.addDependency(strings.FFD.sourceBodyFaceDependencyId, sourceBody.faces.item(0))

            customFeatureInput.setStartAndEndFeatures(baseFeature, baseFeature)

            _skipCompute = True
            try:
                customFeature = component.features.customFeatures.add(customFeatureInput)

                customFeature.attributes.add(
                    strings.FFD.offsetsAttributeGroup,
                    strings.FFD.offsetsAttributeName,
                    json.dumps(_controlPointOffsets)
                )

                customFeature.attributes.add(
                    strings.FFD.offsetsAttributeGroup,
                    strings.FFD.gridSizeAttributeName,
                    json.dumps([_gridSizeX, _gridSizeY, _gridSizeZ])
                )
            finally:
                _skipCompute = False

            sourceBody.isLightBulbOn = False
            _hiddenSourceBody = None

        except:
            if baseFeature is not None and isBaseFeatureEditing:
                baseFeature.finishEdit()

            if eventArgs is not None:
                eventArgs.executeFailed = True
            showMessage.showMessage(f'CreateExecuteHandler: {traceback.format_exc()}\n', True)


class DestroyHandler(adsk.core.CommandEventHandler):
    """Event handler for cleaning up when the FFD create command ends."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.CommandEventArgs) -> None:
        global _hiddenSourceBody

        try:
            clearLatticeGraphics()

            if _hiddenSourceBody is not None:
                _hiddenSourceBody.isLightBulbOn = True
                _hiddenSourceBody = None

        except:
            showMessage.showMessage(f'DestroyHandler: {traceback.format_exc()}\n', True)


class EditActivateHandler(adsk.core.CommandEventHandler):
    """Event handler for activating FFD feature editing."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.CommandEventArgs) -> None:
        try:
            global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature
            global _bodySelectionInput, _controlPointOffsets, _selectedPointIndex
            global _isUpdatingInputs, _gridSizeX, _gridSizeY, _gridSizeZ

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

            sourceBody = getSourceBodyFromFeature(_editedCustomFeature)
            if sourceBody is not None:
                sourceBody.isLightBulbOn = True
                _bodySelectionInput.addSelection(sourceBody)

            _selectedPointIndex = 0
            _controlPointOffsets = getOffsetsFromFeature(_editedCustomFeature)

            _isUpdatingInputs = True
            try:
                _resolutionXInput.value = _gridSizeX
                _resolutionYInput.value = _gridSizeY
                _resolutionZInput.value = _gridSizeZ

                offsets = _controlPointOffsets[0]
                _offsetXInput.expression = formatInternalValue(offsets[0])
                _offsetYInput.expression = formatInternalValue(offsets[1])
                _offsetZInput.expression = formatInternalValue(offsets[2])
                updateManipulatorOrigins()
            finally:
                _isUpdatingInputs = False

            _resolutionXInput.isVisible = True
            _resolutionYInput.isVisible = True
            _resolutionZInput.isVisible = True
            _offsetXInput.isVisible = True
            _offsetYInput.isVisible = True
            _offsetZInput.isVisible = True
            _resetButtonInput.isVisible = True

            updateLatticeDisplay()

        except:
            showMessage.showMessage(f'EditActivateHandler: {traceback.format_exc()}\n', True)


class EditDestroyHandler(adsk.core.CommandEventHandler):
    """Event handler for finishing FFD feature editing."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.CommandEventArgs) -> None:
        try:
            clearLatticeGraphics()

            eventArgs = adsk.core.CommandEventArgs.cast(args)
            if eventArgs.terminationReason != adsk.core.CommandTerminationReason.CompletedTerminationReason:
                sourceBody = getSourceBodyFromFeature(_editedCustomFeature)
                if sourceBody is not None:
                    sourceBody.isLightBulbOn = False

                rollBack()

        except:
            showMessage.showMessage(f'EditDestroyHandler: {traceback.format_exc()}\n', True)


class EditExecuteHandler(adsk.core.CommandEventHandler):
    """Event handler for applying edited FFD feature parameters."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.CommandEventArgs) -> None:
        global _editedCustomFeature, _bodySelectionInput, _controlPointOffsets
        global _gridSizeX, _gridSizeY, _gridSizeZ

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

            if sourceBody is None or sourceBody.faces.count == 0:
                eventArgs.executeFailed = True
                return

            _editedCustomFeature.dependencies.deleteAll()
            _editedCustomFeature.dependencies.add(strings.FFD.sourceBodyFaceDependencyId, sourceBody.faces.item(0))

            attr = _editedCustomFeature.attributes.itemByName(
                strings.FFD.offsetsAttributeGroup, strings.FFD.offsetsAttributeName
            )
            if attr is not None:
                attr.deleteMe()

            _editedCustomFeature.attributes.add(
                strings.FFD.offsetsAttributeGroup,
                strings.FFD.offsetsAttributeName,
                json.dumps(_controlPointOffsets)
            )

            gridAttr = _editedCustomFeature.attributes.itemByName(
                strings.FFD.offsetsAttributeGroup, strings.FFD.gridSizeAttributeName
            )
            if gridAttr is not None:
                gridAttr.deleteMe()

            _editedCustomFeature.attributes.add(
                strings.FFD.offsetsAttributeGroup,
                strings.FFD.gridSizeAttributeName,
                json.dumps([_gridSizeX, _gridSizeY, _gridSizeZ])
            )

            if not updateFeature(_editedCustomFeature):
                eventArgs.executeFailed = True

        except:
            showMessage.showMessage(f'EditExecuteHandler: {traceback.format_exc()}\n', True)

        finally:
            rollBack()


class ComputeCustomFeature(adsk.fusion.CustomFeatureEventHandler):
    """Event handler for computing FFD custom features."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.fusion.CustomFeatureEventArgs) -> None:
        global _skipCompute

        try:
            if _skipCompute:
                return

            eventArgs = adsk.fusion.CustomFeatureEventArgs.cast(args)
            customFeature = eventArgs.customFeature
            updateFeature(customFeature)

        except:
            showMessage.showMessage(f'ComputeCustomFeature: {traceback.format_exc()}\n', True)


def updateFeature(customFeature: adsk.fusion.CustomFeature) -> bool:
    """Recompute the FFD feature output body."""
    baseFeature = CustomFeatures.getBaseFeature(customFeature)
    isBaseFeatureEditing = False

    try:
        if baseFeature is None:
            return False

        component = customFeature.parentComponent
        sourceBody = getSourceBodyFromFeature(customFeature)
        if sourceBody is None:
            return False

        offsets = getOffsetsFromFeature(customFeature)
        gridSizes = getGridSizesFromFeature(customFeature)

        resultBody = Deformations.createFFDBody(sourceBody, offsets, gridSizes[0], gridSizes[1], gridSizes[2])
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
        outputBody.name = strings.FFD.bodyNameTemplate.format(bodyName=sourceBody.name)

        baseFeature.finishEdit()
        isBaseFeatureEditing = False

        sourceBody.isLightBulbOn = False

        return True

    except:
        if baseFeature is not None and isBaseFeatureEditing:
            baseFeature.finishEdit()

        showMessage.showMessage(f'updateFeature: {traceback.format_exc()}\n', True)
        return False


class MouseClickHandler(adsk.core.MouseEventHandler):
    """Event handler for selecting control points by clicking in the 3D viewport."""

    def __init__(self) -> None:
        super().__init__()

    def notify(self, args: adsk.core.MouseEventArgs) -> None:
        global _selectedPointIndex, _isUpdatingInputs
        global _bodySelectionInput
        global _offsetXInput, _offsetYInput, _offsetZInput, _controlPointOffsets

        try:
            if _bodySelectionInput is None or _bodySelectionInput.selectionCount != 1:
                return

            body = adsk.fusion.BRepBody.cast(_bodySelectionInput.selection(0).entity)
            if body is None:
                return

            eventArgs = adsk.core.MouseEventArgs.cast(args)
            viewport = eventArgs.viewport
            if viewport is None:
                return

            viewportPos = eventArgs.viewportPosition
            if viewportPos is None:
                return

            clickX = viewportPos.x
            clickY = viewportPos.y

            latticePoints = buildLatticePoints(body, _controlPointOffsets)

            minDist = float('inf')
            nearestIdx = -1

            for idx, pt in enumerate(latticePoints):
                screenPt = viewport.modelToViewSpace(pt)
                if screenPt is None:
                    continue

                dx = screenPt.x - clickX
                dy = screenPt.y - clickY
                dist = math.sqrt(dx * dx + dy * dy)

                if dist < minDist:
                    minDist = dist
                    nearestIdx = idx

            if nearestIdx < 0 or minDist > constants.FFDConst.pointClickThreshold:
                return

            if nearestIdx >= len(_controlPointOffsets):
                return

            _selectedPointIndex = nearestIdx

            _isUpdatingInputs = True
            try:
                offsets = _controlPointOffsets[nearestIdx]
                _offsetXInput.expression = formatInternalValue(offsets[0])
                _offsetYInput.expression = formatInternalValue(offsets[1])
                _offsetZInput.expression = formatInternalValue(offsets[2])
                updateManipulatorOrigins()
            finally:
                _isUpdatingInputs = False

            updateLatticeDisplay()

        except:
            showMessage.showMessage(f'MouseClickHandler: {traceback.format_exc()}\n', True)


def rollBack() -> None:
    """Restore the timeline after editing an FFD custom feature."""
    global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature, _hiddenSourceBody

    if _isRolledForEdit:
        if _restoreTimelineObject is not None:
            _restoreTimelineObject.rollTo(False)

        _isRolledForEdit = False

    _restoreTimelineObject = None
    _editedCustomFeature = None
    _hiddenSourceBody = None
