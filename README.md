# Project Ditto

A Game Boy Advance game that puts Hoenn, Kanto (with the Sevii Islands) and Johto into one adventure, with all 386 Gen 1–3 Pokémon obtainable in a single playthrough.

- What we have decided and what is still open: [docs/ditto/design.md](docs/ditto/design.md)
- Working in the repo, including with Claude Code: [CLAUDE.md](CLAUDE.md)

## Build and play

Install devkitARM and libpng first; [INSTALL.md](INSTALL.md) has per-platform instructions. Then:

```bash
make modern -j$(sysctl -n hw.ncpu)
```

That produces `pokeemerald_modern.gba`, which runs in any GBA emulator such as [mGBA](https://mgba.io/). On Linux, use `nproc` in place of `sysctl -n hw.ncpu`.

No ROM files are stored in this repository.

## Credits

Project Ditto starts from the [pret/pokeemerald](https://github.com/pret/pokeemerald) decompilation of Pokémon Emerald, at commit `731ad5bfd` (1 October 2026). The engine code here is the work of the pret contributors; the full history of that work is in their repository.
