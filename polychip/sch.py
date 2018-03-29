import collections
import re
import functools
import math
import pprint
import shapely
from gates import *
from polychip import Transistor
from layers import InkscapeFile
from svg_parse import Transform

class SchObject(object):
    timestamp = 0
    inkscape_to_sch_transform = None  # This must be initialized before instantiating any SchObjects.

    def __init__(self, obj, name, centroid, transformed_centroid = None):
        self.obj = obj
        self.name = name
        if transformed_centroid is None:
            self.sch_loc = shapely.affinity.affine_transform(centroid, SchObject.inkscape_to_sch_transform)
        else:
            self.sch_loc = transformed_centroid
        self.libname = ""
        self.short_libname = ""
        self.name_offset = (0, 0)
        self.rotation = 0  # In 90-degree intervals
        self.centroid = centroid
        self.output_offsets = []  # tuple of x,y, ordered same as gate
        self.input_offsets = []
        self.short_libname_offset = None
        self.output_nets = []
        self.input_nets = []

    def transform(self):
        t = Transform.rotate(self.rotation * math.tau / 4) @ Transform.scale(1, -1)
        return "    {:d}    {:d}    {:d}    {:d}  ".format(
            round(t.a), round(t.c), round(t.b), round(t.d))

    def write_component(self, f):
        print("$Comp", file=f)
        print("L project5474:{:s} {:s}".format(self.libname, self.name), file=f)
        print("U 1 1 {:08X}".format(SchObject.timestamp), file=f)
        x = round(self.sch_loc.x)
        y = round(self.sch_loc.y)
        print("P {:d} {:d}".format(x, y), file=f)
        print("F 0 \"{:s}\" H {:d} {:d} 20  0000 C CNN".format(
            self.name, x + self.name_offset[0], y + self.name_offset[1]), file=f)
        libname_x = x
        libname_y = y
        libname_invisible = "1"
        if self.short_libname_offset is not None:
            libname_x += self.short_libname_offset[0]
            libname_y += self.short_libname_offset[1]
            libname_invisible = "0"
        print("F 1 \"{:s}\" H {:d} {:d} 20  000{:s} C CNN".format(
            self.short_libname, libname_x, libname_y, libname_invisible), file=f)
        print("F 2 \"\" H {:d} {:d} 20  0001 C CNN".format(x, y), file=f)
        print("F 3 \"\" H {:d} {:d} 20  0001 C CNN".format(x, y), file=f)
        print("F 4 \"{:s}\" H {:d} {:d} 20  0001 C CNN".format(str(self.centroid), x, y), file=f)
        print("    1    {:d} {:d}".format(x, y), file=f)
        print(self.transform(), file=f)
        print("$EndComp", file=f)
        SchObject.timestamp += 1

        if type(self) == SchTransistor:
            for i, e in enumerate([self.q.electrode0_net, self.q.electrode1_net]):
                offset_x = self.electrode_offsets[i][0]
                offset_y = self.electrode_offsets[i][1]
                loc = shapely.geometry.Point(self.sch_loc.x + offset_x, self.sch_loc.y + offset_y)
                if is_power_net(e):
                    SchPower(e, loc, 2 * i).write_component(f)
                if is_ground_net(e):
                    SchGround(e, loc, 2 * (1 - i)).write_component(f)


class SchTransistor(SchObject):
    def __init__(self, q):
        super().__init__(q, q.name, q.centroid)
        self.q = q
        self.libname = "NMOS-SMALL"
        self.short_libname = "Q"
        self.electrode_offsets = [(30, -60), (30, 60)]
        self.input_offsets = [(-40, 0)]
        # self.output_nets = [q.electrode0_net, q.electrode1_net]
        self.input_nets = [q.gate_net]


class SchPower(SchObject):
    def __init__(self, net, point, rotation):
        super().__init__(None, net, None, point)
        self.libname = "VCC"
        self.short_libname = "VCC"
        self.name_offset = (0, 60)
        self.rotation = rotation


class SchGround(SchObject):
    def __init__(self, net, point, rotation):
        super().__init__(None, net, None, point)
        self.libname = "GND"
        self.short_libname = "GND"
        self.name_offset = (0, -80)
        self.rotation = rotation


