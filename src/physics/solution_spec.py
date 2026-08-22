"""
The common format for handing a geometry from one tool to another.

The inverse designer returns candidates; the direct solvers know how to
simulate one. What was missing between them was a shared vocabulary — that
is this file and nothing else: no UI, no solver, just data.

Two rules head off most unit mistakes:

* **nm and eV, always.** No spec carries joules or metres.
* ``dims_nm`` in the order the model's own label uses — ``(L,)``,
  ``(Lx, Ly)``, ``(R, H)``, ``(R,)`` — so the receiving tool never has to
  guess.

Keys are English ``snake_case`` and are what gets compared and persisted;
the human-readable strings live in the ``*_LABELS`` maps and are only ever
displayed. Nothing in this package compares a label.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Tuple

#: Models a spec can describe. Each tool declares which ones it accepts.
MODEL_1D = "1d"                         # 1D well              dims = (L,)
MODEL_2D = "2d"                         # 2D Cartesian well    dims = (Lx, Ly)
MODEL_2D_CIRCULAR = "2d_circular"       # disc                 dims = (R,)
MODEL_3D = "3d"                         # 3D box               dims = (Lx, Ly, Lz)
MODEL_3D_CYLINDRICAL = "3d_cylindrical"  # cylinder            dims = (R, H)
MODEL_DOT_SPHERICAL = "dot_spherical"   # spherical dot        dims = (R,)
MODEL_DOT_DISC = "dot_disc"             # lens / disc dot      dims = (R, Lz)
MODEL_DOT_PARABOLIC = "dot_parabolic"   # harmonic dot         dims = (hw_xy_meV, hw_z_meV)

MODELS = (
    MODEL_1D, MODEL_2D, MODEL_2D_CIRCULAR, MODEL_3D, MODEL_3D_CYLINDRICAL,
    MODEL_DOT_SPHERICAL, MODEL_DOT_DISC, MODEL_DOT_PARABOLIC,
)

MODEL_LABELS = {
    MODEL_1D: "1D well",
    MODEL_2D: "2D well",
    MODEL_2D_CIRCULAR: "Disc",
    MODEL_3D: "3D box",
    MODEL_3D_CYLINDRICAL: "Cylinder",
    MODEL_DOT_SPHERICAL: "Spherical dot",
    MODEL_DOT_DISC: "Lens dot",
    MODEL_DOT_PARABOLIC: "Parabolic dot",
}

#: Coordinate systems a geometry can be described in. Which ones apply
#: depends on the dimensionality: a 2D geometry is Cartesian or circular, a
#: 3D one Cartesian or cylindrical, a dot spherical, disc or parabolic.
COORDS_CARTESIAN = "cartesian"
COORDS_CIRCULAR = "circular"
COORDS_CYLINDRICAL = "cylindrical"
COORDS_SPHERICAL = "spherical"
COORDS_DISC = "disc"
COORDS_PARABOLIC = "parabolic"

COORDS = (COORDS_CARTESIAN, COORDS_CIRCULAR, COORDS_CYLINDRICAL,
          COORDS_SPHERICAL, COORDS_DISC, COORDS_PARABOLIC)

COORDS_LABELS = {
    COORDS_CARTESIAN: "Cartesian",
    COORDS_CIRCULAR: "Circular",
    COORDS_CYLINDRICAL: "Cylindrical",
    COORDS_SPHERICAL: "Spherical",
    COORDS_DISC: "Disc / lens",
    COORDS_PARABOLIC: "Parabolic",
}

#: Where a spec came from. ``designer`` is the inverse search; the direct
#: solvers stamp their own name when they hand one on.
ORIGIN_DESIGNER = "designer"


@dataclass
class SolutionSpec:
    """One candidate geometry, ready to be simulated by any of the solvers."""

    model: str
    dims_nm: Tuple[float, ...]
    coords: str = COORDS_CARTESIAN
    meff: float = 0.067
    V0_eV: Optional[float] = None          # None = infinite barrier
    targets_eV: Tuple[float, ...] = ()     # the energies the search started from
    computed_eV: Tuple[float, ...] = ()    # what the candidate gives
    rrmse: Optional[float] = None
    origin: str = ""                       # who produced it: "designer", "1d", …
    notes: str = ""
    extras: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.model not in MODELS:
            raise ValueError(f"unknown model: {self.model!r}; "
                             f"expected one of {MODELS}")
        if not self.dims_nm:
            raise ValueError("dims_nm cannot be empty")
        self.dims_nm = tuple(float(d) for d in self.dims_nm)
        if any(d <= 0 for d in self.dims_nm):
            raise ValueError(f"dimensions must be positive: {self.dims_nm}")
        self.targets_eV = tuple(float(t) for t in self.targets_eV)
        self.computed_eV = tuple(float(c) for c in self.computed_eV)

    # ── reading ──────────────────────────────────────────────────────────

    @property
    def ndim(self) -> int:
        """Confined spatial dimensions — a dot counts as 0D."""
        if self.model.startswith("dot_"):
            return 0
        return {MODEL_1D: 1, MODEL_2D: 2, MODEL_2D_CIRCULAR: 2,
                MODEL_3D: 3, MODEL_3D_CYLINDRICAL: 3}[self.model]

    @property
    def infinite_barrier(self) -> bool:
        return self.V0_eV is None or self.V0_eV <= 0

    def label(self) -> str:
        """Short label for a menu or a list."""
        names = {
            MODEL_1D: ("L",), MODEL_2D: ("Lx", "Ly"), MODEL_2D_CIRCULAR: ("R",),
            MODEL_3D: ("Lx", "Ly", "Lz"), MODEL_3D_CYLINDRICAL: ("R", "H"),
            MODEL_DOT_SPHERICAL: ("R",), MODEL_DOT_DISC: ("R", "Lz"),
            MODEL_DOT_PARABOLIC: ("ħω_xy", "ħω_z"),
        }[self.model]
        unit = "meV" if self.model == MODEL_DOT_PARABOLIC else "nm"
        dims = ", ".join(f"{n} = {v:.3f}" for n, v in zip(names, self.dims_nm))
        return f"{dims} {unit}"

    # ── persistence ──────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SolutionSpec":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


def spec_from_designer(solution: dict, meff: float, targets, V0_eV=None,
                       rrmse=None) -> SolutionSpec:
    """Translate one inverse-designer solution into a :class:`SolutionSpec`.

    The designer describes a geometry as ``ndim`` + ``coords`` + ``dims``;
    here that becomes one of the :data:`MODELS` names, which is what the
    solvers read.
    """
    ndim = str(solution.get("ndim", "3D")).upper()
    coords = solution.get("coords", COORDS_CARTESIAN)

    if ndim == "0D":
        model = {COORDS_SPHERICAL: MODEL_DOT_SPHERICAL,
                 COORDS_DISC: MODEL_DOT_DISC,
                 COORDS_PARABOLIC: MODEL_DOT_PARABOLIC}.get(
                     coords, MODEL_DOT_SPHERICAL)
    elif ndim == "1D":
        model = MODEL_1D
    elif ndim == "2D":
        model = MODEL_2D_CIRCULAR if coords == COORDS_CIRCULAR else MODEL_2D
    else:
        model = (MODEL_3D_CYLINDRICAL if coords == COORDS_CYLINDRICAL
                 else MODEL_3D)

    # When the designer matched on differences, the energy origin was
    # shifted: the measured targets count from E_F and the model counts from
    # the bottom of the well. Adding the offset to both sides puts everything
    # in the model's frame, which is the only one the receiving solver can
    # compare in.
    offset = float(solution.get("offset", 0.0) or 0.0)

    return SolutionSpec(
        model=model,
        dims_nm=tuple(solution["dims"]),
        coords=coords,
        meff=meff,
        V0_eV=V0_eV,
        # `targets` is usually an ndarray; `or ()` would be ambiguous on one.
        targets_eV=tuple(float(t) + offset for t in targets)
        if targets is not None else (),
        computed_eV=tuple(m["computed_E"] + offset
                          for m in solution.get("matches", [])),
        rrmse=solution.get("RRMSE", rrmse),
        origin=ORIGIN_DESIGNER,
        # How far up in quantum number the search had to go. The receiving
        # solver has to resolve at least that far, or the matched level
        # simply is not in its list and the error comes out huge for a
        # numerical reason rather than a physical one.
        extras={"sym": solution.get("sym", ""), "max_qn": _max_qn(solution),
                "offset_eV": offset, "match": solution.get("match", "")},
    )


def _max_qn(solution: dict) -> int:
    """The highest quantum number used by the solution's matches."""
    highest = 0
    for match in solution.get("matches", ()):
        for q in match.get("qn", ()):
            try:
                highest = max(highest, int(q))
            except (TypeError, ValueError):
                continue
    return highest
