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
| Level curve and badges | One planned level curve across the whole route. Badges matter all game long, not only inside their own region. |
| Field moves | No HM slaves. If the player has the HM in the bag and the badge it needs, and a party Pokémon can learn the move, they can use it in the field (for example, Scyther cuts the tree, and it is Scyther the player sees doing it). HMs can still be taught as ordinary moves. |
| Day/night | Throughout the game, in every region. Some Pokémon appear only at certain times in certain areas. Hotels let the player sleep through the night. |
| Johto systems | Everything Johto-specific comes along: headbutt trees, Apricorns and Kurt's balls, and the rest. |
| TMs | Single-use, as in Gen 3, but every TM can be bought again and again somewhere. Which shops sell which TMs is decided later. |
| Move relearner and tutors | Yes. |
| Exp. Share | As in Gen 3: a held item that shares with one Pokémon. |
| Shiny rate | 1/4096 (Gen 3 is 1/8192). |
| Levels | Fixed per area, set along the story route. Early areas stay easy when revisited; late areas are hard if reached early, which acts as a soft wall. No runtime scaling. |
| Plots | Keep each region's storyline. Change them only where needed for one region to lead into the next, and keep those changes small, but a game that flows well comes first. |
| Sevii Islands | In 1.0. |
| Kanto and Sevii maps | Ported 1:1 from `pret/pokefirered`, with FireRed's tilesets. The player character keeps the Emerald look. Retiling to Emerald's style is a later tooling job. |
| Johto maps | Ported 1:1. Source is CrystalDust's layouts if they are faithful to the originals; otherwise we write a converter from `pret/pokecrystal`. |
| Completeness | All 386 obtainable in one solo playthrough. Trade evolutions become item or level evolutions. All nine starters, both fossils of each pair and the event-only mythicals are obtainable in-game. |
| Old Emerald features | Battle Frontier, contests and the rest stay for now. Nothing is cut yet. |
| Map tooling | Porymap for humans, plus our own Python toolkit in `tools/ditto/` that AI agents drive. No custom map editor. |
| Repo | Public. Started from a snapshot of pokeemerald without its history; we do not merge upstream updates. No ROM files committed. |
| Workflow | No enforced process. Hand coding, Claude Code and hand editing are all fine. |

## Open — for the group

1. **Gyms and leagues.** Keep all 24 gyms or repurpose some? Three Elite Fours with the last as the true final test, or a different structure? What does the level curve look like across the whole route?
2. **Region links.** Where each new route runs and what blocks it. Can you return freely once a link opens? Are ships or the Magnet Train also used?
3. **Sevii Islands.** On the main story route, or optional?
4. **Story.** The linking storyline and the changes each regional plot needs to fit it. What happens to Aqua/Magma and Team Rocket?
5. **Fairy type.** In or out? Must be answered before 1.0.
6. **Starters and mythicals.** How the player earns the other eight starters, and Mew, Celebi, Jirachi and Deoxys: challenges, story rewards, hidden areas?
7. **Version exclusives and legendaries.** Where each one lives, and which new areas we add to house them.
8. **Link features.** Trading and link battles may not survive the changes. Do we care?
9. **First milestone.** Proposed: walk from Littleroot onto a boat, arrive in a ported Kanto town, fight one trainer there. It proves a second region can be wired in before anyone commits to story.
10. **Name.** What the game is called at 1.0.
11. **Who does what.** Code, maps, art, writing, music.
12. **Region order.** Confirm the working order above, and which league is the final test.
13. **Changing natures and IVs.** Whether, and how. Needs its own discussion.
14. **Physical/special details.** Moves that need a call, such as Hidden Power and Curse.
15. **TM shops.** Where each TM is sold.

## To investigate (not decisions)

- Is CrystalDust's Johto faithful and complete, and what does its licence allow?
- Save-file space. The unmodified game uses 99% of its main save block, and three regions need many more story flags. We will need to free or expand it early; this is probably the first real engineering problem.
- Other systems that assume one region: the town map, Fly destinations, the Pokédex area screen.
- How the physical/special split is best added to vanilla pokeemerald.

## Status

- 2026-11-13: repo set up, unmodified Emerald builds and runs from source.
- 2026-11-13: Kanto mainland imported from FireRed (256 maps, 51 tilesets) as empty, walkable maps. A sailor in Littleroot Town and one in Pallet Town carry you between the regions. This is the proposed first milestone minus the trainer battle. Kanto still needs NPCs, scripts, trainers, wild encounters, tile animations and a town map.
