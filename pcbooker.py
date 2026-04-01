#!/usr/bin/env python3
"""
PCBooker — Gerber viewer + isolation routing + HPGL export

Interactive GUI for PCB laser engraving preparation.
Loads multi-layer Gerber files, generates isolation toolpaths,
checks for open contours, exports HPGL for laser.

Copyright 2026 SCteam (smooker/LZ1CCM)
License: GPL-2.0
"""

import os
import sys
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QScrollArea, QLabel, QCheckBox, QComboBox,
    QDoubleSpinBox, QPushButton, QFileDialog, QMessageBox,
    QStatusBar, QGroupBox, QFrame
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette

import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MplPath

from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
import numpy as np

import gerber_loader
import isolation
import contour_check
import hpgl_export


LAYER_COLORS = {
    'top_copper':    '#ff0000',
    'bottom_copper': '#0000ff',
    'top_mask':      '#00ff0080',
    'bottom_mask':   '#00ff0080',
    'top_silk':      '#ffff00',
    'bottom_silk':   '#ffff00',
    'outline':       '#ffffff',
    'drill_0':       '#00ffff',
}
DEFAULT_COLOR = '#ff8800'
ISOLATION_COLOR = '#00ff00'
PROBLEM_COLOR = '#ff0000'


def shapely_to_mpl_path(geom):
    """Convert Shapely geometry to matplotlib Path for rendering."""
    paths = []
    if isinstance(geom, Polygon):
        coords = np.array(geom.exterior.coords)
        codes = [MplPath.MOVETO] + [MplPath.LINETO] * (len(coords) - 2) + [MplPath.CLOSEPOLY]
        paths.append((coords, codes))
        for interior in geom.interiors:
            coords = np.array(interior.coords)
            codes = [MplPath.MOVETO] + [MplPath.LINETO] * (len(coords) - 2) + [MplPath.CLOSEPOLY]
            paths.append((coords, codes))
    elif isinstance(geom, MultiPolygon):
        for poly in geom.geoms:
            paths.extend(shapely_to_mpl_path(poly))
    return paths


def plot_geometry(ax, geom, color='red', alpha=0.5, linewidth=0.5):
    """Plot Shapely geometry on matplotlib axes."""
    if geom is None or geom.is_empty:
        return
    if isinstance(geom, (Polygon, MultiPolygon)):
        for coords, codes in shapely_to_mpl_path(geom):
            path = MplPath(coords, codes)
            patch = PathPatch(path, facecolor=color, edgecolor='none',
                              alpha=alpha, linewidth=linewidth)
            ax.add_patch(patch)
    elif isinstance(geom, (LineString, MultiLineString)):
        lines = [geom] if isinstance(geom, LineString) else list(geom.geoms)
        for line in lines:
            coords = np.array(line.coords)
            ax.plot(coords[:, 0], coords[:, 1], color=color,
                    linewidth=linewidth, alpha=alpha)


def plot_linestrings(ax, paths, color='green', linewidth=1.0, alpha=0.8):
    """Plot list of LineString/LinearRing paths."""
    for path in paths:
        coords = np.array(path.coords)
        ax.plot(coords[:, 0], coords[:, 1], color=color,
                linewidth=linewidth, alpha=alpha)


class LayerWidget(QFrame):
    """Single layer row with visibility, iso, mode, offset controls."""

    def __init__(self, name, color, on_change=None, iso_controls=True, parent=None):
        super().__init__(parent)
        self.layer_name = name
        self._on_change = on_change
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # Visible checkbox
        self.cb_visible = QCheckBox()
        self.cb_visible.setChecked(True)
        self.cb_visible.setToolTip("Show/hide layer")
        self.cb_visible.stateChanged.connect(self._changed)
        layout.addWidget(self.cb_visible)

        # Color indicator
        color_lbl = QLabel("  ")
        color_lbl.setFixedWidth(16)
        color_lbl.setFixedHeight(16)
        color_lbl.setStyleSheet(f"background-color: {color[:7]}; border: 1px solid #666;")
        layout.addWidget(color_lbl)

        # Layer name
        name_lbl = QLabel(name)
        name_lbl.setMinimumWidth(100)
        layout.addWidget(name_lbl, stretch=1)

        # Iso controls (not shown for generated isolation layers)
        self.cb_iso = None
        self.combo_mode = None
        self.spin_offset = None

        if iso_controls:
            self.cb_iso = QCheckBox("Iso")
            self.cb_iso.setToolTip("Include in isolation routing")
            self.cb_iso.stateChanged.connect(self._changed)
            layout.addWidget(self.cb_iso)

            self.combo_mode = QComboBox()
            self.combo_mode.addItems(["outline", "inline"])
            self.combo_mode.setFixedWidth(80)
            layout.addWidget(self.combo_mode)

            layout.addWidget(QLabel("mm:"))
            self.spin_offset = QDoubleSpinBox()
            self.spin_offset.setRange(0.01, 5.0)
            self.spin_offset.setSingleStep(0.05)
            self.spin_offset.setValue(0.10)
            self.spin_offset.setDecimals(2)
            self.spin_offset.setFixedWidth(70)
            layout.addWidget(self.spin_offset)

    def _changed(self):
        if self._on_change:
            self._on_change()


class PCBookerWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PCBooker — Gerber Viewer + Isolation")
        self.resize(1200, 800)

        self.layers = {}
        self.geometries = {}
        self.merged = {}
        self.iso_paths = {}
        self.problems = {}
        self.layer_widgets = {}
        self.iso_widgets = {}   # isolation layer widgets (separate)

        self._build_ui()

    def _build_ui(self):
        splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter)

        # --- Left panel ---
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(5, 5, 5, 5)

        left_layout.addWidget(QLabel("<b>Layers</b>"))

        # Scrollable layer list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._layer_container = QWidget()
        self._layer_layout = QVBoxLayout(self._layer_container)
        self._layer_layout.setContentsMargins(0, 0, 0, 0)
        self._layer_layout.setSpacing(2)
        self._layer_layout.addStretch()
        scroll.setWidget(self._layer_container)
        left_layout.addWidget(scroll, stretch=1)

        # Buttons
        buttons = [
            ("Load Gerbers (dir)...", self.load_gerbers),
            ("Load Files...",        self.load_files),
            ("Check Contours",       self.check_contours),
            ("Generate Isolation",   self.generate_isolation),
            ("Export HPGL",          self.export_hpgl),
        ]
        for text, slot in buttons:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            left_layout.addWidget(btn)

        left.setFixedWidth(360)
        splitter.addWidget(left)

        # --- Right panel: matplotlib ---
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.fig = Figure(figsize=(8, 6), facecolor='black')
        self.ax = self.fig.add_subplot(111)
        self._setup_axes()

        self.canvas = FigureCanvasQTAgg(self.fig)
        toolbar = NavigationToolbar2QT(self.canvas, right)
        right_layout.addWidget(toolbar)
        right_layout.addWidget(self.canvas, stretch=1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        # Status bar
        self.statusBar().showMessage("Ready. Load Gerber files to begin.")

    def _setup_axes(self):
        self.ax.set_facecolor('black')
        self.ax.set_aspect('equal')
        self.ax.grid(True, color='#333333', linewidth=0.5)
        self.ax.set_xlabel('mm')
        self.ax.set_ylabel('mm')

    # --- File loading ---

    def load_gerbers(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Gerber directory")
        if not directory:
            return
        self.statusBar().showMessage(f"Loading Gerbers from {directory}...")
        QApplication.processEvents()
        try:
            self.layers = gerber_loader.load_board(directory)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load Gerbers:\n{e}")
            self.statusBar().showMessage(f"Error: {e}")
            return
        self._process_layers()

    def load_files(self):
        filepaths, _ = QFileDialog.getOpenFileNames(
            self, "Select Gerber files", "",
            "Gerber files (*.gbr *.ger *.gtl *.gbl *.gts *.gbs *.gto *.gbo *.gm1 "
            "*.GTL *.GBL *.GTS *.GBS *.GTO *.GBO);;Drill files (*.drl *.DRL *.xln);;All files (*)")
        if not filepaths:
            return
        self.statusBar().showMessage(f"Loading {len(filepaths)} files...")
        QApplication.processEvents()
        self.layers = gerber_loader.load_gerber_files(filepaths)
        self._process_layers()

    def _process_layers(self):
        # Clear old widgets
        for w in list(self.layer_widgets.values()):
            self._layer_layout.removeWidget(w)
            w.deleteLater()
        self.layer_widgets.clear()
        self.geometries.clear()
        self.merged.clear()
        self.iso_paths.clear()
        self.problems.clear()

        for name, layer in self.layers.items():
            self.statusBar().showMessage(f"Processing {name}...")
            QApplication.processEvents()

            color = LAYER_COLORS.get(name, DEFAULT_COLOR)
            widget = LayerWidget(name, color, on_change=self.refresh_view)
            # Insert before the stretch
            self._layer_layout.insertWidget(self._layer_layout.count() - 1, widget)
            self.layer_widgets[name] = widget

            geoms = gerber_loader.layer_to_polygons(layer)
            self.geometries[name] = geoms
            merged = gerber_loader.layer_to_merged(layer)
            self.merged[name] = merged

        total = sum(len(g) for g in self.geometries.values())
        self.statusBar().showMessage(
            f"Loaded {len(self.layers)} layers, {total} objects.")
        self.refresh_view()

    # --- Actions ---

    def check_contours(self):
        total_problems = 0
        for name, geoms in self.geometries.items():
            problems = contour_check.check_closed_contours(geoms)
            self.problems[name] = problems
            total_problems += len(problems)

        if total_problems == 0:
            QMessageBox.information(self, "Contour Check", "All contours are closed!")
            self.statusBar().showMessage("Contour check: OK")
        else:
            msg = f"{total_problems} open contour(s) found!\n\n"
            for name, probs in self.problems.items():
                if probs:
                    msg += f"{name}: {len(probs)} open\n"
                    for p in probs:
                        msg += f"  Gap: {p['gap_size_mm']:.3f} mm\n"
            QMessageBox.warning(self, "Contour Check", msg)
            self.statusBar().showMessage(f"Contour check: {total_problems} problems!")
        self.refresh_view()

    def generate_isolation(self):
        # Clear old isolation paths and widgets
        self.iso_paths.clear()
        for w in list(self.iso_widgets.values()):
            self._layer_layout.removeWidget(w)
            w.deleteLater()
        self.iso_widgets.clear()

        count = 0
        selected = 0

        for name, widget in self.layer_widgets.items():
            if widget.cb_iso is None or not widget.cb_iso.isChecked():
                continue
            selected += 1

            merged = self.merged.get(name)
            if merged is None:
                continue

            offset = widget.spin_offset.value()
            mode = widget.combo_mode.currentText()

            try:
                paths = isolation.isolation_paths(merged, offset, mode)
            except Exception as e:
                print(f"  ERROR: {name} isolation failed: {e}")
                continue

            if paths:
                iso_name = f"iso: {name} ({offset}mm {mode})"
                self.iso_paths[iso_name] = paths
                count += len(paths)

                # Add as visible layer in the panel
                iso_widget = LayerWidget(iso_name, ISOLATION_COLOR,
                                         on_change=self.refresh_view,
                                         iso_controls=False)
                self._layer_layout.insertWidget(
                    self._layer_layout.count() - 1, iso_widget)
                self.iso_widgets[iso_name] = iso_widget

        if selected == 0:
            QMessageBox.information(self, "Isolation",
                                    "No layers have 'Iso' checked.\n\n"
                                    "Check the Iso checkbox on copper layers,\n"
                                    "then click Generate Isolation again.")
            self.statusBar().showMessage("No layers selected for isolation!")
            return

        self.statusBar().showMessage(
            f"Generated {count} isolation paths from {selected} layer(s).")
        self.refresh_view()

    def export_hpgl(self):
        if not self.iso_paths:
            QMessageBox.warning(self, "Export",
                                "No isolation paths to export.\n"
                                "Check Iso, Generate Isolation first.")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export HPGL", "", "HPGL files (*.hpgl *.plt);;All files (*)")
        if not filepath:
            return

        all_geoms = []
        for name, paths in self.iso_paths.items():
            for path in paths:
                if hasattr(path, 'coords'):
                    all_geoms.append(LineString(path.coords))

        hpgl_export.export_hpgl(all_geoms, filepath)
        self.statusBar().showMessage(f"Exported {len(all_geoms)} paths to {filepath}")
        QMessageBox.information(self, "Export", f"HPGL saved to:\n{filepath}")

    # --- Drawing ---

    def refresh_view(self):
        self.ax.clear()
        self._setup_axes()

        for name, widget in self.layer_widgets.items():
            if not widget.cb_visible.isChecked():
                continue
            color = LAYER_COLORS.get(name, DEFAULT_COLOR)
            for geom in self.geometries.get(name, []):
                plot_geometry(self.ax, geom, color=color, alpha=0.6)

        for name, paths in self.iso_paths.items():
            iso_w = self.iso_widgets.get(name)
            if iso_w and not iso_w.cb_visible.isChecked():
                continue
            plot_linestrings(self.ax, paths, color=ISOLATION_COLOR,
                             linewidth=1.5, alpha=0.9)

        for name, probs in self.problems.items():
            for p in probs:
                if p['gap_start'] and p['gap_end']:
                    sx, sy = p['gap_start']
                    ex, ey = p['gap_end']
                    self.ax.plot([sx, ex], [sy, ey], 'x-',
                                color=PROBLEM_COLOR, markersize=10, linewidth=2)
                    self.ax.annotate(f"{p['gap_size_mm']:.2f}mm",
                                     xy=((sx+ex)/2, (sy+ey)/2),
                                     color=PROBLEM_COLOR, fontsize=8)

        self.ax.autoscale_view()
        self.canvas.draw()


def main():
    app = QApplication(sys.argv)
    win = PCBookerWindow()
    win.show()

    if len(sys.argv) > 1:
        path = sys.argv[1]
        if os.path.isdir(path):
            win.layers = gerber_loader.load_board(path)
            win._process_layers()
        else:
            win.layers = gerber_loader.load_gerber_files(sys.argv[1:])
            win._process_layers()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
