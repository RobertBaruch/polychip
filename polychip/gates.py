import collections
import re
import networkx as nx
import functools
import pprint
import shapely.wkt

def is_power_net(name):
    return name.startswith('VCC') or name.startswith('VDD')

def is_ground_net(name):
    return name.startswith('VSS') or name.startswith('GND')

class Transistor(object):
    """Represents a transistor.

    For consistency, the electrode0 must alway have lower x (or lower y if x is equal) than
    electrode1 (see InkscapeFile.poly_cmp for details of this comparison).

    Args:
    Attributes:
        name (str): The name of the transistor, if found on the QNames layer, otherwise None.
        gate (int): The index into the InkscapeFile's poly_array that connects to this transistor's gate.
        gate_net (str): The name of the net the gate is connected to.
        gate_shape (shapely.geometry.Polygon): The polygon outlining the transistor's gate. 
        centroid (shapely.geometry.Point): The gate shape's centroid.
        electrode0 (int): The index into the InkscapeFile's diff_array that connects to one
            side of this transistor.
        electrode1 (int): The index into the InkscapeFile's diff_array that connects to the other
            side of this transistor.
        electrode0_net (str): The name of the net electrode 0 is connected to.
        electrode1_net (str): The name of the net electrode 1 is connected to.
    """
    def __init__(self, gate_shape, gate, electrode0, electrode1, name):
        self.gate_shape = gate_shape
        self.gate = gate
        self.electrode0 = electrode0
        self.electrode1 = electrode1
        self.name = name
        if self.gate_shape is not None:
            self.centroid = self.gate_shape.centroid
        self.gate_net = None
        self.electrode0_net = None
        self.electrode1_net = None

    def __hash__(self):
        return hash(self.name)

    def __repr__(self):
        return "Transistor({:s} @ {:f}, {:f})".format(self.name, self.centroid.x, self.centroid.y)

    def to_dict(self):
        """Converts to a dictionary, for JSON encoding."""
        return {
            "__POLYCHIP_OBJECT__": "Transistor",
            "centroid": self.centroid.wkt,
            "electrode0": self.electrode0,
            "electrode1": self.electrode1,
            "electrode0_net": self.electrode0_net,
            "electrode1_net": self.electrode1_net,
            "gate_shape": self.gate_shape.wkt,
            "gate": self.gate,
            "gate_net": self.gate_net,
            "name": self.name,
        }

    @staticmethod
    def from_dict(d):
        """Converts a dictionary to a Transistor, for JSON decoding."""
        assert d["__POLYCHIP_OBJECT__"] == "Transistor", "Transistor.from_dict wasn't given its expected dict: " + str(d)
        t = Transistor(None, None, None, None, None)
        t.centroid = shapely.wkt.loads(d["centroid"])
        t.electrode0 = d["electrode0"]
        t.electrode1 = d["electrode1"]
        t.electrode0_net = d["electrode0_net"]
        t.electrode1_net = d["electrode1_net"]
        t.gate_shape = shapely.wkt.loads(d["gate_shape"])
        t.gate = d["gate"]
        t.gate_net = d["gate_net"]
        t.name = d["name"]
        return t

    def nongrounded_electrode_net(self):
        """Returns the first electrode net not ground, or None if both are ground."""
        if not is_ground_net(self.electrode0_net):
            return self.electrode0_net
        if not is_ground_net(self.electrode1_net):
            return self.electrode1_net
        return None

    def nonvcc_electrode_net(self):
        """Returns the first electrode net not power, or None if both are power."""
        if not is_power_net(self.electrode0_net):
            return self.electrode0_net
        if not is_power_net(self.electrode1_net):
            return self.electrode1_net
        return None

    def opposite_electrode_net(self, net):
        assert net == self.electrode0_net or net == self.electrode1_net, (
            "You have to pass in the net of one of the electrodes.")
        if self.electrode0_net != net:
            return self.electrode0_net
        return self.electrode1_net

    def is_grounding(self):
        return is_ground_net(self.electrode0_net) or is_ground_net(self.electrode1_net)

    def is_powering(self):
        return is_power_net(self.electrode0_net) or is_power_net(self.electrode1_net)

    def is_electrode_connected_to(self, net):
        return self.electrode0_net == net or self.electrode1_net == net


class ParallelTransistor(Transistor):
    """Represents a "power" transistor.

    A power transistor is just a bunch of transistors whose gates are all connected to
    the same net and whose electrodes are all connected to the same nets.
    """
    def __init__(self, qs):
        # We arbitrarily pick the first transistor to represent the whole thing.
        q = next(iter(qs))
        super().__init__(q.gate_shape, q.gate, q.electrode0, q.electrode1, q.name)
        self.gate_net = q.gate_net
        self.electrode0_net = q.electrode0_net
        self.electrode1_net = q.electrode1_net
        self.qs = {q}
        self.component_qs = qs

    def num_qs(self):
        return len(self.component_qs)


