#!/usr/bin/env python3
"""Import Kanto mainland maps and tilesets from a pret/pokefirered checkout.

Usage:
    python3 tools/ditto/import_frlg.py /path/to/pokefirered

What it brings over: layouts (tile grids), tilesets, map headers, warps and
map-to-map connections. What it leaves behind: NPCs, signs, triggers and
scripts, because FireRed scripts use flags, specials and text that do not
exist in this engine. Every imported map gets an empty scripts.inc.

Tileset trick: FireRed splits its 1024 tiles/metatiles 640 primary + 384
secondary and its 13 palettes 7 + 6. Emerald splits 512 + 512 and 6 + 7. The
totals match, so each imported secondary tileset is built as "the primary's
overflow (128 tiles, 128 metatiles, palette 6) followed by the FireRed
secondary". Every tile, metatile and palette index then stays identical and
map.bin files can be copied unchanged.

Safe to re-run: generated sections are replaced, not duplicated.
"""
import json
import re
import shutil
import struct
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
PREFIX = "Kanto"
BEGIN = "// BEGIN ditto:import_frlg (generated, do not edit by hand)"
END = "// END ditto:import_frlg"

FR_PRIMARY, EM_PRIMARY = 640, 512
OVERFLOW = FR_PRIMARY - EM_PRIMARY  # 128

# Map groups that are entirely Kanto mainland interiors.
INDOOR_GROUPS = [
    "IndoorPallet", "IndoorViridian", "IndoorPewter", "IndoorCerulean", "IndoorLavender",
    "IndoorVermilion", "IndoorCeladon", "IndoorFuchsia", "IndoorCinnabar", "IndoorIndigoPlateau",
    "IndoorSaffron", "IndoorRoute2", "IndoorRoute4", "IndoorRoute5", "IndoorRoute6", "IndoorRoute7",
    "IndoorRoute8", "IndoorRoute10", "IndoorRoute11", "IndoorRoute12", "IndoorRoute15",
    "IndoorRoute16", "IndoorRoute18", "IndoorRoute19", "IndoorRoute22", "IndoorRoute23",
    "IndoorRoute25",
]
# Mixed groups: keep only maps whose region-map section is on the mainland.
MIXED_GROUPS = ["TownsAndRoutes", "Dungeons"]
KANTO_MAPSECS = {
    "MAPSEC_PALLET_TOWN", "MAPSEC_VIRIDIAN_CITY", "MAPSEC_PEWTER_CITY", "MAPSEC_CERULEAN_CITY",
    "MAPSEC_LAVENDER_TOWN", "MAPSEC_VERMILION_CITY", "MAPSEC_CELADON_CITY", "MAPSEC_FUCHSIA_CITY",
    "MAPSEC_CINNABAR_ISLAND", "MAPSEC_INDIGO_PLATEAU", "MAPSEC_SAFFRON_CITY",
    *(f"MAPSEC_ROUTE_{n}" for n in range(1, 26)),
    "MAPSEC_VIRIDIAN_FOREST", "MAPSEC_MT_MOON", "MAPSEC_S_S_ANNE", "MAPSEC_UNDERGROUND_PATH",
    "MAPSEC_UNDERGROUND_PATH_2", "MAPSEC_DIGLETTS_CAVE", "MAPSEC_KANTO_VICTORY_ROAD",
    "MAPSEC_ROCKET_HIDEOUT", "MAPSEC_SILPH_CO", "MAPSEC_POKEMON_MANSION",
    "MAPSEC_KANTO_SAFARI_ZONE", "MAPSEC_CERULEAN_CAVE", "MAPSEC_POKEMON_LEAGUE",
    "MAPSEC_ROCK_TUNNEL", "MAPSEC_SEAFOAM_ISLANDS", "MAPSEC_POKEMON_TOWER", "MAPSEC_POWER_PLANT",
}

