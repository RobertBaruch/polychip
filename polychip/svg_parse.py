import copy
import math
import re
import shapely
import shapely.geometry

from lxml import etree

namespaces = {'inkscape': 'http://www.inkscape.org/namespaces/inkscape',
              'svg': 'http://www.w3.org/2000/svg'}


class Transform(object):
    """Represents a transformation matrix.

    A transformation [a, b, c, d, e, f] is equivalent to the matrix:
        / a c e \
        | b d f |
        \ 0 0 1 /

    Transforming a point [x, y] by this matrix is equivalent to:
        / xx \   / a c e \   / x \
        | yy | = | b d f | * | y |
        \ 1  /   \ 0 0 1 /   \ 1 /
    """
    def __init__(self, a, b, c, d, e, f):
        self.a = float(a)
        self.b = float(b)
        self.c = float(c)
        self.d = float(d)
        self.e = float(e)
        self.f = float(f)


    def __matmul__(self, t2):
        """Multiplies this transform by t2. Triggered by the Python 3.5 @-operator.

        Returns:
            Transform: The new transform.
        """
        t1 = self
        if type(t2) == Transform:
            return Transform(
                t1.a * t2.a + t1.c * t2.b,
                t1.b * t2.a + t1.d * t2.b,
                t1.a * t2.c + t1.c * t2.d,
                t1.b * t2.c + t1.d * t2.d,
                t1.a * t2.e + t1.c * t2.f + t1.e,
                t1.b * t2.e + t1.d * t2.f + t1.f)
        raise TypeError("unsupported operand type(s) for @: 'Transform' and '{:s}'".format(
            str(type(t2))))


    def __imatmul__(self, t2):
        """Multiplies this transform in-place by t2. Triggered by the Python 3.5 @=-operator.
        """
        t1 = self
        if type(t2) == Transform:
            a = t1.a * t2.a + t1.c * t2.b
            b = t1.b * t2.a + t1.d * t2.b
            c = t1.a * t2.c + t1.c * t2.d
            d = t1.b * t2.c + t1.d * t2.d
            e = t1.a * t2.e + t1.c * t2.f + t1.e
            f = t1.b * t2.e + t1.d * t2.f + t1.f
            self.a = a
            self.b = b
            self.c = c
            self.d = d
            self.e = e
            self.f = f
            return self
        raise TypeError("unsupported operand type(s) for @=: 'Transform' and '{:s}'".format(
            str(type(t2))))


    def __repr__(self):
        """Returns the Python representation of this transform."""
        return "Transform({:f}, {:f}, {:f}, {:f}, {:f}, {:f})".format(
            self.a, self.b, self.c, self.d, self.e, self.f)


    def to_shapely_transform(self):
        """Returns a transform suitable for use with shapely."""
        return [self.a, self.c, self.b, self.d, self.e, self.f]


    @staticmethod
    def identity():
        """Returns a transform that does nothing."""
        return Transform(1, 0, 0, 1, 0, 0)


    @staticmethod
    def translate(x, y):
        """Returns a translation transform."""
        return Transform(1, 0, 0, 1, x, y)

    @staticmethod
    def rotate(a):
        """Returns a transform that rotates by a.

        Args:
            a (float): radians of rotation.
        """
        return Transform(math.cos(a), math.sin(a), -math.sin(a), math.cos(a), 0, 0)

    @staticmethod
    def scale(x, y):
        """Returns a scale transform."""
        return Transform(x, 0, 0, y, 0, 0)

    @staticmethod
    def parse(transform):
        """Attempts to convert the content of transform element to a transform matrix.

        Args:
            transform (str): The content of the transform element. If None, the returned
                transform is identity.

        Returns:
            Transform: The transform parsed from the content of the transform element. 
        """
        if transform is None:
            return Transform.identity()

        splits = re.split('[()]', transform)
        t = Transform.identity()
        while len(splits) >= 2:
            t @= Transform.parse_(splits)
            splits = splits[2:]
        return t


    @staticmethod
    def parse_(splits):
        """Attempts to convert the content of transform element to a transform matrix.

        Args:
            splits ([str]): The split content of the transform element.

        Returns:
            Transform: The transform parsed from the content of the transform element. 
        """
        params = [float(x) for x in re.split('[, ]', splits[1])]
        if splits[0] == "matrix":
            return Transform(params[0], params[1], params[2], params[3], params[4], params[5])
        if splits[0] == "translate":
            x = params[0]
            y = 0
            if len(params) > 1:
                y = params[1]
            return Transform.translate(x, y)
        if splits[0] == "rotate":
            a = params[0] * math.pi / 180
            r = Transform.rotate(a)
            if len(params) == 1:
                return r
            x = params[1]
            y = params[2]
            t1 = Transform.translate(x, y)
            t2 = Transform.translate(-x, -y)
            return t1 @ r @ t2
        if splits[0] == "scale":
            x = params[0]
            y = x
            if len(params) > 1:
                y = params[1]
            return Transform.scale(x, y)
        if splits[0] == "skewX":
            a = params[0] * math.pi / 180
            return Transform(1, 0, math.tan(a), 1, 0, 0)
        if splits[0] == "skewY":
            a = params[0] * math.pi / 180
            return Transform(1, math.tan(a), 0, 1, 0, 0)
        raise AssertionError("Unknown transform type " + splits[0])