class Gate(object):
    """
    To ensure pass-by-value in the arguments, all lists and sets are copied.

    Attributes:
        output_power_q (Transistor): The transistor giving the output power.
        outputs ([str]): The name of the output nets. Generally the order is significant.
        inputs ([str]): The list of names of the input nets. Generally the order is significant.
        qs ([Transistor]): The list of transistors making up the gate, NOT including
                           those of any subgates.
        subgates ([Gate]): The list of gates that make up this gate.
    """
    def __init__(self, output_power_q, outputs, inputs, qs, subgates=[]):
        self.output_power_q = output_power_q
        self.name = self.output_power_q.name
        self.outputs = list(outputs)
        self.inputs = list(inputs)
        self.qs = list(qs)
        self.subgates = list(subgates)
        for g in subgates:
            self.qs.extend(g.qs)

    def input(self):
        return only(self.inputs)

    def output(self):
        return only(self.outputs)

    def q(self):
        return only(self.qs)

    def num_qs(self):
        return (sum(q.num_qs() for q in self.qs if type(q) == ParallelTransistor) +
            sum(1 for q in self.qs if type(q) != ParallelTransistor))

    def any_input_in(self, nets):
        return any(input in nets for input in inputs)

    def replace_inputs(self, inputs):
        self.inputs = list(inputs)

    def replace_outputs(self, outputs):
        self.outputs = list(outputs)

    def as_dict(self):
        return {
            'type': type(self),
            'output_power_q': self.output_power_q.as_dict(),
            'qs':  [q.as_dict() for q in self.selection_qs],
            'outs': self.outputs,
            'ins': self.inputs,
        }

    @staticmethod
    def sort_by_name(g):
        return str(g.name)


class Lut(Gate):
    """A generalized gate with an nmos resistor at the top and a tree of transistors to
    ground. Within the tree, no electrode may connect to anything except ground, the
    nmos output net, or another in-tree transistor's electrode.
    """
    def __init__(self, nmos_resistor_q, output_net, qs):
        assert len(qs) > 1, "LUT qs for output {:s} has only {:d} qs".format(output_net, len(qs))
        super().__init__(nmos_resistor_q, [output_net], [], qs)
        logic_qs = list(qs)
        logic_qs.remove(nmos_resistor_q)
        neg_ens = {q.gate_net for q in logic_qs if q.is_grounding() and q.nongrounded_electrode_net() == output_net}
        self.neg_ens = list(neg_ens)
        self.non_neg_ens = list({q.gate_net for q in logic_qs} - neg_ens)
        self.replace_inputs(self.neg_ens + self.non_neg_ens)
        self.nor_input_qs = [q for q in logic_qs if q.is_electrode_connected_to(output_net)]
        self.graph = nx.Graph()
        for q in logic_qs:
            self.graph.add_edge(q.electrode0_net, q.electrode1_net, q=q)

    def is_nor(self):
        return len(self.non_neg_ens) == 0

    def is_nand(self):
        grounds = {n for n in self.graph if is_ground_net(n)}
        if len(grounds) > 1:
            return False
        paths = nx.all_simple_paths(self.graph, self.output(), only(grounds))
        next(paths)
        return next(paths, None) == None  # There was only one path to ground.


class PassTransistor(Gate):
    """A pass transistor has (at least) one electrode unpowered and connected to at least one gate.

    Attributes:
        output (str): The electrode net connected to the unpowered net connected to at least one gate.
    """
    def __init__(self, q, output):
        super().__init__(q, [output], [], [q])
        inputs = [q.gate_net, q.electrode0_net, q.electrode1_net]
        inputs.remove(output)
        self.replace_inputs(inputs)
        self.selecting_input = q.gate_net
        self.selected_input = only({q.electrode0_net, q.electrode1_net} - {output})


class Pulldown(Gate):
    """A resistor to ground, formed by an NMOS transistor."""
    def __init__(self, q):
        super().__init__(q, [], [q.nongrounded_electrode_net()], {q})


class Pullup(Gate):
    """A resistor to power, formed by an NMOS transistor. These are the ones that couldn't be included
    in logic gates, so are likely just pin pullups and the like."""
    def __init__(self, q):
        super().__init__(q, [], [q.nonvcc_electrode_net()], {q})


class Multiplexer(Gate):
    """
    Args:
        output (str): The output net.
        selection_qs ([PassTransistor]): The pass transistors in the mux.

    Attributes:
        selected_inputs ([str]): The list of X-inputs which get selected to be the output.
        selecting_inputs ([str]): The list of S-inputs which selected a selected_input to be the output.
    """
    def __init__(self, output, selection_qs):
        assert(len(selection_qs) >= 2)
        # We arbitrarily pick an output power q, since the multiplexer is actually unpowered,
        # but pick the alphanumerically named lowest one for stability.
        super().__init__(sorted(selection_qs, key=Gate.sort_by_name)[0].output_power_q, [output], [], [], selection_qs)
        self.selected_inputs = [q.selected_input for q in selection_qs]
        self.selecting_inputs = [q.selecting_input for q in selection_qs]
        self.inputs = list(self.selected_inputs)
        self.inputs.extend(self.selecting_inputs)

    def as_dict(self):
        d = super().as_dict()
        d.update({
            'type': 'MUX',
            'selected_inputs': self.selected_inputs,
        })
        return d


class PowerMultiplexer(Multiplexer):
    """A mux that selects only between power and ground, and not necessarily with only two inputs.

    Args:
        mux (Multiplexer): The mux selecting between power and ground.

    Attributes:
        high_inputs ([str]): The list of gate inputs which select power.
        low_inputs ([str]): The list of gate inputs which select ground.
    """
    def __init__(self, mux):
        super().__init__(mux.output(), mux.subgates)
        qs = list(mux.qs)
        self.high_inputs = [q.gate_net for q in qs if q.is_powering()]
        self.low_inputs = [q.gate_net for q in qs if q.is_grounding()]
        self.inputs = list(self.high_inputs)
        self.inputs.extend(self.low_inputs)


