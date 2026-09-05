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
- `M`: mute toggle (reserved; no SFX yet)
- `Esc`: close

## Assets

- **Gameplay sprites (current):** Kenney official `assets/kenney/previews/*.png` (CC0).
  Opposite traffic mirrors the preview with `xScale: -1`.
- **GLBs:** `assets/kenney/*.glb` including separate `wheel-default.glb` (for future spinning wheels).
- **Bake experiment:** `tools/bake_sprites.py` renders GLBs → `assets/baked/`. The software
  rasterizer is not production-quality yet (wrong camera/UVs); previews are what the PoC uses
  until the bake looks right.

```sh
python3 -m venv .venv && .venv/bin/pip install trimesh pillow numpy
.venv/bin/python tools/bake_sprites.py --size 320
```

## License

Plugin code is MIT — see [LICENSE](LICENSE). Kenney assets are CC0 — see [NOTICE.md](NOTICE.md).
