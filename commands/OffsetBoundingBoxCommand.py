from dataclasses import dataclass

import adsk.core
import adsk.fusion
from ..apper import apper
from .. import config


def middle(min_p_value, max_p_value):
    return min_p_value + ((max_p_value - min_p_value) / 2)


def mid_point(p1: adsk.core.Point3D, p2: adsk.core.Point3D):
    return adsk.core.Point3D.create(
        middle(p1.x, p2.x),
        middle(p1.y, p2.y),
        middle(p1.z, p2.z)
    )


def get_default_offset():
    ao = apper.AppObjects()
    units = ao.units_manager.defaultLengthUnits
    try:
        default_offset = config.DEFAULT_OFFSET
    except AttributeError:
        default_offset = f"1 {units}"

    default_value = ao.units_manager.evaluateExpression(default_offset)
    return default_value


class Direction:
    def __init__(self, name: str, direction: adsk.core.Vector3D, inputs: adsk.core.CommandInputs, default_value: float):
        self.name = name
        self.direction = direction
        self.origin = adsk.core.Point3D.create(0, 0, 0)

        default_value_input = adsk.core.ValueInput.createByReal(default_value)
        self.dist_input: adsk.core.DistanceValueCommandInput = inputs.addDistanceValueCommandInput(
            f"dist_{self.name}", self.name, default_value_input
        )
        self.dist_input.isEnabled = False
        self.dist_input.isVisible = False
        self.dist_input.minimumValue = 0.0
        self.dist_input.isMinimumValueInclusive = True

    def update_manipulator(self, new_origin):
        self.origin = new_origin
        self.dist_input.setManipulator(self.origin, self.direction)
        self.dist_input.isEnabled = True
        self.dist_input.isVisible = True


