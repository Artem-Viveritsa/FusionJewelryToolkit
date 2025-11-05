import os
import adsk.core, adsk.fusion, traceback

from ... import strings
from ... import constants
from ...helpers.showMessage import showMessage
import math


_handlers = []

_app: adsk.core.Application = None
_ui: adsk.core.UserInterface = None

_customFeatureDefinition: adsk.fusion.CustomFeature = None

_editedCustomFeature: adsk.fusion.CustomFeature = None
_restoreTimelineObject: adsk.fusion.TimelineObject = None
_isRolledForEdit: bool = False

_gemstonesSelectionInput: adsk.core.SelectionCommandInput = None

_heightValueInput: adsk.core.ValueCommandInput = None
_depthValueInput: adsk.core.ValueCommandInput = None
_sizeRatioValueInput: adsk.core.ValueCommandInput = None
_holeRatioValueInput: adsk.core.ValueCommandInput = None
_coneAngleValueInput: adsk.core.ValueCommandInput = None


RESOURCES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

COMMAND_ID = strings.PREFIX + strings.CUTTERS_COMMAND_NAME
CREATE_COMMAND_ID = COMMAND_ID + 'Create'
EDIT_COMMAND_ID = COMMAND_ID + 'Edit'

CREATE_COMMAND_NAME = 'Create Cutters at Gemstones'
CREATE_COMMAND_DESCRIPTION = 'Creates cutters at selected gemstones.'

EDIT_COMMAND_NAME = 'Edit Cutters'
EDIT_COMMAND_DESCRIPTION = 'Edits the parameters of existing cutters.'

SELECT_GEMSTONE_NAME = 'Select Gemstones'
SELECT_GEMSTONE_PROMPT = 'Select the gemstones to make cutters.'


def run(context):
    try:
        global _app, _ui, _customFeatureDefinition
        _app = adsk.core.Application.get()
        _ui  = _app.userInterface

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

        _customFeatureDefinition = adsk.fusion.CustomFeatureDefinition.create(COMMAND_ID, strings.CUTTERS_COMMAND_NAME, RESOURCES_FOLDER)
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


# This class handles the creation of the command dialog for creating new cutters at gemstones.
# It sets up all necessary input controls, including selections for gemstones and value inputs for height and depth.
# It also connects event handlers for validation, preview, and execution.
class CreateCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _gemstonesSelectionInput, _depthValueInput, _heightValueInput, _sizeRatioValueInput, _holeRatioValueInput, _coneAngleValueInput
            
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs
            defaultLengthUnits = _app.activeProduct.unitsManager.defaultLengthUnits

            _gemstonesSelectionInput = inputs.addSelectionInput('selectGemstones', SELECT_GEMSTONE_NAME, SELECT_GEMSTONE_PROMPT)
            _gemstonesSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Bodies)
            _gemstonesSelectionInput.tooltip = SELECT_GEMSTONE_PROMPT
            _gemstonesSelectionInput.setSelectionLimits(1)

            height = adsk.core.ValueInput.createByReal(0.04)
            _heightValueInput = inputs.addValueInput('height', 'Height', defaultLengthUnits, height)
            _heightValueInput.tooltip = "The height of the cutter body extending above the gemstone girdle.\nThis determines how far the cutter protrudes upwards from the girdle."

            depth = adsk.core.ValueInput.createByReal(0.15)
            _depthValueInput = inputs.addValueInput('depth', 'Depth', defaultLengthUnits, depth)
            _depthValueInput.tooltip = "The depth of the cutter hole below the gemstone girdle.\nThis controls how deep the cutter cuts into the material beneath the girdle."

            sizeRatio = adsk.core.ValueInput.createByReal(1.0)
            _sizeRatioValueInput = inputs.addValueInput('sizeRatio', 'Size Ratio', '', sizeRatio)
            _sizeRatioValueInput.tooltip = "The ratio by which the cutter size is scaled relative to the gemstone diameter.\nValues from 0.7 to 1.3 allow shrinking or enlarging the cutter proportionally\n(1.0 = exact match to gemstone size)."

            holeRatio = adsk.core.ValueInput.createByReal(0.5)
            _holeRatioValueInput = inputs.addValueInput('holeRatio', 'Hole Ratio', '', holeRatio)
            _holeRatioValueInput.tooltip = "The ratio of the hole diameter to the cutter diameter.\nValues from 0.2 to 0.8 control the size of the central hole relative to the outer cutter size\n(0.5 = half the diameter)."

            coneAngle = adsk.core.ValueInput.createByReal(41.0)
            _coneAngleValueInput = inputs.addValueInput('coneAngle', 'Cone Angle', '', coneAngle)
            _coneAngleValueInput.tooltip = "The angle of the cutter cone in degrees.\nValues from 30 to 60 degrees control the slope of the conical section\n(41 = default angle)."

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


