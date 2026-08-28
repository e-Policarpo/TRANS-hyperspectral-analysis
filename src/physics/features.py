"""
Feature type system for mixed-coordinate quantum well definitions.

Each feature stores its geometry in its natural coordinate system and
provides a `contains(X, Y, Z=None)` method that tests Cartesian meshgrid
arrays against the feature region, returning a boolean mask.

For smooth potentials (Gaussian), `potential_at(X, Y, Z=None)` returns V(r)
in eV on the same grid.

The simulation grid is always Cartesian; features just define which grid
points lie inside a given region. The geometry itself is exact — a sphere's
test is r <= R and a wedge's is an angle — so what is Cartesian is the
*sampling*, not the shape. See ``build_potential_from_features`` for what
that costs and how ``subsample`` pays it back.
"""

import itertools

import numpy as np


#: What a feature is, as a stable key. The display strings live in
#: :data:`KIND_LABELS` and are the only ones a UI should show — nothing here
#: compares a label.
KIND_LABELS = {
    "segment": "Segment",
    "gaussian": "Gaussian",
    "rect": "Rectangle",
    "triangle": "Triangle",
    "circle": "Circle",
    "ellipse": "Ellipse",
    "wedge": "Wedge",
    "box": "Box",
    "sphere": "Sphere",
    "cylinder": "Cylinder",
    "pyramid": "Pyramid",
    "prism": "Prism",
    "cone": "Cone",
    "lens": "Lens",
}


# ══════════════════════════════════════════════════════════════════════════════
# 1-D Features
# ══════════════════════════════════════════════════════════════════════════════

class SegmentFeature1D:
    """1D rectangular well/barrier: V = V0 for x in [x0, x0+width]."""
    kind = "segment"

    def __init__(self, x0_nm, width_nm, V0_eV, meff=1.0):
        self.x0 = x0_nm
        self.width = width_nm
        self.V0 = V0_eV
        self.meff = meff

    def contains(self, X):
        return (X >= self.x0) & (X <= self.x0 + self.width)

    def center_nm(self):
        return np.array([self.x0 + self.width / 2])

    def label(self, idx):
        return f"F{idx}: Seg x0={self.x0:.1f} w={self.width:.1f}nm V={self.V0:.2f}eV"


class GaussianFeature1D:
    """1D Gaussian potential: V = V0 * exp(-((x-cx)/sigma)^2 / 2)."""
    kind = "gaussian"

    def __init__(self, cx_nm, sigma_nm, V0_eV, meff=1.0):
        self.cx = cx_nm
        self.sigma = sigma_nm
        self.V0 = V0_eV
        self.meff = meff

    def contains(self, X):
        return np.abs(X - self.cx) <= 3 * self.sigma

    def potential_at(self, X):
        """Returns V in eV (not Joules) — caller converts."""
        return self.V0 * np.exp(-0.5 * ((X - self.cx) / self.sigma) ** 2)

    def center_nm(self):
        return np.array([self.cx])

    def label(self, idx):
        return f"F{idx}: Gauss c={self.cx:.1f} σ={self.sigma:.1f}nm V={self.V0:.2f}eV"


# ══════════════════════════════════════════════════════════════════════════════
# 2-D Features
# ══════════════════════════════════════════════════════════════════════════════

class RectFeature2D:
    """Rectangle in Cartesian coords: (x0, y0) is lower-left corner."""
    kind = "rect"

    def __init__(self, x0_nm, y0_nm, w_nm, h_nm, V0_eV, meff=1.0):
        self.x0, self.y0 = x0_nm, y0_nm
        self.w, self.h = w_nm, h_nm
        self.V0 = V0_eV
        self.meff = meff

    def contains(self, X, Y):
        return ((X >= self.x0) & (X <= self.x0 + self.w) &
                (Y >= self.y0) & (Y <= self.y0 + self.h))

    def center_nm(self):
        return np.array([self.x0 + self.w / 2, self.y0 + self.h / 2])

    def label(self, idx):
        return (f"F{idx}: Rect ({self.x0:.1f},{self.y0:.1f}) "
                f"{self.w:.1f}×{self.h:.1f}nm V={self.V0:.2f}eV")


