"""Arch viewer: draws the module map `generated/modules.json` (contract C4).

Jargon
------
Module map
    `spec/BioMech/Architecture.lean`, exported to `generated/modules.json`: every
    module, the APIs between modules, and which module generates and which consumes.
Layer
    Row of the drawing; layer 0 is the top. Generators sit above their consumers.
Detail
    Zoom level 0-3: 0 names and arrows, 1 boxes with API names, 2 adds a head line
    per box, 3 adds owned paths, acceptance commands and API files.
Lane
    Horizontal row in the gap between two layers that carries one API.
Gutter
    Vertical column left of all boxes that carries an API past intermediate layers.

Layout of the package: `model` loads and validates the map; `layout` orders boxes and
assigns lanes; `content` holds the text of a box; `route` joins ports with orthogonal
paths; `text` and `svg` draw; `watch` is the terminal UI; `cli` parses arguments.
"""
