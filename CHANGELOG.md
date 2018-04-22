# v0.8 (22 Apr 2018)
* Adds signal booster, pin inputs and pin i/o gates and schematic symbols. NOT TESTED.
* Adds --output and --input options, so that you can output the results of an SVG analysis as JSON, and input the results on later runs to save time. This is useful when you're working on the code for recognizing more gates, and don't need to re-analyze the drawing because it hasn't changed.
* Adds OR gates, schematic output up to 6-OR.
* Adds schematic output up to 3-NAND.
* Adds truth tables to LUTs up to 10-LUT, and puts table in schematic (in component details) up to 7-LUT.
* numpy is now required, for truth table input permutation. Although this feature isn't yet used.

# v0.7 (14 Apr 2018)
* Adds 5-NOR and 6-NOR schematic symbols.
* Adds a powermux schematic symbol.

# v0.6 (10 Apr 2018)
* Adds pullup recognition
* Adds PNames layer for labeling pins. Pins are also signals, so no need to include the name on the SNames layer.
* Speeds up contact finding from O(N^2) to O(N log N).
* Errors out with diagnostics if a non-power/non-ground signal name connects to a power or ground net, since you probably didn't want that.
* Adds pulldowns, pullups, and pins on the schematic.

# v0.5 (28 Mar 2018)
* Combinatorial gate recognition ("Look-Up Table", or LUT)
* Improved pass transistor recognition algorithm
* Adds more symbols to schematic, adds power and ground connections on transistors.
* More tests added for LUTs, NANDs, pass transistors, mux-based D-latch.

# v0.4.2 (25 Mar 2018)
* Preliminary recognition of multiplexer-based D-latches.
* Preliminary wiring in schematic.
* One of the O(N log N) steps in transistor recognition improved to O(log N).

# v0.4.1 (19 Mar 2018)
* Fixes bug where non-rectangular contacts weren't being recognized.
* Preliminary recognition of pulldown and pass transistors.

# v0.4 (18 Mar 2018)
* Preliminary KiCAD schematic output (gates and transistors only, no wires yet).
* Detects if power is shorted to ground, refuses analysis past that point.
* More gate recognition:
    * Multiplexers and power multiplexers are now found.
    * Tristate inverters and buffers are now found.
    * Parallel transistors that are connected to power or ground are now found and treated as single transistors for gate recognition.
* Added tests for gate recognition.
* Adds --nets and --qs options to print netlist and transistor list.

# v0.3 (10 Mar 2018)
* Contacts may now also be polygons.
* Diff, poly, and metal may now also be rectangles.
* The cubic Bezier curves c, C are now accepted in paths, and handled by approximating with three segments (four points).
* Self-crossing paths are detected and verbosely reported for correction.
* SVG multi-shell and multi-hole paths are now properly handled.
* n-input NOR gates and power NOR gates are now found (a 1-input NOR gate is an inverter)
    * The test/qnames.svg file contains an inverter.
    * Note that drivers formed from parallel transistors are not yet handled.
* Any signal name starting with 'VCC' or 'VDD' is considered power.
* Any signal name starting with 'VSS' or 'GND' is considered ground.
* Added tests for various Inkscape path weirdness:
    * floating-point inaccuracy from relative moves
    * zero-length segments
    * shells that are clockwise (right-hand rule -> negative area)
    * self-crossing paths
    * multi-shell paths
