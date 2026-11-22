# Project Ditto — design notes

Last updated 2026-11-21, with the first round of 1.0 decisions. The group should keep working through the "Open" list.

## What the game is

One Game Boy Advance game on the Emerald engine covering Hoenn, Kanto, the Sevii Islands and Johto. It is not "Emerald with extras": by 1.0 it has its own name and its own story. It is for the group, not for distribution.

1.0 means a game the group can pick up and play: playable from start to credits, all 386 obtainable, and no softlocks. It doesn't have to be perfect.

## Decided

| Area | Decision |
|---|---|
| Engine | `pret/pokeemerald`, built with the modern compiler (`make modern`). |
| Roster | The 386 Gen 1–3 Pokémon only. No later generations and no Megas for 1.0. |
| Battle mechanics | Gen 3, plus the modern physical/special split (each move has its own category, as from Gen 4 on), which we add ourselves. |
| Story shape | One authored route: start in Hoenn, the story carries you to the other regions and back. A choice of starting region may be revisited later. |
| Region links | Regions are joined by new routes, each blocked until the player has done something (as Waterfall gated the Johto–Kanto link in Gen 2). The gates keep the player on the story route. |
| Region order | Working assumption, to be confirmed: start in Hoenn → Kanto → Johto → return to finish Hoenn. |
| Finale | Hoenn's last gym is the last gym of the game. The Hoenn Elite Four is the final, hardest challenge, with the rival as part of it. Where the story leaves Hoenn the first time is decided with the story. |
| Level curve and badges | One planned level curve across the whole route. Badges matter all game long, not only inside their own region. |
| Field moves | No HM slaves. If the player has the HM in the bag and the badge it needs, and a party Pokémon can learn the move, they can use it in the field (for example, Scyther cuts the tree, and it is Scyther the player sees doing it). HMs can still be taught as ordinary moves. |
| Day/night | Throughout the game, in every region. Some Pokémon appear only at certain times in certain areas. Hotels let the player sleep through the night. |
| Johto systems | Everything Johto-specific comes along: headbutt trees, Apricorns and Kurt's balls, and the rest. |
| TMs | Single-use, as in Gen 3, but every TM can be bought again and again somewhere. Which shops sell which TMs is decided later. |
| Move relearner and tutors | Yes. |
| Exp. Share | As in Gen 3: a held item that shares with one Pokémon. |
| Shiny rate | 1/4096 (Gen 3 is 1/8192). |
| Trade evolutions | Use Emerald Legacy's replacements: Kadabra and Haunter evolve at level 42, Graveler and Machoke at 38; Slowking, Steelix, Politoed, Kingdra, Scizor, Porygon2 and Gorebyss evolve by using their trade item like a stone. Any trade evolution not listed (such as Huntail) follows the same item-as-stone pattern; check against Legacy's full docs. |
| Pokédex | One National Pokédex of all 386. No regional dexes. |
| PC boxes | 16 (Emerald has 14). Needs one more 4 KB save block per save copy; how to free it is open item 18. |
| Egg incubator | An incubator upstairs in Pokémon Centers holds eggs and hatches them, so eggs don't take party slots. |
| Quality of life | Fast saving, fast text and battle text; run indoors; offer another Repel when one runs out; show the move name when a TM or HM is received; use healing items repeatedly from the bag; bigger bag with sorting, overflow to the PC; HM moves can be forgotten freely; switch Mach/Acro Bike with one button; summary screen shows IVs and EVs and colours stats by nature; Kurt makes balls instantly. |
| Cleared obstacles | Smashed rocks and cut trees stay gone. |
| Renewable resources | Berry trees don't die out; berries, evolution stones, shards and other evolution items can be bought or farmed again and again. |
| Bug fixes | Turn on pokeemerald's built-in `BUGFIX` switch (`include/config.h`). |
| Trainer AI | Smarter: fix Gen 3's AI bugs (Protect and recovery spam and others) and improve switching, as Emerald Legacy does. |
| Gym rematches | None in 1.0. |
| Fairy type | In. Which Fairy moves to add, and the rest of the Gen 6 type changes, are open items 19 and 20. |
| Version exclusives | None. Every Pokémon from every version is available in this game. Kanto's encounter tables merge FireRed and LeafGreen. |
| Rivals | Each region's rival stays in their own region. |
| Fly | Works only within the region you are in. |
| Johto music | Port Gold/Silver's music. |
| Difficulty | One difficulty for everyone. No difficulty modes. |
| Day/night colours | Johto uses Crystal's own morning, day and night palettes. Hoenn and Kanto get a computed morning and night tint outdoors until someone paints night palettes. Periods follow Crystal: morning 4:00–9:59, day 10:00–17:59, night 18:00–3:59. |
| Whirlpool and Headbutt | HM09 Whirlpool is added and follows the HM rules. Headbutt works on headbutt trees if a party Pokémon knows it, using Crystal's headbutt encounter tables. |
| Johto map names | Every Johto place shows its own name on entry, from a separate name table. Met locations are grouped by town or route, because only 39 map-section slots are free. |
| Johto music, for now | Gold/Silver's songs converted automatically in their original Game Boy sound. GBA-style arrangements can replace them song by song. |
| Weather and battle tweaks | In, following Emerald Legacy (e.g. hail and sandstorm boosts). Weather is added to the other regions where it fits. |
| Levels | Fixed per area, set along the story route. Early areas stay easy when revisited; late areas are hard if reached early, which acts as a soft wall. No runtime scaling. |
| Plots | Keep each region's storyline. Change them only where needed for one region to lead into the next, and keep those changes small, but a game that flows well comes first. |
| Sevii Islands | In 1.0. |
| Kanto and Sevii maps | Ported 1:1 from `pret/pokefirered`, with FireRed's tilesets. The player character keeps the Emerald look. Retiling to Emerald's style is a later tooling job. |
| Johto maps | Converted 1:1 from `pret/pokecrystal` by `tools/ditto/import_crystal.py`, with Crystal's own tiles for now. GBA-style Johto tilesets come later, ideally CrystalDust's if its author agrees. |
| Completeness | All 386 obtainable in one solo playthrough. Trade evolutions become item or level evolutions. All nine starters, both fossils of each pair and the event-only mythicals are obtainable in-game. |
| Old Emerald features | Battle Frontier, contests and the rest stay for now. Nothing is cut yet. |
| Map tooling | Porymap for humans, plus our own Python toolkit in `tools/ditto/` that AI agents drive. No custom map editor. |
| Repo | Public. Started from a snapshot of pokeemerald without its history; we do not merge upstream updates. No ROM files committed. |
| Workflow | No enforced process. Hand coding, Claude Code and hand editing are all fine. |

