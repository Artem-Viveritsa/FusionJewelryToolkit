import os
import adsk.core, adsk.fusion, traceback
import json

from ... import strings
from ...helpers.showMessage import showMessage
from ...helpers.Gemstones import extractGemstonesInfo, findValidConnections
from ...helpers.Prongs import createProngInfosFromConnections, createProngFromInfo, updateProngFromInfo, createProngInfosFromConnections, setProngAttributes, updateProngFeature


_handlers = []

_app: adsk.core.Application = None
_ui: adsk.core.UserInterface = None

_customFeatureDefinition: adsk.fusion.CustomFeature = None

_editedCustomFeature: adsk.fusion.CustomFeature = None
_restoreTimelineObject: adsk.fusion.TimelineObject = None
_isRolledForEdit: bool = False

_gemstonesSelectionInput: adsk.core.SelectionCommandInput = None

_sizeRatioValueInput: adsk.core.ValueCommandInput = None
_heightRatioValueInput: adsk.core.ValueCommandInput = None
_widthBetweenProngsRatioValueInput: adsk.core.ValueCommandInput = None
_maxGapValueInput: adsk.core.ValueCommandInput = None
_weldDistanceValueInput: adsk.core.ValueCommandInput = None


RESOURCES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

COMMAND_ID = strings.PREFIX + strings.PRONGS_BETWEEN_GEMSTONES
CREATE_COMMAND_ID = COMMAND_ID + 'Create'
EDIT_COMMAND_ID = COMMAND_ID + 'Edit'

createCommandInputDef = strings.InputDef(CREATE_COMMAND_ID, 'Create Prongs Between Gemstones', 'Creates prongs at the midpoint between nearby gemstones based on distance constraint.')
editCommandInputDef = strings.InputDef(EDIT_COMMAND_ID, 'Edit Prongs Between Gemstones', 'Edits the parameters of existing prongs between gemstones.')

selectGemstonesInputDef = strings.InputDef(
    'selectGemstones',
    'Select Gemstones',
    'Select at least 2 gemstones to create prongs between them.'
    )

sizeRatioInputDef = strings.InputDef(
    'sizeRatio', 
    'Prong Size Ratio', 
    "Prong size relative to average gemstone diameter.\nFrom 0.1 to 0.5 of average diameter (0.3 default)."
    )

heightRatioInputDef = strings.InputDef(
    'heightRatio', 
    'Prong Height Ratio', 
    "Prong height relative to average gemstone diameter.\nFrom 0.1 to 1.0 of average diameter (0.3 default)."
    )

widthBetweenProngsRatioInputDef = strings.InputDef(
    'widthBetweenProngsRatio', 
    'Width Between Prongs Ratio', 
    "Spacing between prong pair.\nFrom 0.1 to 1.0 of average gemstone diameter (0.5 default)."
    )

maxGapInputDef = strings.InputDef(
    'maxGap', 
    'Max Gap', 
    "Maximum gap between gemstones for prong creation.\nProngs connect gemstones closer than this distance (0.5 mm default)."
    )

weldDistanceInputDef = strings.InputDef(
    'weldDistance', 
    'Weld Distance', 
    "Distance for merging nearby prongs.\nProngs closer than this will combine into one (0.3 mm default)."
    )


def run(panel: adsk.core.ToolbarPanel):
    """Initialize the prongs between gemstones command by setting up command definitions and UI elements."""
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

        _customFeatureDefinition = adsk.fusion.CustomFeatureDefinition.create(COMMAND_ID, strings.PRONGS_BETWEEN_GEMSTONES, RESOURCES_FOLDER)
        _customFeatureDefinition.editCommandId = EDIT_COMMAND_ID

        computeCustomFeature = ComputeCustomFeature()
        _customFeatureDefinition.customFeatureCompute.add(computeCustomFeature)
        _handlers.append(computeCustomFeature)
    except:
        showMessage(f'Run failed:\n{traceback.format_exc()}', True)