# This class handles the creation of the command dialog for editing existing cutter custom feature.
# It retrieves the selected custom feature, populates inputs with existing parameter values and dependencies,
# and connects event handlers for editing operations, including activation, validation, preview, and execution.
class EditCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _editedCustomFeature, _gemstonesSelectionInput, _depthValueInput, _heightValueInput, _sizeRatioValueInput, _holeRatioValueInput, _coneAngleValueInput
            
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs
            defaultLengthUnits = _app.activeProduct.unitsManager.defaultLengthUnits

            # Get the currently selected custom feature from the timeline.
            _editedCustomFeature = _ui.activeSelections.item(0).entity
            if _editedCustomFeature is None:
                return

            _gemstonesSelectionInput = inputs.addSelectionInput('selectGemstones', SELECT_GEMSTONE_NAME, SELECT_GEMSTONE_PROMPT)
            _gemstonesSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Bodies)
            _gemstonesSelectionInput.tooltip = SELECT_GEMSTONE_PROMPT
            _gemstonesSelectionInput.setSelectionLimits(1)

            # Get the collection of custom parameters for this custom feature.
            parameters = _editedCustomFeature.parameters

            # Create value inputs using existing parameter expressions to preserve user-defined values and equations.
            height = adsk.core.ValueInput.createByString(parameters.itemById('height').expression)
            _heightValueInput = inputs.addValueInput('height', 'Height', defaultLengthUnits, height)
            _heightValueInput.tooltip = "The height of the cutter body extending above the gemstone girdle.\nThis determines how far the cutter protrudes upwards from the girdle."

            depth = adsk.core.ValueInput.createByString(parameters.itemById('depth').expression)
            _depthValueInput = inputs.addValueInput('depth', 'Depth', defaultLengthUnits, depth)
            _depthValueInput.tooltip = "The depth of the cutter hole below the gemstone girdle.\nThis controls how deep the cutter cuts into the material beneath the girdle."

            sizeRatio = adsk.core.ValueInput.createByString(parameters.itemById('sizeRatio').expression)
            _sizeRatioValueInput = inputs.addValueInput('sizeRatio', 'Size Ratio', '', sizeRatio)
            _sizeRatioValueInput.tooltip = "The ratio by which the cutter size is scaled relative to the gemstone diameter.\nValues from 0.7 to 1.3 allow shrinking or enlarging the cutter proportionally\n(1.0 = exact match to gemstone size)."

            holeRatio = adsk.core.ValueInput.createByString(parameters.itemById('holeRatio').expression)
            _holeRatioValueInput = inputs.addValueInput('holeRatio', 'Hole Ratio', '', holeRatio)
            _holeRatioValueInput.tooltip = "The ratio of the hole diameter to the cutter diameter.\nValues from 0.2 to 0.8 control the size of the central hole relative to the outer cutter size\n(0.5 = half the diameter)."

            coneAngle = adsk.core.ValueInput.createByString(parameters.itemById('coneAngle').expression)
            _coneAngleValueInput = inputs.addValueInput('coneAngle', 'Cone Angle', '', coneAngle)
            _coneAngleValueInput.tooltip = "The angle of the cutter cone in degrees.\nValues from 30 to 60 degrees control the slope of the conical section\n(41 = default angle)."

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

            onExecute = EditExecuteHandler()
            command.execute.add(onExecute)
            _handlers.append(onExecute)  

        except:
            showMessage(f'EditCommandCreatedHandler: {traceback.format_exc()}\n', True)


