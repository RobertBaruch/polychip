import argparse
import collections
import re
import networkx as nx
import shapely.ops
import functools
import pprint
from enum import Enum, unique
from svg_parse import *
from layers import InkscapeFile
from layers import coerce_multipoly
from gates import Transistor
from gates import Gates
from gates import is_power_name
from gates import is_ground_name
from sch import *


# Text must be Djvu Sans Mono
# On gates, text must be on the QNames layer and must overlap the gate line.
# On polygons, text must be on the SNames layer and must intersect one and only one polygon.

class Contact(object):
    """Represents a contact between polygons on two different layers.

    Args:
        path (shapely.geometry.Polygon): The contact outline.

    Attributes:
        metal (int): If not None, the index into the InkscapeFile's metal_array
            this contact connects.    
        poly (int): If not None, the index into the InkscapeFile's poly_array
            this contact connects.    
        diff (int): If not None, the index into the InkscapeFile's diff_array
            this contact connects.    
    """
    def __init__(self, path_id, path):
        self.path_id = path_id
        self.path = path
        self.metal = None
        self.poly = None
        self.diff = None


@unique
class Type(Enum):
    """ Types of entities."""
    METAL = 1
    POLY = 2
    DIFF = 3
    GATE = 4
    E0 = 5
    E1 = 6

    def __repr__(self):
        return "Type." + str(self.name)


def calculate_contacts(drawing):
    """Returns an array of Contacts.

    Contacts are determined only after transistors are found.
    """
    cs = []
    for id, c in drawing.contact_paths.items():
        contact = Contact(id, c)
        contact.metal = next( (i for i, p in enumerate(drawing.metal_array) if p.intersects(c)), None)
        contact.diff = next( (i for i, p in enumerate(drawing.diff_array) if p.intersects(c)), None)
        contact.poly = next( (i for i, p in enumerate(drawing.poly_array) if p.intersects(c)), None)
        if contact.metal is not None and contact.diff is not None and contact.poly is not None:
            contact.metal = None
        count = 0
        contacted = "Isolated"
        if contact.metal is not None:
            count += 1
            contacted = "Metal"
        if contact.diff is not None:
            count += 1
            contacted = "Diff"
        if contact.poly is not None:
            count += 1
            contacted = "Poly"
        if count != 2:
            print("Warning: {:s} contact at {:s} has no connection".format(
                contacted, str(c)))
        else:
            cs.append(contact)
    print("{:d} valid contacts".format(len(cs)))
    return cs


def any_contact_in_polygon(contacts, polygon):
    """Determines if a polygon contains any contacts.

    Args:
        contacts (shapely.geometry.MultiPoint): All the contacts to check against.
        polygon (shapely.geometry.Polygon): The polygon to check.

    Returns:
        bool: True if at least one contact's midpoint is inside the polygon, False otherwise.
    """
    return polygon.contains(contacts)