def stop(panel: adsk.core.ToolbarPanel):
    """Clean up the prongs between gemstones command by removing UI elements and handlers."""
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
    """Event handler for creating the command dialog for new prongs between gemstones.
    
    This handler sets up all necessary input controls including selections for gemstones 
    and value inputs for prong size, height, and max gap, and connects event handlers for validation,
    preview, and execution.
    """
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _gemstonesSelectionInput, _sizeRatioValueInput, _heightRatioValueInput, _widthBetweenProngsRatioValueInput, _maxGapValueInput, _weldDistanceValueInput
            
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs
            defaultLengthUnits = _app.activeProduct.unitsManager.defaultLengthUnits

            _gemstonesSelectionInput = inputs.addSelectionInput(selectGemstonesInputDef.id, selectGemstonesInputDef.name, selectGemstonesInputDef.tooltip)
            _gemstonesSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Bodies)
            _gemstonesSelectionInput.tooltip = selectGemstonesInputDef.tooltip
            _gemstonesSelectionInput.setSelectionLimits(2)

            inputs.addSeparatorCommandInput('separatorAfterGemstones')

            sizeRatio = adsk.core.ValueInput.createByReal(0.35)
            _sizeRatioValueInput = inputs.addValueInput(sizeRatioInputDef.id, sizeRatioInputDef.name, '', sizeRatio)
            _sizeRatioValueInput.tooltip = sizeRatioInputDef.tooltip

            heightRatio = adsk.core.ValueInput.createByReal(0.3)
            _heightRatioValueInput = inputs.addValueInput(heightRatioInputDef.id, heightRatioInputDef.name, '', heightRatio)
            _heightRatioValueInput.tooltip = heightRatioInputDef.tooltip

            widthBetweenProngsRatio = adsk.core.ValueInput.createByReal(0.65)
            _widthBetweenProngsRatioValueInput = inputs.addValueInput(widthBetweenProngsRatioInputDef.id, widthBetweenProngsRatioInputDef.name, '', widthBetweenProngsRatio)
            _widthBetweenProngsRatioValueInput.tooltip = widthBetweenProngsRatioInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterWidthBetweenProngsRatio')

            maxGap = adsk.core.ValueInput.createByReal(0.05)
            _maxGapValueInput = inputs.addValueInput(maxGapInputDef.id, maxGapInputDef.name, defaultLengthUnits, maxGap)
            _maxGapValueInput.tooltip = maxGapInputDef.tooltip

            weldDistance = adsk.core.ValueInput.createByReal(0.03)
            _weldDistanceValueInput = inputs.addValueInput(weldDistanceInputDef.id, weldDistanceInputDef.name, defaultLengthUnits, weldDistance)
            _weldDistanceValueInput.tooltip = weldDistanceInputDef.tooltip

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
    """Event handler for creating the command dialog for editing existing prongs between gemstones.
    
    This handler retrieves the selected custom feature, populates inputs with existing parameter 
    values and dependencies, and connects event handlers for editing operations including 
    activation, validation, preview, and execution.
    """
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _editedCustomFeature, _gemstonesSelectionInput, _sizeRatioValueInput, _heightRatioValueInput, _widthBetweenProngsRatioValueInput, _maxGapValueInput, _weldDistanceValueInput
            
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

            sizeRatio = adsk.core.ValueInput.createByString(parameters.itemById(sizeRatioInputDef.id).expression)
            _sizeRatioValueInput = inputs.addValueInput(sizeRatioInputDef.id, sizeRatioInputDef.name, '', sizeRatio)
            _sizeRatioValueInput.tooltip = sizeRatioInputDef.tooltip

            heightRatio = adsk.core.ValueInput.createByString(parameters.itemById(heightRatioInputDef.id).expression)
            _heightRatioValueInput = inputs.addValueInput(heightRatioInputDef.id, heightRatioInputDef.name, '', heightRatio)
            _heightRatioValueInput.tooltip = heightRatioInputDef.tooltip

            widthBetweenProngsRatio = adsk.core.ValueInput.createByString(parameters.itemById(widthBetweenProngsRatioInputDef.id).expression)
            _widthBetweenProngsRatioValueInput = inputs.addValueInput(widthBetweenProngsRatioInputDef.id, widthBetweenProngsRatioInputDef.name, '', widthBetweenProngsRatio)
            _widthBetweenProngsRatioValueInput.tooltip = widthBetweenProngsRatioInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterWidthBetweenProngsRatio')

            maxGap = adsk.core.ValueInput.createByString(parameters.itemById(maxGapInputDef.id).expression)
            _maxGapValueInput = inputs.addValueInput(maxGapInputDef.id, maxGapInputDef.name, defaultLengthUnits, maxGap)
            _maxGapValueInput.tooltip = maxGapInputDef.tooltip

            weldDistance = adsk.core.ValueInput.createByString(parameters.itemById(weldDistanceInputDef.id).expression)
            _weldDistanceValueInput = inputs.addValueInput(weldDistanceInputDef.id, weldDistanceInputDef.name, defaultLengthUnits, weldDistance)
            _weldDistanceValueInput.tooltip = weldDistanceInputDef.tooltip

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

            if not _sizeRatioValueInput.isValidExpression:
                eventArgs.areInputsValid = False
                return

            if not (_sizeRatioValueInput.value >= 0.1 and _sizeRatioValueInput.value <= 0.5):
                eventArgs.areInputsValid = False
                return

            if not _heightRatioValueInput.isValidExpression:
                eventArgs.areInputsValid = False
                return

            if not (_heightRatioValueInput.value >= 0.1 and _heightRatioValueInput.value <= 1.0):
                eventArgs.areInputsValid = False
                return

            if not _widthBetweenProngsRatioValueInput.isValidExpression:
                eventArgs.areInputsValid = False
                return

            if not (_widthBetweenProngsRatioValueInput.value >= 0.1 and _widthBetweenProngsRatioValueInput.value <= 1.0):
                eventArgs.areInputsValid = False
                return

            if not _maxGapValueInput.isValidExpression:
                eventArgs.areInputsValid = False
                return

            if not (_maxGapValueInput.value >= 0.0 and _maxGapValueInput.value <= 0.1):
                eventArgs.areInputsValid = False
                return

            if not _weldDistanceValueInput.isValidExpression:
                eventArgs.areInputsValid = False
                return

            if not (_weldDistanceValueInput.value >= 0.0 and _weldDistanceValueInput.value <= 0.05):
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
            gemstones = getSelectedGemstones()
            if not gemstones:
                return

            sizeRatio = _sizeRatioValueInput.value
            heightRatio = _heightRatioValueInput.value
            widthBetweenProngsRatio = _widthBetweenProngsRatioValueInput.value
            maxGap = _maxGapValueInput.value
            weldDistance = _weldDistanceValueInput.value
            
            
            prongs = createBodies(gemstones, sizeRatio, heightRatio, widthBetweenProngsRatio, maxGap, weldDistance)
            if not prongs:
                return

            component = gemstones[0].parentComponent

            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()
            for prong in prongs:
                body = component.bRepBodies.add(prong, baseFeature)
                setProngAttributes(body)
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

            gemstones = getSelectedGemstones()
            if not gemstones:
                eventArgs.executeFailed = True
                showMessage('Please select at least 2 gemstones.\n', True)
                return

            
            prongs = createBodies(gemstones, _sizeRatioValueInput.value, _heightRatioValueInput.value, _widthBetweenProngsRatioValueInput.value, _maxGapValueInput.value, _weldDistanceValueInput.value)
            if not prongs:
                eventArgs.executeFailed = True
                showMessage('Failed to create prongs.\n', True)
                return

            
            component = gemstones[0].parentComponent
            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()
            for prong in prongs:
                body = component.bRepBodies.add(prong, baseFeature)
                setProngAttributes(body)
            baseFeature.finishEdit()

            design: adsk.fusion.Design = _app.activeProduct
            customFeatureInput = component.features.customFeatures.createInput(_customFeatureDefinition)

            
            for i in range(len(gemstones)):
                gemstone = gemstones[i]
                
                if gemstone.faces.count == 0:
                    eventArgs.executeFailed = True
                    return
                firstGemstoneFace = gemstone.faces[0]
                customFeatureInput.addDependency(f'firstGemstoneFace{i}', firstGemstoneFace)

            
            defaultLengthUnits = design.unitsManager.defaultLengthUnits
            
            sizeRatio = adsk.core.ValueInput.createByString(_sizeRatioValueInput.expression)
            customFeatureInput.addCustomParameter(sizeRatioInputDef.id, sizeRatioInputDef.name, sizeRatio, '', True)

            heightRatio = adsk.core.ValueInput.createByString(_heightRatioValueInput.expression)
            customFeatureInput.addCustomParameter(heightRatioInputDef.id, heightRatioInputDef.name, heightRatio, '', True)

            widthBetweenProngsRatio = adsk.core.ValueInput.createByString(_widthBetweenProngsRatioValueInput.expression)
            customFeatureInput.addCustomParameter(widthBetweenProngsRatioInputDef.id, widthBetweenProngsRatioInputDef.name, widthBetweenProngsRatio, '', True)
            
            maxGap = adsk.core.ValueInput.createByString(_maxGapValueInput.expression)
            customFeatureInput.addCustomParameter(maxGapInputDef.id, maxGapInputDef.name, maxGap, defaultLengthUnits, True)

            weldDistance = adsk.core.ValueInput.createByString(_weldDistanceValueInput.expression)
            customFeatureInput.addCustomParameter(weldDistanceInputDef.id, weldDistanceInputDef.name, weldDistance, defaultLengthUnits, True)

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
            pass