# Controls what the user can select when the command is running.
# This checks to make sure the gemstones are valid bodies and not external references.
class PreSelectHandler(adsk.core.SelectionEventHandler):
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

                attribute = preSelectBody.attributes.itemByName(strings.PREFIX, strings.ENTITY)
                if attribute is None:
                    eventArgs.isSelectable = False
                    return
                
                value = attribute.value
                if not value == strings.GEMSTONE:
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

            if _gemstonesSelectionInput.selectionCount < 1:
                eventArgs.areInputsValid = False
                return

            for i in range(_gemstonesSelectionInput.selectionCount):
                body = _gemstonesSelectionInput.selection(i)

                if not body.isValid:
                    eventArgs.areInputsValid = False
                    return

            # Verify the inputs have valid expressions.
            if not all([_depthValueInput.isValidExpression, _heightValueInput.isValidExpression, _sizeRatioValueInput.isValidExpression, _holeRatioValueInput.isValidExpression, _coneAngleValueInput.isValidExpression]):
                eventArgs.areInputsValid = False
                return

            # Enforce minimum size constraints to prevent degenerate geometry.
            if _depthValueInput.value < 0:
                eventArgs.areInputsValid = False
                return
            
            if _heightValueInput.value < 0.01:
                eventArgs.areInputsValid = False
                return

            if not (_sizeRatioValueInput.value >= 0.7 and _sizeRatioValueInput.value <= 1.3):
                eventArgs.areInputsValid = False
                return

            if not (_holeRatioValueInput.value >= 0.2 and _holeRatioValueInput.value <= 0.8):
                eventArgs.areInputsValid = False
                return

            if not (_coneAngleValueInput.value >= 30 and _coneAngleValueInput.value <= 60):
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
            if _gemstonesSelectionInput.selectionCount < 1: return

            gemstones: list[adsk.fusion.BRepBody] = []
            for i in range(_gemstonesSelectionInput.selectionCount):
                gemstone = _gemstonesSelectionInput.selection(i).entity
                if gemstone is None: continue
                gemstones.append(gemstone)

            if not gemstones: return

            height = _heightValueInput.value
            depth = _depthValueInput.value
            sizeRatio = _sizeRatioValueInput.value
            holeRatio = _holeRatioValueInput.value
            coneAngle = _coneAngleValueInput.value
            
            flippedStates = getFlipStatesForGemstones(gemstones)

            cutters = []
            for i, gemstone in enumerate(gemstones):
                cutter = createBody(gemstone, height, depth, sizeRatio, holeRatio, flippedStates[i], coneAngle)
                if cutter is None: continue
                cutters.append(cutter)

            if not cutters: return

            # Create a base feature to contain the cutter bodies, allowing them to be grouped and managed as a single unit.
            component = gemstones[0].parentComponent

            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()
            for i in range(len(cutters)):
                body = component.bRepBodies.add(cutters[i], baseFeature)
                handleNewBody(body)
            baseFeature.finishEdit()

        except:
            showMessage(f'ExecutePreviewHandler: {traceback.format_exc()}\n', True)

