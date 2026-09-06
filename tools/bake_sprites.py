#!/usr/bin/env python3
"""Bake Kenney GLBs to Crossy-style upright dimetric PNG sprites.

Loads each GLB as-is (cars already include wheel meshes — never strip or
re-parent wheel-default). Camera is yaw-only around +Y with a Y-preserving
dimetric projection so verticals stay screen-vertical (no pitch tip).

Projection after yaw:
  sx = x - z
  sy = -y * height_scale + (x + z) * ground_scale
  depth = -(x + z)   # camera from (-X, +Y, -Z); larger depth = closer

ground_scale ≈ tileH/tileW (~0.40 → ~21.8°) to match QML road angle.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import trimesh

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "kenney"
OUT = ROOT / "assets" / "baked"
# Match QML tileH/tileW (38/96 ≈ 0.396 → ~21.6°)
GROUND_SCALE = 0.40
HEIGHT_SCALE = 1.15


def yaw_mat(deg: float) -> np.ndarray:
    r = np.radians(deg)
    c, s = np.cos(r), np.sin(r)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float64)


def load_parts(path: Path) -> list[tuple]:
    scene = trimesh.load(str(path), force="scene")
    parts = []
    for node_name in scene.graph.nodes_geometry:
        transform, geom_name = scene.graph[node_name]
        mesh = scene.geometry[geom_name].copy()
        mesh.apply_transform(transform)
        tex = None
        try:
            mat = mesh.visual.material
            if getattr(mat, "baseColorTexture", None) is not None:
                tex = np.array(mat.baseColorTexture.convert("RGBA"))
        except Exception:
            pass
        if tex is None:
            color = [180, 180, 180, 255]
            try:
                color = list(mesh.visual.material.main_color)
            except Exception:
                pass
            tex = np.zeros((2, 2, 4), dtype=np.uint8)
            tex[:, :] = color
        if getattr(mesh.visual, "uv", None) is None:
            mesh.visual.uv = np.zeros((len(mesh.vertices), 2), dtype=np.float64)
        parts.append((mesh, tex))
    return parts


def render(
    parts: list[tuple],
    size: int,
    yaw: float,
    ground_scale: float = GROUND_SCALE,
    height_scale: float = HEIGHT_SCALE,
) -> Image.Image:
    R = yaw_mat(yaw)
    cam = np.array([-1.0, 1.5, -1.0], dtype=np.float64)
    light = np.array([-0.35, 0.9, -0.3], dtype=np.float64)
    light /= np.linalg.norm(light)

    transformed = []
    for mesh, tex in parts:
        v = mesh.vertices @ R.T
        n = mesh.face_normals @ R.T
        transformed.append((mesh, tex, v, n))

    allv = np.concatenate([v for _, _, v, _ in transformed])
    x, y, z = allv[:, 0], allv[:, 1], allv[:, 2]
    sx_all = x - z
    sy_all = -y * height_scale + (x + z) * ground_scale
    minx, maxx = float(sx_all.min()), float(sx_all.max())
    miny, maxy = float(sy_all.min()), float(sy_all.max())
    pad = 0.07 * max(maxx - minx, maxy - miny, 1e-6)
    minx -= pad
    maxx += pad
    miny -= pad
    maxy += pad
    scale = min(size / (maxx - minx), size / (maxy - miny)) * 0.90
    ox = size / 2 - (minx + maxx) / 2 * scale
    oy = size / 2 - (miny + maxy) / 2 * scale

    img = np.zeros((size, size, 4), dtype=np.uint8)
    zbuf = np.full((size, size), -np.inf, dtype=np.float32)

    for mesh, tex, v, nrms in transformed:
        uvs = mesh.visual.uv
        th, tw = tex.shape[:2]
        x, y, z = v[:, 0], v[:, 1], v[:, 2]
        xs = (x - z) * scale + ox
        ys = (-y * height_scale + (x + z) * ground_scale) * scale + oy
        # Camera from (-X,+Y,-Z): closer points have smaller (x+z)
        depth = -(x + z)
        centers = (v[mesh.faces[:, 0]] + v[mesh.faces[:, 1]] + v[mesh.faces[:, 2]]) / 3.0

        for fi, (a, b, c) in enumerate(mesh.faces):
            # Keep faces that point toward the camera
            if float(nrms[fi].dot(cam - centers[fi])) <= 0.0:
                continue
            x0, y0, z0 = xs[a], ys[a], depth[a]
            x1, y1, z1 = xs[b], ys[b], depth[b]
            x2, y2, z2 = xs[c], ys[c], depth[c]
            # Screen-space backface cull
            if (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0) <= 0:
                continue

            minxi = max(0, int(np.floor(min(x0, x1, x2))))
            maxxi = min(size - 1, int(np.ceil(max(x0, x1, x2))))
            minyi = max(0, int(np.floor(min(y0, y1, y2))))
            maxyi = min(size - 1, int(np.ceil(max(y0, y1, y2))))
            if minxi > maxxi or minyi > maxyi:
                continue
            denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(denom) < 1e-8:
                continue
            yy, xx = np.mgrid[minyi : maxyi + 1, minxi : maxxi + 1]
            w0 = ((y1 - y2) * (xx - x2) + (x2 - x1) * (yy - y2)) / denom
            w1 = ((y2 - y0) * (xx - x2) + (x0 - x2) * (yy - y0)) / denom
            w2 = 1.0 - w0 - w1
            mask = (w0 >= -1e-5) & (w1 >= -1e-5) & (w2 >= -1e-5)
            if not mask.any():
                continue
            z = w0 * z0 + w1 * z1 + w2 * z2
            update = mask & (z > zbuf[yy, xx])
            if not update.any():
                continue
            u = w0 * uvs[a, 0] + w1 * uvs[b, 0] + w2 * uvs[c, 0]
            vv = w0 * uvs[a, 1] + w1 * uvs[b, 1] + w2 * uvs[c, 1]
            tx = np.clip((u * (tw - 1)).astype(np.int32), 0, tw - 1)
            # glTF: V=0 at bottom → flip for image rows
            ty = np.clip(((1.0 - vv) * (th - 1)).astype(np.int32), 0, th - 1)
            cols = tex[ty, tx]
            alpha = cols[..., 3]
            update = update & (alpha > 0)
            if not update.any():
                continue
            shade = max(0.5, float(nrms[fi].dot(light)) * 0.35 + 0.70)
            rgb = np.clip(cols[..., :3] * shade, 0, 255).astype(np.uint8)
            uy, ux = yy[update], xx[update]
            zbuf[uy, ux] = z[update]
            img[uy, ux, 0] = rgb[update, 0]
            img[uy, ux, 1] = rgb[update, 1]
            img[uy, ux, 2] = rgb[update, 2]
            img[uy, ux, 3] = alpha[update]

    im = Image.fromarray(img)
    bbox = im.getbbox()
    return im.crop(bbox) if bbox else im


def fit_height(im: Image.Image, h: int) -> Image.Image:
    if im.height <= 0:
        return im
    r = h / im.height
    return im.resize((max(1, int(round(im.width * r))), h), Image.Resampling.NEAREST)


def write_contact_sheet(baked: dict[str, Image.Image], path: Path) -> None:
    preview = Image.open(ASSETS / "previews" / "sedan.png").convert("RGBA")
    preview = preview.resize(
        (preview.width * 5, preview.height * 5), Image.Resampling.NEAREST
    )
    labels = [
        ("sedan-e (baked)", baked["sedan-e"]),
        ("sedan-w (baked)", baked["sedan-w"]),
        ("race-e (baked)", baked["race-e"]),
        ("official preview", preview),
        ("race-w (baked)", baked["race-w"]),
        ("chick-ne (baked)", baked["chick-ne"]),
        ("chick-sw (baked)", baked["chick-sw"]),
    ]
    cell_w, cell_h = 200, 170
    cols, rows = 4, 2
    sheet = Image.new("RGBA", (cols * cell_w, rows * cell_h), (40, 40, 48, 255))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    for i, (label, im) in enumerate(labels):
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
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)
    print(f"wrote contact sheet {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--ground-scale", type=float, default=GROUND_SCALE)
    ap.add_argument("--height-scale", type=float, default=HEIGHT_SCALE)
    ap.add_argument("--out-height", type=int, default=96)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    baked: dict[str, Image.Image] = {}

    # Cars: Kenney nose is -Z.
    # With sx=x-z, sy=-y*hs+(x+z)*gs (camera from -X-Z):
    #   yaw 270° → nose +X → screen down-right (SE traffic, dir=+1)
    #   yaw  90° → nose -X → screen up-left   (NW traffic, dir=-1)
    # These align with the road diagonal at atan(ground_scale).
    for car in ("sedan", "race"):
        parts = load_parts(ASSETS / f"{car}.glb")
        for suffix, yaw in [("e", 270.0), ("w", 90.0)]:
            im = fit_height(
                render(
                    parts,
                    args.size,
                    yaw=yaw,
                    ground_scale=args.ground_scale,
                    height_scale=args.height_scale,
                ),
                args.out_height,
            )
            key = f"{car}-{suffix}"
            path = OUT / f"{key}.png"
            im.save(path)
            baked[key] = im
            print(f"wrote {path} {im.size}")

    # Chick: beak +Z.
    # yaw 180° → beak up-right/up (NE hop); yaw 0° → opposite (SW).
    chick = load_parts(ASSETS / "animal-chick.glb")
    for name, yaw in [("chick-ne", 180.0), ("chick-sw", 0.0)]:
        im = fit_height(
            render(
                chick,
                args.size,
                yaw=yaw,
                ground_scale=args.ground_scale,
                height_scale=args.height_scale,
            ),
            args.out_height,
        )
        path = OUT / f"{name}.png"
        im.save(path)
        baked[name] = im
        print(f"wrote {path} {im.size}")

    contact = Path("/workspace/crossy-prototype/renders/bake-upright-check.png")
    write_contact_sheet(baked, contact)

    # Sanity: orange/yellow on top, dark wheels near bottom
    for key in ("sedan-e", "chick-ne"):
        arr = np.array(baked[key])
        a = arr[:, :, 3] > 128
        rows = np.where(a.any(axis=1))[0]
        if len(rows) == 0:
            continue
        lo, hi = int(rows[0]), int(rows[-1])
        h = hi - lo + 1
        top = arr[lo : lo + max(1, h // 5)]
        bot = arr[hi - max(1, h // 5) : hi + 1]
        tm = top[top[:, :, 3] > 128][:, :3].mean(0)
        bm = bot[bot[:, :, 3] > 128][:, :3].mean(0)
        print(f"sanity {key}: topRGB={tm.round(0)} botRGB={bm.round(0)}")


if __name__ == "__main__":
    main()
