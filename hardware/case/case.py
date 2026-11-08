#!/usr/bin/env python3
"""Two-part printable case for the MRXBOX RS485 bridge.

Holds three boards:
  * HW-688 buck module (bus +10 V in, 5 V out)     63.4 x 27.5 mm
  * ESP32-WROOM-32 38-pin USB-C dev board          up to 55.5 x 28.5 mm
  * XY-485 auto-direction RS485 module             52.0 x 23.0 mm

and a GX12 4-pin panel socket on the left wall for the bus cable from the MRXBOX.

Board sizes come from the seller listings, not from measurements. Measure the
real boards and connectors with calipers and edit PARAMETERS before printing.

Usage (needs manifold3d + numpy; matplotlib only for --preview):
    python3 -m venv .venv && .venv/bin/pip install manifold3d numpy matplotlib
    .venv/bin/python hardware/case/case.py            # writes base.stl, lid.stl
    .venv/bin/python hardware/case/case.py --preview  # also writes preview.png

Layout, looking down with the lid off (x right, y up):

    +-----------------------------------------------------+
    |        [ HW-688 buck: IN end left, USB-A right ]    |
   o  wiring                                            |
    |   bay      [ ESP32 on two ribs, USB-C ->         ]=|  <- USB-C (flashing)
    |            ( keyholes in the floor )               |
    |        [ XY-485: A+/B- terminal end left ]          |
    +-----------------------------------------------------+
"""
import argparse
import os
import struct
import sys

import numpy as np
from manifold3d import Manifold

# ---------------------------------------------------------------- PARAMETERS
WALL = 2.4          # side wall thickness
FLOOR = 2.0         # base floor thickness
LID = 2.6           # lid plate thickness
FIT = 0.3           # lid lip clearance per side
R = 5.0             # outer corner radius (plan view)
CH_BOT = 1.0        # chamfer, bottom outer edge of the base
CH_TOP = 1.0        # chamfer, top outer edge of the lid
CH_SEAM = 0.6       # small chamfer either side of the base/lid seam

IX, IY, IZ = 97.0, 91.0, 32.0   # interior size

# Boards: (x0, y0) is the board's lower-left corner in interior coordinates.
BUCK = dict(x0=22.0, y0=61.5, l=63.4, w=27.5, pcb=1.6, top=14.0, pad=3.0)
XY485 = dict(x0=22.0, y0=2.0, l=52.0, w=23.0, pcb=1.6, top=11.0, pad=3.0)
# ESP32 sits on two ribs so female Dupont leads fit under its downward pins.
# Its USB-C end is pushed against the right wall, so its length doesn't matter.
ESP = dict(l=55.5, w=28.5, y0=29.0, pcb=1.6, top=3.6, lift=22.0)

PAD = 5.0           # corner pad size for buck / XY-485
CLIP_H = 3.0        # corner clip height above the pad top
CLIP_T = 1.2        # corner clip thickness
CLR = 0.5           # board clearance inside the clips

BOSS_D, BOSS_PILOT = 7.0, 2.5   # lid screw bosses, M3 self-tapping
LID_HOLE, LID_CSK = 3.4, 6.6    # M3 countersunk screws in the lid

# GX12 4-pin aviation sockets (M12 thread). Hole, outside seat recess, inside
# clearance for nut + body + solder cups (checked by the fit check).
GX_HOLE = 12.2
GX_SEAT_D, GX_SEAT = 16.0, 0.6
GX_NUT_D, GX_NUT_T = 16.5, 3.0       # nut across corners, thickness
GX_BODY_D, GX_DEPTH = 11.0, 19.0     # body + solder cups + wire bend, from the inner wall
GX_Z = 16.0                          # centre height above the floor
GX = [("IN", 44.0)]                  # (name, y centre)

USB_W, USB_H, USB_R = 13.0, 7.5, 1.5   # USB-C opening, fits a moulded plug

# Keyholes for wall mounting: floor against the wall, +x up, so the GX12 sockets
# point down. For 4 mm pan-head screws. They sit in the channel between the ribs.
KEY_HEAD, KEY_SHANK, KEY_TRAVEL = 8.5, 4.2, 6.0
RIB_DY = (-7.0, 4.6)                   # rib offsets from the ESP32 centre line
KEYS = [(52.0, None), (82.0, None)]    # big-hole x; y = ESP32 centre line
KEY_RING_D, KEY_RING_H = 13.0, 3.0

