"""
The interactive potential editor: features you can see and drag.

A 2D or 3D model is a handful of wells and barriers placed in a box, and
placing them by typing coordinates is how you end up with a potential nobody
can picture. This draws them — over the potential they make, and optionally
over the state that lives in it — and lets them be picked up and moved.

A 3D model is edited one plane at a time (XY, XZ, YZ). That is not a
compromise for the drawing's sake: dragging in a projection is exactly two
of the three coordinates, and the third stays where it was, which is what
makes the interaction unambiguous.

The mouse work is all here; the feature list itself belongs to the backend,
so this emits "the user moved feature 3 to here" and lets the owner decide
what that means.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging
from collections import namedtuple
from typing import List, Optional

import numpy as np
from PySide6.QtCore import Property, Qt, Signal, Slot

from src.physics.feature_specs import spec_extent, spec_position
from src.widgets.qml_figure_canvas import FigureCanvasItem


def _has_values(value) -> bool:
    """Whether a field handed over from QML actually carries a grid.

    `if not value` is not that test. A QVariantMap entry arrives as a list
    when the backend converted it and as a numpy array when it did not, and
    a truth test on an array of more than one element raises. This runs
    inside paint(), so raising there costs a traceback on every frame and
    an unpainted canvas rather than a message anyone can act on.
    """
    return value is not None and np.asarray(value).size > 0

logger = logging.getLogger(__name__)


#: What a plane cuts out of one feature. `offset` is how far the plane sits
#: from the feature's centre on the axis the view cannot show — zero in a 2-D
#: model, and the whole reason a section is not simply the feature's silhouette.
Cut = namedtuple("Cut", "spec kind axes centre half offset")


def _shrunk(radius: float, offset: float) -> float:
    """The radius of a sphere's (or a circle's) section, `offset` off centre."""
    return float(np.sqrt(max(0.0, radius ** 2 - offset ** 2)))


def _taper(cut: Cut) -> float:
    """How much of a cone or pyramid is left at the height being cut, in [0, 1].

    Their `contains` is `frac = clip((z_top - Z) / H, 0, 1)` and a radius of
    `R * frac`, so a cone cut halfway up is half as wide — which is why one
    drawn at its base radius in every plane is right only where it is widest.
    """
    height = abs(float(cut.spec.get('H', 0.0)))
    if height <= 0:
        return 1.0
    # offset is measured from the centre, and z_top is half a height above it
    return float(np.clip((height / 2.0 - cut.offset) / height, 0.0, 1.0))


def _outline_ellipse(cut, style):
    from matplotlib.patches import Ellipse
    return Ellipse(cut.centre, 2 * cut.half[0], 2 * cut.half[1], **style)


def _outline_circle(cut, style):
    from matplotlib.patches import Circle
    return Circle(cut.centre, cut.half[0], **style)


def _outline_sphere(cut, style):
    from matplotlib.patches import Circle
    return Circle(cut.centre, _shrunk(cut.half[0], cut.offset), **style)


def _outline_wedge(cut, style):
    from matplotlib.patches import Wedge
    if cut.axes != (0, 1):
        # WedgeFeature2D.contains takes no Z: it has no side view to draw.
        return None
    outer = float(cut.spec.get('r_outer', 1.0))
    start = float(cut.spec.get('theta_start', 0.0))
    return Wedge(cut.centre, outer, start,
                 start + float(cut.spec.get('theta_span', 90.0)),
                 width=outer - float(cut.spec.get('r_inner', 0.0)), **style)


def _outline_gaussian(cut, style):
    """A Gaussian has no edge, so 3σ — where its own `contains` stops.

    In three dimensions the hidden axis eats into the same budget of 9, so
    the ellipse in the plane shrinks as the cut moves off centre.
    """
    from matplotlib.patches import Ellipse
    scale = 1.0
    if cut.axes is not None and len(cut.spec) and cut.offset:
        hidden_sigma = 3.0 * abs(float(cut.spec.get(
            ('sx', 'sy', 'sz')[({0, 1, 2} - set(cut.axes)).pop()], 0.0)))
        if hidden_sigma > 0:
            scale = float(np.sqrt(max(0.0, 1.0 - (cut.offset / hidden_sigma) ** 2)))
    return Ellipse(cut.centre, 2 * cut.half[0] * scale,
                   2 * cut.half[1] * scale, **style)


def _outline_cylinder(cut, style):
    from matplotlib.patches import Circle, Rectangle
    if cut.axes == (0, 1):
        return Circle(cut.centre, cut.half[0], **style)
    # Down the side it is a rectangle, but only the chord of the circle
    # survives a cut that misses the axis.
    width = _shrunk(float(cut.spec.get('R', 0.0)), cut.offset)
    return Rectangle((cut.centre[0] - width, cut.centre[1] - cut.half[1]),
                     2 * width, 2 * cut.half[1], **style)


def _outline_cone(cut, style):
    from matplotlib.patches import Circle, Polygon
    radius = float(cut.spec.get('R', 0.0))
    if cut.axes == (0, 1):
        return Circle(cut.centre, radius * _taper(cut), **style)
    # A vertical cut through a cone is a hyperbola; this is its straight-line
    # reading, exact through the axis and tight beside it.
    width = _shrunk(radius, cut.offset)
    base = cut.centre[1] - cut.half[1]
    apex = base + 2 * cut.half[1] * (width / radius if radius else 1.0)
    return Polygon([(cut.centre[0] - width, base),
                    (cut.centre[0] + width, base),
                    (cut.centre[0], apex)], closed=True, **style)


def _outline_polygon(cut, style):
    """Pyramid and prism: a regular n-gon seen from above, tapering if it is
    a pyramid; a rectangle of the polygon's width seen from the side."""
    from matplotlib.patches import Polygon, RegularPolygon, Rectangle
    sides = max(3, int(cut.spec.get('n_sides', 4)))
    half_width = float(cut.spec.get('base', 0.0)) / 2.0
    tapers = cut.kind == 'pyramid'
    if cut.axes == (0, 1):
        radius = half_width * (_taper(cut) if tapers else 1.0)
        if radius <= 0:
            return None
        # -pi/2 puts a vertex on +x, where the feature's own angles put one.
        return RegularPolygon(cut.centre, sides, radius=radius,
                              orientation=-np.pi / 2, **style)
    base = cut.centre[1] - cut.half[1]
    if not tapers:
        return Rectangle((cut.centre[0] - half_width, base),
                         2 * half_width, 2 * cut.half[1], **style)
    return Polygon([(cut.centre[0] - half_width, base),
                    (cut.centre[0] + half_width, base),
                    (cut.centre[0], base + 2 * cut.half[1])],
                   closed=True, **style)


