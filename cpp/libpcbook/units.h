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
