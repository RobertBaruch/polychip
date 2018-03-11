import collections
import re
import networkx as nx
import functools
import pprint

class NorGate(object):
    def __init__(self, nmos_resistor, grounding_qs, output, inputs):
        self.nmos_resistor = nmos_resistor
        self.grounding_qs = grounding_qs
        self.output = output
        self.inputs = inputs

    def __repr__(self):
        return "NorGate({:d}: output net {:s}, with driving {:s} and grounding {:s})".format(
            len(self.grounding_qs), self.output, str(self.nmos_resistor), str(self.grounding_qs))

    def as_dict(self):
        return {
            'type': 'NOR',
            'n_inputs': len(self.grounding_qs),
            'nmos_resistor': self.nmos_resistor.as_dict(),
            'grounding_qs': [q.as_dict() for q in self.grounding_qs],
            'output_net': self.output,
            'input_nets': self.inputs
        }

    def num_qs(self):
        return len(self.grounding_qs) + 1

    @staticmethod
    def from_net(net, gates):
        nmos_resistor = (gates.electrode_qs_in(net) & gates.nmos_resistor_qs).pop()
        grounding_qs = gates.electrode_qs_in(net) - {nmos_resistor}
        output = net
        inputs = {q.gate_net for q in grounding_qs}
        return NorGate(nmos_resistor, grounding_qs, output, inputs)


class PowerNorGate(NorGate):
    def __init__(self, nor_gate, powering_q, grounding_qs, output):
        super().__init__(nor_gate.nmos_resistor, nor_gate.grounding_qs, nor_gate.output, nor_gate.inputs)
        self.powering_q = powering_q
        self.grounding_qs |= grounding_qs
        self.output = output

    def as_dict(self):
        return {
            'type': 'Power NOR',
            'n_inputs': len(self.grounding_qs),
            'nmos_resistor': self.nmos_resistor.as_dict(),
            'powering_q': self.powering_q,
            'grounding_qs': [q.as_dict() for q in self.grounding_qs],
            'output_net': self.output,
            'input_nets': self.inputs
        }

    def num_qs(self):
        return len(self.grounding_qs) + 2

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
        self.qs = qs
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
        print("Powered Qs: {:s}".format(str([q.name for q in self.powered_qs])))


    def electrode_qs_in(self, net):
        return self.qs_by_electrode_net[net]

    def gate_qs_in(self, net):
        return self.qs_by_gate_net[net]

    def all_nets_iter(self):
        return (net for net, _ in self.nets.items())

    def nets_with_n_electrodes_iter(self, n, net_iter):
        return (net for net in net_iter if len(self.electrode_qs_in(net)) == n)

    def nets_with_n_gates_iter(self, n, net_iter):
        return (net for net in net_iter if len(self.gate_qs_in(net)) == n)
        
    def nets_with_n_grounding_qs_iter(self, n, net_iter):
        return (net for net in net_iter if len(self.grounding_qs & self.electrode_qs_in(net)) == n)

    def nets_with_n_powered_qs_iter(self, n, net_iter):
        return (net for net in net_iter if len(self.powered_qs & self.electrode_qs_in(net)) == n)

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

    def nets_powered_by_nmos_resistor_iter(self, net_iter):
        return (net for net in net_iter if len(self.nmos_resistor_qs & self.gate_qs_in(net)) == 1)

    def maybe_upgrade_to_power_nor(self, nor_gate):
        other_qs = (self.gate_qs_in(nor_gate.output) & self.powered_qs) - {nor_gate.nmos_resistor}
        if len(other_qs) != 1:
            return nor_gate
        other_q = other_qs.pop()
        other_q_net = other_q.nonvcc_electrode_net()
        other_input_qs = self.grounding_qs & self.electrode_qs_in(other_q_net)
        if len(other_input_qs) != len(nor_gate.inputs):
            return nor_gate
        if {q.gate_net for q in other_input_qs} != nor_gate.inputs:
            return nor_gate
        return PowerNorGate(nor_gate, other_q, other_input_qs, other_q_net)

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

        gates = (NorGate.from_net(net, self) for net in candidate_net_iter)

        # See if any are high-drive. A high-drive NOR gate is a NOR gate whose output
        # feeds exactly two powered transistors (one is the gate's own nmos resistor), 
        # and the other transisor's electrode net is connected
        # to exactly n grounding transistors, whose gates are connected to the gates of
        # the NOR's inputs.

        gates = (self.maybe_upgrade_to_power_nor(gate) for gate in gates)
        return list(gates)
