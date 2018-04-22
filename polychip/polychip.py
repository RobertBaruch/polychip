import argparse
import collections
import datetime
import json
import re
import networkx as nx
import shapely.ops
import shapely.strtree
import statistics
import functools
import pprint
import sys
from enum import Enum, unique
from svg_parse import *
from layers import InkscapeFile
from layers import Label
from layers import coerce_multipoly
from gates import Transistor
from gates import Gates
from gates import is_power_net
from gates import is_ground_net
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

    def to_dict(self):
        """Convert to dictionary, for JSON output."""
        return {
            "__POLYCHIP_OBJECT__": "Type",
            "n": self.value,
        }

    @staticmethod
    def from_dict(dict):
        """Returns the Type corresponding to the dict."""
        assert dict["__POLYCHIP_OBJECT__"] == "Type", "Type.from_dict wasn't given its expected dict: " + str(dict)
        return Type(dict["n"])


def calculate_contacts(drawing):
    """Returns an array of Contacts.

    Contacts are determined only after transistors are found.
    """
    cs = []

    poly_rtree = shapely.strtree.STRtree(drawing.poly_array)
    poly_dict = {}
    for i, poly in enumerate(drawing.poly_array):
        poly_dict[poly.wkb] = i

    diff_rtree = shapely.strtree.STRtree(drawing.diff_array)
    diff_dict = {}
    for i, diff in enumerate(drawing.diff_array):
        diff_dict[diff.wkb] = i

    metal_rtree = shapely.strtree.STRtree(drawing.metal_array)
    metal_dict = {}
    for i, metal in enumerate(drawing.metal_array):
        metal_dict[metal.wkb] = i

    for id, c in drawing.contact_paths.items():
        contact = Contact(id, c)
        contact.poly = next ((poly_dict[p.wkb] for p in poly_rtree.query(c) if p.intersects(c)), None)
        contact.diff = next ((diff_dict[p.wkb] for p in diff_rtree.query(c) if p.intersects(c)), None)
        contact.metal = next ((metal_dict[p.wkb] for p in metal_rtree.query(c) if p.intersects(c)), None)
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
            print("Warning: {:s} contact at {:s} has no connection".format(contacted, str(c.representative_point())))
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

    t1 = datetime.datetime.now()
    difference = coerce_multipoly(drawing.multidiff.difference(drawing.multipoly))
    t2 = datetime.datetime.now()
    print("Difference diffs: {:d} (in {:f} sec)".format(len(difference), (t2 - t1).total_seconds()))

    t1 = datetime.datetime.now()
    intersections = coerce_multipoly(drawing.multidiff.intersection(drawing.multipoly))
    t2 = datetime.datetime.now()
    print("Intersection diffs: {:d} (in {:f} sec)".format(len(intersections), (t2 - t1).total_seconds()))

    t1 = datetime.datetime.now()
    contacted_intersections_array = []
    gates_array = []
    diff_contacts = coerce_multipoly(intersections.intersection(drawing.multicontact))
    t2 = datetime.datetime.now()
    print("Diff contacts: {:d} (in {:f} sec)".format(len(diff_contacts.geoms), (t2 - t1).total_seconds()))

    t1 = datetime.datetime.now()
    rtree = shapely.strtree.STRtree(diff_contacts)
    t2 = datetime.datetime.now()
    print("R-tree constructed in {:f} sec".format((t2 - t1).total_seconds()))

    t1 = datetime.datetime.now()
    for intersection in intersections.geoms:
        candidates = rtree.query(intersection)
        if len(candidates) != 0 and any(intersection.intersects(candidate) for candidate in candidates):
            contacted_intersections_array.append(intersection)
        else:
            gates_array.append(intersection)

    contacted_intersections = shapely.geometry.MultiPolygon(contacted_intersections_array)
    t2 = datetime.datetime.now()
    print("Contacted intersections: {:d} (in {:f} sec)".format(len(contacted_intersections), (t2 - t1).total_seconds()))
    print("Gates: {:d}".format(len(gates_array)))

    t1 = datetime.datetime.now()
    nongate_diffs = coerce_multipoly(shapely.ops.unary_union([difference, contacted_intersections]))
    t2 = datetime.datetime.now()
    drawing.replace_diff_array(list(nongate_diffs.geoms))
    print("nongate_diffs: {:d} (in {:f} sec)".format(len(drawing.diff_array), (t2 - t1).total_seconds()))

    t1 = datetime.datetime.now()
    qs = []
    rtree = shapely.strtree.STRtree(drawing.poly_array)
    poly_dict = {}
    for i, poly in enumerate(drawing.poly_array):
        poly_dict[poly.wkb] = i

    for gate in gates_array:
        electrodes = [i for i, nongate in enumerate(drawing.diff_array) if gate.touches(nongate)]
        if len(electrodes) != 2:
            print("Error: transistor gate at {:s} doesn't appear to have two electrodes.".format(
                str(gate.centroid)))
            continue
        candidates = rtree.query(gate)
        g = next(poly for poly in candidates if gate.intersects(poly))
        if g is None:
            print("Error: transistor gate doesn't intersect any poly, which should never happen.")
        else:
            g = poly_dict[g.wkb]
        if electrodes[0] > electrodes[1]:
            electrodes[0], electrodes[1] = electrodes[1], electrodes[0]

        q = Transistor(gate, g, electrodes[0], electrodes[1], str(len(qs)))
        qs.append(q)

    t2 = datetime.datetime.now()
    print("Located electrodes (in {:f} sec)".format((t2 - t1).total_seconds()))
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
        print("  ({:s}, {:s}) @ {:s}".format(nodetype, str(nodename), str(polygon.representative_point())))
        return

    print("{")
    prev_nodetype = None
    prev_nodename = None
    prev_polygon = None
    for nodetype, nodename in nodes:
        if prev_nodetype is None:
            prev_nodetype = nodetype
            prev_nodename = nodename
            prev_polygon = get_polygon(prev_nodetype, prev_nodename, drawing)
            continue
        polygon = get_polygon(nodetype, nodename, drawing)
        print("  ({:s}, {:s}) x ({:s}, {:s}) @ {:s}".format(
            prev_nodetype, str(prev_nodename), nodetype, str(nodename),
            str(polygon.intersection(prev_polygon).representative_point())))
        prev_nodetype = nodetype
        prev_nodename = nodename
        prev_polygon = get_polygon(prev_nodetype, prev_nodename, drawing)
    print("}")


