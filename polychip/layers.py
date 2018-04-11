import functools
import shapely
import shapely.geometry

from enum import Enum, unique
from svg_parse import *

def coerce_multipoly(poly):
    """Coerces the given poly to be a MultiPoly.

    Results from shapely operations can be Polygons or MultiPolygons. It's convenient to
    have them always be MultiPolygons so that, for example, we can iterate over whatever it
    is that was returned.

    Args:
        poly (shapely.geometry.Polygon or shapely.geometry.MultiPolygon): The poly to coerce.

    Returns:
        shapely.geometry.MultiPolygon: The coerced poly.
    """
    if type(poly) == shapely.geometry.Polygon:
        return shapely.geometry.MultiPolygon([poly])
    return poly


@unique
class Layer(Enum):
    """ Types of layers."""
    METAL = "Metal"
    POLY = "Poly"
    DIFF = "Diff"
    CONTACTS = "Contacts"
    QNAMES = "QNames"
    SNAMES ="SNames"
    PNAMES ="PNames"

    def path(self):
        return "./svg:g[@inkscape:groupmode='layer'][@inkscape:label='" + self.value + "']"


class Label(object):
    """Represents the text and extents of a label.

    Args:
    Attributes:
        text (str): The text of the label.
        extents (shapely.geometry.LineString): A line from bottom beginning
            to top end (relative to the text string, not its orientation).
    """
    def __init__(self, text, extents):
        self.text = text
        self.extents = extents
        self.center = extents.centroid


