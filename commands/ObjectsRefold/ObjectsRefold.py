import os
from typing import List
import adsk.core, adsk.fusion, traceback

from ... import strings
from ...helpers.showMessage import showMessage
from ...helpers.Surface import refoldBodiesToSurface
from ...helpers.Points import getPointGeometry


_handlers = []

_app: adsk.core.Application = None
_ui: adsk.core.UserInterface = None

_customFeatureDefinition: adsk.fusion.CustomFeature = None

_editedCustomFeature: adsk.fusion.CustomFeature = None
_restoreTimelineObject: adsk.fusion.TimelineObject = None
_isRolledForEdit: bool = False

_sketchSelectionInput: adsk.core.SelectionCommandInput = None
_bodiesSelectionInput: adsk.core.SelectionCommandInput = None

RESOURCES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

COMMAND_ID = strings.PREFIX + strings.ObjectsRefold.objectsRefoldCommandId
CREATE_COMMAND_ID = COMMAND_ID + 'Create'
EDIT_COMMAND_ID = COMMAND_ID + 'Edit'

createCommandInputDef = strings.InputDef(CREATE_COMMAND_ID, 'Objects Refold', 'Transfers bodies from unfolded sketch plane to the original surface.')
editCommandInputDef = strings.InputDef(EDIT_COMMAND_ID, 'Edit Objects Refold', 'Edits the parameters of the objects refold feature.')

selectSketchInputDef = strings.InputDef(
    strings.ObjectsRefold.selectSketchInputId,
    'Select Sketch',
    'Select the sketch created by Surface Unfold command.'
)

selectBodiesInputDef = strings.InputDef(
    strings.ObjectsRefold.selectBodiesInputId,
    'Select Bodies',
    'Select bodies to transfer to the surface (minimum 1).'
)


def run(panel: adsk.core.ToolbarPanel):
    """Initialize the objects refold command by setting up command definitions and UI elements."""
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

        _customFeatureDefinition = adsk.fusion.CustomFeatureDefinition.create(COMMAND_ID, strings.ObjectsRefold.objectsRefoldCommandId, RESOURCES_FOLDER)
        _customFeatureDefinition.editCommandId = EDIT_COMMAND_ID

        computeCustomFeature = ComputeCustomFeature()
        _customFeatureDefinition.customFeatureCompute.add(computeCustomFeature)
        _handlers.append(computeCustomFeature)
    except:
        showMessage(f'Run failed:\n{traceback.format_exc()}', True)


def stop(panel: adsk.core.ToolbarPanel):
    """Clean up the cutters command by removing UI elements and handlers."""
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


def getSurfaceUnfoldFeatureFromSketch(sketch: adsk.fusion.Sketch) -> adsk.fusion.CustomFeature:
    """
    Find the SurfaceUnfold custom feature that created this sketch.
    
    Args:
        sketch: The sketch to find the parent custom feature for.
    
    Returns:
        The CustomFeature if found, None otherwise.
    """
    try:
        nativeSketch = sketch.nativeObject if sketch.nativeObject else sketch
        sketchToken = nativeSketch.entityToken
        
        component = nativeSketch.parentComponent
        
        for feature in component.features.customFeatures:
            if feature.name.startswith(strings.Unfold.surfaceUnfoldCommandId):
                for subFeature in feature.features:
                    if subFeature.objectType == adsk.fusion.BaseFeature.classType():
                        baseFeature = adsk.fusion.BaseFeature.cast(subFeature)
                        for sk in baseFeature.sketches:
                            if sk.entityToken == sketchToken:
                                return feature
        return None
    except:
        return None


