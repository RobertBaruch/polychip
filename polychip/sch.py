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

    def __init__(self, obj, name, centroid, libname, short_libname):
        self.obj = obj
        self.name = name
        self.sch_loc = shapely.affinity.affine_transform(centroid, SchObject.inkscape_to_sch_transform)
        self.libname = libname
        self.short_libname = short_libname
        self.name_offset_x = 0
        self.name_offset_y = 0
        self.rotation = 0  # In 90-degree intervals
        self.centroid = centroid
        self.output_offsets = []  # tuple of x,y, ordered same as gate
        self.input_offsets = []
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
        print("F 0 \"{:s}\" H {:d} {:d} 20  0000 L CNN".format(
            self.name, x + self.name_offset_x, y + self.name_offset_y), file=f)
        print("F 1 \"{:s}\" H {:d} {:d} 20  0001 C CNN".format(self.short_libname, x, y), file=f)
        print("F 2 \"\" H {:d} {:d} 20  0001 C CNN".format(x, y), file=f)
        print("F 3 \"\" H {:d} {:d} 20  0001 C CNN".format(x, y), file=f)
        print("F 4 \"{:s}\" H {:d} {:d} 20  0001 C CNN".format(str(self.centroid), x, y), file=f)
        print("    1    {:d} {:d}".format(x, y), file=f)
        print(self.transform(), file=f)
        print("$EndComp", file=f)
        SchObject.timestamp += 1


class SchTransistor(SchObject):
    def __init__(self, q):
        super().__init__(q, q.name, q.centroid, "NMOS-SMALL", "Q")
        # self.output_offsets = [(30, -60), (30, 60)]
        self.input_offsets = [(-40, 0)]
        # self.output_nets = [q.electrode0_net, q.electrode1_net]
        self.input_nets = [q.gate_net]


class SchGate(SchObject):
    def __init__(self, gate):
        super().__init__(gate, gate.output_power_q.name, gate.output_power_q.centroid, None, None)
        if gate.output is not None:
            self.output_nets = [gate.output]
        self.input_nets = gate.inputs

        if isinstance(gate, PassTransistor):
            self.libname = "NMOS-SMALL"
            self.short_libname = "Q"
            self.rotation = 1

        elif isinstance(gate, Multiplexer):
            n = len(gate.selected_inputs)
            assert n <= 3, "More than 3 input mux isn't supported for schematic output yet."
            self.libname = "{:d}MUX".format(n)
            self.short_libname = "{:d}MUX".format(n)
            self.name_offset_y = 25
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

        elif isinstance(gate, TristateBuffer):
            self.libname = "BUFFER_TRISTATE_NEG_OE_SMALL"
            self.short_libname = "ZBUFF"

        elif isinstance(gate, MuxDLatch):
            self.libname = "MUX_D_LATCH"
            self.short_libname = "DLATCH"

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

        for g in gates.muxes:
            if len(g.inputs) <= 3:
                sch_objects[g.name] = SchGate(g)
            else:
                print("[{:d}-MUX not supported for schematic output; just placing its transistors.".format(
                    len(g.inputs)))
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
