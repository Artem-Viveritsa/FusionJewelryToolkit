import os
import adsk.core, adsk.fusion, traceback

from ... import constants
from ...helpers.showMessage import showMessage
from ...helpers.Surface import unfoldFaceToSketch, unfoldMeshToSketch
from ...helpers.Points import getPointGeometry
from ...helpers.Meshes import core as meshCore
from ...helpers.Meshes import isotropic as meshIsotropic
from ...helpers.Meshes import preview as meshPreview

_app: adsk.core.Application = None
_ui: adsk.core.UserInterface = None

_customFeatureDefinition: adsk.fusion.CustomFeature = None

_sourceSelectionInput: adsk.core.SelectionCommandInput = None
_originVertexSelectionInput: adsk.core.SelectionCommandInput = None
_xDirectionVertexSelectionInput: adsk.core.SelectionCommandInput = None
_yDirectionVertexSelectionInput: adsk.core.SelectionCommandInput = None
_constructionPlaneSelectionInput: adsk.core.SelectionCommandInput = None
_xOffsetValueInput: adsk.core.ValueCommandInput = None
_yOffsetValueInput: adsk.core.ValueCommandInput = None
_accuracyValueInput: adsk.core.ValueCommandInput = None
_algorithmDropdownInput: adsk.core.DropDownCommandInput = None

_editedCustomFeature: adsk.fusion.CustomFeature = None
_restoreTimelineObject: adsk.fusion.TimelineObject = None
_isRolledForEdit: bool = False

_previewGraphicsGroup: adsk.fusion.CustomGraphicsGroup | None = None

_handlers = []

createCommandInputDef = constants.InputDef(constants.Unfold.createCommandId, 'Surface Unfold', 'Unfolds a NURBS surface or mesh to a sketch.')
editCommandInputDef = constants.InputDef(constants.Unfold.editCommandId, 'Edit Surface Unfold', 'Edits the parameters of the unfold feature.')

selectSourceInputDef = constants.InputDef(
    constants.Unfold.selectSourceInputId,
    'Select Source',
    'Select the face or mesh body to unfold.'
    )

accuracyInputDef = constants.InputDef(
    constants.Unfold.accuracyValueInputId,
    'Accuracy',
    "Unfolding accuracy (0.5 - 10 mm).\nMinimum allowed is 0.5 mm to avoid excessive computation."
    )

originVertexInputDef = constants.InputDef(
    constants.Unfold.originVertexInputId,
    'Origin Point',
    'Select a vertex or sketch point on the face to be the origin (0,0) of the sketch.'
    )

xDirectionVertexInputDef = constants.InputDef(
    constants.Unfold.xDirectionVertexInputId,
    'X Direction Point',
    'Select a vertex or sketch point on the face to define the +X direction from origin.'
    )

yDirectionVertexInputDef = constants.InputDef(
    constants.Unfold.yDirectionVertexInputId,
    'Y Direction Point',
    'Select a vertex or sketch point on the face to define the rotation (orientation) of the unfolded sketch.'
    )

constructionPlaneInputDef = constants.InputDef(
    constants.Unfold.constructionPlaneInputId,
    'Plane',
    'Select the construction plane where the unfolded sketch will be created.'
    )

xOffsetInputDef = constants.InputDef(
    constants.Unfold.xOffsetValueInputId,
    'X Offset',
    'Offset along the X axis of the construction plane.'
    )

yOffsetInputDef = constants.InputDef(
    constants.Unfold.yOffsetValueInputId,
    'Y Offset',
    'Offset along the Y axis of the construction plane.'
    )

algorithmInputDef = constants.InputDef(
    constants.Unfold.algorithmInputId,
    'Algorithm',
    'Select the unfolding algorithm: NURBS (parametric grid) or Mesh (tessellation).'
    )

RESOURCES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')


def clearPreviewGraphics() -> None:
    """Remove the temporary mesh preview graphics group."""
    global _previewGraphicsGroup

    meshPreview.clearPreviewGraphics(_previewGraphicsGroup)
    _previewGraphicsGroup = None


