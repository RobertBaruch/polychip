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
        self.name_orientation = "H"
        self.rotation = 0  # In 90-degree intervals
        self.centroid = centroid
        self.output_offsets = []  # tuple of x,y, ordered same as gate
        self.input_offsets = []
        self.short_libname_offset = None
        self.output_nets = []
        self.input_nets = []
        self.extra_data = []

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
        print("F 0 \"{:s}\" {:s} {:d} {:d} 20  0000 C CNN".format(
            self.name, self.name_orientation, x + self.name_offset[0], y + self.name_offset[1]), file=f)
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
        for i, extra in enumerate(self.extra_data):
            print("F {:d} \"{:s}\" H {:d} {:d} 20  0001 C CNN".format(i + 5, self.extra_data[i], x, y), file=f)
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


class SchPulldown(SchObject):
    def __init__(self, gate):
        super().__init__(gate, gate.name, gate.q().centroid)
        self.libname = "Pulldown"
        self.short_libname = "R"
        self.input_offsets = [(0, 0)]
        self.output_offsets = [(0, 0)]
        self.input_nets = [gate.q().nongrounded_electrode_net()]
        self.output_nets = [gate.q().nongrounded_electrode_net()]
        self.name_offset = (0, -115)
        self.name_orientation = "V"


class SchPullup(SchObject):
    def __init__(self, gate):
        super().__init__(gate, gate.name, gate.q().centroid)
        self.libname = "Pullup"
        self.short_libname = "R"
        self.input_offsets = [(0, 0)]
        self.output_offsets = [(0, 0)]
        self.input_nets = [gate.q().nonvcc_electrode_net()]
        self.output_nets = [gate.q().nonvcc_electrode_net()]
        self.name_offset = (0, 115)
        self.name_orientation = "V"


class SchPin(SchObject):
    def __init__(self, label, rotation):
        super().__init__(label, label.text, label.center)
        self.rotation = rotation
        if not is_power_net(label.text) and not is_ground_net(label.text):
            self.output_offsets = [(0, 0)]
            self.input_offsets = [(0, 0)]
            self.output_nets = [label.text]
            self.input_nets = [label.text]

    def write_component(self, f):
        x = round(self.sch_loc.x)
        y = round(self.sch_loc.y)
        print("Text GLabel {:d} {:d} {:d} 50 BiDi ~ 0".format(x, y, self.rotation), file=f)
        print(self.name, file=f)