def find_transistors_and_number_diffs(drawing):
    """Finds transistors and divides diffs at transistor gates.

    The gate of a transistor is defined where poly splits diff without a contact. Diffs 
    at gates are thus split in two.
    
    Args:
        drawing (InkscapeFile): The InkscapeFile object.

    Returns:
        [Transistor]: The array of transistors found.
    """
    new_diff_paths = {}

    print("All diffs: {:d}".format(len(drawing.diff_array)))
    print("All polys: {:d}".format(len(drawing.poly_array)))

    # Divide all diffs by all polys
    difference = coerce_multipoly(drawing.multidiff.difference(drawing.multipoly))
    print("Difference diffs: {:d}".format(len(difference)))

    intersections = coerce_multipoly(drawing.multidiff.intersection(drawing.multipoly))
    print("Intersection diffs: {:d}".format(len(intersections)))

    contacted_intersections_array = []
    gates_array = []
    for intersection in intersections.geoms:
        if intersection.intersects(drawing.multicontact):
            contacted_intersections_array.append(intersection)
        else:
            gates_array.append(intersection)

    contacted_intersections = shapely.geometry.MultiPolygon(contacted_intersections_array)
    print("Contacted intersections: {:d}".format(len(contacted_intersections)))
    print("Gates: {:d}".format(len(gates_array)))

    nongate_diffs = coerce_multipoly(shapely.ops.unary_union([difference, contacted_intersections]))
    drawing.replace_diff_array(list(nongate_diffs.geoms))
    print("nongate_diffs: {:d}".format(len(drawing.diff_array)))

    qs = []
    for gate in gates_array:
        electrodes = [i for i, nongate in enumerate(drawing.diff_array) if gate.touches(nongate)]
        if len(electrodes) != 2:
            print("Error: transistor gate at {:s} doesn't appear to have two electrodes.".format(
                str(gate.centroid)))
            continue
        g = next( (i for i, poly in enumerate(drawing.poly_array) if gate.intersects(poly)), None)
        if g is None:
            print("Error: transistor gate doesn't intersect any poly, which should never happen.")
        if electrodes[0] > electrodes[1]:
            electrodes[0], electrodes[1] = electrodes[1], electrodes[0]

        q = Transistor(gate, g, electrodes[0], electrodes[1], str(len(qs)))
        qs.append(q)

    print("Located {:d} transistors".format(len(qs)))
    return qs


def get_polygon(nodetype, nodename, drawing):
    if nodetype == Type.DIFF:
        return drawing.diff_array[nodename]
    elif nodetype == Type.POLY:
        return drawing.poly_array[nodename]
    elif nodetype == Type.METAL:
        return drawing.metal_array[nodename]

def print_node_path(nodes, drawing):
    if len(nodes) == 1:
        nodetype, nodename = next(nodes)
        polygon = get_polygon(nodetype, nodename, drawing)
        print("  {:s} @ {:s}".format(nodetype, str(polygon.representative_point())))
        return

    print("{")
    prev_nodetype = None
    prev_nodename = None
    for nodetype, nodename in nodes:
        if prev_nodetype is None:
            prev_nodetype = nodetype
            prev_nodename = nodename
            continue
        polygon = get_polygon(nodetype, nodename, drawing)
        prev_polygon = get_polygon(prev_nodetype, prev_nodename, drawing)
        print("  {:s} @ {:s}".format(
            nodetype, str(polygon.intersection(prev_polygon).representative_point())))
        prev_nodetype = nodetype
        prev_nodename = nodename
    print("}")
        

