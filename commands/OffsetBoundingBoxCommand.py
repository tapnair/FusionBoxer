from dataclasses import dataclass
import math
from typing import List

import adsk.core
import adsk.fusion
from ..apper import apper
from .. import config


# region Custom Feature Utilities
@dataclass
class FeatureValues:
    shell_thickness: float
    bar: float
    gap: float
    x_pos: float
    x_neg: float
    y_pos: float
    y_neg: float
    z_pos: float
    z_neg: float


def get_feature_values(feature: adsk.fusion.CustomFeature) -> FeatureValues:
    params = feature.parameters

    return FeatureValues(
        params.itemById('shell_thickness').value,
        params.itemById('bar').value,
        params.itemById('gap').value,
        params.itemById('x_pos').value,
        params.itemById('x_neg').value,
        params.itemById('y_pos').value,
        params.itemById('y_neg').value,
        params.itemById('z_pos').value,
        params.itemById('z_neg').value,
    )


def get_feature_bodies(feature: adsk.fusion.CustomFeature) -> list:
    selections = []
    for dependency in feature.dependencies:
        selections.append(dependency.entity)
    return selections


def get_editing_feature() -> adsk.fusion.CustomFeature:
    ao = apper.AppObjects()
    active_selections = ao.ui.activeSelections
    editing_feature = active_selections.count and adsk.fusion.CustomFeature.cast(active_selections[0].entity)
    active_selections.clear()
    return editing_feature


def get_shell_feature(feature: adsk.fusion.CustomFeature) -> adsk.fusion.ShellFeature:
    return feature.features[1]


def get_base_feature(feature: adsk.fusion.CustomFeature) -> adsk.fusion.BaseFeature:
    return feature.features[0]


def update_base_feature_body(base: adsk.fusion.BaseFeature, tool: adsk.fusion.BRepBody):
    base.startEdit()
    source_body = base.bodies[0]
    base.updateBody(source_body, tool)
    base.finishEdit()


def update_feature_dependencies(feature: adsk.fusion.CustomFeature, bodies: list):
    dependency: adsk.fusion.CustomFeatureDependency
    for dependency in feature.dependencies:
        dependency.deleteMe()

    body: adsk.fusion.BRepBody
    for i, body in enumerate(bodies):
        feature.dependencies.add('body_' + str(i), body)


# endregion


# region Geometry Utilities
def middle(min_p_value: float, max_p_value: float) -> float:
    return min_p_value + ((max_p_value - min_p_value) / 2)


def mid_point(p1: adsk.core.Point3D, p2: adsk.core.Point3D) -> adsk.core.Point3D:
    return adsk.core.Point3D.create(
        middle(p1.x, p2.x),
        middle(p1.y, p2.y),
        middle(p1.z, p2.z)
    )


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


def create_outer_box(inner_o_box: adsk.core.OrientedBoundingBox3D, thickness: float) -> adsk.core.OrientedBoundingBox3D:
    outer_o_box = inner_o_box.copy()

    outer_o_box.length = outer_o_box.length + thickness * 2
    outer_o_box.width = outer_o_box.width + thickness * 2
    outer_o_box.height = outer_o_box.height + thickness * 2

    return outer_o_box


def create_brep_shell_box(modified_b_box, thickness):
    brep_mgr = adsk.fusion.TemporaryBRepManager.get()
    inner_o_box = oriented_b_box_from_b_box(modified_b_box)

    outer_o_box = create_outer_box(inner_o_box, thickness)

    inner_box = brep_mgr.createBox(inner_o_box)
    outer_box = brep_mgr.createBox(outer_o_box)

    brep_mgr.booleanOperation(outer_box, inner_box, adsk.fusion.BooleanTypes.DifferenceBooleanType)

    return outer_box


def create_shell_input(body: adsk.fusion.BRepBody, thickness: float) -> adsk.fusion.ShellFeatureInput:
    obj_col = adsk.core.ObjectCollection.create()
    obj_col.add(body)

    shell_input = body.parentComponent.features.shellFeatures.createInput(obj_col)
    thickness_input = adsk.core.ValueInput.createByReal(thickness)
    shell_input.outsideThickness = thickness_input
    return shell_input


