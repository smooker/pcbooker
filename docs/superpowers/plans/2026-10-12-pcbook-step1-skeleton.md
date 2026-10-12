# pcbook step 1: skeleton, vendored libraries, hpgl in the library, oracle

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `cpp/` CMake project in pcbooker with Clipper2, nlohmann/json and stb inside the
repo, `libpcbook` holding the HPGL reader (moved from `hpglview/`), hpglview rebuilt on top
of it, and committed oracle JSON for the test fixtures.

**Architecture:** One top-level `cpp/CMakeLists.txt`. `libpcbook` is a static library
(no Qt). Clipper2 is a git submodule compiled from its sources directly (not through its own
CMake, so none of its tests/examples build). json and stb are single headers copied into
`cpp/ext/`. Qt6 is optional: without it the library, the tests and (later) CLI/MCP still
build. The oracle generator is Python and uses the existing Python pcbooker; only its JSON
output is used by the C++ tests.

**Tech Stack:** C++17, CMake >= 3.16, Clipper2 2.0.1 (tag `Clipper2_2.0.1`), nlohmann/json
v3.12.0 (`single_include/nlohmann/json.hpp`), stb `stb_image_write.h` (master at
`2c980bb59875b0d32144a71867fbdebb2f77cd20`), Qt6 (optional), Python 3 venv
`/home/claude/venv/pcbooker` (gerbonara, shapely) for the oracle only.

**Spec:** `docs/superpowers/specs/2026-10-12-pcbook-cpp-design.md`

## Global Constraints

- Dependencies: a C++17 compiler and CMake. Qt6 only for the GUI and hpglview. Everything
  else in the repo (`cpp/ext/`).
- Plotter unit 0.0254 mm (5000/127 units per mm), **not 40**; one constant in `units.h`.
- Internal coordinates: int64 nanometres.
- Local commits on branch `cpp`; **no push** to github:smooker/pcbooker without smooker's go.
- The Python pcbooker is not changed.
- Builds: in the sf1 chroot (no Qt: lib + tests) into `/tmp/pcbook-build`; on the sf1 host
  as claude (Qt6: everything) via stmux window `claude:kicad` into `/chroot/claude/tmp/pcbook-qt`.
  Host path of the repo: `/chroot/claude/home/claude/work/pcbooker`.
- Shared tmux rule: no grep/head/tail/redirect inside `stmux ... send-keys` payloads; read
  the pane with `capture-pane`.

## Review Focus

1. A build without Qt6 (the chroot) must configure and build the library and tests with no
   error -- not fail on `find_package(Qt6)`. Pinned in Task 1 (chroot build) and Task 2.
2. `git clone` without `--recursive` leaves `cpp/ext/Clipper2` empty: CMake must stop with a
   message naming the fix (`git submodule update --init`), not a compiler error. Pinned in
   Task 1 Step 6.
3. Moving the HPGL parser must not change its results: all 10 existing parser tests keep
   passing unchanged, and hpglview's `--stats` on the 1marto fixture prints the same JSON
   as before the move. Pinned in Task 2.
4. The oracle must describe the Python pcbooker's behaviour, not a re-derivation: it calls
   `gerber_loader.layer_to_merged`, `isolation.generate_isolation`, `hatch.*` as the GUI
   does. Pinned in Task 3 (generator code).
5. A fixture file gerbonara cannot read (STMOTOR.GBR is RS-274-D with no aperture table)
   must not break the generator: it is listed as unsupported with the reason. Pinned in
   Task 3.

---

## File structure

```
cpp/
  CMakeLists.txt                 top level
  ext/Clipper2/                  submodule
  ext/json/nlohmann/json.hpp     vendored
  ext/stb/stb_image_write.h      vendored
  ext/README.md                  what is vendored, from where, which version
  libpcbook/units.h              unit constants and conversions
  libpcbook/hpgl.h, hpgl.cpp     moved from hpglview/ (namespace hpgl unchanged)
  hpglview/                      moved from ../hpglview: main.cpp view.h view.cpp
  tests/test_hpgl.cpp            moved from hpglview/tests
  tests/test_ext.cpp             Clipper2 + json + units smoke test
  tests/test_oracle.cpp          loads every oracle JSON, checks the fields
  tests/data/1marto_iso.hpgl     moved from hpglview/tests/data
  tests/fixtures/stmbl/          STMBL v4.0 Gerbers + drill from kicad-cli
  tests/oracle/gen.py            oracle generator (Python, run by hand)
  tests/oracle/*.json            generated, committed
```