def file_to_netlist(file, print_netlist=False, print_qs=False):
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

    t1 = datetime.datetime.now()
    qs = find_transistors_and_number_diffs(drawing)
    t2 = datetime.datetime.now()
    print("Located {:d} transistors (in {:f} sec)".format(len(qs), (t2 - t1).total_seconds()))

    areas = [q.gate_shape.area for q in qs]
    if len(areas) > 2:
        areas.sort()
        print("Mean gate area {:f} px^2".format(statistics.mean(areas)))
        print("Median gate area {:f} px^2".format(statistics.median(areas)))
        print("Min, max gate area {:f}, {:f}".format(areas[0], areas[-1]))
        print("Standard deviation in gate area {:f} px^2".format(statistics.pstdev(areas)))

    t1 = datetime.datetime.now()
    cs = calculate_contacts(drawing)
    t2 = datetime.datetime.now()
    print("Classified {:d} contacts (in {:f} sec)".format(len(cs), (t2 - t1).total_seconds()))

    sigs = {Type.DIFF: [None] * len(drawing.diff_array),
            Type.POLY: [None] * len(drawing.poly_array),
            Type.METAL: [None] * len(drawing.metal_array)}
    sig_multimap = collections.defaultdict(set)

    t1 = datetime.datetime.now()
    for sname in drawing.snames:
        spoint = sname.center
        index = next( (i for i, p in enumerate(drawing.metal_array) if p.contains(spoint)), None)
        if index is not None:
            sigs[Type.METAL][index] = sname.text
            sig_multimap[sname.text].add((Type.METAL, index))
            continue

        index = next( (i for i, p in enumerate(drawing.poly_array) if p.contains(spoint)), None)
        if index is not None:
            sigs[Type.POLY][index] = sname.text
            sig_multimap[sname.text].add((Type.POLY, index))
            continue

        index = next( (i for i, p in enumerate(drawing.diff_array) if p.contains(spoint)), None)
        if index is not None:
            sigs[Type.DIFF][index] = sname.text
            sig_multimap[sname.text].add((Type.DIFF, index))
            continue

        print("Warning: label '{:s}' at {:s} not attached to anything".format(sname.text, str(spoint)))

    t2 = datetime.datetime.now()
    print("Attached {:d} signal names (in {:f} sec)".format(len(drawing.snames), (t2 - t1).total_seconds()))

    t1 = datetime.datetime.now()
    for qname in drawing.qnames:
        index = next( (i for i, q in enumerate(qs) if q.gate_shape.intersects(qname.extents)), None)
        if index is not None:
            qs[index].name = qname.text
        else:
            print("Error: transistor name {:s} at {:s} doesn't intersect a gate.".format(
                qname.text, str(qname.extents.coords[0])))
    t2 = datetime.datetime.now()
    print("Attached {:d} transistor names (in {:f} sec)".format(len(drawing.qnames), (t2 - t1).total_seconds()))

    t1 = datetime.datetime.now()
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

    print("Graph has {:d} nodes and {:d} edges".format(len(G.adj), len(cs) + 3 * len(qs)))

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

    # Give each net a name. If one of the components in the net has a signal name, use that. If we
    # end up with more than one signal name in a net, then that's sometimes okay, since maybe you
    # didn't realize the two signals were connected. But if you end up with a signal connected to
    # a power or ground signal name, then you probably didn't want that, so exit.
    #
    # And of course, if a net contains both power and ground, you just shorted the thing out, so
    # exit there, too.
    nets = {}
    anonymous_net = 0
    # net ({(Type, int)}): A connected component (the set of nodes connected to each other)
    for net in nx.connected_components(G):
        netname = None
        netnode = None
        signames = set()
        for node in net:
            nodetype, index = node
            if nodetype in sigs and sigs[nodetype][index] is not None:
                node_signame = sigs[nodetype][index]
                signames.add(node_signame)
                if netname is not None and netname != node_signame:
                    print("Warning: component {:s} is named '{:s}' but is connected to component {:s} named '{:s}'".format(
                        str(node), node_signame, str(netnode), netname))
                    if is_power_net(netname) or is_ground_net(netname) or is_power_net(node_signame) or is_ground_net(node_signame):
                        print("You probably didn't want that. Further analysis is pointless.")
                        node_path = nx.shortest_path(G, node, netnode)
                        print("Here is a path from {:s} to {:s}:".format(node_signame, netname))
                        print(node_path)
                        print("----")
                        print_node_path(node_path, drawing)
                        sys.exit(1)
                else:
                    netname = node_signame
                    netnode = node

        # power/ground short detection
        has_power_node = any((is_power_net(n) for n in signames))
        has_ground_node = any((is_ground_net(n) for n in signames))
        if has_power_node and has_ground_node:
            power_sig_name = next((n for n in signames if is_power_net(n)))
            ground_sig_name = next((n for n in signames if is_ground_net(n)))
            power_node = next((n for n in sig_multimap[power_sig_name]))
            ground_node = next((n for n in sig_multimap[ground_sig_name]))
            node_path = nx.shortest_path(G, power_node, ground_node)
            print("FATAL: There's a short between power and ground. Further analysis is pointless.")
            print("Here is a path from power to ground:")
            print(node_path)
            print("----")
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
    t2 = datetime.datetime.now()
    print("Constructed netlist of {:d} nets (in {:f} sec)".format(len(nets), (t2 - t1).total_seconds()))

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


