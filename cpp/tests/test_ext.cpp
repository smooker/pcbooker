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