def file_to_netlist(file, print_netlist, print_qs):
    """Converts an Inkscape SVG file to a netlist and transistor list.

    Args:
        file (str): The filename of the Inkscape SVG file to load.
        print_netlist (bool): Whether to print the netlist at the end.
        print_qs (bool): Whether to print the transistor locations at the end.

    Returns:
        (nets, qs, drawing):
            nets ([(netname, net)]):
                netname (str): The name of the net, or None if unnamed.
                net ({net_node}):
                    net_node ((type, qname)):
                        type (Type): the transistor connection (E0, E1, or GATE).
                        qname (str): the name of the transistor
            qs ([Transistor]): All the transistors.
            drawing (InkscapeFile): The InkscapeFile.
    """
    root = parse_inkscape_svg(file)
    drawing = InkscapeFile(root)

    qs = find_transistors_and_number_diffs(drawing)
    cs = calculate_contacts(drawing)

    sigs = {Type.DIFF: [None] * len(drawing.diff_array),
            Type.POLY: [None] * len(drawing.poly_array),
            Type.METAL: [None] * len(drawing.metal_array)}
    sig_multimap = collections.defaultdict(set)

    for sname in drawing.snames:
        spoint = sname.center
        index = next( (i for i, p in enumerate(drawing.metal_array) if p.contains(spoint)), None)
        if index is not None:
            sigs[Type.METAL][index] = sname.text
            sig_multimap[sname.text].add((Type.METAL, index))
            print("Attached signal '{:s}' to {:s}".format(sname.text, str((Type.METAL, index))))
            continue

        index = next( (i for i, p in enumerate(drawing.poly_array) if p.contains(spoint)), None)
        if index is not None:
            sigs[Type.POLY][index] = sname.text
            sig_multimap[sname.text].add((Type.POLY, index))
            print("Attached signal '{:s}' to {:s}".format(sname.text, str((Type.POLY, index))))
            continue

        index = next( (i for i, p in enumerate(drawing.diff_array) if p.contains(spoint)), None)
        if index is not None:
            sigs[Type.DIFF][index] = sname.text
            sig_multimap[sname.text].add((Type.DIFF, index))
            print("Attached signal '{:s}' to {:s}".format(sname.text, str((Type.DIFF, index))))
            continue

        print("Warning: label '{:s}' at {:s} not attached to anything".format(
            sname.text, str(spoint)))

    for qname in drawing.qnames:
        index = next( (i for i, q in enumerate(qs) if q.gate_shape.intersects(qname.extents)), None)
        if index is not None:
            qs[index].name = qname.text
            print("Assigned transistor name " + qname.text)
        else:
            print("Error: transistor name {:s} at {:s} doesn't intersect a gate.".format(
                qname.text, str(qname.extents.coords[0])))

    G = nx.Graph()
    for i in range(len(drawing.metal_array)):
        G.add_node((Type.METAL, i))
    for i in range(len(drawing.diff_array)):
        G.add_node((Type.DIFF, i))
    for i in range(len(drawing.poly_array)):
        G.add_node((Type.POLY, i))
    for c in cs:
        if c.poly is None:
            G.add_edge((Type.METAL, c.metal), (Type.DIFF, c.diff))
        elif c.metal is None:
            G.add_edge((Type.POLY, c.poly), (Type.DIFF, c.diff))
        else:
            G.add_edge((Type.METAL, c.metal), (Type.POLY, c.poly))
    for i, q in enumerate(qs):
        G.add_edge((Type.GATE, q.name), (Type.POLY, q.gate))
        G.add_edge((Type.E0, q.name), (Type.DIFF, q.electrode0))
        G.add_edge((Type.E1, q.name), (Type.DIFF, q.electrode1))

    # All signals with the same name are connected, even if not physically.
    for sname, nodes in sig_multimap.items():
        if len(nodes) == 1:
            continue
        print("Joining {:d} components for signal {:s}".format(len(nodes), sname))
        start_node = None
        for node in nodes:
            if start_node is None:
                start_node = node
                continue
            G.add_edge(start_node, node)
            start_node = node

    qs_by_name = {q.name: q for q in qs}

    nets = {}
    anonymous_net = 0
    # net ({(Type, name)}): A connected component (the set of nodes connected to each other)
    for net in nx.connected_components(G):
        netname = None
        signames = set()
        for nodetype, nodename in net:
            if nodetype in sigs and sigs[nodetype][nodename] is not None:
                node_signame = sigs[nodetype][nodename]
                signames.add(node_signame)
                if netname is not None and netname != node_signame:
                    print("Warning: component {:s} is named '{:s}' but is connected to '{:s}'".format(
                        str((nodetype, nodename)), node_signame, netname))
                else:
                    netname = node_signame

        # power/ground short detection
        has_power_node = any((is_power_name(n) for n in signames))
        has_ground_node = any((is_ground_name(n) for n in signames))
        if has_power_node and has_ground_node:
            power_sig_name = next((n for n in signames if is_power_name(n)))
            ground_sig_name = next((n for n in signames if is_ground_name(n)))
            power_node = next((n for n in sig_multimap[power_sig_name]))
            ground_node = next((n for n in sig_multimap[ground_sig_name]))
            node_path = nx.shortest_path(G, power_node, ground_node)
            print("FATAL: There's a short between power and ground. Further analysis is pointless.")
            print("Here is a path from power to ground:")
            print(node_path)
            print('----')
            print_node_path(node_path, drawing)
            sys.exit(1)

        component_net = {x for x in net if x[0] == Type.GATE or x[0] == Type.E0 or x[0] == Type.E1}
        if netname is None:
            netname = '__net__{:d}'.format(anonymous_net)
            anonymous_net += 1
        for (terminal, qname) in component_net:
            if terminal == Type.GATE:
                qs_by_name[qname].gate_net = netname
            elif terminal == Type.E0:
                qs_by_name[qname].electrode0_net = netname
            elif terminal == Type.E1:
                qs_by_name[qname].electrode1_net = netname
        if len(component_net) > 0:
            nets[netname] = component_net

    if print_netlist:
        print(nets)
    if print_qs:
        print(qs)

    return (nets, qs, drawing)