LABEL = "MRXBOX BRIDGE"
PIX = 1.0           # pixel size of the label font
TEXT_DEPTH = 0.6

SEG = 64
# ---------------------------------------------------------------------------


def box(x0, y0, z0, sx, sy, sz):
    return Manifold.cube([sx, sy, sz]).translate([x0, y0, z0])


def cyl(x, y, z0, h, d, d2=None):
    return Manifold.cylinder(h, d / 2, (d2 if d2 is not None else d) / 2, SEG).translate([x, y, z0])


def cyl_x(x0, y, z, length, d):
    """Cylinder along +x from x0 (rotate 90 about y sends +z to +x)."""
    return Manifold.cylinder(length, d / 2, d / 2, SEG).rotate([0, 90, 0]).translate([x0, y, z])


def cyl_y(x, y0, z, length, d):
    """Cylinder along +y from y0 (rotate -90 about x sends +z to +y)."""
    return Manifold.cylinder(length, d / 2, d / 2, SEG).rotate([-90, 0, 0]).translate([x, y0, z])


def rr_x(x0, length, yc, zc, w, h, r):
    """Rounded rectangle (w along y, h along z) extruded along +x from x0."""
    return Manifold.batch_hull([cyl_x(x0, yc + sy * (w / 2 - r), zc + sz * (h / 2 - r), length, 2 * r)
                                for sy in (-1, 1) for sz in (-1, 1)])


def union(parts):
    out = parts[0]
    for p in parts[1:]:
        out = out + p
    return out


def rrect(x0, y0, sx, sy, r, z0, z1, ch_bot=0.0, ch_top=0.0):
    """Rounded-corner slab with optional 45-degree chamfers on its outer edges."""
    r = min(r, sx / 2 - 0.01, sy / 2 - 0.01)
    parts = []
    for cx in (x0 + r, x0 + sx - r):
        for cy in (y0 + r, y0 + sy - r):
            zb, zt = z0 + ch_bot, z1 - ch_top
            parts.append(cyl(cx, cy, zb, zt - zb, 2 * r))
            if ch_bot:
                parts.append(cyl(cx, cy, z0, ch_bot, 2 * (r - ch_bot), 2 * r))
            if ch_top:
                parts.append(cyl(cx, cy, zt, ch_top, 2 * r, 2 * (r - ch_top)))
    return Manifold.batch_hull(parts)


def slot(x0, y0, x1, y1, w, z0, h):
    """Stadium (rounded slot) from (x0,y0) to (x1,y1), width w."""
    return Manifold.batch_hull([cyl(x0, y0, z0, h, w), cyl(x1, y1, z0, h, w)])


OX, OY = IX + 2 * WALL, IY + 2 * WALL       # outer footprint
H = FLOOR + IZ                              # base height


def ix(x):
    return x + WALL


def iy(y):
    return y + WALL


def iz(z):
    return z + FLOOR


BOSSES = [(BOSS_D / 2, BOSS_D / 2), (IX - BOSS_D / 2, BOSS_D / 2),
          (BOSS_D / 2, IY - BOSS_D / 2), (IX - BOSS_D / 2, IY - BOSS_D / 2)]
ESP_X0 = IX - ESP["l"]
ESP_CY = ESP["y0"] + ESP["w"] / 2


def keys():
    return [(kx, ESP_CY if ky is None else ky) for kx, ky in KEYS]


# ----------------------------------------------------------------- lettering
FONT = {
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    " ": ["00000"] * 7,
}


def text_width(s, p=PIX):
    return (len(s) * 6 - 1) * p


def text_cutter(s, p=PIX, depth=TEXT_DEPTH):
    """Letters as a solid in local (u right, v up, w out of the surface) coords,
    from w = -depth (bottom of the engraving) to w = +1 (above the surface)."""
    parts = []
    for k, ch in enumerate(s):
        for row, bits in enumerate(FONT[ch]):
            for col, bit in enumerate(bits):
                if bit == "1":
                    u = (k * 6 + col) * p
                    v = (6 - row) * p
                    parts.append(box(u - 0.01, v - 0.01, -depth, p + 0.02, p + 0.02, depth + 1))
    return union(parts)


