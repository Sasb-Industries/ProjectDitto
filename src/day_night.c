#include "global.h"
#include "day_night.h"
#include "event_object_movement.h"
#include "field_weather.h"
#include "fieldmap.h"
#include "main.h"
#include "overworld.h"
#include "palette.h"
#include "rtc.h"
#include "script.h"
#include "sprite.h"
#include "constants/map_types.h"
#include "constants/rgb.h"

// Day/night for the overworld.
//
// The period (morning, day, night) comes from the real-time clock and is
// never saved. Palettes change in two ways:
//  - Tilesets listed in gTilesetTimePalettes (Johto, converted from Crystal)
//    load their authored morning or night palettes instead of the normal ones.
//    A map using such a tileset counts as "authored" and gets no computed
//    background tint.
//  - Outdoor maps (town, city, route, ocean route) without authored palettes
//    get a computed tint on their tileset palettes (BG slots 0-12).
// Object event palettes (player, NPCs, reflections) and overworld field
// effect palettes get the same computed tint on every outdoor map, authored
// or not. Indoor Hoenn and Kanto maps are left alone.
//
// The tint is applied as the palette is loaded, so it lands in both
// gPlttBufferUnfaded and gPlttBufferFaded exactly as if the tinted colours
// were the source data. Weather colour maps and screen fades read the
// unfaded buffer, so they work on top of the tint without knowing about it.
//
// The period used for loading is latched (sPeriod) when the map's object
// palettes are set up and whenever the overworld notices the clock moved
// into a new period. DayNight_UpdateOverworld checks the clock about once a
// second while the player is walking freely and reloads the affected
// palettes when the period changes.

// Testing aid: uncomment to pin the period regardless of the clock.
// #define DITTO_FORCE_TIME_OF_DAY TIME_OF_DAY_NIGHT

#include "data/tilesets/time_palettes.h"

// ---------------------------------------------------------------------------
// Tint values. Each channel (0-31) becomes (c * mul / 256) + add, clamped.
// Tune here.
struct DayNightTint
{
    u16 mulR, mulG, mulB;
    s8 addR, addG, addB;
};

static const struct DayNightTint sTints[] =
{
    // Warm and slightly brighter.
    [TIME_OF_DAY_MORNING] = { .mulR = 276, .mulG = 262, .mulB = 232, .addR = 1, .addG = 1, .addB = 0 },
    // Unchanged.
    [TIME_OF_DAY_DAY]     = { .mulR = 256, .mulG = 256, .mulB = 256, .addR = 0, .addG = 0, .addB = 0 },
    // Darker and blue.
    [TIME_OF_DAY_NIGHT]   = { .mulR = 150, .mulG = 166, .mulB = 222, .addR = 0, .addG = 0, .addB = 1 },
};
// ---------------------------------------------------------------------------

#define PERIOD_UNSET 0xFF
#define FRAMES_BETWEEN_CLOCK_CHECKS 60

struct ObjectPaletteRecord
{
    const u16 *src; // NULL if the slot is not tracked
    u16 tag;        // sprite palette tag, or TAG_NONE for fixed object event slots
};

EWRAM_DATA static u8 sPeriod = PERIOD_UNSET;
EWRAM_DATA static u8 sClockCheckTimer = 0;
EWRAM_DATA static u8 sPrimaryLoadedPeriod = PERIOD_UNSET;
EWRAM_DATA static bool8 sPrimaryLoadedTinted = FALSE;
EWRAM_DATA static const struct Tileset *sPrimaryLoadedTileset = NULL;
EWRAM_DATA static struct ObjectPaletteRecord sObjectPalettes[16] = {0};

u8 GetTimeOfDayForHour(s32 hour)
{
    if (hour >= 4 && hour < 10)
        return TIME_OF_DAY_MORNING;
    if (hour >= 10 && hour < 18)
        return TIME_OF_DAY_DAY;
    return TIME_OF_DAY_NIGHT;
}

