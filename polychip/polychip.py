import argparse
import re
import networkx as nx
from svg_parse import *
from layers import *

# Text must be Djvu Sans Mono
# On gates, text must be on the QNames layer and must overlap the gate line.
# On polygons, text must be on the SNames layer and must intersect one and only one polygon.

def layer_path(name):
    return "./svg:g[@inkscape:groupmode='layer'][@inkscape:label='" + name + "']"


doc_height = 0;


def calculate_contacts(contacts, metal_paths, diff_paths, poly_paths):
    for cid, c in contacts.items():
        metal = None
        diff = None
        poly = None
        for pid, p in metal_paths.items():
            if p['path'].contains(c['loc']):
                metal = pid
                break
        for pid, p in diff_paths.items():
            if p['path'].contains(c['loc']):
                diff = pid
                break
        for pid, p in poly_paths.items():
            if p['path'].contains(c['loc']):
                poly = pid
                break
        if metal is not None and diff is not None and poly is not None:
            metal = None
        if metal is not None:
            c['metal'] = metal
            if diff is not None:
                metal_paths[metal]['conn'].append(diff)
            elif poly is not None:
                metal_paths[metal]['conn'].append(poly)
        if diff is not None:
            c['diff'] = diff
            if metal is not None:
                diff_paths[diff]['conn'].append(metal)
            elif poly is not None:
                diff_paths[diff]['conn'].append(poly)
        if poly is not None:
            c['poly'] = poly
            if metal is not None:
                poly_paths[poly]['conn'].append(metal)
            elif diff is not None:
                poly_paths[poly]['conn'].append(diff)


def find_bad_contacts(contacts):
    for cid, c in contacts.items():
        if 'metal' not in c and 'diff' not in c and 'poly' not in c:
            print("Error: Contact {:s} at {:s} has no connection".format(cid,
                                                                         str(to_inkscape_coords(c['loc'], doc_height))))
        elif 'metal' in c and 'diff' not in c and 'poly' not in c:
            print("Error: Metal contact {:s} at {:s} has no second connection".format(cid,
                                                                                      str(to_inkscape_coords(c['loc'], doc_height))))
        elif 'diff' in c and 'metal' not in c and 'poly' not in c:
            print("Error: Diff contact {:s} at {:s} has no second connection".format(cid,
                                                                                     str(to_inkscape_coords(c['loc'], doc_height))))
        elif 'poly' in c and 'diff' not in c and 'metal' not in c:
            print("Error: Poly contact {:s} at {:s} has no second connection".format(cid,
                                                                                     str(to_inkscape_coords(c['loc'], doc_height))))


def find_bad_paths(metal_paths, diff_paths, poly_paths):
    for pid, p in metal_paths.items():
        if len(p['conn']) == 0:
            print("Error: metal {:s} is isolated".format(pid))
    for pid, p in diff_paths.items():
        if len(p['conn']) == 0:
            print("Error: diff {:s} is isolated".format(pid))
    for pid, p in poly_paths.items():
        if len(p['conn']) == 0:
            print("Error: poly {:s} is isolated".format(pid))


def file_to_netlist(file):
    root = parse_inkscape_svg(file)

    doc_height = float(root.get('height'))
    contacts, poly_paths, diff_paths, metal_paths, qnames, transistors = parse_layers(root)

    calculate_contacts(contacts, metal_paths, diff_paths, poly_paths)
    find_bad_contacts(contacts)

    for qid, q in transistors.items():
        ends = []
        endpoints = [shapely.geometry.Point(q['path'].coords[0]),
                     shapely.geometry.Point(q['path'].coords[1])]
        # Sort endpoints to get a consistent electrode 0 and 1.
        if (endpoints[0].x > endpoints[1].x or 
            endpoints[0].x == endpoints[1].x and endpoints[0].y > endpoints[1].y):
            endpoints[0], endpoints[1] = endpoints[1], endpoints[0]
            
        for did, d in diff_paths.items():
            if d['path'].contains(endpoints[0]) or d['path'].contains(endpoints[1]):
                ends.append(did)
        if len(ends) == 0:
            print("Error: Transistor {:s} has no electrode connections".format(qid))
        elif len(ends) == 1:
            print("Error: Transistor {:s} has only one electrode connection".format(qid))
        poly = None
        for pid, p in poly_paths.items():
            if q['path'].intersects(p['path']):
                poly = pid
                break
        if poly is None:
            print("Error: Transistor {:s} has no gate".format(qid))
        q['gate'] = pid
        if poly is not None:
            poly_paths[poly]['conn'].append(qid + '_g')
        q['electrodes'] = ends
        for i, e in enumerate(ends):
            diff_paths[e]['conn'].append("{:s}_e{:d}".format(qid, i))

    find_bad_paths(metal_paths, diff_paths, poly_paths)

    G = nx.Graph()
    for paths in [poly_paths, metal_paths, diff_paths]:
        for pid, p in paths.items():
            G.add_node(pid, path=p)
            for c in p['conn']:
                G.add_edge(pid, c)
    for qid, q in transistors.items():
        if q['gate'] is not None:
            gid = qid + '_g'
            G.add_node(gid)
            G.add_edge(gid, q['gate'])
        for i, e in enumerate(q['electrodes']):
            eid = "{:s}_e{:d}".format(qid, i)
            G.add_node(eid)
            G.add_edge(eid, e)

    # Stamp every node in a connected component with any node's label
    for cc in nx.connected_components(G):
        signal_name = None
        for c in cc:
            node = G.nodes[c]
            if 'path' in node and 'label' in node['path']:
                signal_name = node['path']['label']
                if signal_name is not None:
                    break
        if signal_name is not None:
            for c in cc:
                G.nodes[c]['signal'] = signal_name

    nets = []
    for cc in nx.connected_components(G):
        net = {x for x in cc if x.startswith('q_')}
        if len(net) > 0:
            signal_name = None
            node = G.nodes[next(iter(net))]
            if 'signal' in node:
                signal_name = node['signal']
            nets.append((signal_name, net))

    print('Netlist: ' + str(nets))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Polychip.')
    parser.add_argument('file', metavar='<file>', type=argparse.FileType('r'), nargs=1,
                        help='input Inkscape SVG file')
    args = parser.parse_args()

    file_to_netlist(args.file[0])