class TheBox:

    def __init__(self, b_box: adsk.core.BoundingBox3D, inputs: adsk.core.CommandInputs,
                 custom_feature: adsk.fusion.CustomFeature = None):
        ao = apper.AppObjects()
        root_comp = ao.root_comp
        self.b_box = b_box
        self.modified_b_box = self.b_box.copy()

        self.x_pos_vector = root_comp.yZConstructionPlane.geometry.normal.copy()
        self.x_neg_vector = root_comp.yZConstructionPlane.geometry.normal.copy()
        self.x_neg_vector.scaleBy(-1)
        self.y_pos_vector = root_comp.xZConstructionPlane.geometry.normal.copy()
        self.y_neg_vector = root_comp.xZConstructionPlane.geometry.normal.copy()
        self.y_neg_vector.scaleBy(-1)
        self.z_pos_vector = root_comp.xYConstructionPlane.geometry.normal.copy()
        self.z_neg_vector = root_comp.xYConstructionPlane.geometry.normal.copy()
        self.z_neg_vector.scaleBy(-1)

        if custom_feature is None:
            d_o = get_default_offset()
            feature_values = FeatureValues(0.0, d_o, d_o, d_o, d_o, d_o, d_o)

        else:
            feature_values = get_feature_values(custom_feature)

        self.directions = {
            "x_pos": Direction("X Positive", self.x_pos_vector, inputs, feature_values.x_pos),
            "x_neg": Direction("X Negative", self.x_neg_vector, inputs, feature_values.x_neg),
            "y_pos": Direction("Y Positive", self.y_pos_vector, inputs, feature_values.y_pos),
            "y_neg": Direction("Y Negative", self.y_neg_vector, inputs, feature_values.y_neg),
            "z_pos": Direction("Z Positive", self.z_pos_vector, inputs, feature_values.z_pos),
            "z_neg": Direction("Z Negative", self.z_neg_vector, inputs, feature_values.z_neg)
        }

        self.graphics_group = ao.root_comp.customGraphicsGroups.add()
        self.brep_mgr = adsk.fusion.TemporaryBRepManager.get()
        self.brep_box = None
        self.graphics_box = None
        self.selections = []

    def initialize_box(self, b_box):
        self.modified_b_box = b_box.copy()

    def update_box(self, point: adsk.core.Point3D):
        self.modified_b_box.expand(point)

    def update_manipulators(self):
        min_p = self.modified_b_box.minPoint
        max_p = self.modified_b_box.maxPoint

        self.directions["x_pos"].update_manipulator(adsk.core.Point3D.create(
            max_p.x, middle(min_p.y, max_p.y), middle(min_p.z, max_p.z))
        )
        self.directions["x_neg"].update_manipulator(adsk.core.Point3D.create(
            min_p.x, middle(min_p.y, max_p.y), middle(min_p.z, max_p.z))
        )
        self.directions["y_pos"].update_manipulator(adsk.core.Point3D.create(
            middle(min_p.x, max_p.x), max_p.y, middle(min_p.z, max_p.z))
        )
        self.directions["y_neg"].update_manipulator(adsk.core.Point3D.create(
            middle(min_p.x, max_p.x), min_p.y, middle(min_p.z, max_p.z))
        )
        self.directions["z_pos"].update_manipulator(adsk.core.Point3D.create(
            middle(min_p.x, max_p.x), middle(min_p.y, max_p.y), max_p.z)
        )
        self.directions["z_neg"].update_manipulator(adsk.core.Point3D.create(
            middle(min_p.x, max_p.x), middle(min_p.y, max_p.y), min_p.z)
        )

    def box_center(self):
        return mid_point(self.modified_b_box.minPoint, self.modified_b_box.maxPoint)

    def update_graphics(self):
        self.clear_graphics()
        self.update_brep_box()

        color = adsk.core.Color.create(10, 200, 50, 125)
        color_effect = adsk.fusion.CustomGraphicsSolidColorEffect.create(color)
        self.graphics_box = self.graphics_group.addBRepBody(self.brep_box)
        self.graphics_box.color = color_effect

    def clear_graphics(self):
        if self.graphics_box is not None:
            if self.graphics_box.isValid:
                self.graphics_box.deleteMe()

    def update_brep_box(self):
        o_box = oriented_b_box_from_b_box(self.modified_b_box)
        self.brep_box = self.brep_mgr.createBox(o_box)

    # TODO Different on edit
    def create_brep(self, thickness):
        ao = apper.AppObjects()
        self.update_brep_box()

        new_occ: adsk.fusion.Occurrence = ao.root_comp.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        new_comp = new_occ.component
        new_comp.name = "Bounding Box"
        new_comp.opacity = .5


        if ao.design.designType == adsk.fusion.DesignTypes.ParametricDesignType:

            base_feature = new_comp.features.baseFeatures.add()
            base_feature.startEdit()

            new_body = new_comp.bRepBodies.add(self.brep_box, base_feature)
            shell_input = create_shell_input(new_body, thickness)
            # shell_input.targetBaseFeature = base_feature
            # new_comp.features.shellFeatures.add(shell_input)

            base_feature.finishEdit()

            shell_input = create_shell_input(new_body, thickness)
            shell_feature = new_comp.features.shellFeatures.add(shell_input)

            custom_features = new_comp.features.customFeatures
            inputs = custom_features.createInput(config.custom_feature_definition, base_feature, shell_feature)

            for i, selection in enumerate(self.selections):
                inputs.addDependency('body_' + str(i), selection)

            inputs.addCustomParameter('shell_thickness', 'Shell Thickness',
                                      adsk.core.ValueInput.createByReal(thickness), 'cm', True)

            direction: Direction
            for key, direction in self.directions.items():
                inputs.addCustomParameter(
                    key,
                    direction.name,
                    adsk.core.ValueInput.createByString(direction.dist_input.expression),
                    'cm',
                    True
                )

            feature = custom_features.add(inputs)

        else:
            new_body = new_comp.bRepBodies.add(self.brep_box)
            shell_input = create_shell_input(new_body, thickness)
            new_comp.features.shellFeatures.add(shell_input)

    def edit_brep(self, thickness, custom_feature: adsk.fusion.CustomFeature):
        ao = apper.AppObjects()
        self.update_brep_box()
        
        base_feature = _getBaseFeature(custom_feature)
        update_base_feature_body(base_feature, self.brep_box)
        
        direction: Direction
        for key, direction in self.directions.items():
            parameter = custom_feature.parameters.itemById(key)
            parameter.expression = direction.dist_input.expression
        parameter = custom_feature.parameters.itemById('shell_thickness')
        parameter.value = thickness

        reset_feature_dependencies(custom_feature, self.selections)


def update_base_feature_body(base: adsk.fusion.BaseFeature, tool: adsk.fusion.BRepBody):
    base.startEdit()
    source_body = base.bodies[0]
    base.updateBody(source_body, tool)
    base.finishEdit()


def reset_feature_dependencies(feature: adsk.fusion.CustomFeature, bodies: list):
    ao = apper.AppObjects()
    dependency: adsk.fusion.CustomFeatureDependency
    for dependency in feature.dependencies:
        dependency.deleteMe()

    body: adsk.fusion.BRepBody
    for i, body in enumerate(bodies):
        feature.dependencies.add('body_' + str(i), body)