# FireRed metatile behaviours with no same-named Emerald behaviour.
BEHAVIOR_OVERRIDES = {
    "MB_RUNNING_DISALLOWED": "MB_NO_RUNNING",
    "MB_FAST_WATER": "MB_OCEAN_WATER",
    "MB_DEEP_WATER": "MB_DEEP_WATER",
    "MB_UNDERWATER_BLOCKED_ABOVE": "MB_NORMAL",
    "MB_UNUSED_WATER": "MB_OCEAN_WATER",
    "MB_CYCLING_ROAD_WATER": "MB_OCEAN_WATER",
    "MB_STRENGTH_BUTTON": "MB_NORMAL",
    "MB_SAND": "MB_SAND",
    "MB_SEMI_DEEP_WATER": "MB_OCEAN_WATER",
    "MB_ROCK_STAIRS": "MB_NORMAL",
    "MB_SAND_CAVE": "MB_SAND",
    "MB_WARP_DOOR": "MB_ANIMATED_DOOR",
    "MB_POKEMON_CENTER_ESCALATOR": "MB_NORMAL",
    "MB_UP_RIGHT_STAIR_WARP": "MB_EAST_ARROW_WARP",
    "MB_UP_LEFT_STAIR_WARP": "MB_WEST_ARROW_WARP",
    "MB_DOWN_RIGHT_STAIR_WARP": "MB_EAST_ARROW_WARP",
    "MB_DOWN_LEFT_STAIR_WARP": "MB_WEST_ARROW_WARP",
    "MB_UNION_ROOM_WARP": "MB_NORMAL",
    "MB_CYCLING_ROAD_PULL_DOWN": "MB_NORMAL",
    "MB_CYCLING_ROAD_PULL_DOWN_GRASS": "MB_TALL_GRASS",
    # Step-on warps: cave mouths, warp pads and holes all become plain step-on warps.
    "MB_CAVE_DOOR": "MB_NON_ANIMATED_DOOR",
    "MB_REGULAR_WARP": "MB_NON_ANIMATED_DOOR",
    "MB_FALL_WARP": "MB_NON_ANIMATED_DOOR",
    # Spinner tiles (Rocket Hideout, Viridian Gym) need engine support we do not have.
    **{f"MB_SPIN_{d}": "MB_NORMAL" for d in ("LEFT", "RIGHT", "UP", "DOWN")},
    "MB_STOP_SPINNING": "MB_NORMAL",
    # "Press A to read a description" furniture: no behaviour until scripts are ported.
    **{name: "MB_NORMAL" for name in (
        "MB_WINDOW", "MB_DRESSER", "MB_KITCHEN", "MB_CABINET", "MB_COMPUTER", "MB_CUP", "MB_PORTHOLE",
        "MB_SIGNPOST", "MB_FOOD", "MB_PAINTING", "MB_POKEMART_SIGN", "MB_POKEMON_CENTER_SIGN",
        "MB_NEATLY_LINED_UP_TOOLS", "MB_BURGLARY", "MB_TELEPHONE", "MB_POKEMART_SHELF",
        "MB_INDIGO_PLATEAU_SIGN_1", "MB_INDIGO_PLATEAU_SIGN_2", "MB_BLINKING_LIGHTS",
        "MB_POWER_PLANT_MACHINE", "MB_ADVERTISING_POSTER", "MB_BATTLE_RECORDS",
        "MB_CABLE_CLUB_WIRELESS_MONITOR", "MB_FOOD_SMELLS_TASTY", "MB_TRASH_BIN", "MB_BLUEPRINTS",
        "MB_TRAINER_TOWER_MONITOR",
    )},
}
BATTLE_SCENES = {"MAP_BATTLE_SCENE_NORMAL", "MAP_BATTLE_SCENE_GYM"}
WEATHER = {"WEATHER_FOG_HORIZONTAL": "WEATHER_FOG_HORIZONTAL"}


def snake(name):
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


def const_case(name):
    s = re.sub(r"(?<=[a-z])(?=[A-Z0-9])|(?<=[0-9])(?=[A-Z][a-z])|(?<=[A-Z0-9])(?=[A-Z][a-z])", "_", name)
    return s.upper()