`hpglview/` at the repo root is removed (moved into `cpp/`).

---

### Task 1: cpp/ skeleton with Clipper2, json, stb and units.h

**Files:**
- Create: `cpp/CMakeLists.txt`, `cpp/ext/README.md`, `cpp/libpcbook/units.h`,
  `cpp/libpcbook/pcbook.cpp`, `cpp/tests/test_ext.cpp`
- Create (vendored): `cpp/ext/json/nlohmann/json.hpp`, `cpp/ext/stb/stb_image_write.h`
- Create (submodule): `cpp/ext/Clipper2` at tag `Clipper2_2.0.1`
- Modify: `.gitmodules` (created by `git submodule add`)

**Interfaces:**
- Produces: CMake targets `clipper2` (static), `pcbook` (static, links `clipper2`,
  include dirs `cpp/libpcbook`, `cpp/ext/json`, `cpp/ext/stb`), test `ext`.
- Produces `units.h`:
  ```cpp
  namespace pcbook {
  constexpr int64_t NM_PER_MM = 1000000;
  constexpr double HPGL_UNITS_PER_MM = 5000.0 / 127.0;   // 0.0254 mm per unit, not 40
  inline int64_t mm_to_nm(double mm);                     // rounds to nearest
  inline double  nm_to_mm(int64_t nm);
  inline int64_t nm_to_hpgl(int64_t nm);                  // rounds to nearest unit
  }
  ```

- [ ] **Step 1: Add the submodule and vendored headers**

```bash
cd /home/claude/work/pcbooker
git submodule add https://github.com/AngusJohnson/Clipper2 cpp/ext/Clipper2
git -C cpp/ext/Clipper2 checkout -q Clipper2_2.0.1
mkdir -p cpp/ext/json/nlohmann cpp/ext/stb cpp/libpcbook cpp/tests
curl -fsSL -o cpp/ext/json/nlohmann/json.hpp \
  https://raw.githubusercontent.com/nlohmann/json/v3.12.0/single_include/nlohmann/json.hpp
curl -fsSL -o cpp/ext/stb/stb_image_write.h \
  https://raw.githubusercontent.com/nothings/stb/2c980bb59875b0d32144a71867fbdebb2f77cd20/stb_image_write.h
ls -la cpp/ext/json/nlohmann/json.hpp cpp/ext/stb/stb_image_write.h cpp/ext/Clipper2/CPP/Clipper2Lib/src
```
Expected: json.hpp about 900 KB, stb_image_write.h about 70 KB, the Clipper2 `src` directory
lists `clipper.engine.cpp clipper.offset.cpp clipper.rectclip.cpp clipper.triangulation.cpp`.

- [ ] **Step 2: Write `cpp/ext/README.md`**

```markdown
# Third-party code in the repo

Nothing here comes from the system: a C++17 compiler and CMake are enough (Qt6 only for
the GUI and hpglview).

| path | what | version | licence |
|---|---|---|---|
| `Clipper2/` | polygon clipping and offsetting (git submodule) | tag `Clipper2_2.0.1` | Boost 1.0 |
| `json/nlohmann/json.hpp` | JSON (single header) | v3.12.0 | MIT |
| `stb/stb_image_write.h` | PNG writer (single header) | stb master 2c980bb5 | public domain / MIT |

After `git clone`, run `git submodule update --init` (or clone with `--recursive`).
Clipper2 is compiled from `CPP/Clipper2Lib/src` by our CMake, not through its own CMake.
```

- [ ] **Step 3: Write the failing smoke test `cpp/tests/test_ext.cpp`**

