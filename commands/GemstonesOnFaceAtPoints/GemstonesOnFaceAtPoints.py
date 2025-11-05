import os
import adsk.core, adsk.fusion, traceback

from ... import constants
from ... import strings
from ...helpers.showMessage import showMessage

_app: adsk.core.Application = None
_ui: adsk.core.UserInterface = None

_customFeatureDefinition: adsk.fusion.CustomFeature = None

_faceSelectionInput: adsk.core.SelectionCommandInput = None
_pointSelectionInput: adsk.core.SelectionCommandInput = None
_sizeValueInput: adsk.core.ValueCommandInput = None
_flipValueInput: adsk.core.BoolValueCommandInput = None
_depthOffsetValueInput: adsk.core.ValueCommandInput = None

_editedCustomFeature: adsk.fusion.CustomFeature = None
_restoreTimelineObject: adsk.fusion.TimelineObject = None
_isRolledForEdit: bool = False

_handlers = []

_diamondMaterial: adsk.core.Material = None

COMMAND_ID = strings.PREFIX + strings.GEMSTONE_COMMAND_NAME
CREATE_COMMAND_ID = COMMAND_ID + 'Create'
EDIT_COMMAND_ID = COMMAND_ID + 'Edit'

CREATE_COMMAND_NAME = 'Gemstones at Points'
CREATE_COMMAND_DESCRIPTION = 'Creates gemstones at selected points on a face.'

EDIT_COMMAND_NAME = 'Edit Gemstones'
EDIT_COMMAND_DESCRIPTION = 'Edits the parameters of existing gemstones.'

SELECT_FACE_NAME = 'Select Face'
SELECT_FACE_PROMPT = 'Select the face where the gemstone will be placed.'

SELECT_POINT_NAME = 'Select Points'
SELECT_POINT_PROMPT = 'Select points on the face for the gemstone centers.'



RESOURCES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

def run(context):
    try:
        global _app, _ui, _diamondMaterial
        _app = adsk.core.Application.get()
        _ui  = _app.userInterface

        # Load the diamond material from the Fusion Material Library
        MaterialLib = _app.materialLibraries.itemByName('Fusion Material Library')
        _diamondMaterial = MaterialLib.materials.itemByName('Mirror')

        createCommandDefinition = _ui.commandDefinitions.addButtonDefinition(CREATE_COMMAND_ID, 
                                                                CREATE_COMMAND_NAME, 
                                                                CREATE_COMMAND_DESCRIPTION, 
                                                                RESOURCES_FOLDER)        

        solidWorkspace = _ui.workspaces.itemById('FusionSolidEnvironment')
        panel = solidWorkspace.toolbarPanels.itemById('SolidCreatePanel')
        control = panel.controls.addCommand(createCommandDefinition, '', False)     
        control.isPromoted = True

        editCommandDefinition = _ui.commandDefinitions.addButtonDefinition(EDIT_COMMAND_ID, 
                                                            EDIT_COMMAND_NAME, 
                                                            EDIT_COMMAND_DESCRIPTION, 
                                                            RESOURCES_FOLDER)        

        createCommandCreated = CreateCommandCreatedHandler()
        createCommandDefinition.commandCreated.add(createCommandCreated)
        _handlers.append(createCommandCreated)

        editCommandCreated = EditCommandCreatedHandler()
        editCommandDefinition.commandCreated.add(editCommandCreated)
        _handlers.append(editCommandCreated)

        global _customFeatureDefinition
        _customFeatureDefinition = adsk.fusion.CustomFeatureDefinition.create(COMMAND_ID, strings.GEMSTONE_COMMAND_NAME, RESOURCES_FOLDER)
        _customFeatureDefinition.editCommandId = EDIT_COMMAND_ID

        computeCustomFeature = ComputeCustomFeature()
        _customFeatureDefinition.customFeatureCompute.add(computeCustomFeature)
        _handlers.append(computeCustomFeature)
    except:
        showMessage(f'Run Failed:\n{traceback.format_exc()}', True)


def stop(context):
    try:
        solidWorkspace = _ui.workspaces.itemById('FusionSolidEnvironment')
        panel = solidWorkspace.toolbarPanels.itemById('SolidCreatePanel')
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


