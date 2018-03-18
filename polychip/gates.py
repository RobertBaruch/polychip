import collections
import re
import networkx as nx
import functools
import pprint

def is_power_name(name):
    return name.startswith('VCC') or name.startswith('VDD')

def is_ground_name(name):
    return name.startswith('VSS') or name.startswith('GND')

class Transistor(object):
    """Represents a transistor.

    For consistency, the electrode0 must alway have lower x (or lower y if x is equal) than
    electrode1 (see InkscapeFile.poly_cmp for details of this comparison).

    Args:
    Attributes:
        gate_shape (shapely.geometry.Polygon): The polygon outlining the transistor's gate. 
        gate (int): The index into the InkscapeFile's poly_array that connects to this transistor's gate.
        electrode0 (int): The index into the InkscapeFile's diff_array that connects to one
            side of this transistor.
        electrode1 (int): The index into the InkscapeFile's diff_array that connects to the other
            side of this transistor.
        name (str): The name of the transistor, if found on the QNames layer, otherwise None.
        gate_net (str): The name of the net the gate is connected to.
        electrode0_net (str): The name of the net electrode 0 is connected to.
        electrode1_net (str): The name of the net electrode 1 is connected to.
    """
    def __init__(self, gate_shape, gate, electrode0, electrode1, name):
        self.gate_shape = gate_shape
        self.gate = gate
        self.electrode0 = electrode0
        self.electrode1 = electrode1
        self.name = name
        self.centroid = self.gate_shape.centroid
        self.gate_net = None
        self.electrode0_net = None
        self.electrode1_net = None

    def __hash__(self):
        return hash(self.name)

    def __repr__(self):
        return "Transistor({:s} @ {:f}, {:f})".format(self.name, self.centroid.x, self.centroid.y)

    def as_dict(self):
        return {
            'name': self.name,
            'gate': {
                'x': self.centroid.x,
                'y': self.centroid.y,
                'net': self.gate_net
            },
            'e0_net': self.electrode0_net,
            'e1_net': self.electrode1_net
        }

    def nongrounded_electrode_net(self):
        """Returns the first electrode net not ground, or None if both are ground."""
        if not is_ground_name(self.electrode0_net):
            return self.electrode0_net
        if not is_ground_name(self.electrode1_net):
            return self.electrode1_net
        return None

    def nonvcc_electrode_net(self):
        """Returns the first electrode net not power, or None if both are power."""
        if not is_power_name(self.electrode0_net):
            return self.electrode0_net
        if not is_power_name(self.electrode1_net):
            return self.electrode1_net
        return None

    def opposite_electrode_net(self, net):
        assert net == self.electrode0_net or net == self.electrode1_net, (
            "You have to pass in the net of one of the electrodes.")
        if self.electrode0_net != net:
            return self.electrode0_net
        return self.electrode1_net

    def is_grounding(self):
        return is_ground_name(self.electrode0_net) or is_ground_name(self.electrode1_net)

    def is_powering(self):
        return is_power_name(self.electrode0_net) or is_power_name(self.electrode1_net)


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
    Attributes:
        output_power_q (Transistor): The transistor giving the output power.
        output (str): The name of the output net.
        inputs ([str]): The list of names of the input nets. Generally the order is significant.
        qs ({Transistor}): The set of transistors making up the gate.
    """
    def __init__(self, output_power_q, output, inputs, qs):
        self.output_power_q = output_power_q
        self.output = output
        self.inputs = inputs
        self.qs = set(qs)

    def input(self):
        return only(self.inputs)

    def num_qs(self):
        return (sum(q.num_qs() for q in self.qs if type(q) == ParallelTransistor) +
            sum(1 for q in self.qs if type(q) != ParallelTransistor))

    def any_input_in(self, nets):
        return any(input in nets for input in inputs)

    def as_dict(self):
        return {
            'type': type(self),
            'output_power_q': self.output_power_q.as_dict(),
            'qs':  [q.as_dict() for q in self.selection_qs],
            'out': self.output,
            'ins': self.inputs,
        }


class Multiplexer(Gate):
    """
    Attributes:
        selection_qs ([Transistor]): The list of selecting transistors.
    """
    def __init__(self, output, selection_qs):
        assert(len(selection_qs) >= 2)
        # We arbitrarily pick an output power q, since the multiplexer is actually unpowered
        super().__init__(next(iter(selection_qs)), output, [q.gate_net for q in selection_qs],
            selection_qs)
        self.selected_inputs = [q.opposite_electrode_net(output) for q in selection_qs]

    def as_dict(self):
        d = super().as_dict()
        d.update({
            'type': 'MUX',
            'selected_inputs': self.selected_inputs,
        })
        return d


class PowerMultiplexer(Multiplexer):
    """A mux that selects only between power and ground, and not necessary with only two inputs.
    """
    def __init__(self, mux):
        print("power mux detected")
        super().__init__(mux.output, mux.qs)
        qs = list(mux.qs)
        self.high_inputs = [q.gate_net for q in qs if q.is_powering()]
        self.low_inputs = [q.gate_net for q in qs if q.is_grounding()]


class NorGate(Gate):
    def __init__(self, nmos_resistor, grounding_qs, output, inputs):
        super().__init__(nmos_resistor, output, inputs, set(grounding_qs) | {nmos_resistor})
        self.nmos_resistor = nmos_resistor
        self.grounding_qs = grounding_qs

    def as_dict(self):
        d = super().as_dict()
        d.update({
            'type': 'NOR',
            'grounding_qs': [q.as_dict() for q in self.grounding_qs],
        })
        return d

    @staticmethod
    def from_net(net, gates):
        nmos_resistor = (gates.electrode_qs_in(net) & gates.nmos_resistor_qs).pop()
        grounding_qs = list(gates.electrode_qs_in(net) - {nmos_resistor})
        output = net
        inputs = [q.gate_net for q in grounding_qs]
        return NorGate(nmos_resistor, grounding_qs, output, inputs)


class PowerNorGate(Gate):
    def __init__(self, nor_gate, mux, output):
        super().__init__(nor_gate.nmos_resistor, output, nor_gate.inputs, nor_gate.qs | mux.qs)
        self.nor = nor_gate
        self.mux = mux

    def as_dict(self):
        d = super().as_dict()
        d.update({
            'type': 'Power NOR',
        })
        return d


class TristateInverter(Gate):
    def __init__(self, inverter, high_nor, low_nor, mux, noe):
        super().__init__(mux.output_power_q, mux.output, [inverter.input(), noe],
            inverter.qs | high_nor.qs | low_nor.qs | mux.qs)
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
        super().__init__(mux.output_power_q, mux.output, [inverter.input(), noe],
            inverter.qs | high_nor.qs | low_nor.qs | mux.qs)
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
            '/oe': self.oe,
            'in': only(self.inverter.inputs),
        })
        return d


def only(items):
    """Returns the only element in a set or list of one element."""
    assert(len(items) == 1)
    return next(iter(items))


def set_dictionary(generator):
    """Constructs a dictionary of key:set."""
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
    """
    def __init__(self, nets, qs):
        self.nets = nets
        self.qs = set(qs)
        self.qs_by_name = {q.name: q for q in qs}
        self.qs_by_electrode_net = collections.defaultdict(set)
        self.qs_by_gate_net = collections.defaultdict(set)

        for q in qs:
            self.qs_by_electrode_net[q.electrode0_net].add(q)
            self.qs_by_electrode_net[q.electrode1_net].add(q)
            self.qs_by_gate_net[q.gate_net].add(q)

        self.grounding_qs = {q for q in qs if q.is_grounding()}
        self.powered_qs = {q for q in qs if q.is_powering()}
        self.nmos_resistor_qs = {q for q in self.nmos_resistor_iter()}
        self.pulled_up_nets = {q.nonvcc_electrode_net() for q in self.nmos_resistor_qs}
        self.power_nets = {net for net in self.nets.keys() if is_power_name(net)}
        self.ground_nets = {net for net in self.nets.keys() if is_ground_name(net)}
        # Nets with definitive logic values.
        self.logic_nets = self.pulled_up_nets | self.power_nets | self.ground_nets

        self.muxes = set()
        self.nors = set()
        self.tristate_inverters = set()
        self.tristate_buffers = set()

    def find_all_the_things(self):
        self.find_power_qs()
        self.find_muxes()
        for i in range(1, 10):
            self.nmos_nor(i)
        self.find_tristate_inverters()
        self.find_tristate_buffers()

    def remove_q(self, q):
        if q in self.grounding_qs:
            self.grounding_qs.remove(q)
        elif q in self.powered_qs:
            self.powered_qs.remove(q)
        self.qs_by_electrode_net[q.electrode0_net].remove(q)
        self.qs_by_electrode_net[q.electrode1_net].remove(q)
        self.qs_by_gate_net[q.gate_net].remove(q)
        if q in self.nmos_resistor_qs:
            self.nmos_resistor_qs.remove(q)
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

    def nmos_resistor_iter(self):
        """Generator for finding nmos resistors.

        An nmos resistor is one where one electrode is connected to the VCC signal, and its other
        electrode is connected to its own gate.

        This algorithm is linear in the number of VCC-connected transistors.

        Yields:
            Transistor: An nmos-connected transistor.
        """
        print("{:d} candidates for nmos resistors".format(len(self.powered_qs)))
        return (q for q in self.powered_qs if q.gate_net == q.nonvcc_electrode_net())

    def find_muxes(self):
        candidate_net_iter = self.all_nets_iter()
        candidate_net_iter = self.unpowered_net_iter(candidate_net_iter)

        muxes = set()
        for net in candidate_net_iter:
            selection_qs = self.electrode_qs_in(net)
            if len(selection_qs) < 2:
                continue
            opposite_electrode_nets = {q.opposite_electrode_net(net) for q in selection_qs}
            if all(n in self.logic_nets for n in opposite_electrode_nets):
                muxes.add(Multiplexer(net, selection_qs))

        for mux in muxes:
            if all(q.is_powering() or q.is_grounding() for q in mux.qs):
                self.muxes.add(PowerMultiplexer(mux))
            else:
                self.muxes.add(mux)                

        for mux in self.muxes:
            for q in mux.qs:
                self.remove_q(q)

        return self.muxes

    def nmos_nor(self, n):
        """Generator for finding nmos n-input nor gates (number of transistors: n+1).

        This algorithm is O(N) in the number of transistors.

        Args:
            n: The number of inputs to find.
        Yields:
            (Transistor, {Transistor}): A pair where the first transistor is the nmos
                resistor, and the set is the set of grounding transistors comprising
                the NOR gate.
        """
        candidate_net_iter = self.all_nets_iter()
        candidate_net_iter = self.nets_with_n_electrodes_iter(n + 1, candidate_net_iter)
        candidate_net_iter = self.nets_with_n_grounding_qs_iter(n, candidate_net_iter)
        candidate_net_iter = self.nets_powered_by_nmos_resistor_iter(candidate_net_iter)

        nors = {NorGate.from_net(net, self) for net in candidate_net_iter}

        for nor in nors:
            for q in nor.qs:
                self.remove_q(q)

        # See if any are high-drive. A high-drive NOR gate is a NOR gate whose output
        # feeds exactly two powered transistors (one is the gate's own nmos resistor), 
        # and the other transisor's electrode net is connected
        # to exactly n grounding transistors, whose gates are connected to the gates of
        # the NOR's inputs.

        nors = {self.maybe_upgrade_to_power_nor(nor) for nor in nors}
        self.nors |= nors
        return list(nors)

    def maybe_upgrade_to_power_nor(self, nor_gate):
        power_muxes = (mux for mux in self.muxes if type(mux) is PowerMultiplexer)
        for mux in power_muxes:
            # Are all the power selectors set to the nor gate's output?
            if set(mux.high_inputs) != {nor_gate.output}:
                continue

            # Are all the ground selectors set to the nor gate's inputs, and are
            # all inputs represented?
            if set(mux.low_inputs) != set(nor_gate.inputs):
                continue

            print("Power NOR {:d} identified at {:s}".format(len(nor_gate.inputs), str(mux.output_power_q.centroid)))
            nor_gate = PowerNorGate(nor_gate, mux, mux.output)
            break

        if type(nor_gate) == PowerNorGate:
            self.muxes.remove(nor_gate.mux)
        return nor_gate

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
        invs = {n for n in self.nors if len(n.inputs) == 1}
        muxes = {g for g in self.muxes if type(g) == PowerMultiplexer and len(g.selected_inputs) == 2}

        # Map the inverters and nors
        invs_by_output = {inv.output: inv for inv in invs}
        invs_by_input = set_dictionary((inv.input(), inv) for inv in invs)

        nor2_by_output = {nor.output: nor for nor in nor2s}
        nor2s_by_input = set_dictionary((input, nor) 
            for nor in nor2s 
            for input in nor.inputs)

        # Go through the muxes fed by pairs of nors that also have one common input (/oe).
        for mux in muxes:
            # The mux must be fed by nor2s.
            if not all(input in nor2_by_output for input in mux.inputs):
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
        invs = {n for n in self.nors if len(n.inputs) == 1}
        muxes = {g for g in self.muxes if type(g) == PowerMultiplexer and len(g.selected_inputs) == 2}

        # Map the inverters and nors
        invs_by_output = {inv.output: inv for inv in invs}
        invs_by_input = set_dictionary((inv.input(), inv) for inv in invs)

        nor2_by_output = {nor.output: nor for nor in nor2s}
        nor2s_by_input = set_dictionary((input, nor) 
            for nor in nor2s 
            for input in nor.inputs)

        # Go through the muxes fed by pairs of nors that also have one common input (/oe).
        for mux in muxes:
            # The mux must be fed by nor2s.
            if not all(input in nor2_by_output for input in mux.inputs):
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
            self.tristate_buffers.add(TristateInverter(inv, high_nor, low_nor, mux, noe))

        for g in self.tristate_buffers:
            self.nors.remove(g.inverter)
            self.nors.remove(g.high_nor)
            self.nors.remove(g.low_nor)
            self.muxes.remove(g.mux)