```cpp
// Smoke test: the vendored libraries build and link, units convert as specified.
#include "units.h"

#include <clipper2/clipper.h>
#include <nlohmann/json.hpp>

#include <cmath>
#include <cstdio>

static int failures = 0;
#define CHECK(cond)                                                                    \
    do {                                                                               \
        if (!(cond)) {                                                                 \
            std::fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond); \
            ++failures;                                                                \
        }                                                                              \
    } while (0)

static void test_units()
{
    CHECK(pcbook::mm_to_nm(1.0) == 1000000);
    CHECK(pcbook::mm_to_nm(0.0000004) == 0);       // rounds to nearest
    CHECK(pcbook::mm_to_nm(0.0000006) == 1);
    CHECK(std::fabs(pcbook::nm_to_mm(2540000) - 2.54) < 1e-12);
    CHECK(pcbook::nm_to_hpgl(25400) == 1);          // 0.0254 mm = 1 unit
    CHECK(pcbook::nm_to_hpgl(100000000) == 3937);   // 100 mm
    CHECK(pcbook::nm_to_hpgl(-25400) == -1);
}

static void test_clipper_union()
{
    using namespace Clipper2Lib;
    Paths64 a{MakePath({0, 0, 100, 0, 100, 100, 0, 100})};
    Paths64 b{MakePath({50, 0, 150, 0, 150, 100, 50, 100})};
    Paths64 u = Union(a, b, FillRule::NonZero);
    CHECK(u.size() == 1);
    CHECK(std::fabs(Area(u) - 15000.0) < 1e-9);
}

static void test_json()
{
    auto j = nlohmann::json::parse(R"({"area_mm2": 12.5, "bounds_mm": [1, 2, 3, 4]})");
    CHECK(j["area_mm2"].get<double>() == 12.5);
    CHECK(j["bounds_mm"].size() == 4);
}

int main()
{
    test_units();
    test_clipper_union();
    test_json();
    if (failures)
        std::fprintf(stderr, "%d check(s) failed\n", failures);
    else
        std::puts("all ok");
    return failures ? 1 : 0;
}
```

- [ ] **Step 4: Write `cpp/CMakeLists.txt`, an empty `units.h` and `pcbook.cpp`**

`cpp/CMakeLists.txt`:
```cmake
cmake_minimum_required(VERSION 3.16)
project(pcbook CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE RelWithDebInfo)
endif()

# --- third party, all in the repo (ext/README.md) ---
set(CLIPPER2_DIR ${CMAKE_CURRENT_SOURCE_DIR}/ext/Clipper2/CPP/Clipper2Lib)
if(NOT EXISTS ${CLIPPER2_DIR}/src/clipper.engine.cpp)
    message(FATAL_ERROR "ext/Clipper2 is empty: run `git submodule update --init` in the repo")
endif()
add_library(clipper2 STATIC
    ${CLIPPER2_DIR}/src/clipper.engine.cpp
    ${CLIPPER2_DIR}/src/clipper.offset.cpp
    ${CLIPPER2_DIR}/src/clipper.rectclip.cpp)
target_include_directories(clipper2 PUBLIC ${CLIPPER2_DIR}/include)

# --- our code: warnings on, after the third-party targets ---
add_compile_options(-Wall -Wextra)

add_library(pcbook STATIC libpcbook/pcbook.cpp)
target_include_directories(pcbook PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/libpcbook
    ${CMAKE_CURRENT_SOURCE_DIR}/ext/json
    ${CMAKE_CURRENT_SOURCE_DIR}/ext/stb)
target_link_libraries(pcbook PUBLIC clipper2)

enable_testing()
add_executable(test_ext tests/test_ext.cpp)
target_link_libraries(test_ext pcbook)
add_test(NAME ext COMMAND test_ext)
```

`cpp/libpcbook/units.h` (empty namespace for now, so the test fails to compile):
```cpp
#pragma once
#include <cstdint>
namespace pcbook {
}
```

`cpp/libpcbook/pcbook.cpp`:
```cpp
// libpcbook: pcbooker's core in C++. Translation unit so the static library is never empty.
#include "units.h"
```

- [ ] **Step 5: Build, watch it fail**

Run: `cmake -S /home/claude/work/pcbooker/cpp -B /tmp/pcbook-build -DCMAKE_BUILD_TYPE=Debug && cmake --build /tmp/pcbook-build -j8`
Expected: compile error in `test_ext.cpp`: `'mm_to_nm' is not a member of 'pcbook'`.

- [ ] **Step 6: Check the empty-submodule message**

```bash
mv /home/claude/work/pcbooker/cpp/ext/Clipper2/CPP /tmp/c2-aside
cmake -S /home/claude/work/pcbooker/cpp -B /tmp/pcbook-empty 2>&1 | grep -m1 'submodule update'
mv /tmp/c2-aside /home/claude/work/pcbooker/cpp/ext/Clipper2/CPP
rm -rf /tmp/pcbook-empty
```
Expected: the line `ext/Clipper2 is empty: run `git submodule update --init` in the repo`.

