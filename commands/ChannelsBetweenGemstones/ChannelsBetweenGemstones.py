import os
import adsk.core, adsk.fusion, traceback
import json

from ... import strings
from ...helpers.showMessage import showMessage
from ...helpers.Gemstones import GemstoneInfo, extractGemstonesInfo, findValidConnections


_handlers = []

_app: adsk.core.Application = None
_ui: adsk.core.UserInterface = None

_customFeatureDefinition: adsk.fusion.CustomFeature = None

_editedCustomFeature: adsk.fusion.CustomFeature = None
_restoreTimelineObject: adsk.fusion.TimelineObject = None
_isRolledForEdit: bool = False

_gemstonesSelectionInput: adsk.core.SelectionCommandInput = None

_ratioValueInput: adsk.core.ValueCommandInput = None
_maxGapValueInput: adsk.core.ValueCommandInput = None


RESOURCES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

COMMAND_ID = strings.PREFIX + strings.CHANNELS_BETWEEN_GEMSTONES
CREATE_COMMAND_ID = COMMAND_ID + 'Create'
EDIT_COMMAND_ID = COMMAND_ID + 'Edit'

createCommandInputDef = strings.InputDef(CREATE_COMMAND_ID, 'Create Channels Between Gemstones', 'Creates a network of channels connecting nearby gemstones based on distance constraint.')
editCommandInputDef = strings.InputDef(EDIT_COMMAND_ID, 'Edit Channels Between Gemstones', 'Edits the parameters of existing channels between gemstones.')

selectGemstonesInputDef = strings.InputDef(
    'selectGemstones',
    'Select Gemstones',
    'Select at least 2 gemstones to create a channel.'
    )

ratioInputDef = strings.InputDef(
    'ratio', 
    'Channel Ratio', 
    "Channel width relative to gemstone size.\nFrom 0.2 to 0.8 of gemstone diameter (0.5 = half diameter)."
    )

maxGapInputDef = strings.InputDef(
    'maxGap', 
    'Max Gap', 
    "Maximum gap between gemstones for channel creation.\nChannels connect gemstones closer than this distance (0.5 mm default)."
    )


def run(panel: adsk.core.ToolbarPanel):
    """Initialize the channels between gemstones command by setting up command definitions and UI elements."""
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

        _customFeatureDefinition = adsk.fusion.CustomFeatureDefinition.create(COMMAND_ID, strings.CHANNELS_BETWEEN_GEMSTONES, RESOURCES_FOLDER)
        _customFeatureDefinition.editCommandId = EDIT_COMMAND_ID

        computeCustomFeature = ComputeCustomFeature()
        _customFeatureDefinition.customFeatureCompute.add(computeCustomFeature)
        _handlers.append(computeCustomFeature)
    except:
        showMessage(f'Run failed:\n{traceback.format_exc()}', True)


