from importlib import reload

import adsk.core
import adsk.fusion
import apper
from apper import AppObjects
import config

reload(config)


def middle(min_p_value, max_p_value):
    return min_p_value + ((max_p_value - min_p_value) / 2)


def mid_point(p1: adsk.core.Point3D, p2: adsk.core.Point3D):
    return adsk.core.Point3D.create(
        middle(p1.x, p2.x),
        middle(p1.y, p2.y),
        middle(p1.z, p2.z)
    )


class Direction:
    def __init__(self, name: str, direction: adsk.core.Vector3D, inputs: adsk.core.CommandInputs):
        ao = AppObjects()
        self.name = name
        self.direction = direction
        self.origin = adsk.core.Point3D.create(0, 0, 0)

        units = ao.units_manager.defaultLengthUnits
        try:
            default_shell = config.DEFAULT_OFFSET
        except AttributeError:
            default_shell = f"1 {units}"

        default_value = adsk.core.ValueInput.createByString(default_shell)
        self.dist_input: adsk.core.DistanceValueCommandInput = inputs.addDistanceValueCommandInput(
            f"dist_{self.name}", self.name, default_value
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

    def __init__(self, b_box: adsk.core.BoundingBox3D, inputs: adsk.core.CommandInputs):
        ao = AppObjects()
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

        self.directions = {
            "X Positive": Direction("X Positive", self.x_pos_vector, inputs),
            "X Negative": Direction("X Negative", self.x_neg_vector, inputs),
            "Y Positive": Direction("Y Positive", self.y_pos_vector, inputs),
            "Y Negative": Direction("Y Negative", self.y_neg_vector, inputs),
            "Z Positive": Direction("Z Positive", self.z_pos_vector, inputs),
            "Z Negative": Direction("Z Negative", self.z_neg_vector, inputs)
        }

        self.graphics_group = ao.root_comp.customGraphicsGroups.add()
        self.brep_mgr = adsk.fusion.TemporaryBRepManager.get()
        self.brep_box = None
        self.graphics_box = None

    def initialize_box(self, b_box):
        self.modified_b_box = b_box.copy()

    def update_box(self, point: adsk.core.Point3D):
        self.modified_b_box.expand(point)

    def update_manipulators(self):
        min_p = self.modified_b_box.minPoint
        max_p = self.modified_b_box.maxPoint

        self.directions["X Positive"].update_manipulator(adsk.core.Point3D.create(
            max_p.x, middle(min_p.y, max_p.y), middle(min_p.z, max_p.z))
        )
        self.directions["X Negative"].update_manipulator(adsk.core.Point3D.create(
            min_p.x, middle(min_p.y, max_p.y), middle(min_p.z, max_p.z))
        )
        self.directions["Y Positive"].update_manipulator(adsk.core.Point3D.create(
            middle(min_p.x, max_p.x), max_p.y, middle(min_p.z, max_p.z))
        )
        self.directions["Y Negative"].update_manipulator(adsk.core.Point3D.create(
            middle(min_p.x, max_p.x), min_p.y, middle(min_p.z, max_p.z))
        )
        self.directions["Z Positive"].update_manipulator(adsk.core.Point3D.create(
            middle(min_p.x, max_p.x), middle(min_p.y, max_p.y), max_p.z)
        )
        self.directions["Z Negative"].update_manipulator(adsk.core.Point3D.create(
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
        o_box = adsk.core.OrientedBoundingBox3D.create(
            mid_point(self.modified_b_box.minPoint, self.modified_b_box.maxPoint),
            self.x_pos_vector,
            self.y_pos_vector,
            self.modified_b_box.maxPoint.x - self.modified_b_box.minPoint.x,
            self.modified_b_box.maxPoint.y - self.modified_b_box.minPoint.y,
            self.modified_b_box.maxPoint.z - self.modified_b_box.minPoint.z
        )
        self.brep_box = self.brep_mgr.createBox(o_box)

    def make_brep_real(self, thickness):
        ao = AppObjects()
        self.update_brep_box()

        if ao.design.designType == adsk.fusion.DesignTypes.ParametricDesignType:
            start = apper.start_group()

            new_occ: adsk.fusion.Occurrence = ao.root_comp.occurrences.addNewComponent(adsk.core.Matrix3D.create())
            new_comp = new_occ.component

            base_feature = new_comp.features.baseFeatures.add()
            base_feature.startEdit()
            new_comp.bRepBodies.add(self.brep_box, base_feature)
            base_feature.finishEdit()
        else:
            new_occ: adsk.fusion.Occurrence = ao.root_comp.occurrences.addNewComponent(adsk.core.Matrix3D.create())
            new_comp = new_occ.component
            new_comp.bRepBodies.add(self.brep_box)

        obj_col = adsk.core.ObjectCollection.create()
        obj_col.add(new_comp.bRepBodies.item(0))
        shell_input = new_comp.features.shellFeatures.createInput(obj_col)
        thickness_input = adsk.core.ValueInput.createByReal(thickness)
        shell_input.outsideThickness = thickness_input
        new_comp.features.shellFeatures.add(shell_input)

        new_comp.name = "Bounding Box"
        new_comp.opacity = .5

        if ao.design.designType == adsk.fusion.DesignTypes.ParametricDesignType:
            apper.end_group(start)


class OffsetBoundingBoxCommand(apper.Fusion360CommandBase):
    def __init__(self, name: str, options: dict):
        self.the_box: TheBox
        self.the_box = None
        super().__init__(name, options)

    def on_preview(self, command, inputs, args, input_values):
        selections = input_values['body_select']
        if len(selections) > 0:
            new_box: adsk.core.BoundingBox3D = selections[0].boundingBox
            for selection in selections[1:]:
                new_box.combine(selection.boundingBox)

            self.the_box.initialize_box(new_box)

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
        if changed_input.id == 'body_select':
            selections = input_values['body_select']

            if len(selections) > 0:
                new_box: adsk.core.BoundingBox3D = selections[0].boundingBox

                for selection in selections[1:]:
                    new_box.combine(selection.boundingBox)

                self.the_box.initialize_box(new_box)
                self.the_box.update_manipulators()

    def on_execute(self, command, inputs, args, input_values):
        self.the_box.clear_graphics()
        self.the_box.make_brep_real(input_values['thick_input'])

    def on_destroy(self, command, inputs, reason, input_values):
        self.the_box.clear_graphics()

    def on_create(self, command, inputs):
        ao = AppObjects()

        selection_input = inputs.addSelectionInput('body_select', "Select Bodies",
                                                   "Select the bodies to create a bounding Box")
        selection_input.addSelectionFilter('Bodies')
        selection_input.setSelectionLimits(1, 0)

        units = ao.units_manager.defaultLengthUnits
        try:
            default_shell = config.DEFAULT_SHELL
        except AttributeError:
            default_shell = f"1 {units}"
        default_value = adsk.core.ValueInput.createByString(default_shell)
        inputs.addValueInput('thick_input', "Outer Shell Thickness", units, default_value)

        b_box = adsk.core.BoundingBox3D.create(
            adsk.core.Point3D.create(-1, -1, -1),
            adsk.core.Point3D.create(1, 1, 1)
        )
        self.the_box = TheBox(b_box, inputs)