# Event handler for the execute event of the create command.
class CreateExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.CommandEventArgs.cast(args)

            gemstones: list[adsk.fusion.BRepBody] = []
            for i in range(_gemstonesSelectionInput.selectionCount):
                gemstones.append(_gemstonesSelectionInput.selection(i).entity)

            flippedStates = getFlipStatesForGemstones(gemstones)

            # Create a base feature and add the cutter bodies.
            component = gemstones[0].parentComponent
            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()
            for i, gemstone in enumerate(gemstones):
                cutter = createBody(gemstone, _heightValueInput.value, _depthValueInput.value, _sizeRatioValueInput.value, _holeRatioValueInput.value, flippedStates[i], _coneAngleValueInput.value)
                if cutter is None:
                    eventArgs.executeFailed = True
                    return
                body = component.bRepBodies.add(cutter, baseFeature)
                handleNewBody(body)
            baseFeature.finishEdit()

            design: adsk.fusion.Design = _app.activeProduct
            defaultLengthUnits = design.unitsManager.defaultLengthUnits
            
            customFeatureInput = component.features.customFeatures.createInput(_customFeatureDefinition)

            # Add all dependencies first using the first face to establish the feature's geometric relationships.
            for i in range(len(gemstones)):
                gemstone = gemstones[i]
                # Use the first face as dependency to support different gemstone cuts
                if gemstone.faces.count == 0:
                    eventArgs.executeFailed = True
                    return
                firstGemstoneFace = gemstone.faces[0]
                customFeatureInput.addDependency(f'firstGemstoneFace{i}', firstGemstoneFace)

            # Add all parameters with their expressions to support user-defined equations and parametric updates.
            height = adsk.core.ValueInput.createByString(_heightValueInput.expression)             
            customFeatureInput.addCustomParameter('height', 'Height', height, defaultLengthUnits, True) 
            
            depth = adsk.core.ValueInput.createByString(_depthValueInput.expression)
            customFeatureInput.addCustomParameter('depth', 'Depth', depth, defaultLengthUnits, True)
            
            sizeRatio = adsk.core.ValueInput.createByString(_sizeRatioValueInput.expression)
            customFeatureInput.addCustomParameter('sizeRatio', 'Size Ratio', sizeRatio, '', True)

            holeRatio = adsk.core.ValueInput.createByString(_holeRatioValueInput.expression)
            customFeatureInput.addCustomParameter('holeRatio', 'Hole Ratio', holeRatio, '', True)

            coneAngle = adsk.core.ValueInput.createByString(_coneAngleValueInput.expression)
            customFeatureInput.addCustomParameter('coneAngle', 'Cone Angle', coneAngle, '', True)

            customFeatureInput.setStartAndEndFeatures(baseFeature, baseFeature)
            component.features.customFeatures.add(customFeatureInput)

        except:
            eventArgs.executeFailed = True
            showMessage(f'CreateExecuteHandler: {traceback.format_exc()}\n', True)


# This class handles the activation of the edit command for a custom cutter feature.
# It rolls back the timeline to the state before the feature, sets up transaction markers to preserve changes,
# and pre-selects the original gemstone dependencies for editing.
class EditActivateHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature, _gemstonesSelectionInput
            
            eventArgs = adsk.core.CommandEventArgs.cast(args)

            if _isRolledForEdit: return
            
            # Save the current timeline position to restore it after editing, ensuring the model state is preserved.
            design: adsk.fusion.Design = _app.activeProduct
            timeline = design.timeline
            markerPosition = timeline.markerPosition
            _restoreTimelineObject = timeline.item(markerPosition - 1)

            # Roll the timeline to just before the custom feature being edited to access the original geometry dependencies.
            _editedCustomFeature.timelineObject.rollTo(True)
            _isRolledForEdit = True

            command = eventArgs.command
            command.beginStep()

            # Iterate through all first face dependencies and add their bodies to the selection input for editing.
            i = 0
            while True:
                try:
                    dependency = _editedCustomFeature.dependencies.itemById(f'firstGemstoneFace{i}')
                    if dependency is None: break
                    firstGemstoneFace = dependency.entity
                    if firstGemstoneFace is not None and firstGemstoneFace.body is not None:
                        _gemstonesSelectionInput.addSelection(firstGemstoneFace.body)
                    i += 1
                except:
                    break

        except:
            showMessage(f'EditActivateHandler: {traceback.format_exc()}\n', True)
            pass


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
        global _editedCustomFeature, _isRolledForEdit, _restoreTimelineObject
        
        try:
            
            eventArgs = adsk.core.CommandEventArgs.cast(args)    

            # Cache gemstone entities
            gemstoneCount = _gemstonesSelectionInput.selectionCount
            gemstoneEntities = []
            for i in range(gemstoneCount):
                gemstoneEntities.append(_gemstonesSelectionInput.selection(i).entity)

            # Clear and rebuild dependencies to handle cases where the user selects different geometry during edit.
            _editedCustomFeature.dependencies.deleteAll()

            for i in range(gemstoneCount):
                gemstone = gemstoneEntities[i]
                # Use the first face as dependency to support different gemstone cuts
                if gemstone.faces.count == 0:
                    eventArgs.executeFailed = True
                    return
                firstGemstoneFace = gemstone.faces[0]
                _editedCustomFeature.dependencies.add(f'firstGemstoneFace{i}', firstGemstoneFace)

            # Update the parameters.
            _editedCustomFeature.parameters.itemById('height').expression = _heightValueInput.expression
            _editedCustomFeature.parameters.itemById('depth').expression = _depthValueInput.expression
            _editedCustomFeature.parameters.itemById('sizeRatio').expression = _sizeRatioValueInput.expression
            _editedCustomFeature.parameters.itemById('holeRatio').expression = _holeRatioValueInput.expression
            _editedCustomFeature.parameters.itemById('coneAngle').expression = _coneAngleValueInput.expression

            # Update the feature to recompute geometry and handle changes in gemstone count or parameter values.
            updateFeature(_editedCustomFeature)

        except:
            showMessage(f'EditExecuteHandler: {traceback.format_exc()}\n', True)

        finally: rollBack()