def stop(panel: adsk.core.ToolbarPanel):
    """Clean up the channels between gemstones command by removing UI elements and handlers."""
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
    """Event handler for creating the command dialog for new channels between gemstones.
    
    This handler sets up all necessary input controls including selections for gemstones 
    and value inputs for ratio and max gap, and connects event handlers for validation,
    preview, and execution.
    """
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _gemstonesSelectionInput, _ratioValueInput, _maxGapValueInput
            
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs
            defaultLengthUnits = _app.activeProduct.unitsManager.defaultLengthUnits

            _gemstonesSelectionInput = inputs.addSelectionInput(selectGemstonesInputDef.id, selectGemstonesInputDef.name, selectGemstonesInputDef.tooltip)
            _gemstonesSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Bodies)
            _gemstonesSelectionInput.tooltip = selectGemstonesInputDef.tooltip
            _gemstonesSelectionInput.setSelectionLimits(2)

            inputs.addSeparatorCommandInput('separatorAfterGemstones')

            ratio = adsk.core.ValueInput.createByReal(0.35)
            _ratioValueInput = inputs.addValueInput(ratioInputDef.id, ratioInputDef.name, '', ratio)
            _ratioValueInput.tooltip = ratioInputDef.tooltip

            maxGap = adsk.core.ValueInput.createByReal(0.05)
            _maxGapValueInput = inputs.addValueInput(maxGapInputDef.id, maxGapInputDef.name, defaultLengthUnits, maxGap)
            _maxGapValueInput.tooltip = maxGapInputDef.tooltip

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
    """Event handler for creating the command dialog for editing existing channels.
    
    This handler retrieves the selected custom feature, populates inputs with existing parameter 
    values and dependencies, and connects event handlers for editing operations including 
    activation, validation, preview, and execution.
    """
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _editedCustomFeature, _gemstonesSelectionInput, _ratioValueInput, _maxGapValueInput
            
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs
            defaultLengthUnits = _app.activeProduct.unitsManager.defaultLengthUnits

            _editedCustomFeature = _ui.activeSelections.item(0).entity
            if _editedCustomFeature is None:
                return

            _gemstonesSelectionInput = inputs.addSelectionInput(selectGemstonesInputDef.id, selectGemstonesInputDef.name, selectGemstonesInputDef.tooltip)
            _gemstonesSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Bodies)
            _gemstonesSelectionInput.tooltip = selectGemstonesInputDef.tooltip
            _gemstonesSelectionInput.setSelectionLimits(2)

            inputs.addSeparatorCommandInput('separatorAfterGemstones')

            parameters = _editedCustomFeature.parameters

            ratio = adsk.core.ValueInput.createByString(parameters.itemById(ratioInputDef.id).expression)
            _ratioValueInput = inputs.addValueInput(ratioInputDef.id, ratioInputDef.name, '', ratio)
            _ratioValueInput.tooltip = ratioInputDef.tooltip

            maxGap = adsk.core.ValueInput.createByString(parameters.itemById(maxGapInputDef.id).expression)
            _maxGapValueInput = inputs.addValueInput(maxGapInputDef.id, maxGapInputDef.name, defaultLengthUnits, maxGap)
            _maxGapValueInput.tooltip = maxGapInputDef.tooltip

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

            onInputChanged = EditInputChangedHandler()
            command.inputChanged.add(onInputChanged)
            _handlers.append(onInputChanged)

        except:
            showMessage(f'EditCommandCreatedHandler: {traceback.format_exc()}\n', True)


class PreSelectHandler(adsk.core.SelectionEventHandler):
    """Event handler for controlling user selection during command execution.
    
    This handler checks to ensure the gemstones are valid bodies and not external references.
    """
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

                attribute = preSelectBody.attributes.itemByName(strings.PREFIX, strings.PROPERTIES)
                if attribute is None:
                    eventArgs.isSelectable = False
                    return
                
                try:
                    properties = json.loads(attribute.value)
                    if properties.get(strings.ENTITY) != strings.GEMSTONE:
                        eventArgs.isSelectable = False
                        return
                except:
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

            # Verify the input has valid expression.
            if not _ratioValueInput.isValidExpression:
                eventArgs.areInputsValid = False
                return

            # Enforce ratio constraints.
            if not (_ratioValueInput.value >= 0.2 and _ratioValueInput.value <= 0.8):
                eventArgs.areInputsValid = False
                return

            # Verify maxGap has valid expression.
            if not _maxGapValueInput.isValidExpression:
                eventArgs.areInputsValid = False
                return

            # Enforce maxGap constraints (0 to 1 mm = 0 to 0.1 cm).
            if not (_maxGapValueInput.value >= 0.0 and _maxGapValueInput.value <= 0.1):
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
            if _gemstonesSelectionInput.selectionCount < 2: return

            gemstones: list[adsk.fusion.BRepBody] = []
            for i in range(_gemstonesSelectionInput.selectionCount):
                gemstone = _gemstonesSelectionInput.selection(i).entity
                if gemstone is None: continue
                gemstones.append(gemstone)

            if len(gemstones) < 2: return

            ratio = _ratioValueInput.value
            maxGap = _maxGapValueInput.value
            
            # Create the complete channel body
            channel = createBody(gemstones, ratio, maxGap)
            if channel is None: return

            component = gemstones[0].parentComponent

            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()
            body = component.bRepBodies.add(channel, baseFeature)
            handleNewBody(body)
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

            gemstones: list[adsk.fusion.BRepBody] = []
            for i in range(_gemstonesSelectionInput.selectionCount):
                gemstones.append(_gemstonesSelectionInput.selection(i).entity)

            # Create the complete channel body
            channel = createBody(gemstones, _ratioValueInput.value, _maxGapValueInput.value)
            if channel is None:
                eventArgs.executeFailed = True
                showMessage('Failed to create channel body.\n', True)
                return

            # Create a base feature and add the channel body.
            component = gemstones[0].parentComponent
            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()
            body = component.bRepBodies.add(channel, baseFeature)
            handleNewBody(body)
            baseFeature.finishEdit()

            design: adsk.fusion.Design = _app.activeProduct
            
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

            # Add parameter with expression to support user-defined equations and parametric updates.
            ratio = adsk.core.ValueInput.createByString(_ratioValueInput.expression)
            customFeatureInput.addCustomParameter(ratioInputDef.id, ratioInputDef.name, ratio, '', True)

            design: adsk.fusion.Design = _app.activeProduct
            defaultLengthUnits = design.unitsManager.defaultLengthUnits
            
            maxGap = adsk.core.ValueInput.createByString(_maxGapValueInput.expression)
            customFeatureInput.addCustomParameter(maxGapInputDef.id, maxGapInputDef.name, maxGap, defaultLengthUnits, True)

            customFeatureInput.setStartAndEndFeatures(baseFeature, baseFeature)
            component.features.customFeatures.add(customFeatureInput)

        except:
            baseFeature.finishEdit()
            eventArgs.executeFailed = True
            showMessage(f'CreateExecuteHandler: {traceback.format_exc()}\n', True)