def create_gaps(b_box: adsk.core.BoundingBox3D, feature_values: FeatureValues) -> List[adsk.fusion.BRepBody]:
    gap = feature_values.gap
    bar = feature_values.bar
    thk = feature_values.shell_thickness

    o_box = oriented_b_box_from_b_box(b_box)
    create_o_box = adsk.core.OrientedBoundingBox3D.create
    create_point = adsk.core.Point3D.create

    if (o_box.length - bar - gap - thk * 2) > 0:
        x_num = int(math.floor((o_box.length + bar) / (gap + bar)))
        x_step = (o_box.length - (gap * x_num) - (bar * (x_num - 1))) / 2
    else:
        x_num = 0
        x_step = 0

    if (o_box.width - bar - gap - thk * 2) > 0:
        y_num = int(math.floor((o_box.width + bar) / (gap + bar)))
        y_step = (o_box.width - (gap * y_num) - (bar * (y_num - 1))) / 2
    else:
        y_num = 0
        y_step = 0

    if (o_box.height - bar - gap - thk * 2) > 0:
        z_num = int(math.floor((o_box.height + bar) / (gap + bar)))
        z_step = (o_box.height - (gap * z_num) - (bar * (z_num - 1))) / 2
    else:
        z_num = 0
        z_step = 0

    x_min = b_box.minPoint.x + x_step + gap / 2
    y_min = b_box.minPoint.y + y_step + gap / 2
    z_min = b_box.minPoint.z + z_step + gap / 2

    gaps = []
    brep_mgr = adsk.fusion.TemporaryBRepManager.get()

    for z in range(z_num):
        for y in range(y_num):
            cp_x = create_point(
                o_box.centerPoint.x - (o_box.length + thk) / 2, y_min + y * (bar + gap), z_min + z * (bar + gap))
            x_box = create_o_box(cp_x, o_box.lengthDirection, o_box.widthDirection, thk, gap, gap)
            gaps.append(brep_mgr.createBox(x_box))

            cp_x = create_point(
                o_box.centerPoint.x + (o_box.length + thk) / 2, y_min + y * (bar + gap), z_min + z * (bar + gap))
            x_box = create_o_box(cp_x, o_box.lengthDirection, o_box.widthDirection, thk, gap, gap)
            # x_box = create_o_box(cp_x, o_box.lengthDirection, o_box.widthDirection, o_box.length + thk * 2, gap, gap)
            gaps.append(brep_mgr.createBox(x_box))

    for z in range(z_num):
        for x in range(x_num):
            cp_y = create_point(
                x_min + x * (bar + gap), o_box.centerPoint.y - (o_box.width + thk) / 2, z_min + z * (bar + gap))
            y_box = create_o_box(cp_y, o_box.widthDirection, o_box.lengthDirection, thk, gap, gap)
            gaps.append(brep_mgr.createBox(y_box))

            cp_y = create_point(
                x_min + x * (bar + gap), o_box.centerPoint.y + (o_box.width + thk) / 2, z_min + z * (bar + gap))
            y_box = create_o_box(cp_y, o_box.widthDirection, o_box.lengthDirection, thk, gap, gap)
            gaps.append(brep_mgr.createBox(y_box))

    for y in range(y_num):
        for x in range(x_num):
            cp_z = create_point(
                x_min + x * (bar + gap), y_min + y * (bar + gap), o_box.centerPoint.z - (o_box.height + thk) / 2)
            z_box = create_o_box(cp_z, o_box.heightDirection, o_box.widthDirection, thk, gap, gap)
            gaps.append(brep_mgr.createBox(z_box))

            cp_z = create_point(
                x_min + x * (bar + gap), y_min + y * (bar + gap), o_box.centerPoint.z + (o_box.height + thk) / 2)
            z_box = create_o_box(cp_z, o_box.heightDirection, o_box.widthDirection, thk, gap, gap)
            gaps.append(brep_mgr.createBox(z_box))

    return gaps


