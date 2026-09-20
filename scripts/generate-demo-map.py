#!/usr/bin/env python3
"""Render HYHQ's original fictional map; Pillow is already pinned by backend/requirements.txt.

No downloaded tiles, geographic coordinates, fonts or network calls are used.
Run `.venv/bin/python scripts/generate-demo-map.py --check` to verify the committed PNG.
"""
import argparse
import ast
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "miniprogram/assets/maps/demo-campus-v1.png"
WIDTH, HEIGHT, SCALE = 1000, 700, 3
EXPECTED = {
    "campus-gate": (.12, .83), "clear-river": (.26, .48), "mirror-lake": (.64, .36),
    "wetland-garden": (.79, .22), "ginkgo-grove": (.35, .25), "camphor-tree": (.19, .28),
    "bamboo-garden": (.8, .58), "waste-east": (.86, .77), "waste-west": (.18, .65),
    "green-trail": (.57, .57), "library": (.45, .78), "weather-garden": (.58, .16),
}


def check_coordinates():
    tree = ast.parse((ROOT / "backend/ecology/management/commands/seed_demo.py").read_text())
    places = next(ast.literal_eval(node.value) for node in tree.body
                  if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "PLACES" for target in node.targets))
    actual = {row[0]: (row[3], row[4]) for row in places}
    if actual != EXPECTED:
        raise SystemExit("seed_demo PLACES changed: create a new matching map version instead of silently shifting v1.")