def create_shell_input(body: adsk.fusion.BRepBody, thickness: float) -> adsk.fusion.ShellFeatureInput:
    obj_col = adsk.core.ObjectCollection.create()
    obj_col.add(body)

    shell_input = body.parentComponent.features.shellFeatures.createInput(obj_col)
    thickness_input = adsk.core.ValueInput.createByReal(thickness)
    shell_input.outsideThickness = thickness_input
    return shell_input


def oriented_b_box_from_b_box(b_box: adsk.core.BoundingBox3D) -> adsk.core.OrientedBoundingBox3D:
    ao = apper.AppObjects()
    o_box = adsk.core.OrientedBoundingBox3D.create(
        mid_point(b_box.minPoint, b_box.maxPoint),
        ao.root_comp.yZConstructionPlane.geometry.normal.copy(),
        ao.root_comp.xZConstructionPlane.geometry.normal.copy(),
        b_box.maxPoint.x - b_box.minPoint.x,
        b_box.maxPoint.y - b_box.minPoint.y,
        b_box.maxPoint.z - b_box.minPoint.z
    )
    return o_box


class OffsetBoundingBoxCommand(apper.Fusion360CommandBase):
    def __init__(self, name: str, options: dict):
        self.the_box: TheBox
        self.the_box = None
        self.create_feature = options.get('create_feature', True)
        self.editing_feature = None
        super().__init__(name, options)

    def on_preview(self, command, inputs, args, input_values):
        ao = apper.AppObjects()
        ao.print_msg(f'Preview Event - editing_feature = {self.editing_feature}')
        selections = input_values['body_select']
        if len(selections) > 0:
            new_box = bounding_box_from_selections(selections)
            self.the_box.initialize_box(new_box)
            self.the_box.update_manipulators()

            direction: Direction
            for key, direction in self.the_box.directions.items():
                point = direction.dist_input.manipulatorOrigin.copy()
                vector = direction.direction.copy()
                vector.normalize()
                vector.scaleBy(direction.dist_input.value)
                point.translateBy(vector)

                if not self.the_box.modified_b_box.contains(point):
                    self.the_box.update_box(point)

            self.the_box.update_graphics()

    def on_input_changed(self, command, inputs, changed_input, input_values):
        ao = apper.AppObjects()
        ao.print_msg(f'Input Changed Event - editing_feature = {self.editing_feature}')

        if changed_input.id == 'body_select':
            selections = input_values['body_select']

            if len(selections) > 0:
                self.the_box.selections = selections

                new_box = bounding_box_from_selections(selections)

                self.the_box.initialize_box(new_box)
                self.the_box.update_manipulators()

    def on_execute(self, command, inputs, args, input_values):
        ao = apper.AppObjects()
        ao.print_msg(f'Execute Event - editing_feature = {self.editing_feature}')
        self.the_box.clear_graphics()
        if self.create_feature:
            self.the_box.create_brep(input_values['thick_input'])
        else:
            self.the_box.edit_brep(input_values['thick_input'], self.editing_feature)

    def on_destroy(self, command, inputs, reason, input_values):
        ao = apper.AppObjects()
        ao.print_msg(f'Destroy Event - editing_feature = {self.editing_feature}')
        self.the_box.clear_graphics()

    def on_create(self, command, inputs):
        ao = apper.AppObjects()
        ao.print_msg(f'Create Event - editing_feature = {self.editing_feature}')
        units = ao.units_manager.defaultLengthUnits

        selection_input = inputs.addSelectionInput('body_select', "Select Bodies",
                                                   "Select the bodies to create a bounding Box")
        selection_input.addSelectionFilter('Bodies')
        selection_input.setSelectionLimits(1, 0)

        # TODO Handle preselected bodies
        default_selections = []

        if self.create_feature:
            self.editing_feature = None
            default_thickness = get_default_thickness(units)

        else:
            self.editing_feature = get_editing_feature()
            feature_values = get_feature_values(self.editing_feature)
            default_thickness = feature_values.shell_thickness

        default_thickness_vi = adsk.core.ValueInput.createByReal(default_thickness)
        inputs.addValueInput('thick_input', "Outer Shell Thickness", units, default_thickness_vi)

        # Get initialized bounding box
        b_box = bounding_box_from_selections(default_selections)

        # Create main box class
        self.the_box = TheBox(b_box, inputs, self.editing_feature)

    def on_activate(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs, args, input_values):
        ao = apper.AppObjects()
        ao.print_msg(f'Activate Event - editing_feature = {self.editing_feature}')

        if not self.create_feature:
            selection_input = inputs.itemById('body_select')

            default_selections = get_selections_from_feature(self.editing_feature)
            for entity in default_selections:
                selection_input.addSelection(entity)