- [ ] **Step 7: Implement `units.h`**

```cpp
// Units: int64 nanometres inside (as KiCad and Clipper2's Paths64); HPGL at the edge.
#pragma once

#include <cmath>
#include <cstdint>

namespace pcbook {

constexpr int64_t NM_PER_MM = 1000000;
// pcbooker / TRUMPF VectorMark: 0.0254 mm per plotter unit (1016 per inch), NOT 40 per mm
constexpr double HPGL_UNITS_PER_MM = 5000.0 / 127.0;

inline int64_t mm_to_nm(double mm) { return static_cast<int64_t>(std::llround(mm * NM_PER_MM)); }
inline double nm_to_mm(int64_t nm) { return static_cast<double>(nm) / NM_PER_MM; }
// 1 unit = 25400 nm exactly; round half away from zero
inline int64_t nm_to_hpgl(int64_t nm)
{
    return nm >= 0 ? (nm + 12700) / 25400 : -((-nm + 12700) / 25400);
}

} // namespace pcbook
```

- [ ] **Step 8: Build and run, watch it pass**

Run: `cmake --build /tmp/pcbook-build -j8 && ctest --test-dir /tmp/pcbook-build --output-on-failure`
Expected: `100% tests passed, 0 tests failed out of 1`, no compiler warnings from our files.

- [ ] **Step 9: Commit**

```bash
cd /home/claude/work/pcbooker
git add .gitmodules cpp/ext cpp/CMakeLists.txt cpp/libpcbook cpp/tests/test_ext.cpp
git commit -m "cpp: skeleton, Clipper2 submodule, json + stb vendored, units.h"
```

---

### Task 2: move the HPGL reader into libpcbook, hpglview into cpp/

**Files:**
- Move: `hpglview/hpgl.h` -> `cpp/libpcbook/hpgl.h`, `hpglview/hpgl.cpp` -> `cpp/libpcbook/hpgl.cpp`
- Move: `hpglview/main.cpp view.h view.cpp` -> `cpp/hpglview/`
- Move: `hpglview/tests/test_hpgl.cpp` -> `cpp/tests/test_hpgl.cpp`,
  `hpglview/tests/data/1marto_iso.hpgl` -> `cpp/tests/data/1marto_iso.hpgl`
- Delete: `hpglview/CMakeLists.txt`, `hpglview/.gitignore`, the `hpglview/` directory
- Modify: `cpp/CMakeLists.txt`, `cpp/libpcbook/hpgl.h` (use `pcbook::HPGL_UNITS_PER_MM`)

**Interfaces:**
- Consumes: `pcbook` target and `units.h` from Task 1.
- Produces: `hpgl::parse(const std::string&, double units_per_mm = hpgl::UNITS_PER_MM)`,
  `hpgl::stats_json(const Plot&)`, types `hpgl::Seg`, `hpgl::Stats`, `hpgl::Plot` -- unchanged
  names, now in `libpcbook`; executable `hpglview` (only with Qt6); test `hpgl`.

- [ ] **Step 1: Record the pre-move reference output** (host, Qt build of the old layout)

```bash
stmux sf1-host send-keys -t claude:kicad 'clear; /chroot/claude/tmp/hv-qt/hpglview --stats /chroot/claude/home/claude/work/pcbooker/hpglview/tests/data/1marto_iso.hpgl' Enter
stmux sf1-host capture-pane -t claude:kicad -p -S -10
```
Expected: one JSON line starting `{"units_per_mm":39.370079,"segments":7151,`. Save it to
`/tmp/hpgl-before.json` (copy the line from the pane with the Write tool).

- [ ] **Step 2: Move the files with git**

```bash
cd /home/claude/work/pcbooker
mkdir -p cpp/hpglview cpp/tests/data
git mv hpglview/hpgl.h hpglview/hpgl.cpp cpp/libpcbook/
git mv hpglview/main.cpp hpglview/view.h hpglview/view.cpp cpp/hpglview/
git mv hpglview/tests/test_hpgl.cpp cpp/tests/test_hpgl.cpp
git mv hpglview/tests/data/1marto_iso.hpgl cpp/tests/data/1marto_iso.hpgl
git rm -q hpglview/CMakeLists.txt hpglview/.gitignore
ls hpglview 2>&1
```
Expected: `ls: cannot access 'hpglview': No such file or directory`.

