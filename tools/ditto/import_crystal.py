#!/usr/bin/env python3
"""Import Johto maps and tilesets from a pret/pokecrystal checkout.

Usage:
    python3 tools/ditto/import_crystal.py /path/to/pokecrystal

What it brings over: layouts, tilesets, map headers, warps and map-to-map
connections, for every Johto map plus Routes 26-28, Tohjo Falls, Mt. Silver
and the Fast Ship. Kanto maps are skipped (FireRed's Kanto is already
imported). Like the Kanto importer it leaves NPCs, signs, triggers and scripts
behind; every imported map gets an empty scripts.inc.

How Game Boy Color data becomes GBA data:

* A Crystal "block" is 4x4 tiles (32x32 px); an Emerald metatile is 2x2 tiles
  (16x16 px), the size of one step. Each block becomes four metatiles, so a
  map W x H blocks becomes 2W x 2H metatiles. Event coordinates are already in
  steps and carry over unchanged; connection offsets are doubled.
* Crystal collision is stored per block quadrant, which is exactly one
  metatile, so every metatile gets its own behaviour and collision.
* Tiles are 2bpp (4 colours). Colour c becomes GBA colour index c+1, because
  index 0 is transparent on the GBA. Tile 0 of every primary is left blank.
* Crystal picks palettes per map (indoor/outdoor/cave, special tilesets) and
  swaps roof tiles and roof colours per town. On the GBA those belong to the
  tileset, so each Crystal tileset becomes one primary tileset (tiles and
  metatiles) plus one secondary per palette/roof combination ("variant").
  Secondaries hold the 7 map palettes in slots 6-12, the 9 roof tiles at tile
  512, and any metatiles beyond the primary's 512.
* Only the daytime palettes are used. Day/night is a later engine feature.
* Not ported: tile animations (water, flowers), cut trees and whirlpools as
  field-move obstacles (they are walls for now), headbutt trees.

Safe to re-run: generated sections are replaced, not duplicated, and hand-added
object_events, coord_events, bg_events and scripts.inc are kept.
"""
import json
import re
import struct
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
PREFIX = "Johto"
BEGIN = "// BEGIN ditto:import_crystal (generated, do not edit by hand)"
END = "// END ditto:import_crystal"
MANIFEST = REPO / "tools/ditto/import_crystal.manifest.json"

NUM_PRIMARY = 512  # tiles and metatiles in an Emerald primary tileset
ROOF_FIRST, ROOF_LEN = 0x0A, 9  # Crystal swaps these tiles per town
ROOF_TILESETS = {"TILESET_JOHTO", "TILESET_JOHTO_MODERN", "TILESET_BATTLE_TOWER_OUTSIDE"}
# Crystal palette 0-6 (gray, red, green, water, yellow, brown, roof) -> GBA slot 6-12,
# palette 7 (text) -> slot 5 in the primary.
GBA_SLOT = [6, 7, 8, 9, 10, 11, 12, 5]

SKIP_GROUPS = {"CableClub"}
# Kanto-range landmarks we still want: the Johto-Kanto border and Mt. Silver.
EXTRA_LANDMARKS = {"LANDMARK_ROUTE_26", "LANDMARK_ROUTE_27", "LANDMARK_TOHJO_FALLS",
                   "LANDMARK_ROUTE_28", "LANDMARK_FAST_SHIP"}

# Daytime palette indexes into bg_tiles.pal, per environment (data/maps/environment_colors.asm).
ENV_PALETTES = {
    "TOWN": [0x08, 0x09, 0x0A, 0x28, 0x0C, 0x0D, 0x0E, 0x0F],
    "ROUTE": [0x08, 0x09, 0x0A, 0x28, 0x0C, 0x0D, 0x0E, 0x0F],
    "INDOOR": [0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x07],
    "GATE": [0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x07],
    "CAVE": list(range(0x08, 0x10)),
    "DUNGEON": list(range(0x08, 0x10)),
    "ENVIRONMENT_5": list(range(0x08, 0x10)),
}
# Tilesets that replace all 8 palettes (engine/tilesets/tileset_palettes.asm).
SPECIAL_PALETTES = {
    "TILESET_HOUSE": "house.pal",
    "TILESET_RADIO_TOWER": "radio_tower.pal",
    "TILESET_POKECOM_CENTER": "pokecom_center.pal",
    "TILESET_BATTLE_TOWER_INSIDE": "battle_tower_inside.pal",
    "TILESET_ICE_PATH": "ice_path.pal",  # except in INDOOR maps
}

# Met locations are one byte and only ~39 map-section values are free, so dungeons and
# landmarks share their town's or route's section. Their own name still shows on entry
# (see src/data/johto_map_names.h).
LANDMARK_PARENT = {
    "SPROUT_TOWER": "VIOLET_CITY", "RUINS_OF_ALPH": "ROUTE_32", "UNION_CAVE": "ROUTE_33",
    "SLOWPOKE_WELL": "AZALEA_TOWN", "ILEX_FOREST": "ROUTE_34", "RADIO_TOWER": "GOLDENROD_CITY",
    "NATIONAL_PARK": "ROUTE_35", "BURNED_TOWER": "ECRUTEAK_CITY", "TIN_TOWER": "ECRUTEAK_CITY",
    "LIGHTHOUSE": "OLIVINE_CITY", "BATTLE_TOWER": "ROUTE_40", "WHIRL_ISLANDS": "ROUTE_41",
    "MT_MORTAR": "ROUTE_42", "LAKE_OF_RAGE": "ROUTE_43", "ICE_PATH": "ROUTE_44",
    "DRAGONS_DEN": "BLACKTHORN_CITY", "DARK_CAVE": "ROUTE_31", "SILVER_CAVE": "ROUTE_28",
    "TOHJO_FALLS": "ROUTE_27", "FAST_SHIP": "OLIVINE_CITY",
}
POPUP_THEME = {"TOWN": "MAPPOPUP_THEME_WOOD", "ROUTE": "MAPPOPUP_THEME_WOOD", "CAVE": "MAPPOPUP_THEME_STONE",
               "DUNGEON": "MAPPOPUP_THEME_STONE", "INDOOR": "MAPPOPUP_THEME_MARBLE",
               "GATE": "MAPPOPUP_THEME_MARBLE", "ENVIRONMENT_5": "MAPPOPUP_THEME_MARBLE"}

