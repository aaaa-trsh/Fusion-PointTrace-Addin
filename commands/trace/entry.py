import adsk.core
import os, math, traceback, glob, secrets
from ...lib import fusion360utils as futil
from ... import config
app = adsk.core.Application.get()
ui = app.userInterface

# Command Configs
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_trace'
CMD_NAME = 'Trace'
CMD_DESC = 'Traces a point in a joint linkage.'
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Placement Configs
WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidCreatePanel'
COMMAND_BESIDE_ID = ''
IS_PROMOTED = True


# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []

def start():
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_DESC, ICON_FOLDER)

    # Button click handler
    futil.add_handler(cmd_def.commandCreated, command_created)

    # Add the command button
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)
    control.isPromoted = IS_PROMOTED


def stop():
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    command_control = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    # Delete the button command control
    if command_control:
        command_control.deleteMe()

    # Delete the command definition
    if command_definition:
        command_definition.deleteMe()


def command_created(args: adsk.core.CommandCreatedEventArgs):
    # General logging for debug.
    try:
        futil.log(f'{CMD_NAME} Command Created Event')

        # https://help.autodesk.com/view/fusion360/ENU/?contextId=CommandInputs
        inputs = args.command.commandInputs

        # Create a joint selection input.
        jointSelectInput = inputs.addSelectionInput('joint_input', 'Joint', 'Select a joint')
        jointSelectInput.addSelectionFilter("Joints")
        jointSelectInput.setSelectionLimits(1, 1)

        # Create a selection input for the profile to trace against.
        profileSelectInput = inputs.addSelectionInput('profile_input', 'Profile', 'Select a profile')
        profileSelectInput.addSelectionFilter("PlanarFaces")
        profileSelectInput.addSelectionFilter("Profiles")
        profileSelectInput.addSelectionFilter("ConstructionPlanes")
        profileSelectInput.setSelectionLimits(1, 1)

        # Create a point selection input.
        pointSelectInput = inputs.addSelectionInput('point_input', 'Point', 'Select a point')
        pointSelectInput.addSelectionFilter("Vertices")
        pointSelectInput.addSelectionFilter("ConstructionPoints")
        pointSelectInput.addSelectionFilter("SketchPoints")
        pointSelectInput.setSelectionLimits(1, 0)

        # TODO Connect to the events that are needed by this command.
        futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
        futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
        futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
        futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)
    except:
        logFile = os.path.join(os.path.dirname(__file__), 'trace.log')
        with open(logFile, 'w') as f:
            f.write(traceback.format_exc())
        ui.messageBox(traceback.format_exc())

def command_execute(args: adsk.core.CommandEventArgs):
    try:
        design = app.activeProduct
        rootComp = design.rootComponent

        # General logging for debug.
        futil.log(f'{CMD_NAME} Command Execute Event')

        inputs = args.command.commandInputs

        jointInput = inputs.itemById('joint_input')
        pointInput = inputs.itemById('point_input')
        profileInput = inputs.itemById('profile_input')
        
        # Input validation
        if jointInput.selectionCount == 0 or pointInput.selectionCount == 0 or profileInput.selectionCount == 0:
            ui.messageBox('Please select a joint, face, and point to trace.')
            return

        pointCount = pointInput.selectionCount
        selectedPoints = [pointInput.selection(i) for i in range(pointCount)]

        joint = jointInput.selection(0).entity
        profile = profileInput.selection(0).entity

        sketches = rootComp.sketches
        sketch = sketches.add(profile)
        sketchTransformInv = sketch.transform
        sketchTransformInv.invert()
        
        jointLimits = joint.jointMotion.rotationLimits
        minValue = jointLimits.minimumValue if jointLimits.isMinimumValueEnabled else 0
        maxValue = jointLimits.maximumValue if jointLimits.isMaximumValueEnabled else math.pi * 2

        originalValue = joint.jointMotion.rotationValue
        pointCollection = []

        for _ in range(pointCount):
            pointCollection.append(adsk.core.ObjectCollection.create())

        resolution = 100
        for _ in range(resolution):
            joint.jointMotion.rotationValue = minValue + (math.pi * 2 / resolution) * _
            app.activeViewport.refresh()

            for idx in range(pointCount):
                point = selectedPoints[idx].entity
                sketchSpacePoint = point.geometry

                if sketchSpacePoint.objectType == adsk.fusion.SketchPoint.classType():
                    sketchSpacePoint.transformBy(sketchPoint.parentSketch.transform)

                sketchSpacePoint.transformBy(sketchTransformInv)

                pointCollection[idx].add(sketchSpacePoint)

        joint.jointMotion.rotationValue = originalValue
        app.activeViewport.refresh()

        for idx in range(pointCount):
            pointCollection[idx].add(pointCollection[idx].item(0))

            spline = sketch.sketchCurves.sketchFittedSplines.add(pointCollection[idx])
            spline.isFixed = True

        app.activeViewport.refresh()
    except:
        logFile = os.path.join(os.path.dirname(__file__), 'trace.log')
        with open(logFile, 'w') as f:
            f.write(traceback.format_exc())
        ui.messageBox(traceback.format_exc())


def command_preview(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Preview Event')
    inputs = args.command.commandInputs


def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs

    # General logging for debug.
    futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}')    

    if changed_input.id == 'joint_input':
        # set focus to point input
        pointInput = inputs.itemById('profile_input')
        pointInput.hasFocus = True
    elif changed_input.id == 'profile_input':
        # set focus to profile input
        profileInput = inputs.itemById('point_input')
        profileInput.hasFocus = True

# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Destroy Event')

    global local_handlers
    local_handlers = []
