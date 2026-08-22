"""
Quantum-confinement physics: closed-form levels, finite-difference solvers,
and the inverse designer that turns measured energies back into a geometry.

Ported from the standalone `calculadora_autoestados` app, which grew up
outside this repository and had to load TRANS's peak finder by file path.
Inside, it imports :mod:`src.processing.peak_detection` directly, so the
designer and Confinement Analysis agree on what a peak is by construction.

Nothing here imports a UI toolkit — no Tk, no Qt. The modules take numbers
and return numbers, so they run on a worker thread and can be tested
headless. Keys are English ``snake_case`` and are what gets compared and
persisted; display strings live in the ``*_LABELS`` maps beside them.

Units, everywhere: **nm and eV**. Joules and metres appear only inside a
function, never on a boundary.
"""
