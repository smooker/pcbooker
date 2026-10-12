// HPGL parser for hpglview: reads the file pcbooker writes, independent of the exporter.
#pragma once

#include "units.h"

#include <map>
#include <string>
#include <vector>

namespace hpgl {

// the one constant lives in units.h: 0.0254 mm per unit, not 40 u/mm
constexpr double UNITS_PER_MM = pcbook::HPGL_UNITS_PER_MM;

struct Seg {
    int pen;
    bool down;
    double x0, y0, x1, y1; // plotter units
};

struct Stats {
    bool has_cut = false;
    double min_x_mm = 0, min_y_mm = 0, max_x_mm = 0, max_y_mm = 0; // pen-down only
    double cut_mm = 0, travel_mm = 0;
    int pen_lifts = 0;                  // pen down -> up transitions
    int zero_len = 0;                   // moves to the point the pen is already at
    int ignored = 0;                    // known, no effect on geometry (AP ...)
    std::map<int, int> segs_per_pen;
    std::map<std::string, int> unknown; // mnemonic -> count
};

struct Plot {
    std::vector<Seg> segs;
    Stats st;
    double units_per_mm = UNITS_PER_MM;
};

Plot parse(const std::string &text, double units_per_mm = UNITS_PER_MM);
std::string stats_json(const Plot &p);

} // namespace hpgl
