#include "view.h"

#include <QFile>
#include <QFileInfo>
#include <QMouseEvent>
#include <QPainter>
#include <QTimer>
#include <QWheelEvent>
#include <cmath>

void Paths::build(const hpgl::Plot &p)
{
    by_pen.clear();
    bounds = QRectF();
    for (const auto &s : p.segs) {
        QPainterPath &pp = by_pen[{s.pen, s.down}];
        if (pp.isEmpty() || pp.currentPosition() != QPointF(s.x0, s.y0))
            pp.moveTo(s.x0, s.y0);
        pp.lineTo(s.x1, s.y1);
    }
    // fit to the cut: the travel from the origin to the first cut is not the board
    for (bool down : {true, false}) {
        for (const auto &kv : by_pen)
            if (kv.first.second == down)
                bounds = bounds.isNull() ? kv.second.boundingRect()
                                         : bounds.united(kv.second.boundingRect());
        if (!bounds.isNull())
            break;
    }
}

static QColor penColor(int pen)
{
    static const QColor c[] = {Qt::black, QColor(200, 0, 0), QColor(0, 120, 0), QColor(0, 0, 200),
                               QColor(160, 0, 160), QColor(0, 140, 140), QColor(200, 120, 0)};
    return c[pen >= 0 && pen < 7 ? pen : 0];
}

// grid step in mm: 1, 2, 5 x 10^k, at least 25 px apart
static double gridStep(double px_per_mm)
{
    for (double k = 0.01;; k *= 10)
        for (double m : {1.0, 2.0, 5.0})
            if (k * m * px_per_mm >= 25)
                return k * m;
}

void draw(QPainter &g, const hpgl::Plot &p, const Paths &paths, double scale, QPointF origin,
          QSize size, const DrawOpts &o)
{
    g.fillRect(QRect(QPoint(0, 0), size), Qt::white);
    g.setRenderHint(QPainter::Antialiasing, true);
    QTransform t(scale, 0, 0, -scale, origin.x(), origin.y());

    if (o.grid) {
        double ppm = scale * p.units_per_mm;
        double step = gridStep(ppm);
        QTransform inv = t.inverted();
        QRectF vis = inv.mapRect(QRectF(QPoint(0, 0), size));
        double x0 = std::floor(vis.left() / p.units_per_mm / step) * step;
        double y0 = std::floor(vis.top() / p.units_per_mm / step) * step;
        g.setPen(QPen(QColor(230, 230, 240), 0));
        for (double x = x0; x * p.units_per_mm <= vis.right(); x += step) {
            double sx = t.map(QPointF(x * p.units_per_mm, 0)).x();
            g.drawLine(QPointF(sx, 0), QPointF(sx, size.height()));
        }
        for (double y = y0; y * p.units_per_mm <= vis.bottom(); y += step) {
            double sy = t.map(QPointF(0, y * p.units_per_mm)).y();
            g.drawLine(QPointF(0, sy), QPointF(size.width(), sy));
        }
        g.setPen(QColor(150, 150, 170));
        g.drawText(QPointF(6, size.height() - 6), QString("grid %1 mm").arg(step));
    }

    g.save();
    g.setTransform(t);
    for (const auto &[key, path] : paths.by_pen) {
        if (!key.second && !o.travel)
            continue;
        QPen pen(key.second ? penColor(key.first) : QColor(120, 120, 255), 0); // cosmetic 1 px
        if (!key.second)
            pen.setStyle(Qt::DashLine);
        g.setPen(pen);
        g.drawPath(path);
    }
    g.restore();
}

void fit(const Paths &paths, QSize size, double &scale, QPointF &origin)
{
    QRectF b = paths.bounds;
    if (b.isNull() || b.width() + b.height() <= 0) {
        scale = 1;
        origin = QPointF(20, size.height() - 20);
        return;
    }
    const double m = 20;
    double sx = (size.width() - 2 * m) / std::max(b.width(), 1.0);
    double sy = (size.height() - 2 * m) / std::max(b.height(), 1.0);
    scale = std::min(sx, sy);
    // centre the box: screen = (x*scale + ox, -y*scale + oy)
    origin = QPointF(size.width() / 2.0 - b.center().x() * scale,
                     size.height() / 2.0 + b.center().y() * scale);
}

