Crossy Hop for Omarchy
======================

Evan Bacon MagicaVoxel models (gameplay)
----------------------------------------

Active gameplay sprites are baked from MagicaVoxel OBJ/PNG models by Evan Bacon:

  https://github.com/EvanBacon/Expo-Crossy-Road

Copied into this tree as:

  - assets/bacon/chicken/0.obj + 0.png
  - assets/bacon/orange_car/0.obj + 0.png
  - assets/bacon/blue_car/0.obj + 0.png
  - assets/bacon/green_car/0.obj + 0.png
  - assets/bacon/train/{front,middle,back}/0.obj + 0.png

Copyright (c) 2016-present Evan Bacon. Source code of that project is MIT.
His README states the project is strictly for educational purposes and uses
Crossy Road–style work under a fair use / educational purpose framing; he is
not associated with Hipster Whale.

Local `.mtl` files under `assets/bacon/*/` were added here so Blender can bind
`map_Kd` to `0.png` (upstream loads the texture in application code). Do not
add symlinks under the plugin tree — Omarchy rejects them.

Baked outputs: `assets/baked/bacon/*.png` via `tools/bake_bacon_blender.py`
(cars/chicken) and `tools/bake_bacon_train.py` (composed front+middle+back train).

Kenney (CC0; unused / fallback)
-------------------------------

This plugin still ships Kenney assets (https://kenney.nl/) as unused fallbacks:

  - assets/kenney/previews/animal-chick.png
  - assets/kenney/previews/sedan.png
  - assets/kenney/previews/race.png
  - assets/kenney/previews/wheel-default.png
  - assets/kenney/*.glb
  - assets/baked/{sedan,race,chick}-*.png
  - assets/sprites/*

These assets are released under the Creative Commons Zero (CC0) 1.0 Universal
license. You may copy, modify, distribute, and use them, even for commercial
purposes, without asking permission.

The vehicle GLBs include separate wheel models (`wheel-default.glb`) so the
wheels can be animated independently in a future 3D version.

Engine-drawn art
----------------

Trees, boulders, logs, water bands, rails, sleepers and crossing lights are
drawn with Qt Quick Canvas / Rectangle primitives tinted from the Omarchy
theme. They are original to this plugin (MIT). Trains use baked Bacon MagicaVoxel
sprites (see above). No Crossy Road or Hipster Whale assets are used.

Plugin code
-----------

The Omarchy overlay, bar widget, and JavaScript game logic were written for
this plugin and are licensed under the MIT license. See LICENSE.
