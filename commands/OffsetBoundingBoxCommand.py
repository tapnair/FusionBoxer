import adsk.core
import adsk.fusion
import apper
from apper import AppObjects


def middle(min_p_value, max_p_value):
    return min_p_value + ((max_p_value - min_p_value) / 2)


def mid_point(p1: adsk.core.Point3D, p2: adsk.core.Point3D):
    return adsk.core.Point3D.create(
        middle(p1.x, p2.x),
        middle(p1.y, p2.y),
        middle(p1.z, p2.z)
    )


class Direction:
    def __init__(self, name: str, origin: adsk.core.Point3D, direction: adsk.core.Vector3D):
        self.name = name
        self.origin = origin
        self.direction = direction

    def get_distance_input(self, inputs):

        # Create a default value using a string
        default_value = adsk.core.ValueInput.createByString('0.0 in')
        dist_input = inputs.addDistanceValueCommandInput(f"dist_{self.name}", self.name, default_value)
        dist_input.setManipulator(self.origin, self.direction)
        return dist_input


class TheBox:

    def __init__(self, b_box: adsk.core.BoundingBox3D):
        ao = AppObjects()
        root_comp = ao.root_comp

        self.b_box = b_box
        min_p = b_box.minPoint
        max_p = b_box.maxPoint

        self.modified_b_box = self.b_box.copy()

        self.center_point = mid_point(min_p, max_p)

        self.x_pos_vector = root_comp.yZConstructionPlane.geometry.normal.copy()
        self.x_neg_vector = root_comp.yZConstructionPlane.geometry.normal.copy()
        self.x_neg_vector.scaleBy(-1)
        self.y_pos_vector = root_comp.xZConstructionPlane.geometry.normal.copy()
        self.y_neg_vector = root_comp.xZConstructionPlane.geometry.normal.copy()
        self.y_neg_vector.scaleBy(-1)
        self.z_pos_vector = root_comp.xYConstructionPlane.geometry.normal.copy()
        self.z_neg_vector = root_comp.xYConstructionPlane.geometry.normal.copy()
        self.z_neg_vector.scaleBy(-1)

        self.graphics_group = ao.root_comp.customGraphicsGroups.add()

        self.brep_mgr = adsk.fusion.TemporaryBRepManager.get()
        self.brep_box = None
        self.graphics_box = None

        # self.update_graphics()

        self.directions = [
            Direction("X Pos",
                      adsk.core.Point3D.create(max_p.x, middle(min_p.y, max_p.y), middle(min_p.z, max_p.z)),
                      self.x_pos_vector
                      ),
            Direction("X Neg",
                      adsk.core.Point3D.create(min_p.x, middle(min_p.y, max_p.y), middle(min_p.z, max_p.z)),
                      self.x_neg_vector
                      ),
            Direction("Y Pos",
                      adsk.core.Point3D.create(middle(min_p.x, max_p.x), max_p.y, middle(min_p.z, max_p.z)),
                      self.y_pos_vector
                      ),
            Direction("Y Neg",
                      adsk.core.Point3D.create(middle(min_p.x, max_p.x), min_p.y, middle(min_p.z, max_p.z)),
                      self.y_neg_vector
                      ),
            Direction("Z Pos",
                      adsk.core.Point3D.create(middle(min_p.x, max_p.x), middle(min_p.y, max_p.y), max_p.z),
                      self.z_pos_vector
                      ),
            Direction("Z Neg",
                      adsk.core.Point3D.create(middle(min_p.x, max_p.x), middle(min_p.y, max_p.y), min_p.z),
                      self.z_neg_vector
                      )
        ]

    def initialize_box(self):
        self.modified_b_box = self.b_box.copy()

    def update_box(self, point: adsk.core.Point3D):
        self.modified_b_box.expand(point)

    def update_graphics(self):
        self.clear_graphics()
        self.update_brep_box()

        self.graphics_box = self.graphics_group.addBRepBody(self.brep_box)

        # self.graphics_group.setOpacity(.5, True)
        color = adsk.core.Color.create(10, 200, 50, 125)
        color_effect = adsk.fusion.CustomGraphicsSolidColorEffect.create(color)
        self.graphics_box.color = color_effect

        # self.graphics_box.transform = transform

    def clear_graphics(self):
        if self.graphics_box is not None:
            # self.graphics_box = adsk.fusion.CustomGraphicsBRepBody.cast(self.graphics_box)
            if self.graphics_box.isValid:
                self.graphics_box.deleteMe()

    def update_brep_box(self):
        # if self.brep_box is not None:
        #     self.brep_box.deleteMe()
        o_box = adsk.core.OrientedBoundingBox3D.create(
            mid_point(self.modified_b_box.minPoint, self.modified_b_box.maxPoint),
            self.x_pos_vector,
            self.y_pos_vector,
            self.modified_b_box.maxPoint.x - self.modified_b_box.minPoint.x,
            self.modified_b_box.maxPoint.y - self.modified_b_box.minPoint.y,
            self.modified_b_box.maxPoint.z - self.modified_b_box.minPoint.z
        )
        self.brep_box = self.brep_mgr.createBox(o_box)

        # transform = adsk.core.Matrix3D.create()
        # center_point = mid_point(self.b_box.minPoint, self.b_box.maxPoint)
        # vector = center_point.asVector()
        # vector.scaleBy(-1)
        # transform.translation = vector
        # self.brep_mgr.transform(self.brep_box, transform)

    def make_brep_real(self):
        ao = AppObjects()
        self.update_brep_box()
        base_feature = ao.root_comp.features.baseFeatures.add()
        base_feature.startEdit()
        ao.root_comp.bRepBodies.add(self.brep_box, base_feature)
        base_feature.finishEdit()


class OffsetBoundingBoxCommand(apper.Fusion360CommandBase):
    def __init__(self, name: str, options: dict):
        self.the_box: TheBox
        super().__init__(name, options)

    def on_preview(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs, args: adsk.core.CommandEventArgs, input_values):
        ao = AppObjects()
        self.the_box.initialize_box()
        for changed_input in inputs:
            if changed_input.objectType == adsk.core.DistanceValueCommandInput.classType():
                changed_input = adsk.core.DistanceValueCommandInput.cast(changed_input)

                point = changed_input.manipulatorOrigin.copy()
                vector = changed_input.manipulatorDirection.copy()
                vector.normalize()
                vector.scaleBy(changed_input.value)
                point.translateBy(vector)

                if not self.the_box.modified_b_box.contains(point):
                    self.the_box.update_box(point)

        self.the_box.update_graphics()

    def on_destroy(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs, reason, input_values):
        self.the_box.clear_graphics()

    def on_input_changed(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs, changed_input,
                         input_values):
        pass

    def on_execute(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs, args, input_values):
        self.the_box.clear_graphics()
        self.the_box.make_brep_real()

    def on_create(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs):
        ao = AppObjects()
        b_box = ao.root_comp.boundingBox
        self.the_box = TheBox(b_box)

        for direction in self.the_box.directions:
            direction.get_distance_input(inputs)