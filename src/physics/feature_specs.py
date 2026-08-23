"""
Features as plain data, and back again.

The feature classes in :mod:`~src.physics.features` are the physics: they
know how to say whether a grid point is inside them. What an editor needs is
the other half — a feature as a **map of numbers** it can list, edit, drag,
save and hand across the QML bridge, and a way back to the object that builds
a potential.

One table does both. :data:`FEATURE_FIELDS` names each kind's parameters in
the order a form should show them, and everything else here is derived from
it: constructing, reading back, moving, and the labels a UI puts on the
fields. Adding a shape means adding one row.

Positions and sizes are in nm, depths in eV — the package's units, so nothing
converts on the way through.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from src.physics import features as _features

logger = logging.getLogger(__name__)


#: ``kind -> (class, field names in constructor order)``. The trailing
#: ``V0``/``meff`` are common to every kind and appended by the helpers, so
#: the rows here are only what makes each shape itself.
FEATURE_FIELDS: Dict[str, Tuple[type, Tuple[str, ...]]] = {
    # 1D
    'segment': (_features.SegmentFeature1D, ('x0', 'width')),
    'gaussian_1d': (_features.GaussianFeature1D, ('cx', 'sigma')),
    # 2D
    'rect': (_features.RectFeature2D, ('x0', 'y0', 'w', 'h')),
    'circle': (_features.CircleFeature2D, ('cx', 'cy', 'r')),
    'ellipse': (_features.EllipseFeature2D, ('cx', 'cy', 'a', 'b')),
    'wedge': (_features.WedgeFeature2D,
              ('cx', 'cy', 'r_inner', 'r_outer', 'theta_start', 'theta_span')),
    'gaussian_2d': (_features.GaussianFeature2D, ('cx', 'cy', 'sx', 'sy')),
    # 3D
    'box': (_features.BoxFeature3D, ('cx', 'cy', 'cz', 'Lx', 'Ly', 'Lz')),
    'sphere': (_features.SphereFeature3D, ('cx', 'cy', 'cz', 'R')),
    'cylinder': (_features.CylinderFeature3D, ('cx', 'cy', 'cz', 'R', 'H')),
    'pyramid': (_features.PyramidFeature3D, ('cx', 'cy', 'cz', 'base', 'H')),
    'prism': (_features.PrismFeature3D, ('cx', 'cy', 'cz', 'base', 'H')),
    'cone': (_features.ConeFeature3D, ('cx', 'cy', 'cz', 'R', 'H')),
    'gaussian_3d': (_features.GaussianFeature3D,
                    ('cx', 'cy', 'cz', 'sx', 'sy', 'sz')),
    'lens': (_features.LensFeature3D, ('cx', 'cy', 'cz', 'R', 'H')),
}

#: Extra integer parameters some kinds take after V0 and meff.
FEATURE_EXTRAS: Dict[str, Tuple[str, ...]] = {
    'pyramid': ('n_sides',),
    'prism': ('n_sides',),
}

#: Which kinds belong to which editor. A 1D feature in a 2D domain has no
#: meaning, and offering it is how a nonsense potential gets built.
KINDS_1D = ('segment', 'gaussian_1d')
KINDS_2D = ('rect', 'circle', 'ellipse', 'wedge', 'gaussian_2d')
KINDS_3D = ('box', 'sphere', 'cylinder', 'pyramid', 'prism', 'cone',
            'gaussian_3d', 'lens')

KIND_LABELS = {
    'segment': "Segment", 'gaussian_1d': "Gaussian",
    'rect': "Rectangle", 'circle': "Circle", 'ellipse': "Ellipse",
    'wedge': "Wedge / sector", 'gaussian_2d': "Gaussian",
    'box': "Box", 'sphere': "Sphere", 'cylinder': "Cylinder",
    'pyramid': "Pyramid", 'prism': "Prism", 'cone': "Cone",
    'gaussian_3d': "Gaussian", 'lens': "Lens",
}

#: What each field is called on screen, and its unit. Anything not named here
#: falls back to the field name itself.
FIELD_LABELS = {
    'x0': "x₀ (nm)", 'y0': "y₀ (nm)", 'width': "width (nm)",
    'w': "width (nm)", 'h': "height (nm)",
    'cx': "x (nm)", 'cy': "y (nm)", 'cz': "z (nm)",
    'r': "radius (nm)", 'R': "radius (nm)", 'H': "height (nm)",
    'a': "semi-axis a (nm)", 'b': "semi-axis b (nm)",
    'base': "base radius (nm)",
    'r_inner': "inner radius (nm)", 'r_outer': "outer radius (nm)",
    'theta_start': "start angle (°)", 'theta_span': "span (°)",
    'sigma': "σ (nm)", 'sx': "σx (nm)", 'sy': "σy (nm)", 'sz': "σz (nm)",
    'Lx': "Lx (nm)", 'Ly': "Ly (nm)", 'Lz': "Lz (nm)",
    'V0': "depth V₀ (eV)", 'meff': "m*", 'n_sides': "sides",
}

#: Sensible starting values, so "add a feature" produces something visible
#: rather than a zero-sized shape at the origin.
FIELD_DEFAULTS = {
    'width': 4.0, 'w': 4.0, 'h': 4.0, 'r': 2.0, 'R': 2.0, 'H': 4.0,
    'a': 3.0, 'b': 2.0, 'base': 3.0, 'r_inner': 1.0, 'r_outer': 3.0,
    'theta_start': 0.0, 'theta_span': 90.0,
    'sigma': 2.0, 'sx': 2.0, 'sy': 2.0, 'sz': 2.0,
    'Lx': 4.0, 'Ly': 4.0, 'Lz': 4.0, 'n_sides': 4,
}

#: Which fields are the feature's position, per kind — what a drag moves.
#: A rectangle is anchored by its corner and everything else by its centre,
#: which is why this cannot be one rule.
POSITION_FIELDS = {
    'segment': ('x0',), 'gaussian_1d': ('cx',),
    'rect': ('x0', 'y0'),
    'circle': ('cx', 'cy'), 'ellipse': ('cx', 'cy'),
    'wedge': ('cx', 'cy'), 'gaussian_2d': ('cx', 'cy'),
    'box': ('cx', 'cy', 'cz'), 'sphere': ('cx', 'cy', 'cz'),
    'cylinder': ('cx', 'cy', 'cz'), 'pyramid': ('cx', 'cy', 'cz'),
    'prism': ('cx', 'cy', 'cz'), 'cone': ('cx', 'cy', 'cz'),
    'gaussian_3d': ('cx', 'cy', 'cz'), 'lens': ('cx', 'cy', 'cz'),
}


def field_names(kind: str) -> Tuple[str, ...]:
    """Every editable field of a kind, in the order a form should show them."""
    if kind not in FEATURE_FIELDS:
        raise ValueError(f"unknown feature kind: {kind!r}")
    return FEATURE_FIELDS[kind][1] + ('V0', 'meff') + FEATURE_EXTRAS.get(kind, ())


def default_spec(kind: str, position=None, V0_eV: float = -0.3,
                 meff: float = 0.067) -> dict:
    """A new feature of ``kind``, optionally centred on ``position``.

    ``position`` is where the user clicked, in nm — one value per axis of the
    editor. A rectangle anchors at its corner, so it is offset by half its
    size to land where the click was.
    """
    spec = {'kind': kind}
    for name in field_names(kind):
        if name == 'V0':
            spec[name] = float(V0_eV)
        elif name == 'meff':
            spec[name] = float(meff)
        else:
            spec[name] = FIELD_DEFAULTS.get(name, 0.0)

    if position:
        _place(spec, kind, position)
    return spec


def _place(spec: dict, kind: str, position) -> None:
    """Put a spec's position fields at ``position`` (nm, one per axis)."""
    fields = POSITION_FIELDS.get(kind, ())
    for axis, name in enumerate(fields):
        if axis >= len(position):
            break
        value = float(position[axis])
        # A rectangle is anchored at its corner: centring it on the click
        # means backing off by half its size, or it lands up and to the right.
        if kind == 'rect':
            value -= spec.get('w' if name == 'x0' else 'h', 0.0) / 2.0
        elif kind == 'segment' and name == 'x0':
            value -= spec.get('width', 0.0) / 2.0
        spec[name] = value


