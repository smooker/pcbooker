// hpglview -- look at the HPGL pcbooker wrote, the way the laser will read it.
//
//   hpglview FILE                         window: wheel zoom, drag pan, F fit, T travel,
//                                         G grid, R reload; reloads when the file changes
//   hpglview --png OUT [--size PX] FILE   render to PNG, no display needed
//   hpglview --stats FILE                 JSON stats on stdout
//   --unit-per-mm N                       default 39.370 (0.0254 mm); 40 shows what a
//                                         40 u/mm reader would make of the file
#include "hpgl.h"
#include "view.h"

#include <QApplication>
#include <QFile>
#include <QFileInfo>
#include <QGuiApplication>
#include <QImage>
#include <QLabel>
#include <QMainWindow>
#include <QPainter>
#include <QStatusBar>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>

static int usage()
{
    std::fputs("usage: hpglview [--unit-per-mm N] FILE\n"
               "       hpglview [--unit-per-mm N] --png OUT [--size PX] FILE\n"
               "       hpglview [--unit-per-mm N] --stats FILE\n",
               stderr);
    return 2;
}

static bool slurp(const char *path, std::string &out)
{
    std::ifstream f(path, std::ios::binary);
    if (!f)
        return false;
    std::ostringstream s;
    s << f.rdbuf();
    out = s.str();
    return true;
}

static int renderPng(int argc, char **argv, const char *file, const char *out, int px, double upmm)
{
    qputenv("QT_QPA_PLATFORM", "offscreen");
    QGuiApplication app(argc, argv);
    std::string text;
    if (!slurp(file, text)) {
        std::fprintf(stderr, "cannot read %s\n", file);
        return 1;
    }
    hpgl::Plot p = hpgl::parse(text, upmm);
    Paths paths;
    paths.build(p);
    // aspect of the plot, longest side = px, plus a strip for the summary line
    QSizeF b = paths.bounds.size();
    double ar = (b.width() > 0 && b.height() > 0) ? b.width() / b.height() : 1.0;
    QSize area = ar >= 1 ? QSize(px, std::max(100, int(px / ar))) : QSize(std::max(100, int(px * ar)), px);
    const int strip = 24;
    QImage img(area.width(), area.height() + strip, QImage::Format_RGB32);
    img.fill(Qt::white);
    QPainter g(&img);
    double scale;
    QPointF origin;
    fit(paths, area, scale, origin);
    g.translate(0, strip);
    draw(g, p, paths, scale, origin, area, DrawOpts{});
    g.resetTransform();
    g.fillRect(0, 0, img.width(), strip, QColor(245, 245, 245));
    g.setPen(Qt::black);
    g.drawText(QRect(6, 0, img.width() - 12, strip), Qt::AlignVCenter,
               QFileInfo(file).fileName() + "  |  " + summary(p));
    g.end();
    if (!img.save(out)) {
        std::fprintf(stderr, "cannot write %s\n", out);
        return 1;
    }
    std::printf("%s\n", hpgl::stats_json(p).c_str());
    return 0;
}

int main(int argc, char **argv)
{
    const char *file = nullptr, *png = nullptr;
    bool stats = false;
    int px = 2000;
    double upmm = hpgl::UNITS_PER_MM;
    for (int i = 1; i < argc; ++i) {
        if (!std::strcmp(argv[i], "--png") && i + 1 < argc)
            png = argv[++i];
        else if (!std::strcmp(argv[i], "--size") && i + 1 < argc)
            px = std::atoi(argv[++i]);
        else if (!std::strcmp(argv[i], "--unit-per-mm") && i + 1 < argc)
            upmm = std::atof(argv[++i]);
        else if (!std::strcmp(argv[i], "--stats"))
            stats = true;
        else if (argv[i][0] == '-')
            return usage();
        else
            file = argv[i];
    }
    if (!file || upmm <= 0 || px < 100)
        return usage();

    if (stats) {
        std::string text;
        if (!slurp(file, text)) {
            std::fprintf(stderr, "cannot read %s\n", file);
            return 1;
        }
        std::printf("%s\n", hpgl::stats_json(hpgl::parse(text, upmm)).c_str());
        return 0;
    }
    if (png)
        return renderPng(argc, argv, file, png, px, upmm);

    QApplication app(argc, argv);
    QMainWindow w;
    auto *v = new Viewer(upmm);
    auto *pos = new QLabel;
    w.setCentralWidget(v);
    w.statusBar()->addPermanentWidget(pos);
    QObject::connect(v, &Viewer::status, w.statusBar(), [&w](const QString &s) { w.statusBar()->showMessage(s); });
    QObject::connect(v, &Viewer::cursor, pos, &QLabel::setText);
    w.setWindowTitle("hpglview - " + QFileInfo(file).fileName());
    w.resize(1200, 900);
    w.show();
    if (!v->load(file))
        return 1;
    return app.exec();
}
