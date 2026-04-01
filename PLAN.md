# PCBooker GUI — Plan

## Context

smooker използва pcb2gcode за PCB изолация с лазерно гравиране, но инструментът "прави мизерии". Целта е нов Python GUI който:
- Зарежда multi-Gerber файлове (от KiCad, CADSTAR и др.)
- Визуализира слоевете
- За всеки layer: избор outline/inline + offset в mm
- Проверка за затворени контури (критично — "колегата обича да оставя отворен контур")
- Генерира HPGL за лазерно гравиране

## Архитектура

```
pcbooker/
├── pcbooker.py          — главен GUI (matplotlib + tkinter)
├── gerber_loader.py     — зареждане на Gerber файлове (gerbonara)
├── isolation.py         — isolation path генериране (Shapely buffer)
├── contour_check.py     — проверка за затворени контури
├── hpgl_export.py       — HPGL генератор
└── requirements.txt     — dependencies
```

## Dependencies

- **gerbonara** (v1.6.2) — Gerber/Excellon парсер, авто-детекция на layer тип
- **Shapely** — polygon buffer/offset за isolation routing
- **matplotlib** — визуализация + вграден в tkinter GUI
- **tkinter** — GUI framework (идва с Python, не изисква emerge)

## Компоненти

### 1. gerber_loader.py
- `load_board(directory)` — зарежда всички Gerber файлове от папка чрез `gerbonara.LayerStack`
- `load_single(filepath)` — зарежда един Gerber файл
- `layer_to_polygons(layer)` — конвертира gerbonara обекти към Shapely геометрия
  - Flash → Point.buffer(aperture_radius) → Polygon
  - Line → LineString.buffer(aperture_width/2) → Polygon
  - Arc → дискретизация → LineString.buffer() → Polygon
  - Region → Polygon директно
- Връща list от Shapely Polygon/MultiPolygon за всеки layer

### 2. contour_check.py
- `check_closed_contours(polygons)` — проверка за затвореност
  - Shapely `.is_valid` и `.is_ring` за всеки контур
  - Детектиране на gap-ове: ако LineString не е затворена, маркира с червено
  - Връща list от проблемни места (координати + gap размер)
- `auto_close_contours(polygons, tolerance_mm)` — опит за автоматично затваряне
  - Ако gap < tolerance → затваря
  - Ако gap > tolerance → warning с визуализация на проблема
- Визуално маркиране: затворени=зелено, отворени=червено

### 3. isolation.py
- `generate_isolation(polygon, offset_mm, mode='outline')` — генерира isolation path
  - `mode='outline'` → `polygon.buffer(offset_mm)` — отвън
  - `mode='inline'` → `polygon.buffer(-offset_mm)` — отвътре
  - Shapely `buffer()` с `resolution=32` (32 сегмента на четвърт кръг)
- `multi_pass(polygon, offset_mm, passes, overlap)` — многократно минаване
- Връща Shapely геометрия (boundary линии) за HPGL export

### 4. hpgl_export.py
- `export_hpgl(paths, filename, scale=40.0)` — записва HPGL файл
  - HPGL координати: 0.025mm/unit (scale=40 units/mm)
  - Commands: IN; SP1; PU x,y; PD x,y; PU; SP0;
  - Линии: PU → move to start; PD → draw to points
  - Дъги: аппроксимация с линейни сегменти (от Shapely buffer)
- Минимален HPGL:
  ```
  IN;
  SP1;
  PU x0,y0;
  PD x1,y1,x2,y2,...;
  PU;
  SP0;
  ```

### 5. pcbooker.py — GUI
- **Ляв панел:** списък на layers с checkboxes
  - За всеки layer: име, цвят, visible toggle
  - Dropdown: outline / inline
  - Spinbox: offset в mm (default 0.1)
  - Бутон: "Check contours" — маркира отворени контури
- **Централен панел:** matplotlib canvas
  - Рендериране на избрани layers с различни цветове
  - Isolation paths като overlay
  - Zoom/pan (matplotlib toolbar)
  - Отворени контури маркирани с червено
- **Долен панел:**
  - "Load Gerbers" бутон (folder chooser)
  - "Generate Isolation" бутон
  - "Export HPGL" бутон
  - Status bar с warnings

## Workflow на потребителя

1. Натиска "Load Gerbers" → избира папка с Gerber файлове
2. Вижда layers в списъка (auto-detected: F.Cu, B.Cu, Edge.Cuts...)
3. Включва/изключва layers за визуализация
4. За всеки layer избира outline/inline + offset mm
5. Натиска "Check Contours" → червени маркери за отворени контури
6. Натиска "Generate Isolation" → вижда toolpath-ове в preview
7. Натиска "Export HPGL" → записва файл за лазера

## Проверка за затворени контури — детайл

Ключова функционалност (защото "колегата обича да оставя отворен контур"):
- При зареждане: автоматична проверка на всеки layer
- Warning popup ако има отворени контури
- Визуално маркиране с червен X на мястото на gap-а
- В status bar: "Layer F.Cu: 3 open contours detected!"
- Опция "Auto-close gaps < X mm"

## Верификация

1. Инсталиране: `pip install gerbonara shapely matplotlib`
2. Стартиране: `python3 pcbooker.py`
3. Зареждане на тестови Gerber файлове (от KiCad проект)
4. Проверка на layer detection
5. Генериране на isolation paths — визуална проверка
6. Export HPGL → отваряне в HPGL viewer
7. Тест с нарочно отворен контур — трябва да покаже warning

## Файлове за промяна/създаване

Всички нови файлове в `/home/claude/work/sdr/pcbooker/`:
- `pcbooker.py` (нов) — ~300 реда
- `gerber_loader.py` (нов) — ~100 реда
- `isolation.py` (нов) — ~80 реда
- `contour_check.py` (нов) — ~60 реда
- `hpgl_export.py` (нов) — ~80 реда
- `requirements.txt` (нов) — 3 реда
