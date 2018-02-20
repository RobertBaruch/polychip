import argparse
import re
import xml.etree.ElementTree as ET
import networkx as nx
from matplotlib.path import Path

# Text must be Djvu Sans Mono
# On gates, text must be on the QNames layer and must overlap the gate line.
# On polygons, text must be on the SNames layer and must intersect one and only one polygon.

def svgpath_to_mppath(p, trans):
    pt = None
    mode = None
    coords = []
    codes = []
    for t in p.split(' '):
        if t == 'm' or t == 'l' or t == 'v' or t == 'h':
            mode = t
        elif t == 'z':
            break
        else:
            if mode == 'm':
                x, y = map(float, t.split(','))
                pt = [x + trans[0], y + trans[1]]
                mode = 'l'
            elif mode == 'l':
                x, y = map(float, t.split(','))
                pt = [pt[0] + x, pt[1] + y]
            elif mode == 'v':
                pt = [pt[0], pt[1] + float(t)]
            elif mode == 'h':
                pt = [pt[0] + float(t), pt[1]]
            codes.append(Path.LINETO)
            coords.append(pt)

    codes[0] = Path.MOVETO
    return Path(coords, codes)


def parse_translate(s):
    if s is None:
        return [0, 0]
    t = s.split('(')
    t = t[1].split(')')
    t = t[0].split(',')
    x, y = map(float, t)
    return [x, y]


def layer_path(name):
    return "./svg:g[@inkscape:groupmode='layer'][@inkscape:label='" + name + "']"


doc_height = 0;
def to_inkscape_coords(pt):
    return [pt[0], doc_height - pt[1]]


def calculate_contacts(contacts, metal_paths, diff_paths, poly_paths):
    for cid, c in contacts.items():
        metal = None
        diff = None
        poly = None
        for pid, p in metal_paths.items():
            if p['path'].contains_point(c['loc']):
                metal = pid
                break
        for pid, p in diff_paths.items():
            if p['path'].contains_point(c['loc']):
                diff = pid
                break
        for pid, p in poly_paths.items():
            if p['path'].contains_point(c['loc']):
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
                                                                         str(to_inkscape_coords(c['loc']))))
        elif 'metal' in c and 'diff' not in c and 'poly' not in c:
            print("Error: Metal contact {:s} at {:s} has no second connection".format(cid,
                                                                                      str(to_inkscape_coords(c['loc']))))
        elif 'diff' in c and 'metal' not in c and 'poly' not in c:
            print("Error: Diff contact {:s} at {:s} has no second connection".format(cid,
                                                                                     str(to_inkscape_coords(c['loc']))))
        elif 'poly' in c and 'diff' not in c and 'metal' not in c:
            print("Error: Poly contact {:s} at {:s} has no second connection".format(cid,
                                                                                     str(to_inkscape_coords(c['loc']))))


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


def parse_text(text_element, trans, ns):
    # Count characters in <tspan> elements
    tspans = text_element.findall("svg:tspan", ns)
    transform = text_element.get('transform')
    text = "".join(["".join(x.itertext()) for x in tspans])
    xx = float(text_element.get('x'))
    yy = float(text_element.get('y'))
    x = xx
    y = yy

    style = tspans[0].get('style')
    if "font-family:'DejaVu Sans Mono'" not in style:
        print("Warning: font must be DejaVu Sans Mono for " + text)
    m = re.search('(?<=font-size:)[0-9.]+(?=px)', style)
    font_size = 0
    if m is None:
        print("Warning: No pixel-based font size found in text style for " + text)
    else:
        font_size = float(m.group(0))

    # Determined empirically
    capital_char_height = 18.646 * font_size / 21.33333
    char_width = 11.427 * font_size / 21.33333

    sx = len(text) * char_width
    sy = capital_char_height

    if transform == 'rotate(-90)':
        x = yy
        y = -xx
        x2 = x - sy
        y2 = y - sx
    elif transform == 'rotate(90)':
        x = -yy
        y = xx
        x2 = x + sy
        y2 = y + sx
    elif transform == 'rotate(-180)' or transform == 'rotate(180)' or transform == 'scale(-1)':
        x = -xx
        y = -yy
        x2 = x - sy
        y2 = y + sx
    else:
        x2 = x + sx
        y2 = y - sy
    pt = [x + trans[0], y + trans[1]]
    pt2 = [x2 + trans[0], y2 + trans[1]]
    return (text, Path([pt, pt2]))


parser = argparse.ArgumentParser(description='Polychip.')
parser.add_argument('file', metavar='<file>', type=argparse.FileType('r'), nargs=1,
                    help='input Inkscape SVG file')
args = parser.parse_args()

