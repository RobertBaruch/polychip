import argparse
import re
import networkx as nx
import shapely.ops
import functools
from enum import Enum, unique
from svg_parse import *
from layers import InkscapeFile
from layers import coerce_multipoly


# Text must be Djvu Sans Mono
# On gates, text must be on the QNames layer and must overlap the gate line.
# On polygons, text must be on the SNames layer and must intersect one and only one polygon.

class Contact(object):
    """Represents a contact between polygons on two different layers.

    Args:
        loc (shapely.geometry.Point): The midpoint of the contact.

    Attributes:
        metal (int): If not None, the index into the InkscapeFile's metal_array
            this contact connects.    
        poly (int): If not None, the index into the InkscapeFile's poly_array
            this contact connects.    
        diff (int): If not None, the index into the InkscapeFile's diff_array
            this contact connects.    
    """
    def __init__(self, loc):
        self.metal = None
        self.poly = None
        self.diff = None
        self.loc = loc


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
    """
    def __init__(self, gate_shape, gate, electrode0, electrode1, name):
        self.gate_shape = gate_shape
        self.gate = gate
        self.electrode0 = electrode0
        self.electrode1 = electrode1
        self.name = name
        self.centroid = self.gate_shape.centroid

    def __repr__(self):
        return "{:s} @ {:f}, {:f}".format(self.name, self.centroid.x, self.centroid.y)


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

    Contacts are determine only after transistors are found.
    """
    cs = []
    for c in drawing.contacts.geoms:
        contact = Contact(c)
        contact.metal = next( (i for i, p in enumerate(drawing.metal_array) if p.contains(c)), None)
        contact.diff = next( (i for i, p in enumerate(drawing.diff_array) if p.contains(c)), None)
        contact.poly = next( (i for i, p in enumerate(drawing.poly_array) if p.contains(c)), None)
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
        if intersection.intersects(drawing.contacts):
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


def file_to_netlist(file):
    root = parse_inkscape_svg(file)
    drawing = InkscapeFile(root)

    qs = find_transistors_and_number_diffs(drawing)
    cs = calculate_contacts(drawing)

    sigs = {Type.DIFF: [None] * len(drawing.diff_array),
            Type.POLY: [None] * len(drawing.poly_array),
            Type.METAL: [None] * len(drawing.metal_array)}
    for sname in drawing.snames:
        spoint = sname.center
        index = next( (i for i, p in enumerate(drawing.metal_array) if p.contains(spoint)), None)
        if index is not None:
            sigs[Type.METAL][index] = sname.text
            print("Attached signal '{:s}' to {:s}".format(sname.text, str((Type.METAL, index))))
            continue

        index = next( (i for i, p in enumerate(drawing.poly_array) if p.contains(spoint)), None)
        if index is not None:
            sigs[Type.POLY][index] = sname.text
            print("Attached signal '{:s}' to {:s}".format(sname.text, str((Type.POLY, index))))
            continue

        index = next( (i for i, p in enumerate(drawing.diff_array) if p.contains(spoint)), None)
        if index is not None:
            sigs[Type.DIFF][index] = sname.text
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

    nets = []
    for cc in nx.connected_components(G):
        net = {x for x in cc}
        netname = None
        for c in net:
            if c[0] in sigs and sigs[c[0]][c[1]] is not None:
                if netname is not None and netname != sigs[c[0]][c[1]]:
                    print("Warning: component {:s} is named '{:s}' but is connected to '{:s}'".format(
                        str(c), sigs[c[0]][c[1]], netname))
                else:
                    netname = sigs[c[0]][c[1]]
        component_net = {x for x in net if x[0] == Type.GATE or x[0] == Type.E0 or x[0] == Type.E1}
        if netname != None or len(component_net) > 0:
            nets.append((netname, component_net))

    print('Netlist: ' + str(nets))
    print('Transistors: ' + str(qs))
    return (nets, qs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Polychip.')
    parser.add_argument('file', metavar='<file>', type=argparse.FileType('r'), nargs=1,
                        help='input Inkscape SVG file')
    args = parser.parse_args()

    file_to_netlist(args.file[0])