def getDepsFromSurfaceUnfoldFeature(customFeature: adsk.fusion.CustomFeature) -> tuple[adsk.fusion.BRepFace | adsk.fusion.MeshBody | None, adsk.core.Point3D, adsk.core.Point3D, adsk.core.Point3D, bool, adsk.fusion.ConstructionPlane | None]:
    """
    Get the source entity (face or mesh) and vertex dependencies from a SurfaceUnfold custom feature.
    
    Args:
        customFeature: The SurfaceUnfold custom feature.
    
    Returns:
        A tuple containing (sourceEntity, originPoint, xDirPoint, yDirPoint, isMesh, constructionPlane).
        sourceEntity can be BRepFace or MeshBody.
        Elements can be None if not found.
    """
    try:
        sourceEntity = None
        isMesh = False
        
        sourceDep = customFeature.dependencies.itemById(strings.Unfold.sourceDependencyId)
        if sourceDep and sourceDep.entity:
            sourceEntity = sourceDep.entity
            isMesh = sourceEntity.objectType == adsk.fusion.MeshBody.classType()
        
        originDep = customFeature.dependencies.itemById(strings.Unfold.originVertexDependencyId)
        originVertex = originDep.entity if originDep else None
        
        xDirDep = customFeature.dependencies.itemById(strings.Unfold.xDirectionVertexDependencyId)
        xDirVertex = xDirDep.entity if xDirDep else None
        
        yDirDep = customFeature.dependencies.itemById(strings.Unfold.yDirectionVertexDependencyId)
        yDirVertex = yDirDep.entity if yDirDep else None
        
        originPoint = getPointGeometry(originVertex) if originVertex else None
        xDirPoint = getPointGeometry(xDirVertex) if xDirVertex else None
        yDirPoint = getPointGeometry(yDirVertex) if yDirVertex else None

        constructionPlaneDep = customFeature.dependencies.itemById(strings.Unfold.constructionPlaneDependencyId)
        constructionPlane = constructionPlaneDep.entity if constructionPlaneDep else None

        return sourceEntity, originPoint, xDirPoint, yDirPoint, isMesh, constructionPlane
    except:
        return None, None, None, None, False, None


class CreateCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Event handler for creating the command dialog for new objects refold.
    
    This handler sets up all necessary input controls including selection for sketch and bodies,
    and connects event handlers for validation, preview, and execution.
    """
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs

            global _sketchSelectionInput, _bodiesSelectionInput

            _bodiesSelectionInput = inputs.addSelectionInput(
                selectBodiesInputDef.id,
                selectBodiesInputDef.name,
                selectBodiesInputDef.tooltip
            )
            _bodiesSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SolidBodies)
            _bodiesSelectionInput.tooltip = selectBodiesInputDef.tooltip
            _bodiesSelectionInput.setSelectionLimits(1, 0)

            _sketchSelectionInput = inputs.addSelectionInput(
                selectSketchInputDef.id,
                selectSketchInputDef.name,
                selectSketchInputDef.tooltip
            )
            _sketchSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Sketches)
            _sketchSelectionInput.tooltip = selectSketchInputDef.tooltip
            _sketchSelectionInput.setSelectionLimits(1, 1)

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
    """Event handler for creating the command dialog for editing existing objects refold.
    
    This handler retrieves the selected custom feature, populates inputs with existing
    dependencies, and connects event handlers for editing operations.
    """
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs

            global _editedCustomFeature, _sketchSelectionInput, _bodiesSelectionInput
            _editedCustomFeature = _ui.activeSelections.item(0).entity
            if _editedCustomFeature is None:
                return

            _bodiesSelectionInput = inputs.addSelectionInput(
                selectBodiesInputDef.id,
                selectBodiesInputDef.name,
                selectBodiesInputDef.tooltip
            )
            _bodiesSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SolidBodies)
            _bodiesSelectionInput.tooltip = selectBodiesInputDef.tooltip
            _bodiesSelectionInput.setSelectionLimits(1, 0)

            _sketchSelectionInput = inputs.addSelectionInput(
                selectSketchInputDef.id,
                selectSketchInputDef.name,
                selectSketchInputDef.tooltip
            )
            _sketchSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Sketches)
            _sketchSelectionInput.tooltip = selectSketchInputDef.tooltip
            _sketchSelectionInput.setSelectionLimits(1, 1)

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
    
    This handler checks to ensure the selected sketch is from a SurfaceUnfold feature.
    """
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            eventArgs = adsk.core.SelectionEventArgs.cast(args)
            entity = eventArgs.selection.entity
            
            if entity.objectType == adsk.fusion.Sketch.classType():
                customFeature = getSurfaceUnfoldFeatureFromSketch(entity)
                if customFeature is None:
                    eventArgs.isSelectable = False
                    return
                
            if entity.objectType == adsk.fusion.BRepBody.classType():
                pass

        except:
            showMessage(f'PreSelectHandler: {traceback.format_exc()}\n', True)


