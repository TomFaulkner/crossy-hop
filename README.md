# Crossy Hop

A tiny isometric Crossy Road-ish overlay demo as a native
[Omarchy](https://omarchy.org/) shell plugin.

It runs inside the long-lived `omarchy-shell` Quickshell process. Click the
bar icon to open a fullscreen overlay: grass, a two-lane road, cars crossing
in both directions, and an Evan Bacon MagicaVoxel chick you can hop with arrows / WASD.

This is a proof-of-concept, not a full game.

## Install

```sh
git clone https://github.com/TomFaulkner/crossy-hop.git
cd crossy-hop
ln -sfn "$PWD" ~/.config/omarchy/plugins/io.github.tomfaulkner.crossy-hop
omarchy plugin validate ~/.config/omarchy/plugins/io.github.tomfaulkner.crossy-hop
omarchy plugin enable io.github.tomfaulkner.crossy-hop --section right
```

Then click the chick in the bar, or:

```sh
omarchy-shell shell toggle io.github.tomfaulkner.crossy-hop
```

After QML edits: `omarchy restart shell`.

## Controls

- Arrow keys or `W`/`A`/`S`/`D`: hop — up/down across the road, left/right along it
Defaults (Crossy-like dimetric, not true isometric): **ANGLE 40°**, **ROT −26°** (user-matched). Fine-tune still live via hotkeys.

- `[` / `]`: nudge road **angle** (steepness) ±0.5° — HUD `ANGLE`
- `;` / `'`: nudge whole-scene **rotation** ±1° — HUD `ROT`
- `-` / `=`: shrink / grow the game window (desktop stays visible around it)
- `M`: mute toggle (reserved; no SFX yet)
- `Esc`: close

## Assets

- **Gameplay sprites (active):** `assets/baked/bacon/*` — upright dimetric PNGs baked from
  Evan Bacon MagicaVoxel OBJs (`tools/bake_bacon_blender.py`). Chicken NE; cars SE/NW
  (`orange`/`blue`/`green`). No horizontal flip at draw time.
- **Source models:** `assets/bacon/{chicken,orange_car,blue_car,green_car}/` — `0.obj` + `0.png`
  from [Expo-Crossy-Road](https://github.com/EvanBacon/Expo-Crossy-Road) (MIT), plus local
  `.mtl` stubs so Blender can bind textures. See `assets/bacon/NOTICE`.
- **Kenney (unused / fallback):** `assets/kenney/*.glb`, `assets/baked/{sedan,race,chick}-*.png`,
  `assets/sprites/*`. Re-bake with `tools/bake_blender.py` if needed. glTF expects
  `assets/kenney/Textures/colormap.png` as a **real copy** at bake time (gitignored;
  Omarchy forbids symlinks in plugins).
- **Re-bake Bacon sprites:**

```sh
# Blender 5.2+ on PATH
blender --background --python tools/bake_bacon_blender.py -- --size 512 --out-height 96
```

- **Re-bake Kenney (fallback):**

```sh
blender --background --python tools/bake_blender.py -- --size 512 --out-height 96
```

- **Legacy soft rasterizer** (often shards): `tools/bake_sprites.py`

## License

Plugin code is MIT — see [LICENSE](LICENSE).
Bacon MagicaVoxel models: MIT (Evan Bacon / Expo-Crossy-Road) with educational/fair-use
framing noted in his README — see [NOTICE.md](NOTICE.md).
Kenney assets remaining in-tree are CC0 — see [NOTICE.md](NOTICE.md).