class TriangleFeature2D:
    """Isoceles triangle, apex toward +y, base on y = cy - h/2.

    The taper is the cone's, read in the plane: full width w at the base,
    closing linearly to a point at the apex. Keeping the two the same means a
    triangle and a side view of a cone never disagree about which end is the
    apex or where the base sits.
    """
    kind = "triangle"

    def __init__(self, cx_nm, cy_nm, w_nm, h_nm, V0_eV, meff=1.0):
        self.cx, self.cy = cx_nm, cy_nm
        self.w, self.h = w_nm, h_nm
        self.V0 = V0_eV
        self.meff = meff

    def contains(self, X, Y):
        y_bot = self.cy - self.h / 2
        y_top = self.cy + self.h / 2
        y_ok = (Y >= y_bot) & (Y <= y_top)

        # A height of zero has no interior to taper through, so the divisor is
        # held off zero rather than dividing by it; the band it leaves is the
        # single line y = cy, and the width there is 0, so nothing is inside.
        h_safe = self.h if abs(self.h) > 1e-12 else 1e-12
        frac = np.clip((y_top - Y) / h_safe, 0, 1)
        half_width = self.w / 2 * frac
        return y_ok & (np.abs(X - self.cx) <= half_width)

    def center_nm(self):
        return np.array([self.cx, self.cy])

    def label(self, idx):
        return (f"F{idx}: Tri c=({self.cx:.1f},{self.cy:.1f}) "
                f"{self.w:.1f}×{self.h:.1f}nm V={self.V0:.2f}eV")


class CircleFeature2D:
    """Full circle (or ring) with Cartesian centre."""
    kind = "circle"

    def __init__(self, cx_nm, cy_nm, r_nm, V0_eV, meff=1.0):
        self.cx, self.cy = cx_nm, cy_nm
        self.r = r_nm
        self.V0 = V0_eV
        self.meff = meff

    def contains(self, X, Y):
        return (X - self.cx) ** 2 + (Y - self.cy) ** 2 <= self.r ** 2

    def center_nm(self):
        return np.array([self.cx, self.cy])

    def label(self, idx):
        return (f"F{idx}: Circ c=({self.cx:.1f},{self.cy:.1f}) "
                f"R={self.r:.1f}nm V={self.V0:.2f}eV")


class EllipseFeature2D:
    """Ellipse with Cartesian centre and semi-axes."""
    kind = "ellipse"

    def __init__(self, cx_nm, cy_nm, a_nm, b_nm, V0_eV, meff=1.0):
        self.cx, self.cy = cx_nm, cy_nm
        self.a, self.b = a_nm, b_nm
        self.V0 = V0_eV
        self.meff = meff

    def contains(self, X, Y):
        return ((X - self.cx) / self.a) ** 2 + ((Y - self.cy) / self.b) ** 2 <= 1

    def center_nm(self):
        return np.array([self.cx, self.cy])

    def label(self, idx):
        return (f"F{idx}: Ellipse c=({self.cx:.1f},{self.cy:.1f}) "
                f"a={self.a:.1f} b={self.b:.1f}nm V={self.V0:.2f}eV")