class InkscapeFile:
    """Represents all the paths and names found in an Inkscape file.

    Args:
        root (xml.etree.ElementTree.Element): The root element for the Inkscape document.

    Attributes:
        contacts (shapely.geometry.MultiPoint): All the found contacts. Each point
            represents the center position of a rectangular contact.
        qnames([Label]): The list of found transistor labels.
        snames([Label]): The list of found signal labels.
        pnames([Label]): The list of found pin labels.
        poly_array([shapely.geometry.Polygon]): The list of found polysilicon polygons.
        metal_array([shapely.geometry.Polygon]): The list of found metal polygons.
        diff_array([shapely.geometry.Polygon]): The list of found diff polygons.
            Note that this will be altered in a later stage when transistors are found.
        multicontact(shapely.geometry.MultiPolygon): All the found contact polygons.
        multipoly(shapely.geometry.MultiPolygon): All the found polysilicon polygons.
        multidiff(shapely.geometry.MultiPolygon): All the found diffusion polygons.
        multimetal(shapely.geometry.MultiPolygon): All the found metal polygons.
    """
    def __init__(self, root):
        self.qnames = []
        self.snames = []
        self.pnames = []
        self.contact_array = []
        self.poly_array = []
        self.metal_array = []
        self.diff_array = []
        self.multicontact = None
        self.multipoly = None
        self.multidiff = None
        self.multimetal = None

        self.to_screen_coords_transform_ = self.extract_screen_transform(root)

        self.transform = {
            Layer.CONTACTS: self.to_screen_coords_transform_,
            Layer.POLY: self.to_screen_coords_transform_,
            Layer.METAL: self.to_screen_coords_transform_,
            Layer.DIFF: self.to_screen_coords_transform_,
            Layer.QNAMES: self.to_screen_coords_transform_,
            Layer.SNAMES: self.to_screen_coords_transform_,
            Layer.PNAMES: self.to_screen_coords_transform_,
        }

        self.contact_paths = {}
        poly_paths = {}
        diff_paths = {}
        metal_paths = {}

        layer = {}

        layer[Layer.CONTACTS] = root.findall(Layer.CONTACTS.path(), namespaces)[0]
        layer[Layer.POLY] = root.findall(Layer.POLY.path(), namespaces)[0]
        layer[Layer.DIFF] = root.findall(Layer.DIFF.path(), namespaces)[0]
        layer[Layer.METAL] = root.findall(Layer.METAL.path(), namespaces)[0]

        namelayer = root.findall(Layer.QNAMES.path(), namespaces)
        if len(namelayer) > 0:
            layer[Layer.QNAMES] = namelayer[0]
        namelayer = root.findall(Layer.SNAMES.path(), namespaces)
        if len(namelayer) > 0:
            layer[Layer.SNAMES] = namelayer[0]
        namelayer = root.findall(Layer.PNAMES.path(), namespaces)
        if len(namelayer) > 0:
            layer[Layer.PNAMES] = namelayer[0]

        for y in (y for y in Layer if y in layer):
            t = Transform.parse(layer[y].get('transform'))
            self.transform[y] = self.transform[y] @ t
        shapes = {}

        shapes[Layer.CONTACTS] = root.findall(Layer.CONTACTS.path() + "/svg:path", namespaces)
        shapes[Layer.CONTACTS] += root.findall(Layer.CONTACTS.path() + "/svg:rect", namespaces)
        shapes[Layer.POLY] = root.findall(Layer.POLY.path() + "/svg:path", namespaces)
        shapes[Layer.POLY] += root.findall(Layer.POLY.path() + "/svg:rect", namespaces)
        shapes[Layer.DIFF] = root.findall(Layer.DIFF.path() + "/svg:path", namespaces)
        shapes[Layer.DIFF] += root.findall(Layer.DIFF.path() + "/svg:rect", namespaces)
        shapes[Layer.METAL] = root.findall(Layer.METAL.path() + "/svg:path", namespaces)
        shapes[Layer.METAL] += root.findall(Layer.METAL.path() + "/svg:rect", namespaces)
        shapes[Layer.QNAMES] = root.findall(Layer.QNAMES.path() + "/svg:text", namespaces)
        shapes[Layer.SNAMES] = root.findall(Layer.SNAMES.path() + "/svg:text", namespaces)
        shapes[Layer.PNAMES] = root.findall(Layer.PNAMES.path() + "/svg:text", namespaces)

        print("Processing {:d} contact paths".format(len(shapes[Layer.CONTACTS])))
        for p in shapes[Layer.CONTACTS]:
            self.contact_paths['c_' + p.get('id')] = svgelement_to_shapely_polygon(p, self.transform[Layer.CONTACTS])

        print("Processing {:d} poly paths".format(len(shapes[Layer.POLY])))
        for p in shapes[Layer.POLY]:
            poly_paths['p_' + p.get('id')] = svgelement_to_shapely_polygon(p, self.transform[Layer.POLY])

        print("Processing {:d} diff paths".format(len(shapes[Layer.DIFF])))
        for p in shapes[Layer.DIFF]:
            diff_paths['p_' + p.get('id')] = svgelement_to_shapely_polygon(p, self.transform[Layer.DIFF])

        print("Processing {:d} metal paths".format(len(shapes[Layer.METAL])))
        for p in shapes[Layer.METAL]:
            metal_paths['p_' + p.get('id')] = svgelement_to_shapely_polygon(p, self.transform[Layer.METAL])

        print("Processing qnames text")
        for t in shapes[Layer.QNAMES]:
            text, extents = parse_shapely_text(t, self.transform[Layer.QNAMES])
            self.qnames.append(Label(text, extents))

        print("Processing snames text")
        for t in shapes[Layer.SNAMES]:
            text, extents = parse_shapely_text(t, self.transform[Layer.SNAMES])
            self.snames.append(Label(text, extents))

        print("Processing pnames text")
        for t in shapes[Layer.PNAMES]:
            text, extents = parse_shapely_text(t, self.transform[Layer.PNAMES])
            self.pnames.append(Label(text, extents))
            self.snames.append(Label(text, extents))

        print("Merging overlapping sections. Before merge:")
        print("{:d} contacts".format(len(self.contact_paths)))
        print("{:d} diffs".format(len(diff_paths)))
        print("{:d} polys".format(len(poly_paths)))
        print("{:d} metals".format(len(metal_paths)))
        print("After merging:")
        # print(diff_paths['p_rect10018'])

        self.multicontact = coerce_multipoly(shapely.ops.unary_union(
            [p for p in self.contact_paths.values() if p is not None]))
        self.contact_array = list(self.multicontact.geoms)
        list.sort(self.contact_array, key = functools.cmp_to_key(InkscapeFile.poly_cmp))
        print("{:d} contacts".format(len(self.contact_array)))

        self.multidiff = coerce_multipoly(shapely.ops.unary_union(
            [p for p in diff_paths.values() if p is not None]))
        self.diff_array = list(self.multidiff.geoms)
        list.sort(self.diff_array, key = functools.cmp_to_key(InkscapeFile.poly_cmp))
        print("{:d} diffs".format(len(self.diff_array)))

        self.multipoly = coerce_multipoly(shapely.ops.unary_union(
            [p for p in poly_paths.values() if p is not None]))
        self.poly_array = list(self.multipoly.geoms)
        list.sort(self.poly_array, key = functools.cmp_to_key(InkscapeFile.poly_cmp))
        print("{:d} polys".format(len(self.poly_array)))

        self.multimetal = coerce_multipoly(shapely.ops.unary_union(
            [p for p in metal_paths.values() if p is not None]))
        self.metal_array = list(self.multimetal.geoms)
        list.sort(self.metal_array, key = functools.cmp_to_key(InkscapeFile.poly_cmp))
        print("{:d} metals".format(len(self.metal_array)))

        print("{:d} qnames".format(len(self.qnames)))
        print("{:d} snames".format(len(self.snames)))
        print("{:d} pnames".format(len(self.pnames)))


    def extract_screen_transform(self, root):
        """Extracts the height, in pixels, of the document.

        Args:
            root (xml.etree.ElementTree.Element): The root element for the Inkscape document.

        Returns:
            Transform: The transform to get from SVG coordinates to Inkscape screen coordinates.
        """
        height = root.get('height')
        width = root.get('width')
        xdpi = root.get(qname(root, "inkscape:export-xdpi"))
        ydpi = root.get(qname(root, "inkscape:export-ydpi"))
        if height.endswith('mm'):
            h = float(xdpi) * float(height[:-2]) / 25.4
        else:
            h = float(height)

        if width.endswith('mm'):
            w = float(ydpi) * float(width[:-2]) / 25.4
        else:
            w = float(width)

        transform = Transform(1, 0, 0, -1, 0, h)

        # If there's a viewBox, then the document scale needs adjustment.
        viewbox = root.get('viewBox')
        if viewbox is None:
            return transform
        extents = [float(x) for x in re.split('[, ]', viewbox)]
        scalex = w / extents[2]
        scaley = h / extents[3]
        return transform @ Transform.scale(scalex, scaley)


    def replace_diff_array(self, diffs):
        """Replaces the drawing's diff_array with the given one, sorting it first.

        This happens after transistors are identified. The transistor gates split existing
        diffs in two.

        Args:
            diffs ([shapely.geometry.Polygon]): The array of diff polygons.
        """
        self.diff_array = diffs
        list.sort(self.diff_array, key = functools.cmp_to_key(InkscapeFile.poly_cmp))


    @staticmethod
    def poly_cmp(poly1, poly2):
        """Provides an ordering for two polygons based on their bounding box.

        The polygon whose bounding box is leftmost of the two is the lower one. If both polygons are
        left-aligned, then the polygon that is lowermost of the two is the lower one.

        Args:
            poly1 (shapely.geometry.Polygon): The first polygon to compare.
            poly2 (shapely.geometry.Polygon): The polygon to compare the first polygon to.

        Returns:
            int:
                -1 if poly1 is "less than" poly2
                1 if poly1 is "greater than" poly2
                0 if poly1 is "equal to" poly 2

        """
        minx1, miny1, _, _ = poly1.bounds
        minx2, miny2, _, _ = poly2.bounds
        if minx1 < minx2:
            return -1
        if minx1 > minx2:
            return 1
        if miny1 < miny2:
            return -1
        if miny1 > miny2:
            return 1
        return 0