def render():
    canvas = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), "#e8eddb")
    draw = ImageDraw.Draw(canvas)

    def box(values):
        return tuple(round(v * SCALE) for v in values)

    def ellipse(bounds, fill, outline=None, width=1):
        draw.ellipse(box(bounds), fill=fill, outline=outline, width=round(width * SCALE))

    def rect(bounds, fill, radius=0, outline=None, width=1):
        draw.rounded_rectangle(box(bounds), radius=radius * SCALE, fill=fill, outline=outline, width=round(width * SCALE))

    def line(points, fill, width):
        draw.line([box(point) for point in points], fill=fill, width=round(width * SCALE), joint="curve")

    def polygon(points, fill):
        draw.polygon([box(point) for point in points], fill=fill)

    def path(points, width=20):
        line(points, "#d3d4b9", width + 4)
        line(points, "#f9f5df", width)

    def tree(x, y, radius=18, color="#a3be89"):
        ellipse((x - radius, y - radius + 5, x + radius, y + radius + 5), "#becfa3")
        ellipse((x - radius, y - radius, x + radius, y + radius), color)
        ellipse((x - radius * .58, y - radius * .62, x + radius * .4, y + radius * .38), "#bed2a3")

    # Broad garden beds, with deliberate empty space around dynamically rendered marker labels.
    ellipse((-90, -90, 420, 340), "#dae4c4")
    ellipse((35, 80, 405, 320), "#d1dfb8")
    ellipse((718, 290, 1020, 508), "#d1dfb8")
    ellipse((375, 20, 755, 204), "#dce4c5")
    ellipse((663, 30, 956, 269), "#c5d8b3")
    ellipse((434, 138, 834, 446), "#d3dfbf")
    rect((400, 470, 665, 642), "#dce2c9", 26)

    # Water: the river passes through (260, 336); the lake covers (640, 252).
    river = [(94, -60), (99, 41), (120, 137), (172, 215), (233, 291), (260, 336), (288, 410), (315, 482), (374, 560), (407, 641), (412, 760)]
    line(river, "#b4cdaa", 84)
    line(river, "#95c5bf", 66)
    line(river, "#b9d9ce", 42)
    lake = [(575, 178), (633, 158), (700, 181), (739, 229), (735, 280), (700, 326), (632, 343), (569, 322), (528, 278), (534, 222)]
    polygon(lake, "#8fbfb7")
    polygon([(x + (640 - x) * .09, y + (252 - y) * .09) for x, y in lake], "#b4d6cc")
    for x, y in [(560, 253), (605, 205), (667, 285), (626, 311), (692, 238)]:
        line([(x, y), (x + 22, y)], "#d9e9da", 3)

    # Closed ring path around the lake, connected to all west/south/east learning areas.
    path([(120, 720), (120, 581), (160, 518), (180, 455), (177, 380), (191, 306), (190, 196), (224, 132), (350, 112), (450, 112), (580, 112), (715, 110), (790, 154), (822, 231), (830, 325), (800, 406), (778, 468), (860, 539), (879, 620), (1000, 620)], 18)
    path([(120, 581), (226, 581), (335, 571), (450, 546), (570, 526), (689, 506), (778, 468)], 22)
    path([(191, 306), (256, 346), (359, 365), (466, 399), (570, 399), (685, 382), (767, 338), (789, 253), (761, 177), (683, 127), (580, 112)], 16)
    path([(350, 112), (350, 175), (377, 256), (359, 365)], 12)
    path([(450, 546), (474, 486), (466, 399)], 12)
    path([(790, 154), (825, 110), (873, 103)], 10)

    # Bridge over the fictional river, distinct from both walking path and water.
    line([(230, 333), (292, 355)], "#9b8663", 24)
    line([(230, 333), (292, 355)], "#d8c59c", 17)
    for step in range(8):
        x, y = 232 + step * 8, 334 + step * 2.8
        line([(x - 2, y + 8), (x + 3, y - 8)], "#ac976e", 2)

    # Library, entrance, waste stations and weather plot are simple original symbols.
    rect((395, 509, 508, 563), "#b3b594", 8)
    rect((398, 499, 505, 554), "#f4e8c6", 7, "#b5b799", 2)
    rect((443, 534, 460, 555), "#82998a", 2)
    for x in [410, 431, 475]:
        rect((x, 511, x + 11, 523), "#b3cab6", 2)
    line([(409, 489), (452, 470), (497, 489)], "#859782", 6)
    for x in [91, 143]:
        rect((x, 559, x + 14, 599), "#b5b894", 3)
    rect((87, 552, 161, 566), "#799574", 4)
    for center_x, center_y in [(180, 455), (860, 539)]:
        rect((center_x - 32, center_y - 20, center_x + 32, center_y + 25), "#d3d9bb", 7)
        for offset, color in [(-20, "#608d7b"), (-2, "#d1b46d"), (16, "#899d78")]:
            rect((center_x + offset - 6, center_y - 10, center_x + offset + 6, center_y + 13), color, 2)
    rect((546, 80, 615, 142), "#cad6ad", 10, "#aebe95", 2)
    line([(580, 96), (580, 131)], "#7b9279", 3)
    line([(566, 97), (595, 97)], "#7b9279", 3)
    ellipse((576, 82, 584, 90), "#f5edc8")

    # Trees, reeds and bamboo emphasize the locations represented by seed_demo.
    for x, y, r in [(45, 82, 23), (46, 173, 25), (61, 246, 20), (162, 164, 24), (190, 196, 24), (218, 216, 23), (318, 155, 19), (350, 175, 22), (384, 160, 23), (373, 210, 19), (60, 466, 20), (65, 502, 22), (67, 641, 23), (209, 648, 24), (529, 614, 20), (569, 607, 24), (619, 609, 21), (919, 567, 26), (948, 613, 20), (939, 315, 24), (891, 335, 19)]:
        tree(x, y, r)
    for x, y in [(811, 89), (859, 149), (875, 191), (745, 97), (728, 215), (776, 212)]:
        for dx in [-7, 0, 7]:
            line([(x + dx, y + 12), (x + dx - 3, y - 12)], "#7e9e73", 2)
            ellipse((x + dx - 5, y - 18, x + dx, y - 5), "#a7b280")
    for x, y in [(763, 392), (800, 406), (839, 390), (859, 424), (800, 453)]:
        for dx in [-8, 0, 8]:
            line([(x + dx, y + 22), (x + dx, y - 18)], "#6d9870", 3)
            line([(x + dx, y - 5), (x + dx - 9, y - 12)], "#8bae78", 3)
            line([(x + dx, y + 6), (x + dx + 9, y)], "#8bae78", 3)
    # Small benches along the paths. No north arrow or distance scale: this is not a GIS map.
    for x, y in [(438, 144), (502, 433), (713, 429), (224, 506)]:
        line([(x - 12, y), (x + 12, y)], "#a79574", 5)
        line([(x - 9, y), (x - 9, y + 6)], "#829075", 2)
        line([(x + 9, y), (x + 9, y + 6)], "#829075", 2)
    output = BytesIO()
    canvas.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS).save(output, format="PNG", optimize=False)
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare generated bytes without overwriting the asset")
    args = parser.parse_args()
    check_coordinates()
    content = render()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_bytes() != content:
            raise SystemExit("Map asset differs; regenerate using the pinned backend Pillow dependency.")
        print("Original demo-campus v1 PNG matches renderer and all 12 seed coordinates (1000 x 700).")
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_bytes(content)
        print(f"Generated {OUTPUT.relative_to(ROOT)} ({len(content)} bytes).")


if __name__ == "__main__":
    main()