class WedgeFeature2D:
    """Angular wedge / sector with Cartesian centre."""
    kind = "wedge"

    def __init__(self, cx_nm, cy_nm, r_inner_nm, r_outer_nm,
                 theta_start_deg, theta_span_deg, V0_eV, meff=1.0):
        self.cx, self.cy = cx_nm, cy_nm
        self.r_inner, self.r_outer = r_inner_nm, r_outer_nm
        self.theta_start = theta_start_deg
        self.theta_span = theta_span_deg
        self.V0 = V0_eV
        self.meff = meff

    def contains(self, X, Y):
        dx = X - self.cx
        dy = Y - self.cy
        r = np.sqrt(dx ** 2 + dy ** 2)
        theta = np.degrees(np.arctan2(dy, dx)) % 360
        t0 = self.theta_start % 360
        t1 = (self.theta_start + self.theta_span) % 360

        r_ok = (r >= self.r_inner) & (r <= self.r_outer)
        if t0 <= t1:
            th_ok = (theta >= t0) & (theta <= t1)
        else:
            th_ok = (theta >= t0) | (theta <= t1)
        return r_ok & th_ok

    def center_nm(self):
        r_mid = (self.r_inner + self.r_outer) / 2
        t_mid = np.radians(self.theta_start + self.theta_span / 2)
        return np.array([self.cx + r_mid * np.cos(t_mid),
                         self.cy + r_mid * np.sin(t_mid)])

    def label(self, idx):
        return (f"F{idx}: Wedge c=({self.cx:.1f},{self.cy:.1f}) "
                f"r=[{self.r_inner:.1f},{self.r_outer:.1f}] "
                f"θ={self.theta_start:.0f}°+{self.theta_span:.0f}° V={self.V0:.2f}eV")


class GaussianFeature2D:
    """2D Gaussian potential hill/well."""
    kind = "gaussian"

    def __init__(self, cx_nm, cy_nm, sigma_x_nm, sigma_y_nm, V0_eV, meff=1.0):
        self.cx, self.cy = cx_nm, cy_nm
        self.sx, self.sy = sigma_x_nm, sigma_y_nm
        self.V0 = V0_eV
        self.meff = meff

    def contains(self, X, Y):
        return ((X - self.cx) ** 2 / self.sx ** 2 +
                (Y - self.cy) ** 2 / self.sy ** 2) <= 9  # 3-sigma

    def potential_at(self, X, Y):
        return self.V0 * np.exp(-0.5 * (
            ((X - self.cx) / self.sx) ** 2 +
            ((Y - self.cy) / self.sy) ** 2))

    def center_nm(self):
        return np.array([self.cx, self.cy])

    def label(self, idx):
        return (f"F{idx}: Gauss c=({self.cx:.1f},{self.cy:.1f}) "
                f"σ=({self.sx:.1f},{self.sy:.1f})nm V={self.V0:.2f}eV")


# ══════════════════════════════════════════════════════════════════════════════
# 3-D Features
# ══════════════════════════════════════════════════════════════════════════════

class BoxFeature3D:
    """Rectangular box (Cartesian).  cx/cy/cz = centre."""
    kind = "box"

    def __init__(self, cx_nm, cy_nm, cz_nm, Lx_nm, Ly_nm, Lz_nm,
                 V0_eV, meff=1.0):
        self.cx, self.cy, self.cz = cx_nm, cy_nm, cz_nm
        self.Lx, self.Ly, self.Lz = Lx_nm, Ly_nm, Lz_nm
        self.V0 = V0_eV
        self.meff = meff

    def contains(self, X, Y, Z):
        return ((X >= self.cx - self.Lx / 2) & (X <= self.cx + self.Lx / 2) &
                (Y >= self.cy - self.Ly / 2) & (Y <= self.cy + self.Ly / 2) &
                (Z >= self.cz - self.Lz / 2) & (Z <= self.cz + self.Lz / 2))

    def center_nm(self):
        return np.array([self.cx, self.cy, self.cz])

    def label(self, idx):
        return (f"F{idx}: Box ({self.cx:.1f},{self.cy:.1f},{self.cz:.1f}) "
                f"{self.Lx:.1f}×{self.Ly:.1f}×{self.Lz:.1f}nm V={self.V0:.2f}eV")