class NorGate(Lut):
    def __init__(self, lut):
        super().__init__(lut.output_power_q, only(lut.outputs), lut.qs)
        self.lut = lut

    def as_dict(self):
        d = super().as_dict()
        d.update({
            'type': 'NOR',
        })
        return d


class PowerNorGate(NorGate):
    def __init__(self, nor_gate, mux, output):
        super().__init__(nor_gate.lut)
        self.replace_outputs([output])
        self.qs = nor_gate.qs + mux.qs
        self.nor = nor_gate
        self.mux = mux

    def as_dict(self):
        d = super().as_dict()
        d.update({
            'type': 'Power NOR',
        })
        return d


class Nand(Lut):
    def __init__(self, lut):
        super().__init__(lut.output_power_q, only(lut.outputs), lut.qs)
        self.lut = lut

    def as_dict(self):
        d = super().as_dict()
        d.update({
            'type': 'NAND',
        })
        return d


class TristateInverter(Gate):
    def __init__(self, inverter, high_nor, low_nor, mux, noe):
        super().__init__(mux.output_power_q, mux.outputs, [inverter.input(), noe],
            [], [inverter, high_nor, low_nor, mux])
        self.inverter = inverter
        self.high_nor = high_nor
        self.low_nor = low_nor
        self.mux = mux
        self.noe = noe

    def input(self):
        return self.inverter.input()

    def as_dict(self):
        d = super().as_dict()
        d.update({
            'type': 'Tristate Buffering Inverter',
            '/oe': self.oe,
            'in': only(self.inverter.inputs),
        })
        return d


class TristateBuffer(Gate):
    def __init__(self, inverter, high_nor, low_nor, mux, noe):
        super().__init__(mux.output_power_q, mux.outputs, [inverter.input(), noe],
            [], [inverter, high_nor, low_nor, mux])
        self.inverter = inverter
        self.high_nor = high_nor
        self.low_nor = low_nor
        self.mux = mux
        self.noe = noe

    def input(self):
        return self.inverter.input()

    def as_dict(self):
        d = super().as_dict()
        d.update({
            'type': 'Tristate Buffer',
            '/oe': self.noe,
            'in': only(self.inverter.inputs),
        })
        return d


class MuxDLatch(Gate):
    """A multiplexer-based D-latch.

                 _____    +----------------- /Q
         +------|     |   |   _____
         |      | lut |---+-o|     |
         |   +-o|_____|      | lut |-----+--  Q
         |   |            +--|_____|     |
         |   |            |              |
        /SET | Y         /CLR         X0 |
           --------------------------------
           |                              |
        D -| X1           mux             |
           |______________________________|
               | S1                S0 |
               |                      |
               C                      /C

    The inputs are ordered as [D, C, /C], and the outputs are [Q, /Q].
    TODO: What about the SET/CLR inputs? Maybe we could separate out the neg_en
    used in each lut as separate luts. Then they could be represented in the
    schematic.
    """
    def __init__(self, mux, q_lut, nq_lut):
        super().__init__(q_lut.output_power_q, [q_lut.output(), nq_lut.output()], [],
            [], [mux, q_lut, nq_lut])
        self.mux = mux
        self.q_lut = q_lut
        self.nq_lut = nq_lut
        self.q_output = q_lut.output()
        self.nq_output = nq_lut.output()
        i = next(i for i, input in enumerate(mux.selected_inputs) if input == q_lut.output())
        self.nc_input = mux.selecting_inputs[i]
        self.c_input = mux.selecting_inputs[1 - i]
        self.d_input = mux.selected_inputs[1 - i]
        self.set_inputs = [input for input in nq_lut.inputs if input != mux.output()]
        self.clr_inputs = [input for input in q_lut.inputs if input != nq_lut.output()]
        self.inputs = [self.d_input, self.c_input, self.nc_input]


class SignalBooster(Gate):
    """An inverter followed by a 2-input power mux."""
    def __init__(self, mux, inv):
        super().__init__(only([q for q in mux.qs if q.is_powering()]), mux.outputs, inv.inputs,
            [], [mux, inv])
        self.mux = mux
        self.inv = inv


class PinInput(Gate):
    """An inverter followed optionally by one inverter and no other gate.

    The first inverter's input must have a pullup, pulldown, or both.
    """
    def __init__(self, inv1, inv2, pullup, pulldown):
        if inv2 is not None:
            super().__init__(inv2.output_power_q, inv2.outputs, inv1.inputs,
                [], [g for g in [inv1, inv2, pullup, pulldown] if g is not None])
        else:
            super().__init__(inv1.output_power_q, inv1.outputs, inv1.inputs,
                [], [g for g in [inv1, pullup, pulldown] if g is not None])
        self.inv1 = inv1
        self.inv2 = inv2
        self.pullup = pullup
        self.pulldown = pulldown


class PinIO(Gate):
    """A pin feeding a PinInput and fed by a tristate buffer.

    Output ordering is pin_input output, tristate_buffer output (i.e. the pin).
    Input ordering is same as in TristateBuffer.
    """
    def __init__(self, pin_input, tristate_buffer):
        super().__init__(pin_input.output_power_q, [pin_input.output(), tristate_buffer.output()],
            tristate_buffer.inputs, [], [pin_input, tristate_buffer])
        self.pin_input = pin_input
        self.tristate_buffer = tristate_buffer
        self.pin = pin_input.input()