class EditDestroyHandler(adsk.core.CommandEventHandler):
    """Event handler for the destroy event of the edit command."""
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


class EditExecuteHandler(adsk.core.CommandEventHandler):
    """Event handler for the execute event of the edit command."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        global _editedCustomFeature, _isRolledForEdit, _restoreTimelineObject
        
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

            
            _editedCustomFeature.parameters.itemById('sizeRatio').expression = _sizeRatioValueInput.expression
            _editedCustomFeature.parameters.itemById('heightRatio').expression = _heightRatioValueInput.expression
            _editedCustomFeature.parameters.itemById('widthBetweenProngsRatio').expression = _widthBetweenProngsRatioValueInput.expression
            _editedCustomFeature.parameters.itemById('maxGap').expression = _maxGapValueInput.expression
            _editedCustomFeature.parameters.itemById('weldDistance').expression = _weldDistanceValueInput.expression

            
            updateFeature(_editedCustomFeature)

        except:
            showMessage(f'EditExecuteHandler: {traceback.format_exc()}\n', True)

        finally: 
            rollBack()


class ComputeCustomFeature(adsk.fusion.CustomFeatureEventHandler):
    """Event handler for the recomputation of the custom feature.
    
    This handler updates the prong bodies within the base feature to reflect new values or geometry,
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