class SphereFeature3D:
    """Full sphere or spherical cap.  Centre in Cartesian nm."""
    kind = "sphere"

    def __init__(self, cx_nm, cy_nm, cz_nm, R_nm, V0_eV, meff=1.0,
                 theta_min_deg=0, theta_max_deg=180):
        self.cx, self.cy, self.cz = cx_nm, cy_nm, cz_nm
        self.R = R_nm
        self.V0 = V0_eV
        self.meff = meff
        self.theta_min = np.radians(theta_min_deg)
        self.theta_max = np.radians(theta_max_deg)

    def contains(self, X, Y, Z):
        dx = X - self.cx
        dy = Y - self.cy
        dz = Z - self.cz
        r = np.sqrt(dx ** 2 + dy ** 2 + dz ** 2)
        r_ok = r <= self.R

        # Polar angle relative to +z axis of feature
        theta = np.arccos(np.clip(dz / np.maximum(r, 1e-30), -1, 1))
        th_ok = (theta >= self.theta_min) & (theta <= self.theta_max)
        return r_ok & th_ok

    def center_nm(self):
        return np.array([self.cx, self.cy, self.cz])

    def label(self, idx):
        th_str = ""
        if self.theta_min > 0.01 or self.theta_max < np.pi - 0.01:
            th_str = f" θ=[{np.degrees(self.theta_min):.0f}°,{np.degrees(self.theta_max):.0f}°]"
        return (f"F{idx}: Sphere ({self.cx:.1f},{self.cy:.1f},{self.cz:.1f}) "
                f"R={self.R:.1f}nm{th_str} V={self.V0:.2f}eV")


class CylinderFeature3D:
    """Cylinder with axis along z, centre in Cartesian nm."""
    kind = "cylinder"

    def __init__(self, cx_nm, cy_nm, cz_nm, R_nm, H_nm, V0_eV, meff=1.0):
        self.cx, self.cy, self.cz = cx_nm, cy_nm, cz_nm
        self.R, self.H = R_nm, H_nm
        self.V0 = V0_eV
        self.meff = meff

    def contains(self, X, Y, Z):
        rho2 = (X - self.cx) ** 2 + (Y - self.cy) ** 2
        z_ok = (Z >= self.cz - self.H / 2) & (Z <= self.cz + self.H / 2)
        return (rho2 <= self.R ** 2) & z_ok

    def center_nm(self):
        return np.array([self.cx, self.cy, self.cz])

    def label(self, idx):
        return (f"F{idx}: Cyl ({self.cx:.1f},{self.cy:.1f},{self.cz:.1f}) "
                f"R={self.R:.1f} H={self.H:.1f}nm V={self.V0:.2f}eV")


class PyramidFeature3D:
    """N-gonal pyramid (base on z = cz - H/2, apex at cz + H/2).

    n_sides controls the base polygon: 3=triangular, 4=square,
    5=pentagonal, 6=hexagonal, etc.  ``base`` is the circumradius
    of the regular polygon (centre to vertex).
    """
    kind = "pyramid"

    def __init__(self, cx_nm, cy_nm, cz_nm, base_nm, H_nm, V0_eV,
                 meff=1.0, n_sides=4):
        self.cx, self.cy, self.cz = cx_nm, cy_nm, cz_nm
        self.base, self.H = base_nm, H_nm
        self.V0 = V0_eV
        self.meff = meff
        self.n_sides = max(3, int(n_sides))
        # Pre-compute half-plane normals for the regular polygon
        # Each edge of the polygon defines an inward-pointing half-plane.
        self._edge_normals = []  # list of (nx, ny, d_max) at unit scale
        angles = [2 * np.pi * k / self.n_sides for k in range(self.n_sides)]
        verts = [(np.cos(a), np.sin(a)) for a in angles]
        for k in range(self.n_sides):
            x0, y0 = verts[k]
            x1, y1 = verts[(k + 1) % self.n_sides]
            # Inward normal (pointing towards centre)
            nx = -(y1 - y0)
            ny = x1 - x0
            ln = np.sqrt(nx**2 + ny**2)
            nx, ny = nx / ln, ny / ln
            # Max signed distance from centre for points on the edge
            d_max = nx * x0 + ny * y0
            self._edge_normals.append((nx, ny, d_max))

    def contains(self, X, Y, Z):
        z_bot = self.cz - self.H / 2
        z_top = self.cz + self.H / 2
        z_ok = (Z >= z_bot) & (Z <= z_top)

        # Cross-section shrinks linearly from base at bottom to 0 at apex
        frac = np.clip((z_top - Z) / self.H, 0, 1)  # 1 at bottom, 0 at top
        R = self.base / 2 * frac  # circumradius at this z

        # Normalised displacement from centre
        dx = X - self.cx
        dy = Y - self.cy
        # Avoid division by zero where R==0 (apex)
        R_safe = np.where(R > 0, R, 1.0)

        inside = z_ok
        for nx, ny, d_max in self._edge_normals:
            dist = (nx * dx + ny * dy) / R_safe
            inside = inside & (dist >= d_max)
        # At the apex R==0, only the exact centre should be inside
        inside = inside & ((R > 0) | ((np.abs(dx) < 1e-12) & (np.abs(dy) < 1e-12)))
        return inside

    def center_nm(self):
        return np.array([self.cx, self.cy, self.cz])

    def label(self, idx):
        return (f"F{idx}: Pyr{self.n_sides} ({self.cx:.1f},{self.cy:.1f},{self.cz:.1f}) "
                f"base={self.base:.1f} H={self.H:.1f}nm V={self.V0:.2f}eV")