# endregion


# region Get Config Defaults
def get_default_offset():
    ao = apper.AppObjects()
    units = ao.units_manager.defaultLengthUnits
    try:
        default_offset = config.DEFAULT_OFFSET
    except AttributeError:
        default_offset = f"1 {units}"

    default_value = ao.units_manager.evaluateExpression(default_offset)
    return default_value


def get_default_thickness(units):
    ao = apper.AppObjects()
    try:
        default_shell = config.DEFAULT_SHELL
    except AttributeError:
        default_shell = f"1 {units}"
    default_value = ao.units_manager.evaluateExpression(default_shell)
    return default_value


# endregion


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

        self.inputs = inputs
        self.thickness_input = inputs.itemById('thick_input')
        self.gap_input = inputs.itemById('gap')
        self.bar_input = inputs.itemById('bar')

        if custom_feature is None:
            d_o = get_default_offset()
            self.feature_values = FeatureValues(
                self.thickness_input.value, self.bar_input.value, self.gap_input.value, *([d_o] * 6))

        else:
            self.feature_values = get_feature_values(custom_feature)

        self.directions = {
            "x_pos": Direction("X Positive", self.x_pos_vector, inputs, self.feature_values.x_pos),
            "x_neg": Direction("X Negative", self.x_neg_vector, inputs, self.feature_values.x_neg),
            "y_pos": Direction("Y Positive", self.y_pos_vector, inputs, self.feature_values.y_pos),
            "y_neg": Direction("Y Negative", self.y_neg_vector, inputs, self.feature_values.y_neg),
            "z_pos": Direction("Z Positive", self.z_pos_vector, inputs, self.feature_values.z_pos),
            "z_neg": Direction("Z Negative", self.z_neg_vector, inputs, self.feature_values.z_neg)
        }

        self.graphics_group = ao.root_comp.customGraphicsGroups.add()
        self.brep_mgr = adsk.fusion.TemporaryBRepManager.get()
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

        shell_box = create_brep_shell_box(self.modified_b_box, self.thickness_input.value)

        color = adsk.core.Color.create(10, 200, 50, 125)
        color_effect = adsk.fusion.CustomGraphicsSolidColorEffect.create(color)
        self.graphics_box = self.graphics_group.addBRepBody(shell_box)
        self.graphics_box.color = color_effect

    def update_graphics_full(self):
        self.clear_graphics()

        shell_box = create_brep_shell_box(self.modified_b_box, self.thickness_input.value)
        gaps = create_gaps(self.modified_b_box, self.feature_values)

        g_color = adsk.core.Color.create(0, 0, 0, 0)
        g_color_effect = adsk.fusion.CustomGraphicsSolidColorEffect.create(g_color)
        for gap in gaps:
            g_graphic = self.graphics_group.addBRepBody(gap)
            g_graphic.depthPriority = 1
            g_graphic.color = g_color_effect

        # brep_mgr = adsk.fusion.TemporaryBRepManager.get()
        # for gap in gaps:
        #     brep_mgr.booleanOperation(shell_box, gap, adsk.fusion.BooleanTypes.DifferenceBooleanType)

        color = adsk.core.Color.create(10, 200, 50, 125)
        color_effect = adsk.fusion.CustomGraphicsSolidColorEffect.create(color)
        self.graphics_box = self.graphics_group.addBRepBody(shell_box)
        self.graphics_box.color = color_effect

    def clear_graphics(self):
        if self.graphics_box is not None:
            if self.graphics_box.isValid:
                self.graphics_box.deleteMe()
        for entity in self.graphics_group:
            if entity.isValid:
                entity.deleteMe()

    def create_brep(self):
        ao = apper.AppObjects()

        new_occ: adsk.fusion.Occurrence = ao.root_comp.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        new_comp = new_occ.component
        new_comp.name = "Cage Part"
        # new_comp.opacity = .5

        if ao.design.designType == adsk.fusion.DesignTypes.ParametricDesignType:

            base_feature = new_comp.features.baseFeatures.add()
            base_feature.startEdit()

            shell_box = create_brep_shell_box(self.modified_b_box, self.thickness_input.value)

            new_body = new_comp.bRepBodies.add(shell_box, base_feature)

            # shell_input = create_shell_input(new_body, thickness)
            # shell_input.targetBaseFeature = base_feature
            # new_comp.features.shellFeatures.add(shell_input)

            base_feature.finishEdit()
            # shell_input = create_shell_input(new_body, thickness)

            # shell_feature = new_comp.features.shellFeatures.add(shell_input)

            custom_features = new_comp.features.customFeatures
            cf_input = custom_features.createInput(config.custom_feature_definition)
            cf_input.setStartAndEndFeatures(base_feature, base_feature)

            for i, selection in enumerate(self.selections):
                cf_input.addDependency('body_' + str(i), selection)

            cf_input.addCustomParameter(
                'gap', 'Bar Spacing',
                adsk.core.ValueInput.createByString(self.inputs.itemById('gap').expression),
                ao.design.fusionUnitsManager.defaultLengthUnits,
                True
            )

            cf_input.addCustomParameter(
                'bar', 'Bar Width',
                adsk.core.ValueInput.createByString(self.inputs.itemById('bar').expression),
                ao.design.fusionUnitsManager.defaultLengthUnits,
                True
            )

            cf_input.addCustomParameter(
                'shell_thickness', 'Cage Thickness',
                adsk.core.ValueInput.createByString(self.thickness_input.expression),
                ao.design.fusionUnitsManager.defaultLengthUnits,
                True
            )

            direction: Direction
            for key, direction in self.directions.items():
                cf_input.addCustomParameter(
                    key, direction.name,
                    adsk.core.ValueInput.createByString(direction.dist_input.expression),
                    ao.design.fusionUnitsManager.defaultLengthUnits,
                    True
                )

            custom_features.add(cf_input)

        else:
            shell_box = create_brep_shell_box(self.modified_b_box, self.thickness_input.value)
            feature_values = FeatureValues(
                self.thickness_input.value,
                self.inputs.itemById('bar').value,
                self.inputs.itemById('gap').value,
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0
            )
            gaps = create_gaps(self.modified_b_box, feature_values)
            brep_mgr = adsk.fusion.TemporaryBRepManager.get()
            for gap in gaps:
                brep_mgr.booleanOperation(shell_box, gap, adsk.fusion.BooleanTypes.DifferenceBooleanType)

            new_comp.bRepBodies.add(shell_box)

    def edit_brep(self, custom_feature: adsk.fusion.CustomFeature):
        # shell_box = create_brep_shell_box(self.modified_b_box, self.thickness_input.value)
        # base_feature = get_base_feature(custom_feature)
        # update_base_feature_body(base_feature, shell_box)

        direction: Direction
        for key, direction in self.directions.items():
            parameter = custom_feature.parameters.itemById(key)
            parameter.expression = direction.dist_input.expression

        parameter = custom_feature.parameters.itemById('shell_thickness')
        parameter.expression = self.thickness_input.expression

        parameter = custom_feature.parameters.itemById('gap')
        parameter.expression = self.gap_input.expression

        parameter = custom_feature.parameters.itemById('bar')
        parameter.expression = self.bar_input.expression

        update_feature_dependencies(custom_feature, self.selections)