def buildNurbsGridMeshData(face: adsk.fusion.BRepFace, stepSize: float) -> meshCore.TriangleMeshData | None:
    """Build flat TriangleMeshData from the NURBS parametric grid on the face.

    Args:
        face: The BRep face to sample.
        stepSize: Target edge length in centimetres.

    Returns:
        A TriangleMeshData tuple of flat coordinates and indices, or None on failure.
    """
    try:
        evaluator = face.evaluator
        stepSize = max(0.05, stepSize or 0.1)

        rangeBox = evaluator.parametricRange()
        if rangeBox is None:
            return None

        uMin, uMax = rangeBox.minPoint.x, rangeBox.maxPoint.x
        vMin, vMax = rangeBox.minPoint.y, rangeBox.maxPoint.y

        cornerParams = [
            adsk.core.Point2D.create(uMin, vMin), adsk.core.Point2D.create(uMax, vMin),
            adsk.core.Point2D.create(uMin, vMax), adsk.core.Point2D.create(uMax, vMax)
        ]

        success, cornerPoints = evaluator.getPointsAtParameters(cornerParams)
        if not success or len(cornerPoints) < 4:
            return None

        uDist = (cornerPoints[0].distanceTo(cornerPoints[1]) + cornerPoints[2].distanceTo(cornerPoints[3])) / 2
        vDist = (cornerPoints[0].distanceTo(cornerPoints[2]) + cornerPoints[1].distanceTo(cornerPoints[3])) / 2

        numStepsU = min(max(3, int(uDist / stepSize) + 1), 200)
        numStepsV = min(max(3, int(vDist / stepSize) + 1), 200)

        uStep = (uMax - uMin) / (numStepsU - 1) if numStepsU > 1 else 0
        vStep = (vMax - vMin) / (numStepsV - 1) if numStepsV > 1 else 0

        paramGrid = [
            adsk.core.Point2D.create(uMin + i * uStep, vMin + j * vStep)
            for j in range(numStepsV) for i in range(numStepsU)
        ]

        success, points3D = evaluator.getPointsAtParameters(paramGrid)
        if not success:
            return None

        validData = [
            (idx, points3D[idx])
            for idx, param in enumerate(paramGrid)
            if evaluator.isParameterOnFace(param)
        ]

        if len(validData) < 3:
            return None

        validIndices = [d[0] for d in validData]
        validPoints3D = [d[1] for d in validData]

        gridPositionToValid: dict[tuple[int, int], int] = {}
        for validIndex, originalIndex in enumerate(validIndices):
            i, j = originalIndex % numStepsU, originalIndex // numStepsU
            gridPositionToValid[(i, j)] = validIndex

        triangleIndices: list[int] = []
        for j in range(numStepsV - 1):
            for i in range(numStepsU - 1):
                index00 = gridPositionToValid.get((i, j))
                index10 = gridPositionToValid.get((i + 1, j))
                index01 = gridPositionToValid.get((i, j + 1))
                index11 = gridPositionToValid.get((i + 1, j + 1))

                if index00 is not None and index10 is not None and index01 is not None:
                    triangleIndices.extend([index00, index10, index01])
                if index10 is not None and index11 is not None and index01 is not None:
                    triangleIndices.extend([index10, index11, index01])

        if not triangleIndices:
            return None

        coords: list[float] = []
        for point in validPoints3D:
            coords.extend([point.x, point.y, point.z])

        return meshCore.TriangleMeshData(coords, triangleIndices)

    except:
        return None


def getMeshDataForPreview() -> meshCore.TriangleMeshData | None:
    """Build TriangleMeshData for the currently selected source entity.

    Returns:
        TriangleMeshData for the source, or None if inputs are incomplete or invalid.
    """
    global _sourceSelectionInput, _accuracyValueInput, _algorithmDropdownInput

    if _sourceSelectionInput is None or _sourceSelectionInput.selectionCount == 0:
        return None

    sourceEntity = _sourceSelectionInput.selection(0).entity

    if sourceEntity.objectType == adsk.fusion.MeshBody.classType():
        meshBody = adsk.fusion.MeshBody.cast(sourceEntity)
        displayMesh = meshBody.displayMesh
        if displayMesh is None:
            return None

        return meshCore.triangleMeshToMeshData(displayMesh)

    if _accuracyValueInput is None or not _accuracyValueInput.isValidExpression:
        return None

    accuracy = _accuracyValueInput.value
    if accuracy <= 0:
        return None

    face = adsk.fusion.BRepFace.cast(sourceEntity)
    if face is None:
        return None

    algorithmName = _algorithmDropdownInput.selectedItem.name if _algorithmDropdownInput else None
    try:
        algorithm = constants.UnfoldAlgorithm[algorithmName]
    except (KeyError, AttributeError, TypeError):
        algorithm = constants.UnfoldAlgorithm.Mesh

    if algorithm == constants.UnfoldAlgorithm.Mesh:
        tessellationResult = meshIsotropic.createIsotropicTessellationResult(
            [face],
            accuracy,
            meshIsotropic.IsotropicRemeshSettings(
                constants.MeshRemesh.surfaceTolerance,
                constants.MeshRemesh.maxNormalDeviation,
                constants.MeshRemesh.maxAspectRatio,
                constants.Unfold.meshIsotropicIterationCount,
                constants.Unfold.meshIsotropicSmoothingBlend,
            )
        )
        if tessellationResult is None:
            return None

        return tessellationResult.finalMeshData

    return buildNurbsGridMeshData(face, accuracy)


def updateMeshPreview() -> None:
    """Rebuild the mesh preview graphics from the current command inputs."""
    global _previewGraphicsGroup

    meshData = getMeshDataForPreview()
    _previewGraphicsGroup = meshPreview.updateSimpleMeshPreviewGraphics(_app, _previewGraphicsGroup, meshData)


def run(panel: adsk.core.ToolbarPanel):
    """Initialize the surface unfold command by setting up command definitions and UI elements."""
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
        _customFeatureDefinition = adsk.fusion.CustomFeatureDefinition.create(constants.Unfold.commandId, constants.Unfold.id, RESOURCES_FOLDER)
        _customFeatureDefinition.editCommandId = constants.Unfold.editCommandId

        computeCustomFeature = ComputeCustomFeature()
        _customFeatureDefinition.customFeatureCompute.add(computeCustomFeature)
        _handlers.append(computeCustomFeature)
    except:
        showMessage(f'Run failed:\n{traceback.format_exc()}', True)


