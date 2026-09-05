# Crossy Hop

A tiny isometric Crossy Road-ish overlay demo as a native
[Omarchy](https://omarchy.org/) shell plugin.

It runs inside the long-lived `omarchy-shell` Quickshell process. Click the
bar icon to open a fullscreen overlay: a grass field, a two-lane road, cars
crossing in both directions, and a Kenney chick you can hop around with the
arrow keys or WASD.

This is a proof-of-concept, not a full game.

## Install

From this checkout:

```sh
ln -sfn "$PWD" ~/.config/omarchy/plugins/io.github.tomfaulkner.crossy-hop
omarchy plugin validate ~/.config/omarchy/plugins/io.github.tomfaulkner.crossy-hop
omarchy plugin enable io.github.tomfaulkner.crossy-hop --section right
```

Then click the chick icon in the bar, or:

```sh
omarchy-shell shell toggle io.github.tomfaulkner.crossy-hop
```

## Controls

- Arrow keys or `W`/`A`/`S`/`D`: hop the chick one tile
- `M`: mute toggle (no sounds yet; reserved)
- `Esc`: close

## Validate

```sh
omarchy plugin validate .
```

Plugin QML is cached; after editing QML run `omarchy restart shell`.

## Assets

- `assets/kenney/previews/animal-chick.png`, `sedan.png`, `race.png`,
  `wheel-default.png`: CC0 by [Kenney](https://kenney.nl/)
- `assets/kenney/*.glb`: Kenney CC0 vehicle/chick models. The PNG previews are
  used here because Quickshell's Canvas is 2D; the GLBs and wheel GLBs are
  available for a future 3D spin.

## License

Plugin code is MIT. See [LICENSE](LICENSE). Kenney assets are CC0; see
[NOTICE.md](NOTICE.md).
