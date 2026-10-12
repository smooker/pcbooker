// Parser tests for hpglview. Plain asserts, no test framework.
#include "hpgl.h"

#include <cmath>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>

static int failures = 0;

#define CHECK(cond)                                                            \
    do {                                                                       \
        if (!(cond)) {                                                         \
            std::fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__,        \
                         __LINE__, #cond);                                     \
            ++failures;                                                        \
        }                                                                      \
    } while (0)

#define NEAR(a, b, tol) CHECK(std::fabs((a) - (b)) <= (tol))

static std::string slurp(const std::string &path)
{
    std::ifstream f(path, std::ios::binary);
    std::ostringstream s;
    s << f.rdbuf();
    return s.str();
}

// 3937 plotter units at 5000/127 u/mm are 99.9998 mm
static void test_unit_scale()
{
    hpgl::Plot p = hpgl::parse("IN;SP1;PU0,0;PD3937,0;PU;SP0;");
    NEAR(p.st.cut_mm, 100.0, 0.01);
    NEAR(p.st.max_x_mm - p.st.min_x_mm, 100.0, 0.01);
    CHECK(p.st.unknown.empty());
}

// what a 40 u/mm reader makes of the same line: 1.6 % short
static void test_unit_override()
{
    hpgl::Plot p = hpgl::parse("IN;SP1;PU0,0;PD3937,0;", 40.0);
    NEAR(p.st.cut_mm, 98.425, 0.01);
}

static void test_pen_up_down()
{
    hpgl::Plot p = hpgl::parse("IN;SP1;PU0,0;PD100,0,100,100;PU200,100;PD200,0;PU;");
    int down = 0, up = 0;
    for (const auto &s : p.segs)
        (s.down ? down : up)++;
    CHECK(down == 3);
    CHECK(up == 1); // 100,100 -> 200,100; PU0,0 from the origin is no move
    CHECK(p.st.pen_lifts == 2);
    CHECK(p.st.segs_per_pen.at(1) == 4);
}

static void test_relative()
{
    hpgl::Plot p = hpgl::parse("IN;SP1;PA0,0;PD;PR100,0,0,100;PA;PU0,0;");
    CHECK(p.segs.size() >= 3);
    CHECK(p.segs[0].x1 == 100 && p.segs[0].y1 == 0);
    CHECK(p.segs[1].x1 == 100 && p.segs[1].y1 == 100);
    CHECK(p.segs[1].down);
}

static void test_no_separators()
{
    hpgl::Plot p = hpgl::parse("IN SP1 PU0,0 PD10,0 PU");
    CHECK(p.segs.size() == 1);
    CHECK(p.st.unknown.empty());
}

static void test_ignored_and_unknown()
{
    hpgl::Plot p = hpgl::parse("IN;AP3;SP1;XX12;LBhello\x03;PU;");
    CHECK(p.st.ignored == 1);
    CHECK(p.st.unknown.at("XX") == 1);
    CHECK(p.st.unknown.at("LB") == 1);
    CHECK(p.segs.empty());
}

static void test_zero_length()
{
    hpgl::Plot p = hpgl::parse("IN;SP1;PU5,5;PD5,5,5,5,6,5;");
    CHECK(p.st.zero_len == 2);
    CHECK(p.segs.size() == 2); // travel 0,0 -> 5,5 and the cut 5,5 -> 6,5
}

static void test_empty_bbox()
{
    hpgl::Plot p = hpgl::parse("IN;PA0,0;AP3;SP1;\n\nPA0,0;SP0;");
    CHECK(p.segs.empty());
    CHECK(!p.st.has_cut);
}

// pcbooker export of testfiles/1marto.GTL, isolation 0.1 mm outline, min gap 0.05:
// shapely said 39 paths, bounds 109.323,164.238 .. 186.587,242.137 mm, 3637.8 mm
static void test_1marto()
{
    hpgl::Plot p = hpgl::parse(slurp(DATA_DIR "/1marto_iso.hpgl"));
    CHECK(p.st.unknown.empty());
    CHECK(p.st.pen_lifts == 39);
    NEAR(p.st.min_x_mm, 109.323, 0.03);
    NEAR(p.st.min_y_mm, 164.238, 0.03);
    NEAR(p.st.max_x_mm, 186.587, 0.03);
    NEAR(p.st.max_y_mm, 242.137, 0.03);
    NEAR(p.st.cut_mm, 3637.8, 3637.8 * 0.01);
}

static void test_json()
{
    hpgl::Plot p = hpgl::parse("IN;SP1;PU0,0;PD3937,0;XX;");
    std::string j = hpgl::stats_json(p);
    CHECK(j.find("\"cut_mm\":") != std::string::npos);
    CHECK(j.find("\"XX\":1") != std::string::npos);
    CHECK(j.front() == '{' && j.back() == '}');
}

int main()
{
    test_unit_scale();
    test_unit_override();
    test_pen_up_down();
    test_relative();
    test_no_separators();
    test_ignored_and_unknown();
    test_zero_length();
    test_empty_bbox();
    test_1marto();
    test_json();
    if (failures)
        std::fprintf(stderr, "%d check(s) failed\n", failures);
    else
        std::puts("all ok");
    return failures ? 1 : 0;
}
