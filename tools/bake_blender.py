#!/usr/bin/env python3
"""Bake Kenney GLBs to upright Crossy-style dimetric PNG sprites via Blender.

Invoked as:
  blender --background --python tools/bake_blender.py -- [options]

World +Y (glTF) / +Z (Blender after import) stays up — orthographic camera with
yaw-only object rotation so verticals remain screen-vertical. Cars already
include wheels; we never reparent. Texture path: bake copies colormap into assets/kenney/Textures/ (no symlinks).
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector

# ---------------------------------------------------------------------------
# Paths — script lives in <repo>/tools/
# ---------------------------------------------------------------------------
SCRIPT = Path(__file__).resolve()
# When run via blender --python, __file__ is the script path.
ROOT = SCRIPT.parents[1]
ASSETS = ROOT / "assets" / "kenney"
OUT = ROOT / "assets" / "baked"
CONTACT = Path("/workspace/crossy-prototype/renders/bake-blender-check.png")

# Dimetric elevation above horizon. ~30° reads like Kenney previews while
# keeping a gentle Crossy foreshortening (road ~22.6° in QML is separate).
ELEV_DEG = 30.0
# View azimuth in Blender (Z-up): camera sits this many degrees from +Y toward +X
# before object yaw. 45° → classic 3/4.
VIEW_AZIM_DEG = 45.0


def parse_args(argv: list[str] | None = None):
    # Blender forwards args after "--"
    if argv is None:
        argv = sys.argv
        if "--" in argv:
            argv = argv[argv.index("--") + 1 :]
        else:
            argv = []
    ap = argparse.ArgumentParser(description="Bake Crossy Hop sprites with Blender")
    ap.add_argument("--size", type=int, default=512, help="Render resolution")
    ap.add_argument("--out-height", type=int, default=96, help="Nearest downscale height")
    ap.add_argument("--engine", choices=("BLENDER_EEVEE", "CYCLES", "EEVEE"), default="BLENDER_EEVEE")
    ap.add_argument("--elev", type=float, default=ELEV_DEG)
    ap.add_argument("--view-azim", type=float, default=VIEW_AZIM_DEG)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--sweep", action="store_true", help="Yaw sweep contact only (no final bake)")
    ap.add_argument("--no-downscale", action="store_true")
    # Yaws: object rotation around Blender Z (up). 0 = model default facing.
    # After glTF import, sedan front wheels sit at -Y → nose ≈ −Y.
    # With VIEW_AZIM=45°, object yaw that points nose screen-down-left (SW preview):
    #   nose direction after yaw R_z: (-sin(yaw), -cos(yaw)) in XY for default nose -Y
    # Empirically tuned vs Kenney preview; override via flags.
    ap.add_argument("--sedan-sw-yaw", type=float, default=0.0, help="Yaw matching official SW preview")
    ap.add_argument("--car-e-yaw", type=float, default=None, help="SE traffic yaw (default: sw+90)")
    ap.add_argument("--car-w-yaw", type=float, default=None, help="NW traffic yaw (default: sw+270)")
    ap.add_argument("--chick-ne-yaw", type=float, default=None)
    ap.add_argument("--chick-sw-yaw", type=float, default=None)
    return ap.parse_args(argv)


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def ensure_colormap_for_gltf():
    """glTF looks for Textures/colormap.png. Copy (never symlink — Omarchy forbids
    symlinks inside plugin folders). Textures/ is gitignored."""
    import shutil
    tex_dir = ASSETS / "Textures"
    tex_dir.mkdir(parents=True, exist_ok=True)
    dest = tex_dir / "colormap.png"
    target = ASSETS / "colormap.png"
    if target.exists() and (not dest.exists() or dest.is_symlink() or dest.stat().st_mtime < target.stat().st_mtime):
        if dest.is_symlink() or dest.exists():
            dest.unlink()
        shutil.copy2(target, dest)


def import_glb(path: Path):
    ensure_colormap_for_gltf()
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [o for o in bpy.data.objects if o not in before]
    # Parent loose meshes under a root empty at origin for easy yaw.
    root = bpy.data.objects.new("BakeRoot", None)
    bpy.context.scene.collection.objects.link(root)
    for o in imported:
        if o.parent is None:
            o.parent = root
    return root, imported


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
    # Camera looks down its local -Z; +Y local is up.
    # rotation XYZ: (90° - elev) pitches down; Z = azim orbits around world up.
    # This keeps world +Z projecting to screen vertical.
    cam.rotation_euler = (math.radians(90.0) - elev, 0.0, azim)
    dist = 20.0
    # Place camera along its local -Z away from target.
    direction = cam.rotation_euler.to_matrix() @ Vector((0.0, 0.0, -1.0))
    cam.location = target - direction * dist
    return cam


def setup_lights(target: Vector):
    # Soft key (sun) + fill (area) similar to Kenney's clean look.
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
    # Blender 5 uses BLENDER_EEVEE_NEXT or BLENDER_EEVEE — detect.
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
        # EEVEE
        eevee = getattr(scene, "eevee", None)
        if eevee is not None:
            if hasattr(eevee, "taa_render_samples"):
                eevee.taa_render_samples = max(16, samples // 2)
            if hasattr(eevee, "samples"):
                eevee.samples = max(16, samples // 2)



def make_shadeless():
    """Replace Principled with Emission (flat Kenney look); force opaque (no hashed holes)."""
    for mat in bpy.data.materials:
        # Blender 5 EEVEE: HASHED/DITHERED alpha punches holes in atlas textures
        if hasattr(mat, "blend_method"):
            mat.blend_method = "OPAQUE"
        if hasattr(mat, "surface_render_method"):
            try:
                mat.surface_render_method = "DITHERED"  # kept but alpha unused
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
        # Clear existing surface links
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
                n.interpolation = "Closest"  # pixel palette look


def setup_color_management():
    scene = bpy.context.scene
    # Avoid AgX/Filmic crushing Kenney palette saturation
    try:
        scene.display_settings.display_device = "sRGB"
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
    except Exception as e:
        print("color mgmt warn", e)
    # Transparent film already set; disable sequencers
    scene.render.use_compositing = False
    scene.render.use_sequencer = False


def fit_ortho_scale(objects, elev_deg: float, view_azim_deg: float, margin: float = 1.12) -> tuple[float, Vector]:
    """Compute ortho_scale + look-at so the model fills the frame after camera setup."""
    from mathutils import Euler
    mn, mx = scene_bbox(objects)
    center = (mn + mx) * 0.5
    elev = math.radians(elev_deg)
    azim = math.radians(view_azim_deg)
    # Build view matrix: world → camera (rotation only about center)
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


def nearest_downscale(path: Path, out_height: int) -> Path:
    """Downscale with nearest-neighbor via Blender's image API (no PIL needed)."""
    img = bpy.data.images.load(str(path))
    w, h = img.size
    if h <= 0:
        return path
    new_h = out_height
    new_w = max(1, int(round(w * (new_h / h))))
    img.scale(new_w, new_h)
    # Re-save over same path
    img.filepath_raw = str(path)
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    return path