def stop(panel: adsk.core.ToolbarPanel):
    """Clean up the surface unfold command by removing UI elements and handlers."""
    try:
        control = panel.controls.itemById(constants.Unfold.createCommandId)
        if control:
            control.deleteMe()

        commandDefinition = _ui.commandDefinitions.itemById(constants.Unfold.createCommandId)
        if commandDefinition:
            commandDefinition.deleteMe()

        commandDefinition = _ui.commandDefinitions.itemById(constants.Unfold.editCommandId)
        if commandDefinition:
            commandDefinition.deleteMe()
    except:
        showMessage(f'Stop Failed:\n{traceback.format_exc()}', True)


def updateVisibility(sourceType: constants.UnfoldSourceType) -> None:
    """Update visibility of inputs according to the selected source type.

    Args:
        sourceType: The type of source (Face or Mesh).
    """
    global _accuracyValueInput, _algorithmDropdownInput

    isMesh = sourceType == constants.UnfoldSourceType.Mesh
    _accuracyValueInput.isVisible = not isMesh
    _algorithmDropdownInput.isVisible = not isMesh


def getSourceTypeFromSelection() -> constants.UnfoldSourceType:
    """Get the source type from the current selection.

    Returns:
        UnfoldSourceType.Mesh if mesh is selected, UnfoldSourceType.Face otherwise.
    """
    global _sourceSelectionInput

    if _sourceSelectionInput.selectionCount == 0:
        return constants.UnfoldSourceType.Face

    entity = _sourceSelectionInput.selection(0).entity
    if entity.objectType == adsk.fusion.MeshBody.classType():
        return constants.UnfoldSourceType.Mesh
    return constants.UnfoldSourceType.Face


def getSourceTypeFromFeature(customFeature: adsk.fusion.CustomFeature) -> constants.UnfoldSourceType:
    """Get the source type from a custom feature.

    Args:
        customFeature: The custom feature to check.

    Returns:
        UnfoldSourceType.Mesh if mesh source, UnfoldSourceType.Face otherwise.
    """
    sourceDep = customFeature.dependencies.itemById(constants.Unfold.sourceDependencyId)
    if sourceDep and sourceDep.entity:
        if sourceDep.entity.objectType == adsk.fusion.MeshBody.classType():
            return constants.UnfoldSourceType.Mesh

    return constants.UnfoldSourceType.Face


class CreateCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Event handler for creating the command dialog for new surface unfold.

    This handler sets up all necessary input controls including selection for face or mesh and
    value input for accuracy, and connects event handlers for validation, preview, and execution.
    """
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs
            defaultLengthUnits = _app.activeProduct.unitsManager.defaultLengthUnits

            global _sourceSelectionInput, _originVertexSelectionInput, _xDirectionVertexSelectionInput, _yDirectionVertexSelectionInput, _accuracyValueInput, _algorithmDropdownInput

            _sourceSelectionInput = inputs.addSelectionInput(selectSourceInputDef.id, selectSourceInputDef.name, selectSourceInputDef.tooltip)
            _sourceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _sourceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.MeshBodies)
            _sourceSelectionInput.tooltip = selectSourceInputDef.tooltip
            _sourceSelectionInput.setSelectionLimits(1, 1)

            inputs.addSeparatorCommandInput('separatorAfterSource')

            _originVertexSelectionInput = inputs.addSelectionInput(originVertexInputDef.id, originVertexInputDef.name, originVertexInputDef.tooltip)
            _originVertexSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Vertices)
            _originVertexSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchPoints)
            _originVertexSelectionInput.tooltip = originVertexInputDef.tooltip
            _originVertexSelectionInput.setSelectionLimits(1, 1)

            _xDirectionVertexSelectionInput = inputs.addSelectionInput(xDirectionVertexInputDef.id, xDirectionVertexInputDef.name, xDirectionVertexInputDef.tooltip)
            _xDirectionVertexSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Vertices)
            _xDirectionVertexSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchPoints)
            _xDirectionVertexSelectionInput.tooltip = xDirectionVertexInputDef.tooltip
            _xDirectionVertexSelectionInput.setSelectionLimits(1, 1)

            _yDirectionVertexSelectionInput = inputs.addSelectionInput(yDirectionVertexInputDef.id, yDirectionVertexInputDef.name, yDirectionVertexInputDef.tooltip)
            _yDirectionVertexSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Vertices)
            _yDirectionVertexSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchPoints)
            _yDirectionVertexSelectionInput.tooltip = yDirectionVertexInputDef.tooltip
            _yDirectionVertexSelectionInput.setSelectionLimits(1, 1)

            inputs.addSeparatorCommandInput('separatorAfterDirectionVertices')

            global _constructionPlaneSelectionInput, _xOffsetValueInput, _yOffsetValueInput

            _constructionPlaneSelectionInput = inputs.addSelectionInput(constructionPlaneInputDef.id, constructionPlaneInputDef.name, constructionPlaneInputDef.tooltip)
            _constructionPlaneSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.ConstructionPlanes)
            _constructionPlaneSelectionInput.tooltip = constructionPlaneInputDef.tooltip
            _constructionPlaneSelectionInput.setSelectionLimits(1, 1)

            xOffset = adsk.core.ValueInput.createByReal(0.0)
            _xOffsetValueInput = inputs.addValueInput(xOffsetInputDef.id, xOffsetInputDef.name, defaultLengthUnits, xOffset)
            _xOffsetValueInput.tooltip = xOffsetInputDef.tooltip

            yOffset = adsk.core.ValueInput.createByReal(0.0)
            _yOffsetValueInput = inputs.addValueInput(yOffsetInputDef.id, yOffsetInputDef.name, defaultLengthUnits, yOffset)
            _yOffsetValueInput.tooltip = yOffsetInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterOffsets')

            accuracy = adsk.core.ValueInput.createByReal(0.5)
            _accuracyValueInput = inputs.addValueInput(accuracyInputDef.id, accuracyInputDef.name, defaultLengthUnits, accuracy)
            _accuracyValueInput.tooltip = accuracyInputDef.tooltip

            _algorithmDropdownInput = inputs.addDropDownCommandInput(algorithmInputDef.id, algorithmInputDef.name, adsk.core.DropDownStyles.TextListDropDownStyle)
            _algorithmDropdownInput.tooltip = algorithmInputDef.tooltip
            for i, algoName in enumerate(constants.Unfold.algorithms):
                _algorithmDropdownInput.listItems.add(algoName, i == 0)

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

            onDestroy = CreateDestroyHandler()
            command.destroy.add(onDestroy)
            _handlers.append(onDestroy)

        except:
            showMessage(f'CreateCommandCreatedHandler: {traceback.format_exc()}\n', True)


class EditCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Event handler for creating the command dialog for editing existing surface unfold.

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

            global _editedCustomFeature, _sourceSelectionInput, _originVertexSelectionInput, _xDirectionVertexSelectionInput, _yDirectionVertexSelectionInput, _accuracyValueInput, _algorithmDropdownInput
            _editedCustomFeature = _ui.activeSelections.item(0).entity
            if _editedCustomFeature is None:
                return

            _sourceSelectionInput = inputs.addSelectionInput(selectSourceInputDef.id, selectSourceInputDef.name, selectSourceInputDef.tooltip)
            _sourceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _sourceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.MeshBodies)
            _sourceSelectionInput.tooltip = selectSourceInputDef.tooltip
            _sourceSelectionInput.setSelectionLimits(1, 1)

            inputs.addSeparatorCommandInput('separatorAfterSource')

            _originVertexSelectionInput = inputs.addSelectionInput(originVertexInputDef.id, originVertexInputDef.name, originVertexInputDef.tooltip)
            _originVertexSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Vertices)
            _originVertexSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchPoints)
            _originVertexSelectionInput.tooltip = originVertexInputDef.tooltip
            _originVertexSelectionInput.setSelectionLimits(1, 1)

            _xDirectionVertexSelectionInput = inputs.addSelectionInput(xDirectionVertexInputDef.id, xDirectionVertexInputDef.name, xDirectionVertexInputDef.tooltip)
            _xDirectionVertexSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Vertices)
            _xDirectionVertexSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchPoints)
            _xDirectionVertexSelectionInput.tooltip = xDirectionVertexInputDef.tooltip
            _xDirectionVertexSelectionInput.setSelectionLimits(1, 1)

            _yDirectionVertexSelectionInput = inputs.addSelectionInput(yDirectionVertexInputDef.id, yDirectionVertexInputDef.name, yDirectionVertexInputDef.tooltip)
            _yDirectionVertexSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Vertices)
            _yDirectionVertexSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchPoints)
            _yDirectionVertexSelectionInput.tooltip = yDirectionVertexInputDef.tooltip
            _yDirectionVertexSelectionInput.setSelectionLimits(1, 1)

            inputs.addSeparatorCommandInput('separatorAfterDirectionVertices')

            global _constructionPlaneSelectionInput, _xOffsetValueInput, _yOffsetValueInput

            _constructionPlaneSelectionInput = inputs.addSelectionInput(constructionPlaneInputDef.id, constructionPlaneInputDef.name, constructionPlaneInputDef.tooltip)
            _constructionPlaneSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.ConstructionPlanes)
            _constructionPlaneSelectionInput.tooltip = constructionPlaneInputDef.tooltip
            _constructionPlaneSelectionInput.setSelectionLimits(1, 1)

            parameters = _editedCustomFeature.parameters

            xOffset = adsk.core.ValueInput.createByString(parameters.itemById(xOffsetInputDef.id).expression)
            _xOffsetValueInput = inputs.addValueInput(xOffsetInputDef.id, xOffsetInputDef.name, defaultLengthUnits, xOffset)
            _xOffsetValueInput.tooltip = xOffsetInputDef.tooltip

            yOffset = adsk.core.ValueInput.createByString(parameters.itemById(yOffsetInputDef.id).expression)
            _yOffsetValueInput = inputs.addValueInput(yOffsetInputDef.id, yOffsetInputDef.name, defaultLengthUnits, yOffset)
            _yOffsetValueInput.tooltip = yOffsetInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterOffsets')

            accuracy = adsk.core.ValueInput.createByString(parameters.itemById(accuracyInputDef.id).expression)
            _accuracyValueInput = inputs.addValueInput(accuracyInputDef.id, accuracyInputDef.name, defaultLengthUnits, accuracy)
            _accuracyValueInput.tooltip = accuracyInputDef.tooltip

            _algorithmDropdownInput = inputs.addDropDownCommandInput(algorithmInputDef.id, algorithmInputDef.name, adsk.core.DropDownStyles.TextListDropDownStyle)
            _algorithmDropdownInput.tooltip = algorithmInputDef.tooltip
            for i, algoName in enumerate(constants.Unfold.algorithms):
                _algorithmDropdownInput.listItems.add(algoName, False)

            try:
                algorithmParam = parameters.itemById(algorithmInputDef.id)
                val = algorithmParam.value
                try:
                    selectedIndex = int(val)
                except:
                    name = str(val).strip()
                    matched = None
                    for member in constants.UnfoldAlgorithm:
                        if member.name.lower() == name.lower():
                            matched = member
                            break
                    selectedIndex = matched.value if matched is not None else constants.UnfoldAlgorithm.Mesh.value

                if 0 <= selectedIndex < _algorithmDropdownInput.listItems.count:
                    _algorithmDropdownInput.listItems.item(selectedIndex).isSelected = True
                else:
                    _algorithmDropdownInput.listItems.item(0).isSelected = True
            except:
                _algorithmDropdownInput.listItems.item(0).isSelected = True

            sourceType = getSourceTypeFromFeature(_editedCustomFeature)
            updateVisibility(sourceType)

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
            showMessage(f'EditCommandCreatedHandler: {traceback.format_exc()}\n', True)


class PreSelectHandler(adsk.core.SelectionEventHandler):
    """Event handler for controlling user selection during command execution.

    This handler checks to ensure the selected face or mesh is valid.
    """
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.SelectionEventArgs.cast(args)
            entity = eventArgs.selection.entity
            entityType = entity.objectType

            if entityType == adsk.fusion.BRepFace.classType():
                if entity is None:
                    eventArgs.isSelectable = False
                    return
            elif entityType == adsk.fusion.MeshBody.classType():
                if entity is None:
                    eventArgs.isSelectable = False
                    return

        except:
            showMessage(f'PreSelectHandler: {traceback.format_exc()}\n', True)


class ValidateInputsHandler(adsk.core.ValidateInputsEventHandler):
    """Event handler for the validateInputs event."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        global _sourceSelectionInput, _accuracyValueInput, _originVertexSelectionInput, _xDirectionVertexSelectionInput, _yDirectionVertexSelectionInput, _constructionPlaneSelectionInput, _xOffsetValueInput, _yOffsetValueInput
        try:
            eventArgs = adsk.core.ValidateInputsEventArgs.cast(args)

            if _sourceSelectionInput.selectionCount != 1:
                eventArgs.areInputsValid = False
                return

            if _originVertexSelectionInput.selectionCount != 1:
                eventArgs.areInputsValid = False
                return

            if _xDirectionVertexSelectionInput.selectionCount != 1:
                eventArgs.areInputsValid = False
                return

            if _yDirectionVertexSelectionInput.selectionCount != 1:
                eventArgs.areInputsValid = False
                return

            if _constructionPlaneSelectionInput.selectionCount != 1:
                eventArgs.areInputsValid = False
                return

            if not _xOffsetValueInput.isValidExpression:
                eventArgs.areInputsValid = False
                return

            if not _yOffsetValueInput.isValidExpression:
                eventArgs.areInputsValid = False
                return

            sourceEntity = _sourceSelectionInput.selection(0).entity
            isMesh = sourceEntity.objectType == adsk.fusion.MeshBody.classType()

            if not isMesh:
                if not _accuracyValueInput.isValidExpression:
                    eventArgs.areInputsValid = False
                    return

                accuracy = _accuracyValueInput.value
                if accuracy < 0.05 or accuracy > 1.0:
                    eventArgs.areInputsValid = False
                    return

        except:
            showMessage(f'ValidateInputsHandler: {traceback.format_exc()}\n', True)


