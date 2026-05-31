"""
Micro-benchmarks for the pyqtgraph-port work.

Tests in this directory use ``pytest-benchmark`` to assert real-world
thresholds for the native rendering paths added in Phases 3 (curve
rendering) and 7 (image levels + LUT) of the pyqtgraph port. They run
under the normal ``pytest tests/`` invocation but only emit timing
output when ``--benchmark-only`` is passed.

Phase 1 ships this directory empty (with the ``conftest.py`` shared
config) so subsequent phases can drop benchmark modules in without
re-bootstrapping the layout.
"""