- [ ] **Step 3: Make the unit constant single-sourced** -- in `cpp/libpcbook/hpgl.h` replace

```cpp
// pcbooker / TRUMPF VectorMark: 0.0254 mm per unit (hpgl_export.py), not 40 u/mm
constexpr double UNITS_PER_MM = 5000.0 / 127.0;
```
with
```cpp
// the one constant lives in units.h: 0.0254 mm per unit, not 40 u/mm
constexpr double UNITS_PER_MM = pcbook::HPGL_UNITS_PER_MM;
```
and add `#include "units.h"` after `#pragma once`.

- [ ] **Step 4: Wire into `cpp/CMakeLists.txt`** -- change the library line to

```cmake
add_library(pcbook STATIC libpcbook/pcbook.cpp libpcbook/hpgl.cpp)
```
and append at the end:
```cmake
add_executable(test_hpgl tests/test_hpgl.cpp)
target_link_libraries(test_hpgl pcbook)
target_compile_definitions(test_hpgl PRIVATE DATA_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/data")
add_test(NAME hpgl COMMAND test_hpgl)

# --- Qt6 front ends: optional, the chroot has no Qt ---
find_package(Qt6 COMPONENTS Core Gui Widgets QUIET)
if(Qt6_FOUND)
    set(CMAKE_AUTOMOC ON)
    add_executable(hpglview hpglview/main.cpp hpglview/view.cpp)
    target_link_libraries(hpglview pcbook Qt6::Core Qt6::Gui Qt6::Widgets)
    # Terminus from pcbooker's fonts/, for the status line and the PNG summary
    qt_add_resources(hpglview fonts
        PREFIX /fonts
        BASE ${CMAKE_CURRENT_SOURCE_DIR}/../fonts
        FILES ${CMAKE_CURRENT_SOURCE_DIR}/../fonts/Terminus.ttf
              ${CMAKE_CURRENT_SOURCE_DIR}/../fonts/TerminusBold.ttf)
else()
    message(STATUS "Qt6 not found: library, CLI, MCP and tests only")
endif()
```

- [ ] **Step 5: Chroot build (no Qt): tests pass, no Qt error**

Run: `cmake -S /home/claude/work/pcbooker/cpp -B /tmp/pcbook-build && cmake --build /tmp/pcbook-build -j8 && ctest --test-dir /tmp/pcbook-build --output-on-failure`
Expected: configure prints `Qt6 not found: library, CLI, MCP and tests only`;
`100% tests passed, 0 tests failed out of 2`.

- [ ] **Step 6: Host build (Qt6): hpglview builds, same stats as before the move**

```bash
stmux sf1-host send-keys -t claude:kicad 'clear; cmake -S /chroot/claude/home/claude/work/pcbooker/cpp -B /chroot/claude/tmp/pcbook-qt && cmake --build /chroot/claude/tmp/pcbook-qt -j8 && ctest --test-dir /chroot/claude/tmp/pcbook-qt && /chroot/claude/tmp/pcbook-qt/hpglview --stats /chroot/claude/home/claude/work/pcbooker/cpp/tests/data/1marto_iso.hpgl; echo S2_RC=$?' Enter
stmux sf1-host capture-pane -t claude:kicad -p -S -200
```
Expected: `100% tests passed, 0 tests failed out of 2`, then a JSON line identical to
`/tmp/hpgl-before.json`, then `S2_RC=0`.

- [ ] **Step 7: Commit**

```bash
cd /home/claude/work/pcbooker
git add -A cpp hpglview
git commit -m "cpp: HPGL reader moves into libpcbook, hpglview into cpp/"
```

---

### Task 3: STMBL fixtures, oracle generator, oracle JSON and the C++ loader test

**Files:**
- Create: `cpp/tests/fixtures/stmbl/*` (kicad-cli output), `cpp/tests/fixtures/README.md`
- Create: `cpp/tests/oracle/gen.py`, `cpp/tests/oracle/*.json` (generated)
- Create: `cpp/tests/test_oracle.cpp`
- Modify: `cpp/CMakeLists.txt`

**Interfaces:**
- Consumes: Python pcbooker modules `gerber_loader.load_single`,
  `gerber_loader.layer_to_merged`, `isolation.generate_isolation`, `hatch.ablate_region`,
  `hatch.hatch_lines`; gerbonara `ExcellonFile`.