def build_feature(spec: dict):
    """One feature object from a spec map.

    Unknown keys are ignored rather than refused: a spec that has been
    through a UI carries selection state and labels the physics has no use
    for.
    """
    spec = dict(spec or {})
    kind = str(spec.get('kind', ''))
    if kind not in FEATURE_FIELDS:
        raise ValueError(f"unknown feature kind: {kind!r}")

    cls, geometry = FEATURE_FIELDS[kind]
    args = [float(spec.get(name, FIELD_DEFAULTS.get(name, 0.0)))
            for name in geometry]
    args.append(float(spec.get('V0', 0.0)))
    args.append(float(spec.get('meff', 1.0)))
    for name in FEATURE_EXTRAS.get(kind, ()):
        args.append(int(spec.get(name, FIELD_DEFAULTS.get(name, 3))))
    return cls(*args)


def build_features(specs) -> List:
    """Every spec that builds, in order.

    One bad feature does not cost the user the rest of the model: it is
    logged and skipped, because the alternative is a potential that will not
    render at all and no way to see which entry is wrong.
    """
    built = []
    for index, spec in enumerate(specs or []):
        try:
            built.append(build_feature(spec))
        except Exception as exc:
            logger.warning("Feature %d (%s) could not be built: %s",
                           index, (spec or {}).get('kind', '?'), exc)
    return built