class EditActivateHandler(adsk.core.CommandEventHandler):
    """Event handler for the activation of the edit command for a custom channel feature.
    
    This handler rolls back the timeline to the state before the feature, sets up transaction markers 
    to preserve changes, and pre-selects the original gemstone dependencies for editing.
    """
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
        global _editedCustomFeature, _isRolledForEdit, _restoreTimelineObject
        
        try:
            
            eventArgs = adsk.core.CommandEventArgs.cast(args)    

            gemstoneCount = _gemstonesSelectionInput.selectionCount
            gemstoneEntities = []
            for i in range(gemstoneCount):
                gemstoneEntities.append(_gemstonesSelectionInput.selection(i).entity)

            _editedCustomFeature.dependencies.deleteAll()

            for i in range(gemstoneCount):
                gemstone = gemstoneEntities[i]
                if gemstone.faces.count == 0:
                    eventArgs.executeFailed = True
                    return
                firstGemstoneFace = gemstone.faces[0]
                _editedCustomFeature.dependencies.add(f'firstGemstoneFace{i}', firstGemstoneFace)

            _editedCustomFeature.parameters.itemById('ratio').expression = _ratioValueInput.expression
            _editedCustomFeature.parameters.itemById('maxGap').expression = _maxGapValueInput.expression

        except:
            showMessage(f'EditExecuteHandler: {traceback.format_exc()}\n', True)

        finally: rollBack()


class ComputeCustomFeature(adsk.fusion.CustomFeatureEventHandler):
    """Event handler for the recomputation of the custom feature.
    
    This handler updates the channel bodies within the base feature to reflect new values or geometry,
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

class EditInputChangedHandler(adsk.core.InputChangedEventHandler):
    """Event handler for the inputChanged event of the edit command."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.InputChangedEventArgs.cast(args)
            # customFeature = eventArgs
            # updateFeature(customFeature)

        except:
            showMessage(f'EditInputChangedHandler: {traceback.format_exc()}\n', True)


def createChannelSegment(info1: GemstoneInfo, info2: GemstoneInfo, ratio: float = 0.5) -> adsk.fusion.BRepBody | None:
    """
    Create a cylinder or cone connecting two gemstones.
    If gemstones have different radii, creates a cone. Otherwise creates a cylinder.
    Takes into account absolute and relative depth offsets and flip state of each gemstone.
    """
    try:
        temporaryBRep: adsk.fusion.TemporaryBRepManager = adsk.fusion.TemporaryBRepManager.get()
        
        # Use pre-computed centroids and radii
        centroid1 = info1.centroid.copy()
        centroid2 = info2.centroid.copy()
        
        # Get normalized normal and total offset for first gemstone
        normal1 = info1.getNormalizedNormal()
        if normal1 is not None:
            totalDepthOffset1 = info1.getTotalDepthOffset()
            normal1.scaleBy(-totalDepthOffset1)
            centroid1.translateBy(normal1)
        
        # Get normalized normal and total offset for second gemstone
        normal2 = info2.getNormalizedNormal()
        if normal2 is not None:
            totalDepthOffset2 = info2.getTotalDepthOffset()
            normal2.scaleBy(-totalDepthOffset2)
            centroid2.translateBy(normal2)
        
        radius1 = info1.radius * ratio
        radius2 = info2.radius * ratio
        
        channel = temporaryBRep.createCylinderOrCone(centroid1, radius1, centroid2, radius2)
        
        return channel
    
    except:
        showMessage(f'createChannelSegment: {traceback.format_exc()}\n', True)
        return None