class SchGate(SchObject):
    def __init__(self, gate):
        super().__init__(gate, gate.output_power_q.name, gate.output_power_q.centroid)
        self.output_nets = gate.outputs
        self.input_nets = gate.inputs

        if isinstance(gate, PassTransistor):
            self.libname = "NMOS-SMALL"
            self.short_libname = "Q"
            self.rotation = 1

        elif isinstance(gate, PowerMultiplexer):
            n = len(gate.selecting_inputs)
            assert n <= 3, "More than 3 input powermux isn't supported for schematic yet."
            self.name_orientation = "V"
            # + inputs come first, then - inputs.
            if len(gate.high_inputs) == 1 and len(gate.low_inputs) == 1:
                self.libname = "2PWRMUX"
                self.output_offsets = [(150, 0)]
                self.input_offsets = [(-150, -50), (-150, 50)]

            elif len(gate.high_inputs) == 2 and len(gate.low_inputs) == 1:
                self.libname = "2+1-MUX"
                self.output_offsets = [(150, 0)]
                self.input_offsets = [(-150, -50), (-150, 0), (-150, 50)]

            elif len(gate.high_inputs) == 1 and len(gate.low_inputs) == 2:
                self.libname = "1+2-MUX"
                self.output_offsets = [(150, 0)]
                self.input_offsets = [(-150, -50), (-150, 0), (-150, 50)]

            self.short_libname = self.libname

        elif isinstance(gate, Multiplexer):
            n = len(gate.selected_inputs)
            assert n <= 3, "More than 3 input mux isn't supported for schematic output yet."
            self.libname = "{:d}MUX".format(n)
            self.short_libname = self.libname
            self.name_offset = (0, 25)
            # Selected inputs (X) come first, then selecting inputs (S).
            if n == 2:
                self.output_offsets = [(150, 0)]
                self.input_offsets = [(-150, -50), (-150, 50), (-50, 150), (50, 150)]
            elif n == 3:
                self.output_offsets = [(200, 0)]
                self.input_offsets = [(-200, -100), (-200, 0), (-200, 100), (-100, 200), (0, 200), (100, 200)]

        elif isinstance(gate, NorGate) or isinstance(gate, PowerNorGate):
            n = len(gate.inputs)
            assert n <= 6, "More than 6-input NOR isn't supported for schematic output yet."
            if n == 1:
                self.libname = "NOT"
                self.short_libname = "NOT"
            else:
                self.libname = "{:d}NOT-AND".format(n)
                self.short_libname = "{:d}NOR".format(n)
            if n == 1:
                self.output_offsets = [(150, 0)]
                self.input_offsets = [(-150, 0)]
            elif n == 2:
                self.output_offsets = [(200, 0)]
                self.input_offsets = [(-150, -50), (-150, 50)]
            elif n == 3:
                self.output_offsets = [(200, 0)]
                self.input_offsets = [(-150, -50), (-150, 0), (-150, 50)]
            elif n == 4:
                self.output_offsets = [(200, 0)]
                self.input_offsets = [(-150, -150), (-150, -50), (-150, 50), (-150, 150)]
            elif n == 5:
                self.output_offsets = [(200, 0)]
                self.input_offsets = [(-150, -200), (-150, -100), (-150, 0), (-150, 100), (-150, 200)]
            elif n == 6:
                self.output_offsets = [(200, 0)]
                self.input_offsets = [(-150, -250), (-150, -150), (-150, -50), (-150, 50), (-150, 150), (-150, 250)]

        elif isinstance(gate, Nand):
            n = len(gate.inputs)
            assert n <= 3, "More than 3-input NAND isn't supported for schematic output yet."
            assert n > 1, "1-input NAND gate makes no sense."
            self.libname = "{:d}NAND".format(n)
            self.short_libname = self.libname
            if n == 2:
                self.output_offsets = [(200, 0)]
                self.input_offsets = [(-150, -50), (-150, 50)]
            elif n == 3:
                self.output_offsets = [(200, 0)]
                self.input_offsets = [(-150, -50), (-150, 0), (-150, 50)]

        elif isinstance(gate, Or):
            n = len(gate.inputs)
            assert n <= 6, "More than 6-input OR isn't supported for schematic output yet."
            assert n > 1, "1-input OR gate makes no sense."
            self.libname = "{:d}OR".format(n)
            self.short_libname = self.libname
            x = round(self.sch_loc.x)
            y = round(self.sch_loc.y)
            print("Place {:s} at {:d}, {:d}".format(self.libname, x, y))
            if n == 2:
                self.output_offsets = [(200, 0)]
                self.input_offsets = [(-150, -50), (-150, 50)]
            elif n == 3:
                self.output_offsets = [(200, 0)]
                self.input_offsets = [(-150, -50), (-150, 0), (-150, 50)]
            elif n == 4:
                self.output_offsets = [(200, 0)]
                self.input_offsets = [(-150, -150), (-150, -50), (-150, 50), (-150, 150)]
            elif n == 5:
                self.output_offsets = [(200, 0)]
                self.input_offsets = [(-150, -200), (-150, -100), (-150, 0), (-150, 100), (-150, 200)]
            elif n == 6:
                self.output_offsets = [(200, 0)]
                self.input_offsets = [(-150, -250), (-150, -150), (-150, -50), (-150, 50), (-150, 150), (-150, 250)]

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
            self.extra_data.append(gate.truth_table().as_output_string())

        elif isinstance(gate, SignalBooster):
            self.libname = "BUFF"
            self.short_libname = self.libname
            self.output_offsets = [(150, 0)]
            self.input_offsets = [(-150, 0)]

        elif isinstance(gate, PinInput):
            self.output_offsets = [(150, 0)]
            self.input_offsets = [(-150, 0)]
            if gate.inverting:
                t = "INV"
            else:
                t = "BUFF"
            self.short_libname = "PIN_" + t
            if gate.pullup is not None and gate.pulldown is not None:
                self.libname = t + "_PULLUP_PULLDOWN"
            elif gate.pullup is not None:
                self.libname = t + "_PULLUP"
            elif gate.pulldown is not None:
                self.libname = t + "_PULLDOWN"
            else:
                raise AssertionError("Unexpected type of PinInput, with no pullup or pulldown.")

        elif isinstance(gate, PinIO):
            self.output_offsets = [(-240, 0), (70, -190)]
            self.input_offsets = [(220, -40), (220, 70)]
            if gate.pin_input.inverting:
                self.libname = "PIN_IO_INV"
            else:
                self.libname = "PIN_IO"
            self.short_libname = self.libname

        else:
            raise AssertionError("Unsupported gate for schematic output: " + str(type(gate)))