def _outline_triangle(cut, style):
    """The 2-D triangle: isoceles, apex toward +y.

    Not `_outline_polygon`: that one draws a regular n-gon around a base
    *radius*, and this shape is given a width and a height that differ. It is
    2-D, so there is no hidden axis and nothing for `offset` to do.
    """
    from matplotlib.patches import Polygon
    half_w = abs(float(cut.spec.get('w', 0.0))) / 2.0
    half_h = abs(float(cut.spec.get('h', 0.0))) / 2.0
    if half_w <= 0 or half_h <= 0:
        return None
    cx, cy = cut.centre[0], cut.centre[1]
    return Polygon([(cx - half_w, cy - half_h), (cx + half_w, cy - half_h),
                    (cx, cy + half_h)], closed=True, **style)


def _lens_sphere_radius(spec: dict) -> float:
    """The radius of the sphere a lens is a cap of, ``(R^2 + H^2) / 2H``.

    LensFeature3D computes the same number in its constructor; recomputing it
    from the spec is what keeps this file clear of the physics classes, the
    way every other outline here is driven by field names alone.
    """
    height = abs(float(spec.get('H', 0.0)))
    if height <= 0:
        return 0.0
    return (float(spec.get('R', 0.0)) ** 2 + height ** 2) / (2.0 * height)


