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
