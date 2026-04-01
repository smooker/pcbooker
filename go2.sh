#!/bin/bash
cd "$(dirname "$0")"
~/.local/bin/python3 -c "
import gerber_loader
layer = gerber_loader.load_single('/home/chichko/Documents/PCB/marto_naliaganev1.3.2/1marto.GTL')
print(f'Objects: {len(layer.objects)}')
for obj in layer.objects[:5]:
    print(f'  {type(obj).__name__}: {dir(obj)}')
geoms = gerber_loader.layer_to_polygons(layer)
print(f'Geometries: {len(geoms)}')
merged = gerber_loader.layer_to_merged(layer)
print(f'Merged: {type(merged).__name__ if merged else None}')
if merged:
    print(f'Area: {merged.area:.4f}')
"