def only(items):
    """Returns the only element in a set or list of one element."""
    assert len(items) == 1, "Oops, length of iterable in only() was {:d}.".format(len(items))
    return next(iter(items))


def set_dictionary(generator):
    """Constructs a dictionary of key:set(value) from a generator of (key, value) tuples."""
    d = collections.defaultdict(set)
    for k, v in generator:
        d[k].add(v)
    return d


class Gates(object):
    """
    Attributes:
        nets ([(netname, net)]): See args.
        qs ([Transistor]): A list of all the transistors.
        qs_by_name ({str: Transistor}): A map of transistors by name.
        qs_by_electrode_net ({str: {Transistor}}): A map of net -> transistors connected to that net
            by at least one electrode.
        qs_by_gate_net ({str: {Transistor}}): A map of net -> transistors connected to that net
            by their gate.
        grounding_qs ({Transistor}): The set of transistors with at least one electrode connected to GND.
        powered_qs ({Transistor}): The set of transistors with at least one electrode connected to VCC.
        nmos_resistor_qs ({Transistor}): The set of transistors connected as nmos resistors.

    Args:
        nets ([(netname, net)]):
            netname (str): The name of the net, or None if unnamed.
            net ({net_node}):
                net_node ((type, qname)):
                    type (Type): the transistor connection (E0, E1, or GATE).
                    qname (str): the name of the transistor
        qs ([Transistor]): A list of all the transistors.
        pnames ([Label]): A list of all the pin labels.
    """
    def __init__(self, nets, qs, pnames):
        self.nets = nets
        self.qs = set(qs)
        self.pnames = pnames
        self.qs_by_name = {q.name: q for q in qs}
        self.qs_by_electrode_net = collections.defaultdict(set)
        self.qs_by_gate_net = collections.defaultdict(set)

        for q in qs:
            self.qs_by_electrode_net[q.electrode0_net].add(q)
            self.qs_by_electrode_net[q.electrode1_net].add(q)
            self.qs_by_gate_net[q.gate_net].add(q)

        self.grounding_qs = {q for q in qs if q.is_grounding()}
        self.powered_qs = {q for q in qs if q.is_powering()}
        self.nmos_resistor_qs = {q for q in self.powered_qs if q.gate_net == q.nonvcc_electrode_net() or is_power_net(q.gate_net)}
        self.pulled_up_nets = {q.nonvcc_electrode_net() for q in self.nmos_resistor_qs}
        self.power_nets = {net for net in self.nets.keys() if is_power_net(net)}
        self.ground_nets = {net for net in self.nets.keys() if is_ground_net(net)}
        # Nets with non-Z logic values.
        self.logic_nets = self.pulled_up_nets | self.power_nets | self.ground_nets
        # Nets with potentially Z logic values.
        self.unpowered_nets = set(nets.keys()) - self.logic_nets

        self.pulldowns = set()
        self.pullups = set()
        self.pass_qs = set()
        self.luts = set()
        self.muxes = set()
        self.nors = set()
        self.nands = set()
        self.tristate_inverters = set()
        self.tristate_buffers = set()
        self.mux_d_latches = set()
        self.signal_boosters = set()
        self.pin_inputs = set()
        self.pin_ios = set()

    def all_gates(self):
        all = set()
        for gs in [self.pulldowns, self.pullups, self.pass_qs, self.luts, self.muxes, self.nors,
                self.nands, self.tristate_inverters, self.tristate_buffers, self.mux_d_latches,
                self.signal_boosters, self.pin_inputs, self.pin_ios]:
            all.update(gs)
        return all

    def gates_by_input(self):
        """Returns a set dictionary of input to gate."""
        return set_dictionary(((i, g) for g in self.all_gates() for i in g.inputs))

    def find_all_the_things(self):
        lut_strategy = 2

        self.find_pulldowns()
        self.find_power_qs()
        if lut_strategy == 2:
            self.find_luts2()
            self.find_pass_transistors2()
        else:
            self.find_pass_transistors()
            self.find_luts()
        self.find_muxes()
        self.find_nors()
        self.find_nands()
        self.find_tristate_inverters()
        self.find_tristate_buffers()
        self.find_mux_d_latches()
        self.find_pullups()
        self.find_signal_boosters()
        self.find_pin_inputs()
        self.find_pin_ios()

    def remove_q(self, q):
        # if q in self.grounding_qs:
        #     self.grounding_qs.remove(q)
        # elif q in self.powered_qs:
        #     self.powered_qs.remove(q)
        # self.qs_by_electrode_net[q.electrode0_net].remove(q)
        # self.qs_by_electrode_net[q.electrode1_net].remove(q)
        # self.qs_by_gate_net[q.gate_net].remove(q)
        # if q in self.nmos_resistor_qs:
        #     self.nmos_resistor_qs.remove(q)
        self.qs.remove(q)

    def add_q(self, q):
        self.qs_by_electrode_net[q.electrode0_net].add(q)
        self.qs_by_electrode_net[q.electrode1_net].add(q)
        self.qs_by_gate_net[q.gate_net].add(q)
        self.qs.add(q)
        if q.is_grounding():
            self.grounding_qs.add(q)
        elif q.is_powering():
            self.powered_qs.add(q)

    def electrode_qs_in(self, net):
        return self.qs_by_electrode_net[net]

    def gate_qs_in(self, net):
        return self.qs_by_gate_net[net]

    def all_nets_iter(self):
        return (net for net in self.nets.keys())

    def nets_with_n_electrodes_iter(self, n, net_iter):
        return (net for net in net_iter if len(self.electrode_qs_in(net)) == n)

    def nets_with_n_gates_iter(self, n, net_iter):
        return (net for net in net_iter if len(self.gate_qs_in(net)) == n)
        
    def nets_with_n_grounding_qs_iter(self, n, net_iter):
        return (net for net in net_iter if len(self.grounding_qs & self.electrode_qs_in(net)) == n)

    def nets_with_n_powered_qs_iter(self, n, net_iter):
        return (net for net in net_iter if len(self.powered_qs & self.electrode_qs_in(net)) == n)

    def nets_powered_by_nmos_resistor_iter(self, net_iter):
        return (net for net in net_iter if len(self.nmos_resistor_qs & self.gate_qs_in(net)) == 1)

    def unpowered_net_iter(self, net_iter):
        return (net for net in net_iter if net not in self.logic_nets)

    def invs(self):
        return [nor for nor in self.nors if len(nor.inputs) == 1]

    def find_power_qs(self):
        powered_parallel_qs = []
        grounding_parallel_qs = []

        # Start with the ones connected to power and ground, since they are most likely.
        # This is O(N).

        powered_qs_by_electrode_net = set_dictionary((q.nonvcc_electrode_net(), q) for q in self.powered_qs)
        for net, qs in powered_qs_by_electrode_net.items():
            if len(qs) < 2:
                continue
            those_qs_by_gate_net = set_dictionary((q.gate_net, q) for q in qs)
            for gate_net, gqs in those_qs_by_gate_net.items():
                if len(gqs) >= 2:
                    powered_parallel_qs.append(ParallelTransistor(gqs))

        grounding_qs_by_electrode_net = set_dictionary((q.nongrounded_electrode_net(), q) for q in self.grounding_qs)
        for net, qs in grounding_qs_by_electrode_net.items():
            if len(qs) < 2:
                continue
            those_qs_by_gate_net = set_dictionary((q.gate_net, q) for q in qs)
            for gate_net, gqs in those_qs_by_gate_net.items():
                if len(gqs) >= 2:
                    grounding_parallel_qs.append(ParallelTransistor(gqs))

        # The rest we ignore for now.

        print("Found {:d} powered parallel transistors (total {:d} qs)".format(
            len(powered_parallel_qs), sum(q.num_qs() for q in powered_parallel_qs)))
        print("Found {:d} grounding parallel transistors (total {:d} qs)".format(
            len(grounding_parallel_qs), sum(q.num_qs() for q in grounding_parallel_qs)))

        # Now we fix up all the maps and sets to replace each transistor found with the parallel version.
        for q in powered_parallel_qs:
            for qq in q.component_qs:
                self.remove_q(qq)
            self.add_q(q)

        for q in grounding_parallel_qs:
            for qq in q.component_qs:
                self.remove_q(qq)
            self.add_q(q)

    def find_pulldowns(self):
        self.pulldowns = {Pulldown(q) for q in self.grounding_qs if is_ground_net(q.gate_net)}
        for g in self.pulldowns:
            self.remove_q(g.q())

    def find_pullups(self):
        self.pullups = {Pullup(q) for q in self.qs & self.nmos_resistor_qs}
        for g in self.pullups:
            self.remove_q(g.q())

    def find_luts2(self):
        G = nx.Graph()
        for i, q in enumerate(self.qs - self.nmos_resistor_qs):
            if not q.is_powering():
                if q.is_grounding():
                    G.add_edge(q.nongrounded_electrode_net(), "GND___." + str(i), q=q)
                else:
                    G.add_edge(q.electrode0_net, q.electrode1_net, q=q)
            if q.gate_net not in self.pulled_up_nets:
                G.add_edge(q.gate_net, "__GATE__", q=q)

        # No gates anywhere? Then just return.
        if "__GATE__" not in G:
            return

        # find all simple paths from a pulled-up net to a gate.
        pass_paths = []
        for pullup_q, net in ((q, q.nonvcc_electrode_net()) for q in self.nmos_resistor_qs):
            if net not in G:
                continue
            pass_paths.extend(list(nx.all_simple_paths(G, net, "__GATE__")))
        print("{:d} paths lead from pullups to a gate.".format(len(pass_paths)))
        for path in map(nx.utils.pairwise, pass_paths):
            for edge in (edge for edge in path if G.has_edge(edge[0], edge[1])):
                G.remove_edge(edge[0], edge[1])

        for net in (net for net in nx.connected_components(G) if len(net & self.pulled_up_nets) == 1):
            subgraph = G.subgraph(net).copy()
            output_net = only(net & self.pulled_up_nets)
            nmos_resistor_qs = self.qs_by_electrode_net[output_net] & self.nmos_resistor_qs
            if len(nmos_resistor_qs) != 1:
                print("Error: nonunique nmos resistor Q pulling up net {:s}. Qs are {:s}".format(
                    output_net, str(["{:s} @ {:s}".format(q.name, str(q.centroid)) for q in nmos_resistor_qs])))
                continue
            nmos_resistor_q = only(nmos_resistor_qs)
            grounds = [n for n in net if is_ground_net(n)]
            if len(grounds) == 0:
                print("Error: pulled up net {:s} (by Q {:s} @ {:s}) has no ground path".format(
                    output_net, nmos_resistor_q.name, str(nmos_resistor_q.centroid)))
                continue
            qs = {q for u, v, q in subgraph.edges.data('q')} | {nmos_resistor_q}
            if len(qs) < 2:
                continue
            lut = Lut(nmos_resistor_q, output_net, qs)
            self.luts.add(lut)

        print("Identified {:d} luts using find_luts2".format(len(self.luts)))
        for g in self.luts:
            for q in g.qs:
                self.remove_q(q)

    def find_pass_transistors2(self):
        for q in self.qs:
            for e in [q.electrode0_net, q.electrode1_net]:
                if e not in self.logic_nets:
                    self.pass_qs.add(PassTransistor(q, e))
                    break

        print("Found {:d} pass transistors.".format(len(self.pass_qs)))

        for g in self.pass_qs:
            self.remove_q(g.q())

    # TODO: How about pin muxes? Those are not connected to a gate.
    def find_pass_transistors(self):
        """One electrode must be unpowered and connected to at least one gate."""
        gate_nets = {q.gate_net for q in self.qs}

        for q in self.qs:
            for e in [q.electrode0_net, q.electrode1_net]:
                if e not in self.logic_nets and e in gate_nets:
                    self.pass_qs.add(PassTransistor(q, e))
                    break

        print("Found {:d} pass transistors.".format(len(self.pass_qs)))

        for g in self.pass_qs:
            self.remove_q(g.q())

    def find_luts(self):
        # Create a graph from the transistors where every ground node is separate, but any
        # transistor gate that is not part of a pullup resistor is a single node called __GATE__.
        # We also exclude pullups from the transistors in the graph.
        G = nx.Graph()
        tmp = 0
        for q in self.qs - self.nmos_resistor_qs:
            if not q.is_powering():
                if q.is_grounding():
                    G.add_edge(q.nongrounded_electrode_net(), "GND___." + str(tmp), q=q)
                    tmp += 1
                else:
                    G.add_edge(q.electrode0_net, q.electrode1_net, q=q)
            if q.gate_net not in self.pulled_up_nets:
                G.add_edge(q.gate_net, "__GATE__")

        # We should now be able to ensure that starting from a pulled-up net, no
        # path leads to __GATE__, and no paths lead to another pulled-up net. If
        # true, then we've found a LUT. So basically we've got a self-contained set of nodes.
        #
        # If a path does lead to another pulled-up net, then likely we're passing through
        # a pass transistor somewhere.

        # net ({(Type, name)}): A connected component (the set of nodes connected to each other)
        for net in (net for net in nx.connected_components(G) if len(net & self.pulled_up_nets) == 1 and "__GATE__" not in net):
            subgraph = G.subgraph(net).copy()
            output_net = only(net & self.pulled_up_nets)
            nmos_resistor_q = only(self.qs_by_electrode_net[output_net] & self.nmos_resistor_qs)
            qs = {q for u, v, q in subgraph.edges.data('q')} | {nmos_resistor_q}
            lut = Lut(nmos_resistor_q, output_net, qs)
            self.luts.add(lut)

        print("Identified {:d} luts using find_luts".format(len(self.luts)))
        for g in self.luts:
            for q in g.qs:
                self.remove_q(q)

    def find_muxes(self):
        pass_qs_by_output = set_dictionary(((q.output(), q) for q in self.pass_qs))
        # Hopefully no value set overlaps.

        muxes = set()
        for output, qs in pass_qs_by_output.items():
            if len(qs) < 2:
                continue
            muxes.add(Multiplexer(output, list(qs)))

        # Upgrade muxes to power muxes. A power mux selects between power and ground.
        for mux in muxes:
            if (any(q.is_powering() for q in mux.qs) and 
                any(q.is_grounding() for q in mux.qs) and
                all(q.is_powering() or q.is_grounding() for q in mux.qs)):
                self.muxes.add(PowerMultiplexer(mux))
            else:
                self.muxes.add(mux)                

        for mux in self.muxes:
            for pass_q in mux.subgates:
                self.pass_qs.remove(pass_q)

        return self.muxes

    def find_nors(self):
        """Finds NOR gates from LUTs."""
        self.nors = {NorGate(lut) for lut in self.luts if lut.is_nor()}

        for nor in self.nors:
            self.luts.remove(nor.lut)

        # See if any are high-drive. A high-drive NOR gate is a NOR gate whose output
        # feeds exactly two powered transistors (one is the gate's own nmos resistor), 
        # and the other transisor's electrode net is connected
        # to exactly n grounding transistors, whose gates are connected to the gates of
        # the NOR's inputs.

        self.nors = {self.maybe_upgrade_to_power_nor(nor) for nor in self.nors}

    def maybe_upgrade_to_power_nor(self, nor):
        power_muxes = (mux for mux in self.muxes if type(mux) is PowerMultiplexer)
        for mux in power_muxes:
            # Are all the power selectors set to the nor gate's output?
            if set(mux.high_inputs) != {nor.output()}:
                continue

            # Are all the ground selectors set to the nor gate's inputs, and are
            # all inputs represented?
            if set(mux.low_inputs) != set(nor.inputs):
                continue
            nor = PowerNorGate(nor, mux, mux.output())
            break

        if type(nor) == PowerNorGate:
            self.muxes.remove(nor.mux)
        return nor

    def find_nands(self):
        """Finds NAND gates from LUTs."""
        self.nands = {Nand(lut) for lut in self.luts if lut.is_nand()}

        for nand in self.nands:
            self.luts.remove(nand.lut)

    def find_tristate_inverters(self):
        """Finds tristate inverters. This is O(N).

                              _____        VCC
        IN --+-| inv |o------|     |       _|_
             |               | nor |o-----|   |
             |           +---|_____|      | m |
        /OE -------------+    _____       | u |---- OUT
             |           +---|     |      | x |
             |               | nor |o-----|___|
             +---------------|_____|        |
                                           GND
        """

        # Get just those components that make a tristate inverter.
        nor2s = {n for n in self.nors if len(n.inputs) == 2}
        invs = self.invs()
        muxes = {g for g in self.muxes if type(g) == PowerMultiplexer and len(g.selected_inputs) == 2}

        # Map the inverters and nors
        invs_by_output = {inv.output(): inv for inv in invs}
        invs_by_input = set_dictionary((inv.input(), inv) for inv in invs)

        nor2_by_output = {nor.output(): nor for nor in nor2s}
        nor2s_by_input = set_dictionary((input, nor) 
            for nor in nor2s 
            for input in nor.inputs)

        # Go through the muxes fed by pairs of nors that also have one common input (/oe).
        for mux in muxes:
            # The mux must be fed by nor2s.
            if not all(input in nor2_by_output for input in mux.selecting_inputs):
                continue

            # The nor2s must have one common input (/oe).
            high_nor = nor2_by_output[only(mux.high_inputs)]
            low_nor = nor2_by_output[only(mux.low_inputs)]
            high_nor_inputs = set(high_nor.inputs)
            low_nor_inputs = set(low_nor.inputs)
            common_inputs = high_nor_inputs & low_nor_inputs
            if len(common_inputs) != 1:
                continue

            # The low nor's other input must be the output of an inverter.
            low_nor_input = only(low_nor_inputs - common_inputs)
            inv = invs_by_output.get(low_nor_input)
            if inv is None:
                continue

            # The inverter's input must also be the high nor's other input.
            if inv.input() != only(high_nor_inputs - common_inputs):
                continue

            # TODO: make sure the thing is self-contained: the inverter's output
            # feeds no other input, and the nors' outputs feed nothing other than the
            # mux. This requires an output -> gate/q map.

            noe = only(common_inputs)
            self.tristate_inverters.add(TristateInverter(inv, high_nor, low_nor, mux, noe))

        for g in self.tristate_inverters:
            self.nors.remove(g.inverter)
            self.nors.remove(g.high_nor)
            self.nors.remove(g.low_nor)
            self.muxes.remove(g.mux)

    def find_tristate_buffers(self):
        """Finds tristate buffers. This is O(N).

                              _____        VCC
        IN --+---------------|     |       _|_
             |               | nor |o-----|   |
             |           +---|_____|      | m |
        /OE -------------+    _____       | u |---- OUT
             |           +---|     |      | x |
             |               | nor |o-----|___|
             +-| inv |o------|_____|        |
                                           GND

        Basically this is the same logic as a tristate inverter except the inverter is
        feeding the low nor rather than the high nor.
        """

        # Get just those components that make a tristate buffer.
        nor2s = {n for n in self.nors if len(n.inputs) == 2}
        invs = self.invs()
        muxes = {g for g in self.muxes if type(g) == PowerMultiplexer and len(g.selected_inputs) == 2}

        # Map the inverters and nors
        invs_by_output = {inv.output(): inv for inv in invs}
        invs_by_input = set_dictionary((inv.input(), inv) for inv in invs)

        nor2_by_output = {nor.output(): nor for nor in nor2s}
        nor2s_by_input = set_dictionary((input, nor) 
            for nor in nor2s 
            for input in nor.inputs)

        # Go through the muxes fed by pairs of nors that also have one common input (/oe).
        for mux in muxes:
            # The mux must be fed by nor2s.
            if not all(input in nor2_by_output for input in mux.selecting_inputs):
                continue

            # The nor2s must have one common input (/oe).
            high_nor = nor2_by_output[only(mux.high_inputs)]
            low_nor = nor2_by_output[only(mux.low_inputs)]
            high_nor_inputs = set(high_nor.inputs)
            low_nor_inputs = set(low_nor.inputs)
            common_inputs = high_nor_inputs & low_nor_inputs
            if len(common_inputs) != 1:
                continue

            # The high nor's other input must be the output of an inverter.
            high_nor_input = only(high_nor_inputs - common_inputs)
            inv = invs_by_output.get(high_nor_input)
            if inv is None:
                continue

            # The inverter's input must also be the low nor's other input.
            if inv.input() != only(low_nor_inputs - common_inputs):
                continue

            noe = only(common_inputs)
            self.tristate_buffers.add(TristateBuffer(inv, high_nor, low_nor, mux, noe))

        for g in self.tristate_buffers:
            self.nors.remove(g.inverter)
            self.nors.remove(g.high_nor)
            self.nors.remove(g.low_nor)
            self.muxes.remove(g.mux)

    def find_mux_d_latches(self):
        """Finds multiplexer-based D-latches.

                 _____    +----------------- /Q
         +------|     |   |   _____
         |      | nor |o--+--|     |
         |   +--|_____|      | nor |o----+--  Q
         |   |            +--|_____|     |
         |   |            |              |
        SET  | Y         CLR          X0 |
           --------------------------------
           |                              |
        D -| X1           mux             |
           |______________________________|
               | S1                S0 |
               |                      |
               C                      /C

        """
        # Get just those muxes that go in the gate.
        muxes = {g for g in self.muxes if type(g) != PowerMultiplexer and len(g.selected_inputs) == 2}

        # for mux in muxes:
        #     q_nor = next((nor for nor in self.nors if any(mux_input == nor.output() for mux_input in mux.selected_inputs)), None)
        #     if q_nor is None:
        #         continue
        #     nq_nor_candidates = (nor for nor in self.nors if any(nor_input == mux.output() for nor_input in nor.inputs))
        #     nq_nor_candidates = [nor for nor in nq_nor_candidates if any(qnor_input == nor.output() for qnor_input in q_nor.inputs)]
        #     if len(nq_nor_candidates) != 1:
        #         continue
        #     self.mux_d_latches.add(MuxDLatch(mux, q_nor, only(nq_nor_candidates)))

        # for g in self.mux_d_latches:
        #     self.nors.remove(g.q_nor)
        #     self.nors.remove(g.nq_nor)
        #     self.muxes.remove(g.mux)

        luts = [lut for lut in self.luts if len(lut.neg_ens) > 0]
        luts.extend(self.nors)
        for mux in muxes:
            q_luts = (lut for lut in luts if any(mux_input == lut.output() for mux_input in mux.selected_inputs))
            for q_lut in q_luts:
                nq_lut_candidates = (lut for lut in luts if any(neg_en == mux.output() for neg_en in lut.neg_ens))
                nq_lut_candidates = [lut for lut in nq_lut_candidates if any(neg_en == lut.output() for neg_en in q_lut.neg_ens)]
                if len(nq_lut_candidates) != 1:
                    continue
                self.mux_d_latches.add(MuxDLatch(mux, q_lut, only(nq_lut_candidates)))
                continue

        for g in self.mux_d_latches:
            if type(g.q_lut) == NorGate:
                self.nors.remove(g.q_lut)
            else:
                self.luts.remove(g.q_lut)
            if type(g.nq_lut) == NorGate:
                self.nors.remove(g.nq_lut)
            else:
                self.luts.remove(g.nq_lut)
            self.muxes.remove(g.mux)


    def find_signal_boosters(self):
        """Finds SignalBooster instances."""
        # Get only 2-input PowerMultiplexers
        muxes = [mux for mux in self.muxes if type(mux) == PowerMultiplexer and len(mux.selecting_inputs) == 2]

        muxes_by_pos_input = {only(mux.high_inputs): mux for mux in muxes}

        # Find inverters whose output connects to the + selecting input
        invs = [inv for inv in self.invs() if inv.input() in muxes_by_pos_input]

        gates_by_input = self.gates_by_input()

        # Keep only inverters where the output goes only to the mux
        invs = [inv for inv in invs if len(gates_by_input[inv.output()]) == 1]

        # For each inverter, if its output goes to the - selecting input, we have a signal booster.
        for inv in invs:
            mux = muxes_by_pos_input[inv.input()]
            if inv.output() == only(mux.low_inputs):
                self.signal_boosters.add(SignalBooster(mux, inv))

        for g in self.signal_boosters:
            self.nors.remove(g.inv)
            self.muxes.remove(g.mux)

    def find_pin_inputs(self):
        """Finds PinInput instances."""
        # Get only inverters whose input connects to a pin.
        pnames = {label.text for label in self.pnames}
        invs = [inv for inv in self.invs() if inv.input() in pnames]

        # Eliminate those first inverters without pullups or pulldowns.
        pullups_by_net = {p.input(): p for p in self.pullups}
        pulldowns_by_net = {p.input(): p for p in self.pulldowns}
        invs = [inv for inv in invs if inv.input() in pullups_by_net or inv.input() in pulldowns_by_net]

        # At this point we may have a pin inverter or a pin buffer. There's one last check to do.
        invs_by_input = {inv.input(): inv for inv in self.invs()}
        gates_by_input = self.gates_by_input()

        for inv in invs:
            pullup = pullups_by_net.get(inv.input())
            pulldown = pulldowns_by_net.get(inv.input())

            # Ensure that the pin feeds only the inverter and the optional pullup and pulldown,
            # i.e. it feeds no "foreign" gates.
            fed_gates = set(gates_by_input[inv.input()]) - {x for x in [inv, pullup, pulldown] if x is not None}
            if len(fed_gates) > 0:
                continue

            # If the inverter feeds another inverter and nothing else, then it's a pin buffer.
            # Otherwise it's a pin inverter.
            inv2 = None
            if inv.output() in invs_by_input and len(gates_by_input[inv.output()]) == 1:
                inv2 = invs_by_input[inv.output()]
            g = PinInput(inv, inv2, pullup, pulldown)
            self.pin_inputs.add(g)

        for g in self.pin_inputs:
            if g.pullup is not None:
                self.pullups.remove(g.pullup)
            if g.pulldown is not None:
                self.pulldowns.remove(g.pulldown)
            self.nors.remove(g.inv1)
            if g.inv2 is not None:
                self.nors.remove(g.inv2)

    def find_pin_ios(self):
        """Finds PinIO instances.

        If a pin feeds a PinInput and is fed by a TristateBuffer, we can coalesce them to a PinIO.
        """
        tristate_buffers_by_output = {buff.output(): buff for buff in self.tristate_buffers}
        for pin_input in self.pin_inputs:
            buff = tristate_buffers_by_output.get(pin_input.input())
            if buff is not None:
                self.pin_ios.add(PinIO(pin_input, buff))

        for g in self.pin_ios:
            self.pin_inputs.remove(g.pin_input)
            self.tristate_buffers.remove(g.tristate_buffer)