- Produces: one JSON per fixture in `cpp/tests/oracle/`, read by steps 2-4 of the spec:
  ```json
  {"file": "<path relative to repo root>", "kind": "gerber",
   "area_mm2": 0.0, "bounds_mm": [minx, miny, maxx, maxy], "polygons": 0, "holes": 0,
   "iso_area_mm2": {"0.05": 0.0, "0.1": 0.0},
   "hatch_len_mm": {"0": 0.0, "45": 0.0}, "hatch_pitch_mm": 0.045, "hatch_offset_mm": 0.05}
  ```
  ```json
  {"file": "...", "kind": "excellon", "hits": 0, "slots": 0, "diameters_mm": [0.8, 1.0]}
  ```
  ```json
  {"file": "...", "kind": "unsupported", "reason": "<parser error text>"}
  ```
  plus `cpp/tests/oracle/index.json`: `{"fixtures": ["<name>.json", ...]}`.
  Test `oracle` and compile definition `ORACLE_DIR`.

- [ ] **Step 1: Export STMBL v4.0 from the committed board** (not the clone smooker may have
  edited)

```bash
mkdir -p /tmp/stmbl-export
git -C /tmp/kref/stmbl show HEAD:hw/kicad/v4.0/stmbl_4.0.kicad_pcb > /tmp/stmbl-export/stmbl_4.0.kicad_pcb
stmux sf1-host send-keys -t claude:kicad 'clear; kicad-cli pcb export gerbers --layers F.Cu,B.Cu,Edge.Cuts -o /chroot/claude/tmp/stmbl-export/out/ /chroot/claude/tmp/stmbl-export/stmbl_4.0.kicad_pcb && kicad-cli pcb export drill --format excellon -o /chroot/claude/tmp/stmbl-export/out/ /chroot/claude/tmp/stmbl-export/stmbl_4.0.kicad_pcb; echo EXP_RC=$?' Enter
stmux sf1-host capture-pane -t claude:kicad -p -S -40
ls -la /tmp/stmbl-export/out/
```
Expected: `EXP_RC=0`; `out/` holds three Gerber files (F_Cu, B_Cu, Edge_Cuts; extension as
KiCad names them) and one or two `.drl` files.

- [ ] **Step 2: Copy them in and write `cpp/tests/fixtures/README.md`**

```bash
mkdir -p /home/claude/work/pcbooker/cpp/tests/fixtures/stmbl
cp /tmp/stmbl-export/out/* /home/claude/work/pcbooker/cpp/tests/fixtures/stmbl/
du -sh /home/claude/work/pcbooker/cpp/tests/fixtures/stmbl
```

`cpp/tests/fixtures/README.md`:
```markdown
# Test fixtures

| fixture | what | source |
|---|---|---|
| `../../../testfiles/1marto.GTL` | single copper layer, hand-made board | pcbooker repo |
| `../../../drill/1MARTO.DRL` | its drills (Excellon) | pcbooker repo |
| `../../../gerber/STMOTOR.GBR` | RS-274-D, no aperture table: listed as unsupported | pcbooker repo |
| `stmbl/` | STMBL v4.0 (rene-dev/stmbl, GPL-3): F.Cu, B.Cu, Edge.Cuts, drills | `kicad-cli` 10.0.3 from the committed `hw/kicad/v4.0/stmbl_4.0.kicad_pcb`, 2026-10-12 |

The oracle JSON for each is in `../oracle/`, made by `../oracle/gen.py`.
```

- [ ] **Step 3: Write the oracle generator `cpp/tests/oracle/gen.py`**

