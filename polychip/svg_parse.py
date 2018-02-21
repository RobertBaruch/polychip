import xml.etree.ElementTree as ET
import svg.path as svgpath
import re
import shapely
import shapely.geometry

namespaces = {'inkscape': 'http://www.inkscape.org/namespaces/inkscape',
              'svg': 'http://www.w3.org/2000/svg'}


def svgpath_to_shapely_path(p, trans):
    coords = []

    lines = svgpath.parse_path(p)
    for line in lines:
        coord = line.start
        end = line.end
        coords.append((coord.real + trans[0], coord.imag + trans[1]))
    coords.append((end.real + trans[0], end.imag + trans[1]))

    if len(coords) == 2:
        return shapely.geometry.LineString(coords)
    else:
        return shapely.geometry.Polygon(coords)


def parse_translate(s):
    if s is None:
        return [0, 0]
    t = s.split('(')
    t = t[1].split(')')
    t = t[0].split(',')
    x, y = map(float, t)
    return [x, y]


def parse_font_size(style):
    if style is None:
        return 0
    m = re.search('(?<=font-size:)[0-9.]+(?=px)', style)
    if m is None:
        return 0
    return float(m.group(0))


def parse_text_extents(text_element, trans):
    # Count characters in <tspan> elements
    tspans = text_element.findall("svg:tspan", namespaces)
    transform = text_element.get('transform')
    text = "".join(["".join(x.itertext()) for x in tspans])
    xx = float(text_element.get('x'))
    yy = float(text_element.get('y'))
    x = xx
    y = yy

    style = tspans[0].get('style')
    parent_style = text_element.get('style')
    if (style is not None and "font-family:'DejaVu Sans Mono'" not in style
        and parent_style is not None and "font-family:'DejaVu Sans Mono'" not in parent_style):
        print("Warning: font must be DejaVu Sans Mono for " + text)
    font_size = parse_font_size(style)
    parent_font_size = parse_font_size(parent_style)
    if font_size == 0:
        font_size = parent_font_size

    if font_size == 0:
        print("Warning: No pixel-based font size found in text style for " + text)

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
    return (text, pt, pt2)    


def parse_shapely_text(text_element, trans):
    text, pt, pt2 = parse_text_extents(text_element, trans)
    return (text, shapely.geometry.LineString([(pt[0], pt[1]), (pt2[0], pt2[1])]))


def parse_inkscape_svg(file):
    tree = ET.parse(file)
    return tree.getroot()