def qname(element, qtag):
    """Returns the qualified tag name for the given name.

    Args:
        element (etree.Element): The element to provide the namespace context, i.e., which
            namespaces are defined at this point.
        qtag (str): The qualified tag in namespaceprefix:tag format, which is how you'll
            see it in the actual XML document.

    Returns:
        etree.QName: A qualified tag name.
    """
    splits = qtag.split(":")
    return etree.QName(element.nsmap[splits[0]], splits[1])


def svgpath_to_shapely_path(element, trans):
    """Converts an svg <path> element into a shapely.geometry.Polygon.

    Only supports moveto and lineto. No curves!

    It seems that for paths with holes, the shell (outer path) comes first, then the holes (inner paths).

    Args:
        element (etree.Element): The svg <path> element.
        trans (Transform): The parent element's transform.

    Returns:
        shapely.geometry.Polygon: The polygon.
    """
    tokens = re.split('[, ]', element.get('d'))
    polys = []
    i = 0;
    x = 0
    y = 0
    coords = []
    relative_mode = False
    commands = {'m', 'M', 'l', 'L', 'v', 'V', 'h', 'H', 'z'}

    while i < len(tokens):
        if tokens[i] == "":
            i += 1

        elif tokens[i] not in commands:
            if relative_mode:
                x2 = x + float(tokens[i])
                y2 = y + float(tokens[i + 1])
            else:
                x2 = float(tokens[i])
                y2 = float(tokens[i + 1])
            coords.append((x2, y2))
            x = x2
            y = y2
            i += 2

        elif tokens[i] == 'm':
            relative_mode = True
            x += float(tokens[i + 1])
            y += float(tokens[i + 2])
            coords.append((x, y))
            i += 3

        elif tokens[i] == 'M':
            relative_mode = False
            x = float(tokens[i + 1])
            y = float(tokens[i + 2])
            coords.append((x, y))
            i += 3

        elif tokens[i] == 'l':
            relative_mode = True
            x2 = x + float(tokens[i + 1])
            y2 = y + float(tokens[i + 2])
            coords.append((x2, y2))
            x = x2
            y = y2
            i += 3
        elif tokens[i] == 'L':
            relative_mode = False
            x2 = float(tokens[i + 1])
            y2 = float(tokens[i + 2])
            coords.append((x2, y2))
            x = x2
            y = y2
            i += 3
        elif tokens[i] == 'h':
            x2 = x + float(tokens[i + 1])
            coords.append((x2, y))
            x = x2
            i += 2
        elif tokens[i] == 'H':
            x2 = float(tokens[i + 1])
            coords.append((x2, y))
            x = x2
            i += 2
        elif tokens[i] == 'v':
            y2 = y + float(tokens[i + 1])
            coords.append((x, y2))
            y = y2
            i += 2
        elif tokens[i] == 'V':
            y2 = float(tokens[i + 1])
            coords.append((x, y2))
            y = y2
            i += 2
        elif tokens[i] == 'z':
            polys.append(coords)
            # Start at start point of this path.
            x = coords[0][0]
            y = coords[0][1]
            coords = []
            i += 1
        else:
            raise AssertionError("Unknown line command " + tokens[i])

    transform = (trans @ Transform.parse(element.get('transform'))).to_shapely_transform()

    if len(polys) == 1 and len(polys[0]) == 2:
        return shapely.affinity.affine_transform(
            shapely.geometry.LineString(polys[0]), transform)

    shell = polys[0]
    holes = None
    if len(polys) > 1:
        holes = polys[1:]

    return shapely.affinity.affine_transform(
        shapely.geometry.Polygon(shell, holes), transform)


def parse_font_size(style):
    if style is None:
        return 0
    m = re.search('(?<=font-size:)[0-9.]+(?=px)', style)
    if m is None:
        return 0
    return float(m.group(0))


def parse_text_extents(text_element, trans):
    """Parses a text element.

    Args:
        text_element (etree.Element): the text element to parse.
        trans (Transform): the parent element's transform.

    Returns:
        (str, shapely.geometry.Point, shapely.geometry.Point): A tuple of
            (text, beginning lower, end upper).
    """
    # Count characters in <tspan> elements
    tspans = text_element.findall(qname(text_element, "svg:tspan"))
    text_transform = Transform.parse(text_element.get('transform'))
    transform = trans @ text_transform
    text = "".join(["".join(x.itertext()) for x in tspans])
    x = float(text_element.get('x'))
    y = float(text_element.get('y'))
    pt1 = shapely.affinity.affine_transform(shapely.geometry.Point(x, y), 
        transform.to_shapely_transform())

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
    capital_char_height = 16.135 * font_size / 21.33333
    char_width = (36.8 / 3) * font_size / 21.33333

    x2 = x + len(text) * char_width
    y2 = y - capital_char_height

    pt2 = shapely.affinity.affine_transform(shapely.geometry.Point(x2, y2), 
        transform.to_shapely_transform())
    return (text, pt1, pt2)    


def parse_shapely_text(text_element, trans):
    text, pt, pt2 = parse_text_extents(text_element, trans)
    return (text, shapely.geometry.LineString([(pt.x, pt.y), (pt2.x, pt2.y)]))


def parse_inkscape_svg(file):
    tree = etree.parse(file)
    return tree.getroot()
