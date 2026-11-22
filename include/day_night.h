#ifndef GUARD_DAY_NIGHT_H
#define GUARD_DAY_NIGHT_H

// Day/night for the overworld. See src/day_night.c for how it works.
// Nothing here is saved: the period always comes from the real-time clock.

enum { TIME_OF_DAY_MORNING, TIME_OF_DAY_DAY, TIME_OF_DAY_NIGHT };

// Current period, read fresh from the real-time clock.
u8 GetTimeOfDay(void);

// Pure mapping from an hour (0-23) to a period, following Pokémon Crystal:
// morning 4:00-9:59, day 10:00-17:59, night 18:00-3:59.
u8 GetTimeOfDayForHour(s32 hour);

// Authored per-period palettes for a tileset (generated from Crystal for Johto).
struct TilesetTimePalettes
{
    const struct Tileset *tileset;
    const u16 (*morning)[16]; // same layout as tileset->palettes: 16 palettes of 16 colours
    const u16 (*night)[16];
};

extern const struct TilesetTimePalettes gTilesetTimePalettes[]; // ends with an entry whose tileset is NULL

// Engine hooks.
void DayNight_LatchPeriod(void);
const u16 (*DayNight_GetTilesetPalettes(const struct Tileset *tileset))[16];
void DayNight_TintBgPalettes(u16 offset, u16 numColors);
void DayNight_OnPrimaryTilesetPaletteLoaded(const struct MapLayout *mapLayout);
bool8 DayNight_PrimaryTilesetPaletteIsStale(const struct MapLayout *mapLayout);
void DayNight_ClearObjectPaletteRecords(void);
void DayNight_OnObjectPaletteLoaded(u8 paletteSlot, const u16 *src, u16 tag);
void DayNight_UpdateOverworld(void);

#endif // GUARD_DAY_NIGHT_H