ns = {'inkscape': 'http://www.inkscape.org/namespaces/inkscape',
      'svg': 'http://www.w3.org/2000/svg'}

tree = ET.parse(args.file[0])
root = tree.getroot()

doc_height = float(root.get('height'))

layer = {}

layer['contacts'] = root.findall(layer_path("Contacts"), ns)[0]
layer['poly'] = root.findall(layer_path("Poly"), ns)[0]
layer['diff'] = root.findall(layer_path("Diff"), ns)[0]
layer['metal'] = root.findall(layer_path("Metal"), ns)[0]
layer['gates'] = root.findall(layer_path("Gates"), ns)[0]
layer['qnames'] = root.findall(layer_path("QNames"), ns)[0]
layer['snames'] = root.findall(layer_path("SNames"), ns)[0]

layer_translates = {}
layer_translates['contacts'] = parse_translate(layer['contacts'].get('transform'))
layer_translates['poly'] = parse_translate(layer['poly'].get('transform'))
layer_translates['diff'] = parse_translate(layer['diff'].get('transform'))
layer_translates['metal'] = parse_translate(layer['metal'].get('transform'))
layer_translates['gates'] = parse_translate(layer['gates'].get('transform'))
layer_translates['qnames'] = parse_translate(layer['qnames'].get('transform'))
layer_translates['snames'] = parse_translate(layer['snames'].get('transform'))

shapes = {}

shapes['contacts'] = root.findall(layer_path("Contacts") + "/svg:rect", ns)
shapes['poly'] = root.findall(layer_path("Poly") + "/svg:path", ns)
shapes['diff'] = root.findall(layer_path("Diff") + "/svg:path", ns)
shapes['metal'] = root.findall(layer_path("Metal") + "/svg:path", ns)
shapes['gates'] = root.findall(layer_path("Gates") + "/svg:path", ns)
shapes['qnames'] = root.findall(layer_path("QNames") + "/svg:text", ns)
shapes['snames'] = root.findall(layer_path("SNames") + "/svg:text", ns)

contacts = {}
for c in shapes['contacts']:
    contacts[c.get('id')] = {'loc': [
        float(c.get('x')) + float(c.get('width'))/2 + layer_translates['contacts'][0],
        float(c.get('y')) + float(c.get('height'))/2 + layer_translates['contacts'][1]]}

print("{:d} contacts".format(len(contacts)))

poly_paths = {}
for p in shapes['poly']:
    poly_paths['p_' + p.get('id')] = {'path': svgpath_to_mppath(p.get('d'), layer_translates['poly']), 
                                      'conn': []}
diff_paths = {}
for p in shapes['diff']:
    diff_paths['d_' + p.get('id')] = {'path': svgpath_to_mppath(p.get('d'), layer_translates['diff']), 
                                      'conn': []}

metal_paths = {}
for p in shapes['metal']:
    metal_paths['m_' + p.get('id')] = {'path': svgpath_to_mppath(p.get('d'), layer_translates['metal']), 
                                       'conn': []}

print("{:d} diffs".format(len(diff_paths)))
print("{:d} metals".format(len(metal_paths)))
print("{:d} polys".format(len(poly_paths)))

calculate_contacts(contacts, metal_paths, diff_paths, poly_paths)
find_bad_contacts(contacts)

qnames = []
for t in shapes['qnames']:
    qnames.append(parse_text(t, layer_translates['qnames'], ns))

transistors = {}
for g in shapes['gates']:
    path = svgpath_to_mppath(g.get('d'), layer_translates['gates'])
    name = 'q_' + g.get('id')
    for n in qnames:
        text, textpath = n
        if textpath.intersects_path(path):
            name = 'q_' + text
            break
    transistors[name] = {'path': path}

print("{:d} transistors".format(len(transistors)))

for qid, q in transistors.items():
    ends = []
    for did, d in diff_paths.items():
        if d['path'].contains_point(q['path'].vertices[0]) or d['path'].contains_point(q['path'].vertices[1]):
            ends.append(did)
    if len(ends) == 0:
        print("Error: Transistor {:s} has no electrode connections".format(qid))
    elif len(ends) == 1:
        print("Error: Transistor {:s} has only one electrode connection".format(qid))
    poly = None
    for pid, p in poly_paths.items():
        if q['path'].intersects_path(p['path']):
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

for t in shapes['snames']:
    text, path = parse_text(t, layer_translates['snames'], ns)
    for paths in [poly_paths, metal_paths, diff_paths]:
        found = False
        for pid, p in paths.items():
            if path.intersects_path(p['path']):
                p['label'] = text
                print("Path {:s} is labeled signal {:s}".format(pid, text))
                found = True
                break
        if found:
            break

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