# --------------------------------------------------------------------- parts
def pads_and_clips(b):
    """Corner pads lift the PCB off its solder joints; L clips stop it sliding."""
    parts = []
    h = b["pad"] + CLIP_H
    for left in (True, False):
        for front in (True, False):
            px = b["x0"] if left else b["x0"] + b["l"] - PAD
            py = b["y0"] if front else b["y0"] + b["w"] - PAD
            parts.append(box(ix(px), iy(py), iz(0), PAD, PAD, b["pad"]))
            cx = b["x0"] - CLR - CLIP_T if left else b["x0"] + b["l"] + CLR
            cy = b["y0"] - CLR - CLIP_T if front else b["y0"] + b["w"] + CLR
            leg_y = cy if front else cy - PAD
            leg_x = cx if left else cx - PAD
            parts.append(box(ix(cx), iy(leg_y), iz(0), CLIP_T, PAD + CLIP_T, h))
            parts.append(box(ix(leg_x), iy(cy), iz(0), PAD + CLIP_T, CLIP_T, h))
    return parts


def base():
    outer = rrect(0, 0, OX, OY, R, 0, H, ch_bot=CH_BOT, ch_top=CH_SEAM)
    cavity = rrect(WALL, WALL, IX, IY, R - WALL, FLOOR, H + 1)
    parts = [outer - cavity]

    for bx, by in BOSSES:
        # Boss fused into the corner.
        cx = 0 if bx < IX / 2 else IX - 1
        cy = 0 if by < IY / 2 else IY - 1
        parts.append(Manifold.batch_hull([cyl(ix(bx), iy(by), iz(0), IZ, BOSS_D),
                                          box(ix(cx), iy(cy), iz(0), 1, 1, IZ)]))
    parts += pads_and_clips(BUCK)
    parts += pads_and_clips(XY485)
    for dy in RIB_DY:
        parts.append(box(ix(ESP_X0 + 6), iy(ESP_CY + dy), iz(0), ESP["l"] - 8, 2.4, ESP["lift"]))
    for kx, ky in keys():
        parts.append(slot(ix(kx), iy(ky), ix(kx + KEY_TRAVEL), iy(ky), KEY_RING_D, iz(0), KEY_RING_H))
    solid = union(parts)

    cuts = []
    for bx, by in BOSSES:
        cuts.append(cyl(ix(bx), iy(by), iz(IZ - 12), 13, BOSS_PILOT))
    # GX12 sockets: through hole plus a shallow round seat on the outside.
    for _, gy in GX:
        cuts.append(cyl_x(-1, iy(gy), iz(GX_Z), WALL + 2, GX_HOLE))
        cuts.append(cyl_x(-1, iy(gy), iz(GX_Z), GX_SEAT + 1, GX_SEAT_D))
    # USB-C opening: rounded rectangle through the right wall.
    usb_z = ESP["lift"] + ESP["pcb"] + 1.6
    cuts.append(rr_x(ix(IX) - 1, WALL + 2, iy(ESP_CY), iz(usb_z), USB_W, USB_H, USB_R))
    # Back-wall vents: rounded vertical slots.
    for k in range(7):
        x = ix(BUCK["x0"] + 6 + k * 8)
        cuts.append(Manifold.batch_hull([cyl_y(x, iy(IY) - 1, iz(z), WALL + 2, 3.2) for z in (4.5, 11.5)]))
    # Keyholes: through hole + slot in the floor, head pocket above the slot.
    for kx, ky in keys():
        cuts.append(cyl(ix(kx), iy(ky), -1, FLOOR + KEY_RING_H + 2, KEY_HEAD))
        cuts.append(slot(ix(kx), iy(ky), ix(kx + KEY_TRAVEL), iy(ky), KEY_SHANK, -1, FLOOR + KEY_RING_H + 2))
        cuts.append(slot(ix(kx), iy(ky), ix(kx + KEY_TRAVEL), iy(ky), KEY_HEAD, FLOOR, KEY_RING_H + 1))
    return solid - union(cuts)