def nmos_nand_iter(nets, qs):
    """Generator for finding nmos n-input nand gates (number of transistors: n+1).

    This algorithm is O(N) in the number of transistors.

    Args:
        nets ([(netname, net)]):
            netname (str): The name of the net, or None if unnamed.
            net ({net_node}):
                net_node ((type, qname)):
                    type (Type): the transistor connection (E0, E1, or GATE).
                    qname (str): the name of the transistor
        qs ([Transistor]): All the transistors.
    Yields:
        (Transistor, Transistor): A pair of transistors comprising the inverter. The first
            transistor is the nmos resistor.
    """
    qs_by_name = {q.name: q for q in qs}

    # A map of netname -> transistors connected to net by (at least) one electrode
    qs_by_net = collections.defaultdict(set)
    for q in qs:
        qs_by_net[q.electrode0_net].add(q)
        qs_by_net[q.electrode1_net].add(q)

    # The set of all transistors having (at least) one electrode grounded.
    grounding_qs = qs_by_net['GND']

    # Save only those nets with 2 electrodes connected to them.
    qs_by_net = {net: qs for net, qs in qs_by_net.items() if len(qs) == 2}

    # Construct a graph using the transistors' electrodes as nodes connected by an edge.
    G = nx.Graph()
    for qset in qs_by_net.values():
        for q in qset:
            G.add_edge(q.electrode0_net, q.electrode1_net)
    paths = nx.algorithms.simple_paths.all_simple_paths(G, "VCC", "GND")
    for path in paths:
        if len(path) > 3:
            print(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Polychip, a program to help recognize transistors and "
        "gates in an Inkscape file traced from an NMOS integrated circuit.")
    parser.add_argument("file", metavar="<file>", type=argparse.FileType('r'), nargs=1,
                        help="input Inkscape SVG file")
    parser.add_argument("--sch", action="store_true",
                        help="whether to generate a KiCAD .sch file")
    parser.add_argument("--nets", action="store_true",
                        help="whether to print the netlist")
    parser.add_argument("--qs", action="store_true",
                        help="whether to print the transistor locations")
    args = parser.parse_args()

    nets, qs, drawing = file_to_netlist(args.file[0], args.nets, args.qs)
    gates = Gates(nets, qs)

    print("{:d} total transistors".format(len(gates.qs)))

    gates.find_all_the_things()

    print("Found {:d} muxes (total {:d} qs)".format(len(gates.muxes),
        sum(g.num_qs() for g in gates.muxes)))
    for i in range(2, 10):
        gs = {g for g in gates.muxes if len(g.selected_inputs) == i}
        print("  {:d} {:d}-muxes".format(len(gs), i))

    for i in range(1, 10):
        nors = {nor for nor in gates.nors if len(nor.inputs) == i}
        print("Found {:d} {:d}-input NOR gates (total {:d} qs)".format(len(nors), i,
            sum(g.num_qs() for g in nors)))

    print("Found {:d} tristate inverters (total {:d} qs)".format(len(gates.tristate_inverters),
        sum(g.num_qs() for g in gates.tristate_inverters)))
    print("Found {:d} tristate buffers (total {:d} qs)".format(len(gates.tristate_buffers),
        sum(g.num_qs() for g in gates.tristate_buffers)))

    print("{:d} unallocated transistors".format(len(gates.qs)))

    if args.sch:
        inkscape_to_sch_transform = sch_size_transform(drawing)
        write_sch_file("polychip.sch", gates, inkscape_to_sch_transform)
