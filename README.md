# PCBooker

PCB fabrication toolkit — Gerber viewer, isolation routing, HPGL export for laser engraving.

## PCBooker GUI (v0.1)

Python GUI for PCB laser engraving preparation:
- Multi-layer Gerber loading (auto layer detection via gerbonara)
- Per-layer controls: visible, outline/inline mode, offset in mm
- Isolation path generation (Shapely polygon buffer)
- Open contour detection with visual gap markers
- HPGL export for vector laser engraver

### Dependencies

    pip install gerbonara shapely matplotlib

### Usage

    python3 pcbooker.py                     # open GUI
    python3 pcbooker.py /path/to/gerbers    # auto-load Gerber directory

## Legacy Tools

### drill2gcode (Perl)
Excellon DRL to G-code converter with helix pocket drilling for holes > 3.0mm.
Uses CADSTAR 7.6 REP files for tool definitions.

    perl drill/drill2gcode.pl input.drl tools.rep

### grb2hpgl (Shell)
Gerber to HPGL converter using pcb2gcode backend.

    cd gerber && ./go.sh

## Submodules

- `pcb2gcode` — reference C++ Gerber-to-Gcode converter
- `bCNC` — CNC control software (Python/Tkinter)

## TODO

- Raster hatching mode (simulated raster via horizontal/vertical interrupted HPGL lines)
- PPM frequency correction for CW generator integration
- Multi-pass isolation with configurable overlap

## License

GPL-2.0

## Authors

SCteam (smooker/LZ1CCM)