def _outline_lens(cut, style):
    """A spherical cap: a circle from above, the cap's own profile from the side.

    The cap's sphere is centred `H - Rs` above the base plane — below it for a
    shallow lens, inside it for a tall one — and that one number places both
    views. From above, the section is that sphere's circle at the height being
    cut; from the side it is the sphere's circle at the lateral distance being
    cut, with everything below the base plane taken off. Only the base
    truncates: the cap closes to its own apex before the top of the body can
    bite.
    """
    from matplotlib.patches import Circle, Polygon
    sphere = _lens_sphere_radius(cut.spec)
    if sphere <= 0:
        return None
    height = abs(float(cut.spec.get('H', 0.0)))
    # How far the sphere's centre sits above the base of the body.
    centre_up = height - sphere

    if cut.axes == (0, 1):
        # offset is measured from cz, the centre of the body, so the height
        # above the base is offset + H/2, and the distance from the sphere's
        # centre is that less centre_up.
        radius = _shrunk(sphere, cut.offset + height / 2.0 - centre_up)
        return Circle(cut.centre, radius, **style) if radius > 0 else None

    # A vertical cut is the circle the plane takes out of the sphere, so its
    # radius falls off the axis exactly as a sphere's section does.
    arc = _shrunk(sphere, cut.offset)
    if arc <= 0 or -centre_up >= arc:        # the plane passes beside the cap
        return None
    base = cut.centre[1] - cut.half[1]
    # Where that circle crosses the base plane, as an angle from horizontal.
    start = float(np.arcsin(np.clip(-centre_up / arc, -1.0, 1.0)))
    angles = np.linspace(start, np.pi - start, 48)
    points = [(cut.centre[0] + arc * np.cos(a),
               base + centre_up + arc * np.sin(a)) for a in angles]
    # closed=True runs the base chord back from the last point to the first.
    return Polygon(points, closed=True, **style)


#: Kind -> the outline its section is. Anything absent reads as its bounding
#: rectangle, which is right for a box and for a 2-D rectangle and is the
#: honest fallback for a shape nobody has worked out yet.
OUTLINES = {
    'circle': _outline_circle,
    'ellipse': _outline_ellipse,
    'triangle': _outline_triangle,
    'wedge': _outline_wedge,
    'gaussian_2d': _outline_gaussian,
    'gaussian_3d': _outline_gaussian,
    'sphere': _outline_sphere,
    'cylinder': _outline_cylinder,
    'cone': _outline_cone,
    'lens': _outline_lens,
    'pyramid': _outline_polygon,
    'prism': _outline_polygon,
}