QString summary(const hpgl::Plot &p)
{
    const auto &s = p.st;
    QString u = QString::number(p.units_per_mm, 'f', 3);
    if (!s.has_cut)
        return QString("no cut  |  %1 u/mm").arg(u);
    QString r = QString("%1 x %2 mm  |  cut %3 mm  travel %4 mm  |  lifts %5  zero %6  |  %7 u/mm")
                    .arg(s.max_x_mm - s.min_x_mm, 0, 'f', 2)
                    .arg(s.max_y_mm - s.min_y_mm, 0, 'f', 2)
                    .arg(s.cut_mm, 0, 'f', 1)
                    .arg(s.travel_mm, 0, 'f', 1)
                    .arg(s.pen_lifts)
                    .arg(s.zero_len)
                    .arg(u);
    if (!s.unknown.empty()) {
        r += "  |  unknown:";
        for (const auto &[m, n] : s.unknown)
            r += QString(" %1x%2").arg(QString::fromStdString(m)).arg(n);
    }
    return r;
}

QImage renderImage(const hpgl::Plot &p, const Paths &paths, int px, const QString &title,
                   const DrawOpts &o)
{
    // aspect of the plot, longest side = px, plus a strip for the summary line
    QSizeF b = paths.bounds.size();
    double ar = (b.width() > 0 && b.height() > 0) ? b.width() / b.height() : 1.0;
    QSize area = ar >= 1 ? QSize(px, std::max(100, int(px / ar)))
                         : QSize(std::max(100, int(px * ar)), px);
    const int strip = 24;
    QImage img(area.width(), area.height() + strip, QImage::Format_RGB32);
    img.fill(Qt::white);
    QPainter g(&img);
    double scale;
    QPointF origin;
    fit(paths, area, scale, origin);
    g.translate(0, strip);
    draw(g, p, paths, scale, origin, area, o);
    g.resetTransform();
    g.fillRect(0, 0, img.width(), strip, QColor(245, 245, 245));
    g.setPen(Qt::black);
    g.drawText(QRect(6, 0, img.width() - 12, strip), Qt::AlignVCenter, title + "  |  " + summary(p));
    return img;
}

Viewer::Viewer(double units_per_mm, QWidget *parent) : QWidget(parent), upmm_(units_per_mm)
{
    setMouseTracking(true);
    setFocusPolicy(Qt::StrongFocus);
    setMinimumSize(400, 300);
    // an exporter rewrites the file: reload a moment later, re-add the watch (it is lost on replace)
    connect(&watch_, &QFileSystemWatcher::fileChanged, this, [this] {
        QTimer::singleShot(300, this, [this] { reload(); });
    });
}

QString Viewer::title() const
{
    return QFileInfo(path_).fileName();
}

bool Viewer::load(const QString &path)
{
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly)) {
        emit status("cannot open " + path);
        return false;
    }
    if (path != path_) { // another file: watch it instead, fit it once
        if (!watch_.files().isEmpty())
            watch_.removePaths(watch_.files());
        fitted_ = false;
    }
    path_ = path;
    plot_ = hpgl::parse(f.readAll().toStdString(), upmm_);
    paths_.build(plot_);
    if (!watch_.files().contains(path))
        watch_.addPath(path);
    if (!fitted_) {
        fitView();
        fitted_ = true;
    }
    emit status(title() + "  |  " + summary(plot_));
    update();
    return true;
}

void Viewer::setUnitsPerMm(double u)
{
    upmm_ = u;
    reload();
}

void Viewer::fitView()
{
    fit(paths_, size(), scale_, origin_);
    update();
}

void Viewer::zoomBy(double k)
{
    QPointF c(width() / 2.0, height() / 2.0);
    origin_ = c + (origin_ - c) * k;
    scale_ *= k;
    update();
}

void Viewer::paintEvent(QPaintEvent *)
{
    QPainter g(this);
    draw(g, plot_, paths_, scale_, origin_, size(), opts_);
}

void Viewer::resizeEvent(QResizeEvent *)
{
    if (fitted_)
        fitView();
}

void Viewer::wheelEvent(QWheelEvent *e)
{
    double k = std::pow(1.2, e->angleDelta().y() / 120.0);
    QPointF c = e->position();
    origin_ = c + (origin_ - c) * k; // keep the point under the cursor fixed
    scale_ *= k;
    update();
}

void Viewer::mousePressEvent(QMouseEvent *e)
{
    drag_ = e->position();
}

void Viewer::mouseMoveEvent(QMouseEvent *e)
{
    if (e->buttons() & (Qt::LeftButton | Qt::MiddleButton)) {
        origin_ += e->position() - drag_;
        drag_ = e->position();
        update();
    }
    double x = (e->position().x() - origin_.x()) / scale_ / upmm_;
    double y = (origin_.y() - e->position().y()) / scale_ / upmm_;
    emit cursor(QString("%1, %2 mm").arg(x, 0, 'f', 3).arg(y, 0, 'f', 3));
}