## Open — for the group

1. **Gyms and leagues.** Keep all 24 gyms or repurpose some? What happens to the Kanto and Johto Elite Fours, given Hoenn's is the finale? What does the level curve look like across the whole route?
2. **Region links.** Where each new route runs and what blocks it. Can you return freely once a link opens? Are ships or the Magnet Train also used?
3. **Sevii Islands.** On the main story route, or optional?
4. **Story.** The linking storyline and the changes each regional plot needs to fit it. What happens to Aqua/Magma and Team Rocket?
5. **Starters and mythicals.** How the player earns the other eight starters, and Mew, Celebi, Jirachi and Deoxys: challenges, story rewards, hidden areas?
6. **Legendaries and former version exclusives.** Where each one lives, and which new areas we add to house them.
7. **Link features.** Trading and link battles may not survive the changes. Do we care?
8. **First milestone.** Proposed: walk from Littleroot onto a boat, arrive in a ported Kanto town, fight one trainer there. It proves a second region can be wired in before anyone commits to story.
9. **Name.** What the game is called at 1.0.
10. **Who does what.** Code, maps, art, writing, music.
11. **Region order.** Confirm the working order above, and the point in Hoenn's story where the player first leaves for Kanto.
12. **Changing natures and IVs.** Whether, and how. Needs its own discussion. (Showing them is decided.)
13. **Physical/special details.** Moves that need a call, such as Hidden Power and Curse.
14. **TM shops.** Where each TM is sold.
15. **Badge level cap.** Should badges raise a level cap, to back up the fixed level curve?
16. **Changing the clock.** Can players set the time freely, or only skip the night at hotels?
17. **Incubator details.** How many eggs it holds, and how they hatch (steps walked, time, or both).
18. **Room for 16 boxes.** Free the two save blocks used by Trainer Hill and recorded battles (cuts those saves), store boxed Pokémon more compactly (more work, cuts nothing), or drop the backup save copy (last resort).
19. **Fairy moves.** Gen 3 has only three moves that later became Fairy (Charm, Sweet Kiss, Moonlight), none of them attacks. Fairy Pokémon need attacking moves (Moonblast, Dazzling Gleam, Play Rough, Fairy Wind, Draining Kiss), which would be the first later-gen moves we add.
20. **The rest of Gen 6's type changes.** Steel no longer resisting Ghost and Dark, and the Gen 6 retypings (Clefairy, Jigglypuff, Togepi, Snubbull and Marill lines, Mr. Mime, Ralts line, Mawile).

## To investigate (not decisions)

- Johto tilesets and music. CrystalDust (Sierraffinity/CrystalDust, built on pokeemerald like us) has GBA-style tilesets and about 20 Johto tracks, but covers only New Bark to Goldenrod, has no licence and no commits since December 2022. Someone should ask its author whether we can use its tilesets and music.
- Save-file space. The unmodified game uses 99% of its main save block, and three regions need many more story flags. We will need to free or expand it early; this is probably the first real engineering problem.
- Other systems that assume one region: the town map, Fly destinations, the Pokédex area screen.
- How the physical/special split is best added to vanilla pokeemerald.

## Status

- 2026-11-13: repo set up, unmodified Emerald builds and runs from source.
- 2026-11-13: Kanto mainland imported from FireRed (256 maps, 51 tilesets) as empty, walkable maps. A sailor in Littleroot Town and one in Pallet Town carry you between the regions. This is the proposed first milestone minus the trainer battle. Kanto still needs NPCs, scripts, trainers, wild encounters, tile animations and a town map.
- 2026-11-21: Johto imported from pokecrystal (230 maps, 34 tilesets) as empty, walkable maps with Crystal's own graphics. A sailor in Pallet Town and one in New Bark Town carry you between Kanto and Johto.
- 2026-11-22: Johto gets tile animations, Crystal's morning/day/night palettes, map names on entry, cut trees, HM09 Whirlpool and Headbutt trees. Day/night runs everywhere (tinted in Hoenn and Kanto). Gold/Silver music converted in its original Game Boy sound.
