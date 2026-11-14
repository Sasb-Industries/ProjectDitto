# Project Ditto — design notes

Last updated 2026-11-13, from the setup session. The first group meeting should work through the "Open" list.

## What the game is

One Game Boy Advance game on the Emerald engine covering Hoenn, Kanto, the Sevii Islands and Johto. It is not "Emerald with extras": by 1.0 it has its own name and its own story. It is for the group, not for distribution.

## Decided

| Area | Decision |
|---|---|
| Engine | `pret/pokeemerald`, built with the modern compiler (`make modern`). |
| Roster | The 386 Gen 1–3 Pokémon only. No later generations and no Megas for 1.0. |
| Battle mechanics | Gen 3, plus the physical/special split, which we add ourselves. |
| Story shape | One authored route: start in Hoenn, the story carries you to the other regions and back. A choice of starting region may be revisited later. |
| Levels | Fixed per area, set along the story route. Early areas stay easy when revisited; late areas are hard if reached early, which acts as a soft wall. No runtime scaling. |
| Plots | Keep each region's original plot for now so nothing has to be rewritten to get started. A full rewrite comes later. |
| Kanto and Sevii maps | Ported 1:1 from `pret/pokefirered`, with FireRed's tilesets. The player character keeps the Emerald look. Retiling to Emerald's style is a later tooling job. |
| Johto maps | Ported 1:1. Source is CrystalDust's layouts if they are faithful to the originals; otherwise we write a converter from `pret/pokecrystal`. |
| Completeness | All 386 obtainable in one solo playthrough. Trade evolutions become item or level evolutions. All nine starters, both fossils of each pair and the event-only mythicals are obtainable in-game. |
| Old Emerald features | Battle Frontier, contests and the rest stay for now. Nothing is cut yet. |
| Map tooling | Porymap for humans, plus our own Python toolkit in `tools/ditto/` that AI agents drive. No custom map editor. |
| Repo | Public, a plain clone of pokeemerald with `pret` as `upstream`. No ROM files committed. |
| Workflow | No enforced process. Hand coding, Claude Code and hand editing are all fine. |

## Open — for the group

1. **Gyms and leagues.** Keep all 24 gyms or repurpose some? Three Elite Fours with the last as the true final test, or a different structure? What does the level curve look like across the whole route?
2. **Region travel.** How do you get between regions (ship, Magnet Train, a story event)? Can you return freely once a link opens?
3. **Sevii Islands.** Part of the story, or optional side content?
4. **Story.** The linking storyline, and eventually the rewrite of the regional plots. What happens to Aqua/Magma and Team Rocket?
5. **Fairy type.** In or out? Must be answered before 1.0.
6. **Starters and mythicals.** How the player earns the other eight starters, and Mew, Celebi, Jirachi and Deoxys: challenges, story rewards, hidden areas?
7. **Version exclusives and legendaries.** Where each one lives, and which new areas we add to house them.
8. **Link features.** Trading and link battles may not survive the changes. Do we care?
9. **First milestone.** Proposed: walk from Littleroot onto a boat, arrive in a ported Kanto town, fight one trainer there. It proves a second region can be wired in before anyone commits to story.
10. **Name.** What the game is called at 1.0.
11. **Who does what.** Code, maps, art, writing, music.

## To investigate (not decisions)

- Is CrystalDust's Johto faithful and complete, and what does its licence allow?
- Save-file space. The unmodified game uses 99% of its main save block, and three regions need many more story flags. We will need to free or expand it early; this is probably the first real engineering problem.
- Other systems that assume one region: the town map, Fly destinations, the Pokédex area screen.
- How the physical/special split is best added to vanilla pokeemerald.

## Status

- 2026-11-13: repo set up, unmodified Emerald builds and runs from source.
