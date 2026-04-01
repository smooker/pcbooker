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

    selected = False
    _normal_style = ""
    _selected_style = "background-color: #335588; border: 1px solid #5588cc;"

    def __init__(self, name, color, on_change=None, iso_controls=True,
                 info_text=None, selectable=False, parent=None):
        super().__init__(parent)
        self.layer_name = name
        self._on_change = on_change
        self._selectable = selectable
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
        self.spin_passes = None

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
            self.spin_offset.setFixedWidth(60)
            self.spin_offset.setToolTip("First pass offset from copper")
            layout.addWidget(self.spin_offset)

            layout.addWidget(QLabel("x"))
            from PyQt5.QtWidgets import QSpinBox
            self.spin_passes = QSpinBox()
            self.spin_passes.setRange(1, 20)
            self.spin_passes.setValue(1)
            self.spin_passes.setFixedWidth(45)
            self.spin_passes.setToolTip(
                "Number of passes. Each additional pass\n"
                "is 0.05mm (50um) further from the previous.\n"
                "1 = single pass only.")
            layout.addWidget(self.spin_passes)

        elif info_text:
            # Read-only info for generated isolation layers
            info = QLabel(info_text)
            info.setStyleSheet("color: #888; font-size: 10px;")
            layout.addWidget(info)

    def set_selected(self, sel):
        self.selected = sel
        if sel:
            self.setStyleSheet(self._selected_style)
        else:
            self.setStyleSheet(self._normal_style)

    def mousePressEvent(self, event):
        if self._selectable:
            # Let the parent window handle selection logic
            win = self.window()
            if hasattr(win, '_on_layer_clicked'):
                win._on_layer_clicked(self, event)
        super().mousePressEvent(event)

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
        self._last_clicked_iso = None  # for shift-select range

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
            ("Gap Analysis",         self.gap_analysis),
            ("Generate Isolation",   self.generate_isolation),
            ("Delete Selected",      self.delete_selected_iso),
            ("Export HPGL",          self.export_hpgl),
        ]
        for text, slot in buttons:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            left_layout.addWidget(btn)

        # Min gap control (laser beam width — merges paths closer than this)
        gap_frame = QHBoxLayout()
        gap_frame.addWidget(QLabel("Min gap:"))
        self.spin_min_gap = QDoubleSpinBox()
        self.spin_min_gap.setRange(0.0, 2.0)
        self.spin_min_gap.setSingleStep(0.05)
        self.spin_min_gap.setValue(0.10)
        self.spin_min_gap.setDecimals(2)
        self.spin_min_gap.setSuffix(" mm")
        self.spin_min_gap.setToolTip(
            "Isolation paths closer than this get merged.\n"
            "Set to laser beam width to prevent double burns.")
        gap_frame.addWidget(self.spin_min_gap)
        left_layout.addLayout(gap_frame)

        # Pass step (distance between multi-pass outlines)
        step_frame = QHBoxLayout()
        step_frame.addWidget(QLabel("Pass step:"))
        self.spin_pass_step = QDoubleSpinBox()
        self.spin_pass_step.setRange(0.01, 1.0)
        self.spin_pass_step.setSingleStep(0.01)
        self.spin_pass_step.setValue(0.05)
        self.spin_pass_step.setDecimals(2)
        self.spin_pass_step.setSuffix(" mm")
        self.spin_pass_step.setToolTip(
            "Distance between each additional pass.\n"
            "Default 0.05mm (50um).")
        step_frame.addWidget(self.spin_pass_step)
        left_layout.addLayout(step_frame)

        # Overlap distance (path dedup — skip segments near already-drawn paths)
        dedup_frame = QHBoxLayout()
        dedup_frame.addWidget(QLabel("Dedup:"))
        self.spin_dedup = QDoubleSpinBox()
        self.spin_dedup.setRange(0.0, 1.0)
        self.spin_dedup.setSingleStep(0.01)
        self.spin_dedup.setValue(0.05)
        self.spin_dedup.setDecimals(2)
        self.spin_dedup.setSuffix(" mm")
        self.spin_dedup.setToolTip(
            "Skip path segments closer than this to already-drawn paths.\n"
            "Pen lifts near old paths, drops when clear. Prevents double laser pass.")
        dedup_frame.addWidget(self.spin_dedup)
        left_layout.addLayout(dedup_frame)

        left.setFixedWidth(360)
        splitter.addWidget(left)

        # --- Right panel: matplotlib ---
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.fig = Figure(facecolor='black')
        self.fig.set_tight_layout(True)
        self.ax = self.fig.add_subplot(111)
        self._setup_axes()

        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.setSizePolicy(
            self.canvas.sizePolicy().horizontalPolicy(),
            self.canvas.sizePolicy().verticalPolicy())
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

    def gap_analysis(self):
        """Analyze gaps between copper features and report."""
        if not self.merged:
            QMessageBox.information(self, "Gap Analysis", "Load Gerber files first.")
            return

        msg = ""
        for name, widget in self.layer_widgets.items():
            merged = self.merged.get(name)
            if merged is None:
                continue
            offset = widget.spin_offset.value() if widget.spin_offset else 0.1
            gaps = isolation.gap_analysis(merged, offset)
            if not gaps:
                continue

            tight = [g for g in gaps if g['status'] == 'tight']
            overlap = [g for g in gaps if g['status'] == 'overlap']

            if tight or overlap:
                msg += f"{name} (offset={offset}mm):\n"
                if overlap:
                    msg += f"  {len(overlap)} gaps < offset — copper overlaps in isolation!\n"
                    for g in overlap[:3]:
                        msg += f"    gap: {g['gap_mm']:.3f}mm (need >{2*offset:.2f}mm)\n"
                if tight:
                    msg += f"  {len(tight)} tight gaps — paths will be merged\n"
                    for g in tight[:3]:
                        msg += f"    gap: {g['gap_mm']:.3f}mm (max offset: {g['min_offset']:.3f}mm)\n"
                msg += "\n"

        if not msg:
            QMessageBox.information(self, "Gap Analysis", "All gaps OK for current offsets.")
        else:
            QMessageBox.warning(self, "Gap Analysis", msg)
        self.statusBar().showMessage("Gap analysis complete.")

    def _add_iso_layer(self, iso_name, paths, info_text, color=None):
        """Add an isolation result as a toggleable, selectable layer."""
        if not paths:
            return 0
        self.iso_paths[iso_name] = paths
        iso_widget = LayerWidget(iso_name, color or ISOLATION_COLOR,
                                  on_change=self.refresh_view,
                                  iso_controls=False,
                                  info_text=info_text,
                                  selectable=True)
        self._layer_layout.insertWidget(
            self._layer_layout.count() - 1, iso_widget)
        self.iso_widgets[iso_name] = iso_widget
        return len(paths)

    def _on_layer_clicked(self, widget, event):
        """Handle click on iso layer for selection (Ctrl/Shift)."""
        from PyQt5.QtCore import Qt as QtC
        modifiers = QApplication.keyboardModifiers()
        iso_names = list(self.iso_widgets.keys())

        if widget.layer_name not in self.iso_widgets:
            return

        if modifiers & QtC.ControlModifier:
            # Ctrl+click: toggle this one
            widget.set_selected(not widget.selected)
        elif modifiers & QtC.ShiftModifier:
            # Shift+click: range select from last clicked
            if self._last_clicked_iso and self._last_clicked_iso in iso_names:
                idx_a = iso_names.index(self._last_clicked_iso)
                idx_b = iso_names.index(widget.layer_name)
                lo, hi = min(idx_a, idx_b), max(idx_a, idx_b)
                for i, name in enumerate(iso_names):
                    self.iso_widgets[name].set_selected(lo <= i <= hi)
            else:
                widget.set_selected(True)
        else:
            # Plain click: select only this one
            for w in self.iso_widgets.values():
                w.set_selected(False)
            widget.set_selected(True)

        self._last_clicked_iso = widget.layer_name

    def delete_selected_iso(self):
        """Delete selected isolation layers."""
        to_delete = [name for name, w in self.iso_widgets.items() if w.selected]
        if not to_delete:
            self.statusBar().showMessage("No iso layers selected. "
                                          "Click to select, Ctrl/Shift for multi.")
            return

        for name in to_delete:
            w = self.iso_widgets.pop(name)
            self._layer_layout.removeWidget(w)
            w.deleteLater()
            self.iso_paths.pop(name, None)

        self._last_clicked_iso = None
        self.statusBar().showMessage(f"Deleted {len(to_delete)} iso layer(s).")
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
        min_gap = self.spin_min_gap.value()
        pass_step = self.spin_pass_step.value()

        # Colors for multi-pass (cycle through)
        pass_colors = [ISOLATION_COLOR, '#00cc88', '#00aaff', '#ffaa00',
                       '#ff00ff', '#88ff00', '#00ffff', '#ff8800']

        for name, widget in self.layer_widgets.items():
            if widget.cb_iso is None or not widget.cb_iso.isChecked():
                continue
            selected += 1

            merged = self.merged.get(name)
            if merged is None:
                continue

            offset = widget.spin_offset.value()
            mode = widget.combo_mode.currentText()
            num_passes = widget.spin_passes.value()

            print(f"\n=== Isolation: {name} ===")
            print(f"  Mode: {mode}, offset: {offset}mm, "
                  f"passes: {num_passes}, step: {pass_step}mm, "
                  f"min_gap: {min_gap}mm")

            for p in range(num_passes):
                cur_offset = offset + p * pass_step
                pass_num = p + 1

                print(f"  --- Pass {pass_num}/{num_passes}: "
                      f"offset={cur_offset:.3f}mm ---")

                try:
                    paths = isolation.isolation_paths(
                        merged, cur_offset, mode, min_gap_mm=min_gap)
                except Exception as e:
                    print(f"    ERROR: {e}")
                    continue

                total_len = sum(
                    len(list(pt.coords)) for pt in paths) if paths else 0
                print(f"    Result: {len(paths)} paths, "
                      f"{total_len} points")

                if not paths:
                    print(f"    No paths at this offset — "
                          f"gap too narrow, stopping.")
                    break

                iso_name = f"iso: {name} pass{pass_num}"
                info = (f"pass {pass_num}: {mode} {cur_offset:.2f}mm "
                        f"(base={offset}+{p}x{pass_step})")
                color = pass_colors[p % len(pass_colors)]
                n = self._add_iso_layer(iso_name, paths, info, color=color)
                count += n
                print(f"    Added {n} paths as layer '{iso_name}'")

        if selected == 0:
            QMessageBox.information(self, "Isolation",
                                    "No layers have 'Iso' checked.\n\n"
                                    "Check the Iso checkbox on copper layers,\n"
                                    "then click Generate Isolation again.")
            self.statusBar().showMessage("No layers selected for isolation!")
            return

        gap_info = f" (min_gap={min_gap}mm)" if min_gap > 0 else ""
        self.statusBar().showMessage(
            f"Generated {count} isolation paths from {selected} layer(s){gap_info}.")
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

        # Collect all visible paths
        all_paths = []
        print(f"\n=== HPGL Export ===")
        for name, paths in self.iso_paths.items():
            iso_w = self.iso_widgets.get(name)
            if iso_w and not iso_w.cb_visible.isChecked():
                print(f"  SKIP (hidden): {name}")
                continue
            all_paths.extend(paths)
            print(f"  Include: {name} — {len(paths)} paths")

        total_before = sum(
            (LineString(p.coords) if not isinstance(p, LineString) else p).length
            for p in all_paths)
        print(f"  Total: {len(all_paths)} paths, {total_before:.1f}mm")

        # Deduplicate — skip segments near already-drawn paths
        dedup_dist = self.spin_dedup.value()
        if dedup_dist > 0:
            before_n = len(all_paths)
            all_paths = isolation.deduplicate_paths(all_paths, dedup_dist)
            total_after = sum(p.length for p in all_paths)
            saved = total_before - total_after
            print(f"  Dedup (min_dist={dedup_dist}mm): "
                  f"{before_n} -> {len(all_paths)} segments")
            print(f"  Length: {total_before:.1f}mm -> {total_after:.1f}mm "
                  f"(saved {saved:.1f}mm = {saved/max(total_before,1)*100:.1f}%)")

        all_geoms = [p if isinstance(p, LineString) else LineString(p.coords)
                     for p in all_paths]

        hpgl_export.export_hpgl(all_geoms, filepath)
        print(f"  Written: {filepath}")
        self.statusBar().showMessage(
            f"Exported {len(all_geoms)} paths to {filepath}")
        QMessageBox.information(self, "Export",
                                f"HPGL saved to:\n{filepath}\n"
                                f"{len(all_geoms)} path segments")

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
        self.fig.tight_layout(pad=0.5)
        self.canvas.draw()


def _load_fonts():
    """Load bundled Terminus font from fonts/ directory."""
    from PyQt5.QtGui import QFontDatabase, QFont
    font_dir = Path(__file__).parent / 'fonts'
    loaded = []
    if font_dir.is_dir():
        for ttf in sorted(font_dir.glob('*.ttf')):
            fid = QFontDatabase.addApplicationFont(str(ttf))
            if fid >= 0:
                families = QFontDatabase.applicationFontFamilies(fid)
                loaded.extend(families)
    return loaded


def main():
    app = QApplication(sys.argv)

    # Load bundled font and apply as default
    families = _load_fonts()
    if families:
        from PyQt5.QtGui import QFont
        font = QFont(families[0], 11)
        app.setFont(font)

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
