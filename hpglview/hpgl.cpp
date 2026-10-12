#include "hpgl.h"

#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>

namespace hpgl {

namespace {

struct State {
    double x = 0, y = 0;
    int pen = 0;
    bool down = false;
    bool relative = false;
};

// numbers after a mnemonic, up to ';' or the next letter
std::vector<double> params(const std::string &t, size_t &i)
{
    std::vector<double> v;
    while (i < t.size() && t[i] != ';' && !std::isalpha(static_cast<unsigned char>(t[i]))) {
        char c = t[i];
        if (std::isdigit(static_cast<unsigned char>(c)) || c == '-' || c == '+' || c == '.') {
            char *end = nullptr;
            double d = std::strtod(t.c_str() + i, &end);
            size_t n = static_cast<size_t>(end - (t.c_str() + i));
            if (n == 0) {
                ++i;
                continue;
            }
            v.push_back(d);
            i += n;
        } else {
            ++i; // ',' and white space
        }
    }
    return v;
}

void move(Plot &p, State &s, double x, double y)
{
    if (s.relative) {
        x += s.x;
        y += s.y;
    }
    if (x == s.x && y == s.y) {
        ++p.st.zero_len;
        return;
    }
    p.segs.push_back({s.pen, s.down, s.x, s.y, x, y});
    ++p.st.segs_per_pen[s.pen];
    double len = std::hypot(x - s.x, y - s.y) / p.units_per_mm;
    if (s.down) {
        p.st.cut_mm += len;
        if (!p.st.has_cut) {
            p.st.min_x_mm = p.st.max_x_mm = s.x / p.units_per_mm;
            p.st.min_y_mm = p.st.max_y_mm = s.y / p.units_per_mm;
            p.st.has_cut = true;
        }
        for (double px : {s.x, x}) {
            double mm = px / p.units_per_mm;
            if (mm < p.st.min_x_mm) p.st.min_x_mm = mm;
            if (mm > p.st.max_x_mm) p.st.max_x_mm = mm;
        }
        for (double py : {s.y, y}) {
            double mm = py / p.units_per_mm;
            if (mm < p.st.min_y_mm) p.st.min_y_mm = mm;
            if (mm > p.st.max_y_mm) p.st.max_y_mm = mm;
        }
    } else {
        p.st.travel_mm += len;
    }
    s.x = x;
    s.y = y;
}

void moves(Plot &p, State &s, const std::vector<double> &v)
{
    for (size_t k = 0; k + 1 < v.size(); k += 2)
        move(p, s, v[k], v[k + 1]);
}

void pen(Plot &p, State &s, bool down)
{
    if (s.down && !down)
        ++p.st.pen_lifts;
    s.down = down;
}

} // namespace

Plot parse(const std::string &t, double units_per_mm)
{
    Plot p;
    p.units_per_mm = units_per_mm;
    State s;
    size_t i = 0;
    while (i < t.size()) {
        if (!std::isalpha(static_cast<unsigned char>(t[i]))) {
            ++i;
            continue;
        }
        if (i + 1 >= t.size() || !std::isalpha(static_cast<unsigned char>(t[i + 1]))) {
            ++p.st.unknown[std::string(1, static_cast<char>(std::toupper(t[i])))];
            ++i;
            continue;
        }
        std::string m{static_cast<char>(std::toupper(t[i])),
                      static_cast<char>(std::toupper(t[i + 1]))};
        i += 2;
        if (m == "LB") { // label text runs to ETX
            while (i < t.size() && t[i] != '\x03')
                ++i;
            ++p.st.unknown[m];
            continue;
        }
        std::vector<double> v = params(t, i);
        if (m == "IN") {
            int keep = s.pen; // IN: origin, pen up, absolute; pen selection stays
            s = State{};
            s.pen = keep;
        } else if (m == "SP") {
            s.pen = v.empty() ? 0 : static_cast<int>(v[0]);
        } else if (m == "PU" || m == "PD") {
            pen(p, s, m == "PD");
            moves(p, s, v);
        } else if (m == "PA" || m == "PR") {
            s.relative = (m == "PR");
            moves(p, s, v);
        } else if (m == "AP") {
            ++p.st.ignored;
        } else {
            ++p.st.unknown[m];
        }
    }
    return p;
}

std::string stats_json(const Plot &p)
{
    const Stats &st = p.st;
    char buf[512];
    std::snprintf(buf, sizeof buf,
                  "{\"units_per_mm\":%.6f,\"segments\":%zu,\"has_cut\":%s,"
                  "\"bbox_mm\":[%.3f,%.3f,%.3f,%.3f],\"size_mm\":[%.3f,%.3f],"
                  "\"cut_mm\":%.3f,\"travel_mm\":%.3f,\"pen_lifts\":%d,"
                  "\"zero_len\":%d,\"ignored\":%d",
                  p.units_per_mm, p.segs.size(), st.has_cut ? "true" : "false",
                  st.min_x_mm, st.min_y_mm, st.max_x_mm, st.max_y_mm,
                  st.max_x_mm - st.min_x_mm, st.max_y_mm - st.min_y_mm,
                  st.cut_mm, st.travel_mm, st.pen_lifts, st.zero_len, st.ignored);
    std::string j = buf;
    j += ",\"segs_per_pen\":{";
    bool first = true;
    for (const auto &[pen, n] : st.segs_per_pen) {
        j += (first ? "\"" : ",\"") + std::to_string(pen) + "\":" + std::to_string(n);
        first = false;
    }
    j += "},\"unknown\":{";
    first = true;
    for (const auto &[m, n] : st.unknown) {
        j += (first ? "\"" : ",\"") + m + "\":" + std::to_string(n);
        first = false;
    }
    j += "}}";
    return j;
}

} // namespace hpgl