def createBodies(gemstones: list[adsk.fusion.BRepBody], sizeRatio: float, heightRatio: float, widthBetweenProngsRatio: float, maxGap: float = 0.05, weldDistance: float = 0.03) -> list[adsk.fusion.BRepBody] | None:
    """Create prongs between nearby gemstones using ProngInfo workflow.

    Args:
        gemstones: List of gemstone bodies to connect.
        sizeRatio: The ratio of the prong size to the average diameter of the two gemstones.
        heightRatio: The ratio of the prong height to the average diameter of the two gemstones.
        widthBetweenProngsRatio: The ratio of the distance between two prongs to the average diameter.
        maxGap: Maximum gap between gemstones to create prongs, in cm (0.05 cm = 0.5 mm default).
        weldDistance: Distance threshold for merging nearby prongs, in cm (0.03 cm = 0.3 mm default, range 0.0-0.5 cm = 0.0-5.0 mm).

    Returns:
        List of created prong bodies or None if creation failed.
    """
    try:
        if not gemstones or len(gemstones) < 2:
            return None
        
        
        gemstoneInfos = extractGemstonesInfo(gemstones)
        if gemstoneInfos is None or len(gemstoneInfos) < 2:
            return None
        
        
        connections = findValidConnections(gemstoneInfos, maxGap)
        
        if not connections:
            return None
        
        
        prongInfos = createProngInfosFromConnections(connections, gemstoneInfos, sizeRatio, heightRatio, widthBetweenProngsRatio, weldDistance)
        
        if not prongInfos:
            return None
        
        
        prongs = []
        for prongInfo in prongInfos:
            prong = createProngFromInfo(prongInfo)
            if prong is not None:
                prongs.append(prong)
        
        return prongs if len(prongs) > 0 else None
    
    except:
        showMessage(f'createBody: {traceback.format_exc()}\n', True)
        return None
    