class PrismFeature3D:
    """N-gonal prism (uniform polygon cross-section extruded along z).

    n_sides controls the polygon: 3=triangular, 4=square,
    5=pentagonal, 6=hexagonal, etc.  ``base`` is the circumradius
    of the regular polygon (centre to vertex).
    The prism extends from z = cz - H/2  to  z = cz + H/2.
    """
    kind = "prism"

    def __init__(self, cx_nm, cy_nm, cz_nm, base_nm, H_nm, V0_eV,
                 meff=1.0, n_sides=6):
        self.cx, self.cy, self.cz = cx_nm, cy_nm, cz_nm
        self.base, self.H = base_nm, H_nm
        self.V0 = V0_eV
        self.meff = meff
        self.n_sides = max(3, int(n_sides))
        # Pre-compute half-plane normals (same as Pyramid, but no tapering)
        self._edge_normals = []
        angles = [2 * np.pi * k / self.n_sides for k in range(self.n_sides)]
        verts = [(np.cos(a), np.sin(a)) for a in angles]
        for k in range(self.n_sides):
            x0, y0 = verts[k]
            x1, y1 = verts[(k + 1) % self.n_sides]
            nx = -(y1 - y0)
            ny = x1 - x0
            ln = np.sqrt(nx**2 + ny**2)
            nx, ny = nx / ln, ny / ln
            d_max = nx * x0 + ny * y0
            self._edge_normals.append((nx, ny, d_max))

    def contains(self, X, Y, Z):
        z_bot = self.cz - self.H / 2
        z_top = self.cz + self.H / 2
        inside = (Z >= z_bot) & (Z <= z_top)

        R = self.base / 2  # circumradius (constant along z)
        dx = X - self.cx
        dy = Y - self.cy
        R_safe = max(R, 1e-12)

        for nx, ny, d_max in self._edge_normals:
            dist = (nx * dx + ny * dy) / R_safe
            inside = inside & (dist >= d_max)
        return inside

    def center_nm(self):
        return np.array([self.cx, self.cy, self.cz])

    def label(self, idx):
        return (f"F{idx}: Prism{self.n_sides} ({self.cx:.1f},{self.cy:.1f},"
                f"{self.cz:.1f}) base={self.base:.1f} H={self.H:.1f}nm "
                f"V={self.V0:.2f}eV")