u8 GetTimeOfDay(void)
{
#ifdef DITTO_FORCE_TIME_OF_DAY
    return DITTO_FORCE_TIME_OF_DAY;
#else
    // Without a working clock, stay in daytime rather than guess.
    if (RtcGetErrorStatus() & RTC_ERR_FLAG_MASK)
        return TIME_OF_DAY_DAY;
    RtcCalcLocalTime();
    return GetTimeOfDayForHour(gLocalTime.hours);
#endif
}

static u8 GetPeriod(void)
{
    if (sPeriod == PERIOD_UNSET)
        sPeriod = GetTimeOfDay();
    return sPeriod;
}

void DayNight_LatchPeriod(void)
{
    sPeriod = GetTimeOfDay();
    sClockCheckTimer = 0;
}

static bool8 IsOutdoorMapType(u8 mapType)
{
    switch (mapType)
    {
    case MAP_TYPE_TOWN:
    case MAP_TYPE_CITY:
    case MAP_TYPE_ROUTE:
    case MAP_TYPE_OCEAN_ROUTE:
        return TRUE;
    default:
        return FALSE;
    }
}

static const struct TilesetTimePalettes *FindTimePalettes(const struct Tileset *tileset)
{
    const struct TilesetTimePalettes *entry;

    if (tileset == NULL)
        return NULL;
    for (entry = gTilesetTimePalettes; entry->tileset != NULL; entry++)
    {
        if (entry->tileset == tileset)
            return entry;
    }
    return NULL;
}

static bool8 IsLayoutAuthored(const struct MapLayout *mapLayout)
{
    if (mapLayout == NULL)
        return FALSE;
    return FindTimePalettes(mapLayout->primaryTileset) != NULL
        || FindTimePalettes(mapLayout->secondaryTileset) != NULL;
}

static bool8 ShouldTintBg(void)
{
    return GetPeriod() != TIME_OF_DAY_DAY
        && IsOutdoorMapType(gMapHeader.mapType)
        && !IsLayoutAuthored(gMapHeader.mapLayout);
}

static bool8 ShouldTintObjects(void)
{
    return GetPeriod() != TIME_OF_DAY_DAY && IsOutdoorMapType(gMapHeader.mapType);
}

static inline u32 TintChannel(u32 value, u32 mul, s32 add)
{
    s32 result = (s32)((value * mul) >> 8) + add;
    if (result < 0)
        return 0;
    if (result > 31)
        return 31;
    return result;
}

static void TintColors(u16 *colors, u16 count, const struct DayNightTint *tint)
{
    u16 i;

    for (i = 0; i < count; i++)
    {
        u32 color = colors[i];
        u32 r = TintChannel(GET_R(color), tint->mulR, tint->addR);
        u32 g = TintChannel(GET_G(color), tint->mulG, tint->addG);
        u32 b = TintChannel(GET_B(color), tint->mulB, tint->addB);
        colors[i] = RGB(r, g, b);
    }
}

// Tints colours that were just loaded into both palette buffers.
static void TintLoadedColors(u16 offset, u16 numColors)
{
    const struct DayNightTint *tint = &sTints[GetPeriod()];

    TintColors(&gPlttBufferUnfaded[offset], numColors, tint);
    TintColors(&gPlttBufferFaded[offset], numColors, tint);
}

// Called from LoadTilesetPalette: which palette array to load for a tileset.
const u16 (*DayNight_GetTilesetPalettes(const struct Tileset *tileset))[16]
{
    const struct TilesetTimePalettes *entry = FindTimePalettes(tileset);

    if (entry != NULL)
    {
        switch (GetPeriod())
        {
        case TIME_OF_DAY_MORNING:
            if (entry->morning != NULL)
                return entry->morning;
            break;
        case TIME_OF_DAY_NIGHT:
            if (entry->night != NULL)
                return entry->night;
            break;
        }
    }
    return tileset->palettes;
}

// Called from LoadTilesetPalette right after the colours are loaded.
// offset and numColors are in colours, as LoadPalette's offset is.
void DayNight_TintBgPalettes(u16 offset, u16 numColors)
{
    if (ShouldTintBg())
        TintLoadedColors(offset, numColors);
}

