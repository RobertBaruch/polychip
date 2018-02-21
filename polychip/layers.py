from svg_parse import *
import shapely
import shapely.geometry

def layer_path(name):
    return "./svg:g[@inkscape:groupmode='layer'][@inkscape:label='" + name + "']"

def to_inkscape_coords(pt, doc_height):
    return [pt.x, doc_height - pt.y]

def parse_layers(root):
    layer = {}

    layer['contacts'] = root.findall(layer_path("Contacts"), namespaces)[0]
    layer['poly'] = root.findall(layer_path("Poly"), namespaces)[0]
    layer['diff'] = root.findall(layer_path("Diff"), namespaces)[0]
    layer['metal'] = root.findall(layer_path("Metal"), namespaces)[0]
    layer['gates'] = root.findall(layer_path("Gates"), namespaces)[0]
    layer['qnames'] = root.findall(layer_path("QNames"), namespaces)[0]
    layer['snames'] = root.findall(layer_path("SNames"), namespaces)[0]

    layer_translates = {}
    layer_translates['contacts'] = parse_translate(layer['contacts'].get('transform'))
    layer_translates['poly'] = parse_translate(layer['poly'].get('transform'))
    layer_translates['diff'] = parse_translate(layer['diff'].get('transform'))
    layer_translates['metal'] = parse_translate(layer['metal'].get('transform'))
    layer_translates['gates'] = parse_translate(layer['gates'].get('transform'))
    layer_translates['qnames'] = parse_translate(layer['qnames'].get('transform'))
    layer_translates['snames'] = parse_translate(layer['snames'].get('transform'))

    shapes = {}

    shapes['contacts'] = root.findall(layer_path("Contacts") + "/svg:rect", namespaces)
    shapes['poly'] = root.findall(layer_path("Poly") + "/svg:path", namespaces)
    shapes['diff'] = root.findall(layer_path("Diff") + "/svg:path", namespaces)
    shapes['metal'] = root.findall(layer_path("Metal") + "/svg:path", namespaces)
    shapes['gates'] = root.findall(layer_path("Gates") + "/svg:path", namespaces)
    shapes['qnames'] = root.findall(layer_path("QNames") + "/svg:text", namespaces)
    shapes['snames'] = root.findall(layer_path("SNames") + "/svg:text", namespaces)

    contacts = {}
    for c in shapes['contacts']:
        contacts[c.get('id')] = {'loc': shapely.geometry.Point(
            float(c.get('x')) + float(c.get('width'))/2 + layer_translates['contacts'][0],
            float(c.get('y')) + float(c.get('height'))/2 + layer_translates['contacts'][1])}

    print("{:d} contacts".format(len(contacts)))

    poly_paths = {}
    for p in shapes['poly']:
        poly_paths['p_' + p.get('id')] = {'path': svgpath_to_shapely_path(p.get('d'), layer_translates['poly']), 
                                          'conn': []}
    diff_paths = {}
    for p in shapes['diff']:
        diff_paths['d_' + p.get('id')] = {'path': svgpath_to_shapely_path(p.get('d'), layer_translates['diff']), 
                                          'conn': []}

    metal_paths = {}
    for p in shapes['metal']:
        metal_paths['m_' + p.get('id')] = {'path': svgpath_to_shapely_path(p.get('d'), layer_translates['metal']), 
                                           'conn': []}

    print("{:d} diffs".format(len(diff_paths)))
    print("{:d} metals".format(len(metal_paths)))
    print("{:d} polys".format(len(poly_paths)))

    qnames = []
    for t in shapes['qnames']:
        qnames.append(parse_shapely_text(t, layer_translates['qnames']))

    transistors = {}
    for g in shapes['gates']:
        #path = svgpath_to_mppath(g.get('d'), layer_translates['gates'])
        path = svgpath_to_shapely_path(g.get('d'), layer_translates['gates'])
        name = 'q_' + g.get('id')
        for n in qnames:
            text, textpath = n
            if textpath.intersects(path):
                name = 'q_' + text
                break
        transistors[name] = {'path': path}

    print("{:d} transistors".format(len(transistors)))

    for t in shapes['snames']:
        text, path = parse_shapely_text(t, layer_translates['snames'])
        for paths in [poly_paths, metal_paths, diff_paths]:
            found = False
            for pid, p in paths.items():
                if path.intersects(p['path']):
                    p['label'] = text
                    print("Path {:s} is labeled signal {:s}".format(pid, text))
                    found = True
                    break
            if found:
                break

    return (contacts, poly_paths, diff_paths, metal_paths, qnames, transistors)