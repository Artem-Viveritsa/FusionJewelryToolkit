import os
import adsk.core, adsk.fusion, traceback

from ... import strings
from ... import constants
from ...helpers.showMessage import showMessage
from ...helpers.Bodies import placeBody
import math


_handlers = []

_app: adsk.core.Application = None
_ui: adsk.core.UserInterface = None

_customFeatureDefinition: adsk.fusion.CustomFeature = None

_editedCustomFeature: adsk.fusion.CustomFeature = None
_restoreTimelineObject: adsk.fusion.TimelineObject = None
_isRolledForEdit: bool = False

_gemstonesSelectionInput: adsk.core.SelectionCommandInput = None

_cutterBottomTypeInput: adsk.core.DropDownCommandInput = None
_heightValueInput: adsk.core.ValueCommandInput = None
_depthValueInput: adsk.core.ValueCommandInput = None
_sizeRatioValueInput: adsk.core.ValueCommandInput = None
_holeRatioValueInput: adsk.core.ValueCommandInput = None
_coneAngleValueInput: adsk.core.ValueCommandInput = None

RESOURCES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

COMMAND_ID = strings.PREFIX + strings.Cutter.cutterForGemstonesCommandId
CREATE_COMMAND_ID = COMMAND_ID + 'Create'
EDIT_COMMAND_ID = COMMAND_ID + 'Edit'

createCommandInputDef = strings.InputDef(CREATE_COMMAND_ID, 'Create Cutters for Gemstones', 'Creates cutters for selected gemstones.')
editCommandInputDef = strings.InputDef(EDIT_COMMAND_ID, 'Edit Cutters', 'Edits the parameters of existing cutters.')

selectGemstonesInputDef = strings.InputDef(
    strings.Cutter.selectGemstonesInputId,
    'Select Gemstones',
    'Select the gemstones to make cutters.'
    )

heightInputDef = strings.InputDef(
    strings.Cutter.heightValueInputId, 
    'Height', 
    "Cutter height above girdle.\nHow far the cutter protrudes upward from the gemstone girdle."
    )

depthInputDef = strings.InputDef(
    strings.Cutter.depthValueInputId, 
    'Depth', 
    "Cutter hole depth below girdle.\nHow deep the cutter cuts into the material beneath the girdle."
    )

sizeRatioInputDef = strings.InputDef(
    strings.Cutter.sizeRatioValueInputId, 
    'Size Ratio', 
    "Cutter size relative to gemstone.\nScale the cutter from 0.7 to 1.3 of gemstone diameter (1.0 = exact match)."
    )

holeRatioInputDef = strings.InputDef(
    strings.Cutter.holeRatioValueInputId, 
    'Hole Ratio', 
    "Hole size within cutter.\nRatio of hole diameter to cutter diameter, from 0.2 to 0.8 (0.5 = half diameter)."
    )

coneAngleInputDef = strings.InputDef(
    strings.Cutter.coneAngleValueInputId, 
    'Cone Angle', 
    "Cutter cone angle.\nSlope of the conical section, from 30° to 60° (41° default)."
    )

cutterBottomTypeInputDef = strings.InputDef(
    strings.Cutter.bottomTypeInputId,
    'Bottom Type',
    "Type of cutter bottom: Hole, Cone, or Hemisphere."
    )


def run(panel: adsk.core.ToolbarPanel):
    """Initialize the cutters command by setting up command definitions and UI elements."""
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

        _customFeatureDefinition = adsk.fusion.CustomFeatureDefinition.create(COMMAND_ID, strings.Cutter.cutterForGemstonesCommandId, RESOURCES_FOLDER)
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