class ValidateInputsHandler(adsk.core.ValidateInputsEventHandler):
    """Event handler for the validateInputs event."""
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            eventArgs = adsk.core.ValidateInputsEventArgs.cast(args)

            if _sketchSelectionInput.selectionCount != 1:
                eventArgs.areInputsValid = False
                return

            if _bodiesSelectionInput.selectionCount < 1:
                eventArgs.areInputsValid = False
                return

            sketch = _sketchSelectionInput.selection(0).entity
            customFeature = getSurfaceUnfoldFeatureFromSketch(sketch)
            if customFeature is None:
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
            sketch: adsk.fusion.Sketch = _sketchSelectionInput.selection(0).entity
            
            bodies = adsk.core.ObjectCollection.create()
            for i in range(_bodiesSelectionInput.selectionCount):
                body = _bodiesSelectionInput.selection(i).entity
                if body: bodies.add(body)

            if bodies.count == 0: return

            component = sketch.parentComponent

            unfoldFeature = getSurfaceUnfoldFeatureFromSketch(sketch)
            if unfoldFeature is None: return

            face = None
            originPoint = None
            xDirPoint = None
            yDirPoint = None
            constructionPlane = None

            sourceEntity, originPoint, xDirPoint, yDirPoint, isMesh, constructionPlane = getDepsFromSurfaceUnfoldFeature(unfoldFeature)
            if not isMesh:
                face = sourceEntity

            resultBodies, validOldBodies, transformations = refoldBodiesToSurface(bodies, face, sketch, originPoint, xDirPoint, yDirPoint, constructionPlane)
            if not resultBodies: return

            baseFeature = component.features.baseFeatures.add()

            baseFeature.startEdit()

            # for i in range(validOldBodies.count):
            #     body = validOldBodies.item(i)
            #     # body = component.bRepBodies.add(validOldBodies.item(i), baseFeature)
            #     transformation = transformations[i]

            #     bodyCollection = adsk.core.ObjectCollection.create()
            #     bodyCollection.add(body)

            #     moveFeatureInput = component.features.moveFeatures.createInput2(bodyCollection)
            #     moveFeatureInput.targetBaseFeature = baseFeature
            #     moveFeatureInput.defineAsFreeMove(transformation)
            #     component.features.moveFeatures.add(moveFeatureInput)

            for resultBody in resultBodies:
                component.bRepBodies.add(resultBody, baseFeature)

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

            sketch: adsk.fusion.Sketch = _sketchSelectionInput.selection(0).entity
            
            bodies = adsk.core.ObjectCollection.create()
            for i in range(_bodiesSelectionInput.selectionCount):
                bodies.add(_bodiesSelectionInput.selection(i).entity)

            if bodies.count == 0:
                showMessage('No bodies selected.', True)
                eventArgs.executeFailed = True
                return

            component = sketch.parentComponent

            unfoldFeature = getSurfaceUnfoldFeatureFromSketch(sketch)
            if unfoldFeature is None:
                showMessage('Selected sketch is not from a Surface Unfold feature.', True)
                eventArgs.executeFailed = True
                return

            face = None
            originPoint = None
            xDirPoint = None
            yDirPoint = None
            constructionPlane = None

            sourceEntity, originPoint, xDirPoint, yDirPoint, isMesh, constructionPlane = getDepsFromSurfaceUnfoldFeature(unfoldFeature)
            if isMesh:
                face = None
            else:
                face = sourceEntity
                if face is None:
                    showMessage('Could not find the original face from the Surface Unfold feature.', True)
                    eventArgs.executeFailed = True
                    return

            resultBodies, validOldBodies, transformations = refoldBodiesToSurface(bodies, face, sketch, originPoint, xDirPoint, yDirPoint, constructionPlane)

            if not resultBodies:
                showMessage('No bodies were transferred to the surface.', True)
                eventArgs.executeFailed = True
                return
            
            # moveFeatures: List[adsk.fusion.MoveFeature] = []
            
            # for i in range(validOldBodies.count):
            #     body = validOldBodies.item(i)
            #     transformation = transformations[i]
            #     bodyCollection = adsk.core.ObjectCollection.create()
            #     bodyCollection.add(body)
            #     moveFeatureInput = component.features.moveFeatures.createInput2(bodyCollection)
            #     moveFeatureInput.defineAsFreeMove(transformation)
            #     moveFeatures.append(component.features.moveFeatures.add(moveFeatureInput))

            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()

            for i, resultBody in enumerate(resultBodies):
                component.bRepBodies.add(resultBody, baseFeature)
                # bodies[i].deleteMe()

            baseFeature.finishEdit()

            customFeatureInput = component.features.customFeatures.createInput(_customFeatureDefinition)

            customFeatureInput.addDependency('sketch', sketch)
            
            for i, body in enumerate(bodies):
                if body.faces.count == 0:
                    eventArgs.executeFailed = True
                    return
                firstBodyFace = body.faces[0]
                customFeatureInput.addDependency(f'firstBodyFace{i}', firstBodyFace)

            # customFeatureInput.setStartAndEndFeatures(moveFeatures[0], moveFeatures[-1])
            customFeatureInput.setStartAndEndFeatures(baseFeature, baseFeature)
            component.features.customFeatures.add(customFeatureInput)

        except:
            baseFeature.finishEdit()
            eventArgs.executeFailed = True
            showMessage(f'CreateExecuteHandler: {traceback.format_exc()}\n', True)


