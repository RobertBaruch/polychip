# polychip
Python app to extract a netlist of NMOS transistors from an Inkscape diagram.

Open the `polychip-template.svg` file in Inkscape. Instructions on how to organize your drawing is in that file.

The Python 3 app is dependent on [`matplotlib`](https://matplotlib.org/) and [`networkx`](https://networkx.github.io/). These can be installed via pip.

You can run the program like so:

`$ python3 polychip.py <svg-file>`

The output will show you how many transistors, contacts, diff, poly, and metal were found. Errors are displayed for contacts only attaching one diff, poly, or metal, and for text that violates the requirements set forth in the template file. Errors are also displayed for poly, diff, or metal not connected to anything else, and for transistors with fewer than two electrodes detected.

The netlist is an array of tuples. The first element of the tuple is the net name, or None if no net name was defined for the net on the SNames layer. The second element is a set of transistor names, of the format `q_<name>_<terminal>`, where `<name>` is either the name of the transistor as defined on the QNames layer, or a unique path name defined by Inkscape, and `<terminal>` is `g` for the gate, and `e0` and `e1` for the two electrodes.