```python
#!/usr/bin/env python3
"""
Oracle for the C++ pcbook tests: what the Python pcbooker makes of each fixture.

Run by hand when fixtures or the Python pcbooker change:
    /home/claude/venv/pcbooker/bin/python -I cpp/tests/oracle/gen.py
from the repo root. Writes cpp/tests/oracle/<fixture>.json and index.json.
It calls pcbooker's own modules, as the GUI does, so the numbers are pcbooker's behaviour.
"""
import glob
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, ROOT)

import gerber_loader  # noqa: E402
import hatch  # noqa: E402
import isolation  # noqa: E402
from gerbonara import ExcellonFile  # noqa: E402

OUT = os.path.join(ROOT, 'cpp', 'tests', 'oracle')
ISO_OFFSETS = (0.05, 0.1)
HATCH_PITCH, HATCH_OFFSET, HATCH_ANGLES = 0.045, 0.05, (0, 45)

GERBERS = ['testfiles/1marto.GTL', 'gerber/STMOTOR.GBR'] + sorted(
    os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, 'cpp/tests/fixtures/stmbl/*'))
    if not p.lower().endswith(('.drl', '.md')))
DRILLS = ['drill/1MARTO.DRL'] + sorted(
    os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, 'cpp/tests/fixtures/stmbl/*.drl')))


def r(x):
    return round(float(x), 6)


def gerber_oracle(rel):
    try:
        merged = gerber_loader.layer_to_merged(gerber_loader.load_single(os.path.join(ROOT, rel)))
    except Exception as e:  # noqa: BLE001 -- the reason goes into the oracle
        return {'file': rel, 'kind': 'unsupported', 'reason': str(e).splitlines()[0]}
    if merged is None or merged.is_empty:
        return {'file': rel, 'kind': 'unsupported', 'reason': 'no geometry'}
    polys = list(getattr(merged, 'geoms', [merged]))
    o = {'file': rel, 'kind': 'gerber',
         'area_mm2': r(merged.area),
         'bounds_mm': [r(b) for b in merged.bounds],
         'polygons': len(polys),
         'holes': sum(len(p.interiors) for p in polys),
         'iso_area_mm2': {}, 'hatch_len_mm': {},
         'hatch_pitch_mm': HATCH_PITCH, 'hatch_offset_mm': HATCH_OFFSET}
    for off in ISO_OFFSETS:
        g = isolation.generate_isolation(merged, off, 'outline')
        o['iso_area_mm2'][str(off)] = r(g.area if g is not None else 0)
    region = hatch.ablate_region(merged, HATCH_OFFSET, margin_mm=1.0)
    for ang in HATCH_ANGLES:
        o['hatch_len_mm'][str(ang)] = r(sum(l.length for l in hatch.hatch_lines(region, HATCH_PITCH, ang)))
    return o


def drill_oracle(rel):
    try:
        f = ExcellonFile.open(os.path.join(ROOT, rel))
    except Exception as e:  # noqa: BLE001
        return {'file': rel, 'kind': 'unsupported', 'reason': str(e).splitlines()[0]}
    hits = slots = 0
    dias = set()
    for obj in f.objects:
        d = obj.tool.diameter
        unit = getattr(obj, 'unit', None) or f.unit
        mm = unit.convert_to('mm', d) if hasattr(unit, 'convert_to') else d
        dias.add(round(float(mm), 4))
        if type(obj).__name__ == 'Flash':
            hits += 1
        else:
            slots += 1
    return {'file': rel, 'kind': 'excellon', 'hits': hits, 'slots': slots,
            'diameters_mm': sorted(dias)}


def main():
    os.makedirs(OUT, exist_ok=True)
    names = []
    for rel, fn in [(g, gerber_oracle) for g in GERBERS] + [(d, drill_oracle) for d in DRILLS]:
        o = fn(rel)
        name = rel.replace('/', '__') + '.json'
        with open(os.path.join(OUT, name), 'w') as f:
            json.dump(o, f, indent=1, sort_keys=True)
        names.append(name)
        print(f"{o['kind']:11s} {rel}" + (f"  ({o['reason']})" if o['kind'] == 'unsupported' else ''))
    with open(os.path.join(OUT, 'index.json'), 'w') as f:
        json.dump({'fixtures': names}, f, indent=1)


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run it**

Run: `cd /home/claude/work/pcbooker && /home/claude/venv/pcbooker/bin/python -I cpp/tests/oracle/gen.py`
Expected: `gerber      testfiles/1marto.GTL`, `unsupported gerber/STMOTOR.GBR  (... undefined aperture 26)`,
one `gerber` line per STMBL Gerber, `excellon    drill/1MARTO.DRL` and one per STMBL `.drl`.
If any STMBL file comes out `unsupported`, stop and report the reason (the C++ parser will
need that fixture, so it has to be readable by the oracle).
Check one number by hand: `testfiles__1marto.GTL.json` has `area_mm2` close to 3511.8 and
`bounds_mm` close to `[109.423, 164.338, 186.487, 242.037]` (values seen on 2026-10-12).

- [ ] **Step 5: Write the failing loader test `cpp/tests/test_oracle.cpp`**

```cpp
// Every oracle JSON is present and complete: the contract later parser/geometry tests rely on.
#include <nlohmann/json.hpp>

