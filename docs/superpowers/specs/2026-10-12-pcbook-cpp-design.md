# pcbook: pcbooker's core in C++ (library, CLI, MCP, Qt6 GUI, KiCad plugin)

Date: 2026-10-12. Status: design, waiting for smooker's review.

## Why

pcbooker (Python: gerbonara + shapely + PyQt5/matplotlib) turns Gerber into HPGL for the
TRUMPF VectorMark. smooker wants:
- an API that Claude can drive (MCP) and that a KiCad plugin can call later;
- in **C++, not Python**;
- **no dependence on what the system has installed**: libraries live in the repo.

Decisions already taken (2026-10-12):
- the whole thing in C++, the GUI included (Qt6), with the existing `hpglview` as its view;
- geometry: **Clipper2**, a git submodule;
- Gerber/Excellon: **our own parser** (libgerbv is ruled out: its public header pulls in
  GDK, i.e. GTK2 from the system);
- shape: a library with thin front ends (CLI, MCP, GUI, KiCad plugin), no daemon. Live
  control of a running GUI is a later step on top of the same library.

The Python pcbooker stays as it is and keeps working until the C++ one has caught up. It is
also the test oracle (below).

## Goals

1. `libpcbook`: Gerber + Excellon in; copper geometry, isolation, raster (hatch), checks,
   HPGL out. Same results as the Python pcbooker within stated tolerances.
2. `pcbook` CLI: every step from the command line, JSON on stdout.
3. `pcbook-mcp`: MCP server over stdio, so Claude uses it as tools; renders PNGs itself.
4. `pcbooker-qt`: the GUI, feature for feature with the Python one, plus the hpglview view.
5. A KiCad 10 plugin that runs the chain on the open board.

Dependencies: a C++17 compiler and CMake. Qt6 only for the GUI and hpglview. Everything
else is in the repo (`ext/`). Clipper2 and the header-only libraries below are the only
third-party code.

## Non-goals

- Drawing Gerbers for a fab house, panelising, CAM beyond isolation + raster + drills.
- G-code for drills in C++ (`drill/drill2gcode.pl` stays) -- until asked for.
- A network service. MCP is stdio; the KiCad plugin starts a process.

## Layout

```
pcbooker/
  cpp/
    CMakeLists.txt            top level: lib, cli, mcp, tests always; gui + hpglview if Qt6
    ext/Clipper2/             submodule (AngusJohnson/Clipper2), CPP only
    ext/json/                 nlohmann/json single header (vendored, MIT)
    ext/stb/                  stb_image_write.h (vendored, public domain)
    libpcbook/
      units.h                 internal unit: int64 nanometres (as KiCad); HPGL 5000/127 u/mm
      gerber.{h,cpp}          RS-274X parser -> Layer (polygons with polarity, flattened)
      aperture.{h,cpp}        C, R, O, P, macros (AM primitives 1,4,5,7,20,21) -> polygons
      excellon.{h,cpp}        drill files -> holes (x, y, d)
      geom.{h,cpp}            Clipper2 wrappers: union, offset, difference, clip open paths
      isolation.{h,cpp}       isolation paths, passes, min-gap merge (as isolation.py)
      checks.{h,cpp}          open contours, gap analysis
      dedup.{h,cpp}           skip segments near already-drawn ones (as deduplicate_paths)
      raster.{h,cpp}          hatch: ablate region, angle, pitch, cross, serpentine; outline
      hpgl.{h,cpp}            writer + reader/stats (the reader is hpglview's parser, moved)
      render.{h,cpp}          software PNG rasteriser (anti-aliased lines, polygon fill)
      pcbook.h                the public API (below)
    cli/main.cpp              pcbook
    mcp/main.cpp              pcbook-mcp
    gui/                      pcbooker-qt (Qt6)
    hpglview/                 moved from ../hpglview, links libpcbook for the parser
    tests/                    ctest; fixtures + oracle JSON
  kicad-plugin/               KiCad 10 IPC plugin (step 6)
```

## Units and geometry

- Internal coordinates: `int64` nanometres, the same as KiCad and Clipper2's `Paths64`.
  No floating-point drift between steps; the HPGL writer converts with 5000/127 units per
  mm (**0.0254 mm per unit, not 40**) and rounds once.
- Arcs are flattened when parsed, with a chord error bound (default 1 µm), not a fixed
  segment count. This avoids the Python version's 30 000 repeated points: the writer also
  drops consecutive points that round to the same plotter unit.
- Clipper2 does union, difference, offset (round joins for isolation) and clipping of open
  paths (hatch lines against the ablate region).

## Gerber parser (scope)

