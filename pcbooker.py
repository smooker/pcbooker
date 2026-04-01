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
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MplPath
from matplotlib.collections import PatchCollection
import matplotlib.pyplot as plt

from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
import numpy as np

import gerber_loader
import isolation
import contour_check
import hpgl_export


# Layer colors for visualization
LAYER_COLORS = {
    'top_copper':  '#ff0000',
    'bottom_copper': '#0000ff',
    'top_mask':    '#00ff0080',
    'bottom_mask': '#00ff0080',
    'top_silk':    '#ffff00',
    'bottom_silk': '#ffff00',
    'outline':     '#ffffff',
    'drill_0':     '#00ffff',
}
DEFAULT_COLOR = '#ff8800'
ISOLATION_COLOR = '#00ff00'
PROBLEM_COLOR = '#ff0000'


def shapely_to_mpl_path(geom):
    """Convert Shapely geometry to matplotlib Path for rendering."""
    paths = []

    if isinstance(geom, Polygon):
        # Exterior
        coords = np.array(geom.exterior.coords)
        codes = [MplPath.MOVETO] + [MplPath.LINETO] * (len(coords) - 2) + [MplPath.CLOSEPOLY]
        paths.append((coords, codes))
        # Interiors (holes)
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
        paths_data = shapely_to_mpl_path(geom)
        for coords, codes in paths_data:
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


class LayerPanel(ttk.Frame):
    """Panel for a single layer with controls."""

    def __init__(self, parent, name, color, **kwargs):
        super().__init__(parent, **kwargs)
        self.layer_name = name

        self.visible = tk.BooleanVar(value=True)
        self.mode = tk.StringVar(value='outline')
        self.offset = tk.DoubleVar(value=0.1)
        self.isolate = tk.BooleanVar(value=False)

        # Row layout
        cb = ttk.Checkbutton(self, variable=self.visible, text='')
        cb.pack(side=tk.LEFT, padx=2)

        # Color indicator
        clr = tk.Canvas(self, width=12, height=12, bg=color,
                        highlightthickness=1, highlightbackground='gray')
        clr.pack(side=tk.LEFT, padx=2)

        lbl = ttk.Label(self, text=name, width=15, anchor='w')
        lbl.pack(side=tk.LEFT, padx=2)

        # Isolate checkbox
        iso_cb = ttk.Checkbutton(self, variable=self.isolate, text='Iso')
        iso_cb.pack(side=tk.LEFT, padx=2)

        # Mode dropdown
        mode_cb = ttk.Combobox(self, textvariable=self.mode,
                               values=['outline', 'inline'], width=7, state='readonly')
        mode_cb.pack(side=tk.LEFT, padx=2)

        # Offset spinbox
        ttk.Label(self, text='mm:').pack(side=tk.LEFT)
        spn = ttk.Spinbox(self, textvariable=self.offset,
                          from_=0.01, to=5.0, increment=0.05, width=5)
        spn.pack(side=tk.LEFT, padx=2)