def updateFeature(customFeature: adsk.fusion.CustomFeature) -> bool:
    """Update the bodies of an existing custom prongs feature using ProngInfo workflow.

    Args:
        customFeature: The custom feature to update.

    Returns:
        True if the update was successful, False otherwise.
        
    Note:
        All length values (maxGap, weldDistance) are expected to be in centimeters.
        Values use internal Fusion 360 units where 0.05 cm = 0.5 mm, 0.03 cm = 0.3 mm.
    """
    try:
        
        baseFeature: adsk.fusion.BaseFeature = None

        for feature in customFeature.features:
            if feature.objectType == adsk.fusion.BaseFeature.classType():
                baseFeature = feature
        if baseFeature is None: return False

        
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

        
        gemstones: list[adsk.fusion.BRepBody] = [face.body for face in firstGemstoneFaces]

        
        gemstoneInfos = extractGemstonesInfo(gemstones)
        if gemstoneInfos is None or len(gemstoneInfos) < 2:
            return False

        sizeRatio = customFeature.parameters.itemById('sizeRatio').value
        heightRatio = customFeature.parameters.itemById('heightRatio').value
        widthBetweenProngsRatio = customFeature.parameters.itemById('widthBetweenProngsRatio').value
        maxGap = customFeature.parameters.itemById('maxGap').value
        weldDistance = customFeature.parameters.itemById('weldDistance').value

        
        connections = findValidConnections(gemstoneInfos, maxGap)
        prongInfos = createProngInfosFromConnections(connections, gemstoneInfos, sizeRatio, heightRatio, widthBetweenProngsRatio, weldDistance)
        
        baseFeature.startEdit()

        if connections is None or len(connections) == 0:
            while baseFeature.bodies.count > 0:
                baseFeature.bodies.item(0).deleteMe()
            baseFeature.finishEdit()
            return True

        if not prongInfos:
            while baseFeature.bodies.count > 0:
                baseFeature.bodies.item(0).deleteMe()
            baseFeature.finishEdit()
            return True
        
        component = customFeature.parentComponent
        
        
        existingBodies = [baseFeature.bodies.item(i) for i in range(baseFeature.bodies.count)]
        
        
        for i, prongInfo in enumerate(prongInfos):
            if i < len(existingBodies):
                
                updatedBody = updateProngFromInfo(existingBodies[i], prongInfo)
                if updatedBody is not None:
                    baseFeature.updateBody(existingBodies[i], updatedBody)
            else:
                
                newProng = createProngFromInfo(prongInfo)
                if newProng is not None:
                    newBody = component.bRepBodies.add(newProng, baseFeature)
                    if not _isRolledForEdit:
                        setProngAttributes(newBody)

        while baseFeature.bodies.count > len(prongInfos):
            baseFeature.bodies.item(baseFeature.bodies.count - 1).deleteMe()

        baseFeature.finishEdit()

        return True
    
    except:
        baseFeature.finishEdit()
        showMessage(f'UpdateFeature: {traceback.format_exc()}\n', True)
        return False
    

def rollBack():
    """Roll back the timeline to the state before editing."""
    global _restoreTimelineObject, _isRolledForEdit, _editedCustomFeature
    
    if _isRolledForEdit:
        _editedCustomFeature.timelineObject.rollTo(False)
        updateProngFeature(_editedCustomFeature)
        _restoreTimelineObject.rollTo(False)
        _isRolledForEdit = False

    _editedCustomFeature = None


def getSelectedGemstones() -> list[adsk.fusion.BRepBody]:
    """Get list of selected gemstone bodies from the selection input.
    
    Returns:
        List of selected BRepBody objects or empty list if fewer than 2 selected.
    """
    gemstones: list[adsk.fusion.BRepBody] = []
    for i in range(_gemstonesSelectionInput.selectionCount):
        gemstone = _gemstonesSelectionInput.selection(i).entity
        if gemstone is not None:
            gemstones.append(gemstone)
    return gemstones if len(gemstones) >= 2 else []