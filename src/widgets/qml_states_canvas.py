"""
What a solved model actually looks like.

The Qt port could solve a 3-D model but only ever showed one plane of it at a
time, which is not how a state is read: a wavefunction that looks confined in
XY may be leaking out through z, and the only way to see that is to look at
the volume and its three cuts together. This is the Tk app's view brought
across — a cloud of |ψ|² with the features drawn around it, and the XY, XZ and
YZ cuts beside it, each labelled with the position it was cut at.

The same canvas draws the tunnelling picture, behind :attr:`mode`. They are
never on screen at once, they share every colour, every axis style and the
colorbar handling, and one figure is one Agg buffer instead of two — a second
canvas would keep a full-size buffer alive for a view nobody is looking at.
The table in the workstation stays: a rate is a number you copy, and a bar
chart is a number you compare.

Nothing large crosses the bridge. The backend sends slices and a capped
scatter, never a grid — see ``ModelingBackend.statePlots``.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging

import numpy as np
from matplotlib.gridspec import GridSpec
from PySide6.QtCore import Property, Signal, Slot

from src.widgets.qml_figure_canvas import FigureCanvasItem, scale_or_default

logger = logging.getLogger(__name__)


def _array(value):
    """``value`` as a float array, or None when it is not one.

    Everything here arrives across the QML bridge, where a missing key is
    ``undefined``, an empty list is a legitimate answer and a ragged list is
    a bug upstream. All three have to end as None rather than as an exception
    inside a draw.
    """
    if value is None:
        return None
    try:
        array = np.asarray(list(value), dtype=float)
    except (TypeError, ValueError):
        return None
    return array if array.size else None


def _number(value):
    """``value`` as a float, or None for anything that is not a real one."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _plane(values, horizontal, vertical):
    """A cut oriented the way ``pcolormesh`` wants it, or None.

    This project stores a plane indexed ``[first axis][second axis]`` — the
    potential canvas draws its grids with ``.T`` for the same reason — while
    matplotlib wants one row per vertical sample. A non-square cut says which
    way round it came, so a backend that sends the other convention still
    draws correctly instead of raising.
    """
    grid = _array(values)
    if grid is None or grid.ndim != 2 or horizontal is None or vertical is None:
        return None
    nh, nv = horizontal.size, vertical.size
    if grid.shape == (nh, nv):
        return grid.T
    if grid.shape == (nv, nh):
        return grid
    return None


