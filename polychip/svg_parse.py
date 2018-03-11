import copy
import math
import re
import shapely
import shapely.geometry
import shapely.validation
import sys
import traceback

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


def add_relative_point_to_path(dx, dy, path):
    if math.fabs(dx) + math.fabs(dy) < 0.01:
        return
    path.append((path[-1][0] + dx, path[-1][1] + dy))


def add_absolute_point_to_path(x, y, path):
    if len(path) == 0:
        path.append((x, y))
        return
    add_relative_point_to_path(x - path[-1][0], y - path[-1][1], path)


def svgelement_to_shapely_polygon(element, trans, debug = False):
    if element.tag.endswith('rect'):
        return svgrect_to_shapely_path(element, trans, debug)
    if element.tag.endswith('path'):
        return svgpath_to_shapely_path(element, trans, debug)
    else:
        print("Error: unknown element skipped: " + element.tag)
        return None


def svgrect_to_shapely_path(element, trans, debug = False):
    """Converts an svg <rect> element into a shapely.geometry.Polygon.

    Args:
        element (etree.Element): The svg <rect> element.
        trans (Transform): The parent element's transform.

    Returns:
        shapely.geometry.Polygon: The polygon.
    """
    transform = (trans @ Transform.parse(element.get('transform'))).to_shapely_transform()
    x = float(element.get('x'))
    y = float(element.get('y'))
    x2 = x + float(element.get('width'))
    y2 = y + float(element.get('height'))
    if x > x2:
        x, x2 = x2, x
    if y > y2:
        y, y2 = y2, y
    return shapely.affinity.affine_transform(shapely.geometry.box(x, y, x2, y2), transform)


def polygon_is_topologically_sound(id, polygon):
    """Returns whether a polygon with no holes is topologically sound.

    Assumes the polygon is oriented counter-clockwise (right-hand rule -> positive area).

    If a polygon crosses itself, some bits of its area will be negative. Subtracting the polygon
    from its own bounding box will likely result in shapely throwing an exception.
    """
    minx, miny, maxx, maxy = polygon.bounds
    bounding_box = shapely.geometry.box(minx, miny, maxx, maxy)
    try:
        leftovers = bounding_box.difference(polygon)
        return True
    except shapely.errors.TopologicalError:
        assert False, ("Warning: Skipping path {:s} which starts at {:s} because it is topologically "
            "unsound (e.g. crosses itself).".format(
                id, str((polygon.exterior.coords[0][0], polygon.exterior.coords[0][1]))))

def cubic_bezier_point(t, p0, p1, p2, p3):
    """Returns the point along the bezier curve corresponding to the parameter t.

    Args:
        t (float): The parameter (0 <= t <= 1).
        p0 ((float, float)): The (x, y) coordinates of the starting point.
        p1 ((float, float)): The coordinates of the first control point.
        p2 ((float, float)): The coordinates of the second control point.
        p3 ((float, float)): The coordinates of the ending point.

    Returns:
        (float, float): The coordinate of the point.
    """
    assert t >= 0 and t <= 1
    x = ((1 - t) * (1 - t) * (1 - t) * p0[0] + 3 * t * (1 - t) * (1 - t) * p1[0] +
        3 * t * t * (1 - t) * p2[0] + t * t * t * p3[0])
    y = ((1 - t) * (1 - t) * (1 - t) * p0[1] + 3 * t * (1 - t) * (1 - t) * p1[1] +
        3 * t * t * (1 - t) * p2[1] + t * t * t * p3[1])
    return (x, y)


def cubic_bezier_points(n, p0, p1, p2, p3):
    """Returns n points along the cubic bezier curve.

    The points are not evenly spaced, but they are in parameter space (t):

    B(t) = p0*(1-t)^3 + 3p1*t(1-t)^2 + 3p2*t^2(1-t) + p3 * t^3 (0 <= t <= 1)

    Args:
        n (int): The number of points to return. Minimum 2 (i.e. the endpoints).
        p0 ((float, float)): The (x, y) coordinates of the starting point.
        p1 ((float, float)): The coordinates of the first control point.
        p2 ((float, float)): The coordinates of the second control point.
        p3 ((float, float)): The coordinates of the ending point.

    Returns:
        [(float, float)]: An array of n coordinates along the curve.
    """
    assert n >= 2
    return [cubic_bezier_point(t, p0, p1, p2, p3) for t in (float(x) / (n - 1) for x in range(n))]


