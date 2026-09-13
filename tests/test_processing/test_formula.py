"""
Tests for the Unit Converter's set-values formulas (src/processing/formula.py).
"""

import numpy as np
import pytest

from src.processing.formula import (FormulaError, apply_formulas, compile_formula,
                                    evaluate)


@pytest.fixture
def xy():
    x = np.linspace(-1.0, 1.0, 11)
    y = np.column_stack([x, 2 * x, x ** 2])
    return x, y


class TestEvaluation:
    def test_x_formula_rescales_the_axis_only(self, xy):
        x, y = xy
        nx, ny = apply_formulas(x, y, "x * 1e3", "")
        np.testing.assert_allclose(nx, x * 1e3)
        np.testing.assert_array_equal(ny, y)

    def test_y_formula_applies_to_every_spectrum(self, xy):
        x, y = xy
        nx, ny = apply_formulas(x, y, "", "y / 1e-9")
        np.testing.assert_array_equal(nx, x)
        np.testing.assert_allclose(ny, y / 1e-9)

    def test_x_broadcasts_across_spectra(self, xy):
        x, y = xy
        _, ny = apply_formulas(x, y, "", "y * x")
        np.testing.assert_allclose(ny, y * x[:, None])

    def test_both_formulas_see_the_original_axis(self, xy):
        """Changing x must not change what y / x means."""
        x, y = xy
        _, ny = apply_formulas(x, y, "x * 1e3", "y * x")
        np.testing.assert_allclose(ny, y * x[:, None])

    def test_reductions_are_per_spectrum(self, xy):
        x, y = xy
        _, ny = apply_formulas(x, y, "", "y - min(y)")
        assert np.all(ny.min(axis=0) == 0)
        assert ny.shape == y.shape

    def test_caret_is_power(self, xy):
        x, y = xy
        nx, _ = apply_formulas(x, y, "x^2", "")
        np.testing.assert_allclose(nx, x ** 2)

    def test_physical_constants(self, xy):
        x, y = xy
        nm = np.array([400.0, 620.0])
        e = evaluate("hc_eVnm / x", nm, np.zeros((2, 1)))
        np.testing.assert_allclose(e.ravel(), [3.0996, 1.99975], rtol=1e-4)

    def test_empty_formulas_are_identity(self, xy):
        x, y = xy
        nx, ny = apply_formulas(x, y, "", "   ")
        np.testing.assert_array_equal(nx, x)
        np.testing.assert_array_equal(ny, y)


class TestSafety:
    @pytest.mark.parametrize("bad", [
        '__import__("os").system("true")',
        "x.real",
        "open('f')",
        "lambda: 1",
        "x[0]",
        "'text'",
        "y if True else exec",
        "import os",
        "print(x)",
    ])
    def test_non_whitelisted_source_is_rejected(self, bad):
        with pytest.raises(FormulaError):
            compile_formula(bad)

    def test_unknown_name_is_named_in_the_error(self):
        with pytest.raises(FormulaError, match="foo"):
            compile_formula("x + foo")

    def test_syntax_error_is_a_formula_error(self):
        with pytest.raises(FormulaError, match="syntax"):
            compile_formula("x +* 2")

    def test_x_formula_must_keep_one_value_per_sample(self, xy):
        x, y = xy
        with pytest.raises(FormulaError):
            apply_formulas(x, y, "sum(y)", "")
