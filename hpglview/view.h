// Drawing and the interactive widget. The PNG export uses the same draw code.
#pragma once

#include "hpgl.h"

#include <QFileSystemWatcher>
#include <QPainterPath>
#include <QPointF>
#include <QString>
#include <QWidget>
#include <map>

class QPainter;

struct DrawOpts {
    bool travel = true; // pen-up moves, dashed
    bool grid = true;   // mm grid
};

// Plot geometry as painter paths in plotter units, one per (pen, down). Built once per load.
struct Paths {
    std::map<std::pair<int, bool>, QPainterPath> by_pen;
    QRectF bounds; // pen-down segments (all segments if nothing is cut), plotter units
    void build(const hpgl::Plot &p);
};

// scale = pixels per plotter unit; origin = screen position of plotter (0,0). Y points up.
void draw(QPainter &g, const hpgl::Plot &p, const Paths &paths, double scale, QPointF origin,
          QSize size, const DrawOpts &o);
// scale/origin that fit the plot into size with a margin
void fit(const Paths &paths, QSize size, double &scale, QPointF &origin);
QString summary(const hpgl::Plot &p);

class Viewer : public QWidget {
    Q_OBJECT
public:
    explicit Viewer(double units_per_mm, QWidget *parent = nullptr);
    bool load(const QString &path);
signals:
    void status(const QString &s);
    void cursor(const QString &s);
protected:
    void paintEvent(QPaintEvent *) override;
    void resizeEvent(QResizeEvent *) override;
    void wheelEvent(QWheelEvent *) override;
    void mousePressEvent(QMouseEvent *) override;
    void mouseMoveEvent(QMouseEvent *) override;
    void keyPressEvent(QKeyEvent *) override;
private:
    void doFit();
    hpgl::Plot plot_;
    Paths paths_;
    QString path_;
    double upmm_;
    double scale_ = 1;
    QPointF origin_;
    QPointF drag_;
    bool fitted_ = false;
    DrawOpts opts_;
    QFileSystemWatcher watch_;
};