class InputChangedHandler(adsk.core.InputChangedEventHandler):
    """Event handler for the inputChanged event."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.InputChangedEventArgs.cast(args)
            changedInput = eventArgs.input

            if changedInput.id == selectSourceInputDef.id:
                sourceType = getSourceTypeFromSelection()
                updateVisibility(sourceType)

            if changedInput.id in (selectSourceInputDef.id, accuracyInputDef.id, algorithmInputDef.id):
                updateMeshPreview()

        except:
            showMessage(f'InputChangedHandler: {traceback.format_exc()}\n', True)


class ExecutePreviewHandler(adsk.core.CommandEventHandler):
    """Event handler for the executePreview event."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        global _sourceSelectionInput, _accuracyValueInput, _originVertexSelectionInput, _xDirectionVertexSelectionInput, _yDirectionVertexSelectionInput, _algorithmDropdownInput, _constructionPlaneSelectionInput, _xOffsetValueInput, _yOffsetValueInput
        try:
            eventArgs = adsk.core.CommandEventArgs.cast(args)

            sourceEntity = _sourceSelectionInput.selection(0).entity
            originPoint = getPointGeometry(_originVertexSelectionInput.selection(0).entity)
            xDirPoint = getPointGeometry(_xDirectionVertexSelectionInput.selection(0).entity)
            yDirPoint = getPointGeometry(_yDirectionVertexSelectionInput.selection(0).entity)
            constructionPlane = _constructionPlaneSelectionInput.selection(0).entity
            xOffset = _xOffsetValueInput.value
            yOffset = _yOffsetValueInput.value

            isMesh = sourceEntity.objectType == adsk.fusion.MeshBody.classType()

            if isMesh:
                meshBody: adsk.fusion.MeshBody = sourceEntity
                component = meshBody.parentComponent
            else:
                face: adsk.fusion.BRepFace = sourceEntity
                component = face.body.parentComponent

            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()

            sketches = component.sketches
            sketch = sketches.add(component.xYConstructionPlane)
            sketch.name = "Unfolded Surface"

            if isMesh:
                unfoldMeshToSketch(meshBody.displayMesh, sketch, originPoint, xDirPoint, yDirPoint, constructionPlane, xOffset, yOffset)

            else:
                accuracy = _accuracyValueInput.value
                algorithmName = _algorithmDropdownInput.selectedItem.name
                try:
                    algorithm = constants.UnfoldAlgorithm[algorithmName]
                except (KeyError, AttributeError):
                    algorithm = constants.UnfoldAlgorithm.Mesh
                unfoldFaceToSketch(face, accuracy, sketch, originPoint, xDirPoint, yDirPoint, constructionPlane, xOffset, yOffset, algorithm)

            baseFeature.finishEdit()
            updateMeshPreview()

        except:
            baseFeature.finishEdit()
            showMessage(f'ExecutePreviewHandler: {traceback.format_exc()}\n', True)


