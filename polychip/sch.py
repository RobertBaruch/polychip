import collections
import re
import functools
import pprint
import shapely
from gates import *
from polychip import Transistor
from layers import InkscapeFile
from svg_parse import Transform

class SchObject(object):
    timestamp = 0
    inkscape_to_sch_transform = None  # This must be initialized before instantiating any SchObjects.

    def __init__(self, name, centroid, libname, short_libname):
        self.name = name
        self.sch_loc = shapely.affinity.affine_transform(centroid, SchObject.inkscape_to_sch_transform)
        self.libname = libname
        self.short_libname = short_libname
        self.name_offset_x = 0
        self.name_offset_y = 0
        self.centroid = centroid

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
        print("    1    {:d} {:d}".format(x, y), file=f)
        print("    1    0    0    -1  ", file=f)
        print("$EndComp", file=f)
        print("{:s} {:s} -> {:d}, {:d} ({:s})".format(self.short_libname, self.name, x, y, str(self.centroid)))
        SchObject.timestamp += 1


class SchTransistor(SchObject):
    def __init__(self, q):
        super().__init__(q.name, q.centroid, "NMOS-SMALL", "Q")
        self.name_offset_x = -20
        self.name_offset_y = -50


class SchGate(SchObject):
    def __init__(self, gate):
        super().__init__(gate.output_power_q.name, gate.output_power_q.centroid, None, None)

        if isinstance(gate, PassTransistor):
            self.libname = "NMOS_SUBSTR"
            self.short_libname = "P"
        elif isinstance(gate, Multiplexer):
            assert len(gate.selected_inputs) == 2, "More than 2 input mux isn't supported for schematic output yet."
            self.libname = "2MUX"
            self.short_libname = "2MUX"
            self.name_offset_y = 25
        elif isinstance(gate, NorGate) or isinstance(gate, PowerNorGate):
            n = len(gate.inputs)
            assert n <= 4, "More than 4 input NOR isn't supported for schematic output yet."
            self.libname = ["NOT", "2NOT-AND", "3NOT-AND", "4NOT-AND"][n - 1]
            self.short_libname = ["NOT", "2NOR", "3NOR", "4NOR"][n - 1]
        elif isinstance(gate, TristateInverter):
            self.libname = "INV_TRISTATE_NEG_OE_SMALL"
            self.short_libname = "ZINV"
        elif isinstance(gate, TristateBuffer):
            self.libname = "BUFFER_TRISTATE_NEG_OE_SMALL"
            self.short_libname = "ZBUFF"
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

        for q in gates.qs:
            SchTransistor(q).write_component(f)

        for g in gates.pulldowns:
            SchTransistor(only(g.qs)).write_component(f)

        for g in gates.pass_qs:
            SchGate(g).write_component(f)

        for g in gates.muxes:
            if len(g.inputs) == 2:
                SchGate(g).write_component(f)
            else:
                print("[{:d}-MUX not supported for schematic output; just placing its transistors.".format(
                    len(g.inputs)))
                for q in g.qs:
                    SchTransistor(q).write_component(f)

        for g in gates.nors:
            if len(g.inputs) <= 4:
                SchGate(g).write_component(f)
            else:
                print("[{:d}-NOR not supported for schematic output; just placing its transistors.".format(
                    len(g.inputs)))
                for q in g.qs:
                    SchTransistor(q).write_component(f)

        for g in gates.tristate_inverters:
            SchGate(g).write_component(f)

        for g in gates.tristate_buffers:
            SchGate(g).write_component(f)

        print("$EndSCHEMATC", file=f)
