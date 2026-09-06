#!/usr/bin/env python3
"""Bake Kenney GLBs to Crossy-style 3/4 PNG sprites (software rasterizer).

Sprites face ALONG the isometric road:
  *-e.png    nose toward screen down-right (SE, cars with dir=+1)
  *-w.png    nose toward screen up-left   (NW, cars with dir=-1)
  chick-ne   beak toward screen up-right  (player forward hop)

Kenney car models face -Z (nose toward -Z); the chick's beak faces +Z.
Up is +Y for all models.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image
import trimesh

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "kenney"
OUT = ROOT / "assets" / "baked"

PITCH = 32.0  # camera looks down at the model


def yaw_mat(deg: float) -> np.ndarray:
    r = np.radians(deg)
    c, s = np.cos(r), np.sin(r)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float64)


def pitch_mat(deg: float) -> np.ndarray:
    r = np.radians(deg)
    c, s = np.cos(r), np.sin(r)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float64)


def extract_tex(mesh) -> np.ndarray | None:
    try:
        mat = mesh.visual.material
        if hasattr(mat, "baseColorTexture") and mat.baseColorTexture is not None:
            return np.array(mat.baseColorTexture.convert("RGBA"))
    except Exception:
        pass
    return None


def flat_tex(color) -> np.ndarray:
    tex = np.zeros((2, 2, 4), dtype=np.uint8)
    tex[:, :] = color
    return tex


def load_textured_meshes(path: Path) -> list[tuple]:
    """Return list of (mesh, tex_rgba_array) with scene graph transforms applied."""
    scene = trimesh.load(str(path), force="scene")
    out = []
    for node_name in scene.graph.nodes_geometry:
        transform, geom_name = scene.graph[node_name]
        mesh = scene.geometry[geom_name].copy()
        mesh.apply_transform(transform)
        tex = extract_tex(mesh)
        if tex is None:
            color = [200, 200, 200, 255]
            try:
                if hasattr(mesh.visual.material, "main_color"):
                    color = list(mesh.visual.material.main_color)
            except Exception:
                pass
            tex = flat_tex(color)
        if not hasattr(mesh.visual, "uv") or mesh.visual.uv is None:
            mesh.visual.uv = np.zeros((len(mesh.vertices), 2))
        out.append((mesh, tex))
    return out


def car_with_wheels(body: Path, wheel: Path) -> list[tuple]:
    """Load car body, replace its (blocky) wheel nodes with wheel-default.glb."""
    scene = trimesh.load(str(body), force="scene")
    body_parts: list[tuple] = []
    wheel_xforms: list[np.ndarray] = []
    for node_name in scene.graph.nodes_geometry:
        transform, geom_name = scene.graph[node_name]
        if "wheel" in geom_name.lower() or "wheel" in node_name.lower():
            wheel_xforms.append(np.array(transform, dtype=np.float64))
            continue
        mesh = scene.geometry[geom_name].copy()
        mesh.apply_transform(transform)
        tex = extract_tex(mesh)
        if tex is None:
            tex = flat_tex([180, 180, 180, 255])
        if not hasattr(mesh.visual, "uv") or mesh.visual.uv is None:
            mesh.visual.uv = np.zeros((len(mesh.vertices), 2))
        body_parts.append((mesh, tex))

    # Reference wheel geometry from the separate wheel GLB.
    wscene = trimesh.load(str(wheel), force="scene")
    wgeom = None
    wtex = None
    for node_name in wscene.graph.nodes_geometry:
        wt, gname = wscene.graph[node_name]
        wgeom = wscene.geometry[gname].copy()
        wgeom.apply_transform(wt)
        wtex = extract_tex(wgeom)
        break
    if wgeom is None:
        return body_parts
    if wtex is None:
        wtex = flat_tex([40, 40, 40, 255])
    if not hasattr(wgeom.visual, "uv") or wgeom.visual.uv is None:
        wgeom.visual.uv = np.zeros((len(wgeom.vertices), 2))

    for xf in wheel_xforms:
        wm = wgeom.copy()
        wm.apply_transform(xf)
        body_parts.append((wm, wtex))
    return body_parts


def render(parts: list[tuple], size: int, yaw: float, pitch: float = PITCH) -> Image.Image:
    """Orbit camera: yaw around model +Y, then pitch the camera down.

    Kenney car noses are at -Z (yaw 0 pitch 0 shows the rear bumper);
    the chick's beak is at +Z. After R = pitch @ yaw, screen +x is right
    and +y is down. For a car (nose -Z):
      yaw  45 -> nose down-right (SE)   yaw 225 -> nose up-left (NW)
    For the chick (beak +Z):
      yaw 135 -> beak up-right (NE)     yaw 315 -> beak down-left (SW)
    """
    R = pitch_mat(pitch) @ yaw_mat(yaw)
    transformed = []
    for mesh, tex in parts:
        v = mesh.vertices @ R.T
        n = mesh.face_normals @ R.T
        transformed.append((mesh, tex, v, n))

    allv = np.concatenate([v for _, _, v, _ in transformed])
    minx, maxx = allv[:, 0].min(), allv[:, 0].max()
    miny, maxy = allv[:, 1].min(), allv[:, 1].max()
    pad = 0.05 * max(maxx - minx, maxy - miny, 1e-6)
    minx -= pad
    maxx += pad
    miny -= pad
    maxy += pad
    scale = min(size / (maxx - minx), size / (maxy - miny)) * 0.92
    ox = size / 2 - (minx + maxx) / 2 * scale
    oy = size / 2 + (miny + maxy) / 2 * scale  # model +Y is up -> screen down

    img = np.zeros((size, size, 4), dtype=np.uint8)
    zbuf = np.full((size, size), -np.inf, dtype=np.float32)
    light = np.array([0.35, 0.85, 0.35], dtype=np.float64)
    light /= np.linalg.norm(light)

    for mesh, tex, v, nrms in transformed:
        uvs = mesh.visual.uv
        th, tw = tex.shape[:2]
        xs = v[:, 0] * scale + ox
        ys = -v[:, 1] * scale + oy
        zs = v[:, 2]
        for fi, (a, b, c) in enumerate(mesh.faces):
            # backface cull: camera looks along +Z after the pitch
            if nrms[fi, 2] > -0.05:
                continue
            x0, y0, z0 = xs[a], ys[a], zs[a]
            x1, y1, z1 = xs[b], ys[b], zs[b]
            x2, y2, z2 = xs[c], ys[c], zs[c]
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
            w1 = ((y2 - y0) * (xx - x2) + (x0 - x2) * (yy - y2)) / denom
            w2 = 1.0 - w0 - w1
            mask = (w0 >= -1e-5) & (w1 >= -1e-5) & (w2 >= -1e-5)
            # ignore stray barycentrics on degenerate slivers (wheel UV seams)
            mask &= (w0 <= 1.05) & (w1 <= 1.05) & (w2 <= 1.05)
            if not mask.any():
                continue
            z = w0 * z0 + w1 * z1 + w2 * z2
            update = mask & (z > zbuf[yy, xx])
            if not update.any():
                continue
            u = w0 * uvs[a, 0] + w1 * uvs[b, 0] + w2 * uvs[c, 0]
            vv = w0 * uvs[a, 1] + w1 * uvs[b, 1] + w2 * uvs[c, 1]
            tx = np.clip((u * (tw - 1)).astype(np.int32), 0, tw - 1)
            # glTF V is bottom-up; image arrays are top-down
            ty = np.clip(((1.0 - vv) * (th - 1)).astype(np.int32), 0, th - 1)
            cols = tex[ty, tx]
            alpha = cols[..., 3]
            update = update & (alpha > 0)
            if not update.any():
                continue
            shade = max(0.35, float(nrms[fi].dot(light)) * 0.5 + 0.55)
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
    if im.height == 0:
        return im
    r = h / im.height
    return im.resize((max(1, int(im.width * r)), h), Image.Resampling.NEAREST)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=320)
    ap.add_argument("--pitch", type=float, default=PITCH)
    ap.add_argument("--car-pitch", type=float, default=26.0,
                    help="lower camera pitch for cars (more side, less roof)")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    # yaw maps model nose/beak to screen directions, see render() docs.
    chick = load_textured_meshes(ASSETS / "animal-chick.glb")
    for name, yaw, h in [("chick-ne", 135, 96), ("chick-sw", 315, 96)]:
        im = fit_height(render(chick, args.size, yaw=yaw, pitch=args.pitch), h)
        im.save(OUT / f"{name}.png")
        print(f"wrote {OUT / (name + '.png')} {im.size}")

    for car in ("sedan", "race"):
        parts = car_with_wheels(ASSETS / f"{car}.glb", ASSETS / "wheel-default.glb")
        for suffix, yaw in [("e", 45), ("w", 225)]:
            im = fit_height(render(parts, args.size, yaw=yaw, pitch=args.car_pitch), 72)
            path = OUT / f"{car}-{suffix}.png"
            im.save(path)
            print(f"wrote {path} {im.size}")


if __name__ == "__main__":
    main()