What KiCad, Eagle and CADSTAR write, by RS-274X (Gerber X2 attributes are read and
ignored):
- `%FS` (format, leading/trailing zeros, absolute), `%MO` (mm/in);
- `%AD` C, R, O, P (with holes) and `%AM` macros: primitives 1 circle, 4 outline, 5 polygon,
  7 thermal, 20 vector line, 21 centre line, with arithmetic expressions and variables
  (KiCad's RoundRect and FreePoly macros use them);
- D01 (draw), D02 (move), D03 (flash); G01/G02/G03 with G75 (multi-quadrant), G74 if seen;
- regions G36/G37 (with cut-ins);
- `%LP` dark/clear (clear subtracts from what is under it), `%SR` step-repeat, `%AB` blocks;
- unknown commands: counted and reported, never silent.
Excellon: METRIC/INCH, tool table, `T` select, X/Y hits, `G85` slots.

Output per file: `Layer { name, kind (copper/outline/mask/silk/drill/other, guessed from
X2 attributes or file name), Paths64 dark, stats }`.

## Public API (`pcbook.h`)

```cpp
namespace pcbook {
struct Layer;           // name, kind, merged copper (Paths64), holes, parse stats
struct Board { std::vector<Layer> layers; std::optional<Paths64> outline; };

Board  load_files(const std::vector<std::string>& paths);
Board  load_dir(const std::string& dir);

struct IsoParams    { double offset_mm = 0.1; bool inline_ = false; int passes = 1;
                      double pass_step_mm = 0.05; double min_gap_mm = 0.1; };
struct RasterParams { double angle_deg = 45; bool cross = false; double pitch_mm = 0.045;
                      double margin_mm = 1.0; };
struct Paths        { std::vector<Path64> open; };   // laser paths, in order

std::vector<Paths> isolate(const Layer&, const IsoParams&);           // one per pass
Paths              raster (const Layer&, const Board&, double offset_mm, const RasterParams&);
Report             check_contours(const Layer&);
Report             gap_analysis (const Layer&, double offset_mm);
Paths              dedup(const Paths&, double min_dist_mm);
void               write_hpgl(const std::vector<Paths>& in_order, const std::string& file, int pen = 1);
HpglStats          hpgl_stats(const std::string& file);                // the hpglview reader
Image              render(const Board&, const std::vector<Paths>&, int px);  // for PNG
}
```

Errors: exceptions with the file name and line for parse errors; unknown commands go in the
layer's stats, not exceptions.

## Front ends

**CLI `pcbook`** (JSON on stdout, human text on stderr):
- `pcbook info FILES...` -- layers, kinds, bounds, area, unknown commands;
- `pcbook make FILES... --iso 0.05 [--passes N --pass-step 0.05 --min-gap 0.05 --inline]
  [--raster 0|45|cross --pitch 0.045] [--dedup 0.05] -o out.hpgl [--png out.png]`;
- `pcbook check FILES... [--offset 0.1]` -- open contours and narrow gaps;
- `pcbook stats out.hpgl`.

**MCP `pcbook-mcp`**: JSON-RPC 2.0 over stdio (newline-delimited), MCP protocol by hand on
nlohmann/json -- no SDK, no Python, no Node. Tools mirror the CLI: `load`, `info`,
`isolate`, `raster`, `check`, `export_hpgl`, `hpgl_stats`, `render` (PNG returned as image
content). A session keeps the loaded board between calls. Runs in the sf1 chroot (no Qt
needed there: `render` is the software rasteriser).

**GUI `pcbooker-qt`**: the Python GUI's features -- layer list with visibility, Iso, mode,
offset, passes; min gap, pass step, dedup, raster (off / 0° / 45° / 0°+90° cross, pitch);
Check Contours, Gap Analysis, Generate, Delete Selected, Export HPGL; Terminus font -- with
a QPainter view (the hpglview widget extended to filled polygons) instead of matplotlib.

**KiCad plugin**: a KiCad 10 IPC plugin with a toolbar button in the PCB editor: export the
board's copper and Edge.Cuts with `kicad-cli pcb export gerbers` to a temp dir, run `pcbook
make` with the last-used parameters, open the result in `hpglview`. How a KiCad 10 plugin
is declared (Python runtime vs a plain executable) is checked when that step starts.

## Testing

- ctest, plain asserts like `hpglview/tests`; built and run in the chroot (no Qt needed for
  the lib, CLI, MCP and their tests).
- **Oracle:** `tests/oracle/gen.py` (run by hand, uses the Python pcbooker + gerbonara +
  shapely) writes JSON per fixture: copper area, bounds, polygon and hole counts; area of
  the isolation result per offset; hatch length per angle/pitch. The JSON is committed, so
  the C++ tests never need Python. Tolerances: area 0.5 %, bounds 5 µm, lengths 1 %.
- **Fixtures:** `testfiles/1marto.GTL`, `gerber/STMOTOR.GBR`, and the STMBL v4.0 board
  exported with `kicad-cli` (copper, Edge.Cuts, drills) -- KiCad output with macros,
  regions and clear polarity. Plus one small hand-written file per parser feature.
- **Parser units:** each feature (format, each aperture, each macro primitive, arcs, regions,
  LP, SR, AB) has its own small test.
- **End to end:** `pcbook make` on 1marto; `hpgl_stats` of the result against the Python
  pcbooker's export (bbox, cut length 1 %); PNG rendered and looked at.

## Order of work (each step: its own plan, TDD, local commits)

1. Skeleton: `cpp/` CMake, Clipper2 submodule, json/stb vendored, `hpgl` moved in from
   hpglview, oracle generator + JSON for the fixtures.
2. Gerber parser + apertures + macros, then Excellon; oracle tests green on all fixtures.
3. Geometry: isolation (passes, min gap), checks, dedup, raster, outline; oracle tests.
4. CLI + software PNG renderer; end-to-end test against the Python export.
5. MCP server; registered in Claude Code on sf1; a session drives 1marto end to end.
6. Qt6 GUI.
7. KiCad plugin.

Steps 1-5 give Claude the full chain without any GUI; 6 replaces the Python GUI for
smooker; 7 brings it into KiCad.

## Rules

- Local commits on branch `cpp`; **no push to github:smooker/pcbooker without smooker's go**.
- Plotter unit 0.0254 mm everywhere; one constant (`units.h`).
- The Python pcbooker is not changed by this work, except bug fixes smooker asks for.