class EditActivateHandler(adsk.core.CommandEventHandler):
    """Event handler for the activation of the edit command for a custom cutter feature.
    
    This handler rolls back the timeline to the state before the feature, sets up transaction markers 
    to preserve changes, and pre-selects the original gemstone dependencies for editing.
    """
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

            i = 0
            while True:
                try:
                    faceDep = _editedCustomFeature.dependencies.itemById(f'firstBodyFace{i}')
                    if faceDep is None:
                        break
                    firstBodyFace = faceDep.entity
                    if firstBodyFace is not None and firstBodyFace.body is not None:
                        _bodiesSelectionInput.addSelection(firstBodyFace.body)
                    i += 1
                except:
                    break

            sketchDep = _editedCustomFeature.dependencies.itemById('sketch')
            if sketchDep and sketchDep.entity:
                _sketchSelectionInput.addSelection(sketchDep.entity)

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

            sketch = _sketchSelectionInput.selection(0).entity
            
            bodies = []
            for i in range(_bodiesSelectionInput.selectionCount):
                body = _bodiesSelectionInput.selection(i).entity
                if body: bodies.append(body)

            _editedCustomFeature.dependencies.deleteAll()
            _editedCustomFeature.dependencies.add('sketch', sketch)

            for i, body in enumerate(bodies):
                if body.faces.count == 0:
                    eventArgs.executeFailed = True
                    return
                firstBodyFace = body.faces[0]
                _editedCustomFeature.dependencies.add(f'firstBodyFace{i}', firstBodyFace)

            updateFeature(_editedCustomFeature)

        except:
            showMessage(f'EditExecuteHandler: {traceback.format_exc()}\n', True)

        finally: rollBack()


class ComputeCustomFeature(adsk.fusion.CustomFeatureEventHandler):
    """Event handler for the recomputation of the custom feature.
    
    This handler updates the cutter bodies within the base feature to reflect new values or geometry,
    ensuring the custom feature remains parametric and up-to-date.
    """
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.fusion.CustomFeatureEventArgs.cast(args)
            customFeature = eventArgs.customFeature
            updateFeature(customFeature)

        except:
            showMessage(f'ComputeCustomFeature: {traceback.format_exc()}\n', True)
    

def updateFeature(customFeature: adsk.fusion.CustomFeature) -> bool:
    """
    Update the bodies of an existing custom objects refold feature.

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
        
        sketchDep = customFeature.dependencies.itemById('sketch')
        if sketchDep is None or sketchDep.entity is None: return False
        sketch: adsk.fusion.Sketch = sketchDep.entity

        firstBodyFaces: list[adsk.fusion.BRepFace] = []
        i = 0
        while True:
            faceDep = customFeature.dependencies.itemById(f'firstBodyFace{i}')
            if faceDep is None: break
            firstBodyFace = faceDep.entity
            if firstBodyFace is None: break
            firstBodyFaces.append(firstBodyFace)
            i += 1
        if len(firstBodyFaces) == 0: return False

        bodies = adsk.core.ObjectCollection.create()
        for face_item in firstBodyFaces:
            bodies.add(face_item.body)

        unfoldFeature = getSurfaceUnfoldFeatureFromSketch(sketch)
        if unfoldFeature is None: return False

        component = sketch.parentComponent

        face = None
        originPoint = None
        xDirPoint = None
        yDirPoint = None
        constructionPlane = None

        sourceEntity, originPoint, xDirPoint, yDirPoint, isMesh, constructionPlane = getDepsFromSurfaceUnfoldFeature(unfoldFeature)
        if isMesh:
            face = None
        else:
            face = sourceEntity
            if face is None: return False

        resultBodies, _, _ = refoldBodiesToSurface(bodies, face, sketch, originPoint, xDirPoint, yDirPoint, constructionPlane)

        if not resultBodies: return False

        baseFeature.startEdit()

        for i in range(len(resultBodies)):
            resultBody = resultBodies[i]
            if i < baseFeature.bodies.count:
                currentBody = baseFeature.bodies.item(i)
                baseFeature.updateBody(currentBody, resultBody)
            else:
                component.bRepBodies.add(resultBody, baseFeature)

        while baseFeature.bodies.count > len(resultBodies):
            baseFeature.bodies.item(baseFeature.bodies.count - 1).deleteMe()

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
        # _editedCustomFeature.timelineObject.rollTo(False)
        _isRolledForEdit = False

    _editedCustomFeature = None