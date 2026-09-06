# Crossy Hop

A tiny isometric Crossy Road-ish overlay demo as a native
[Omarchy](https://omarchy.org/) shell plugin.

It runs inside the long-lived `omarchy-shell` Quickshell process. Click the
bar icon to open a fullscreen overlay: grass, a two-lane road, cars crossing
in both directions, and a Kenney chick you can hop with arrows / WASD.

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

- Arrow keys or `W`/`A`/`S`/`D`: hop one tile
Defaults (Crossy-like dimetric, not true isometric): **ANGLE 40°**, **ROT −20°**. Fine-tune window ~38–42° / −18–−22°.

- `[` / `]`: nudge road **angle** (steepness) ±0.5° — HUD `ANGLE`
- `;` / `'`: nudge whole-scene **rotation** ±1° — HUD `ROT`
- `-` / `=`: shrink / grow the game window (desktop stays visible around it)
- `M`: mute toggle (reserved; no SFX yet)
- `Esc`: close

## Assets

- **Gameplay sprites:** `assets/baked/*` — upright dimetric PNGs baked from Kenney GLBs with
  Blender 5.2 EEVEE (`tools/bake_blender.py`). Cars use SE/NW facings; chick uses NE.
  No horizontal flip at draw time.
- **Preview fallbacks:** `assets/sprites/*` — Kenney official preview PNGs (optional stand-ins).
- **Source GLBs:** `assets/kenney/*.glb` (car bodies already include wheel meshes;
  `wheel-default.glb` is also there for a future spin pass). The glTF importer expects
  `assets/kenney/Textures/colormap.png` is created as a **real copy** at bake time (gitignored; Omarchy forbids symlinks in plugins).
- **Re-bake (Blender, preferred):**

```sh
# Blender 5.2+ on PATH
blender --background --python tools/bake_blender.py -- --size 512 --out-height 96
```

- **Legacy soft rasterizer** (often shards): `tools/bake_sprites.py`

## License

Plugin code is MIT — see [LICENSE](LICENSE). Kenney assets are CC0 — see [NOTICE.md](NOTICE.md).