class Net(object):
    """Representation of a net as it comes from file_to_netlist, except without using sets so that
    it is dumpable by JSONEncoder.

    Args:
        netname (str): The name of the net, or None if unnamed.
        net ({net_node}):
            net_node ((type, qname)):
                type (Type): the transistor connection (E0, E1, or GATE).
                qname (str): the name of the transistor
    """
    def __init__(self, netname, net):
        self.netname = netname
        self.net = list(net)

    def to_dict(self):
        return {
            "__POLYCHIP_OBJECT__": "Net",
            "netname": self.netname,
            "net": self.net,
        }

    @staticmethod
    def from_dict(d):
        """Returns not a Net, but (netname, net) as was given originally in the constructor."""
        assert d["__POLYCHIP_OBJECT__"] == "Net", "Net.from_dict wasn't given its expected dict: " + str(d)
        netname = d["netname"]
        net = {(e[0], e[1]) for e in d["net"]}
        return (netname, net)


class PolychipJsonEncoder(json.JSONEncoder):
    def default(self, o):
        if type(o) == set:
            print("FATAL: attempted to encode set object: " + str(o))
        if isinstance(o, Transistor) or isinstance(o, Net) or isinstance(o, Type) or isinstance(o, Label):
            return o.to_dict()
        return json.JSONEncoder.default(self, o)