class CreateExecuteHandler(adsk.core.CommandEventHandler):
    """Event handler for the execute event of the create command."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        global _sourceSelectionInput, _accuracyValueInput, _originVertexSelectionInput, _xDirectionVertexSelectionInput, _yDirectionVertexSelectionInput, _algorithmDropdownInput, _customFeatureDefinition, _app, _constructionPlaneSelectionInput, _xOffsetValueInput, _yOffsetValueInput
        try:
            eventArgs = adsk.core.CommandEventArgs.cast(args)

            sourceEntity = _sourceSelectionInput.selection(0).entity
            originVertex = _originVertexSelectionInput.selection(0).entity
            xDirVertex = _xDirectionVertexSelectionInput.selection(0).entity
            yDirVertex = _yDirectionVertexSelectionInput.selection(0).entity
            constructionPlane = _constructionPlaneSelectionInput.selection(0).entity
            xOffset = _xOffsetValueInput.value
            yOffset = _yOffsetValueInput.value

            originPoint = getPointGeometry(originVertex)
            xDirPoint = getPointGeometry(xDirVertex)
            yDirPoint = getPointGeometry(yDirVertex)

            isMesh = sourceEntity.objectType == adsk.fusion.MeshBody.classType()

            if isMesh:
                meshBody: adsk.fusion.MeshBody = sourceEntity
                comp = meshBody.parentComponent
            else:
                face: adsk.fusion.BRepFace = sourceEntity
                comp = face.body.parentComponent

            baseFeature = comp.features.baseFeatures.add()
            baseFeature.startEdit()

            sketches = comp.sketches
            sketch = sketches.add(comp.xYConstructionPlane)
            sketch.name = "Unfolded Surface"

            if isMesh:
                unfoldMeshToSketch(meshBody.displayMesh, sketch, originPoint, xDirPoint, yDirPoint, constructionPlane, xOffset, yOffset)
            else:
                accuracy = _accuracyValueInput.value
                algorithmName = _algorithmDropdownInput.selectedItem.name
                try:
                    algorithm = constants.UnfoldAlgorithm[algorithmName]
                except:
                    algorithm = constants.UnfoldAlgorithm.Mesh
                unfoldFaceToSketch(face, accuracy, sketch, originPoint, xDirPoint, yDirPoint, constructionPlane, xOffset, yOffset, algorithm)

            baseFeature.finishEdit()

            design: adsk.fusion.Design = _app.activeProduct
            defLengthUnits = design.unitsManager.defaultLengthUnits
            customFeatureInput = comp.features.customFeatures.createInput(_customFeatureDefinition)

            customFeatureInput.addDependency(constants.Unfold.sourceDependencyId, sourceEntity)

            if not isMesh:
                accuracyInput = adsk.core.ValueInput.createByString(_accuracyValueInput.expression)
                customFeatureInput.addCustomParameter(accuracyInputDef.id, accuracyInputDef.name, accuracyInput,
                                                  defLengthUnits, True)

                algorithmIndex = adsk.core.ValueInput.createByReal(_algorithmDropdownInput.selectedItem.index)
                customFeatureInput.addCustomParameter(algorithmInputDef.id, algorithmInputDef.name, algorithmIndex, '', False)

            customFeatureInput.addDependency(constants.Unfold.constructionPlaneDependencyId, constructionPlane)

            xOffsetInput = adsk.core.ValueInput.createByString(_xOffsetValueInput.expression)
            customFeatureInput.addCustomParameter(xOffsetInputDef.id, xOffsetInputDef.name, xOffsetInput, defLengthUnits, True)

            yOffsetInput = adsk.core.ValueInput.createByString(_yOffsetValueInput.expression)
            customFeatureInput.addCustomParameter(yOffsetInputDef.id, yOffsetInputDef.name, yOffsetInput, defLengthUnits, True)

            customFeatureInput.addDependency(constants.Unfold.originVertexDependencyId, originVertex)
            customFeatureInput.addDependency(constants.Unfold.xDirectionVertexDependencyId, xDirVertex)
            customFeatureInput.addDependency(constants.Unfold.yDirectionVertexDependencyId, yDirVertex)

            customFeatureInput.setStartAndEndFeatures(baseFeature, baseFeature)
            comp.features.customFeatures.add(customFeatureInput)

        except:
            baseFeature.finishEdit()
            eventArgs.executeFailed = True
            showMessage(f'CreateExecuteHandler: {traceback.format_exc()}\n', True)


class CreateDestroyHandler(adsk.core.CommandEventHandler):
    """Clean up preview graphics when the create command is closed."""

    def __init__(self):
        super().__init__()

    def notify(self, args: adsk.core.CommandEventArgs) -> None:
        try:
            clearPreviewGraphics()
        except:
            showMessage(f'CreateDestroyHandler: {traceback.format_exc()}\n', True)


class EditActivateHandler(adsk.core.CommandEventHandler):
    """Event handler for the activate event."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature
            global _sourceSelectionInput, _originVertexSelectionInput, _xDirectionVertexSelectionInput, _yDirectionVertexSelectionInput, _constructionPlaneSelectionInput

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

            sourceDep = _editedCustomFeature.dependencies.itemById(constants.Unfold.sourceDependencyId)
            if sourceDep and sourceDep.entity:
                _sourceSelectionInput.addSelection(sourceDep.entity)

            sourceType = getSourceTypeFromSelection()

            originVertexDep = _editedCustomFeature.dependencies.itemById(constants.Unfold.originVertexDependencyId)
            if originVertexDep and originVertexDep.entity:
                _originVertexSelectionInput.addSelection(originVertexDep.entity)

            xDirVertexDep = _editedCustomFeature.dependencies.itemById(constants.Unfold.xDirectionVertexDependencyId)
            if xDirVertexDep and xDirVertexDep.entity:
                _xDirectionVertexSelectionInput.addSelection(xDirVertexDep.entity)

            yDirVertexDep = _editedCustomFeature.dependencies.itemById(constants.Unfold.yDirectionVertexDependencyId)
            if yDirVertexDep and yDirVertexDep.entity:
                _yDirectionVertexSelectionInput.addSelection(yDirVertexDep.entity)

            constructionPlaneDep = _editedCustomFeature.dependencies.itemById(constants.Unfold.constructionPlaneDependencyId)
            if constructionPlaneDep and constructionPlaneDep.entity:
                _constructionPlaneSelectionInput.addSelection(constructionPlaneDep.entity)

            updateVisibility(sourceType)
            updateMeshPreview()

        except:
            showMessage(f'EditActivateHandler: {traceback.format_exc()}\n', True)


