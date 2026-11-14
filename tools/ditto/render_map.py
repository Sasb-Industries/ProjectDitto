#!/usr/bin/env python3
"""Render a map layout to a PNG, the way the game would draw it.

Usage:
    python3 tools/ditto/render_map.py PalletTown out.png [--grid] [--collision] [--scale 2]

The first argument is a map name (data/maps/<name>) or a layout id (LAYOUT_...).
--grid draws tile coordinates every 5 tiles; --collision tints impassable tiles red.
Events are drawn as coloured squares: warps blue, objects (NPCs) yellow.
"""
import argparse
import json
import re
import struct
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[2]
NUM_PRIMARY = 512  # tiles and metatiles in a primary tileset
PALS_PRIMARY = 6


def tileset_dirs():
    # A few tilesets (General among them) are declared in graphics.c instead of graphics.h.
    text = (REPO / "src/data/tilesets/graphics.h").read_text() + (REPO / "src/graphics.c").read_text()
    tiles = dict(re.findall(r"gTilesetTiles_(\w+)\[\]\s*=\s*INC\w+\(\"([^\"]+)/tiles", text))
    return {"gTileset_" + k: REPO / v for k, v in tiles.items()}


class Tileset:
    def __init__(self, path):
        img = Image.open(path / "tiles.png")
        self.w = img.width // 8
        self.pix = img.load()
        self.count = self.w * (img.height // 8)
        self.metatiles = (path / "metatiles.bin").read_bytes()
        self.attrs = (path / "metatile_attributes.bin").read_bytes()
        self.pals = []
        for i in range(16):
            lines = (path / "palettes" / f"{i:02d}.pal").read_text().split("\n")[3:19]
            self.pals.append([tuple(int(c) for c in l.split()) for l in lines])

    def tile(self, index):
        if index >= self.count:
            return None
        ox, oy = (index % self.w) * 8, (index // self.w) * 8
        return [[self.pix[ox + x, oy + y] for x in range(8)] for y in range(8)]


def load_layout(name):
    layouts = json.loads((REPO / "data/layouts/layouts.json").read_text())["layouts"]
    events = None
    if not name.startswith("LAYOUT_"):
        events = json.loads((REPO / "data/maps" / name / "map.json").read_text())
        name = events["layout"]
    return next(l for l in layouts if l["id"] == name), events


def render(layout, events, grid=False, collision=False, scale=1):
    dirs = tileset_dirs()
    prim, sec = Tileset(dirs[layout["primary_tileset"]]), Tileset(dirs[layout["secondary_tileset"]])
    w, h = layout["width"], layout["height"]
    blocks = struct.unpack(f"<{w * h}H", (REPO / layout["blockdata_filepath"]).read_bytes()[: w * h * 2])
    img = Image.new("RGB", (w * 16, h * 16), (0, 0, 0))
    out = img.load()
    for i, block in enumerate(blocks):
        mid = block & 0x3FF
        ts, local = (prim, mid) if mid < NUM_PRIMARY else (sec, mid - NUM_PRIMARY)
        raw = ts.metatiles[local * 16: local * 16 + 16]
        if len(raw) < 16:
            continue
        bx, by = (i % w) * 16, (i // w) * 16
        for n, entry in enumerate(struct.unpack("<8H", raw)):
            tidx, hflip, vflip, pal = entry & 0x3FF, entry & 0x400, entry & 0x800, entry >> 12
            tile = prim.tile(tidx) if tidx < NUM_PRIMARY else sec.tile(tidx - NUM_PRIMARY)
            if tile is None:
                continue
            colors = (prim if pal < PALS_PRIMARY else sec).pals[pal]
            tx, ty = bx + (n % 2) * 8, by + ((n % 4) // 2) * 8
            for y in range(8):
                for x in range(8):
                    c = tile[7 - y if vflip else y][7 - x if hflip else x]
                    if c == 0 and n >= 4:
                        continue  # colour 0 is transparent on the top layer
                    out[tx + x, ty + y] = colors[c]
    draw = ImageDraw.Draw(img, "RGBA")
    if collision:
        for i, block in enumerate(blocks):
            if (block >> 10) & 3:
                x, y = (i % w) * 16, (i // w) * 16
                draw.rectangle([x, y, x + 15, y + 15], fill=(255, 0, 0, 90))
    if events:
        for key, color in (("warp_events", (40, 120, 255, 200)), ("object_events", (255, 220, 0, 220))):
            for e in events.get(key) or []:
                draw.rectangle([e["x"] * 16 + 3, e["y"] * 16 + 3, e["x"] * 16 + 12, e["y"] * 16 + 12], fill=color)
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
        draw = ImageDraw.Draw(img, "RGBA")
    if grid:
        for x in range(0, w, 5):
            draw.line([x * 16 * scale, 0, x * 16 * scale, img.height], fill=(255, 255, 255, 110))
            draw.text((x * 16 * scale + 2, 1), str(x), fill=(255, 255, 255, 255))
        for y in range(0, h, 5):
            draw.line([0, y * 16 * scale, img.width, y * 16 * scale], fill=(255, 255, 255, 110))
            draw.text((1, y * 16 * scale + 2), str(y), fill=(255, 255, 255, 255))
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    ap.add_argument("out")
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--collision", action="store_true")
    ap.add_argument("--scale", type=int, default=1)
    a = ap.parse_args()
    layout, events = load_layout(a.name)
    render(layout, events, a.grid, a.collision, a.scale).save(a.out)
    print(f"{a.out}: {layout['width']}x{layout['height']} tiles")


if __name__ == "__main__":
    main()