def replace_block(path, body, comment="//"):
    begin, end = BEGIN.replace("//", comment, 1), END.replace("//", comment, 1)
    text = path.read_text()
    block = f"{begin}\n{body.rstrip()}\n{end}\n"
    if begin in text:
        text = re.sub(re.escape(begin) + r".*?" + re.escape(end) + r"\n", lambda _: block, text, flags=re.S)
    else:
        text = text.rstrip("\n") + "\n\n" + block
    path.write_text(text)


# ---------------------------------------------------------------- behaviours

def load_behaviors(frlg):
    fr = {}
    for name, val in re.findall(r"^#define\s+(MB_\w+)\s+(0x[0-9A-Fa-f]+|\d+)\s*$",
                                (frlg / "include/constants/metatile_behaviors.h").read_text(), re.M):
        fr[int(val, 0)] = name
    body = re.search(r"enum\s*\{(.*?)\};", (REPO / "include/constants/metatile_behaviors.h").read_text(), re.S).group(1)
    body = re.sub(r"//.*", "", body)
    em, i = {}, 0
    for entry in body.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "=" in entry:
            entry, v = (p.strip() for p in entry.split("="))
            i = int(v, 0)
        em[entry] = i
        i += 1
    return fr, em


class BehaviorMap:
    def __init__(self, frlg):
        self.fr, self.em = load_behaviors(frlg)
        self.unmapped = {}

    def convert(self, value):
        name = self.fr.get(value)
        if name is None:
            self.unmapped[f"0x{value:02X}"] = self.unmapped.get(f"0x{value:02X}", 0) + 1
            return 0
        target = BEHAVIOR_OVERRIDES.get(name, name)
        if target not in self.em:
            self.unmapped[name] = self.unmapped.get(name, 0) + 1
            return 0
        return self.em[target]


# ------------------------------------------------------------------ tilesets

class Source:
    """Where one FireRed tileset keeps its parts. Some tilesets borrow another's
    tiles and palettes (Silph Co. uses the Condominiums graphics), so each part
    is located separately."""

    def __init__(self, tiles, palettes, metatiles, attributes):
        self.tiles, self.palettes, self.metatiles, self.attributes = tiles, palettes, metatiles, attributes
        self.name = metatiles.parent.name


def parse_tilesets(frlg):
    """Return {gTileset_X: Source}."""
    headers = (frlg / "src/data/tilesets/headers.h").read_text()
    # The General tileset's graphics are declared in graphics.c, the rest in graphics.h.
    text = "".join((frlg / f).read_text() for f in (
        "src/data/tilesets/graphics.h", "src/graphics.c", "src/data/tilesets/metatiles.h"))
    first_path = {}
    for sym, path in re.findall(r"(g\w+)\[\](?:\[16\])?\s*=\s*\{?\s*INC\w+\(\"([^\"]+)\"", text):
        first_path[sym] = frlg / path
    out = {}
    for name, body in re.findall(r"const struct Tileset (gTileset_\w+) =\s*\{(.*?)\};", headers, re.S):
        field = lambda f: re.search(rf"\.{f} = (\w+)", body).group(1)
        try:
            out[name] = Source(
                tiles=first_path[field("tiles")].parent / "tiles.png",
                palettes=first_path[field("palettes")].parent,
                metatiles=first_path[field("metatiles")],
                attributes=first_path[field("metatileAttributes")],
            )
        except KeyError:
            continue
    return out


def read_tiles(path):
    img = Image.open(path)
    if img.mode != "P":
        raise SystemExit(f"{path}: expected an indexed PNG")
    if img.width != 128:
        raise SystemExit(f"{path}: expected width 128, got {img.width}")
    return img


def save_tiles(rows, palette, path):
    """rows: list of (image, top, bottom) strips stacked vertically."""
    height = sum(b - t for _, t, b in rows)
    out = Image.new("P", (128, max(height, 8)), 0)
    out.putpalette(palette)
    y = 0
    for img, top, bottom in rows:
        avail = min(bottom, img.height)
        if avail > top:
            out.paste(img.crop((0, top, 128, avail)), (0, y))
        y += bottom - top
    out.save(path, bits=4)