class OffsetBoundingBoxCommand(apper.Fusion360CommandBase):
    def __init__(self, name: str, options: dict):
        self.create_feature: bool = options.get('create_feature', True)

        self.the_box: TheBox = None
        self.editing_feature: adsk.fusion.CustomFeature
        self.editing_feature = None
        self.restore_timeline_object: adsk.fusion.TimelineObject
        self.restore_timeline_object = None
        self.rolled_for_edit = False
        self.inputs_initialized = False
        super().__init__(name, options)

        self.make_full_preview = False

    def on_preview(self, command, inputs, args, input_values):
        ao = apper.AppObjects()
        ao.print_msg(f'Preview Event - editing_feature = {self.editing_feature}')

        selections = input_values['body_select']
        if len(selections) > 0:
            new_box = bounding_box_from_selections(selections)
            self.the_box.initialize_box(new_box)

            direction: Direction
            for key, direction in self.the_box.directions.items():
                point = direction.dist_input.manipulatorOrigin.copy()
                vector = direction.direction.copy()
                vector.normalize()
                vector.scaleBy(direction.dist_input.value)
                point.translateBy(vector)

                # if not self.the_box.modified_b_box.contains(point):
                self.the_box.update_box(point)

            if self.make_full_preview:
                self.the_box.update_graphics_full()
                self.make_full_preview = False
            else:
                self.the_box.update_graphics()

    def on_input_changed(self, command, inputs, changed_input, input_values):
        ao = apper.AppObjects()
        ao.print_msg(f'Input Changed Event - editing_feature = {self.editing_feature}')
        self.make_full_preview = True

        thickness_value = input_values['thick_input']
        bar_value = input_values['bar']
        gap_value = input_values['gap']
        gap_limit = thickness_value * 2

        if changed_input.id == 'body_select':
            selections = input_values['body_select']

            if len(selections) > 0:
                self.the_box.selections = selections

                new_box = bounding_box_from_selections(selections)

                self.the_box.initialize_box(new_box)
                self.the_box.update_manipulators()

                o_box = oriented_b_box_from_b_box(new_box)
                # min_side = min(o_box.length, o_box.width, o_box.height)

                min_gaps = []
                for side in [o_box.length, o_box.width, o_box.height]:
                    min_gap = side * .9
                    if min_gap > gap_limit:
                        min_gaps.append(min_gap)

                if len(min_gaps) > 0:
                    most_min_gap = min(min_gaps)
                else:
                    most_min_gap = thickness_value

                four_gaps = (side - bar_value * 3) / 4
                three_gaps = (side - bar_value * 2) / 3
                two_gaps = (side - bar_value) / 2

                if four_gaps > gap_limit:
                    new_gap = four_gaps
                elif three_gaps > gap_limit:
                    new_gap = three_gaps
                elif two_gaps > gap_limit:
                    new_gap = two_gaps
                else:
                    new_gap = most_min_gap

                inputs.itemById('gap').value = new_gap
                self.the_box.feature_values.gap = new_gap

        elif changed_input.id == 'bar':
            self.the_box.feature_values.bar = bar_value

        elif changed_input.id == 'gap':
            self.the_box.feature_values.gap = gap_value

        elif changed_input.id == 'thick_input':
            self.the_box.feature_values.shell_thickness = thickness_value
        else:
            self.make_full_preview = False

    def on_mouse_drag_end(self, command, inputs, args, input_values):
        ao = apper.AppObjects()
        ao.print_msg(f'Mouse Drag End Event - editing_feature = {self.editing_feature}')
        self.make_full_preview = True
        command.doExecutePreview()

    def on_execute(self, command, inputs, args, input_values):
        ao = apper.AppObjects()
        ao.print_msg(f'Execute Event - editing_feature = {self.editing_feature}')

        self.the_box.clear_graphics()
        if self.create_feature:
            self.the_box.create_brep()
        else:
            self.the_box.edit_brep(self.editing_feature)

            if self.restore_timeline_object is not None:
                self.restore_timeline_object.rollTo(False)

    def on_destroy(self, command, inputs, reason, input_values):
        ao = apper.AppObjects()
        ao.print_msg(f'Destroy Event - editing_feature = {self.editing_feature}')

        self.the_box.clear_graphics()

    def on_create(self, command, inputs):
        ao = apper.AppObjects()
        ao.print_msg(f'Create Event - editing_feature = {self.editing_feature}')

        self.inputs_initialized = False
        self.rolled_for_edit = False

        units = ao.units_manager.defaultLengthUnits

        selection_input = inputs.addSelectionInput('body_select', "Input Bodies", "Bodies for Bounding Box")
        selection_input.addSelectionFilter('Bodies')
        selection_input.setSelectionLimits(1, 0)

        # TODO Handle preselected bodies?
        default_selections = []

        # Get initialized bounding box, may really not be needed here...
        b_box = bounding_box_from_selections(default_selections)
        o_box = oriented_b_box_from_b_box(b_box)

        if self.create_feature:
            self.editing_feature = None
            default_thickness = get_default_thickness(units)
            thickness_input = adsk.core.ValueInput.createByReal(default_thickness)

            gap_input = adsk.core.ValueInput.createByReal(2)
            bar_input = adsk.core.ValueInput.createByReal(.2)
        else:
            self.editing_feature = get_editing_feature()
            thickness_expression = self.editing_feature.parameters.itemById('shell_thickness').expression
            thickness_input = adsk.core.ValueInput.createByString(thickness_expression)
            gap_expression = self.editing_feature.parameters.itemById('gap').expression
            gap_input = adsk.core.ValueInput.createByString(gap_expression)
            bar_expression = self.editing_feature.parameters.itemById('bar').expression
            bar_input = adsk.core.ValueInput.createByString(bar_expression)

        inputs.addValueInput('thick_input', "Cage Thickness", units, thickness_input)

        inputs.addValueInput('gap', "Bar Spacing", units, gap_input)
        inputs.addValueInput('bar', "Bar Width", units, bar_input)

        # Create main box class
        self.the_box = TheBox(b_box, inputs, self.editing_feature)

    def on_activate(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs, args, input_values):
        ao = apper.AppObjects()
        ao.print_msg(f'Activate Event - editing_feature = {self.editing_feature}')

        if not self.create_feature:

            if not self.rolled_for_edit:
                self.editing_feature = get_editing_feature()
                timeline = self.editing_feature.parentComponent.parentDesign.timeline
                marker = timeline.markerPosition
                self.restore_timeline_object = timeline[marker - 1]
                self.editing_feature.timelineObject.rollTo(True)
                self.rolled_for_edit = True
                command.beginStep()

            if not self.inputs_initialized:
                selection_input = inputs.itemById('body_select')
                default_selections = get_feature_bodies(self.editing_feature)
                for entity in default_selections:
                    selection_input.addSelection(entity)
                self.inputs_initialized = True
                self.make_full_preview = True
        else:
            # TODO Handle preselected bodies?
            pass