LIP_H = 2.5


def lid():
    """The lid in its closed position, in base coordinates (plate on top)."""
    top = H
    plate = rrect(0, 0, OX, OY, R, top, top + LID, ch_bot=CH_SEAM, ch_top=CH_TOP)
    lx, ly = IX - 2 * FIT, IY - 2 * FIT
    r_in = R - WALL - FIT
    lip = rrect(ix(FIT), iy(FIT), lx, ly, r_in, top - LIP_H, top + 0.01) - \
        rrect(ix(FIT + 1.2), iy(FIT + 1.2), lx - 2.4, ly - 2.4, max(r_in - 1.2, 0.5), top - LIP_H - 1, top + 1)
    for bx, by in BOSSES:
        lip -= box(ix(bx - BOSS_D / 2 - 1.5), iy(by - BOSS_D / 2 - 1.5), top - LIP_H - 1,
                   BOSS_D + 3, BOSS_D + 3, LIP_H + 2)
    out = plate + lip
    cuts = []
    for bx, by in BOSSES:
        cuts.append(cyl(ix(bx), iy(by), top - 1, LID + 2, LID_HOLE))
        # 90-degree countersink from the top face.
        h = (LID_CSK - LID_HOLE) / 2
        cuts.append(cyl(ix(bx), iy(by), top + LID - h, h + 0.01, LID_HOLE, LID_CSK))
        cuts.append(cyl(ix(bx), iy(by), top + LID, 1, LID_CSK))
    # Vents over the buck module: rounded slots.
    for k in range(7):
        x = ix(BUCK["x0"] + 8 + k * 8)
        cuts.append(slot(x, iy(BUCK["y0"] + 6), x, iy(BUCK["y0"] + BUCK["w"] - 6), 3.2, top - 1, LID + 2))
    # Label, engraved into the top over the XY-485 / ESP rows.
    tw = text_width(LABEL)
    cuts.append(text_cutter(LABEL).translate([OX / 2 - tw / 2, iy(14.0), top + LID]))
    return out - union(cuts)


def lid_for_print(l):
    """Flip the lid so its flat top lies on the print bed."""
    return l.rotate([180, 0, 0]).translate([0, OY, H + LID])


# ------------------------------------------------------------- fit checking
def ghosts():
    """Board, connector and wiring volumes in base coordinates."""
    g = {}
    for name, b in (("buck", BUCK), ("xy485", XY485)):
        g[name] = box(ix(b["x0"]), iy(b["y0"]), iz(b["pad"]), b["l"], b["w"], b["pcb"] + b["top"])
    z = ESP["lift"]
    g["esp32"] = box(ix(ESP_X0), iy(ESP["y0"]), iz(z), ESP["l"], ESP["w"], ESP["pcb"] + ESP["top"])
    for k, yy in enumerate((ESP["y0"] + 0.2, ESP["y0"] + ESP["w"] - 2.8)):
        g[f"dupont{k}"] = box(ix(ESP_X0), iy(yy), iz(z - 20), ESP["l"], 2.6, 20)
    usb_z = ESP["lift"] + ESP["pcb"] + 1.6
    g["usb_plug"] = box(ix(IX) - 0.5, iy(ESP_CY - 6), iz(usb_z - 3.25), 25, 12, 6.5)
    for label, gy in GX:
        g[f"gx_{label}"] = cyl_x(WALL + 0.05, iy(gy), iz(GX_Z), GX_NUT_T, GX_NUT_D) + \
            cyl_x(WALL + 0.05, iy(gy), iz(GX_Z), GX_DEPTH, GX_BODY_D)
    for k, (kx, ky) in enumerate(keys()):
        # Screw head (pan head, 3 mm tall) anywhere along the slot, standing on the floor.
        g[f"screwhead{k}"] = slot(ix(kx), iy(ky), ix(kx + KEY_TRAVEL), iy(ky), KEY_HEAD - 0.4,
                                  FLOOR + 0.05, 3.0)
    return g