void DayNight_OnPrimaryTilesetPaletteLoaded(const struct MapLayout *mapLayout)
{
    sPrimaryLoadedTileset = mapLayout->primaryTileset;
    sPrimaryLoadedPeriod = GetPeriod();
    sPrimaryLoadedTinted = ShouldTintBg();
}

// Walking across a map connection only reloads the secondary tileset's
// palettes. This says whether the primary ones must be reloaded too because
// the new map is tinted differently.
bool8 DayNight_PrimaryTilesetPaletteIsStale(const struct MapLayout *mapLayout)
{
    return sPrimaryLoadedTileset != mapLayout->primaryTileset
        || sPrimaryLoadedPeriod != GetPeriod()
        || sPrimaryLoadedTinted != ShouldTintBg();
}

void DayNight_ClearObjectPaletteRecords(void)
{
    memset(sObjectPalettes, 0, sizeof(sObjectPalettes));
}

// Called right after an object event or field effect palette is loaded
// into OBJ palette slot paletteSlot from src.
void DayNight_OnObjectPaletteLoaded(u8 paletteSlot, const u16 *src, u16 tag)
{
    if (paletteSlot >= ARRAY_COUNT(sObjectPalettes))
        return;

    sObjectPalettes[paletteSlot].src = src;
    sObjectPalettes[paletteSlot].tag = tag;
    if (ShouldTintObjects())
        TintLoadedColors(OBJ_PLTT_ID(paletteSlot), 16);
}

static bool8 IsObjectPaletteRecordValid(u8 slot)
{
    const struct ObjectPaletteRecord *record = &sObjectPalettes[slot];

    if (record->src == NULL)
        return FALSE;
    // A tracked slot must still belong to whatever was loaded there.
    return GetSpritePaletteTagByPaletteNum(slot) == record->tag;
}

static void ReloadPalettesForNewPeriod(bool8 bgAffected, bool8 objectsAffected)
{
    u8 i;

    if (bgAffected)
    {
        LoadMapTilesetPalettes(gMapHeader.mapLayout);
        for (i = 0; i < NUM_PALS_TOTAL; i++)
            ApplyWeatherColorMapToPal(i);
    }

    if (objectsAffected)
    {
        for (i = 0; i < ARRAY_COUNT(sObjectPalettes); i++)
        {
            if (!IsObjectPaletteRecordValid(i))
            {
                sObjectPalettes[i].src = NULL;
                continue;
            }
            LoadPalette(sObjectPalettes[i].src, OBJ_PLTT_ID(i), PLTT_SIZE_4BPP);
            DayNight_OnObjectPaletteLoaded(i, sObjectPalettes[i].src, sObjectPalettes[i].tag);
            UpdateSpritePaletteWithWeather(i);
        }
    }
}

// Called every frame from CB2_Overworld.
void DayNight_UpdateOverworld(void)
{
    u8 oldPeriod, newPeriod;
    bool8 oldBgTint, oldObjectTint, authored, bgAffected, objectsAffected;

    if (sClockCheckTimer < FRAMES_BETWEEN_CLOCK_CHECKS)
    {
        sClockCheckTimer++;
        return;
    }

    // Only change palettes while the player is walking around freely and
    // nothing is fading, so menus, scripts, warps and weather transitions
    // are never disturbed. Check again next frame otherwise.
    if (ArePlayerFieldControlsLocked()
     || gPaletteFade.active
     || gWeatherPtr->palProcessingState != WEATHER_PAL_STATE_IDLE)
        return;

    sClockCheckTimer = 0;
    oldPeriod = GetPeriod();
    newPeriod = GetTimeOfDay();
    if (newPeriod == oldPeriod)
        return;

    oldBgTint = ShouldTintBg();
    oldObjectTint = ShouldTintObjects();
    sPeriod = newPeriod;

    authored = IsLayoutAuthored(gMapHeader.mapLayout);
    bgAffected = authored || oldBgTint || ShouldTintBg();
    objectsAffected = oldObjectTint || ShouldTintObjects();
    ReloadPalettesForNewPeriod(bgAffected, objectsAffected);
}