def svgpath_to_shapely_path(element, trans, debug = False):
    """Converts an svg <path> element into a shapely.geometry.Polygon.

    Only supports moveto, lineto, vertical, and horizontal. No curves!

    It seems that an svg path starts with a shell, which may be clockwise or counter-clockwise.
    Then, for every following subpath, it is another shell if it has the same orientation, or
    a hole if it has the opposite orientation.

    For consistency, we modify the orientations so thatshells are always counter-clockwise
    (right-hand rule -> positive area) and holes are clockwise (right-hand rule -> negative area).

    When a path is explicity closed (i.e. a -> b -> c -> a) and the points are relative moves, 
    and then followed by 'z' to close the path, there is the problem of floating point inaccuracy making
    the last 'a' not equal to the first 'a'. Thus, when we hit the 'z' at the end of the path, we check
    to see if the last 'a' is sufficiently close to the first 'a'. If so, eliminate the last 'a'. This
    lets shapely close the path exactly by using the first 'a' as the last 'a' instead.

    If two neighboring points are very close to each other, or on top of each other, they are merged.

    Args:
        element (etree.Element): The svg <path> element.
        trans (Transform): The parent element's transform.

    Returns:
        shapely.geometry.Polygon: The polygon found, or None otherwise.
    """
    path_id = element.get('id')
    path_string = element.get('d')
    start_point = None
    transform = (trans @ Transform.parse(element.get('transform'))).to_shapely_transform()

    try:
        tokens = re.split('[, ]', path_string)
        rings = []
        i = 0;
        endpoint = (0, 0)
        coords = []
        last_command = None
        commands = "cCmMlLvVhHzZ"
        # The curves we don't yet support
        unsupported_commands = "qQtTsSA"

        while i < len(tokens):
            if tokens[i] == "":
                i += 1
                continue

            elif tokens[i] in unsupported_commands:
                print("Warning: {:s}-curves in paths are not supported. Skipping path {:s}, curve starts at {:s}".format(
                    tokens[i], path_id, str((point.x, point.y))))
                return None

            elif tokens[i] not in commands:
                command = last_command

            else:
                command = tokens[i]
                last_command = command
                i += 1

            if command == 'm':
                last_command = 'l'
                dx = float(tokens[i])
                dy = float(tokens[i + 1])
                add_absolute_point_to_path(endpoint[0] + dx, endpoint[1] + dy, coords)
                i += 2

            elif command == 'M':
                last_command = 'L'
                x = float(tokens[i])
                y = float(tokens[i + 1])
                add_absolute_point_to_path(x, y, coords)
                i += 2

            elif command == 'c':
                px0 = coords[-1][0]
                py0 = coords[-1][1]
                px1 = px0 + float(tokens[i])
                py1 = py0 + float(tokens[i + 1])
                px2 = px0 + float(tokens[i + 2])
                py2 = py0 + float(tokens[i + 3])
                px3 = px0 + float(tokens[i + 4])
                py3 = py0 + float(tokens[i + 5])
                for p in cubic_bezier_points(4, (px0, py0), (px1, py1), (px2, py2), (px3, py3)):
                    add_absolute_point_to_path(p[0], p[1], coords)
                i += 6

            elif command == 'C':
                px0 = coords[-1][0]
                py0 = coords[-1][1]
                px1 = float(tokens[i])
                py1 = float(tokens[i + 1])
                px2 = float(tokens[i + 2])
                py2 = float(tokens[i + 3])
                px3 = float(tokens[i + 4])
                py3 = float(tokens[i + 5])
                for p in cubic_bezier_points(4, (px0, py0), (px1, py1), (px2, py2), (px3, py3)):
                    add_absolute_point_to_path(p[0], p[1], coords)
                i += 6

            elif command == 'l':
                dx = float(tokens[i])
                dy = float(tokens[i + 1])
                add_relative_point_to_path(dx, dy, coords)
                i += 2

            elif command == 'L':
                x = float(tokens[i])
                y = float(tokens[i + 1])
                add_absolute_point_to_path(x, y, coords)
                i += 2

            elif command == 'h':
                dx = float(tokens[i])
                add_relative_point_to_path(dx, 0, coords)
                i += 1

            elif command == 'H':
                x = float(tokens[i]) 
                add_absolute_point_to_path(x, coords[-1][1], coords)
                i += 1

            elif command == 'v':
                dy = float(tokens[i])
                add_relative_point_to_path(0, dy, coords)
                i += 1

            elif command == 'V':
                y = float(tokens[i])
                add_absolute_point_to_path(coords[-1][0], y, coords)
                i += 1

            elif command == 'z' or command == 'Z':
                # Taxicab distance here is good enough.
                # See the explanation in the docs above for why we're doing this.
                if math.fabs(coords[0][0] - coords[-1][0]) + math.fabs(coords[0][1] - coords[-1][1]) < 0.01:
                    coords = coords[:-1]
                endpoint = (coords[0][0], coords[0][1])
                ring = shapely.geometry.LinearRing(coords)
                ring = shapely.affinity.affine_transform(ring, transform)
                rings.append(ring)
                coords = []

            else:
                raise AssertionError("Unexpected line command " + tokens[i])

        if len(rings) == 1 and len(rings[0].coords) == 2:
            return shapely.geometry.LineString(rings[0])

        polygon = None
        shell_orientation = None
        if debug:
            print("++ Start path {:s}".format(path_id))
        for ring in rings:
            subpolygon = shapely.geometry.polygon.orient(shapely.geometry.Polygon(ring))
            if not polygon_is_topologically_sound(path_id, subpolygon):
                return None
            if shell_orientation is None:
                shell_orientation = ring.is_ccw
            ring_orientation = ring.is_ccw
            if ring_orientation != shell_orientation:
                if debug:
                    print("  -- hole (orientation: {!r:s})".format(ring_orientation))
                polygon = polygon.difference(subpolygon)
            else:
                if debug:
                    print("  ++ shell (orientation: {!r:s})".format(ring_orientation))
                if polygon is None:
                    polygon = subpolygon
                else:
                    polygon = polygon.union(subpolygon) 
        if debug:
            print("++ End path: {:s}".format(str(polygon)))

        return polygon

    except:
        traceback.print_exc()
        assert False, ("Failed to parse path id {:s}. Path 'd' was: '{:s}'".format(path_id, path_string))


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
        # print("Warning: font must be DejaVu Sans Mono for '{:s}' at {:s}. Assigning this text to"
        #     " a signal will not be accurate.".format(
        #     text, str(pt1)))
        pass
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