class ConeFeature3D:
    """Cone with apex up, base on z = cz - H/2."""
    kind = "cone"

    def __init__(self, cx_nm, cy_nm, cz_nm, R_nm, H_nm, V0_eV, meff=1.0):
        self.cx, self.cy, self.cz = cx_nm, cy_nm, cz_nm
        self.R, self.H = R_nm, H_nm
        self.V0 = V0_eV
        self.meff = meff

    def contains(self, X, Y, Z):
        z_bot = self.cz - self.H / 2
        z_top = self.cz + self.H / 2
        z_ok = (Z >= z_bot) & (Z <= z_top)

        frac = np.clip((z_top - Z) / self.H, 0, 1)
        r_max = self.R * frac
        rho2 = (X - self.cx) ** 2 + (Y - self.cy) ** 2
        return z_ok & (rho2 <= r_max ** 2)

    def center_nm(self):
        return np.array([self.cx, self.cy, self.cz])

    def label(self, idx):
        return (f"F{idx}: Cone ({self.cx:.1f},{self.cy:.1f},{self.cz:.1f}) "
                f"R={self.R:.1f} H={self.H:.1f}nm V={self.V0:.2f}eV")


class GaussianFeature3D:
    """3D Gaussian potential: V0 * exp(-((x-cx)^2/2sx^2 + ...))."""
    kind = "gaussian"

    def __init__(self, cx_nm, cy_nm, cz_nm,
                 sigma_x_nm, sigma_y_nm, sigma_z_nm,
                 V0_eV, meff=1.0):
        self.cx, self.cy, self.cz = cx_nm, cy_nm, cz_nm
        self.sx, self.sy, self.sz = sigma_x_nm, sigma_y_nm, sigma_z_nm
        self.V0 = V0_eV
        self.meff = meff

    def contains(self, X, Y, Z):
        return (((X - self.cx) / self.sx) ** 2 +
                ((Y - self.cy) / self.sy) ** 2 +
                ((Z - self.cz) / self.sz) ** 2) <= 9  # 3-sigma

    def potential_at(self, X, Y, Z):
        return self.V0 * np.exp(-0.5 * (
            ((X - self.cx) / self.sx) ** 2 +
            ((Y - self.cy) / self.sy) ** 2 +
            ((Z - self.cz) / self.sz) ** 2))

    def center_nm(self):
        return np.array([self.cx, self.cy, self.cz])

    def label(self, idx):
        return (f"F{idx}: Gauss ({self.cx:.1f},{self.cy:.1f},{self.cz:.1f}) "
                f"σ=({self.sx:.1f},{self.sy:.1f},{self.sz:.1f})nm V={self.V0:.2f}eV")


class LensFeature3D:
    """Lens-shaped quantum dot (a spherical cap) — common InAs/GaAs QD shape.

    Defined by base radius R and height H about a centre at (cx, cy, cz):
    the base sits on z = cz - H/2 and the apex on z = cz + H/2, the same
    convention as the box, the sphere and the cylinder, so the editor's
    position and extent tables describe it correctly.
    """
    kind = "lens"

    def __init__(self, cx_nm, cy_nm, cz_nm, R_nm, H_nm, V0_eV, meff=1.0):
        self.cx, self.cy, self.cz = cx_nm, cy_nm, cz_nm
        self.R, self.H = R_nm, H_nm
        self.V0 = V0_eV
        self.meff = meff
        # Sphere radius from R and H:  R_sphere = (R^2 + H^2) / (2*H).
        # Held off zero the way PrismFeature3D holds its base off zero: a
        # height of 0 is a shape with nothing in it, not an error worth
        # raising from a constructor the preview calls on every keystroke.
        self._Rs = (R_nm ** 2 + H_nm ** 2) / (2.0 * max(abs(H_nm), 1e-12))

    def contains(self, X, Y, Z):
        rho2 = (X - self.cx) ** 2 + (Y - self.cy) ** 2
        z_rel = Z - (self.cz - self.H / 2)  # height above the base plane

        # Above the base plane and below the spherical cap
        z_ok = (z_rel >= 0) & (z_rel <= self.H)
        # The cap's sphere is centred Rs - H *below* the base, which is what
        # makes the section R wide there and closes it to a point at z_rel=H.
        sphere_ok = rho2 + (z_rel - (self.H - self._Rs)) ** 2 <= self._Rs ** 2
        return z_ok & sphere_ok

    def center_nm(self):
        return np.array([self.cx, self.cy, self.cz])

    def label(self, idx):
        return (f"F{idx}: Lens ({self.cx:.1f},{self.cy:.1f},{self.cz:.1f}) "
                f"R={self.R:.1f} H={self.H:.1f}nm V={self.V0:.2f}eV")