class BoxCustomFeature(apper.Fusion360CustomFeatureBase):
    def __init__(self, name: str, options: dict):
        super().__init__(name, options)
        config.custom_feature_definition = self.definition

    def on_compute(self, args: adsk.fusion.CustomFeatureEventArgs):
        # Get feature parameters and dependencies
        feature_bodies = get_feature_bodies(args.customFeature)
        feature_values = get_feature_values(args.customFeature)

        # Make the box
        b_box = bounding_box_from_selections(feature_bodies)
        expand_box_by_feature_values(b_box, feature_values)

        # TODO Only if necessary, Best way to tell if this is different?  Maybe check min/max points?
        shell_box = create_brep_shell_box(b_box, feature_values.shell_thickness)

        gaps = create_gaps(b_box, feature_values)
        brep_mgr = adsk.fusion.TemporaryBRepManager.get()
        for gap in gaps:
            brep_mgr.booleanOperation(shell_box, gap, adsk.fusion.BooleanTypes.DifferenceBooleanType)

        # Update base feature
        base = get_base_feature(args.customFeature)
        update_base_feature_body(base, shell_box)

        # TODO Update shell feature.  How to properly do this, or is possible today?
        # shell = _getShellFeature(args.customFeature)

        # shell.setThicknesses(
        #     adsk.core.ValueInput.createByReal(0.0),
        #     adsk.core.ValueInput.createByReal(feature_values.shell_thickness)
        # )