def polychip_decode_json(d):
    """Decodes a decoded json disctionary to polychip objects."""
    if "__POLYCHIP_OBJECT__" not in d:
        return d
    t = d["__POLYCHIP_OBJECT__"]
    if t == "Net":
        return Net.from_dict(d)
    elif t == "Transistor":
        return Transistor.from_dict(d)
    elif t == "Type":
        return Type.from_dict(d)
    elif t == "Label":
        return Label.from_dict(d)
    else:
        raise AssertionError("Unsupported polychip object for JSON decode: " + t)


if __name__ == "__main__":
    version = "0.8"
    print("Polychip v" + version)

    parser = argparse.ArgumentParser(description="Polychip, a program to help recognize transistors and "
        "gates in an Inkscape file traced from an NMOS integrated circuit.")
    parser.add_argument("file", metavar="<svgfile>", type=argparse.FileType('r'), nargs="?", default=None,
                        help="input Inkscape SVG file")
    parser.add_argument("--sch", action="store_true",
                        help="whether to generate a KiCAD .sch file. Outputs to polychip.sch, use eeschema to view!")
    parser.add_argument("--nets", action="store_true",
                        help="whether to print the netlist")
    parser.add_argument("--qs", action="store_true",
                        help="whether to print the transistor locations")
    parser.add_argument("--output", metavar="<outfile>", type=str, nargs=1, action="store",
                        help="a JSON file to output the net, q, and drawing data to. Use with --input to skip a lot of work!")
    parser.add_argument("--input", metavar="<infile>", type=str, nargs=1, action="store",
                        help="a JSON file to input the net, q, and drawing data from. Use with --output to skip a lot of work!")
    args = parser.parse_args()

    if args.input is None:
        if args.file is None:
            parser.print_help()
            sys.exit(1)

        # nets ({netname: net}):
        #     netname (str): The name of the net, or None if unnamed.
        #     net ({net_node}):
        #         net_node ((type, qname)):
        #             type (Type): the transistor connection (E0, E1, or GATE).
        #             qname (str): the name of the transistor
        # qs ([Transistor]): list of transistors found.
        # drawing (InkscapeFile): the InkscapeFile representation.
        nets, qs, drawing = file_to_netlist(args.file, args.nets, args.qs)

        # drawing_bounding_box (float, float, float, float): Bounding box (minx, miny, maxx, maxy) for the InkscapeFile.
        layer_bounds = [m.bounds for m in [drawing.multicontact, drawing.multipoly, drawing.multidiff, drawing.multimetal]
            if m.bounds != ()]
        drawing_bounding_box = shapely.ops.cascaded_union(
            [shapely.geometry.box(*bounds) for bounds in layer_bounds]).bounds

        # pnames ([Label]): list of pin names.
        pnames = drawing.pnames

        if args.output is not None:
            # We dump everything that any stage after this requires.
            with open(args.output[0], 'wt', encoding='utf-8') as f:
                json.dump({
                    "nets": [Net(netname, net) for netname, net in nets.items()],
                    "qs": qs,
                    "pnames": pnames,
                    "drawing_bounding_box": drawing_bounding_box,  # note: this tuple becomes a list.
                }, f, cls=PolychipJsonEncoder)

    if args.input is not None:
        with open(args.input[0], 'rt', encoding='utf-8') as f:
            d = json.load(f, object_hook=polychip_decode_json)
            nets = {netname: net for (netname, net) in d["nets"]}
            qs = d["qs"]
            pnames = d["pnames"]
            box = d["drawing_bounding_box"]
            drawing_bounding_box = (box[0], box[1], box[2], box[3])

    gates = Gates(nets, qs, pnames)

    print("{:d} total transistors".format(len(gates.qs)))

    gates.find_all_the_things()

    if args.sch:
        write_sch_file("polychip.sch", drawing_bounding_box, gates)