# ══════════════════════════════════════════════════════════════════════════════
# Unified potential builder
# ══════════════════════════════════════════════════════════════════════════════

def _cell_offsets(axis, subsample: int):
    """Where a cell's sub-samples sit, relative to its centre.

    An axis of one point has no cell to divide, and a preview that has
    already been sliced hands exactly that in for the axis it cut — which
    must not be averaged through, or the slice stops being a slice.
    """
    axis = np.asarray(axis, dtype=float)
    if subsample <= 1 or axis.size < 2:
        return np.zeros(1)
    step = float(axis[1] - axis[0])
    return ((np.arange(subsample) + 0.5) / subsample - 0.5) * step


def _occupancy(feat, meshes, offsets):
    """What fraction of each cell the feature covers, in [0, 1]."""
    covered = None
    samples = 0
    for shifts in itertools.product(*offsets):
        inside = feat.contains(*[mesh + shift
                                 for mesh, shift in zip(meshes, shifts)])
        covered = np.asarray(inside, dtype=float) if covered is None \
            else covered + inside
        samples += 1
    return covered / samples


def build_potential_from_features(features, grid_arrays, V_barrier_eV=0.0,
                                  subsample: int = 1):
    """
    Build potential on a Cartesian grid from a list of Feature objects.

    Parameters
    ----------
    features : list of Feature objects (any mix of types)
    grid_arrays : tuple of 1D arrays in nm
        1D: (x,)     2D: (x, y)     3D: (x, y, z)
    V_barrier_eV : float — background potential
    subsample : int
        How many sub-samples per cell per axis. The default of 1 asks
        ``contains`` at the cell centre only, so every cell is wholly in or
        wholly out: a round feature becomes a staircase of whole cells, its
        volume jumps as it is dragged across the grid, and the preview draws
        it as blocks. Above 1, a boundary cell takes the fraction of itself
        the feature actually covers and the potential there is that fraction
        of the depth — the standard cure for a curved boundary on a square
        grid, at ``subsample ** ndim`` evaluations of ``contains``.

    Returns
    -------
    V : ndarray in Joules
    meshgrids : tuple of meshgrid arrays in nm
    """
    from scipy.constants import e as eV_to_J

    meshes = np.meshgrid(*grid_arrays, indexing='ij')
    offsets = [_cell_offsets(axis, subsample) for axis in grid_arrays]

    V = np.full(meshes[0].shape, V_barrier_eV * eV_to_J)
    for feat in features:
        depth = (feat.potential_at(*meshes) * eV_to_J
                 if hasattr(feat, 'potential_at') else feat.V0 * eV_to_J)
        # Blended rather than assigned, so a partly-covered cell is partly
        # deep. At subsample=1 the fraction is 0 or 1 and this is the plain
        # overwrite it replaces, feature by feature, in order. Guarded by
        # `covered > 0` because the blend multiplies rather than selects:
        # 0.0 * nan is nan, so a `potential_at` that goes non-finite anywhere
        # — a Gaussian typed with sigma 0 does — would otherwise poison cells
        # the feature does not even cover, and the solve dies later with an
        # unrelated LAPACK message.
        covered = _occupancy(feat, meshes, offsets)
        V = np.where(covered > 0, covered * depth + (1.0 - covered) * V, V)
    return V, tuple(meshes)


# Registry for UI dropdowns
FEATURE_TYPES_1D = [SegmentFeature1D, GaussianFeature1D]
FEATURE_TYPES_2D = [RectFeature2D, TriangleFeature2D, CircleFeature2D,
                    EllipseFeature2D, WedgeFeature2D, GaussianFeature2D]
FEATURE_TYPES_3D = [BoxFeature3D, SphereFeature3D, CylinderFeature3D,
                    PyramidFeature3D, PrismFeature3D, ConeFeature3D,
                    GaussianFeature3D, LensFeature3D]