class EditDestroyHandler(adsk.core.CommandEventHandler):
    """Event handler for the destroy event of the edit command."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            clearPreviewGraphics()
            eventArgs = adsk.core.CommandEventArgs.cast(args)
            if eventArgs.terminationReason != adsk.core.CommandTerminationReason.CompletedTerminationReason:
                rollBack()
        except:
            showMessage(f'EditDestroyHandler: {traceback.format_exc()}\n', True)


class EditExecuteHandler(adsk.core.CommandEventHandler):
    """Event handler for the execute event of the edit command."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        global _editedCustomFeature, _isRolledForEdit
        global _sourceSelectionInput, _originVertexSelectionInput, _xDirectionVertexSelectionInput, _yDirectionVertexSelectionInput, _accuracyValueInput, _algorithmDropdownInput, _constructionPlaneSelectionInput, _xOffsetValueInput, _yOffsetValueInput

        try:
            eventArgs = adsk.core.CommandEventArgs.cast(args)

            sourceEntity = _sourceSelectionInput.selection(0).entity
            originVertex = _originVertexSelectionInput.selection(0).entity
            xDirVertex = _xDirectionVertexSelectionInput.selection(0).entity
            yDirVertex = _yDirectionVertexSelectionInput.selection(0).entity
            constructionPlane = _constructionPlaneSelectionInput.selection(0).entity

            isMesh = sourceEntity.objectType == adsk.fusion.MeshBody.classType()

            _editedCustomFeature.dependencies.deleteAll()

            _editedCustomFeature.dependencies.add(constants.Unfold.sourceDependencyId, sourceEntity)

            if not isMesh:
                try:
                    _editedCustomFeature.parameters.itemById(accuracyInputDef.id).expression = _accuracyValueInput.expression
                    _editedCustomFeature.parameters.itemById(algorithmInputDef.id).value = _algorithmDropdownInput.selectedItem.index
                except:
                    pass

            _editedCustomFeature.dependencies.add(constants.Unfold.constructionPlaneDependencyId, constructionPlane)

            try:
                _editedCustomFeature.parameters.itemById(xOffsetInputDef.id).expression = _xOffsetValueInput.expression
                _editedCustomFeature.parameters.itemById(yOffsetInputDef.id).expression = _yOffsetValueInput.expression
            except:
                pass

            _editedCustomFeature.dependencies.add(constants.Unfold.originVertexDependencyId, originVertex)
            _editedCustomFeature.dependencies.add(constants.Unfold.xDirectionVertexDependencyId, xDirVertex)
            _editedCustomFeature.dependencies.add(constants.Unfold.yDirectionVertexDependencyId, yDirVertex)

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
    """Update the sketch of an existing custom surface unfold feature.

    Args:
        customFeature: The custom feature to update.

    Returns:
        True if the update was successful, False otherwise.
    """
    try:
        component = customFeature.parentComponent
        baseFeature: adsk.fusion.BaseFeature = None
        sketch: adsk.fusion.Sketch = None

        for feature in customFeature.features:
            if feature.objectType == adsk.fusion.BaseFeature.classType():
                baseFeature = feature
                break
        if baseFeature is None: return False

        for sk in baseFeature.sketches:
            sketch = sk
            break
        if sketch is None: return False

        sourceType = getSourceTypeFromFeature(customFeature)
        isMesh = sourceType == constants.UnfoldSourceType.Mesh

        source = customFeature.dependencies.itemById(constants.Unfold.sourceDependencyId).entity

        if source is None:
            baseFeature.finishEdit()
            return False

        originVertex = customFeature.dependencies.itemById(constants.Unfold.originVertexDependencyId).entity
        xDirVertex = customFeature.dependencies.itemById(constants.Unfold.xDirectionVertexDependencyId).entity
        yDirVertex = customFeature.dependencies.itemById(constants.Unfold.yDirectionVertexDependencyId).entity

        originPoint = getPointGeometry(originVertex)
        xDirPoint = getPointGeometry(xDirVertex)
        yDirPoint = getPointGeometry(yDirVertex)

        constructionPlaneDep = customFeature.dependencies.itemById(constants.Unfold.constructionPlaneDependencyId)
        if constructionPlaneDep and constructionPlaneDep.entity:
            constructionPlane = constructionPlaneDep.entity
        else:
            constructionPlane = component.xYConstructionPlane

        try:
            xOffset = customFeature.parameters.itemById(xOffsetInputDef.id).value
        except:
            xOffset = 0.0

        try:
            yOffset = customFeature.parameters.itemById(yOffsetInputDef.id).value
        except:
            yOffset = 0.0


        baseFeature.startEdit()

        curvesToDelete = [curve for curve in sketch.sketchCurves]
        for curve in curvesToDelete:
            curve.deleteMe()

        pointsToDelete = [p for p in sketch.sketchPoints]
        for p in pointsToDelete:
            try:
                p.deleteMe()
            except:
                pass

        if isMesh:
            meshBody: adsk.fusion.MeshBody = source
            unfoldMeshToSketch(meshBody.displayMesh, sketch, originPoint, xDirPoint, yDirPoint, constructionPlane, xOffset, yOffset)
        else:
            faceEntity: adsk.fusion.BRepFace = source

            try:
                accuracy = customFeature.parameters.itemById(accuracyInputDef.id).value
            except:
                accuracy = 0.5

            try:
                algorithmVal = customFeature.parameters.itemById(algorithmInputDef.id).value
                try:
                    algorithmIndex = int(algorithmVal)
                    algorithmEnumList = list(constants.UnfoldAlgorithm)
                    if 0 <= algorithmIndex < len(algorithmEnumList):
                        algorithm = algorithmEnumList[algorithmIndex]
                    else:
                        algorithm = constants.UnfoldAlgorithm.Mesh
                except (ValueError, TypeError):
                    algorithmName = str(algorithmVal).strip()
                    match = None
                    for member in constants.UnfoldAlgorithm:
                        if member.name.lower() == algorithmName.lower():
                            match = member
                            break
                    algorithm = match if match is not None else constants.UnfoldAlgorithm.Mesh
            except:
                algorithm = constants.UnfoldAlgorithm.Mesh

            unfoldFaceToSketch(faceEntity, accuracy, sketch, originPoint, xDirPoint, yDirPoint, constructionPlane, xOffset, yOffset, algorithm)

        baseFeature.finishEdit()

        return True

    except:
        baseFeature.finishEdit()
        showMessage(f'updateFeature: {traceback.format_exc()}\n', True)
        return False


def rollBack():
    """Roll back the timeline to the state before editing."""
    global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature

    if _isRolledForEdit:
        _restoreTimelineObject.rollTo(False)
        _isRolledForEdit = False

    _editedCustomFeature = None