class SchGate(SchObject):
    def __init__(self, gate):
        super().__init__(gate, gate.output_power_q.name, gate.output_power_q.centroid)
        self.output_nets = gate.outputs
        self.input_nets = gate.inputs

        if isinstance(gate, PassTransistor):
            self.libname = "NMOS-SMALL"
            self.short_libname = "Q"
            self.rotation = 1

        elif isinstance(gate, Multiplexer):
            n = len(gate.selected_inputs)
            assert n <= 3, "More than 3 input mux isn't supported for schematic output yet."
            self.libname = "{:d}MUX".format(n)
            self.short_libname = self.libname
            self.name_offset = (0, 25)
            if n == 2:
                self.output_offsets = [(150, 0)]
                self.input_offsets = [(-150, -50), (-150, 50), (-50, 150), (50, 150)]

        elif isinstance(gate, NorGate) or isinstance(gate, PowerNorGate):
            n = len(gate.inputs)
            assert n <= 4, "More than 4 input NOR isn't supported for schematic output yet."
            self.libname = ["NOT", "2NOT-AND", "3NOT-AND", "4NOT-AND"][n - 1]
            self.short_libname = ["NOT", "2NOR", "3NOR", "4NOR"][n - 1]
            if n == 1:
                self.output_offsets = [(150, 0)]
                self.input_offsets = [(-150, 0)]
            elif n == 2:
                self.output_offsets = [(200, 0)]
                self.input_offsets = [(-150, -50), (-150, 50)]

        elif isinstance(gate, TristateInverter):
            self.libname = "INV_TRISTATE_NEG_OE_SMALL"
            self.short_libname = "ZINV"
            self.input_offsets = [(-30, 0), (40, -70)]
            self.output_offsets = [(100, 0)]

        elif isinstance(gate, TristateBuffer):
            self.libname = "BUFFER_TRISTATE_NEG_OE_SMALL"
            self.short_libname = "ZBUFF"
            self.input_offsets = [(-30, 0), (40, -70)]
            self.output_offsets = [(100, 0)]

        elif isinstance(gate, MuxDLatch):
            self.libname = "MUX_D_LATCH"
            self.short_libname = "DLATCH"
            self.input_offsets = [(-200, 0), (-50, 200), (50, 200)]
            self.output_offsets = [(200, 50), (200, -50)]

        elif isinstance(gate, Lut):
            n = len(gate.inputs)
            assert n > 1, "A 1LUT ({:s}) makes no sense. It must be an inverter.".format(gate.name)
            assert n <= 7, "{:d}LUT ({:s}) isn't supported for schematic output yet.".format(n, gate.name)
            self.libname = "{:d}LUT".format(n)
            self.short_libname = self.libname
            self.output_offsets = [(120, 0)]
            self.name_offset = (0, 30)
            self.short_libname_offset = (0, -30)
            if n == 2:
                self.input_offsets = [(-120, -30), (-120, 30)]
            elif n == 3:
                self.input_offsets = [(-120, -70), (-120, 0), (-120, 70)]
            elif n == 4:
                self.input_offsets = [(-120, -90), (-120, -30), (-120, 30), (-120, 90)]
            elif n == 5:
                self.input_offsets = [(-120, -120), (-120, -60), (-120, 0), (-120, 60), (-120, 120)]
            elif n == 6:
                self.input_offsets = [(-120, -150), (-120, -90), (-120, -30), (-120, 30), (-120, 90), (-120, 150)]
            elif n == 7:
                self.input_offsets = [(-120, -180), (-120, -120), (-120, -60), (-120, 0), (-120, 60), (-120, 120), (-120, 180)]

        else:
            raise AssertionError("Unsupported gate for schematic output: " + str(type(gate)))


def sch_size_transform(file):
    bounding_box = shapely.ops.cascaded_union([shapely.geometry.box(*m.bounds) for m in 
        [file.multicontact, file.multipoly, file.multidiff, file.multimetal]]).bounds
    minx, miny, maxx, maxy = bounding_box
    print(str(bounding_box))
    w = maxx - minx
    h = maxy - miny
    d = max(w, h)
    transform = Transform.translate(0, h) @ Transform.scale(1, -1) @ Transform.translate(-minx, -miny)
    transform = Transform.scale(48000.0 / d, 48000.0 / d) @ transform
    return transform.to_shapely_transform()