def createBody(gemstones: list[adsk.fusion.BRepBody], ratio: float = 0.5, maxGap: float = 0.05) -> adsk.fusion.BRepBody | None:
    """Create a complete channel body connecting multiple gemstones.

    Args:
        gemstones: List of gemstone bodies to connect.
        ratio: Ratio of channel diameter to gemstone diameter.
        maxGap: Maximum gap between gemstones to create connections.

    Returns:
        The created channel body or None if creation failed.
    """
    """
    Create a complete channel body connecting gemstones within distance constraint.
    Creates a network of channels between all gemstones that are close enough.
    Returns a single unified body with all segments combined.
    """
    try:
        if not gemstones or len(gemstones) < 2:
            return None
        
        # Extract geometric information from all gemstones once
        gemstoneInfos = extractGemstonesInfo(gemstones)
        if gemstoneInfos is None or len(gemstoneInfos) < 2:
            return None
        
        # Find all valid connections based on distance constraint
        connections = findValidConnections(gemstoneInfos, maxGap)
        
        if not connections:
            return None
        
        temporaryBRep: adsk.fusion.TemporaryBRepManager = adsk.fusion.TemporaryBRepManager.get()
        
        channel = None
        
        # Create channel segments for all valid connections
        for info1, info2 in connections:
            segment = createChannelSegment(info1, info2, ratio)
            if segment is None: continue
            if channel is None: channel = segment
            else: temporaryBRep.booleanOperation(channel, segment, adsk.fusion.BooleanTypes.UnionBooleanType)
        return channel
    
    except:
        showMessage(f'createBody: {traceback.format_exc()}\n', True)
        return None
    

def updateFeature(customFeature: adsk.fusion.CustomFeature) -> bool:
    """Update the bodies of an existing custom channels feature.

    Args:
        customFeature: The custom feature to update.

    Returns:
        True if the update was successful, False otherwise.
    """
    try:
        # Locate the base feature that contains the channel body within the custom feature's feature collection.
        baseFeature: adsk.fusion.BaseFeature = None

        for feature in customFeature.features:
            if feature.objectType == adsk.fusion.BaseFeature.classType():
                baseFeature = feature
        if baseFeature is None: return False

        # Collect all first face dependencies in order to regenerate channel for each gemstone.
        firstGemstoneFaces: list[adsk.fusion.BRepFace] = []
        i = 0
        while True:
            dependency = customFeature.dependencies.itemById(f'firstGemstoneFace{i}')
            if dependency is None: break
            firstGemstoneFace = dependency.entity
            if firstGemstoneFace is None: break
            firstGemstoneFaces.append(firstGemstoneFace)
            i += 1
        if len(firstGemstoneFaces) < 2: return False

        # Get gemstones from first faces
        gemstones: list[adsk.fusion.BRepBody] = [face.body for face in firstGemstoneFaces]

        ratio = customFeature.parameters.itemById('ratio').value
        maxGap = customFeature.parameters.itemById('maxGap').value

        # Create the complete channel body
        channel = createBody(gemstones, ratio, maxGap)
        if channel is None:
            return False

        # Get the correct component for the custom feature
        component = customFeature.parentComponent

        baseFeature.startEdit()
        
        # Update or create the channel body
        if baseFeature.bodies.count > 0:
            currentBody = baseFeature.bodies.item(0)
            baseFeature.updateBody(currentBody, channel)
        else:
            component.bRepBodies.add(channel, baseFeature)

        # Remove extra bodies if any exist (there should only be one channel body)
        while baseFeature.bodies.count > 1:
            baseFeature.bodies.item(baseFeature.bodies.count - 1).deleteMe()

        baseFeature.finishEdit()

        return True
    
    except:
        baseFeature.finishEdit()
        showMessage(f'UpdateFeature: {traceback.format_exc()}\n', True)
        return False
    

def handleNewBody(body: adsk.fusion.BRepBody):
    """Handle the creation of a new channel body by setting its name and attributes.

    Args:
        body: The new channel body to handle.
    """
    body.name = strings.CHANNEL
    body.attributes.add(strings.PREFIX, strings.ENTITY, strings.CHANNEL)

def updateAttributes():
    """Update the attributes of all channel bodies in the edited custom feature."""
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