def sch_size_transform(bounding_box):
    minx, miny, maxx, maxy = bounding_box
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


def write_sch_file(filename, drawing_bounding_box, gates):
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

        SchObject.inkscape_to_sch_transform = sch_size_transform(drawing_bounding_box)
        sch_objects = {}

        for q in gates.qs:
            sch_objects[q.name] = SchTransistor(q)

        for g in gates.pulldowns:
            sch_objects[g.name] = SchPulldown(g)

        for g in gates.pullups:
            sch_objects[g.name] = SchPullup(g)

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
            if len(g.inputs) <= 6:
                sch_objects[g.name] = SchGate(g)
            else:
                print("[{:d}-NOR not supported for schematic output; just placing its transistors.".format(
                    len(g.inputs)))
                for q in g.qs:
                    sch_objects[q.name] = SchTransistor(q)

        for g in gates.nands:
            if len(g.inputs) <= 3:
                sch_objects[g.name] = SchGate(g)
            else:
                print("[{:d}-NAND not supported for schematic output; just placing its transistors.".format(
                    len(g.inputs)))
                for q in g.qs:
                    sch_objects[q.name] = SchTransistor(q)

        for g in gates.ors:
            if len(g.inputs) <= 6:
                sch_objects[g.name] = SchGate(g)
            else:
                print("[{:d}-OR not supported for schematic output; just placing its transistors.".format(
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

        for g in gates.signal_boosters:
            sch_objects[g.name] = SchGate(g)

        for g in gates.pin_inputs:
            sch_objects[g.name] = SchGate(g)

        for g in gates.pin_ios:
            sch_objects[g.name] = SchGate(g)

        for label in gates.pnames:
            sch_objects["__LABEL__" + label.text] = SchPin(label, 0)

        for sch_object in sch_objects.values():
            sch_object.write_component(f)

        sch_objects_by_input_net = collections.defaultdict(set)
        sch_objects_by_output_net = collections.defaultdict(set)
        for o in sch_objects.values():
            for input in o.input_nets:
                sch_objects_by_input_net[input].add(o)
            for output in o.output_nets:
                sch_objects_by_output_net[output].add(o)

        for o in sch_objects.values():
            for i, output_offset in enumerate(o.output_offsets):
                output_net = o.output_nets[i]
                for input_obj in (x for x in sch_objects_by_input_net[output_net] if len(x.input_offsets) > 0):
                    for ii, input_net in enumerate(input_obj.input_nets):
                        if input_net == output_net:
                            write_wire(f, o.sch_loc, output_offset, input_obj.sch_loc, input_obj.input_offsets[ii])

        print("$EndSCHEMATC", file=f)