def render_one(
    glb: Path,
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
    root, imported = import_glb(glb)
    root.rotation_euler = (0.0, 0.0, math.radians(yaw_deg))
    # Update matrices
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
        # Crop transparent padding then downscale — use temporary full res crop via pixels
        crop_and_downscale(out_path, out_height)
    print(f"wrote {out_path}")


def crop_and_downscale(path: Path, out_height: int):
    """Alpha-crop then nearest-neighbor resize using bpy images."""
    img = bpy.data.images.load(str(path))
    w, h = img.size
    pixels = list(img.pixels)  # RGBA float 0..1, row-major bottom-up in Blender
    # Blender stores pixels bottom-up
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

    cw = max_x - min_x + 1
    ch = max_y - min_y + 1
    # Add small pad
    pad = max(2, int(0.04 * max(cw, ch)))
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


def write_contact_sheet(cells: list[tuple[str, Path]], out: Path, cell: int = 200):
    """Compose a labeled contact sheet with Pillow if available, else external venv."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        import subprocess
        vpy = Path("/workspace/crossy-prototype/.venv/bin/python")
        if vpy.exists():
            # Serialize jobs for external composer
            import json, tempfile
            payload = {"out": str(out), "cell": cell, "cells": [[a, str(b)] for a, b in cells]}
            tf = Path("/tmp/bake_contact_payload.json")
            tf.write_text(json.dumps(payload))
            helper = Path("/tmp/bake_contact_helper.py")
            helper.write_text(
                "import json\nfrom pathlib import Path\nfrom PIL import Image, ImageDraw, ImageFont\n"
                "import math\n"
                "p=json.loads(Path('/tmp/bake_contact_payload.json').read_text())\n"
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
        _contact_bpy(cells, out, cell)
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
        draw.text(
            (col * cell_w + 8, row * cell_h + 4),
            label,
            fill=(255, 220, 80, 255),
            font=font,
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(f"wrote contact sheet {out}")


def _contact_bpy(cells, out, cell):
    # Minimal fallback without PIL
    print("WARN: PIL unavailable inside Blender; writing simple sheet via first images only")
    out.parent.mkdir(parents=True, exist_ok=True)
    # Just copy first existing as placeholder note
    for _, p in cells:
        if p.exists():
            import shutil
            shutil.copy(p, out)
            print(f"wrote fallback contact {out}")
            return


def main():
    args = parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    CONTACT.parent.mkdir(parents=True, exist_ok=True)

    # Default yaws relative to SW preview match.
    sw = args.sedan_sw_yaw
    car_e = args.car_e_yaw if args.car_e_yaw is not None else (sw + 90.0)  # SE = nose down-right
    car_w = args.car_w_yaw if args.car_w_yaw is not None else (sw + 270.0)  # NW = nose up-left
    # Chick: beak +Z glTF → after import Blender_Y = -glTF_Z → beak at -Y (same as car nose).
    # NE hop = up-right on screen. From SW preview yaw, NE is opposite = sw+180.
    chick_ne = args.chick_ne_yaw if args.chick_ne_yaw is not None else (sw + 180.0)
    chick_sw = args.chick_sw_yaw if args.chick_sw_yaw is not None else sw

    down_h = None if args.no_downscale else args.out_height

    if args.sweep:
        # Render sedan at several yaws + official preview for picking.
        tmp = CONTACT.parent / "yaw-sweep-blender"
        tmp.mkdir(parents=True, exist_ok=True)
        cells = []
        preview = ASSETS / "previews" / "sedan.png"
        for yaw in range(0, 360, 45):
            p = tmp / f"sedan-yaw{yaw:03d}.png"
            render_one(
                ASSETS / "sedan.glb",
                float(yaw),
                p,
                args.size,
                args.elev,
                args.view_azim,
                args.engine,
                args.samples,
                128,
            )
            cells.append((f"yaw {yaw}", p))
        cells.append(("official SW preview", preview))
        write_contact_sheet(cells, CONTACT.parent / "blender-yaw-sweep.png", cell=180)
        print("SWEEP_DONE")
        print(f"default car_e={car_e} car_w={car_w} chick_ne={chick_ne} chick_sw={chick_sw} sw={sw}")
        return

    jobs = [
        ("sedan-e", ASSETS / "sedan.glb", car_e),
        ("sedan-w", ASSETS / "sedan.glb", car_w),
        ("race-e", ASSETS / "race.glb", car_e),
        ("race-w", ASSETS / "race.glb", car_w),
        ("chick-ne", ASSETS / "animal-chick.glb", chick_ne),
        ("chick-sw", ASSETS / "animal-chick.glb", chick_sw),
    ]
    baked_paths = {}
    for name, glb, yaw in jobs:
        out = OUT / f"{name}.png"
        render_one(
            glb,
            yaw,
            out,
            args.size,
            args.elev,
            args.view_azim,
            args.engine,
            args.samples,
            down_h,
        )
        baked_paths[name] = out

    cells = [
        ("sedan-e (blender)", baked_paths["sedan-e"]),
        ("sedan-w (blender)", baked_paths["sedan-w"]),
        ("race-e (blender)", baked_paths["race-e"]),
        ("official preview", ASSETS / "previews" / "sedan.png"),
        ("race-w (blender)", baked_paths["race-w"]),
        ("chick-ne (blender)", baked_paths["chick-ne"]),
        ("chick-sw (blender)", baked_paths["chick-sw"]),
    ]
    # Prefer Pillow from a known venv if bpy's python lacks it.
    venv_site = Path("/workspace/crossy-prototype/.venv/lib")
    if venv_site.exists():
        for p in venv_site.glob("python*/site-packages"):
            sp = str(p)
            if sp not in sys.path:
                sys.path.insert(0, sp)
    write_contact_sheet(cells, CONTACT)

    print("YAWS", {"sw": sw, "car_e": car_e, "car_w": car_w, "chick_ne": chick_ne, "chick_sw": chick_sw})
    print("DONE")


if __name__ == "__main__":
    main()
