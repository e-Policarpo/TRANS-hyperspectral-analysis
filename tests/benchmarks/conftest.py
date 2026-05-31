"""
Shared pytest-benchmark configuration for the rendering benchmarks.

Pin ``min_rounds`` so a slow run on a busy machine doesn't flap the
threshold assertions. Importing ``pytest_benchmark`` is gated so the
rest of the suite still collects cleanly when the plugin isn't
installed (it's listed as optional in ``requirements.txt``).
"""

from __future__ import annotations

import pytest

pytest_benchmark = pytest.importorskip(
    "pytest_benchmark",
    reason="pytest-benchmark not installed; run `pip install pytest-benchmark`",
)


@pytest.fixture(autouse=True, scope="module")
def _bench_min_rounds(request):
    """Force every benchmark in this directory to run at least 5 rounds."""
    bench = getattr(request.config.option, "benchmark_min_rounds", None)
    if bench is None or bench < 5:
        request.config.option.benchmark_min_rounds = 5
    yield