def updateVisibility(selectedIndex: int) -> None:
    """Update visibility of inputs according to the selected bottom type index.

    This function expects an integer index (matching the enum member values).
    """
    global _depthValueInput, _holeRatioValueInput, _coneAngleValueInput

    _depthValueInput.isVisible = (selectedIndex == strings.CutterBottomType.Hole.value)
    _holeRatioValueInput.isVisible = (selectedIndex == strings.CutterBottomType.Hole.value)
    _coneAngleValueInput.isVisible = (selectedIndex in (strings.CutterBottomType.Hole.value, strings.CutterBottomType.Cone.value))


class CreateCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Event handler for creating the command dialog for new cutters for gemstones.
    
    This handler sets up all necessary input controls including selections for gemstones 
    and value inputs for height, depth, size ratio, hole ratio, and cone angle, and connects 
    event handlers for validation, preview, and execution.
    """
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _gemstonesSelectionInput, _depthValueInput, _heightValueInput, _sizeRatioValueInput, _holeRatioValueInput, _coneAngleValueInput, _cutterBottomTypeInput
            
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            command = eventArgs.command
            inputs = command.commandInputs
            defaultLengthUnits = _app.activeProduct.unitsManager.defaultLengthUnits

            _gemstonesSelectionInput = inputs.addSelectionInput(selectGemstonesInputDef.id, selectGemstonesInputDef.name, selectGemstonesInputDef.tooltip)
            _gemstonesSelectionInput.addSelectionFilter(adsk.core.SelectionCommandInput.Bodies)
            _gemstonesSelectionInput.tooltip = selectGemstonesInputDef.tooltip
            _gemstonesSelectionInput.setSelectionLimits(1)

            inputs.addSeparatorCommandInput('separatorAfterSelection')

            height = adsk.core.ValueInput.createByReal(0.04)
            _heightValueInput = inputs.addValueInput(heightInputDef.id, heightInputDef.name, defaultLengthUnits, height)
            _heightValueInput.tooltip = heightInputDef.tooltip

            sizeRatio = adsk.core.ValueInput.createByReal(1.0)
            _sizeRatioValueInput = inputs.addValueInput(sizeRatioInputDef.id, sizeRatioInputDef.name, '', sizeRatio)
            _sizeRatioValueInput.tooltip = sizeRatioInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterHeight')

            _cutterBottomTypeInput = inputs.addDropDownCommandInput(cutterBottomTypeInputDef.id, cutterBottomTypeInputDef.name, adsk.core.DropDownStyles.LabeledIconDropDownStyle)
            for i, typename in enumerate(strings.Cutter.bottomTypes):
                _cutterBottomTypeInput.listItems.add(typename, i == 0)
            _cutterBottomTypeInput.tooltip = cutterBottomTypeInputDef.tooltip

            depth = adsk.core.ValueInput.createByReal(0.15)
            _depthValueInput = inputs.addValueInput(depthInputDef.id, depthInputDef.name, defaultLengthUnits, depth)
            _depthValueInput.tooltip = depthInputDef.tooltip

            holeRatio = adsk.core.ValueInput.createByReal(0.5)
            _holeRatioValueInput = inputs.addValueInput(holeRatioInputDef.id, holeRatioInputDef.name, '', holeRatio)
            _holeRatioValueInput.tooltip = holeRatioInputDef.tooltip

            coneAngle = adsk.core.ValueInput.createByReal(41.0)
            _coneAngleValueInput = inputs.addValueInput(coneAngleInputDef.id, coneAngleInputDef.name, '', coneAngle)
            _coneAngleValueInput.tooltip = coneAngleInputDef.tooltip
            
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

        except:
            showMessage(f'CreateCommandCreatedHandler: {traceback.format_exc()}\n', True)


class EditCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Event handler for creating the command dialog for editing existing cutters.
    
    This handler retrieves the selected custom feature, populates inputs with existing parameter 
    values and dependencies, and connects event handlers for editing operations including 
    activation, validation, preview, and execution.
    """
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _editedCustomFeature, _gemstonesSelectionInput, _depthValueInput, _heightValueInput, _sizeRatioValueInput, _holeRatioValueInput, _coneAngleValueInput, _cutterBottomTypeInput
            
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
            _gemstonesSelectionInput.setSelectionLimits(1)

            parameters = _editedCustomFeature.parameters

            inputs.addSeparatorCommandInput('separatorAfterSelection')

            height = adsk.core.ValueInput.createByString(parameters.itemById(heightInputDef.id).expression)
            _heightValueInput = inputs.addValueInput(heightInputDef.id, heightInputDef.name, defaultLengthUnits, height)
            _heightValueInput.tooltip = heightInputDef.tooltip

            sizeRatio = adsk.core.ValueInput.createByString(parameters.itemById(sizeRatioInputDef.id).expression)
            _sizeRatioValueInput = inputs.addValueInput(sizeRatioInputDef.id, sizeRatioInputDef.name, '', sizeRatio)
            _sizeRatioValueInput.tooltip = sizeRatioInputDef.tooltip

            inputs.addSeparatorCommandInput('separatorAfterHeight')

            _cutterBottomTypeInput = inputs.addDropDownCommandInput(cutterBottomTypeInputDef.id, cutterBottomTypeInputDef.name, adsk.core.DropDownStyles.LabeledIconDropDownStyle)
            for typename in strings.Cutter.bottomTypes: _cutterBottomTypeInput.listItems.add(typename, False)
            _cutterBottomTypeInput.tooltip = cutterBottomTypeInputDef.tooltip

            try:
                selectedIndex = int(parameters.itemById(strings.Cutter.bottomTypeInputId).value)
            except (ValueError, TypeError):
                val = parameters.itemById(strings.Cutter.bottomTypeInputId).value
                val = parameters.itemById(strings.Cutter.bottomTypeInputId).value
                match = None
                for member in strings.CutterBottomType:
                    if member.name.lower() == str(val).lower():
                        match = member
                        break
                selectedIndex = match.value if match is not None else strings.CutterBottomType.Hole.value
            if 0 <= selectedIndex < _cutterBottomTypeInput.listItems.count:
                _cutterBottomTypeInput.listItems.item(selectedIndex).isSelected = True
            else:
                _cutterBottomTypeInput.listItems.item(0).isSelected = True

            depth = adsk.core.ValueInput.createByString(parameters.itemById(depthInputDef.id).expression)
            _depthValueInput = inputs.addValueInput(depthInputDef.id, depthInputDef.name, defaultLengthUnits, depth)
            _depthValueInput.tooltip = depthInputDef.tooltip

            holeRatio = adsk.core.ValueInput.createByString(parameters.itemById(holeRatioInputDef.id).expression)
            _holeRatioValueInput = inputs.addValueInput(holeRatioInputDef.id, holeRatioInputDef.name, '', holeRatio)
            _holeRatioValueInput.tooltip = holeRatioInputDef.tooltip

            coneAngle = adsk.core.ValueInput.createByString(parameters.itemById(coneAngleInputDef.id).expression)
            _coneAngleValueInput = inputs.addValueInput(coneAngleInputDef.id, coneAngleInputDef.name, '', coneAngle)
            _coneAngleValueInput.tooltip = coneAngleInputDef.tooltip

            currentSelectedIndex = _cutterBottomTypeInput.selectedItem.index
            updateVisibility(currentSelectedIndex)

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
    
    This handler checks to ensure the gemstones are valid bodies and not external references.
    """
    def __init__(self):
        """Initialize the PreSelectHandler."""
        super().__init__()
    def notify(self, args):
        """Handle the selection event to validate user selections.

        Args:
            args: The selection event arguments.
        """
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


class ValidateInputsHandler(adsk.core.ValidateInputsEventHandler):
    """Event handler for the validateInputs event."""
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

            
            if not all([_heightValueInput.isValidExpression, _sizeRatioValueInput.isValidExpression]):
                eventArgs.areInputsValid = False
                return

            if _depthValueInput.isVisible and not _depthValueInput.isValidExpression:
                eventArgs.areInputsValid = False
                return

            if _holeRatioValueInput.isVisible and not _holeRatioValueInput.isValidExpression:
                eventArgs.areInputsValid = False
                return

            if _coneAngleValueInput.isVisible and not _coneAngleValueInput.isValidExpression:
                eventArgs.areInputsValid = False
                return

            
            if _depthValueInput.isVisible and _depthValueInput.value < 0:
                eventArgs.areInputsValid = False
                return
            
            if _heightValueInput.value < 0.01:
                eventArgs.areInputsValid = False
                return

            if not (_sizeRatioValueInput.value >= 0.7 and _sizeRatioValueInput.value <= 1.3):
                eventArgs.areInputsValid = False
                return

            if _holeRatioValueInput.isVisible and not (_holeRatioValueInput.value >= 0.2 and _holeRatioValueInput.value <= 0.8):
                eventArgs.areInputsValid = False
                return

            if _coneAngleValueInput.isVisible and not (_coneAngleValueInput.value >= 30 and _coneAngleValueInput.value <= 60):
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

            if changedInput == _cutterBottomTypeInput:
                updateVisibility(_cutterBottomTypeInput.selectedItem.index)

        except:
            showMessage(f'InputChangedHandler: {traceback.format_exc()}\n', True)


class ExecutePreviewHandler(adsk.core.CommandEventHandler):
    """Event handler for the executePreview event."""
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
            cutterBottomTypeIndex = _cutterBottomTypeInput.selectedItem.index
            cutterBottomType = strings.CutterBottomType(cutterBottomTypeIndex)
            
            flippedStates = getFlipStatesForGemstones(gemstones)

            cutters = []
            for i, gemstone in enumerate(gemstones):
                cutter = createBody(gemstone, height, depth, sizeRatio, holeRatio, flippedStates[i], coneAngle, cutterBottomType)
                if cutter is None: continue
                cutters.append(cutter)

            if not cutters: return

            
            component = gemstones[0].parentComponent

            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()
            for i in range(len(cutters)):
                body = component.bRepBodies.add(cutters[i], baseFeature)
                handleNewBody(body)
            baseFeature.finishEdit()

        except:
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

            flippedStates = getFlipStatesForGemstones(gemstones)

            cutterBottomTypeIndex = _cutterBottomTypeInput.selectedItem.index
            cutterBottomType = strings.CutterBottomType(cutterBottomTypeIndex)
            
            component = gemstones[0].parentComponent
            baseFeature = component.features.baseFeatures.add()
            baseFeature.startEdit()
            for i, gemstone in enumerate(gemstones):
                cutter = createBody(gemstone, _heightValueInput.value, _depthValueInput.value, _sizeRatioValueInput.value, _holeRatioValueInput.value, flippedStates[i], _coneAngleValueInput.value, cutterBottomType)
                if cutter is None:
                    eventArgs.executeFailed = True
                    return
                body = component.bRepBodies.add(cutter, baseFeature)
                handleNewBody(body)
            baseFeature.finishEdit()

            design: adsk.fusion.Design = _app.activeProduct
            defaultLengthUnits = design.unitsManager.defaultLengthUnits
            
            customFeatureInput = component.features.customFeatures.createInput(_customFeatureDefinition)
            
            for i in range(len(gemstones)):
                gemstone = gemstones[i]
                
                if gemstone.faces.count == 0:
                    eventArgs.executeFailed = True
                    return
                firstGemstoneFace = gemstone.faces[0]
                customFeatureInput.addDependency(f'firstGemstoneFace{i}', firstGemstoneFace)

            
            height = adsk.core.ValueInput.createByString(_heightValueInput.expression)             
            customFeatureInput.addCustomParameter(heightInputDef.id, heightInputDef.name, height, defaultLengthUnits, True) 
            
            depth = adsk.core.ValueInput.createByString(_depthValueInput.expression)
            customFeatureInput.addCustomParameter(depthInputDef.id, depthInputDef.name, depth, defaultLengthUnits, True)
            
            sizeRatio = adsk.core.ValueInput.createByString(_sizeRatioValueInput.expression)
            customFeatureInput.addCustomParameter(sizeRatioInputDef.id, sizeRatioInputDef.name, sizeRatio, '', True)

            holeRatio = adsk.core.ValueInput.createByString(_holeRatioValueInput.expression)
            customFeatureInput.addCustomParameter(holeRatioInputDef.id, holeRatioInputDef.name, holeRatio, '', True)

            coneAngle = adsk.core.ValueInput.createByString(_coneAngleValueInput.expression)
            customFeatureInput.addCustomParameter(coneAngleInputDef.id, coneAngleInputDef.name, coneAngle, '', True)

            cutterBottomTypeIndex = adsk.core.ValueInput.createByReal(_cutterBottomTypeInput.selectedItem.index)
            customFeatureInput.addCustomParameter(cutterBottomTypeInputDef.id, cutterBottomTypeInputDef.name, cutterBottomTypeIndex, '', True)

            customFeatureInput.setStartAndEndFeatures(baseFeature, baseFeature)
            component.features.customFeatures.add(customFeatureInput)

        except:
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
        """Initialize the EditDestroyHandler."""
        super().__init__()
    def notify(self, args):
        """Handle the destroy event of the edit command.

        Args:
            args: The command event arguments.
        """
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

            
            _editedCustomFeature.parameters.itemById('height').expression = _heightValueInput.expression
            _editedCustomFeature.parameters.itemById('depth').expression = _depthValueInput.expression
            _editedCustomFeature.parameters.itemById('sizeRatio').expression = _sizeRatioValueInput.expression
            _editedCustomFeature.parameters.itemById('holeRatio').expression = _holeRatioValueInput.expression
            _editedCustomFeature.parameters.itemById('coneAngle').expression = _coneAngleValueInput.expression
            _editedCustomFeature.parameters.itemById(strings.Cutter.bottomTypeInputId).expression = str(_cutterBottomTypeInput.selectedItem.index)

            
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


def getFlipStatesForGemstones(gemstones: list[adsk.fusion.BRepBody]) -> list[bool]:
    """Get the flip states for a list of gemstone bodies.

    Args:
        gemstones: List of gemstone bodies.

    Returns:
        List of boolean values indicating if each gemstone is flipped.
    """
    flippedStates = []
    for gemstone in gemstones:
        isFlipped = False
        try:
            for feature in gemstone.parentComponent.features.customFeatures:
                if feature.name.startswith(strings.GEMSTONES_ON_FACE_AT_POINTS):
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


def createBody(body: adsk.fusion.BRepBody, height: float, depth: float, sizeRatio: float = 1.0, holeRatio: float = 0.5, isFlipped: bool = False, coneAngle: float = 42.0, cutterBottomType: strings.CutterBottomType = strings.CutterBottomType.Hole) -> adsk.fusion.BRepBody | None:
    """Create a cutter body based on a gemstone body.

    Args:
        body: The gemstone body to create a cutter for.
        height: The height of the cutter above the gemstone.
        depth: The depth of the cutter hole below the gemstone.
        sizeRatio: The ratio of cutter size to gemstone size.
        holeRatio: The ratio of hole diameter to cutter diameter.
        isFlipped: Whether the gemstone is flipped.
        coneAngle: The angle of the cutter cone.
        cutterBottomType: The type of cutter bottom (Hole, Cone, or Hemisphere).

    Returns:
        The created cutter body or None if creation failed.
    """
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
        
        if isFlipped:
            normal.scaleBy(-1)

        radius = cylinder.radius * sizeRatio
        holeRadius = radius * holeRatio

        bodies = []

        topPoint = adsk.core.Point3D.create(0, 0, height)
        bodies.append(temporaryBRep.createCylinderOrCone(constants.zeroPoint, radius, topPoint, radius))

        if cutterBottomType == strings.CutterBottomType.Hemisphere:
            hemisphere = temporaryBRep.createSphere(constants.zeroPoint, radius)
            clipTop = temporaryBRep.createCylinderOrCone(constants.zeroPoint, radius * 1.01, adsk.core.Point3D.create(0, 0, radius), radius * 1.01)
            temporaryBRep.booleanOperation(hemisphere, clipTop, adsk.fusion.BooleanTypes.DifferenceBooleanType)
            bodies.append(hemisphere)
        else:
            theta = math.radians(coneAngle)
            h = radius * math.tan(theta)
            bottomPoint = adsk.core.Point3D.create(0, 0, -h)
            bodies.append(temporaryBRep.createCylinderOrCone(constants.zeroPoint, radius, bottomPoint, 0))
        
            if cutterBottomType == strings.CutterBottomType.Hole:
                bottomPoint = adsk.core.Point3D.create(0, 0, min(-radius, -depth))
                bodies.append(temporaryBRep.createCylinderOrCone(constants.zeroPoint, holeRadius, bottomPoint, holeRadius))

        
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

        placeBody(cutter, girdleCentroid, lengthDirection, widthDirection, normal)

        return cutter
    
    except:
        showMessage(f'CreateBodies: {traceback.format_exc()}\n', True)
        return None
    

def updateFeature(customFeature: adsk.fusion.CustomFeature) -> bool:
    """Update the bodies of an existing custom cutters feature.

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

        
        gemstones: list[adsk.fusion.BRepBody] = [face.body for face in firstGemstoneFaces]

        height = customFeature.parameters.itemById('height').value
        depth = customFeature.parameters.itemById('depth').value
        sizeRatio = customFeature.parameters.itemById('sizeRatio').value
        holeRatio = customFeature.parameters.itemById('holeRatio').value
        coneAngle = customFeature.parameters.itemById('coneAngle').value
        try:
            cutterBottomTypeIndex = int(customFeature.parameters.itemById(strings.Cutter.bottomTypeInputId).value)
        except (ValueError, TypeError):
            val = customFeature.parameters.itemById(strings.Cutter.bottomTypeInputId).value
            match = None
            for member in strings.CutterBottomType:
                if member.name.lower() == str(val).lower():
                    match = member
                    break
            cutterBottomTypeIndex = match.value if match is not None else strings.CutterBottomType.Hole.value
        cutterBottomType = strings.CutterBottomType(cutterBottomTypeIndex)

        component = gemstones[0].parentComponent
        flippedStates = getFlipStatesForGemstones(gemstones)

        baseFeature.startEdit()
        
        
        for i in range(len(gemstones)):
            gemstone = gemstones[i]
            isFlipped = flippedStates[i]
            
            cutter = createBody(gemstone, height, depth, sizeRatio, holeRatio, isFlipped, coneAngle, cutterBottomType)
            if cutter is None:
                baseFeature.finishEdit()
                return False

            if i < baseFeature.bodies.count:
                currentBody = baseFeature.bodies.item(i)
                baseFeature.updateBody(currentBody, cutter)
                
            else:
                newBody = component.bRepBodies.add(cutter, baseFeature)
                handleNewBody(newBody)

        
        while baseFeature.bodies.count > len(gemstones):
            baseFeature.bodies.item(baseFeature.bodies.count - 1).deleteMe()

        baseFeature.finishEdit()

        return True
    
    except:
        showMessage(f'UpdateFeature: {traceback.format_exc()}\n', True)
        return False
    

def handleNewBody(body: adsk.fusion.BRepBody):
    """Handle the creation of a new cutter body by setting its name and attributes.

    Args:
        body: The new cutter body to handle.
    """
    body.name = strings.Cutter.name
    body.attributes.add(strings.PREFIX, strings.ENTITY, strings.Cutter.name)

def updateAttributes():
    """Update the attributes of all cutter bodies in the edited custom feature."""
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