MAP_TYPES = {"TOWN": "MAP_TYPE_TOWN", "ROUTE": "MAP_TYPE_ROUTE", "INDOOR": "MAP_TYPE_INDOOR",
             "GATE": "MAP_TYPE_INDOOR", "CAVE": "MAP_TYPE_UNDERGROUND",
             "DUNGEON": "MAP_TYPE_UNDERGROUND", "ENVIRONMENT_5": "MAP_TYPE_INDOOR"}

# Placeholder music until the Gold/Silver soundtrack is ported.
MUSIC = [("POKEMON_CENTER", "MUS_POKE_CENTER"), ("GYM", "MUS_GYM"), ("ROUTE", "MUS_RG_ROUTE3")]
ENV_MUSIC = {"TOWN": "MUS_RG_PEWTER", "ROUTE": "MUS_RG_ROUTE3", "CAVE": "MUS_RG_MT_MOON",
             "DUNGEON": "MUS_RG_POKE_TOWER"}


def behavior_for(name):
    """Emerald behaviour for a Crystal collision constant name (without COLL_)."""
    if name is None:
        return "MB_NORMAL"
    if "TALL_GRASS" in name or name.startswith("GRASS_"):
        return "MB_TALL_GRASS"
    if "LONG_GRASS" in name:
        return "MB_LONG_GRASS"
    if name.startswith("WATERFALL"):
        return "MB_WATERFALL"
    if name.startswith(("WATER", "CURRENT", "WHIRLPOOL")) or "BUOY" in name:
        return "MB_POND_WATER"
    if name.startswith("ICE"):
        return "MB_ICE"
    hops = {"HOP_DOWN": "MB_JUMP_SOUTH", "HOP_UP": "MB_JUMP_NORTH", "HOP_LEFT": "MB_JUMP_WEST",
            "HOP_RIGHT": "MB_JUMP_EAST", "HOP_DOWN_LEFT": "MB_JUMP_SOUTHWEST",
            "HOP_DOWN_RIGHT": "MB_JUMP_SOUTHEAST", "HOP_UP_LEFT": "MB_JUMP_NORTHWEST",
            "HOP_UP_RIGHT": "MB_JUMP_NORTHEAST"}
    if name in hops:
        return hops[name]
    carpets = {"WARP_CARPET_DOWN": "MB_SOUTH_ARROW_WARP", "WARP_CARPET_UP": "MB_NORTH_ARROW_WARP",
               "WARP_CARPET_LEFT": "MB_WEST_ARROW_WARP", "WARP_CARPET_RIGHT": "MB_EAST_ARROW_WARP"}
    if name in carpets:
        return carpets[name]
    if name.startswith("LADDER"):
        return "MB_LADDER"
    if name.startswith(("DOOR", "STAIRCASE", "CAVE", "WARP", "PIT")):
        return "MB_NON_ANIMATED_DOOR"
    return {"COUNTER": "MB_COUNTER", "COUNTER_98": "MB_COUNTER", "BOOKSHELF": "MB_BOOKSHELF",
            "MART_SHELF": "MB_SHOP_SHELF"}.get(name, "MB_NORMAL")


def camel(const):
    return "".join(w.capitalize() for w in const.split("_"))


def snake(name):
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


def replace_block(path, body, comment="//"):
    begin, end = BEGIN.replace("//", comment, 1), END.replace("//", comment, 1)
    text = path.read_text()
    block = f"{begin}\n{body.rstrip()}\n{end}\n"
    if begin in text:
        text = re.sub(re.escape(begin) + r".*?" + re.escape(end) + r"\n", lambda _: block, text, flags=re.S)
    else:
        text = text.rstrip("\n") + "\n\n" + block
    path.write_text(text)


def asm_lines(path):
    for line in path.read_text().splitlines():
        line = line.split(";", 1)[0].strip()
        if line:
            yield line


def args(line):
    return [a.strip() for a in line.split(None, 1)[1].split(",")] if " " in line or "\t" in line else []


# ------------------------------------------------------------- crystal data

