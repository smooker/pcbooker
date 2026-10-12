// hpglview -- look at the HPGL pcbooker wrote, the way the laser will read it.
//
//   hpglview [FILE]                       window with menus; wheel zoom, drag pan;
//                                         reloads when the file changes
//   hpglview --png OUT [--size PX] FILE   render to PNG, no display needed
//   hpglview --stats FILE                 JSON stats on stdout
//   --unit-per-mm N                       default 39.370 (0.0254 mm); 40 shows what a
//                                         40 u/mm reader would make of the file
#include "hpgl.h"
#include "view.h"

#include <QActionGroup>
#include <QApplication>
#include <QFileDialog>
#include <QFileInfo>
#include <QFontDatabase>
#include <QGuiApplication>
#include <QKeySequence>
#include <QLabel>
#include <QMainWindow>
#include <QMenuBar>
#include <QMessageBox>
#include <QStatusBar>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>

static int usage()
{
    std::fputs("usage: hpglview [--unit-per-mm N] [FILE]\n"
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

// Terminus, bundled from pcbooker's fonts/ as a Qt resource (as pcbooker's own GUI does)
static QFont terminus(int pt)
{
    static QString family;
    if (family.isEmpty()) {
        for (const char *f : {":/fonts/Terminus.ttf", ":/fonts/TerminusBold.ttf"}) {
            int id = QFontDatabase::addApplicationFont(f);
            if (id >= 0 && family.isEmpty())
                family = QFontDatabase::applicationFontFamilies(id).value(0);
        }
    }
    QFont font(family.isEmpty() ? QString("monospace") : family, pt);
    font.setStyleHint(QFont::Monospace);
    return font;
}

static int renderPng(int argc, char **argv, const char *file, const char *out, int px, double upmm)
{
    qputenv("QT_QPA_PLATFORM", "offscreen");
    QGuiApplication app(argc, argv);
    QGuiApplication::setFont(terminus(11));
    std::string text;
    if (!slurp(file, text)) {
        std::fprintf(stderr, "cannot read %s\n", file);
        return 1;
    }
    hpgl::Plot p = hpgl::parse(text, upmm);
    Paths paths;
    paths.build(p);
    if (!renderImage(p, paths, px, QFileInfo(file).fileName()).save(out)) {
        std::fprintf(stderr, "cannot write %s\n", out);
        return 1;
    }
    std::printf("%s\n", hpgl::stats_json(p).c_str());
    return 0;
}

static void buildMenus(QMainWindow &w, Viewer *v, double upmm)
{
    QMenu *file = w.menuBar()->addMenu("&File");
    file->addAction("&Open...", QKeySequence::Open, &w, [&w, v] {
        QString f = QFileDialog::getOpenFileName(&w, "Open HPGL", QFileInfo(v->path()).path(),
                                                 "HPGL (*.hpgl *.plt *.hpg *.hgl);;All files (*)");
        if (!f.isEmpty() && v->load(f))
            w.setWindowTitle("hpglview - " + QFileInfo(f).fileName());
    });
    file->addAction("&Reload", QKeySequence(Qt::Key_R), v, &Viewer::reload);
    file->addAction("&Export PNG...", QKeySequence("Ctrl+E"), &w, [&w, v] {
        QString f = QFileDialog::getSaveFileName(&w, "Export PNG",
                                                 QFileInfo(v->path()).completeBaseName() + ".png",
                                                 "PNG (*.png)");
        if (!f.isEmpty() && !v->image(3000).save(f))
            QMessageBox::warning(&w, "hpglview", "cannot write " + f);
    });
    file->addSeparator();
    file->addAction("&Quit", QKeySequence::Quit, &w, &QWidget::close);

    QMenu *view = w.menuBar()->addMenu("&View");
    view->addAction("&Fit", QKeySequence(Qt::Key_F), v, &Viewer::fitView);
    view->addAction("Zoom &in", QKeySequence(Qt::Key_Plus), v, [v] { v->zoomBy(1.5); });
    view->addAction("Zoom &out", QKeySequence(Qt::Key_Minus), v, [v] { v->zoomBy(1 / 1.5); });
    view->addSeparator();
    QAction *travel = view->addAction("&Travel moves", QKeySequence(Qt::Key_T), v, &Viewer::setTravel);
    travel->setCheckable(true);
    travel->setChecked(v->opts().travel);
    QAction *grid = view->addAction("mm &grid", QKeySequence(Qt::Key_G), v, &Viewer::setGrid);
    grid->setCheckable(true);
    grid->setChecked(v->opts().grid);

    QMenu *units = w.menuBar()->addMenu("&Units");
    auto *g = new QActionGroup(&w);
    struct U { const char *name; double upmm; };
    for (U u : {U{"0.0254 mm/unit (TRUMPF, 1016/in)", hpgl::UNITS_PER_MM},
                U{"0.025 mm/unit (40/mm)", 40.0}}) {
        QAction *a = units->addAction(u.name, v, [v, x = u.upmm] { v->setUnitsPerMm(x); });
        a->setCheckable(true);
        a->setChecked(std::abs(u.upmm - upmm) < 1e-6);
        g->addAction(a);
    }

    QMenu *help = w.menuBar()->addMenu("&Help");
    help->addAction("&Keys", &w, [&w] {
        QMessageBox::information(&w, "hpglview",
                                 "wheel      zoom at the cursor\n"
                                 "drag       pan\n"
                                 "F          fit\n"
                                 "+ / -      zoom in / out\n"
                                 "T          travel moves on/off\n"
                                 "G          mm grid on/off\n"
                                 "R          reload (also automatic on change)\n"
                                 "Ctrl+O     open\n"
                                 "Ctrl+E     export PNG\n\n"
                                 "red = pen down (cut), blue dashed = pen up (travel)");
    });
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
    if (upmm <= 0 || px < 100 || ((stats || png) && !file))
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
    QFont mono = terminus(12);
    w.statusBar()->setFont(mono);
    pos->setFont(mono);
    pos->setMinimumWidth(QFontMetrics(mono).horizontalAdvance("-0000.000, -0000.000 mm"));
    w.setCentralWidget(v);
    w.statusBar()->addPermanentWidget(pos);
    QObject::connect(v, &Viewer::status, w.statusBar(), [&w](const QString &s) { w.statusBar()->showMessage(s); });
    QObject::connect(v, &Viewer::cursor, pos, &QLabel::setText);
    buildMenus(w, v, upmm);
    w.setWindowTitle(file ? "hpglview - " + QFileInfo(file).fileName() : QString("hpglview"));
    w.resize(1200, 900);
    w.show();
    if (file && !v->load(file))
        return 1;
    return app.exec();
}