def get_editing_feature() -> adsk.fusion.CustomFeature:
    ao = apper.AppObjects()
    active_selections = ao.ui.activeSelections
    editing_feature = active_selections.count and adsk.fusion.CustomFeature.cast(active_selections[0].entity)
    active_selections.clear()
    return editing_feature


def get_default_thickness(units):
    ao = apper.AppObjects()
    try:
        default_shell = config.DEFAULT_SHELL
    except AttributeError:
        default_shell = f"1 {units}"
    default_value = ao.units_manager.evaluateExpression(default_shell)
    return default_value


def bounding_box_from_selections(selections):
    if len(selections) > 0:
        b_box: adsk.core.BoundingBox3D = selections[0].boundingBox
        for selection in selections[1:]:
            b_box.combine(selection.boundingBox)

    else:
        b_box = adsk.core.BoundingBox3D.create(
            adsk.core.Point3D.create(-1, -1, -1),
            adsk.core.Point3D.create(1, 1, 1)
        )
    return b_box


def _getBaseFeature(feature: adsk.fusion.CustomFeature) -> adsk.fusion.BaseFeature:
    return feature.features[0]


def _getShellFeature(feature: adsk.fusion.CustomFeature) -> adsk.fusion.ShellFeature:
    return feature.features[1]


def get_selections_from_feature(feature: adsk.fusion.CustomFeature) -> list:
    selections = []
    for dependency in feature.dependencies:
        selections.append(dependency.entity)
    return selections


@dataclass
class FeatureValues:
    shell_thickness: float
    x_pos: float
    x_neg: float
    y_pos: float
    y_neg: float
    z_pos: float
    z_neg: float


def expand_box_by_feature_values(b_box: adsk.core.BoundingBox3D, f_values: FeatureValues):
    min_p = b_box.minPoint
    max_p = b_box.maxPoint

    points = [
        adsk.core.Point3D.create(max_p.x + f_values.x_pos, middle(min_p.y, max_p.y), middle(min_p.z, max_p.z)),
        adsk.core.Point3D.create(min_p.x - f_values.x_neg, middle(min_p.y, max_p.y), middle(min_p.z, max_p.z)),
        adsk.core.Point3D.create(middle(min_p.x, max_p.x), max_p.y + f_values.y_pos, middle(min_p.z, max_p.z)),
        adsk.core.Point3D.create(middle(min_p.x, max_p.x), min_p.y - f_values.y_neg, middle(min_p.z, max_p.z)),
        adsk.core.Point3D.create(middle(min_p.x, max_p.x), middle(min_p.y, max_p.y), max_p.z + f_values.z_pos),
        adsk.core.Point3D.create(middle(min_p.x, max_p.x), middle(min_p.y, max_p.y), min_p.z - f_values.z_neg)
    ]

    for point in points:
        if not b_box.contains(point):
            b_box.expand(point)


def get_feature_values(feature: adsk.fusion.CustomFeature) -> FeatureValues:
    params = feature.parameters

    return FeatureValues(
        params.itemById('shell_thickness').value,
        params.itemById('x_pos').value,
        params.itemById('x_neg').value,
        params.itemById('y_pos').value,
        params.itemById('y_neg').value,
        params.itemById('z_pos').value,
        params.itemById('z_neg').value,
    )


class BoxCustomFeature(apper.Fusion360CustomFeatureBase):
    def __init__(self, name: str, options: dict):
        super().__init__(name, options)
        config.custom_feature_definition = self.definition

    def on_compute(self, args: adsk.fusion.CustomFeatureEventArgs):
        ao = apper.AppObjects()
        # ao.ui.messageBox("Computing")

        # Make the box
        selections = get_selections_from_feature(args.customFeature)
        feature_values = get_feature_values(args.customFeature)

        b_box = bounding_box_from_selections(selections)
        expand_box_by_feature_values(b_box, feature_values)
        o_box = oriented_b_box_from_b_box(b_box)

        # TODO Only if necessary
        brep_mgr = adsk.fusion.TemporaryBRepManager.get()
        brep_box = brep_mgr.createBox(o_box)

        # Update base feature
        base = _getBaseFeature(args.customFeature)
        base.startEdit()
        sourceBody = base.bodies[0]
        base.updateBody(sourceBody, brep_box)
        base.finishEdit()

        # TODO Update shell feature
        # shell = _getShellFeature(args.customFeature)

        # shell.setThicknesses(
        #     adsk.core.ValueInput.createByReal(0.0),
        #     adsk.core.ValueInput.createByReal(feature_values.shell_thickness)
        # )
