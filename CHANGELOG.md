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