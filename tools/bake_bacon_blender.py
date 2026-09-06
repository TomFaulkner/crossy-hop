#!/usr/bin/env python3
"""Bake Evan Bacon MagicaVoxel OBJs to upright Crossy-style dimetric PNG sprites.

Invoked as:
  blender --background --python tools/bake_bacon_blender.py -- [options]

Companion to tools/bake_blender.py (Kenney GLB path). Same ortho/dimetric camera
feel: elev 30°, view azim 45°, transparent film, SE + NW car facings, NE chick.
Default yaws (car E=75, W=255, chick NE=195, SW=15) match road/hop at ANGLE 40°.

OBJ sources live under assets/bacon/{chicken,orange_car,blue_car,green_car}/
with local .mtl binding map_Kd to 0.png (real files — never symlinks).
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector

SCRIPT = Path(__file__).resolve()
# Prefer repo tools/ neighbor; when copied to /tmp for Blender, fall back to known worktree.
_CANDIDATES = [
    SCRIPT.parents[1] if SCRIPT.name == "bake_bacon_blender.py" and (SCRIPT.parents[1] / "assets" / "bacon").is_dir() else None,
    Path("/home/box/Projects/crossy-hop/relm-poc"),
    Path.cwd(),
]
ROOT = next(c for c in _CANDIDATES if c is not None and (c / "assets" / "bacon").is_dir())
ASSETS = ROOT / "assets" / "bacon"
OUT = ROOT / "assets" / "baked" / "bacon"
CONTACT = Path("/workspace/crossy-prototype/renders/bake-bacon-check.png")

ELEV_DEG = 30.0
VIEW_AZIM_DEG = 45.0


def parse_args(argv: list[str] | None = None):
    if argv is None:
        argv = sys.argv
        if "--" in argv:
            argv = argv[argv.index("--") + 1 :]
        else:
            argv = []
    ap = argparse.ArgumentParser(description="Bake Bacon MagicaVoxel sprites with Blender")
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--out-height", type=int, default=96)
    ap.add_argument("--engine", choices=("BLENDER_EEVEE", "CYCLES", "EEVEE"), default="BLENDER_EEVEE")
    ap.add_argument("--elev", type=float, default=ELEV_DEG)
    ap.add_argument("--view-azim", type=float, default=VIEW_AZIM_DEG)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--sweep", action="store_true", help="Yaw sweep contact only (no final bake)")
    ap.add_argument("--no-downscale", action="store_true")
    # MagicaVoxel cars are long on Z; after OBJ Y-up→Blender Z-up, length ≈ ±Y,
    # nose toward Blender -Y. Tuned so projected nose matches road at ANGLE 40°
    # (SE ≈ screen +40°, NW ≈ -140°) under elev 30° / view-azim 45° bake camera.
    # Chick beak also -Y; NE hop ≈ screen -40°.
    ap.add_argument("--base-yaw", type=float, default=0.0, help="Legacy offset; prefer explicit --*-yaw")
    ap.add_argument("--car-e-yaw", type=float, default=75.0, help="SE traffic (dir=+1), nose down-right")
    ap.add_argument("--car-w-yaw", type=float, default=255.0, help="NW traffic (dir=-1), nose up-left")
    ap.add_argument("--chick-ne-yaw", type=float, default=195.0, help="Hop-forward NE (up-right)")
    ap.add_argument("--chick-sw-yaw", type=float, default=15.0, help="Opposite SW facing")
    return ap.parse_args(argv)


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_obj(path: Path):
    """Import Wavefront OBJ (Y-up MagicaVoxel) and parent under BakeRoot."""
    before = set(bpy.data.objects)
    # Blender 4+/5: wm.obj_import; older: import_scene.obj
    kwargs = dict(
        filepath=str(path),
        forward_axis="NEGATIVE_Z",
        up_axis="Y",
    )
    try:
        bpy.ops.wm.obj_import(**kwargs)
    except TypeError:
        # Older signature without axis kwargs or different op
        try:
            bpy.ops.wm.obj_import(filepath=str(path))
        except Exception:
            bpy.ops.import_scene.obj(filepath=str(path), axis_forward="-Z", axis_up="Y")
    imported = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new("BakeRoot", None)
    bpy.context.scene.collection.objects.link(root)
    for o in imported:
        if o.parent is None:
            o.parent = root
    # Ensure texture is bound even if MTL parse was flaky
    ensure_png_texture(path.with_name("0.png"), imported)
    return root, imported


def ensure_png_texture(png: Path, objects):
    if not png.exists():
        print(f"WARN missing texture {png}")
        return
    img = bpy.data.images.load(str(png), check_existing=True)
    img.colorspace_settings.name = "sRGB"
    for o in objects:
        if o.type != "MESH":
            continue
        mats = list(o.data.materials) if o.data.materials else []
        if not mats:
            mat = bpy.data.materials.new(name=f"Bacon_{o.name}")
            mat.use_nodes = True
            o.data.materials.append(mat)
            mats = [mat]
        for mat in mats:
            if mat is None:
                continue
            mat.use_nodes = True
            nt = mat.node_tree
            nodes, links = nt.nodes, nt.links
            # Find or create Image Texture
            tex = next((n for n in nodes if n.type == "TEX_IMAGE"), None)
            if tex is None:
                tex = nodes.new("ShaderNodeTexImage")
                tex.location = (-300, 200)
            tex.image = img
            tex.interpolation = "Closest"
            principled = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
            if principled is not None:
                bc = principled.inputs.get("Base Color")
                if bc is not None and not bc.is_linked:
                    links.new(tex.outputs["Color"], bc)


def scene_bbox(objects) -> tuple[Vector, Vector]:
    pts = []
    for o in objects:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            pts.append(o.matrix_world @ Vector(c))
    if not pts:
        return Vector((0, 0, 0)), Vector((0, 0, 0))
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    return Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))


def setup_camera(elev_deg: float, view_azim_deg: float, ortho_scale: float, target: Vector):
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("BakeCam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = ortho_scale
    cam = bpy.data.objects.new("BakeCam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    elev = math.radians(elev_deg)
    azim = math.radians(view_azim_deg)
    cam.rotation_euler = (math.radians(90.0) - elev, 0.0, azim)
    dist = 20.0
    direction = cam.rotation_euler.to_matrix() @ Vector((0.0, 0.0, -1.0))
    cam.location = target - direction * dist
    return cam


def setup_lights(target: Vector):
    sun_data = bpy.data.lights.new("BakeSun", type="SUN")
    sun_data.energy = 2.5
    sun_data.angle = math.radians(5.0)
    sun = bpy.data.objects.new("BakeSun", sun_data)
    bpy.context.scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(50), math.radians(15), math.radians(35))
    sun.location = target + Vector((4, -3, 8))

    area_data = bpy.data.lights.new("BakeFill", type="AREA")
    area_data.energy = 40.0
    area_data.size = 6.0
    fill = bpy.data.objects.new("BakeFill", area_data)
    bpy.context.scene.collection.objects.link(fill)
    fill.location = target + Vector((-3, 4, 5))
    fill.rotation_euler = (math.radians(60), 0, math.radians(-40))


def setup_render(size: int, engine: str, samples: int, out_path: Path):
    scene = bpy.context.scene
    eng = engine
    if eng == "EEVEE":
        eng = "BLENDER_EEVEE"
    available = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    if eng not in available:
        if "BLENDER_EEVEE_NEXT" in available:
            eng = "BLENDER_EEVEE_NEXT"
        elif "BLENDER_EEVEE" in available:
            eng = "BLENDER_EEVEE"
        else:
            eng = "CYCLES"
    scene.render.engine = eng
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.filepath = str(out_path)

    if eng == "CYCLES":
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        try:
            scene.cycles.device = "CPU"
        except Exception:
            pass
    else:
        eevee = getattr(scene, "eevee", None)
        if eevee is not None:
            if hasattr(eevee, "taa_render_samples"):
                eevee.taa_render_samples = max(16, samples // 2)
            if hasattr(eevee, "samples"):
                eevee.samples = max(16, samples // 2)


def make_shadeless():
    for mat in bpy.data.materials:
        if hasattr(mat, "blend_method"):
            mat.blend_method = "OPAQUE"
        if hasattr(mat, "surface_render_method"):
            try:
                mat.surface_render_method = "DITHERED"
            except Exception:
                pass
        if hasattr(mat, "use_transparency_overlap"):
            mat.use_transparency_overlap = False
        if not getattr(mat, "use_nodes", False):
            continue
        nt = mat.node_tree
        nodes = nt.nodes
        links = nt.links
        principled = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
        out = next((n for n in nodes if n.type == "OUTPUT_MATERIAL"), None)
        if principled is None or out is None:
            continue
        bc = principled.inputs.get("Base Color")
        for link in list(out.inputs["Surface"].links):
            links.remove(link)
        emis = nodes.new("ShaderNodeEmission")
        emis.location = (principled.location.x + 40, principled.location.y - 60)
        emis.inputs["Strength"].default_value = 1.15
        if bc is not None and bc.is_linked:
            links.new(bc.links[0].from_socket, emis.inputs["Color"])
        elif bc is not None:
            emis.inputs["Color"].default_value = bc.default_value
        links.new(emis.outputs["Emission"], out.inputs["Surface"])
        for n in nodes:
            if n.type == "TEX_IMAGE" and n.image is not None:
                n.image.colorspace_settings.name = "sRGB"
                n.interpolation = "Closest"


def setup_color_management():
    scene = bpy.context.scene
    try:
        scene.display_settings.display_device = "sRGB"
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
    except Exception as e:
        print("color mgmt warn", e)
    scene.render.use_compositing = False
    scene.render.use_sequencer = False


def fit_ortho_scale(objects, elev_deg: float, view_azim_deg: float, margin: float = 1.12) -> tuple[float, Vector]:
    from mathutils import Euler
    mn, mx = scene_bbox(objects)
    center = (mn + mx) * 0.5
    elev = math.radians(elev_deg)
    azim = math.radians(view_azim_deg)
    R = Euler((math.radians(90.0) - elev, 0.0, azim), "XYZ").to_matrix().inverted()
    pts = []
    for o in objects:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            pts.append(o.matrix_world @ Vector(c))
    if not pts:
        return 4.0, center
    xs, ys = [], []
    for p in pts:
        local = R @ (p - center)
        xs.append(local.x)
        ys.append(local.y)
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    scale = max(w, h) * margin
    return max(scale, 0.5), center


def crop_and_downscale(path: Path, out_height: int):
    img = bpy.data.images.load(str(path))
    w, h = img.size
    pixels = list(img.pixels)
    min_x, min_y, max_x, max_y = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            a = pixels[(y * w + x) * 4 + 3]
            if a > 0.02:
                if x < min_x:
                    min_x = x
                if x > max_x:
                    max_x = x
                if y < min_y:
                    min_y = y
                if y > max_y:
                    max_y = y
    if max_x < min_x:
        bpy.data.images.remove(img)
        return

    pad = max(2, int(0.04 * max(max_x - min_x + 1, max_y - min_y + 1)))
    min_x = max(0, min_x - pad)
    min_y = max(0, min_y - pad)
    max_x = min(w - 1, max_x + pad)
    max_y = min(h - 1, max_y + pad)
    cw = max_x - min_x + 1
    ch = max_y - min_y + 1

    cropped = bpy.data.images.new("cropped", cw, ch, alpha=True)
    cpix = [0.0] * (cw * ch * 4)
    for y in range(ch):
        for x in range(cw):
            sx = min_x + x
            sy = min_y + y
            si = (sy * w + sx) * 4
            di = (y * cw + x) * 4
            cpix[di : di + 4] = pixels[si : si + 4]
    cropped.pixels = cpix
    new_h = out_height
    new_w = max(1, int(round(cw * (new_h / ch))))
    cropped.scale(new_w, new_h)
    cropped.filepath_raw = str(path)
    cropped.file_format = "PNG"
    cropped.save()
    bpy.data.images.remove(img)
    bpy.data.images.remove(cropped)


def render_one(
    obj_path: Path,
    yaw_deg: float,
    out_path: Path,
    size: int,
    elev: float,
    view_azim: float,
    engine: str,
    samples: int,
    out_height: int | None,
):
    clear_scene()
    root, imported = import_obj(obj_path)
    root.rotation_euler = (0.0, 0.0, math.radians(yaw_deg))
    bpy.context.view_layer.update()
    make_shadeless()

    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    ortho, target = fit_ortho_scale(meshes, elev, view_azim)
    setup_camera(elev, view_azim, ortho, target)
    setup_lights(target)
    setup_render(size, engine, samples, out_path)
    setup_color_management()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)

    if out_height:
        crop_and_downscale(out_path, out_height)
    print(f"wrote {out_path}")


def write_contact_sheet(cells: list[tuple[str, Path]], out: Path, cell: int = 200):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        import json
        import subprocess
        vpy = Path("/workspace/crossy-prototype/.venv/bin/python")
        if vpy.exists():
            payload = {"out": str(out), "cell": cell, "cells": [[a, str(b)] for a, b in cells]}
            tf = Path("/tmp/bake_bacon_contact_payload.json")
            tf.write_text(json.dumps(payload))
            helper = Path("/tmp/bake_bacon_contact_helper.py")
            helper.write_text(
                "import json, math\nfrom pathlib import Path\nfrom PIL import Image, ImageDraw, ImageFont\n"
                "p=json.loads(Path('/tmp/bake_bacon_contact_payload.json').read_text())\n"
                "cells=p['cells']; out=Path(p['out']); cell=p['cell']\n"
                "cols=4; cell_w=cell; cell_h=int(cell*0.85)\n"
                "rows=max(1, math.ceil(len(cells)/cols))\n"
                "sheet=Image.new('RGBA',(cols*cell_w, rows*cell_h),(40,40,48,255))\n"
                "draw=ImageDraw.Draw(sheet); font=ImageFont.load_default()\n"
                "for i,(label,path) in enumerate(cells):\n"
                "  path=Path(path)\n"
                "  if not path.exists():\n"
                "    continue\n"
                "  im=Image.open(path).convert('RGBA')\n"
                "  col,row=i%cols,i//cols\n"
                "  cx=col*cell_w+cell_w//2; cy=row*cell_h+cell_h//2+10\n"
                "  max_h=cell_h-40; max_w=cell_w-20\n"
                "  r=min(max_w/max(im.width,1), max_h/max(im.height,1))\n"
                "  disp=im.resize((max(1,int(im.width*r)), max(1,int(im.height*r))), Image.Resampling.NEAREST)\n"
                "  sheet.paste(disp,(cx-disp.width//2, cy-disp.height//2), disp)\n"
                "  draw.text((col*cell_w+8, row*cell_h+4), label, fill=(255,220,80,255), font=font)\n"
                "out.parent.mkdir(parents=True, exist_ok=True)\n"
                "sheet.save(out); print('wrote contact sheet', out)\n"
            )
            subprocess.check_call([str(vpy), str(helper)])
            return
        print("WARN: no PIL; skipping contact sheet")
        return

    cols = 4
    rows = max(1, math.ceil(len(cells) / cols))
    cell_w, cell_h = cell, int(cell * 0.85)
    sheet = Image.new("RGBA", (cols * cell_w, rows * cell_h), (40, 40, 48, 255))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    for i, (label, path) in enumerate(cells):
        if not path.exists():
            continue
        im = Image.open(path).convert("RGBA")
        col, row = i % cols, i // cols
        cx = col * cell_w + cell_w // 2
        cy = row * cell_h + cell_h // 2 + 10
        max_h = cell_h - 40
        max_w = cell_w - 20
        r = min(max_w / max(im.width, 1), max_h / max(im.height, 1))
        disp = im.resize(
            (max(1, int(im.width * r)), max(1, int(im.height * r))),
            Image.Resampling.NEAREST,
        )
        sheet.paste(disp, (cx - disp.width // 2, cy - disp.height // 2), disp)
        draw.text((col * cell_w + 8, row * cell_h + 4), label, fill=(255, 220, 80, 255), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(f"wrote contact sheet {out}")


def main():
    args = parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    CONTACT.parent.mkdir(parents=True, exist_ok=True)

    base = args.base_yaw
    # Explicit defaults (75/255/195/15) align to ANGLE 40° road/hop; base only shifts if non-zero.
    car_e = args.car_e_yaw + base
    car_w = args.car_w_yaw + base
    chick_ne = args.chick_ne_yaw + base
    chick_sw = args.chick_sw_yaw + base

    down_h = None if args.no_downscale else args.out_height

    orange = ASSETS / "orange_car" / "0.obj"
    blue = ASSETS / "blue_car" / "0.obj"
    green = ASSETS / "green_car" / "0.obj"
    chicken = ASSETS / "chicken" / "0.obj"

    if args.sweep:
        tmp = CONTACT.parent / "yaw-sweep-bacon"
        tmp.mkdir(parents=True, exist_ok=True)
        cells = []
        for yaw in range(0, 360, 45):
            p = tmp / f"orange-yaw{yaw:03d}.png"
            render_one(orange, float(yaw), p, args.size, args.elev, args.view_azim, args.engine, args.samples, 128)
            cells.append((f"orange yaw {yaw}", p))
        for yaw in (0, 90, 180, 270):
            p = tmp / f"chicken-yaw{yaw:03d}.png"
            render_one(chicken, float(yaw), p, args.size, args.elev, args.view_azim, args.engine, args.samples, 128)
            cells.append((f"chick yaw {yaw}", p))
        write_contact_sheet(cells, CONTACT.parent / "bacon-yaw-sweep.png", cell=180)
        print("SWEEP_DONE")
        print(f"default car_e={car_e} car_w={car_w} chick_ne={chick_ne} chick_sw={chick_sw} base={base}")
        return

    jobs = [
        ("orange-e", orange, car_e),
        ("orange-w", orange, car_w),
        ("blue-e", blue, car_e),
        ("blue-w", blue, car_w),
        ("green-e", green, car_e),
        ("green-w", green, car_w),
        ("chicken-ne", chicken, chick_ne),
        ("chicken-sw", chicken, chick_sw),
    ]
    baked_paths = {}
    for name, obj, yaw in jobs:
        out = OUT / f"{name}.png"
        render_one(obj, yaw, out, args.size, args.elev, args.view_azim, args.engine, args.samples, down_h)
        baked_paths[name] = out

    cells = [
        ("orange-e", baked_paths["orange-e"]),
        ("orange-w", baked_paths["orange-w"]),
        ("blue-e", baked_paths["blue-e"]),
        ("blue-w", baked_paths["blue-w"]),
        ("green-e", baked_paths["green-e"]),
        ("green-w", baked_paths["green-w"]),
        ("chicken-ne", baked_paths["chicken-ne"]),
        ("chicken-sw", baked_paths["chicken-sw"]),
    ]
    venv_site = Path("/workspace/crossy-prototype/.venv/lib")
    if venv_site.exists():
        for p in venv_site.glob("python*/site-packages"):
            sp = str(p)
            if sp not in sys.path:
                sys.path.insert(0, sp)
    write_contact_sheet(cells, CONTACT)

    print("YAWS", {"base": base, "car_e": car_e, "car_w": car_w, "chick_ne": chick_ne, "chick_sw": chick_sw})
    print("DONE")


if __name__ == "__main__":
    main()