class Crystal:
    def __init__(self, root):
        self.root = root
        self.read_collision()
        self.read_palettes()
        self.read_tilesets()
        self.read_maps()
        self.anim = AnimSimulator(self)

    def read_collision(self):
        self.coll_name, self.coll_value = {}, {}
        for name, val in re.findall(r"DEF COLL_(\w+)\s+EQU \$([0-9a-fA-F]+)",
                                    (self.root / "constants/collision_constants.asm").read_text()):
            self.coll_name[int(val, 16)] = name
            self.coll_value[name] = int(val, 16)
        perm = []
        for line in asm_lines(self.root / "data/collision/collision_permissions.asm"):
            if line.startswith("db "):
                perm.append(line[3:])
        self.permission = perm  # index -> "LAND_TILE" / "WATER_TILE" / "WALL_TILE | TALK" ...

    def coll_kind(self, value):
        p = self.permission[value] if value < len(self.permission) else "WALL_TILE"
        return "wall" if "WALL" in p else "water" if "WATER" in p else "land"

    def read_palettes(self):
        def rgbs(path):
            nums = [int(n) for n in re.findall(r"\d+", " ".join(
                l[3:] for l in asm_lines(path) if l.startswith("RGB")))]
            return [tuple(nums[i:i + 3]) for i in range(0, len(nums), 3)]
        colours = rgbs(self.root / "gfx/tilesets/bg_tiles.pal")
        self.bg_pals = [colours[i:i + 4] for i in range(0, len(colours), 4)]
        self.special = {k: [rgbs(self.root / "gfx/tilesets" / f)[i:i + 4] for i in range(0, 32, 4)]
                        for k, f in SPECIAL_PALETTES.items()}
        roof = rgbs(self.root / "gfx/tilesets/roofs.pal")
        self.roof_pals = [roof[i * 4:i * 4 + 2] for i in range(len(roof) // 4)]  # morn/day colours 1-2
        self.roof_gfx, groups = [], []
        for line in asm_lines(self.root / "data/maps/roofs.asm"):
            if line.startswith("INCBIN"):
                self.roof_gfx.append(self.root / line.split('"')[1].replace(".2bpp", ".png"))
            elif line.startswith("db "):
                groups.append(line[3:])
        roof_ids = {}
        for line in asm_lines(self.root / "data/maps/roofs.asm"):
            m = re.match(r"const (ROOF_\w+)", line)
            if m:
                roof_ids[m.group(1)] = len(roof_ids)
        self.group_roof = [None if g == "-1" else roof_ids[g] for g in groups]  # by 0-based group

    def read_tilesets(self):
        consts = [m for m in re.findall(r"const (TILESET_\w+)",
                                        (self.root / "constants/tileset_constants.asm").read_text())]
        names = [re.match(r"tileset Tileset(\w+)", l).group(1)
                 for l in asm_lines(self.root / "data/tilesets.asm") if l.startswith("tileset ")]
        # tileset 0 is a duplicate of Johto; const_def starts at 1 for TILESET_JOHTO
        self.tileset_name = dict(zip(consts, names[1:]))
        gfx = (self.root / "gfx/tilesets.asm").read_text()
        pal = (self.root / "gfx/tileset_palette_maps.asm").read_text()
        self.tilesets = {}
        for const, name in self.tileset_name.items():
            def find(text, suffix):
                m = re.search(rf"Tileset{name}{suffix}::?\s*(?:\w+::?\s*)*(INC\w+)\s+\"([^\"]+)\"", text)
                return self.root / m.group(2)
            tiles = find(gfx, "GFX")
            self.tilesets[const] = {
                "name": name,
                "tiles": tiles.with_name(tiles.name.replace(".2bpp.lz", ".png").replace(".2bpp", ".png")),
                "meta": find(gfx, "Meta"),
                "coll": find(gfx, "Coll"),
                "palmap": find(pal, "PalMap"),
            }

    def read_maps(self):
        # map constants (sizes) in group order
        groups, sizes, gname = [], {}, None
        for line in asm_lines(self.root / "constants/map_constants.asm"):
            if line.startswith("newgroup"):
                gname = args(line)[0]
                groups.append((gname, []))
            elif line.startswith("map_const"):
                c, w, h = args(line)
                groups[-1][1].append(c)
                sizes[c] = (int(w), int(h))
        # map headers, same order
        headers, current = {}, None
        for line in asm_lines(self.root / "data/maps/maps.asm"):
            m = re.match(r"MapGroup_(\w+):", line)
            if m:
                current = m.group(1)
                headers[current] = []
            elif line.startswith("map ") and current:
                a = args(line)
                headers[current].append(dict(name=a[0], tileset=a[1], env=a[2], landmark=a[3],
                                             music=a[4], palette=a[6]))
        self.maps = {}
        for gi, ((gconst, consts), (gname, hdrs)) in enumerate(zip(groups, headers.items())):
            for c, h in zip(consts, hdrs):
                h.update(const=c, group=gname, group_index=gi + 1, size=sizes[c])
                self.maps[c] = h
        self.by_name = {h["name"]: h for h in self.maps.values()}
        # landmarks
        lm = [m for m in re.findall(r"const (LANDMARK_\w+)",
                                    (self.root / "constants/landmark_constants.asm").read_text())]
        text = (self.root / "constants/landmark_constants.asm").read_text()
        kanto_first = len(re.findall(r"const LANDMARK_\w+", text.split("DEF KANTO_LANDMARK")[0]))
        self.johto_landmarks = set(lm[:kanto_first])
        names = dict(re.findall(r'^(\w+)Name:\s*db "([^"]*)"',
                                (self.root / "data/maps/landmarks.asm").read_text(), re.M))
        order = [re.match(r"landmark\s+-?\d+,\s*-?\d+,\s*(\w+)Name", l).group(1)
                 for l in asm_lines(self.root / "data/maps/landmarks.asm") if l.startswith("landmark ")]
        self.landmark_name = {}
        for const, label in zip(lm, order):
            text = names.get(label, "").replace("<BSP>", " ").replace("¯", " ").rstrip("@")
            self.landmark_name[const] = re.sub(r"\s+", " ", text).strip()
        # block files
        label_file, pending = {}, []
        for line in asm_lines(self.root / "data/maps/blocks.asm"):
            m = re.match(r"(\w+)_Blocks::?", line)
            if m:
                pending.append(m.group(1))
            elif line.startswith("INCBIN"):
                for p in pending:
                    label_file[p] = self.root / line.split('"')[1]
                pending = []
        self.blocks = label_file
        # connections
        self.connections, current = {}, None
        for line in asm_lines(self.root / "data/maps/attributes.asm"):
            if line.startswith("map_attributes"):
                a = args(line)
                current = a[1]
                self.connections[current] = {"border": int(a[2].replace("$", ""), 16), "list": []}
            elif line.startswith("connection") and current:
                a = args(line)
                off = int(eval(a[3])) if len(a) == 4 else int(eval(a[3])) - int(eval(a[4]))
                self.connections[current]["list"].append((a[0], a[2], off))

    def warps(self, name):
        out = []
        for line in asm_lines(self.root / "maps" / f"{name}.asm"):
            if line.startswith("warp_event"):
                x, y, dest, wid = args(line)
                out.append((int(x), int(y), dest, int(wid)))
        return out

    def palette_map(self, const):
        """tile id (0-255) -> Crystal palette 0-7."""
        names = ["GRAY", "RED", "GREEN", "WATER", "YELLOW", "BROWN", "ROOF", "TEXT"]
        banks = {"0": [], "1": []}
        for line in asm_lines(self.tilesets[const]["palmap"]):
            if line.startswith("tilepal"):
                a = args(line)
                banks[a[0]] += a[1:]  # listed in tile order (even tile = low nibble)
        out = [7] * 256  # 0x60-0x7F is the font area: text palette
        for t, n in enumerate(banks["0"][:0x60]):
            out[t] = names.index(n) if n in names else 7
        for t, n in enumerate(banks["1"][:0x60]):
            out[0x80 + t] = names.index(n) if n in names else 7
        return out

    def collision(self, const):
        out = []
        for line in asm_lines(self.tilesets[const]["coll"]):
            if line.startswith("tilecoll"):
                vals = []
                for a in args(line):
                    vals.append(self.coll_value[a] if a in self.coll_value else int(a, 16))
                out.append(vals)
        return out


def tile_pixels(img, index):
    """2bpp tile `index` of a Crystal greyscale PNG as 64 colour numbers 0-3 (0 = white)."""
    cols = img.width // 8
    x0, y0 = (index % cols) * 8, (index // cols) * 8
    px = img.load()
    out = []
    for y in range(8):
        for x in range(8):
            if y0 + y >= img.height:
                out.append(0)
                continue
            v = px[x0 + x, y0 + y]
            if isinstance(v, tuple):
                v = v[0]
            out.append(3 - round(v / 85))
    return out


def write_tiles_png(tiles, path):
    """tiles: list of 64-pixel lists of GBA colour indexes."""
    rows = max(1, (len(tiles) + 15) // 16)
    img = Image.new("P", (128, rows * 8), 0)
    img.putpalette([v for i in range(16) for v in (i * 16, i * 16, i * 16)])
    px = img.load()
    for n, t in enumerate(tiles):
        x0, y0 = (n % 16) * 8, (n // 16) * 8
        for i, c in enumerate(t):
            px[x0 + i % 8, y0 + i // 8] = c
    img.save(path, bits=4)


def write_pal(path, colours):
    lines = ["JASC-PAL", "0100", "16"]
    for r, g, b in colours:
        lines.append(f"{r * 255 // 31} {g * 255 // 31} {b * 255 // 31}")
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode())  # .gitattributes stores .pal as CRLF


def gba_palette(gbc):
    """4 GBC colours -> 16-colour GBA palette with the GBC colours at 1-4."""
    return [(0, 0, 0)] + list(gbc) + [(0, 0, 0)] * 11


# ---------------------------------------------------------------- animations

def encode_2bpp(px):
    out = bytearray()
    for y in range(8):
        lo = hi = 0
        for x in range(8):
            c = px[y * 8 + x]
            lo |= (c & 1) << (7 - x)
            hi |= ((c >> 1) & 1) << (7 - x)
        out += bytes((lo, hi))
    return out


def decode_2bpp(data):
    return [((data[2 * y] >> (7 - x)) & 1) | (((data[2 * y + 1] >> (7 - x)) & 1) << 1)
            for y in range(8) for x in range(8)]


class AnimSimulator:
    """Runs Crystal's tile-animation script (data/tileset_anims.asm) frame by frame,
    so the game can replay the exact tile contents without reimplementing each routine."""

    def __init__(self, cr):
        self.cr = cr
        engine = (cr.root / "engine/tilesets/tileset_anims.asm").read_text()
        incbin = dict(re.findall(r'^(\w+):\s*INCBIN "([^"]+)"', engine, re.M))
        def png_tiles(path):
            img = Image.open(cr.root / path.replace(".2bpp", ".png")).convert("L")
            return [encode_2bpp(tile_pixels(img, i)) for i in range((img.width // 8) * (img.height // 8))]
        self.pointers = {}
        for name, tile, src in re.findall(r"^(\w+):\s*dw vTiles2 tile \$(\w+),\s*(\w+)", engine, re.M):
            self.pointers[name] = (int(tile, 16), png_tiles(incbin[src]))
        g = lambda f: png_tiles(f"gfx/tilesets/{f}.2bpp")
        self.water = [t for t in g("water/water")]
        self.flower = [g("flower/cgb_1")[0], g("flower/cgb_2")[0]]
        self.fountain = [g(f"fountain/{i}")[0] for i in range(1, 6)]
        self.lava = [g(f"lava/{i}")[0] for i in range(1, 5)]
        self.tree = [g(f"forest-tree/{i}")[0] for i in range(1, 5)]
        self.scripts, pending, last_was_frame = {}, [], False
        for line in asm_lines(cr.root / "data/tileset_anims.asm"):
            m = re.match(r"(\w+):", line)
            if m:
                if last_was_frame:
                    pending = []  # a label after a script starts a new script
                pending.append(m.group(1))
                self.scripts[m.group(1)] = []
                last_was_frame = False
            elif line.startswith("tileframe"):
                a = args(line)
                for p in pending:
                    self.scripts[p].append((a[0], a[1] if len(a) > 1 else None))
                last_was_frame = True
            else:
                pending, last_was_frame = [], False

    @staticmethod
    def tile_arg(arg):
        m = re.match(r"vTiles2 tile \$(\w+)", arg or "")
        return int(m.group(1), 16) if m else None

    def run(self, script_name, initial):
        """initial: {crystal tile id: 16-byte 2bpp}. Returns (period, {tile: [state per frame]})."""
        script = self.scripts.get(script_name) or []
        if not any(f not in ("WaitTileAnimation", "DoneTileAnimation", "StandingTileFrame8",
                             "StandingTileFrame", "AnimateWaterPalette", "FlickeringCaveEntrancePalette")
                   for f, _ in script):
            return 0, {}
        touched = {0x03, 0x0C, 0x0F, 0x38, 0x5B}
        touched |= {self.tile_arg(a) for _, a in script if self.tile_arg(a) is not None}
        touched |= {self.pointers[a][0] for _, a in script if a in self.pointers}
        vram = {t: bytearray(d) for t, d in initial.items() if t in touched}
        buf = bytearray(16)
        timer = frame = 0

        def write(tile, data):
            vram[tile] = bytearray(data)

        def step():
            nonlocal timer, frame, buf
            fn, arg = script[frame]
            frame += 1
            t = self.tile_arg(arg)
            if fn == "DoneTileAnimation":
                frame = 0
            elif fn == "StandingTileFrame8":
                timer = (timer + 1) & 7
            elif fn == "StandingTileFrame":
                timer = (timer + 1) & 7  # every reader uses only the low 3 bits
            elif fn == "AnimateWaterTile":
                write(t, self.water[(timer >> 1) & 3])
            elif fn == "AnimateFlowerTile":
                write(0x03, self.flower[(timer >> 1) & 1])
            elif fn == "AnimateFountainTile":
                write(t, self.fountain[[0, 1, 2, 3, 2, 3, 4, 0][timer & 7]])
            elif fn in ("ForestTreeLeftAnimation", "ForestTreeLeftAnimation2"):
                write(0x0C, self.tree[0])  # only animates during the Celebi event
            elif fn in ("ForestTreeRightAnimation", "ForestTreeRightAnimation2"):
                write(0x0F, self.tree[2])
            elif fn == "AnimateLavaBubbleTile1":
                write(0x5B, self.lava[(((timer & 6) >> 1) + 2) & 3])
            elif fn == "AnimateLavaBubbleTile2":
                write(0x38, self.lava[(timer >> 1) & 3])
            elif fn == "AnimateTowerPillarTile":
                dest, frames = self.pointers[arg]
                write(dest, frames[[0, 1, 2, 3, 4, 3, 2, 1][timer & 7]])
            elif fn == "AnimateWhirlpoolTile":
                dest, frames = self.pointers[arg]
                write(dest, frames[timer & 3])
            elif fn == "ReadTileToAnimBuffer":
                buf = bytearray(vram.get(t, bytes(16)))
            elif fn == "WriteTileFromAnimBuffer":
                write(t, buf)
            elif fn in ("ScrollTileRightLeft", "ScrollTileUpDown"):
                timer = (timer + 1) & 7
                if fn == "ScrollTileRightLeft":
                    buf = scroll(buf, "left" if timer & 4 else "right")
                else:
                    buf = scroll(buf, "down" if timer & 4 else "up")
            elif fn in ("ScrollTileLeft", "ScrollTileRight", "ScrollTileUp", "ScrollTileDown"):
                buf = scroll(buf, fn[len("ScrollTile"):].lower())
            # palette animations and waits change no tiles

        def scroll(b, way):
            b = bytearray(b)
            if way == "left":
                return bytearray(((x << 1) | (x >> 7)) & 0xFF for x in b)
            if way == "right":
                return bytearray(((x >> 1) | (x << 7)) & 0xFF for x in b)
            rows = [b[i:i + 2] for i in range(0, 16, 2)]
            rows = rows[-1:] + rows[:-1] if way == "down" else rows[1:] + rows[:1]
            return bytearray(x for r in rows for x in r)

        def state():
            return (timer, frame, bytes(buf), tuple(sorted((k, bytes(v)) for k, v in vram.items())))

        seen, history = {}, []
        while True:
            st = state()
            if st in seen:
                start = seen[st]
                break
            seen[st] = len(history)
            history.append({k: bytes(v) for k, v in vram.items()})
            step()
            if len(history) > 20000:
                raise SystemExit(f"{script_name}: animation does not repeat")
        cycle = history[start:]
        tiles = {k for frame_state in cycle for k in frame_state
                 if len({fs.get(k) for fs in cycle}) > 1}
        return len(cycle), {k: [fs[k] for fs in cycle] for k in sorted(tiles)}


# ------------------------------------------------------------------ tilesets

class TilesetBuilder:
    """One Crystal tileset -> one primary plus secondaries per variant."""

    def __init__(self, cr, const, em_behaviors):
        self.cr, self.const = cr, const
        ts = cr.tilesets[const]
        self.name = {"Johto": "Outdoor", "JohtoModern": "OutdoorModern"}.get(ts["name"], ts["name"])
        self.sym = PREFIX + self.name
        img = Image.open(ts["tiles"]).convert("L")
        n_src = (img.width // 8) * (img.height // 8)
        self.src_tiles = [tile_pixels(img, i) for i in range(n_src)]
        self.roofed = const in ROOF_TILESETS
        palmap = cr.palette_map(const)
        coll = cr.collision(const)
        meta = ts["meta"].read_bytes()
        n_blocks = len(meta) // 16

        # GBA primary tiles: 0 blank, 1..n_src Crystal tiles (colour+1), then one solid tile.
        self.solid = 1 + n_src
        self.gba_tiles = [[0] * 64] + [[c + 1 for c in t] for t in self.src_tiles] + [[1] * 64]

        def entry(t):
            pal = GBA_SLOT[palmap[t]]
            if self.roofed and ROOF_FIRST <= t < ROOF_FIRST + ROOF_LEN:
                return (NUM_PRIMARY + t - ROOF_FIRST) | (pal << 12)
            if t < 0x60:
                idx = 1 + t if t < n_src else 0
            elif t >= 0x80 and t - 0x80 < 0x60:
                idx = 1 + 0x60 + (t - 0x80) if 0x60 + (t - 0x80) < n_src else 0
            else:
                idx = self.solid  # font area: shows as a flat colour
            return idx | (pal << 12)

        self.metatiles, self.attrs, index = [], [], {}
        self.quad = []  # block -> [metatile id for TL, TR, BL, BR]
        self.quad_kind = []  # block -> [land/water/wall per quadrant]
        for b in range(n_blocks):
            blk = meta[b * 16:(b + 1) * 16]
            cv = coll[b] if b < len(coll) else [0, 0, 0, 0]
            ids, kinds = [], []
            for q in range(4):
                qx, qy = q % 2, q // 2
                tiles = [blk[(2 * qy + dy) * 4 + 2 * qx + dx] for dy in range(2) for dx in range(2)]
                entries = tuple(entry(t) for t in tiles)
                beh = em_behaviors[behavior_for(cr.coll_name.get(cv[q]))]
                key = (entries, beh)
                if key not in index:
                    index[key] = len(self.metatiles)
                    self.metatiles.append(entries)
                    self.attrs.append(beh | (1 << 12))  # METATILE_LAYER_TYPE_COVERED
                ids.append(index[key])
                kinds.append(cr.coll_kind(cv[q]))
            self.quad.append(ids)
            self.quad_kind.append(kinds)
        if len(self.metatiles) > 1024:
            raise SystemExit(f"{const}: {len(self.metatiles)} metatiles, more than 1024")
        self.variants = {}  # key -> secondary symbol suffix
        # tile animations: Crystal tile id -> GBA primary tile index
        self.anim_period, self.anims = 0, {}
        script = f"Tileset{ts['name']}Anim"
        initial = {t: encode_2bpp(self.src_tiles[t]) for t in range(min(0x60, n_src))}
        period, anims = cr.anim.run(script, initial)
        if self.roofed:
            anims = {t: v for t, v in anims.items() if not ROOF_FIRST <= t < ROOF_FIRST + ROOF_LEN}
        if anims:
            self.anim_period = period
            self.anims = {1 + t: frames for t, frames in anims.items()}

    def metatile_bytes(self, mts):
        out = bytearray()
        for entries in mts:
            out += struct.pack("<4H", *entries) + struct.pack("<4H", 0, 0, 0, 0)
        return bytes(out)

    def variant(self, pals, roof, tag):
        key = (tuple(tuple(p) for p in pals), roof)
        if key not in self.variants:
            name = f"{self.sym}_{tag}"
            n = 2
            while name in self.variants.values():
                name, n = f"{self.sym}_{tag}{n}", n + 1
            self.variants[key] = name
        return self.variants[key]

    def write(self):
        made = []
        d = REPO / "data/tilesets/primary" / f"johto_{snake(self.name)}"
        (d / "palettes").mkdir(parents=True, exist_ok=True)
        write_tiles_png(self.gba_tiles, d / "tiles.png")
        prim = self.metatiles[:NUM_PRIMARY]
        (d / "metatiles.bin").write_bytes(self.metatile_bytes(prim))
        (d / "metatile_attributes.bin").write_bytes(struct.pack(f"<{len(prim)}H", *self.attrs[:NUM_PRIMARY]))
        text = self.cr.bg_pals[7]  # the text palette never changes
        for i in range(16):
            write_pal(d / "palettes" / f"{i:02d}.pal", gba_palette(text if i == 5 else self.cr.bg_pals[0x08]))
        made.append((self.sym, d.relative_to(REPO), False))

        # INCBIN cannot include an empty file, so a secondary always has at least one metatile.
        over = self.metatiles[NUM_PRIMARY:] or [(0, 0, 0, 0)]
        over_attrs = self.attrs[NUM_PRIMARY:] or [0]
        for (pals, roof), sym in sorted(self.variants.items(), key=lambda kv: kv[1]):
            d = REPO / "data/tilesets/secondary" / f"johto_{snake(sym[len(PREFIX):])}"
            (d / "palettes").mkdir(parents=True, exist_ok=True)
            if roof is not None:
                img = Image.open(self.cr.roof_gfx[roof]).convert("L")
                roof_tiles = [tile_pixels(img, i) for i in range(ROOF_LEN)]
            elif self.roofed:
                roof_tiles = self.src_tiles[ROOF_FIRST:ROOF_FIRST + ROOF_LEN]
            else:
                roof_tiles = []
            write_tiles_png([[c + 1 for c in t] for t in roof_tiles] or [[0] * 64], d / "tiles.png")
            (d / "metatiles.bin").write_bytes(self.metatile_bytes(over))
            (d / "metatile_attributes.bin").write_bytes(struct.pack(f"<{len(over)}H", *over_attrs))
            for i in range(16):
                gbc = pals[GBA_SLOT.index(i)] if i in GBA_SLOT[:7] else self.cr.bg_pals[0x08]
                write_pal(d / "palettes" / f"{i:02d}.pal", gba_palette(gbc))
            made.append((sym, d.relative_to(REPO), True))
        return made


def anim_c(builders):
    """Generated tile animations for the Johto primaries (included by src/tileset_anims.c)."""
    out = ["// Generated by tools/ditto/import_crystal.py. Do not edit by hand.",
           "// Johto tile animations, replayed frame by frame from Crystal's animation scripts.", ""]
    protos = []
    for b in builders:
        if not b.anims:
            continue
        sym = b.sym
        calls = []
        for n, (gba_tile, states) in enumerate(sorted(b.anims.items())):
            frames = list(dict.fromkeys(states))
            seq = [frames.index(s) for s in states]
            words = []
            for f in frames:
                px = [c + 1 for c in decode_2bpp(f)]
                data = bytes((px[i] | (px[i + 1] << 4)) for i in range(0, 64, 2))
                words.append(", ".join(f"0x{data[i] | (data[i + 1] << 8):04X}" for i in range(0, 32, 2)))
            out.append(f"static const u16 s{sym}Anim{n}_Frames[][16] =\n{{\n"
                       + "".join(f"    {{ {w} }},\n" for w in words) + "};")
            out.append(f"static const u8 s{sym}Anim{n}_Sequence[] = {{ {', '.join(map(str, seq))} }};\n")
            calls.append(f"    if (timer == 0 || s{sym}Anim{n}_Sequence[timer] != s{sym}Anim{n}_Sequence[timer - 1])\n"
                         f"        AppendTilesetAnimToBuffer(s{sym}Anim{n}_Frames[s{sym}Anim{n}_Sequence[timer]], "
                         f"(u16 *)(BG_VRAM + TILE_OFFSET_4BPP({gba_tile})), TILE_SIZE_4BPP);")
        out.append(f"static void TilesetAnim_{sym}(u16 timer)\n{{\n" + "\n".join(calls) + "\n}\n")
        out.append(f"void InitTilesetAnim_{sym}(void)\n{{\n    sPrimaryTilesetAnimCounter = 0;\n"
                   f"    sPrimaryTilesetAnimCounterMax = {b.anim_period};\n"
                   f"    sPrimaryTilesetAnimCallback = TilesetAnim_{sym};\n}}\n")
        protos.append(f"void InitTilesetAnim_{sym}(void);")
    (REPO / "src/data/tilesets/johto_anims.h").write_text("\n".join(out))
    replace_block(REPO / "include/tileset_anims.h", "\n".join(protos))


def tileset_c(made, callbacks):
    headers, graphics, metatiles = [], [], []
    for sym, d, secondary in made:
        headers.append(
            f"const struct Tileset gTileset_{sym} =\n{{\n    .isCompressed = TRUE,\n"
            f"    .isSecondary = {'TRUE' if secondary else 'FALSE'},\n    .tiles = gTilesetTiles_{sym},\n"
            f"    .palettes = gTilesetPalettes_{sym},\n    .metatiles = gMetatiles_{sym},\n"
            f"    .metatileAttributes = gMetatileAttributes_{sym},\n    .callback = {callbacks.get(sym, 'NULL')},\n}};\n")
        pals = "\n".join(f'\tINCGFX_U16("{d}/palettes/{i:02d}.pal", ".gbapal"),' for i in range(16))
        graphics.append(
            f'const u32 gTilesetTiles_{sym}[] = INCGFX_U32("{d}/tiles.png", ".4bpp.lz");\n\n'
            f"const u16 gTilesetPalettes_{sym}[][16] =\n{{\n{pals}\n}};\n")
        metatiles.append(
            f'const u16 gMetatiles_{sym}[] = INCBIN_U16("{d}/metatiles.bin");\n'
            f'const u16 gMetatileAttributes_{sym}[] = INCBIN_U16("{d}/metatile_attributes.bin");\n')
    base = REPO / "src/data/tilesets"
    replace_block(base / "headers.h", "\n".join(headers))
    replace_block(base / "graphics.h", "\n".join(graphics))
    replace_block(base / "metatiles.h", "\n".join(metatiles))


def map_palettes(cr, m):
    """The 8 daytime palettes Crystal would load for this map, and a short tag naming them."""
    env, ts = m["env"], m["tileset"]
    if ts in SPECIAL_PALETTES and not (ts == "TILESET_ICE_PATH" and env == "INDOOR"):
        return [list(p) for p in cr.special[ts]], camel(ts[len("TILESET_"):])
    pals = [list(cr.bg_pals[i]) for i in ENV_PALETTES[env]]
    tag = {"TOWN": "Outdoor", "ROUTE": "Outdoor", "INDOOR": "Indoor", "GATE": "Indoor"}.get(env, "Cave")
    if env in ("TOWN", "ROUTE"):
        roof = cr.roof_pals[m["group_index"]]
        pals[6] = [pals[6][0], roof[0], roof[1], pals[6][3]]
        tag += m["group"]
    return pals, tag


# ---------------------------------------------------------------------- main

def load_em_behaviors():
    body = re.search(r"enum\s*\{(.*?)\};", (REPO / "include/constants/metatile_behaviors.h").read_text(), re.S).group(1)
    body = re.sub(r"//.*", "", body)
    em, i = {}, 0
    for e in (x.strip() for x in body.split(",")):
        if not e:
            continue
        if "=" in e:
            e, v = (p.strip() for p in e.split("="))
            i = int(v, 0)
        em[e] = i
        i += 1
    return em


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    cr = Crystal(Path(sys.argv[1]).resolve())
    em_beh = load_em_behaviors()

    # 1. choose maps
    chosen = [m for m in cr.maps.values()
              if m["group"] not in SKIP_GROUPS
              and (m["landmark"] in cr.johto_landmarks or m["landmark"] in EXTRA_LANDMARKS)
              and m["landmark"] != "LANDMARK_SPECIAL"]
    chosen_consts = {m["const"] for m in chosen}

    # 2. names, avoiding clashes with maps and layouts we do not own
    groups_path = REPO / "data/maps/map_groups.json"
    em_groups = json.loads(groups_path.read_text())
    layouts_path = REPO / "data/layouts/layouts.json"
    em_layouts = json.loads(layouts_path.read_text())
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"layouts": [], "maps": []}
    ours_groups = {g for g in em_groups["group_order"] if g.startswith("gMapGroup_" + PREFIX)}
    ours_layouts = set(manifest["layouts"])
    other_names = {n for g in em_groups["group_order"] if g not in ours_groups for n in em_groups[g]}
    other_ids = set()
    for n in other_names:
        p = REPO / "data/maps" / n / "map.json"
        if p.exists():
            other_ids.add(json.loads(p.read_text())["id"])
    other_layout_ids = {l["id"] for l in em_layouts["layouts"] if l and l["id"] not in ours_layouts}
    other_layout_dirs = {Path(l["blockdata_filepath"]).parent.name for l in em_layouts["layouts"]
                         if l and l["id"] not in ours_layouts}
    map_name, map_id = {}, {}
    for m in chosen:
        name, mid = m["name"], "MAP_" + m["const"]
        if name in other_names or mid in other_ids or name in other_layout_dirs:
            name, mid = f"{PREFIX}_{name}", f"MAP_{PREFIX.upper()}_{m['const']}"
        map_name[m["const"]], map_id[m["const"]] = name, mid

    # 3. tilesets and variants
    builders = {}
    layout_key = {}
    for m in chosen:
        ts = m["tileset"]
        if ts not in builders:
            builders[ts] = TilesetBuilder(cr, ts, em_beh)
        b = builders[ts]
        pals, tag = map_palettes(cr, m)
        roof = cr.group_roof[m["group_index"]] if b.roofed else None
        if roof is not None and m["env"] in ("TOWN", "ROUTE"):
            tag = tag  # roof graphics follow the group, already in the tag for outdoor maps
        elif roof is not None:
            tag += m["group"]
        sec = b.variant(pals, roof, tag)
        layout_key[m["const"]] = (cr.blocks[m["name"]], ts, sec)
    made = []
    for b in builders.values():
        made += b.write()
    tileset_c(made, {b.sym: f"InitTilesetAnim_{b.sym}" for b in builders.values() if b.anims})
    anim_c(builders.values())

    # 4. layouts: one per (block file, tileset, variant)
    layout_of, new_layouts, seen = {}, [], {}
    for m in sorted(chosen, key=lambda m: m["const"]):
        key = layout_key[m["const"]]
        if key in seen:
            layout_of[m["const"]] = seen[key]
            continue
        name = map_name[m["const"]]
        lid = "LAYOUT_" + map_id[m["const"]][len("MAP_"):]
        if lid in other_layout_ids:
            lid = f"LAYOUT_{PREFIX.upper()}_{m['const']}"
        seen[key] = layout_of[m["const"]] = lid
        b = builders[m["tileset"]]
        w, h = m["size"]
        blk = key[0].read_bytes()
        cells = [0] * (4 * w * h)
        for by in range(h):
            for bx in range(w):
                bid = blk[by * w + bx] if by * w + bx < len(blk) else 0
                if bid >= len(b.quad):
                    bid = 0
                for q in range(4):
                    kind = b.quad_kind[bid][q]
                    coll, elev = {"wall": (1, 0), "water": (0, 1), "land": (0, 3)}[kind]
                    x, y = 2 * bx + q % 2, 2 * by + q // 2
                    cells[y * 2 * w + x] = b.quad[bid][q] | (coll << 10) | (elev << 12)
        d = REPO / "data/layouts" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "map.bin").write_bytes(struct.pack(f"<{len(cells)}H", *cells))
        border = cr.connections.get(m["const"], {}).get("border", 0)
        border = border if border < len(b.quad) else 0
        (d / "border.bin").write_bytes(struct.pack("<4H", *[b.quad[border][q] | (1 << 10) for q in range(4)]))
        if 2 * w * 2 * h > 0 and (2 * w + 15) * (2 * h + 14) > 10240:
            raise SystemExit(f"{name} is too large for Emerald's map buffer")
        new_layouts.append({
            "id": lid, "name": f"{name}_Layout", "width": 2 * w, "height": 2 * h,
            "primary_tileset": f"gTileset_{b.sym}", "secondary_tileset": f"gTileset_{key[2]}",
            "border_filepath": f"data/layouts/{name}/border.bin",
            "blockdata_filepath": f"data/layouts/{name}/map.bin",
        })
    em_layouts["layouts"] = [l for l in em_layouts["layouts"] if not l or l["id"] not in ours_layouts] + new_layouts
    layouts_path.write_text(json.dumps(em_layouts, indent=2) + "\n")

    # 5. map sections (met locations) and per-map names shown on entry
    def mapsec_of(m):
        lm = m["landmark"][len("LANDMARK_"):]
        return "MAPSEC_" + LANDMARK_PARENT.get(lm, lm)
    mapsecs = sorted({mapsec_of(m) for m in chosen},
                     key=lambda ms: list(cr.landmark_name).index("LANDMARK_" + ms[len("MAPSEC_"):]))
    sec_path = REPO / "src/data/region_map/region_map_sections.json"
    secs = json.loads(sec_path.read_text())
    owned = set(manifest.get("mapsecs", []))
    clash = {e["id"] for e in secs["map_sections"] if e["id"] not in owned} & set(mapsecs)
    if clash:
        raise SystemExit(f"map sections already exist: {sorted(clash)}")
    secs["map_sections"] = [e for e in secs["map_sections"] if e["id"] not in owned] + [
        {"id": ms, "name": cr.landmark_name["LANDMARK_" + ms[len("MAPSEC_"):]]} for ms in mapsecs]
    sec_path.write_text(json.dumps(secs, indent=2, ensure_ascii=False) + "\n")
    if len(secs["map_sections"]) + 1 > 0xFD:
        raise SystemExit("too many map sections: met location values 0xFD-0xFF are reserved")
    strings, rows = {}, []
    for m in sorted(chosen, key=lambda m: m["const"]):
        name = cr.landmark_name[m["landmark"]]
        sym = strings.setdefault(name, "sJohtoMapName_" + re.sub(r"\W", "", name.title().replace(" ", "")))
        rows.append(f"    {{ MAP_GROUP({map_id[m['const']]}), MAP_NUM({map_id[m['const']]}), {sym}, "
                    f"{POPUP_THEME[m['env']]} }},")
    (REPO / "src/data/johto_map_names.h").write_text(
        "// Generated by tools/ditto/import_crystal.py. Do not edit by hand.\n"
        "// The name shown on entering each Johto map, and its pop-up frame.\n\n"
        + "".join(f'static const u8 {sym}[] = _("{name}");\n' for name, sym in strings.items())
        + "\nstatic const struct JohtoMapName sJohtoMapNames[] =\n{\n" + "\n".join(rows) + "\n};\n")

    # 6. maps
    songs = (REPO / "include/constants/songs.h").read_text()
    dropped_warps = dropped_conns = 0
    for m in chosen:
        c = m["const"]
        music = next((mus for k, mus in MUSIC if k in m["music"]), ENV_MUSIC.get(m["env"], "MUS_RG_PEWTER"))
        if not re.search(rf"\b{music}\b", songs):
            music = "MUS_RG_PEWTER"
        dirs = {"north": "up", "south": "down", "west": "left", "east": "right"}
        conns = []
        for direction, target, off in cr.connections.get(c, {}).get("list", []):
            if target in chosen_consts:
                conns.append({"map": map_id[target], "offset": 2 * off, "direction": dirs[direction]})
            else:
                dropped_conns += 1
        warps = []
        for i, (x, y, dest, wid) in enumerate(cr.warps(m["name"])):
            if dest in chosen_consts:
                warps.append({"x": x, "y": y, "elevation": 0, "dest_map": map_id[dest], "dest_warp_id": str(wid - 1)})
            else:  # leads to a map we did not import: loop back so warp ids stay stable
                warps.append({"x": x, "y": y, "elevation": 0, "dest_map": map_id[c], "dest_warp_id": str(i)})
                dropped_warps += 1
        outdoor = m["env"] in ("TOWN", "ROUTE")
        out = {
            "id": map_id[c], "name": map_name[c], "layout": layout_of[c], "music": music,
            "region_map_section": mapsec_of(m), "requires_flash": m["palette"] == "PALETTE_DARK",
            "weather": "WEATHER_SUNNY" if outdoor else "WEATHER_NONE",
            "map_type": MAP_TYPES[m["env"]],
            "allow_cycling": m["env"] in ("TOWN", "ROUTE", "CAVE", "DUNGEON"),
            "allow_escaping": m["env"] in ("CAVE", "DUNGEON"),
            "allow_running": m["env"] not in ("INDOOR", "GATE", "ENVIRONMENT_5"),
            "show_map_name": m["env"] in ("TOWN", "ROUTE", "CAVE", "DUNGEON"),
            "battle_scene": "MAP_BATTLE_SCENE_GYM" if "Gym" in m["name"] else "MAP_BATTLE_SCENE_NORMAL",
            "connections": conns or None,
            "object_events": [], "warp_events": warps, "coord_events": [], "bg_events": [],
        }
        d = REPO / "data/maps" / map_name[c]
        d.mkdir(parents=True, exist_ok=True)
        mj = d / "map.json"
        if mj.exists():
            old = json.loads(mj.read_text())
            for key in ("object_events", "coord_events", "bg_events"):
                out[key] = old.get(key, [])
        mj.write_text(json.dumps(out, indent=2) + "\n")
        if not (d / "scripts.inc").exists():
            (d / "scripts.inc").write_text(f"{map_name[c]}_MapScripts::\n\t.byte 0\n")

    # 7. map groups and script includes
    ours_maps = {n for g in ours_groups for n in em_groups[g]}
    for g in ours_groups:
        del em_groups[g]
    em_groups["group_order"] = [g for g in em_groups["group_order"] if g not in ours_groups]
    order = [n for n in em_groups["connections_include_order"] if n not in ours_maps]
    rebuilt = {k: v for k, v in em_groups.items() if k != "connections_include_order"}
    all_names = []
    for gname in dict.fromkeys(m["group"] for m in chosen):
        key = f"gMapGroup_{PREFIX}{gname}"
        members = [m for m in chosen if m["group"] == gname]
        rebuilt[key] = [map_name[m["const"]] for m in members]
        rebuilt["group_order"].append(key)
        all_names += rebuilt[key]
        order += [map_name[m["const"]] for m in members if cr.connections.get(m["const"], {}).get("list")
                  and any(t in chosen_consts for _, t, _ in cr.connections[m["const"]]["list"])]
    rebuilt["connections_include_order"] = order
    groups_path.write_text(json.dumps(rebuilt, indent=2) + "\n")
    includes = "\n".join(f'\t.include "data/maps/{n}/scripts.inc"' for n in all_names)
    replace_block(REPO / "data/event_scripts.s", includes, comment="@")
    MANIFEST.write_text(json.dumps({"layouts": sorted(set(layout_of.values())), "maps": sorted(all_names),
                                    "mapsecs": mapsecs},
                                   indent=2) + "\n")

    print(f"maps: {len(chosen)}  layouts: {len(new_layouts)}  tilesets: {len(made)} "
          f"({len(builders)} primaries)")
    for b in builders.values():
        print(f"  {b.sym}: {len(b.metatiles)} metatiles, {len(b.variants)} variants")
    print(f"warps looped back (destination not imported): {dropped_warps}; connections dropped: {dropped_conns}")
    renamed = sorted(v for k, v in map_name.items() if v != cr.maps[k]["name"])
    print(f"renamed to avoid clashes: {renamed}")


if __name__ == "__main__":
    main()