# This class handles the creation of the command dialog for creating new gemstones at points.
# It sets up all necessary input controls, including selections for face and points, value inputs for size, flip, and depth offset.
# It also connects event handlers for validation, preview, and execution.
class CreateCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs
            defaultLengthUnits = _app.activeProduct.unitsManager.defaultLengthUnits

            global _faceSelectionInput, _pointSelectionInput, _sizeValueInput, _flipValueInput, _depthOffsetValueInput

            _faceSelectionInput = inputs.addSelectionInput('selectFace', SELECT_FACE_NAME, SELECT_FACE_PROMPT)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _faceSelectionInput.tooltip = SELECT_FACE_PROMPT
            _faceSelectionInput.setSelectionLimits(1, 1)

            _pointSelectionInput = inputs.addSelectionInput('selectPoints', SELECT_POINT_NAME, SELECT_POINT_PROMPT)
            _pointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchPoints)
            _pointSelectionInput.tooltip = SELECT_POINT_PROMPT
            _pointSelectionInput.setSelectionLimits(1)  # Minimum 1, no maximum limit

            size = adsk.core.ValueInput.createByReal(0.15)
            _sizeValueInput = inputs.addValueInput('size', 'Size', defaultLengthUnits, size)
            _sizeValueInput.tooltip = "The size of the gemstone.\nThis scales the gemstone proportionally to match the specified dimension."

            # Create toggle input for the flip option
            flip = False
            _flipValueInput = inputs.addBoolValueInput('flip', 'Flip', True, '', flip)
            _flipValueInput.tooltip = "Whether to flip the gemstone orientation.\nReverses the direction the gemstone faces relative to the surface."

            # Create value input for the depth offset
            depthOffset = adsk.core.ValueInput.createByReal(0.0)
            _depthOffsetValueInput = inputs.addValueInput('depthOffset', 'Depth Offset', defaultLengthUnits, depthOffset)
            _depthOffsetValueInput.tooltip = "The offset of the gemstone along the face normal.\nPositive values move the gemstone outward from the surface, negative values inward."

            # Connect to the needed command related events.
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


# This class handles the creation of the command dialog for editing existing gemstones custom feature.
# It retrieves the selected custom feature, populates inputs with existing parameter values and dependencies,
# and connects event handlers for editing operations, including activation, validation, preview, and execution.
class EditCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs
            defaultLengthUnits = _app.activeProduct.unitsManager.defaultLengthUnits

            # Get the currently selected custom feature.
            global _editedCustomFeature, _faceSelectionInput, _pointSelectionInput
            _editedCustomFeature = _ui.activeSelections.item(0).entity
            if _editedCustomFeature is None:
                return

            global _sizeValueInput, _flipValueInput

            # Create selection input for the face
            _faceSelectionInput = inputs.addSelectionInput('selectFace', SELECT_FACE_NAME, SELECT_FACE_PROMPT)
            _faceSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Faces)
            _faceSelectionInput.tooltip = SELECT_FACE_PROMPT
            _faceSelectionInput.setSelectionLimits(1, 1)

            # Create selection input for the sketch points
            _pointSelectionInput = inputs.addSelectionInput('selectPoints', SELECT_POINT_NAME, SELECT_POINT_PROMPT)
            _pointSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.SketchPoints)
            _pointSelectionInput.tooltip = SELECT_POINT_PROMPT
            _pointSelectionInput.setSelectionLimits(1)  # Minimum 1, no maximum limit

            # Get the collection of custom parameters for this custom feature.
            params = _editedCustomFeature.parameters

            # Create value input for the size using existing parameter
            size = adsk.core.ValueInput.createByString(params.itemById('size').expression)
            _sizeValueInput = inputs.addValueInput('size', 'Size', defaultLengthUnits, size)
            _sizeValueInput.tooltip = "The size of the gemstone.\nThis scales the gemstone proportionally to match the specified dimension."

            # Create toggle input for the flip option
            flip = params.itemById('flip').expression.lower() == 'true'
            _flipValueInput = inputs.addBoolValueInput('flip', 'Flip', True, '', flip)
            _flipValueInput.tooltip = "Whether to flip the gemstone orientation.\nReverses the direction the gemstone faces relative to the surface."

            # Create value input for the depth offset using existing parameter
            depthOffset = adsk.core.ValueInput.createByString(params.itemById('depthOffset').expression)
            global _depthOffsetValueInput
            _depthOffsetValueInput = inputs.addValueInput('depthOffset', 'Depth Offset', defaultLengthUnits, depthOffset)
            _depthOffsetValueInput.tooltip = "The offset of the gemstone along the face normal.\nPositive values move the gemstone outward from the surface, negative values inward."

            # Connect to the needed command related events.
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

            # command.

            onExecute = EditExecuteHandler()
            command.execute.add(onExecute)
            _handlers.append(onExecute)  

        except:
            showMessage(f'EditCommandCreatedHandler: {traceback.format_exc()}\n', True)