class PotentialCanvas(FigureCanvasItem):
    """Draws a model's features, and lets the mouse move them."""

    #: One colour per feature, cycled. Distinct rather than a gradient: they
    #: identify features in the list, they do not encode a quantity. Fixed,
    #: not themed — a feature that changed colour when the scheme did would
    #: no longer be the same feature in a screenshot, in the feature table,
    #: or in the states view, which cycles this same sequence so a wireframe
    #: there is the outline with that colour here.
    FEATURE_COLOURS = ("#5BCEFA", "#F5A9B8", "#66ff66", "#FFD700", "#FF6B6B",
                       "#9B4F96", "#00BCD4", "#FF9800", "#E91E63", "#2ECC71")
    #: The selected feature's resize handle. Also fixed, and for a sharper
    #: reason than the rest: it has to differ from all ten colours above at
    #: once, and no colour taken from a scheme can promise that.
    SELECTED_COLOUR = "#FFD700"

    #: One potential sample per this many device pixels of the plot. Two is
    #: the point where a finer grid stops showing: the image is interpolated
    #: up to the widget, and a sample per pixel would be paid for and then
    #: averaged away.
    PREVIEW_PIXELS_PER_SAMPLE = 2.0
    #: Below this the preview reads as blocks whatever the widget size;
    #: above it, the cost climbs as the square for detail nobody can see.
    PREVIEW_POINTS_MIN = 160
    PREVIEW_POINTS_MAX = 400

    #: How near a handle a click has to land, in screen pixels. In pixels and
    #: not nanometres because a handle is a fixed size on screen whatever the
    #: zoom.
    HANDLE_GRAB_PX = 9.0

    #: Which pairs of axes each projection shows.
    PROJECTIONS = {'xy': (0, 1), 'xz': (0, 2), 'yz': (1, 2)}
    AXIS_LABELS = {'xy': ("x (nm)", "y (nm)"),
                   'xz': ("x (nm)", "z (nm)"),
                   'yz': ("y (nm)", "z (nm)")}

    #: The user picked a feature (or -1 for empty space).
    featureSelected = Signal(int)
    #: A feature was dragged; the centre it should now have, in the plane
    #: being shown. The owner decides which of its coordinates that means.
    featureMoved = Signal(int, float, float)
    #: A handle was dragged; the half-size it should now have on each shown
    #: axis, in nm.
    featureResized = Signal(int, float, float)
    #: A double-click on empty space, in data coordinates.
    featureAdded = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setAcceptHoverEvents(False)

        self._features: List[dict] = []
        self._selected = -1
        self._projection = 'xy'
        self._domain = [20.0, 20.0, 20.0]
        self._potential = {}
        self._density = {}
        self._drag = None

    # ── what is being edited ─────────────────────────────────────────────

    featuresChanged = Signal()
    selectedIndexChanged = Signal()
    projectionChanged = Signal()
    domainChanged = Signal()

    # The palette itself is the base class's. This canvas needs no restyle
    # of its own: `_render` rebuilds the whole figure from the model on
    # every frame, so a colour change is already a redraw — which is what
    # the inherited `_restyle` ends with.

    def _get_projection(self):
        return self._projection

    def _set_projection(self, value):
        value = str(value or 'xy').lower()
        if value in self.PROJECTIONS and value != self._projection:
            self._projection = value
            self.projectionChanged.emit()
            self.redraw()

    #: Which plane of a 3D model is shown — and therefore which two
    #: coordinates a drag changes.
    projection = Property(str, _get_projection, _set_projection,
                          notify=projectionChanged)

    def _get_selected(self):
        return self._selected

    def _set_selected(self, index):
        index = int(index)
        if index != self._selected:
            self._selected = index
            self.selectedIndexChanged.emit()
            self.redraw()

    selectedIndex = Property(int, _get_selected, _set_selected,
                             notify=selectedIndexChanged)

    @Slot('QVariantList')
    def setFeatures(self, specs) -> None:
        """Replace the features being shown."""
        self._features = [dict(spec) for spec in (specs or [])]
        self.featuresChanged.emit()
        self.redraw()

    @Slot('QVariantList')
    def setDomain(self, domain) -> None:
        """The box the features live in: ``[Lx, Ly]`` or ``[Lx, Ly, Lz]``."""
        values = [float(v) for v in (domain or []) if float(v) > 0]
        if values:
            self._domain = (values + [values[-1], values[-1]])[:3]
            self.domainChanged.emit()
            self.redraw()

    @Slot('QVariantMap')
    def setPotential(self, potential) -> None:
        """The potential to draw underneath, as ``{x_nm, y_nm, V_eV}``.

        Optional: the outlines alone are enough to place features by, and on
        a coarse preview grid the image is the slower half of the redraw.
        """
        self._potential = dict(potential or {})
        self.redraw()

    @Slot('QVariantMap')
    def setDensity(self, density) -> None:
        """A state's |psi|² to contour over the model, or ``{}`` for none."""
        self._density = dict(density or {})
        self.redraw()

    # ── drawing ──────────────────────────────────────────────────────────

    def _axes(self):
        return self.figure.axes[0] if self.figure.axes else None

    # A slot rather than a Property, against the usual rule in this repo:
    # the rule is there so a binding updates, and this has no change signal
    # to update one — it is read once, imperatively, when the preview is
    # rebuilt, which is also the only moment its answer matters.
    @Slot(result=int)
    def previewPoints(self) -> int:
        """How many samples across the potential preview should be built.

        Sized from the plot, not fixed: a 120-sample grid stretched across
        900 device pixels is one sample per seven and a half of them, which
        is what makes the features look low-resolution however smoothly the
        edge is drawn.
        """
        pixels = max(1.0, float(self.width())) * max(1.0, float(self._dpr))
        wanted = int(round(pixels / self.PREVIEW_PIXELS_PER_SAMPLE))
        return int(np.clip(wanted, self.PREVIEW_POINTS_MIN,
                           self.PREVIEW_POINTS_MAX))

    def _shown_axes(self):
        """Which two of the model's axes the current projection shows."""
        return self.PROJECTIONS.get(self._projection, (0, 1))

    def _cut_title(self) -> str:
        """The plane on screen and where on the hidden axis it was cut.

        Empty for a 2-D model: with no hidden axis there is nothing to
        disambiguate, the axis labels already name the plane, and a title
        would only cost rows in a panel that has few to spare. `slice_at`
        missing is exactly that case — and also a preview that failed and
        handed back nothing, which degrades to the same silence.

        The position quoted is the potential's, not the density's. The two
        are cut on different grids, so after a solve they can snap up to half
        a cell apart; the potential is the one always present and the one the
        outlines are sectioned against (`_hidden_offset` reads this very
        key), so a title taken from the density would be a title that
        disagreed with the picture under it.
        """
        axes = self._shown_axes()
        hidden = ({0, 1, 2} - set(axes)).pop()
        try:
            where = float(self._potential['slice_at'])
            length = float(self._domain[hidden])
        except (KeyError, TypeError, ValueError, IndexError):
            return ""
        if not (np.isfinite(where) and length > 0):
            return ""
        # Decimals from the length of the axis, never from the value: a
        # position-dependent format changes width as the slider moves, and a
        # title that jitters while being dragged is the one moment anybody
        # is looking at it. Four significant figures of the domain, so a
        # 2000 nm box reads whole and a 4 nm one resolves its cells.
        decimals = int(np.clip(3 - int(np.floor(np.log10(length))), 0, 3))
        return (f"{self._projection.upper()} cut · "
                f"{'xyz'[hidden]} = {where:.{decimals}f} nm")

    def _render(self) -> None:
        # Rebuilt on every render rather than kept: the figure is cheap at
        # this size, and a stale axes is how a drag ends up mapping to the
        # wrong data coordinates after a resize.
        self.figure.clf()
        ax = self.figure.add_subplot(111)
        axes = self._shown_axes()

        self._draw_potential(ax)
        self._draw_density(ax)
        # Biggest first, so a small feature is never buried under a large
        # one it happens to sit behind. Only the drawing is reordered — the
        # indices, the colours and the hit test still follow the model.
        order = sorted(range(len(self._features)),
                       key=lambda i: -self._projected_area(self._features[i],
                                                           axes))
        for index in order:
            self._draw_feature(ax, index, self._features[index], axes)
        if 0 <= self._selected < len(self._features):
            self._draw_handles(ax, self._features[self._selected], axes)

        labels = self.AXIS_LABELS.get(self._projection, ("x (nm)", "y (nm)"))
        ax.set_xlabel(labels[0])
        ax.set_ylabel(labels[1])
        ax.set_xlim(0, self._domain[axes[0]])
        ax.set_ylim(0, self._domain[axes[1]])
        ax.set_aspect('equal', adjustable='box')
        self._style(ax)
        title = self._cut_title()
        if title:
            # Coloured explicitly, like the ticks and the labels: matplotlib's
            # default is near-black, which on this palette is a title nobody
            # can read.
            ax.set_title(title, color=self._foreground, fontsize=8, pad=4)
        self.figure.tight_layout(pad=0.6)

        super()._render()

    def _draw_potential(self, ax) -> None:
        x = self._potential.get('x_nm')
        y = self._potential.get('y_nm')
        values = self._potential.get('V_eV')
        if not (_has_values(x) and _has_values(y) and _has_values(values)):
            return
        grid = np.asarray(values, dtype=float)
        if grid.ndim != 2:
            return
        # Transposed because the potential is built as (x, y) and pcolormesh
        # wants (row, column) = (y, x). Getting this wrong mirrors the model
        # about its diagonal, which looks like a placement bug.
        # Interpolated, not one flat square per sample: drawing each cell as
        # a block of a single colour is the other half of why a round feature
        # looked blocky — the first half being that the cell was wholly in or
        # wholly out of it (see `build_potential_from_features`). This draws
        # the edge the sub-sampling measured rather than the lattice it was
        # measured on.
        #
        # imshow rather than pcolormesh(shading="gouraud"): the grid is
        # uniform, so an image is the honest description of it, and gouraud
        # leaves a visible seam between its triangles across a flat region.
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        half_x = (x[1] - x[0]) / 2.0 if x.size > 1 else 0.5
        half_y = (y[1] - y[0]) / 2.0 if y.size > 1 else 0.5
        ax.imshow(grid.T, cmap="viridis", alpha=0.85, origin="lower",
                  interpolation="bilinear", aspect="auto",
                  extent=(x[0] - half_x, x[-1] + half_x,
                          y[0] - half_y, y[-1] + half_y))

    def _draw_density(self, ax) -> None:
        x = self._density.get('x_nm')
        y = self._density.get('y_nm')
        values = self._density.get('values')
        if not (_has_values(x) and _has_values(y) and _has_values(values)):
            return
        grid = np.asarray(values, dtype=float)
        if grid.ndim != 2 or not np.any(grid):
            return
        ax.contour(np.asarray(x, dtype=float), np.asarray(y, dtype=float),
                   grid.T, levels=6, colors=self.SELECTED_COLOUR,
                   linewidths=0.8, alpha=0.9)

    def _projected_area(self, spec: dict, axes) -> float:
        """How much of the view a feature covers, for the painting order."""
        half = spec_extent(spec, axes)
        return float(half[0] * half[1]) if len(half) >= 2 else 0.0

    def _hidden_offset(self, spec: dict, axes) -> float:
        """How far the plane on screen sits from a feature's centre, on the
        axis the view cannot show. Zero for a 2-D model, which has none."""
        if len(self._domain) < 3 or self._projection not in ('xy', 'xz', 'yz'):
            return 0.0
        # Guarded the way _cut_title guards the same key. This runs inside
        # _render, which runs inside paint(): anything that raises here is a
        # traceback per frame over a blank canvas, and the title three lines
        # away already refuses to trust the value.
        try:
            where = float(self._potential.get('slice_at'))
        except (TypeError, ValueError):         # a 2-D model has no cut
            return 0.0
        hidden = ({0, 1, 2} - set(axes)).pop()
        return where - spec_position(spec, (hidden,))[0]

    def _cuts_the_plane(self, spec: dict, axes) -> bool:
        """Whether the plane on screen actually passes through the feature.

        A projection draws every feature, wherever it sits on the axis it
        cannot show — so a box at z = 15 is painted over a dot at z = 5 and
        the view quietly claims they are neighbours. The ones the cut misses
        are still drawn, as outlines, which is both honest about what is in
        the plane and what stops them hiding each other.
        """
        if len(self._domain) < 3 or self._projection not in ('xy', 'xz', 'yz'):
            return True
        if self._potential.get('slice_at') is None:
            return True
        hidden = ({0, 1, 2} - set(axes)).pop()
        return (abs(self._hidden_offset(spec, axes))
                <= spec_extent(spec, (hidden,))[0])

    def _draw_feature(self, ax, index: int, spec: dict, axes) -> None:
        from matplotlib.colors import to_rgba
        from matplotlib.patches import Rectangle

        colour = (self.SELECTED_COLOUR if index == self._selected
                  else self._seriesColour(
                      self.FEATURE_COLOURS[index % len(self.FEATURE_COLOURS)]))
        selected = index == self._selected
        in_plane = self._cuts_the_plane(spec, axes)
        centre = spec_position(spec, axes)
        half = spec_extent(spec, axes)
        kind = str(spec.get('kind', ''))
        # Face and edge carry their own alpha rather than one over the whole
        # patch: the fill has to be faint enough to see what is underneath
        # it, and the outline has to stay readable through three of them.
        # An outline in the feature's own colour is also what tells two
        # overlapping features apart, which a common foreground edge did not.
        fill = 0.0 if not in_plane else (0.42 if selected else 0.20)
        dashes = (0, (4, 3))
        style = dict(facecolor=to_rgba(colour, fill),
                     edgecolor=to_rgba(colour, 1.0 if in_plane else 0.65),
                     linewidth=2.4 if selected else 1.4,
                     linestyle='-' if in_plane else dashes)
        if kind.startswith('gaussian'):
            style['linestyle'] = (0, (2, 2)) if in_plane else dashes

        # A feature the cut misses is drawn at its full silhouette, not at
        # the empty section the plane actually takes out of it: the dashes
        # already say it is not in this plane, and a cylinder five nanometres
        # off it would otherwise be a zero-width line saying nothing about
        # where it is or how big.
        cut = Cut(spec=spec, kind=kind, axes=axes, centre=centre, half=half,
                  offset=self._hidden_offset(spec, axes) if in_plane else 0.0)
        build = OUTLINES.get(kind)
        patch = build(cut, style) if build else None
        if patch is None and build is None:
            patch = Rectangle((centre[0] - half[0], centre[1] - half[1]),
                              2 * half[0], 2 * half[1], **style)
        if patch is None:                       # a section with nothing in it
            return
        ax.add_patch(patch)

        ax.annotate(f"F{index}", centre, color=self._foreground, fontsize=7,
                    ha="center", va="center", alpha=1.0 if in_plane else 0.5)

    def _draw_handles(self, ax, spec: dict, axes) -> None:
        """Corner markers on the selected feature, for resizing."""
        centre = spec_position(spec, axes)
        half = spec_extent(spec, axes)
        if half[0] <= 0 and half[1] <= 0:
            return
        corners = [(centre[0] + half[0], centre[1] + half[1])]
        # Black outline whatever the theme: the handle is drawn on top of
        # the feature's own colour, so its edge is a contrast device rather
        # than a palette colour, and it has to work over all ten of them.
        ax.plot([c[0] for c in corners], [c[1] for c in corners], "s",
                color=self.SELECTED_COLOUR, markeredgecolor="#000000",
                markersize=6, zorder=5)

    # ── the mouse ────────────────────────────────────────────────────────

    def _hit(self, x: float, y: float):
        """What is under the point: ``('handle'|'feature', index)`` or None.

        Handles first, and features from the top down — the one drawn last is
        the one on top, and picking the one underneath is the classic way an
        editor feels broken.
        """
        ax = self._axes()
        data = self.data_at(x, y, ax)
        if data is None:
            return None
        axes = self._shown_axes()

        if 0 <= self._selected < len(self._features):
            spec = self._features[self._selected]
            centre = spec_position(spec, axes)
            half = spec_extent(spec, axes)
            corner = self.item_at(centre[0] + half[0], centre[1] + half[1], ax)
            if corner is not None:
                if (abs(corner[0] - x) <= self.HANDLE_GRAB_PX
                        and abs(corner[1] - y) <= self.HANDLE_GRAB_PX):
                    return ('handle', self._selected)

        for index in range(len(self._features) - 1, -1, -1):
            spec = self._features[index]
            centre = spec_position(spec, axes)
            half = spec_extent(spec, axes)
            if (abs(data[0] - centre[0]) <= max(half[0], 1e-9)
                    and abs(data[1] - centre[1]) <= max(half[1], 1e-9)):
                return ('feature', index)
        return None

    def mousePressEvent(self, event) -> None:
        x, y = event.position().x(), event.position().y()
        hit = self._hit(x, y)
        data = self.data_at(x, y)

        if hit is None:
            self._drag = None
            if self._selected != -1:
                self._set_selected(-1)
            self.featureSelected.emit(-1)
            event.accept()
            return

        what, index = hit
        if index != self._selected:
            self._set_selected(index)
            self.featureSelected.emit(index)

        axes = self._shown_axes()
        centre = spec_position(self._features[index], axes)
        self._drag = {'what': what, 'index': index,
                      'grab': data,
                      'offset': (centre[0] - data[0], centre[1] - data[1])
                      if data else (0.0, 0.0)}
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not self._drag:
            event.ignore()
            return
        data = self.data_at(event.position().x(), event.position().y())
        if data is None:
            event.accept()
            return

        index = self._drag['index']
        if self._drag['what'] == 'feature':
            offset = self._drag['offset']
            self.featureMoved.emit(index, data[0] + offset[0],
                                   data[1] + offset[1])
        else:
            centre = spec_position(self._features[index], self._shown_axes())
            # A handle sets the half-size directly: it is dragged to where the
            # corner should be, so the distance from the centre IS the answer.
            self.featureResized.emit(index, abs(data[0] - centre[0]),
                                     abs(data[1] - centre[1]))
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag = None
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        x, y = event.position().x(), event.position().y()
        if self._hit(x, y) is not None:
            event.accept()
            return
        data = self.data_at(x, y)
        if data is not None:
            self.featureAdded.emit(data[0], data[1])
        event.accept()