def convert_attrs(data, bmap):
    out = bytearray()
    for (v,) in struct.iter_unpack("<I", data[: len(data) // 4 * 4]):
        behavior = bmap.convert(v & 0x1FF)
        layer = (v >> 29) & 0x3
        out += struct.pack("<H", behavior | (layer << 12))
    return bytes(out)


def pad(data, size):
    return data[:size] + b"\0" * (size - len(data[:size]))


def write_palettes(dst, src, slot6_from=None):
    (dst / "palettes").mkdir(parents=True, exist_ok=True)
    for i in range(16):
        source = src
        if i == 6 and slot6_from is not None:
            source = slot6_from
        shutil.copyfile(source.palettes / f"{i:02d}.pal", dst / "palettes" / f"{i:02d}.pal")


def new_tileset_name(old):
    return "gTileset_" + PREFIX + old[len("gTileset_"):]


def import_tilesets(frlg, pairs, bmap):
    dirs = parse_tilesets(frlg)
    made = []  # (symbol suffix, repo-relative dir, is_secondary)
    primaries = sorted({p for p, _ in pairs})
    secondary_primary = {}
    for p, s in sorted(pairs):
        if secondary_primary.setdefault(s, p) != p:
            raise SystemExit(f"{s} is used with two primaries; variants are not supported yet")

    for p in primaries:
        src = dirs[p]
        dst = REPO / "data/tilesets/primary" / f"kanto_{src.name}"
        dst.mkdir(parents=True, exist_ok=True)
        img = read_tiles(src.tiles)
        save_tiles([(img, 0, EM_PRIMARY // 16 * 8)], img.getpalette(), dst / "tiles.png")
        (dst / "metatiles.bin").write_bytes(src.metatiles.read_bytes()[: EM_PRIMARY * 16])
        attrs = convert_attrs(src.attributes.read_bytes(), bmap)
        (dst / "metatile_attributes.bin").write_bytes(attrs[: EM_PRIMARY * 2])
        write_palettes(dst, src)
        made.append((new_tileset_name(p)[len("gTileset_"):], dst.relative_to(REPO), False))

    for s, p in sorted(secondary_primary.items()):
        src, psrc = dirs[s], dirs[p]
        dst = REPO / "data/tilesets/secondary" / f"kanto_{src.name}"
        dst.mkdir(parents=True, exist_ok=True)
        pimg, simg = read_tiles(psrc.tiles), read_tiles(src.tiles)
        top = EM_PRIMARY // 16 * 8
        save_tiles([(pimg, top, top + OVERFLOW // 16 * 8), (simg, 0, simg.height)],
                   simg.getpalette(), dst / "tiles.png")
        pmeta = psrc.metatiles.read_bytes()[EM_PRIMARY * 16:]
        (dst / "metatiles.bin").write_bytes(pad(pmeta, OVERFLOW * 16) + src.metatiles.read_bytes())
        pattr = convert_attrs(psrc.attributes.read_bytes(), bmap)[EM_PRIMARY * 2:]
        sattr = convert_attrs(src.attributes.read_bytes(), bmap)
        (dst / "metatile_attributes.bin").write_bytes(pad(pattr, OVERFLOW * 2) + sattr)
        write_palettes(dst, src, slot6_from=psrc)
        made.append((new_tileset_name(s)[len("gTileset_"):], dst.relative_to(REPO), True))

    headers, graphics, metatiles = [], [], []
    for sym, d, secondary in made:
        headers.append(
            f"const struct Tileset gTileset_{sym} =\n{{\n    .isCompressed = TRUE,\n"
            f"    .isSecondary = {'TRUE' if secondary else 'FALSE'},\n    .tiles = gTilesetTiles_{sym},\n"
            f"    .palettes = gTilesetPalettes_{sym},\n    .metatiles = gMetatiles_{sym},\n"
            f"    .metatileAttributes = gMetatileAttributes_{sym},\n    .callback = NULL,\n}};\n")
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
    return len(made)


# ---------------------------------------------------------------------- maps

def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    frlg = Path(sys.argv[1]).resolve()
    bmap = BehaviorMap(frlg)

    fr_groups = json.loads((frlg / "data/maps/map_groups.json").read_text())
    fr_layouts = {l["id"]: l for l in json.loads((frlg / "data/layouts/layouts.json").read_text())["layouts"] if l}

    # 1. choose maps
    chosen = {}  # group -> [map dir names]
    fr_maps = {}
    for group in MIXED_GROUPS + INDOOR_GROUPS:
        for name in fr_groups["gMapGroup_" + group]:
            m = json.loads((frlg / "data/maps" / name / "map.json").read_text())
            if group in MIXED_GROUPS and m["region_map_section"] not in KANTO_MAPSECS:
                continue
            chosen.setdefault(group, []).append(name)
            fr_maps[m["id"]] = m

    # 2. names, avoiding collisions with what Emerald already has
    em_groups_path = REPO / "data/maps/map_groups.json"
    em_groups = json.loads(em_groups_path.read_text())
    em_layouts_path = REPO / "data/layouts/layouts.json"
    em_layouts = json.loads(em_layouts_path.read_text())
    ours_groups = {g for g in em_groups["group_order"] if g.startswith("gMapGroup_" + PREFIX)}
    ours_maps = {n for g in ours_groups for n in em_groups[g]}
    ours_layout_ids = set(json.loads(MANIFEST.read_text())["layouts"]) if MANIFEST.exists() else set()
    em_map_names = {n for g in em_groups["group_order"] if g not in ours_groups for n in em_groups[g]}
    em_layout_ids = {l["id"] for l in em_layouts["layouts"] if l["id"] not in ours_layout_ids}
    em_layout_dirs = {Path(l["blockdata_filepath"]).parent.name for l in em_layouts["layouts"]
                      if l["id"] not in ours_layout_ids}

    map_name, map_id = {}, {}
    for mid, m in fr_maps.items():
        if m["name"] in em_map_names:
            map_name[mid] = f"{PREFIX}_{m['name']}"
            map_id[mid] = "MAP_" + PREFIX.upper() + "_" + mid[len("MAP_"):]
        else:
            map_name[mid], map_id[mid] = m["name"], mid

    used_layouts = {m["layout"] for m in fr_maps.values()}
    layout_id, layout_dir = {}, {}
    for lid in used_layouts:
        l = fr_layouts[lid]
        d = Path(l["blockdata_filepath"]).parent.name
        clash = lid in em_layout_ids or d in em_layout_dirs
        layout_id[lid] = "LAYOUT_" + PREFIX.upper() + "_" + lid[len("LAYOUT_"):] if clash else lid
        layout_dir[lid] = f"{PREFIX}_{d}" if clash else d

    # 3. tilesets
    pairs = {(fr_layouts[l]["primary_tileset"], fr_layouts[l]["secondary_tileset"]) for l in used_layouts}
    n_tilesets = import_tilesets(frlg, pairs, bmap)

    # 4. layouts
    new_layouts = []
    for lid in sorted(used_layouts):
        l = fr_layouts[lid]
        dst = REPO / "data/layouts" / layout_dir[lid]
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(frlg / l["blockdata_filepath"], dst / "map.bin")
        bw, bh = l.get("border_width", 2), l.get("border_height", 2)
        border = list(struct.unpack(f"<{bw * bh}H", (frlg / l["border_filepath"]).read_bytes()[: bw * bh * 2]))
        cells = [border[(y % bh) * bw + (x % bw)] for y in range(2) for x in range(2)]
        (dst / "border.bin").write_bytes(struct.pack("<4H", *cells))
        new_layouts.append({
            "id": layout_id[lid], "name": f"{layout_dir[lid]}_Layout",
            "width": l["width"], "height": l["height"],
            "primary_tileset": new_tileset_name(l["primary_tileset"]),
            "secondary_tileset": new_tileset_name(l["secondary_tileset"]),
            "border_filepath": f"data/layouts/{layout_dir[lid]}/border.bin",
            "blockdata_filepath": f"data/layouts/{layout_dir[lid]}/map.bin",
        })
    em_layouts["layouts"] = [l for l in em_layouts["layouts"] if l["id"] not in ours_layout_ids] + new_layouts
    em_layouts_path.write_text(json.dumps(em_layouts, indent=2) + "\n")

    # 5. maps
    songs = (REPO / "include/constants/songs.h").read_text()
    dropped_warps = dropped_conns = 0
    for mid, m in fr_maps.items():
        music = "MUS_RG_" + m["music"][len("MUS_"):]
        if not re.search(rf"\b{music}\b", songs):
            music = "MUS_NONE" if m["music"] == "MUS_NONE" else "MUS_RG_PALLET"
        conns = []
        for c in m.get("connections") or []:
            if c["map"] in fr_maps:
                conns.append({"map": map_id[c["map"]], "offset": c["offset"], "direction": c["direction"]})
            else:
                dropped_conns += 1
        warps = []
        for i, w in enumerate(m["warp_events"]):
            w = dict(w)
            if w["dest_map"] in fr_maps:
                w["dest_map"] = map_id[w["dest_map"]]
            else:  # leads to a map we did not import: loop back onto itself so warp ids stay stable
                w["dest_map"], w["dest_warp_id"] = map_id[mid], str(i)
                dropped_warps += 1
            warps.append(w)
        out = {
            "id": map_id[mid], "name": map_name[mid], "layout": layout_id[m["layout"]],
            "music": music, "region_map_section": m["region_map_section"],
            "requires_flash": m["requires_flash"],
            "weather": m["weather"], "map_type": m["map_type"],
            "allow_cycling": m["allow_cycling"], "allow_escaping": m["allow_escaping"],
            "allow_running": m["allow_running"], "show_map_name": m["show_map_name"],
            "battle_scene": m["battle_scene"] if m["battle_scene"] in BATTLE_SCENES else "MAP_BATTLE_SCENE_NORMAL",
            "connections": conns or None,
            "object_events": [], "warp_events": warps, "coord_events": [], "bg_events": [],
        }
        dst = REPO / "data/maps" / map_name[mid]
        dst.mkdir(parents=True, exist_ok=True)
        map_json = dst / "map.json"
        if map_json.exists():
            old = json.loads(map_json.read_text())
            # keep anything added by hand since the last import
            for key in ("object_events", "coord_events", "bg_events"):
                out[key] = old.get(key, [])
        map_json.write_text(json.dumps(out, indent=2) + "\n")
        scripts = dst / "scripts.inc"
        if not scripts.exists():
            scripts.write_text(f"{map_name[mid]}_MapScripts::\n\t.byte 0\n")

    # 6. map groups and script includes
    for g in ours_groups:
        del em_groups[g]
    em_groups["group_order"] = [g for g in em_groups["group_order"] if g not in ours_groups]
    order = [n for n in em_groups["connections_include_order"] if n not in ours_maps]
    rebuilt = {k: v for k, v in em_groups.items() if k != "connections_include_order"}
    all_names = []
    for group, names in chosen.items():
        key = f"gMapGroup_{PREFIX}{group}"
        ids = [next(i for i, m in fr_maps.items() if m["name"] == n) for n in names]
        rebuilt[key] = [map_name[i] for i in ids]
        rebuilt["group_order"].append(key)
        all_names += rebuilt[key]
        order += [map_name[i] for i in ids if fr_maps[i].get("connections")]
    rebuilt["connections_include_order"] = order
    em_groups_path.write_text(json.dumps(rebuilt, indent=2) + "\n")

    includes = "\n".join(f'\t.include "data/maps/{n}/scripts.inc"' for n in all_names)
    replace_block(REPO / "data/event_scripts.s", includes, comment="@")

    MANIFEST.write_text(json.dumps({"layouts": sorted(layout_id.values()), "maps": sorted(all_names)}, indent=2) + "\n")

    print(f"tilesets: {n_tilesets}  layouts: {len(new_layouts)}  maps: {len(fr_maps)}")
    print(f"warps looped back (destination not imported): {dropped_warps}; connections dropped: {dropped_conns}")
    renamed = sorted(v for k, v in map_name.items() if v != fr_maps[k]["name"])
    print(f"renamed to avoid clashes: {renamed}")
    if bmap.unmapped:
        print("UNMAPPED behaviours (set to MB_NORMAL):", bmap.unmapped)


MANIFEST = REPO / "tools/ditto/import_frlg.manifest.json"

if __name__ == "__main__":
    main()