# This class handles the recomputation of the custom feature when dependencies or parameters change.
# It updates the cutter bodies within the base feature to reflect new values or geometry,
# ensuring the custom feature remains parametric and up-to-date.
class ComputeCustomFeature(adsk.fusion.CustomFeatureEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.fusion.CustomFeatureEventArgs.cast(args)
            customFeature = eventArgs.customFeature
            updateFeature(customFeature)

        except:
            showMessage(f'ComputeCustomFeature: {traceback.format_exc()}\n', True)


# Helper function to read flip state from gemstone's CustomFeature
def getFlipStatesForGemstones(gemstones: list[adsk.fusion.BRepBody]) -> list[bool]:
    flippedStates = []
    component = gemstones[0].parentComponent
    for gemstone in gemstones:
        isFlipped = False
        try:
            for feature in component.features.customFeatures:
                if feature.name.startswith(strings.GEMSTONE_COMMAND_NAME):
                    for subFeature in feature.features:
                        if subFeature.objectType == adsk.fusion.BaseFeature.classType():
                            baseFeature = adsk.fusion.BaseFeature.cast(subFeature)
                            for body in baseFeature.bodies:
                                if body.entityToken == gemstone.entityToken:
                                    flipParam = feature.parameters.itemById('flip')
                                    if flipParam:
                                        isFlipped = flipParam.expression.lower() == 'true'
                                    break
        except:
            pass
        flippedStates.append(isFlipped)
    return flippedStates


# Utility function that creates the cutter body based on the gemstone body, height, and depth.
def createBody(body: adsk.fusion.BRepBody, height: float, depth: float, sizeRatio: float = 1.0, holeRatio: float = 0.5, isFlipped: bool = False, coneAngle: float = 42.0) -> adsk.fusion.BRepBody | None:
    try:
        if body is None: return None

        temporaryBRep: adsk.fusion.TemporaryBRepManager = adsk.fusion.TemporaryBRepManager.get()
        tempBody = temporaryBRep.copy(body)

        topFace = sorted(tempBody.faces, key = lambda x: x.area, reverse = True)[0]
        topPlane = adsk.core.Plane.cast(topFace.geometry)

        lengthDirection = topPlane.uDirection
        widthDirection = topPlane.vDirection
        normal = topPlane.normal

        cylindricalFace = None
        cylinder = None

        for face in tempBody.faces:
            if face.geometry.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType:
                tempCylinder = adsk.core.Cylinder.cast(face.geometry)
                cylinderAxis = tempCylinder.axis
                if cylinderAxis.isParallelTo(normal):
                    cylindricalFace = face
                    cylinder = tempCylinder
                    break
        
        if cylindricalFace is None or cylinder is None: return None

        girdleCentroid = cylindricalFace.centroid


        # If gemstone is flipped, flip the cutter too so they point in opposite directions
        if isFlipped:
            normal.scaleBy(-1)

        radius = cylinder.radius * sizeRatio
        holeRadius = radius * holeRatio

        bodies = []

        # Create the cutter cylinder
        topPoint = adsk.core.Point3D.create(0, 0, height)
        bodies.append(temporaryBRep.createCylinderOrCone(constants.zeroPoint, radius, topPoint, radius))

        # Create the cutter cone
        theta = math.radians(coneAngle)
        h = radius * math.tan(theta)
        bottomPoint = adsk.core.Point3D.create(0, 0, -h)
        bodies.append(temporaryBRep.createCylinderOrCone(constants.zeroPoint, radius, bottomPoint, 0))

        # Create the cutter bottom cylinder
        bottomPoint = adsk.core.Point3D.create(0, 0, min(-radius, -depth))
        bodies.append(temporaryBRep.createCylinderOrCone(constants.zeroPoint, holeRadius, bottomPoint, holeRadius))

        # Combine the bodies into a single cutter body.
        cutter: adsk.fusion.BRepBody = None
        for body in bodies:
            if cutter is None:
                cutter = body
            else:
                temporaryBRep.booleanOperation(cutter, body, adsk.fusion.BooleanTypes.UnionBooleanType)

        transformation = adsk.core.Matrix3D.create()

        transformation.setToAlignCoordinateSystems(
            girdleCentroid, lengthDirection, widthDirection, normal,
            constants.zeroPoint, constants.xVector, constants.yVector, constants.zVector
            )
        temporaryBRep.transform(tempBody, transformation)

        girdleThickness = abs(cylindricalFace.boundingBox.minPoint.z - cylindricalFace.boundingBox.maxPoint.z)

        translate = normal.copy()
        translate.scaleBy(girdleThickness / -2)
        girdleCentroid.translateBy(translate)

        transformation.setToIdentity()
        transformation.setWithCoordinateSystem(girdleCentroid, lengthDirection, widthDirection, normal)
        temporaryBRep.transform(cutter, transformation)

        return cutter
    
    except:
        showMessage(f'CreateBodies: {traceback.format_exc()}\n', True)
        return None
    

# Updates the bodies of an existing custom cutter feature.
def updateFeature(customFeature: adsk.fusion.CustomFeature) -> bool:
    try:
        # Locate the base feature that contains the cutter bodies within the custom feature's feature collection.
        baseFeature: adsk.fusion.BaseFeature = None

        for feature in customFeature.features:
            if feature.objectType == adsk.fusion.BaseFeature.classType():
                baseFeature = feature
        if baseFeature is None: return False

        # Collect all first face dependencies in order to regenerate cutters for each gemstone.
        firstGemstoneFaces: list[adsk.fusion.BRepFace] = []
        i = 0
        while True:
            dependency = customFeature.dependencies.itemById(f'firstGemstoneFace{i}')
            if dependency is None: break
            firstGemstoneFace = dependency.entity
            if firstGemstoneFace is None: break
            firstGemstoneFaces.append(firstGemstoneFace)
            i += 1
        if len(firstGemstoneFaces) == 0: return False

        # Get gemstones from first faces
        gemstones: list[adsk.fusion.BRepBody] = [face.body for face in firstGemstoneFaces]

        height = customFeature.parameters.itemById('height').value
        depth = customFeature.parameters.itemById('depth').value
        sizeRatio = customFeature.parameters.itemById('sizeRatio').value
        holeRatio = customFeature.parameters.itemById('holeRatio').value
        coneAngle = customFeature.parameters.itemById('coneAngle').value

        component = gemstones[0].parentComponent
        flippedStates = getFlipStatesForGemstones(gemstones)

        baseFeature.startEdit()
        
        # Update existing bodies or add new ones to handle parameter changes and gemstone count modifications.
        for i in range(len(gemstones)):
            gemstone = gemstones[i]
            isFlipped = flippedStates[i]
            
            cutter = createBody(gemstone, height, depth, sizeRatio, holeRatio, isFlipped, coneAngle)
            if cutter is None:
                baseFeature.finishEdit()
                return False

            if i < baseFeature.bodies.count:
                currentBody = baseFeature.bodies.item(i)
                baseFeature.updateBody(currentBody, cutter)
                
            else:
                newBody = component.bRepBodies.add(cutter, baseFeature)
                handleNewBody(newBody)

        # Remove extra bodies if the gemstone count has decreased during editing.
        while baseFeature.bodies.count > len(gemstones):
            baseFeature.bodies.item(baseFeature.bodies.count - 1).deleteMe()

        baseFeature.finishEdit()

        return True
    
    except:
        showMessage(f'UpdateFeature: {traceback.format_exc()}\n', True)
        return False
    

def handleNewBody(body: adsk.fusion.BRepBody) -> bool:
    try:
        body.name = strings.CUTTER
        body.attributes.add(strings.PREFIX, strings.ENTITY, strings.CUTTER)
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