def write_wire(f, output_loc, output_offset, input_loc, input_offset):
    x1 = round(output_loc.x + output_offset[0])
    y1 = round(output_loc.y + output_offset[1])
    x2 = round(input_loc.x + input_offset[0])
    y2 = round(input_loc.y + input_offset[1])
    print("Wire Wire Line", file=f)
    print("    {:d} {:d} {:d} {:d}".format(x1, y1, x2, y2), file=f)


def write_sch_file(filename, gates, inkscape_to_sch_transform):
    with open(filename, 'wt', encoding='utf-8') as f:
        print("EESchema Schematic File Version 4", file=f)
        print("EELAYER 26 0", file=f)
        print("EELAYER END", file=f)
        print("$Descr User 48000 48000", file=f)
        print("encoding utf-8", file=f)
        print("Sheet 1 1", file=f)
        print("Title \"\"", file=f)
        print("Date \"\"", file=f)
        print("Rev \"\"", file=f)
        print("Comp \"\"", file=f)
        print("Comment1 \"\"", file=f)
        print("Comment2 \"\"", file=f)
        print("Comment3 \"\"", file=f)
        print("Comment4 \"\"", file=f)
        print("$EndDescr", file=f)

        SchObject.inkscape_to_sch_transform = inkscape_to_sch_transform
        sch_objects = {}

        for q in gates.qs:
            sch_objects[q.name] = SchTransistor(q)

        for g in gates.pulldowns:
            sch_objects[only(g.qs).name] = SchTransistor(only(g.qs))

        for g in gates.pass_qs:
            sch_objects[g.name] = SchGate(g)

        for g in gates.luts:
            if len(g.inputs) <= 7:
                sch_objects[g.name] = SchGate(g)
            else:
                print("[{:d}-LUT not supported for schematic output; just placing its transistors.".format(
                    len(g.inputs)))
                for q in g.qs:
                    sch_objects[q.name] = SchTransistor(q)

        for g in gates.muxes:
            if len(g.selecting_inputs) <= 3:
                sch_objects[g.name] = SchGate(g)
            else:
                print("[{:d}-MUX not supported for schematic output; just placing its transistors.".format(
                    len(g.selecting_inputs)))
                for q in g.qs:
                    sch_objects[q.name] = SchTransistor(q)

        for g in gates.nors:
            if len(g.inputs) <= 4:
                sch_objects[g.name] = SchGate(g)
            else:
                print("[{:d}-NOR not supported for schematic output; just placing its transistors.".format(
                    len(g.inputs)))
                for q in g.qs:
                    sch_objects[q.name] = SchTransistor(q)

        for g in gates.tristate_inverters:
            sch_objects[g.name] = SchGate(g)

        for g in gates.tristate_buffers:
            sch_objects[g.name] = SchGate(g)

        for g in gates.mux_d_latches:
            if len(g.clr_inputs) <= 1 and len(g.set_inputs) <= 1:
                sch_objects[g.name] = SchGate(g)
            else:
                print("D-latch with {:d} clears and {:d} sets not "
                      "supported for schematic output; just placing its transistors.".format(
                        len(g.clr_inputs), len(g.set_inputs)))
                for q in g.qs:
                    sch_objects[q.name] = SchTransistor(q)

        for sch_object in sch_objects.values():
            sch_object.write_component(f)

        sch_objects_by_input_net = collections.defaultdict(set)
        sch_objects_by_output_net = collections.defaultdict(set)
        for o in sch_objects.values():
            for input in o.input_nets:
                sch_objects_by_input_net[input].add(o)
            for output in o.output_nets:
                sch_objects_by_output_net[output].add(o)

        for net, os in sch_objects_by_output_net.items():
            print("output net {:s} -> {:d}".format(net, len(os)))
        for net, os in sch_objects_by_input_net.items():
            print("input net {:s} -> {:d}".format(net, len(os)))

        for o in sch_objects.values():
            for i, output_offset in enumerate(o.output_offsets):
                output_net = o.output_nets[i]
                for input_obj in (x for x in sch_objects_by_input_net[output_net] if len(x.input_offsets) > 0):
                    for ii, input_net in enumerate(input_obj.input_nets):
                        if input_net == output_net:
                            write_wire(f, o.sch_loc, output_offset, input_obj.sch_loc, input_obj.input_offsets[ii])



        print("$EndSCHEMATC", file=f)