def check(b, l):
    ok = True
    gs = ghosts()
    for name, gv in gs.items():
        v = (b ^ gv).volume()
        if v > 1e-3:
            print(f"  CLASH  {name} overlaps the base by {v:.1f} mm^3")
            ok = False
        v = (l ^ gv).volume()
        if v > 1e-3:
            print(f"  CLASH  lid hits {name} by {v:.1f} mm^3")
            ok = False
    names = list(gs)
    group = {"esp32", "dupont0", "dupont1", "usb_plug"}
    for i, a in enumerate(names):
        for c in names[i + 1:]:
            if {a, c} <= group:
                continue
            v = (gs[a] ^ gs[c]).volume()
            if v > 1e-3:
                print(f"  CLASH  {a} overlaps {c} by {v:.1f} mm^3")
                ok = False
    v = (l ^ b).volume()
    if v > 1e-3:
        print(f"  CLASH  lid overlaps base by {v:.1f} mm^3")
        ok = False
    return ok, l, gs


# ------------------------------------------------------------------- output
def write_stl(m, path):
    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties)[:, :3]
    t = np.asarray(mesh.tri_verts)
    with open(path, "wb") as f:
        f.write(b"MRXBOX bridge case".ljust(80, b" "))
        f.write(struct.pack("<I", len(t)))
        for a, b, c in t:
            p0, p1, p2 = v[a], v[b], v[c]
            n = np.cross(p1 - p0, p2 - p0)
            ln = np.linalg.norm(n)
            n = n / ln if ln else n
            f.write(struct.pack("<12fH", *n, *p0, *p1, *p2, 0))


def preview(b, lid_on, gs, path):
    """Top-down cross-sections of base, boards and lid at a few heights."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon

    cuts = [("z=1: floor, keyholes", 1.0),
            (f"z={FLOOR + 4:.0f}: pads, clips, keyhole rings, back vents", FLOOR + 4),
            (f"z={FLOOR + GX_Z:.0f}: boards, ribs, Dupont space, GX12 sockets", FLOOR + GX_Z),
            (f"z={FLOOR + 25:.1f}: ESP32, USB-C opening", FLOOR + 25.2),
            (f"z={H - 1:.0f}: lid lip", H - 1),
            (f"z={H + LID - 0.3:.1f}: lid top, vents, label, countersinks", H + LID - 0.3)]
    fig, axs = plt.subplots(2, 3, figsize=(16, 11))
    for ax, (title, z) in zip(axs.flat, cuts):
        for m, fc in ((b, "#8aa0b8"), (lid_on, "#c7a77f")):
            for poly in m.slice(z).to_polygons():
                ax.add_patch(Polygon(poly, closed=True, fc=fc, ec="k", lw=0.4))
        for name, gv in gs.items():
            for poly in gv.slice(z).to_polygons():
                ax.add_patch(Polygon(poly, closed=True, fc="#e377c2" if name.startswith("gx") else "#2ca02c",
                                     alpha=0.35, ec="k", lw=0.3))
        ax.set_xlim(-8, OX + 30)
        ax.set_ylim(-2, OY + 2)
        ax.set_aspect("equal")
        ax.set_title(title, fontsize=9)
        ax.grid(alpha=0.2)
    fig.suptitle("Cross-sections: grey = base, tan = lid, translucent = boards, leads and connectors", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=100)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    a = ap.parse_args()
    b, l = base(), lid()
    ok, lid_on, gs = check(b, l)
    for name, m in (("base", b), ("lid", l)):
        if m.status().name != "NoError" or m.genus() < 0:
            print(f"  BAD MESH {name}: {m.status()}")
            ok = False
    write_stl(b, os.path.join(a.out, "base.stl"))
    lp = lid_for_print(l)
    assert abs(lp.bounding_box()[2]) < 1e-4, "lid not on the bed"
    write_stl(lp, os.path.join(a.out, "lid.stl"))
    print(f"outer {OX:.1f} x {OY:.1f} x {H + LID:.1f} mm")
    print(f"base {b.volume() / 1000:.1f} cm^3, lid {l.volume() / 1000:.1f} cm^3")
    print("fit check:", "OK" if ok else "FAILED")
    if a.preview:
        preview(b, lid_on, gs, os.path.join(a.out, "preview.png"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
