#!/usr/bin/env python3
"""Bake Evan Bacon MagicaVoxel train (front+middle+back) to e/w PNG sprites.

Reuses patterns from tools/bake_bacon_blender.py. Composes pieces like
Expo-Crossy-Road Train.withSize(1): front @0, middle @depth(front), back @accum.

Train OBJs are long on X (cars are long on Z→Y after import). We rotate the
composed root +90° around Z so length aligns with car convention (±Y), then
apply the same car e/w yaws (75 / 255).

Invoked as:
  blender --background --python /tmp/bake_bacon_train.py -- [options]
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path("/home/box/Projects/crossy-hop/relm-poc")
ASSETS = ROOT / "assets" / "bacon" / "train"
OUT = ROOT / "assets" / "baked" / "bacon"
CONTACT = Path("/workspace/crossy-prototype/renders/bake-bacon-train-check.png")

ELEV_DEG = 30.0
VIEW_AZIM_DEG = 45.0


def parse_args(argv=None):
    if argv is None:
        argv = sys.argv
        if "--" in argv:
            argv = argv[argv.index("--") + 1 :]
        else:
            argv = []
    ap = argparse.ArgumentParser(description="Bake Bacon train sprites")
    ap.add_argument("--size", type=int, default=768)
    ap.add_argument("--out-height", type=int, default=96)
    ap.add_argument("--engine", choices=("BLENDER_EEVEE", "CYCLES", "EEVEE"), default="BLENDER_EEVEE")
    ap.add_argument("--elev", type=float, default=ELEV_DEG)
    ap.add_argument("--view-azim", type=float, default=VIEW_AZIM_DEG)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--no-downscale", action="store_true")
    ap.add_argument("--car-e-yaw", type=float, default=75.0)
    ap.add_argument("--car-w-yaw", type=float, default=255.0)
    ap.add_argument("--axis-yaw", type=float, default=90.0,
                    help="Pre-yaw to map train length X→Y (try 90 or -90)")
    ap.add_argument("--middles", type=int, default=1)
    return ap.parse_args(argv)


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_obj(path: Path):
    before = set(bpy.data.objects)
    kwargs = dict(filepath=str(path), forward_axis="NEGATIVE_Z", up_axis="Y")
    try:
        bpy.ops.wm.obj_import(**kwargs)
    except TypeError:
        try:
            bpy.ops.wm.obj_import(filepath=str(path))
        except Exception:
            bpy.ops.import_scene.obj(filepath=str(path), axis_forward="-Z", axis_up="Y")
    imported = [o for o in bpy.data.objects if o not in before]
    ensure_png_texture(path.with_name("0.png"), imported)
    return imported


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


def scene_bbox(objects):
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


def depth_x(objects) -> float:
    mn, mx = scene_bbox(objects)
    return mx.x - mn.x


def setup_camera(elev_deg, view_azim_deg, ortho_scale, target):
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


def setup_lights(target):
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


def setup_render(size, engine, samples, out_path):
    scene = bpy.context.scene
    eng = "BLENDER_EEVEE" if engine == "EEVEE" else engine
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


def fit_ortho_scale(objects, elev_deg, view_azim_deg, margin=1.12):
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


def compose_train(middles: int = 1):
    """Bacon withSize: front @0, middles along +X, back at end. Parent under BakeRoot."""
    root = bpy.data.objects.new("BakeRoot", None)
    bpy.context.scene.collection.objects.link(root)
    all_meshes = []

    front_objs = import_obj(ASSETS / "front" / "0.obj")
    for o in front_objs:
        if o.parent is None:
            o.parent = root
    all_meshes.extend(front_objs)
    bpy.context.view_layer.update()
    offset = depth_x(front_objs)
    print(f"front depth_x={offset:.3f}")

    for i in range(middles):
        mid_objs = import_obj(ASSETS / "middle" / "0.obj")
        mid_empty = bpy.data.objects.new(f"Middle_{i}", None)
        bpy.context.scene.collection.objects.link(mid_empty)
        mid_empty.parent = root
        mid_empty.location.x = offset
        for o in mid_objs:
            if o.parent is None:
                o.parent = mid_empty
        all_meshes.extend(mid_objs)
        bpy.context.view_layer.update()
        d = depth_x(mid_objs)
        print(f"middle[{i}] depth_x={d:.3f} at offset={offset:.3f}")
        offset += d

    back_objs = import_obj(ASSETS / "back" / "0.obj")
    back_empty = bpy.data.objects.new("Back", None)
    bpy.context.scene.collection.objects.link(back_empty)
    back_empty.parent = root
    back_empty.location.x = offset
    for o in back_objs:
        if o.parent is None:
            o.parent = back_empty
    all_meshes.extend(back_objs)
    bpy.context.view_layer.update()
    print(f"back at offset={offset:.3f}, total_x≈{offset + depth_x(back_objs):.3f}")
    return root, all_meshes


def render_train(yaw_deg, axis_yaw, out_path, size, elev, view_azim, engine, samples, out_height, middles):
    clear_scene()
    root, imported = compose_train(middles)
    # Map train length (X) onto car length axis (Y), then apply car-facing yaw.
    root.rotation_euler = (0.0, 0.0, math.radians(axis_yaw + yaw_deg))
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
    print(f"wrote {out_path} yaw={yaw_deg} axis={axis_yaw}")


def write_contact_sheet(cells, out: Path, cell: int = 280):
    import json
    import subprocess
    vpy = Path("/workspace/crossy-prototype/.venv/bin/python")
    payload = {"out": str(out), "cell": cell, "cells": [[a, str(b)] for a, b in cells]}
    tf = Path("/tmp/bake_train_contact_payload.json")
    tf.write_text(json.dumps(payload))
    helper = Path("/tmp/bake_train_contact_helper.py")
    helper.write_text(
        "import json, math\nfrom pathlib import Path\nfrom PIL import Image, ImageDraw, ImageFont\n"
        "p=json.loads(Path('/tmp/bake_train_contact_payload.json').read_text())\n"
        "cells=p['cells']; out=Path(p['out']); cell=p['cell']\n"
        "cols=min(4, max(1,len(cells))); cell_w=cell; cell_h=int(cell*0.55)\n"
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
        "  max_h=cell_h-36; max_w=cell_w-16\n"
        "  r=min(max_w/max(im.width,1), max_h/max(im.height,1))\n"
        "  disp=im.resize((max(1,int(im.width*r)), max(1,int(im.height*r))), Image.Resampling.NEAREST)\n"
        "  sheet.paste(disp,(cx-disp.width//2, cy-disp.height//2), disp)\n"
        "  draw.text((col*cell_w+8, row*cell_h+4), label, fill=(255,220,80,255), font=font)\n"
        "out.parent.mkdir(parents=True, exist_ok=True)\n"
        "sheet.save(out); print('wrote contact sheet', out)\n"
    )
    if vpy.exists():
        subprocess.check_call([str(vpy), str(helper)])
    else:
        subprocess.check_call([sys.executable, str(helper)])


def main():
    args = parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    CONTACT.parent.mkdir(parents=True, exist_ok=True)
    down_h = None if args.no_downscale else args.out_height
    tmp = CONTACT.parent / "yaw-sweep-train"
    tmp.mkdir(parents=True, exist_ok=True)

    if args.sweep:
        cells = []
        # Compare axis ±90 with car yaws and a few extras
        for axis in (90.0, -90.0):
            for yaw in (0, 75, 255, 90, 180):
                p = tmp / f"axis{int(axis)}-yaw{yaw:03d}.png"
                render_train(float(yaw), axis, p, args.size, args.elev, args.view_azim,
                             args.engine, args.samples, 128, args.middles)
                cells.append((f"ax{int(axis)} y{yaw}", p))
        # Include existing car refs for facing comparison
        for name in ("orange-e", "orange-w"):
            src = OUT / f"{name}.png"
            if src.exists():
                cells.append((name, src))
        write_contact_sheet(cells, CONTACT.parent / "bacon-train-yaw-sweep.png", cell=260)
        print("SWEEP_DONE")
        return

    jobs = [
        ("train-e", args.car_e_yaw),
        ("train-w", args.car_w_yaw),
    ]
    baked = {}
    for name, yaw in jobs:
        out = OUT / f"{name}.png"
        render_train(yaw, args.axis_yaw, out, args.size, args.elev, args.view_azim,
                     args.engine, args.samples, down_h, args.middles)
        baked[name] = out

    cells = [
        ("train-e", baked["train-e"]),
        ("train-w", baked["train-w"]),
        ("orange-e", OUT / "orange-e.png"),
        ("orange-w", OUT / "orange-w.png"),
    ]
    write_contact_sheet(cells, CONTACT, cell=320)
    print("DONE", {k: str(v) for k, v in baked.items()}, "axis_yaw", args.axis_yaw)


if __name__ == "__main__":
    main()
