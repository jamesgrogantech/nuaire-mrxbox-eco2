#!/usr/bin/env python3
"""3D preview renders of the bridge case, with simple board models inside.

A small z-buffer rasteriser (numpy only) with flat shading and outline edges,
so no OpenGL or OpenSCAD is needed. Board, connector and wiring models are
rough stand-ins built from the same PARAMETERS as case.py, for checking the
layout, not exact parts.

    .venv/bin/python hardware/case/render.py      # writes renders/*.png
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case as C  # noqa: E402
from manifold3d import Manifold  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "renders")

# ------------------------------------------------------------ colours (RGB)
CASE = (0.24, 0.26, 0.29)       # charcoal base
LID = (0.90, 0.90, 0.88)        # warm white lid
PCB_BLUE = (0.10, 0.32, 0.72)
PCB_BLACK = (0.13, 0.13, 0.15)
METAL = (0.78, 0.78, 0.80)
DARK = (0.18, 0.18, 0.20)
TERM = (0.15, 0.45, 0.85)
WHITE = (0.93, 0.93, 0.90)
CAP = (0.60, 0.60, 0.64)
CABLE = (0.85, 0.85, 0.83)
BOOT = (0.10, 0.10, 0.11)
LEADS = [(0.85, 0.15, 0.15), (0.10, 0.10, 0.10), (0.95, 0.85, 0.15), (0.20, 0.65, 0.25)]
BUS = {"red": (0.85, 0.15, 0.15), "blue": (0.15, 0.35, 0.85),
       "yellow": (0.95, 0.85, 0.15), "green": (0.20, 0.65, 0.25)}


def box(x, y, z, sx, sy, sz):
    return Manifold.cube([sx, sy, sz]).translate([x, y, z])


def cyl(x, y, z, h, d):
    return Manifold.cylinder(h, d / 2, d / 2, 32).translate([x, y, z])


def wire(points, d=1.4):
    """A wire through a list of points: capsules between consecutive points."""
    s = [Manifold.sphere(d / 2, 12).translate(list(p)) for p in points]
    return C.union([Manifold.batch_hull([a, b]) for a, b in zip(s, s[1:])])


# ------------------------------------------------------------- board models
def buck_parts():
    b = C.BUCK
    x, y, z = C.ix(b["x0"]), C.iy(b["y0"]), C.iz(b["pad"])
    t = z + b["pcb"]
    l, w = b["l"], b["w"]
    return [
        (box(x, y, z, l, w, b["pcb"]), PCB_BLUE),
        (box(x + 1, y + w - 12, t, 14, 9, 11), DARK),                  # DC jack (input end)
        (box(x + 1, y + 1, t, 8, 10, 10), TERM),                       # IN terminal
        (cyl(x + 20, y + w / 2 + 3, t, 11, 8), CAP),                   # input cap
        (box(x + 26, y + 6, t, 8, 6, 3), DARK),                        # regulator
        (box(x + 36, y + 9, t, 12, 12, 8), METAL),                     # inductor "330"
        (cyl(x + 44, y + 5, t, 12, 8), CAP),                           # output cap
        (box(x + l - 15, y + 7, t, 15, 13, 7), METAL),                 # USB-A
        (box(x + l - 10, y + w - 9, t, 8, 8, 10), TERM),               # OUT terminal
    ]


def xy485_parts():
    b = C.XY485
    x, y, z = C.ix(b["x0"]), C.iy(b["y0"]), C.iz(b["pad"])
    t = z + b["pcb"]
    l, w = b["l"], b["w"]
    return [
        (box(x, y, z, l, w, b["pcb"]), PCB_BLUE),
        (box(x + 1, y + 2, t, 8, w - 4, 10), TERM),                    # A+ B- Earth
        (box(x + 18, y + 8, t, 5, 6, 1.6), DARK),                      # MAX485
        (box(x + 28, y + 5, t, 9, 4, 1.6), DARK),                      # CD4069
        (box(x + l - 7, y + 3, t, 6, 12, 6), WHITE),                   # JST TTL plug
    ]


def esp_parts():
    e = C.ESP
    x, y, z = C.ix(C.ESP_X0), C.iy(e["y0"]), C.iz(e["lift"])
    t = z + e["pcb"]
    l, w = e["l"], e["w"]
    parts = [
        (box(x, y, z, l, w, e["pcb"]), PCB_BLACK),
        (box(x, y + (w - 18) / 2, t, 25.5, 18, 3.1), METAL),           # WROOM-32 module
        (box(x + l - 7.4, C.iy(C.ESP_CY) - 4.5, t, 7.4, 9, 3.2), METAL),  # USB-C
        (box(x + 30, y + 10, t, 5, 5, 1.2), DARK),                     # CP2102
    ]
    for yy in (y + 0.2, y + w - 2.7):
        parts.append((box(x + 2, yy, z - 2.5, l - 4, 2.5, 2.5), DARK))   # header rows
    # Four Dupont leads on the front row, down and across to the XY-485's plug.
    jx = C.ix(C.XY485["x0"] + C.XY485["l"] - 4)
    jy = C.iy(C.XY485["y0"] + 6)
    jz = C.iz(C.XY485["pad"] + C.XY485["pcb"] + 6)
    for k, col in enumerate(LEADS):
        lx = x + l - 8 - k * 2.54
        parts.append((box(lx, y + 0.2, z - 16.5, 2.5, 2.5, 14), DARK))  # housing
        parts.append((wire([(lx + 1.25, y + 1.45, z - 16.5), (lx + 1.25, y + 1.45, C.iz(9)),
                            (jx + 5, jy + 2 + k * 2, C.iz(10)), (jx, jy + 2 + k * 2, jz)], 1.2), col))
    return parts


def gx_parts(plugged=True):
    """GX12 panel sockets, and optionally the mating plugs with their cables."""
    parts = []
    zc = C.iz(C.GX_Z)
    for _, gy in C.GX:
        yc = C.iy(gy)
        parts.append((C.cyl_x(C.GX_SEAT - 2.0, yc, zc, 2.0, 15.0), METAL))       # outside flange
        parts.append((C.cyl_x(C.WALL + 0.05, yc, zc, C.GX_NUT_T, 16.0), METAL))  # inside nut
        parts.append((C.cyl_x(C.WALL + 3.1, yc, zc, 10.0, 11.0), BOOT))          # body + cups
        if plugged:
            parts.append((C.cyl_x(-22.0, yc, zc, 20.0, 15.0), METAL))     # coupling nut
            parts.append((C.cyl_x(-36.0, yc, zc, 14.0, 9.0), BOOT))       # strain relief
            parts.append((C.cyl_x(-75.0, yc, zc, 39.5, 5.5), CABLE))      # 4-core bus cable
    return parts


def bus_wiring():
    """Socket to buck IN (red/blue) and XY-485 A+/B- (yellow/green)."""
    gx = dict(C.GX)
    zc = C.iz(C.GX_Z)
    x0 = C.WALL + 13.5
    yin = C.iy(gx["IN"])
    bx, by = C.ix(C.BUCK["x0"] + 5), C.iy(C.BUCK["y0"] + 6)
    bz = C.iz(C.BUCK["pad"] + C.BUCK["pcb"] + 10)
    ax_, ay = C.ix(C.XY485["x0"] + 5), C.iy(C.XY485["y0"] + 8)
    az = C.iz(C.XY485["pad"] + C.XY485["pcb"] + 10)
    out = []
    dests = (("red", (bx, by - 2, bz)), ("blue", (bx, by + 2, bz)),
             ("yellow", (ax_, ay - 2, az)), ("green", (ax_, ay + 2, az)))
    for k, (col, (dx, dy_, dz)) in enumerate(dests):
        off = (k - 1.5) * 2.2
        start = (x0, yin + off, zc)
        mid = (x0 + 3, (yin + dy_) / 2, max(zc, dz) + 3)
        out.append((wire([start, mid, (dx, dy_, dz + 3), (dx, dy_, dz)]), BUS[col]))
    return out


def boards():
    return buck_parts() + xy485_parts() + esp_parts() + gx_parts() + bus_wiring()


# --------------------------------------------------------------- rasteriser
def view_matrix(az, el):
    a, e = np.radians(az), np.radians(el)
    rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, np.cos(e), -np.sin(e)], [0, np.sin(e), np.cos(e)]])
    # rows of the result: screen x, depth (into the screen), screen y
    return rx @ rz


def render(items, az, el, size=(1400, 1000), ss=2, light=(-0.4, -0.7, 0.9)):
    W, H = size[0] * ss, size[1] * ss
    m = view_matrix(az, el)
    L = np.array(light) / np.linalg.norm(light)
    tris, cols, ids = [], [], []
    for k, (man, col) in enumerate(items):
        mesh = man.to_mesh()
        v = np.asarray(mesh.vert_properties)[:, :3]
        t = v[np.asarray(mesh.tri_verts)]
        tris.append(t)
        cols.append(np.repeat([col], len(t), axis=0))
        ids.append(np.full(len(t), k))
    tris, cols, ids = np.concatenate(tris), np.concatenate(cols), np.concatenate(ids)
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    shade = 0.35 + 0.65 * np.clip(n @ L, 0, 1)
    vn = n @ m.T
    p = tris @ m.T
    sx, sd, sy = p[..., 0], p[..., 1], p[..., 2]
    lo = np.array([sx.min(), sy.min()])
    hi = np.array([sx.max(), sy.max()])
    scale = 0.9 * min(W / (hi[0] - lo[0]), H / (hi[1] - lo[1]))
    cx, cy = (lo + hi) / 2
    X = (sx - cx) * scale + W / 2
    Y = H / 2 - (sy - cy) * scale

    zbuf = np.full((H, W), np.inf)
    img = np.ones((H, W, 3))
    idb = np.full((H, W), -1)
    nbuf = np.zeros((H, W, 3))
    for i in range(len(tris)):
        if vn[i, 1] > 0:                              # back face
            continue
        x0, x1 = int(max(X[i].min(), 0)), int(min(X[i].max() + 1, W))
        y0, y1 = int(max(Y[i].min(), 0)), int(min(Y[i].max() + 1, H))
        if x0 >= x1 or y0 >= y1:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        (ax_, bx, cx_), (ay, by, cy_) = X[i], Y[i]
        den = (by - cy_) * (ax_ - cx_) + (cx_ - bx) * (ay - cy_)
        if abs(den) < 1e-9:
            continue
        w0 = ((by - cy_) * (gx - cx_) + (cx_ - bx) * (gy - cy_)) / den
        w1 = ((cy_ - ay) * (gx - cx_) + (ax_ - cx_) * (gy - cy_)) / den
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not inside.any():
            continue
        d = w0 * sd[i, 0] + w1 * sd[i, 1] + w2 * sd[i, 2]
        zb = zbuf[y0:y1, x0:x1]
        upd = inside & (d < zb)
        zb[upd] = d[upd]
        img[y0:y1, x0:x1][upd] = np.array(cols[i]) * shade[i]
        idb[y0:y1, x0:x1][upd] = ids[i]
        nbuf[y0:y1, x0:x1][upd] = vn[i]

    # Outline edges: object boundary, crease (normal change) or depth jump.
    edge = np.zeros((H, W), bool)
    for dy, dx in ((0, 1), (1, 0)):
        a, b = (slice(0, H - dy), slice(0, W - dx)), (slice(dy, H), slice(dx, W))
        za, zb_ = zbuf[a], zbuf[b]
        fin = np.isfinite(za) & np.isfinite(zb_)
        e = idb[a] != idb[b]
        e |= fin & ((nbuf[a] * nbuf[b]).sum(-1) < 0.9)
        with np.errstate(invalid="ignore"):
            e |= fin & (np.abs(np.where(fin, za - zb_, 0)) > 1.5)   # depth jump, mm
        edge[a] |= e
    img[edge] *= 0.3
    bg = np.linspace(1.0, 0.90, H)[:, None, None] * np.ones((1, W, 3))
    img = np.where(np.isinf(zbuf)[..., None] & ~edge[..., None], bg, img)
    img = img.reshape(size[1], ss, size[0], ss, 3).mean(axis=(1, 3))
    return np.clip(img, 0, 1)


def save(img, name, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    h, w = img.shape[:2]
    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(img)
    ax.axis("off")
    ax.text(20, 40, title, fontsize=15, color="#222222", family="sans-serif")
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return path


def main():
    os.makedirs(OUT, exist_ok=True)
    base, lid = C.base(), C.lid()
    lid_print = C.lid_for_print(lid)
    parts = boards()
    outside = gx_parts()
    shots = []
    shots.append(("1-closed.png", "Closed: GX12 bus socket with plug, engraved label",
                  render([(base, CASE), (lid, LID)] + outside, az=40, el=26)))
    shots.append(("2-closed-usb.png", "Closed, from the right: USB-C for flashing, back vents",
                  render([(base, CASE), (lid, LID)] + outside, az=-140, el=24)))
    beside = lid_print.translate([0, C.OY + 15, 0])
    shots.append(("3-open.png", "Open: boards, bus wiring from the GX12 socket, lid underside",
                  render([(base, CASE), (beside, LID)] + parts, az=-30, el=44)))
    ycut = C.iy(C.ESP["y0"] - 1.0)
    keep = box(-200, ycut, -50, 400, 300, 300)
    cut = [(base ^ keep, CASE)] + [(m ^ keep, c) for m, c in parts if not (m ^ keep).is_empty()]
    shots.append(("4-cutaway.png", "Cutaway: GX12 socket, ESP32 on its ribs, Dupont leads",
                  render(cut, az=0, el=12)))
    shots.append(("5-bottom.png", "Underside: keyholes for wall mounting (socket points down)",
                  render([(base, CASE), (lid, LID)] + outside, az=30, el=-55, light=(-0.3, -0.5, -0.9))))
    shots.append(("6-sockets.png", "Left wall, plug out: GX12 socket in its seat",
                  render([(base, CASE), (lid, LID)] + gx_parts(plugged=False), az=72, el=12,
                         light=(-0.9, -0.3, 0.5))))

    paths = [save(img, name, title) for name, title, img in shots]

    import matplotlib.pyplot as plt
    import matplotlib.image as mpimg
    fig, axs = plt.subplots(3, 2, figsize=(20, 21.5))
    for ax in axs.flat:
        ax.axis("off")
    for ax, pth in zip(axs.flat, paths):
        ax.imshow(mpimg.imread(pth))
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "sheet.png"), dpi=80)
    for pth in paths:
        print(pth)


if __name__ == "__main__":
    main()
