# Crossy Hop

An isometric Crossy Road-ish overlay game as a native
[Omarchy](https://omarchy.org/) shell plugin.

It runs inside the long-lived `omarchy-shell` Quickshell process. Click the bar
icon to open a fullscreen overlay: an endless isometric world of grass, roads,
rivers and railroads. Hop the Evan Bacon MagicaVoxel chick forward with
arrows / WASD — every new row you reach is a point. Cars squash you, water
drowns you, trains splat you.

## Gameplay loop

- **Score** — one point per row of forward progress (furthest row reached, so
  you cannot farm points by hopping back and forth). `BEST` keeps the best run
  of the session.
- **Endless lanes** — a sliding window of ~9 rows is generated ahead of you as
  you advance. Lane types:
  - **grass** — safe; some cells hold trees / boulders that block your hop
  - **road** — Bacon cars (orange / blue / green) in both directions; contact = death
  - **river** — you drown unless you land on a log; logs carry you sideways
  - **railroad** — infrequent, fast train; crossing lights blink ~2s before it arrives
- **Scrolling** — hop past the middle of the board and the whole world slides
  down so the chick stays in the bottom third.
- **Game over** — traffic freezes for half a second, then a `GAME OVER` card
  shows the score. Restart with `Space` / `Enter` / `R` (or just hop again).

## Controls

- Arrow keys or `W`/`A`/`S`/`D`: hop — up/down across the road, left/right along it
- `Space` / `Enter` / `R`: restart after a game over
- Defaults (Crossy-like dimetric, not true isometric): **ANGLE 40°**, **ROT −26°** (user-matched). Fine-tune still live via hotkeys.
- `[` / `]`: nudge road **angle** (steepness) ±0.5° — HUD `ANGLE`
- `;` / `'`: nudge whole-scene **rotation** ±1° — HUD `ROT`
- `-` / `=`: shrink / grow the game window

## Crash debug log

While hunting random Quickshell crashes, every **2nd hop** (plus resets/deaths)
appends a line to `~/.local/state/crossy-hop/hop-debug.log` (or `$XDG_STATE_HOME/crossy-hop/`).
Also printed as `console.warn` in the shell log. Paste the last ~20 lines if it dies again. (desktop stays visible around it)
- `M`: mute toggle (reserved; no SFX yet)
- `Esc`: close

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

## How it works

- `CrossyHop.qml` — the whole game: iso projection (ANGLE/ROT baked in and
  centre-fitted into the upright play card), lane generation, a 16 ms `Timer`
  driving `step(dt)`, Canvas lane painting (grass diamonds, road bands with
  dashed centre lines, water, rails + sleepers + crossing lights) and QML
  `Repeater`s for sprites (Bacon cars / trains) and Canvas props (trees,
  boulders) and logs.
- World coordinates: absolute row `ar` grows as you advance;
  `screenRow(ar) = rows - (ar - winAnchor)`. `winAnchor` is a real number so a
  forward hop can animate the world scroll.
- Lane generation keeps hazards separated by at least one safe grass row and
  never walls off a whole row with obstacles.

## Assets

- **Gameplay sprites (active):** `assets/baked/bacon/*` — upright dimetric PNGs baked from
  Evan Bacon MagicaVoxel OBJs (`tools/bake_bacon_blender.py`, `tools/bake_bacon_train.py`).
  Chicken NE/SW; cars + trains SE/NW
  (`orange`/`blue`/`green`). No horizontal flip at draw time.
- **Drawn in-engine (no third-party art):** trees, boulders, logs,
  water, rails and crossing lights are Canvas / `Rectangle` primitives tinted
  from the Omarchy theme.
- **Source models:** `assets/bacon/{chicken,orange_car,blue_car,green_car,train/{front,middle,back}}/` — `0.obj` + `0.png`
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

## TODO

- Sound effects (the `M` mute toggle is wired but silent), maybe a hop blip and
  a squish.
- Eagle / edge-of-world pressure when you dawdle (Crossy's anti-camping rule).
- Chicken skins + coin pickups.
- Persist `BEST` across sessions.
- Baked MagicaVoxel tree / log sprites instead of Canvas primitives (trains done).

## License

Plugin code is MIT — see [LICENSE](LICENSE).
Bacon MagicaVoxel models: MIT (Evan Bacon / Expo-Crossy-Road) with educational/fair-use
framing noted in his README — see [NOTICE.md](NOTICE.md).
Kenney assets remaining in-tree are CC0 — see [NOTICE.md](NOTICE.md).