class StatesCanvas(FigureCanvasItem):
    """The 2×2 state view, and the tunnelling view behind ``mode``."""

    #: One colour per feature, cycled — the same sequence the potential
    #: editor uses, so a wireframe here is the feature with that colour there.
    FEATURE_COLOURS = ("#5BCEFA", "#F5A9B8", "#66ff66", "#FFD700", "#FF6B6B",
                       "#9B4F96", "#00BCD4", "#FF9800", "#E91E63", "#2ECC71")
    #: The selected state. Fixed for the same reason as the editor's handle:
    #: it has to differ from all ten feature colours at once.
    SELECTED_COLOUR = "#FFD700"

    #: A level no feature holds, by how bound it is — the old app's
    #: three-way split. This one *is* semantic rather than an identity:
    #: below the well floor / bound / above zero is a good-middling-bad
    #: reading, so it takes the scheme's success, accent and error when
    #: those three still tell each other apart, and these when they do not.
    DEEP_COLOUR = "#2ecc71"
    BOUND_COLOUR = "#5BCEFA"
    FREE_COLOUR = "#e74c3c"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "states"
        self._plots: dict = {}
        self._tunneling: dict = {}
        self._selected_state = -1
        # Colorbars outlive the axes they were made for: clearing the figure
        # drops the axes but the colorbar keeps its own, and rebuilding
        # without removing them is how the Tk app grew a strip of them down
        # the side (its safe_clear_colorbar). Held so they can be removed.
        self._colorbars: list = []

    # ── theming ──────────────────────────────────────────────────────────

    modeChanged = Signal()
    selectedStateChanged = Signal()

    def _level_scale(self):
        """Deep / bound / free, themed only while they stay distinguishable."""
        return scale_or_default(
            (self._success, self._accent, self._error),
            (self.DEEP_COLOUR, self.BOUND_COLOUR, self.FREE_COLOUR))

    def _restyle(self) -> None:
        """Draw the current view again in the new colours.

        This canvas keeps everything it was last given, so a colour change
        is a full redraw and the level ladder follows the theme rather than
        only the frame around it. A message showing over the top of that
        data is replayed first — it is what is on screen.
        """
        if not self._replay():
            self._rebuild()

    def _get_mode(self) -> str:
        return self._mode

    def _set_mode(self, value) -> None:
        value = str(value or "states").lower()
        if value not in ("states", "tunneling") or value == self._mode:
            return
        self._mode = value
        self.modeChanged.emit()
        self._rebuild()

    #: Which picture to draw: ``"states"`` or ``"tunneling"``. The data for
    #: both is kept, so switching is a redraw and not a round trip.
    mode = Property(str, _get_mode, _set_mode, notify=modeChanged)

    def _get_selected_state(self) -> int:
        return self._selected_state

    def _set_selected_state(self, index) -> None:
        index = int(index)
        if index != self._selected_state:
            self._selected_state = index
            self.selectedStateChanged.emit()
            if self._mode == "tunneling":
                self._rebuild()

    #: Which level the tunnelling diagram picks out. Only the tunnelling view
    #: uses it — the state view draws whatever it was last handed.
    selectedState = Property(int, _get_selected_state, _set_selected_state,
                             notify=selectedStateChanged)

    # ── what to draw ─────────────────────────────────────────────────────

    @Slot('QVariantMap')
    def setPlots(self, data) -> None:
        """The state view's data, exactly as ``statePlots()`` returns it."""
        self._plots = dict(data or {})
        self._last_draw = None          # new data replaces any message
        if self._mode == "states":
            self._rebuild()

    @Slot('QVariantMap')
    def setTunneling(self, data) -> None:
        """The tunnelling view's data, as ``tunneling()`` returns it.

        ``E_eV`` and ``overlap`` are drawn when the backend sends them and
        their panels are left out when it does not, rather than the view
        refusing to draw the rates it does have.
        """
        self._tunneling = dict(data or {})
        self._last_draw = None          # new data replaces any message
        if self._mode == "tunneling":
            self._rebuild()

    def _rebuild(self) -> None:
        """Draw the current mode from scratch.

        Never raises: this is reached from a property write and from a slot,
        and a half-built figure would then be painted every frame.
        """
        self._clear_colorbars()
        self.figure.clf()
        try:
            if self._mode == "tunneling":
                self._draw_tunneling()
            else:
                self._draw_states()
        except Exception:
            logger.exception("StatesCanvas: the %s view could not be drawn",
                             self._mode)
            self.figure.clf()
            self._draw_message("This view could not be drawn — see the log")
        self.redraw()

    def _clear_colorbars(self) -> None:
        for bar in self._colorbars:
            try:
                bar.remove()
            except (KeyError, ValueError, AttributeError):
                pass
        self._colorbars = []

    # ── the state view ───────────────────────────────────────────────────

    @staticmethod
    def _reason(data, fallback: str) -> str:
        """What to say instead of a plot.

        The backend's own message when it sent one — it knows why it could
        not answer — and otherwise the instruction that gets there.
        """
        return str((data or {}).get('error') or "").strip() or fallback

    def _draw_states(self) -> None:
        data = self._plots
        if not data or not data.get('ok'):
            self._draw_message(self._reason(
                data, "Solve the model to see its states"))
            return

        x = _array(data.get('x_nm'))
        y = _array(data.get('y_nm'))
        z = _array(data.get('z_nm'))

        # A 2-D model has no volume and no hidden axis: one cut is the whole
        # of it, and a 2×2 of three empty panels would only say so louder.
        if z is None:
            ax = self.figure.add_subplot(111)
            self._draw_cut(ax, data.get('xy'), x, y, "x (nm)", "y (nm)",
                           "XY", "z")
            ax.set_title(self._state_title(data), fontsize=9)
            self.figure.tight_layout(pad=0.6)
            return

        grid = GridSpec(2, 2, figure=self.figure, hspace=0.35, wspace=0.30)

        cloud = self.figure.add_subplot(grid[0, 0], projection='3d')
        self._draw_cloud(cloud, data, x, y, z)

        self._draw_cut(self.figure.add_subplot(grid[0, 1]), data.get('xy'),
                       x, y, "x (nm)", "y (nm)", "XY", "z")
        self._draw_cut(self.figure.add_subplot(grid[1, 0]), data.get('xz'),
                       x, z, "x (nm)", "z (nm)", "XZ", "y")
        self._draw_cut(self.figure.add_subplot(grid[1, 1]), data.get('yz'),
                       y, z, "y (nm)", "z (nm)", "YZ", "x")

    @staticmethod
    def _state_title(data: dict) -> str:
        # The index is the backend's, which counts from zero; the level table
        # beside this view labels the same state E{index + 1}.
        state = int(_number(data.get('state')) or 0)
        energy = _number(data.get('E_eV'))
        title = f"|ψ|²  state {state}"
        if energy is not None:
            title += f"  E={energy:.4f} eV"
        # A capped cloud is a smaller cloud, not a sparser one — the points
        # kept are the brightest, so a state filling the box draws as a blob
        # in the middle of it. Saying so is the difference between a picture
        # that is wrong and one that is partial.
        scatter = dict(data.get('scatter') or {})
        total, shown = _number(scatter.get('total')), _number(scatter.get('shown'))
        if total is not None and shown is not None and shown < total:
            title += f"\nbrightest {int(shown):,} of {int(total):,} points"
        return title

    def _draw_cloud(self, ax, data: dict, x, y, z) -> None:
        """|ψ|² as points, inside the features that hold it.

        The threshold is the old app's 0.05 of the maximum and is applied in
        the backend, which is also where the point count is capped: a 60³
        solve is 216 000 points and neither the bridge nor a scatter wants
        them all.
        """
        scatter = dict(data.get('scatter') or {})
        xs, ys, zs = (_array(scatter.get('x')), _array(scatter.get('y')),
                      _array(scatter.get('z')))
        cs = _array(scatter.get('c'))
        if xs is not None and ys is not None and zs is not None \
                and xs.size == ys.size == zs.size:
            if cs is None or cs.size != xs.size:
                cs = np.ones_like(xs)
            # 'hot' is the old app's map and it starts at black, which on a
            # white figure is the darkest thing on screen and on this one is
            # the background. So the ramp is floored below the faintest point
            # kept: the ordering is untouched, the whole cloud just sits in
            # the part of the map that can be seen against near-black.
            span = float(cs.max() - cs.min())
            ax.scatter(xs, ys, zs, c=cs, cmap='hot', s=3, alpha=0.5,
                       depthshade=True, vmin=float(cs.min()) - 0.5 * span
                       - 1e-3, vmax=float(cs.max()))

        self._draw_features_3d(ax, data.get('features') or [])

        ax.set_xlabel("x (nm)")
        ax.set_ylabel("y (nm)")
        ax.set_zlabel("z (nm)")
        ax.set_title(self._state_title(data), fontsize=9)
        for setter, axis in ((ax.set_xlim, x), (ax.set_ylim, y),
                             (ax.set_zlim, z)):
            if axis is not None and axis.size > 1:
                setter(float(axis[0]), float(axis[-1]))
        self._style_3d(ax)

    def _draw_cut(self, ax, cut, horizontal, vertical, hlabel, vlabel,
                  plane: str, axis_name: str) -> None:
        """One slice, titled with where it was cut.

        The position in the title is the detail that made this view readable:
        two cuts of the same state at different z are different pictures, and
        without the number there is no telling which is which.
        """
        cut = dict(cut or {})
        title = f"{plane} cut"
        position = _number(cut.get('slice_at'))
        if position is not None:
            title += f"  {axis_name} = {position:.1f} nm"
        ax.set_title(title, fontsize=9)
        ax.set_xlabel(hlabel)
        ax.set_ylabel(vlabel)
        self._style(ax)

        grid = _plane(cut.get('values'), horizontal, vertical)
        if grid is None:
            return
        mesh = ax.pcolormesh(horizontal, vertical, grid, cmap='inferno',
                             shading='auto')
        self._colorbar(mesh, ax)
        ax.set_aspect('equal')

    # ── feature wireframes ───────────────────────────────────────────────

    def _draw_features_3d(self, ax, features) -> None:
        """The model's shapes drawn around the cloud.

        A cloud on its own says where the state is but not what is holding
        it. Each shape is drawn in its own colour and each is guarded on its
        own: a spec this drawer does not understand costs its wireframe, not
        the whole figure.
        """
        for index, spec in enumerate(features or []):
            spec = dict(spec or {})
            colour = self._seriesColour(
                self.FEATURE_COLOURS[index % len(self.FEATURE_COLOURS)])
            try:
                self._draw_feature(ax, spec, colour, f"F{index}")
            except Exception:
                logger.debug("StatesCanvas: feature %d (%s) has no wireframe",
                             index, spec.get('kind'), exc_info=True)

    def _draw_feature(self, ax, spec: dict, colour: str, label: str) -> None:
        kind = str(spec.get('kind', ''))
        get = lambda name, default=0.0: float(spec.get(name, default))  # noqa: E731

        if kind == 'box':
            self._draw_box(ax, get('cx') - get('Lx') / 2,
                           get('cy') - get('Ly') / 2,
                           get('cz') - get('Lz') / 2,
                           get('Lx'), get('Ly'), get('Lz'), colour, 0.15,
                           label)
        elif kind == 'sphere':
            self._draw_sphere(ax, get('cx'), get('cy'), get('cz'), get('R'),
                              colour)
        elif kind == 'cylinder':
            self._draw_cylinder(ax, get('cx'), get('cy'), get('cz'), get('R'),
                                get('H'), colour)
        elif kind in ('pyramid', 'prism'):
            # `base` is a diameter here whatever its label says: the feature
            # itself takes half of it as the circumradius of the cross
            # section (`R = self.base / 2`), and a wireframe that disagreed
            # with the potential would be worse than none.
            sides = max(3, int(spec.get('n_sides', 4 if kind == 'pyramid'
                                        else 6)))
            radius = get('base') / 2.0
            if kind == 'pyramid':
                self._draw_pyramid(ax, get('cx'), get('cy'), get('cz'),
                                   radius, get('H'), sides, colour, label)
            else:
                self._draw_prism(ax, get('cx'), get('cy'), get('cz'), radius,
                                 get('H'), sides, colour, label)
        elif kind == 'cone':
            self._draw_cone(ax, get('cx'), get('cy'), get('cz'), get('R'),
                            get('H'), colour, label)
        elif kind == 'lens':
            self._draw_lens(ax, get('cx'), get('cy'), get('cz'), get('R'),
                            get('H'), colour, label)
        elif kind == 'gaussian_3d':
            # Three sigma: a Gaussian has no edge, and this is where it stops
            # mattering.
            self._draw_box(ax, get('cx') - 3 * get('sx', 1.0),
                           get('cy') - 3 * get('sy', 1.0),
                           get('cz') - 3 * get('sz', 1.0),
                           6 * get('sx', 1.0), 6 * get('sy', 1.0),
                           6 * get('sz', 1.0), colour, 0.10, label)

    def _draw_box(self, ax, x, y, z, wx, wy, wz, colour, alpha,
                  label="") -> None:
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        v = [[x, y, z], [x + wx, y, z], [x + wx, y + wy, z], [x, y + wy, z],
             [x, y, z + wz], [x + wx, y, z + wz],
             [x + wx, y + wy, z + wz], [x, y + wy, z + wz]]
        faces = [[v[0], v[1], v[2], v[3]], [v[4], v[5], v[6], v[7]],
                 [v[0], v[1], v[5], v[4]], [v[2], v[3], v[7], v[6]],
                 [v[0], v[3], v[7], v[4]], [v[1], v[2], v[6], v[5]]]
        box = Poly3DCollection(faces, alpha=alpha, linewidths=0.8,
                               edgecolors=colour)
        box.set_facecolor(colour)
        ax.add_collection3d(box)
        self._label(ax, x + wx / 2, y + wy / 2, z, label, colour)

    @staticmethod
    def _draw_sphere(ax, cx, cy, cz, R, colour) -> None:
        n = 16
        theta, phi = np.meshgrid(np.linspace(0.0, np.pi, n),
                                 np.linspace(0.0, 2 * np.pi, 2 * n))
        ax.plot_wireframe(cx + R * np.sin(theta) * np.cos(phi),
                          cy + R * np.sin(theta) * np.sin(phi),
                          cz + R * np.cos(theta),
                          color=colour, alpha=0.3, linewidth=0.5,
                          rstride=2, cstride=2)

    @staticmethod
    def _draw_cylinder(ax, cx, cy, cz, R, H, colour) -> None:
        theta, z = np.meshgrid(np.linspace(0.0, 2 * np.pi, 24),
                               np.linspace(cz - H / 2, cz + H / 2, 8))
        ax.plot_wireframe(cx + R * np.cos(theta), cy + R * np.sin(theta), z,
                          color=colour, alpha=0.3, linewidth=0.5,
                          rstride=2, cstride=2)

    def _draw_pyramid(self, ax, cx, cy, cz, R, H, sides, colour,
                      label="") -> None:
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        z_bottom, z_top = cz - H / 2, cz + H / 2
        angles = np.linspace(0.0, 2 * np.pi, sides + 1)
        bx, by = cx + R * np.cos(angles), cy + R * np.sin(angles)
        bz = np.full_like(bx, z_bottom)

        ax.plot(bx, by, bz, color=colour, alpha=0.6, linewidth=1.2)
        for k in range(sides):
            ax.plot([bx[k], cx], [by[k], cy], [z_bottom, z_top],
                    color=colour, alpha=0.4, linewidth=0.8)
        ax.add_collection3d(Poly3DCollection([list(zip(bx, by, bz))],
                                             alpha=0.12, facecolor=colour,
                                             edgecolor=colour, linewidth=0.5))
        self._label(ax, cx, cy, z_bottom, label, colour)

    def _draw_prism(self, ax, cx, cy, cz, R, H, sides, colour,
                    label="") -> None:
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        z_bottom, z_top = cz - H / 2, cz + H / 2
        angles = np.linspace(0.0, 2 * np.pi, sides + 1)
        bx, by = cx + R * np.cos(angles), cy + R * np.sin(angles)

        for level in (z_bottom, z_top):
            ax.plot(bx, by, np.full_like(bx, level), color=colour, alpha=0.6,
                    linewidth=1.2)
            ax.add_collection3d(Poly3DCollection(
                [list(zip(bx, by, np.full_like(bx, level)))], alpha=0.10,
                facecolor=colour, edgecolor=colour, linewidth=0.5))
        for k in range(sides):
            ax.plot([bx[k], bx[k]], [by[k], by[k]], [z_bottom, z_top],
                    color=colour, alpha=0.4, linewidth=0.8)
            side = [(bx[k], by[k], z_bottom), (bx[k + 1], by[k + 1], z_bottom),
                    (bx[k + 1], by[k + 1], z_top), (bx[k], by[k], z_top)]
            ax.add_collection3d(Poly3DCollection([side], alpha=0.08,
                                                 facecolor=colour,
                                                 edgecolor=colour,
                                                 linewidth=0.3))
        self._label(ax, cx, cy, z_bottom, label, colour)

    def _draw_cone(self, ax, cx, cy, cz, R, H, colour, label="") -> None:
        n = 24
        z_bottom, z_top = cz - H / 2, cz + H / 2
        angles = np.linspace(0.0, 2 * np.pi, n + 1)
        bx, by = cx + R * np.cos(angles), cy + R * np.sin(angles)
        ax.plot(bx, by, np.full_like(bx, z_bottom), color=colour, alpha=0.6,
                linewidth=1.0)
        for k in range(0, n, max(1, n // 8)):
            ax.plot([bx[k], cx], [by[k], cy], [z_bottom, z_top], color=colour,
                    alpha=0.3, linewidth=0.6)
        # A few cross sections, because a cone drawn only by its edges reads
        # as a fan of lines rather than a solid.
        for fraction in (0.25, 0.5, 0.75):
            r = R * (1 - fraction)
            ax.plot(cx + r * np.cos(angles), cy + r * np.sin(angles),
                    np.full_like(angles, z_bottom + fraction * H),
                    color=colour, alpha=0.2, linewidth=0.4)
        self._label(ax, cx, cy, z_bottom, label, colour)

    def _draw_lens(self, ax, cx, cy, cz, R, H, colour, label="") -> None:
        """A spherical cap standing on its base plane.

        The old app had no lens wireframe and fell back to a bounding box —
        the one shape here where a box actively misleads, since a cap fills
        barely a third of it and a lobe that looks like it is spilling out
        of the corners is not. Worth drawing properly now that the geometry
        is pinned: base on ``cz - H/2``, apex on ``cz + H/2``, the same span
        the feature builds its potential over.
        """
        if R <= 0 or H <= 0:
            return
        # The cap's own sphere, from the formula the feature uses: centred
        # below the base, so the section is R wide there and closes to a
        # point at the apex.
        sphere_R = (R * R + H * H) / (2.0 * H)
        z_bottom = cz - H / 2
        heights = np.linspace(0.0, H, 8)
        radii = np.sqrt(np.maximum(
            sphere_R ** 2 - (heights - (H - sphere_R)) ** 2, 0.0))
        angles = np.linspace(0.0, 2 * np.pi, 25)
        theta, radius = np.meshgrid(angles, radii)
        z = np.repeat((z_bottom + heights)[:, None], angles.size, axis=1)
        ax.plot_wireframe(cx + radius * np.cos(theta),
                          cy + radius * np.sin(theta), z, color=colour,
                          alpha=0.3, linewidth=0.5, rstride=1, cstride=3)
        ax.plot(cx + R * np.cos(angles), cy + R * np.sin(angles),
                np.full_like(angles, z_bottom), color=colour, alpha=0.6,
                linewidth=1.0)
        self._label(ax, cx, cy, z_bottom, label, colour)

    @staticmethod
    def _label(ax, x, y, z, label, colour) -> None:
        if label:
            ax.text(x, y, z, label, fontsize=7, ha='center', color=colour,
                    fontweight='bold')

    # ── the tunnelling view ──────────────────────────────────────────────

    def _draw_tunneling(self) -> None:
        data = self._tunneling
        if not data or not data.get('ok'):
            self._draw_message(self._reason(
                data, "Solve a model with more than one feature"))
            return

        energies = _array(data.get('E_eV'))
        overlap = _array(data.get('overlap'))
        if overlap is not None and overlap.ndim != 2:
            overlap = None
        rates = [dict(r or {}) for r in (data.get('rates') or [])]

        panels = [name for name, present in (('levels', energies is not None),
                                             ('overlap', overlap is not None),
                                             ('rates', bool(rates)))
                  if present]
        if not panels:
            self._draw_message("Nothing to compare yet")
            return

        grid = GridSpec(1, len(panels), figure=self.figure, wspace=0.35)
        for column, name in enumerate(panels):
            ax = self.figure.add_subplot(grid[0, column])
            if name == 'levels':
                self._draw_levels(ax, energies, data, rates)
            elif name == 'overlap':
                self._draw_overlap(ax, overlap)
            else:
                self._draw_rates(ax, rates)
            self._style(ax)
        if energies is None:
            self.figure.suptitle(
                "Energies were not sent with the analysis — no level diagram",
                color=self._foreground, fontsize=8)

    def _draw_levels(self, ax, energies, data: dict, rates) -> None:
        """The ladder, coloured by which feature each state sits in.

        A rate only means something against the levels it connects, which is
        why the diagram and the bars belong in one picture.
        """
        assignments = [int(a) for a in (data.get('assignments') or [])]
        floor = _number(data.get('V_min_eV'))
        ax.axhline(0.0, color=self._grid, linestyle="--", lw=0.8)
        if floor is not None and floor < 0:
            # Emphasis rather than identity — nothing is compared against
            # the shading by colour — so it follows the theme's accent.
            ax.axhspan(floor, 0.0, alpha=0.12, color=self._accent)
            # Off to the side of the levels, not down the middle of them:
            # the selected state's own label sits at x=0.5.
            ax.text(1.05, floor / 2, "Well", ha="center", va="center",
                    fontsize=7, color=self._accent, alpha=0.8)

        for i, energy in enumerate(energies):
            feature = assignments[i] if i < len(assignments) else -1
            held = feature >= 0
            colour = self._seriesColour(
                self.FEATURE_COLOURS[feature % len(self.FEATURE_COLOURS)]
                if held else self._unbound_colour(energy, floor))
            chosen = (i == self._selected_state)
            # Held levels are drawn solid, unheld ones dashed, and that is
            # what carries the distinction — not the colour.
            #
            # Colour alone cannot carry it. This one axes mixes two palettes:
            # FEATURE_COLOURS, which says *which feature* holds a state, and
            # the deep/bound/free scale, which says *how bound* a state no
            # feature holds is. All three of the scale's fallback colours are
            # exact matches for a feature colour — #2ecc71 is FEATURE_COLOURS[9],
            # #5BCEFA is [0], and the themed `free` lands on #FF6B6B, which is
            # [4] — so in a model with five or more features "held by feature 5"
            # and "not confined at all" drew the identical red line. Ten
            # identity hues already cover the wheel, so no triple can be made
            # distinct from all of them on 22 schemes; the dash is a second
            # channel that never collides.
            ax.hlines(energy, 0.1, 0.9,
                      colors=self.SELECTED_COLOUR if chosen else colour,
                      linewidth=2.5 if chosen else 1.2,
                      linestyles="solid" if held else (0, (4, 2)),
                      alpha=1.0 if chosen else 0.7)
            if chosen:
                ax.text(0.5, energy, f"E{i + 1}", fontsize=8, ha="center",
                        va="bottom", fontweight="bold",
                        color=self.SELECTED_COLOUR)
            else:
                side, align = (0.02, "left") if i % 2 == 0 else (0.98, "right")
                ax.text(side, energy, str(i + 1), fontsize=6, ha=align,
                        va="center", color=colour, alpha=0.8)

        # The strongest few transitions, drawn between the levels they join.
        for rank, rate in enumerate(rates[:5]):
            i, j = int(rate.get('from_state', -1)), int(rate.get('to_state', -1))
            if not (0 <= i < len(energies) and 0 <= j < len(energies)):
                continue
            if float(rate.get('rate_Hz', 0.0)) <= 0:
                continue
            ax.annotate("", xy=(0.5, energies[j]), xytext=(0.5, energies[i]),
                        arrowprops=dict(arrowstyle="<->",
                                        color=self.SELECTED_COLOUR,
                                        alpha=max(0.3, 1.0 - rank * 0.15),
                                        lw=1.2))

        ax.set_xlim(0.0, 1.2)
        ax.set_xticks([])
        ax.set_ylabel("Energy (eV)")
        ax.set_title("Energy levels", fontsize=9)
        low = min(float(energies.min()), floor if floor is not None else
                  float(energies.min()))
        span = max(float(energies.max()) - low, 0.01)
        ax.set_ylim(low - 0.1 * span, float(energies.max()) + 0.1 * span)

    def _unbound_colour(self, energy: float, floor) -> str:
        """What to draw a level in when no feature claims it.

        The old app split these three ways and the split is worth keeping: a
        state below the well's own floor, one merely below zero, and one
        above it are three different answers to "is this held anywhere", and
        one flat grey for all three throws the question away. With no floor
        published there is nothing to be deep relative to, so it falls back
        to bound-or-not.
        """
        deep, bound, free = self._level_scale()
        if floor is not None and energy < floor:
            return deep
        return bound if energy < 0 else free

    def _draw_overlap(self, ax, overlap) -> None:
        image = ax.imshow(overlap, cmap='hot', origin='lower', vmin=0.0,
                          vmax=1.0)
        self._colorbar(image, ax)
        # Numbered the way every other panel numbers a state — the ladder
        # beside this one counts from E1, and a matrix indexed from 0 next
        # to it is one off for the whole time you are reading it. Every
        # state gets a tick only while they fit: this panel is about a
        # quarter of the figure wide, and 24 labels across it run together
        # into one string of digits, so past a dozen states they are thinned
        # to every fifth the way an ordinary locator would.
        count = int(overlap.shape[0])
        step = 1 if count <= 12 else 5
        ticks = np.arange(0, count, step)
        labels = [str(int(t) + 1) for t in ticks]
        ax.set_xticks(ticks, labels)
        ax.set_yticks(ticks, labels)
        ax.set_xlabel("State j")
        ax.set_ylabel("State i")
        ax.set_title("Overlap |⟨ψᵢ|ψⱼ⟩|", fontsize=9)

    def _draw_rates(self, ax, rates) -> None:
        """The strongest rates, on a log axis because they span decades.

        WKB rates are comparisons, not measurements — the bar next to it is
        the only thing a bar here means.
        """
        top = rates[:10]
        labels = [f"E{int(r.get('from_state', 0)) + 1}↔"
                  f"E{int(r.get('to_state', 0)) + 1}" for r in top]
        values = [max(float(r.get('rate_Hz', 0.0)), 1e-30) for r in top]
        ax.barh(range(len(top)), values, color=self._accent)
        ax.set_yticks(range(len(top)))
        ax.set_yticklabels(labels, fontsize=7)
        ax.set_xscale('log')
        ax.set_xlabel("WKB rate (Hz)")
        ax.set_title("Tunnelling rates", fontsize=9)
        ax.invert_yaxis()

    # ── styling ──────────────────────────────────────────────────────────

    # `_style` and `_style_3d` are the base class's — every canvas in this
    # family paints an axes the same way, and the 3-D treatment was written
    # here first.

    def _colorbar(self, mappable, ax):
        """A colorbar that can be read on a dark ground, and removed later.

        Its ticks and its outline are not the parent axes' and do not inherit
        anything from it: a default colorbar here is black text on near-black.
        """
        bar = self.figure.colorbar(mappable, ax=ax, fraction=0.046, pad=0.04)
        self._colorbars.append(bar)
        bar.ax.set_facecolor(self._background)
        bar.ax.tick_params(colors=self._foreground, labelsize=6)
        bar.ax.yaxis.label.set_color(self._foreground)
        try:
            bar.outline.set_edgecolor(self._grid)
        except AttributeError:
            pass
        return bar

    # ── nothing to draw ──────────────────────────────────────────────────
    #
    # `_draw_message` is the base class's.

    @Slot(str)
    def showMessage(self, message: str) -> None:
        """Put a line of text where a plot would be.

        Clears the colorbars first, which the base class knows nothing
        about: they outlive the axes they were made for.
        """
        self._clear_colorbars()
        super().showMessage(message)

    # ── teardown ─────────────────────────────────────────────────────────

    @Slot()
    def cleanup(self) -> None:
        self._clear_colorbars()
        self._plots = {}
        self._tunneling = {}
        super().cleanup()