def spec_from_feature(feature, kind: Optional[str] = None) -> dict:
    """A spec map read back off a feature object."""
    kind = kind or getattr(feature, 'kind', '')
    # The 1D and 2D/3D Gaussians share a `kind`, so it cannot identify them
    # on its own; the class does.
    for name, (cls, _fields) in FEATURE_FIELDS.items():
        if type(feature) is cls:
            kind = name
            break
    if kind not in FEATURE_FIELDS:
        raise ValueError(f"unknown feature kind: {kind!r}")

    spec = {'kind': kind}
    for name in field_names(kind):
        value = getattr(feature, name, FIELD_DEFAULTS.get(name, 0.0))
        spec[name] = int(value) if name == 'n_sides' else float(value)
    return spec


def move_spec(spec: dict, position, axes=(0, 1)) -> dict:
    """A copy of ``spec`` moved so its position lands on ``position``.

    ``axes`` says which of the feature's axes the two coordinates are — the
    3D editor shows one plane at a time, so a drag on the XZ view moves x and
    z and leaves y alone.
    """
    moved = dict(spec)
    kind = str(moved.get('kind', ''))
    fields = POSITION_FIELDS.get(kind, ())
    for value, axis in zip(position, axes):
        if axis >= len(fields):
            continue
        name = fields[axis]
        offset = 0.0
        if kind == 'rect':
            offset = moved.get('w' if name == 'x0' else 'h', 0.0) / 2.0
        elif kind == 'segment' and name == 'x0':
            offset = moved.get('width', 0.0) / 2.0
        moved[name] = float(value) - offset
    return moved


def spec_position(spec: dict, axes=(0, 1)) -> Tuple[float, ...]:
    """Where a spec sits, on the axes asked for — the centre, always.

    The inverse of :func:`move_spec`, including the corner-anchor correction,
    so a hit test and a drag agree about where a feature is.
    """
    kind = str(spec.get('kind', ''))
    fields = POSITION_FIELDS.get(kind, ())
    out = []
    for axis in axes:
        if axis >= len(fields):
            out.append(0.0)
            continue
        name = fields[axis]
        value = float(spec.get(name, 0.0))
        if kind == 'rect':
            value += float(spec.get('w' if name == 'x0' else 'h', 0.0)) / 2.0
        elif kind == 'segment' and name == 'x0':
            value += float(spec.get('width', 0.0)) / 2.0
        out.append(value)
    return tuple(out)


def spec_extent(spec: dict, axes=(0, 1)) -> Tuple[float, ...]:
    """Half-width of a spec on each axis asked for, for hit tests and patches.

    A Gaussian has no edge, so it is taken at 3σ — the same place the
    feature's own ``contains`` stops.
    """
    kind = str(spec.get('kind', ''))
    per_axis = {
        'segment': ('width',),
        'gaussian_1d': ('sigma',),
        'rect': ('w', 'h'),
        'circle': ('r', 'r'),
        'ellipse': ('a', 'b'),
        'wedge': ('r_outer', 'r_outer'),
        'gaussian_2d': ('sx', 'sy'),
        'box': ('Lx', 'Ly', 'Lz'),
        'sphere': ('R', 'R', 'R'),
        'cylinder': ('R', 'R', 'H'),
        'pyramid': ('base', 'base', 'H'),
        'prism': ('base', 'base', 'H'),
        'cone': ('R', 'R', 'H'),
        'gaussian_3d': ('sx', 'sy', 'sz'),
        'lens': ('R', 'R', 'H'),
    }.get(kind, ())

    halves = []
    for axis in axes:
        if axis >= len(per_axis):
            halves.append(0.0)
            continue
        name = per_axis[axis]
        value = float(spec.get(name, 0.0))
        if name in ('w', 'h', 'width', 'Lx', 'Ly', 'Lz', 'H'):
            value /= 2.0            # a size, not a radius
        elif name in ('sigma', 'sx', 'sy', 'sz'):
            value *= 3.0            # a Gaussian's edge is where it stops
        halves.append(abs(value))
    return tuple(halves)