class PCBookerApp:
    """Main application."""

    def __init__(self, root):
        self.root = root
        self.root.title('PCBooker — Gerber Viewer + Isolation')
        self.root.geometry('1200x800')

        self.layers = {}        # {name: GerberFile}
        self.geometries = {}    # {name: list of Shapely geom}
        self.merged = {}        # {name: merged Shapely geom}
        self.iso_paths = {}     # {name: list of paths}
        self.problems = {}      # {name: list of problem dicts}
        self.layer_panels = {}  # {name: LayerPanel}

        self._build_ui()

    def _build_ui(self):
        # Main paned window
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Left panel — layer list
        left = ttk.Frame(paned, width=320)
        paned.add(left, weight=0)

        ttk.Label(left, text='Layers', font=('', 12, 'bold')).pack(pady=5)

        # Scrollable layer list
        self.layer_frame = ttk.Frame(left)
        self.layer_frame.pack(fill=tk.BOTH, expand=True)

        # Buttons
        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill=tk.X, pady=5, padx=5)

        ttk.Button(btn_frame, text='Load Gerbers',
                   command=self.load_gerbers).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text='Load Files...',
                   command=self.load_files).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text='Check Contours',
                   command=self.check_contours).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text='Generate Isolation',
                   command=self.generate_isolation).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text='Export HPGL',
                   command=self.export_hpgl).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text='Refresh View',
                   command=self.refresh_view).pack(fill=tk.X, pady=2)

        # Right panel — matplotlib canvas
        right = ttk.Frame(paned)
        paned.add(right, weight=1)

        self.fig = Figure(figsize=(8, 6), facecolor='black')
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor('black')
        self.ax.set_aspect('equal')
        self.ax.grid(True, color='#333333', linewidth=0.5)
        self.ax.set_xlabel('mm')
        self.ax.set_ylabel('mm')

        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        toolbar = NavigationToolbar2Tk(self.canvas, right)
        toolbar.update()

        # Status bar
        self.status = tk.StringVar(value='Ready. Load Gerber files to begin.')
        ttk.Label(self.root, textvariable=self.status,
                  relief=tk.SUNKEN, anchor='w').pack(fill=tk.X, side=tk.BOTTOM)

    def load_gerbers(self):
        """Load all Gerbers from a directory."""
        directory = filedialog.askdirectory(title='Select Gerber directory')
        if not directory:
            return

        self.status.set(f'Loading Gerbers from {directory}...')
        self.root.update()

        try:
            self.layers = gerber_loader.load_board(directory)
        except Exception as e:
            messagebox.showerror('Error', f'Failed to load Gerbers:\n{e}')
            self.status.set(f'Error: {e}')
            return

        self._process_layers()

    def load_files(self):
        """Load individual Gerber files."""
        filepaths = filedialog.askopenfilenames(
            title='Select Gerber files',
            filetypes=[
                ('All files', '*.*'),
                ('Gerber files', '*.gbr *.ger *.gtl *.gbl *.gts *.gbs *.gto *.gbo *.gm1 *.GTL *.GBL *.GTS *.GBS *.GTO *.GBO'),
                ('Drill files', '*.drl *.DRL *.xln'),
            ]
        )
        if not filepaths:
            return

        self.status.set(f'Loading {len(filepaths)} files...')
        self.root.update()

        self.layers = gerber_loader.load_gerber_files(filepaths)
        self._process_layers()

    def _process_layers(self):
        """Convert loaded layers to geometry and update UI."""
        # Clear old panels
        for widget in self.layer_frame.winfo_children():
            widget.destroy()
        self.layer_panels.clear()
        self.geometries.clear()
        self.merged.clear()
        self.iso_paths.clear()
        self.problems.clear()

        for name, layer in self.layers.items():
            self.status.set(f'Processing {name}...')
            self.root.update()

            color = LAYER_COLORS.get(name, DEFAULT_COLOR)
            panel = LayerPanel(self.layer_frame, name, color)
            panel.pack(fill=tk.X, padx=5, pady=1)
            self.layer_panels[name] = panel

            # Convert to Shapely
            geoms = gerber_loader.layer_to_polygons(layer)
            self.geometries[name] = geoms
            self.merged[name] = gerber_loader.layer_to_merged(layer)

        self.status.set(f'Loaded {len(self.layers)} layers. '
                        f'Total objects: {sum(len(g) for g in self.geometries.values())}')
        self.refresh_view()

    def check_contours(self):
        """Check all layers for open contours."""
        total_problems = 0

        for name, geoms in self.geometries.items():
            problems = contour_check.check_closed_contours(geoms)
            self.problems[name] = problems
            total_problems += len(problems)

        if total_problems == 0:
            messagebox.showinfo('Contour Check', 'All contours are closed!')
            self.status.set('Contour check: OK — all closed.')
        else:
            msg = f'{total_problems} open contour(s) found!\n\n'
            for name, probs in self.problems.items():
                if probs:
                    msg += f'{name}: {len(probs)} open\n'
                    for p in probs:
                        msg += f'  Gap: {p["gap_size_mm"]:.3f} mm\n'

            messagebox.showwarning('Contour Check', msg)
            self.status.set(f'Contour check: {total_problems} problems found!')

        self.refresh_view()

    def generate_isolation(self):
        """Generate isolation paths for selected layers."""
        self.iso_paths.clear()
        count = 0

        for name, panel in self.layer_panels.items():
            if not panel.isolate.get():
                continue

            merged = self.merged.get(name)
            if merged is None:
                continue

            offset = panel.offset.get()
            mode = panel.mode.get()

            paths = isolation.isolation_paths(merged, offset, mode)
            if paths:
                self.iso_paths[name] = paths
                count += len(paths)

        self.status.set(f'Generated {count} isolation paths.')
        self.refresh_view()

    def export_hpgl(self):
        """Export isolation paths to HPGL file."""
        if not self.iso_paths:
            messagebox.showwarning('Export', 'No isolation paths to export.\n'
                                   'Check "Iso" for layers and click "Generate Isolation" first.')
            return

        filepath = filedialog.asksaveasfilename(
            title='Export HPGL',
            defaultextension='.hpgl',
            filetypes=[('HPGL files', '*.hpgl *.plt'), ('All files', '*.*')],
        )
        if not filepath:
            return

        # Collect all paths
        all_geoms = []
        for name, paths in self.iso_paths.items():
            for path in paths:
                if hasattr(path, 'coords'):
                    all_geoms.append(LineString(path.coords))

        hpgl_export.export_hpgl(all_geoms, filepath)
        self.status.set(f'Exported {len(all_geoms)} paths to {filepath}')
        messagebox.showinfo('Export', f'HPGL saved to:\n{filepath}')

    def refresh_view(self):
        """Redraw the matplotlib canvas."""
        self.ax.clear()
        self.ax.set_facecolor('black')
        self.ax.set_aspect('equal')
        self.ax.grid(True, color='#333333', linewidth=0.5)
        self.ax.set_xlabel('mm')
        self.ax.set_ylabel('mm')

        for name, panel in self.layer_panels.items():
            if not panel.visible.get():
                continue

            color = LAYER_COLORS.get(name, DEFAULT_COLOR)
            geoms = self.geometries.get(name, [])

            for geom in geoms:
                plot_geometry(self.ax, geom, color=color, alpha=0.6)

        # Draw isolation paths
        for name, paths in self.iso_paths.items():
            plot_linestrings(self.ax, paths, color=ISOLATION_COLOR,
                             linewidth=1.5, alpha=0.9)

        # Draw problem markers
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
    root = tk.Tk()
    app = PCBookerApp(root)

    # If directory passed as argument, auto-load
    if len(sys.argv) > 1:
        path = sys.argv[1]
        if os.path.isdir(path):
            app.layers = gerber_loader.load_board(path)
            app._process_layers()
        else:
            app.layers = gerber_loader.load_gerber_files(sys.argv[1:])
            app._process_layers()

    root.mainloop()


if __name__ == '__main__':
    main()
