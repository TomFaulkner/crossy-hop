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
  - **train** — infrequent, fast train; crossing lights blink ~2s before it arrives
- **Scrolling** — hop past the middle of the board and the whole world slides
  down so the chick stays in the bottom third.
- **Game over** — traffic freezes for half a second, then a `GAME OVER` card
  shows the score. Restart with `Space` / `Enter` / `R` (or just hop again).
- **Pause** — `P` freezes traffic and the chick under a light veil; the board
  stays visible. Closing while paused still saves the mid-run state.

## Edge markers

Subtle accent lines mark the playable column edges (the drown boundary
where logs carry you off). They align with `drownColMin` / `drownColMax`
so you can see the death zone before you cross it.

## Controls

- Arrow keys or `W`/`A`/`S`/`D`: hop — up/down across the road, left/right along it
- `P`: pause / resume (light translucent veil; the board stays visible).
  Hops are ignored while paused; `Esc` still closes.
- `Space` / `Enter` / `R`: restart after a game over
- `Esc`: close — always, whatever the game is doing (never blocked by a save)
- Click **outside** the game card: close. Click the card: give it keyboard focus.
- Defaults (Crossy-like dimetric, not true isometric): **ANGLE 40°**, **ROT −26°** (user-matched). Fine-tune still live via hotkeys.
- `[` / `]`: nudge road **angle** (steepness) ±0.5° — HUD `ANGLE`
- `;` / `'`: nudge whole-scene **rotation** ±1° — HUD `ROT`
- `-` / `=`: grow / shrink the game window (default 1.05, max 1.20)

The overlay asks for keyboard focus **on demand** (`WlrKeyboardFocus.OnDemand`),
not exclusively: Omarchy's own shortcuts keep working while the game is open,
and keys Crossy Hop does not use are passed straight through.

## Crash debug log

While hunting random Quickshell crashes, every **2nd hop** (plus resets/deaths)
appends a line to `~/.local/state/crossy-hop/hop-debug.log` (or `$XDG_STATE_HOME/crossy-hop/`).
Also printed as `console.warn` in the shell log. Paste the last ~20 lines if it dies again. (desktop stays visible around it)
- `M`: mute toggle (reserved; no SFX yet)
- `Esc`: close

## Resume / Save

Game state saves automatically on close (mid-run) and persists `BEST` always.
On reopen, a mid-run save is restored instead of resetting. After game over,
the mid-run save is cleared but `BEST` carries over. Saves live at
`~/.local/state/crossy-hop/save.json`.

1.2.2 notes:

- The save is **plain JSON** written straight to disk by a `FileView`
  (atomic temp-file + rename) — no base64, no payload inside `sh -c`, so
  nothing is truncated and dismiss is never blocked by IO. Lanes serialise as
  a plain **array** of plain objects (a QML `var` map did not survive
  `JSON.stringify`, which made every reopen look "best-only" and reset the run).
- The load now starts **before** any reset: `open()` reads first and only
  builds a fresh world when there is no mid-run save. The sim is held
  (`loadHold`) for that read, so a stale world cannot drown the chick on the
  first frame.
- `console.warn` reports every save/load (`save ok`, `save failed`,
  `load: resumed …`, `load: best-only …`).

## Edge markers

Subtle accent lines mark the playable column edges (the drown boundary
where logs carry you off). They align with `drownColMin` / `drownColMax`
so you can see the death zone before you cross it.

## Install

```sh
omarchy plugin add https://github.com/TomFaulkner/crossy-hop.git --enable
```

Then click the chick in the bar, or:

```sh
omarchy-shell shell toggle io.github.tomfaulkner.crossy-hop
```

After QML edits: `omarchy restart shell`. Do not run `omarchy-refresh-shell`; that resets `shell.json`.

## Remove

```sh
omarchy plugin disable io.github.tomfaulkner.crossy-hop
omarchy plugin remove io.github.tomfaulkner.crossy-hop --yes
rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/crossy-hop"
```

## How it works

- `CrossyHop.qml` — the whole game: iso projection (ANGLE/ROT baked in and
  centre-fitted into the upright play card), lane generation, a 16 ms `Timer`
  driving `step(dt)`, Canvas lane painting (grass diamonds, road bands with
  dashed centre lines, water, rails + sleepers + crossing lights) and Canvas-only
  traffic (cars + trains + logs). Trains draw with their own vertical anchor
  (`trainYAnchor` 0.51 vs `carYAnchor` 0.70) so the long diagonal bake sits
  centred on the dark rail bed instead of riding the top rail. Auto-saves
  mid-run to `save.json`; resumes on reopen. Edge markers show the drown boundary; they (and the lane band
  edges) stroke with AA on, while sprite `drawImage` stays unsmoothed so the
  bakes stay crisp.
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
- Chicken skins + coin pickups.
- Persist `BEST` across sessions (saves now persist per-session best).
- Baked MagicaVoxel tree / log sprites instead of Canvas primitives (trains done).

## License

Plugin code is MIT — see [LICENSE](LICENSE).
Bacon MagicaVoxel models: MIT (Evan Bacon / Expo-Crossy-Road) with educational/fair-use
framing noted in his README — see [NOTICE.md](NOTICE.md).
Kenney assets remaining in-tree are CC0 — see [NOTICE.md](NOTICE.md).