# Controls what the user can select when the command is running.
# This checks to make sure the point is on a planar face and the
# body the point is on is not an external reference.
class PreSelectHandler(adsk.core.SelectionEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.SelectionEventArgs.cast(args)
            type = eventArgs.selection.entity.objectType

            # showMessage(f'PreSelectHandler: {type}')

            if type == adsk.fusion.BRepFace.classType():
                if eventArgs.selection.entity is None:
                    eventArgs.isSelectable = False
                    return

            if type == adsk.fusion.SketchPoint.classType():
                preSelectPoint: adsk.fusion.SketchPoint = eventArgs.selection.entity

                # Verify the body is not from an XRef.
                if preSelectPoint.assemblyContext:
                    occ = preSelectPoint.assemblyContext
                    if occ.isReferencedComponent:
                        eventArgs.isSelectable = False
                        return
            
        except:
            showMessage(f'PreSelectHandler: {traceback.format_exc()}\n', True)


# Event handler for the validateInputs event.
class ValidateInputsHandler(adsk.core.ValidateInputsEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.ValidateInputsEventArgs.cast(args)

            if _faceSelectionInput.selectionCount != 1 or _pointSelectionInput.selectionCount < 1:
                eventArgs.areInputsValid = False
                return

            if not all( [_sizeValueInput.isValidExpression, _flipValueInput.isValid, _depthOffsetValueInput.isValidExpression] ):
                eventArgs.areInputsValid = False
                return

            size = _sizeValueInput.value
            if size < 0.05:
                eventArgs.areInputsValid = False
                return
            
        except:
            showMessage(f'ValidateInputsHandler: {traceback.format_exc()}\n', True)


# Event handler for the executePreview event.
class ExecutePreviewHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            face: adsk.fusion.BRepFace = _faceSelectionInput.selection(0).entity
            
            size = _sizeValueInput.value
            flip = _flipValueInput.value
            depthOffset = _depthOffsetValueInput.value

            component = face.body.parentComponent
            baseFeat = component.features.baseFeatures.add()
            baseFeat.startEdit()

            for i in range(_pointSelectionInput.selectionCount):
                sketchPoint: adsk.fusion.SketchPoint = _pointSelectionInput.selection(i).entity
                gemstone = createBody(face, sketchPoint.worldGeometry, size, flip, depthOffset)
                if gemstone is not None:
                    body = component.bRepBodies.add(gemstone, baseFeat)
                    handleNewBody(body, flip)
                    body.material = _diamondMaterial

            baseFeat.finishEdit()
            

        except:
            showMessage(f'ExecutePreviewHandler: {traceback.format_exc()}\n', True)


# Event handler for the execute event of the create command.
class CreateExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.CommandEventArgs.cast(args)        

            face: adsk.fusion.BRepFace = _faceSelectionInput.selection(0).entity
            comp = face.body.parentComponent
            pointEntities: list[adsk.fusion.SketchPoint] = []
            for i in range(_pointSelectionInput.selectionCount):
                pointEntities.append(_pointSelectionInput.selection(i).entity)

            # Create gemstones for each selected point

            baseFeat = comp.features.baseFeatures.add()
            baseFeat.startEdit()

            for i in range(len(pointEntities)):
                sketchPoint = pointEntities[i]    
                gemstone = createBody(face, sketchPoint.worldGeometry, _sizeValueInput.value, _flipValueInput.value, _depthOffsetValueInput.value)
                if gemstone is None:
                    eventArgs.executeFailed = True
                    return
                
                body = comp.bRepBodies.add(gemstone, baseFeat)
                handleNewBody(body, _flipValueInput.value)
                body.material = _diamondMaterial

            baseFeat.finishEdit()

            # Create the custom feature input.
            design: adsk.fusion.Design = _app.activeProduct
            defLengthUnits = design.unitsManager.defaultLengthUnits
            customFeatureInput = comp.features.customFeatures.createInput(_customFeatureDefinition)

            sizeInput = adsk.core.ValueInput.createByString(_sizeValueInput.expression)
            customFeatureInput.addCustomParameter('size', 'Size', sizeInput,
                                              defLengthUnits, True)
                         
            flipInput = adsk.core.ValueInput.createByString(str(_flipValueInput.value).lower())
            customFeatureInput.addCustomParameter('flip', 'Flip', flipInput, '', True)

            depthOffsetInput = adsk.core.ValueInput.createByString(_depthOffsetValueInput.expression)
            customFeatureInput.addCustomParameter('depthOffset', 'Depth Offset', depthOffsetInput,
                                              defLengthUnits, True)

            customFeatureInput.addDependency('face', face)
            
            for i in range(len(pointEntities)):
                customFeatureInput.addDependency(f'point{i}', pointEntities[i])

            customFeatureInput.setStartAndEndFeatures(baseFeat, baseFeat)
            comp.features.customFeatures.add(customFeatureInput)
        except:
            eventArgs.executeFailed = True
            showMessage(f'CreateExecuteHandler: {traceback.format_exc()}\n', True)


# Event handler for the activate event.
class EditActivateHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature

            if _isRolledForEdit: return

            eventArgs = adsk.core.CommandEventArgs.cast(args)
            
            # Save the current position of the timeline.
            design: adsk.fusion.Design = _app.activeProduct
            timeline = design.timeline
            markerPosition = timeline.markerPosition
            _restoreTimelineObject = timeline.item(markerPosition - 1)

            # Roll the timeline to just before the custom feature being edited.
            _editedCustomFeature.timelineObject.rollTo(True)
            _isRolledForEdit = True

            # Define a transaction marker so the the roll is not aborted with each change.
            command = eventArgs.command
            command.beginStep()


            # Get the face and points and add them to the selection inputs.
            face = _editedCustomFeature.dependencies.itemById('face').entity
            _faceSelectionInput.addSelection(face)
            
            # Add all point dependencies to the selection input
            i = 0
            while True:
                try:
                    dependency = _editedCustomFeature.dependencies.itemById(f'point{i}')
                    if dependency is None: break
                    sketchPoint = dependency.entity
                    if sketchPoint is not None: _pointSelectionInput.addSelection(sketchPoint)
                    i += 1
                except:
                    break
                
        except:
            showMessage(f'EditActivateHandler: {traceback.format_exc()}\n', True)


class EditDestroyHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _editedCustomFeature, _isRolledForEdit
            eventArgs = adsk.core.CommandEventArgs.cast(args)
            if eventArgs.terminationReason != adsk.core.CommandTerminationReason.CompletedTerminationReason:
                rollBack()
        except:
            showMessage(f'EditDeactivateHandler: {traceback.format_exc()}\n', True)


# Event handler for the execute event of the edit command.
class EditExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        global _editedCustomFeature, _isRolledForEdit

        try:
            eventArgs = adsk.core.CommandEventArgs.cast(args)    

            # Cache face entity
            faceEntity = _faceSelectionInput.selection(0).entity
            pointCount = _pointSelectionInput.selectionCount
            pointEntities = []
            for i in range(pointCount):
                pointEntities.append(_pointSelectionInput.selection(i).entity)

            # Clear and rebuild dependencies to handle cases where the user selects different geometry during edit.
            _editedCustomFeature.dependencies.deleteAll()
            _editedCustomFeature.dependencies.add('face', faceEntity)

            for i in range(pointCount):
                _editedCustomFeature.dependencies.add(f'point{i}', pointEntities[i])

            # Update the parameters.
            _editedCustomFeature.parameters.itemById('size').expression = _sizeValueInput.expression
            _editedCustomFeature.parameters.itemById('flip').expression = str(_flipValueInput.value).lower()
            _editedCustomFeature.parameters.itemById('depthOffset').expression = _depthOffsetValueInput.expression

            # Update the feature.
            updateFeature(_editedCustomFeature)

        except:
            showMessage(f'EditExecuteHandler: {traceback.format_exc()}\n', True)

        finally: rollBack()


# Event handler to handle the compute of the custom feature.
class ComputeCustomFeature(adsk.fusion.CustomFeatureEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs: adsk.fusion.CustomFeatureEventArgs = args

            # Get the custom feature that is being computed.
            custFeature = eventArgs.customFeature

            updateFeature(custFeature)

        except:
            showMessage(f'ComputeCustomFeature: {traceback.format_exc()}\n', True)


# Utility function that creates the gemstone body based on the face, point, size, and flip.
def createBody(face: adsk.fusion.BRepFace, point: adsk.core.Point3D, size: float, flip: bool = False, depthOffset: float = 0.0):
    try:
        if face is None or point is None: return None

        temporaryBRep: adsk.fusion.TemporaryBRepManager = adsk.fusion.TemporaryBRepManager.get()

        faceEvaluator = face.evaluator
        _, param = faceEvaluator.getParameterAtPoint(point)
        _, pointOnFace = faceEvaluator.getPointAtParameter(param)
        _, normal = faceEvaluator.getNormalAtParameter(param)
        _, lengthDir, _ = faceEvaluator.getFirstDerivative(param)
        widthDir = normal.crossProduct(lengthDir)

        # Normalize the direction vectors
        lengthDir.normalize()
        widthDir.normalize()
        normal.normalize()

        # Load the gemstone from file and transform it
        filePath = RESOURCES_FOLDER + strings.GEMSTONE_ROUND_CUT + '.sat'
        gemstone = temporaryBRep.createFromFile(filePath).item(0)
        
        cylindricalFace = list(filter(lambda x: x.geometry.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType, gemstone.faces))[0]
        originPoint = cylindricalFace.centroid

        girdleThickness = abs(cylindricalFace.boundingBox.minPoint.z - cylindricalFace.boundingBox.maxPoint.z)

        lengthDir.scaleBy(size)
        widthDir.scaleBy(size)
        normal.scaleBy(size)

        translate = normal.copy()
        translate.scaleBy(girdleThickness / 2)
        pointOnFace.translateBy(translate)

        # Add depthOffset in the normal direction (absolute, not scaled)
        originalNormal = normal.copy()
        originalNormal.normalize()
        offsetVector = originalNormal.copy()
        offsetVector.scaleBy(depthOffset)
        pointOnFace.translateBy(offsetVector)

        if flip: normal.scaleBy(-1)

        # Transform the gemstone to the face position
        transformation = adsk.core.Matrix3D.create()
        transformation.setToAlignCoordinateSystems(
            originPoint, constants.xVector, constants.yVector, constants.zVector,
            pointOnFace, lengthDir, widthDir, normal
            )
        temporaryBRep.transform(gemstone, transformation)

        return gemstone
    
    except:
        showMessage(f'createBodies: {traceback.format_exc()}\n', True)

def updateBody(body: adsk.fusion.BRepBody, face: adsk.fusion.BRepFace, point: adsk.core.Point3D, size: float = 1.5, flip: bool = False, depthOffset: float = 0.0) -> adsk.fusion.BRepBody | None:
    try:
        if body is None or face is None or point is None: return None

        temporaryBRep = adsk.fusion.TemporaryBRepManager.get()
        tempBody = temporaryBRep.copy(body)

        topFace = sorted(tempBody.faces, key = lambda x: x.area, reverse = True)[0]
        topPlane = adsk.core.Plane.cast(topFace.geometry)
        cylindricalFace = list(filter(lambda x: x.geometry.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType, tempBody.faces))[0]
        cylinder = adsk.core.Cylinder.cast(cylindricalFace.geometry)
        gridleCentroid = cylindricalFace.centroid

        oldSize = cylinder.radius * 2
        sizeScale = size / oldSize
        # oldFaceNormal.normalize()  

        oldNormal = topPlane.normal
        if flip: oldNormal.scaleBy(-1)

        transformation = adsk.core.Matrix3D.create()
        transformation.setToAlignCoordinateSystems(
            gridleCentroid, topPlane.uDirection, topPlane.vDirection, oldNormal,
            constants.zeroPoint, constants.xVector, constants.yVector, constants.zVector
            )
        temporaryBRep.transform(tempBody, transformation)

        girdleThickness = abs(cylindricalFace.boundingBox.minPoint.z - cylindricalFace.boundingBox.maxPoint.z)

        faceEvaluator = face.evaluator
        _, parameter = faceEvaluator.getParameterAtPoint(point)
        _, newFacePoint = faceEvaluator.getPointAtParameter(parameter)
        _, newFaceNormal = faceEvaluator.getNormalAtParameter(parameter)
        _, newLengthDirection, _ = faceEvaluator.getFirstDerivative(parameter)
        newWidthDirection = newFaceNormal.crossProduct(newLengthDirection)

        newLengthDirection.normalize()
        newWidthDirection.normalize()
        newFaceNormal.normalize()

        newLengthDirection.scaleBy(sizeScale)
        newWidthDirection.scaleBy(sizeScale)
        newFaceNormal.scaleBy(sizeScale)

        translate = newFaceNormal.copy()
        translate.scaleBy(girdleThickness / 2)
        newFacePoint.translateBy(translate)

        # Add depthOffset in the normal direction (absolute, not scaled)
        originalNormal = newFaceNormal.copy()
        originalNormal.normalize()
        offsetVector = originalNormal.copy()
        offsetVector.scaleBy(depthOffset)
        newFacePoint.translateBy(offsetVector)
        
        transformation.setToIdentity()
        transformation.setToAlignCoordinateSystems(
            constants.zeroPoint, constants.xVector, constants.yVector, constants.zVector,
            newFacePoint, newLengthDirection, newWidthDirection, newFaceNormal
            )
        temporaryBRep.transform(tempBody, transformation)

        return tempBody
    
    except:
        showMessage(f'updateBody: {traceback.format_exc()}\n', True)

# Updates the bodies of an existing custom gemstone feature.
def updateFeature(customFeature: adsk.fusion.CustomFeature) -> bool:
    try:
        # Locate the base feature that contains the gemstone bodies within the custom feature's feature collection.
        baseFeature: adsk.fusion.BaseFeature = None

        for feature in customFeature.features:
            if feature.objectType == adsk.fusion.BaseFeature.classType():
                baseFeature = feature
        if baseFeature is None: return False

        faceEntity: adsk.fusion.BRepFace = customFeature.dependencies.itemById('face').entity
        if faceEntity is None: return False

        # Collect all point dependencies in order to regenerate gemstones for each point.
        points: list[adsk.fusion.SketchPoint] = []
        i = 0
        while True:
            dependency = customFeature.dependencies.itemById(f'point{i}')
            if dependency is None: break
            sketchPoint = dependency.entity
            if sketchPoint is None: break
            points.append(sketchPoint)
            i += 1
        if len(points) == 0: return False

        size = customFeature.parameters.itemById('size').value
        flip = customFeature.parameters.itemById('flip').expression.lower() == 'true'
        depthOffset = customFeature.parameters.itemById('depthOffset').value

        component = faceEntity.body.parentComponent

        baseFeature.startEdit()
        
        # Update existing bodies or add new ones to handle parameter changes and point count modifications.
        success = True
        for i in range(len(points)):
            point = points[i]

            if i < baseFeature.bodies.count:
                # Update existing body
                currentBody = baseFeature.bodies.item(i)
                newBody = updateBody(currentBody, faceEntity, point.worldGeometry, size, flip, depthOffset)
                if newBody is not None:
                    baseFeature.updateBody(currentBody, newBody)
                else:
                    success = False
            else:
                # Add new body
                gemstone = createBody(faceEntity, point.worldGeometry, size, flip, depthOffset)
                if gemstone is not None:
                    body = component.bRepBodies.add(gemstone, baseFeature)
                    body.material = _diamondMaterial
                else:
                    success = False

        # Remove extra bodies if the point count has decreased during editing.
        while baseFeature.bodies.count > len(points):
            baseFeature.bodies.item(baseFeature.bodies.count - 1).deleteMe()


        baseFeature.finishEdit()
        
        for i in range(baseFeature.bodies.count):
            currentBody = baseFeature.bodies.item(i)
            handleNewBody(currentBody, flip)
        
        
        return success
    
    except:
        showMessage(f'updateFeature: {traceback.format_exc()}\n', True)
        return False
    
def handleNewBody(body: adsk.fusion.BRepBody, flip: bool = False) -> bool:
    try:
        body.name = strings.GEMSTONE_ROUND_CUT

        body.attributes.add(strings.PREFIX, strings.ENTITY, strings.GEMSTONE)
        body.attributes.add(strings.PREFIX, strings.GEMSTONE_CUT, strings.GEMSTONE_ROUND_CUT)
        body.attributes.add(strings.PREFIX, strings.GEMSTONE_IS_FLIPPED, str(flip).lower())
        return True
    except:
        showMessage(f'handleNewBody: {traceback.format_exc()}\n', True)
        return False

def rollBack():
    global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature
    if _isRolledForEdit:
        _restoreTimelineObject.rollTo(False)
        _isRolledForEdit = False
    _editedCustomFeature = None