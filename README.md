# polychip
Python program to extract a netlist of NMOS transistors from an Inkscape diagram.

## Prerequisites

### Python 3.6 or above
* Windows: Get it [here](https://www.python.org/downloads/). Alternatively, run Bash on Ubuntu on Windows and follow the instructions for Ubuntu 14.04.
* Ubuntu: Run `lsb_release -a` to determine your Ubuntu version. Then follow the advice given [here](https://askubuntu.com/questions/865554/how-do-i-install-python-3-6-using-apt-get) under the appropriate version.
* Debian: Follow the advice given [here](https://unix.stackexchange.com/questions/332641/how-to-install-python-3-6).
* OSX: Get it [here](https://www.python.org/downloads/mac-osx/)

### Python packages: install with pip
`$ pip3 -V`

If the above doesn't show your version of python, then you'll have to read up on using virtual environments. If you never want to use a previous version of python again, then feel free to overwrite pip like so: `curl https://bootstrap.pypa.io/get-pip.py | sudo python3.6` (or whatever your python version is).

Then:
`$ sudo pip3 install -r requirements.txt`

## Instructions
Open the `polychip-template.svg` file in Inkscape. Instructions on how to organize your drawing is in that file.

You can run the program like so:

`$ python3.6 polychip/polychip.py <svg-file>`

Try it out on `polychip-template.svg`!

The output will show you how many transistors, contacts, diff, poly, and metal were found. Errors are displayed for contacts only attaching one diff, poly, or metal, and for text that violates the requirements set forth in the template file. Errors are also displayed for poly, diff, or metal not connected to anything else, and for transistors with fewer than two electrodes detected.

The netlist is an array of tuples. The first element of the tuple is the net name, or None if no net name was defined for the net on the SNames layer. The second element is a set of transistor connections, of the format `(Type.terminal>, qname`, where `<terminal>` is GATE for the gate, and E0 and E1 for the two electrodes (N is meaningless), and `qname` is either the name of the transistor as defined on the QNames layer, or a unique number.

You can run all tests like so:

`$ python3.6 polychip/tests.py`