#include <cstdio>
#include <fstream>
#include <string>

static int failures = 0;
#define CHECK(cond)                                                                    \
    do {                                                                               \
        if (!(cond)) {                                                                 \
            std::fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond); \
            ++failures;                                                                \
        }                                                                              \
    } while (0)

using nlohmann::json;

static json load(const std::string &name)
{
    std::ifstream f(std::string(ORACLE_DIR) + "/" + name);
    if (!f) {
        std::fprintf(stderr, "missing %s\n", name.c_str());
        ++failures;
        return json::object();
    }
    return json::parse(f);
}

int main()
{
    json index = load("index.json");
    CHECK(index.contains("fixtures") && index["fixtures"].size() >= 5);
    int gerbers = 0, drills = 0, unsupported = 0;
    for (const auto &n : index.value("fixtures", json::array())) {
        json o = load(n.get<std::string>());
        CHECK(o.contains("file") && o.contains("kind"));
        std::string kind = o.value("kind", "");
        if (kind == "gerber") {
            ++gerbers;
            CHECK(o["area_mm2"].get<double>() > 0);
            CHECK(o["bounds_mm"].size() == 4);
            CHECK(o["bounds_mm"][2].get<double>() > o["bounds_mm"][0].get<double>());
            CHECK(o["polygons"].get<int>() >= 1);
            CHECK(o["iso_area_mm2"].contains("0.05") && o["iso_area_mm2"].contains("0.1"));
            CHECK(o["iso_area_mm2"]["0.1"].get<double>() > o["iso_area_mm2"]["0.05"].get<double>());
            CHECK(o["hatch_len_mm"].contains("0") && o["hatch_len_mm"].contains("45"));
        } else if (kind == "excellon") {
            ++drills;
            CHECK(o["hits"].get<int>() + o["slots"].get<int>() > 0);
            CHECK(!o["diameters_mm"].empty());
        } else if (kind == "unsupported") {
            ++unsupported;
            CHECK(!o.value("reason", "").empty());
        } else {
            CHECK(!"unknown kind");
        }
    }
    CHECK(gerbers >= 4);     // 1marto + STMBL F.Cu, B.Cu, Edge.Cuts
    CHECK(drills >= 2);      // 1MARTO.DRL + STMBL
    CHECK(unsupported == 1); // STMOTOR.GBR (RS-274-D)
    std::printf("%d gerber, %d excellon, %d unsupported\n", gerbers, drills, unsupported);
    if (failures)
        std::fprintf(stderr, "%d check(s) failed\n", failures);
    return failures ? 1 : 0;
}
```

- [ ] **Step 6: Register the test in `cpp/CMakeLists.txt` with a wrong directory first, watch it fail**

Append:
```cmake
add_executable(test_oracle tests/test_oracle.cpp)
target_link_libraries(test_oracle pcbook)
target_compile_definitions(test_oracle PRIVATE ORACLE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/oracle-missing")
add_test(NAME oracle COMMAND test_oracle)
```
Run: `cmake --build /tmp/pcbook-build -j8 && ctest --test-dir /tmp/pcbook-build -R oracle --output-on-failure`
Expected: FAIL with `missing index.json`.

- [ ] **Step 7: Point it at the real directory, watch it pass**

Change `oracle-missing` to `oracle` in that line.
Run: `cmake --build /tmp/pcbook-build -j8 && ctest --test-dir /tmp/pcbook-build --output-on-failure`
Expected: `100% tests passed, 0 tests failed out of 3`; the oracle test prints e.g.
`4 gerber, 2 excellon, 1 unsupported` (more if KiCad wrote more files).

- [ ] **Step 8: Commit**

```bash
cd /home/claude/work/pcbooker
git add cpp/tests/fixtures cpp/tests/oracle cpp/tests/test_oracle.cpp cpp/CMakeLists.txt
git commit -m "cpp: STMBL fixtures, oracle generator + JSON from the Python pcbooker"
```

---

## Done when

- `ctest` passes 3/3 in the chroot (no Qt) and on the host (Qt), with hpglview built on the host.
- `hpglview --stats` on the 1marto fixture prints the same JSON as before the move.
- `cpp/tests/oracle/` holds a JSON per fixture and `index.json`; STMOTOR is the only
  `unsupported` one.
- Three commits on branch `cpp`, nothing pushed.
