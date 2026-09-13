"""
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy

Set-column-values formulas for the Unit Converter.

A formula is a one-line expression in ``x`` (the independent axis) and
``y`` (the spectra), e.g. ``x * 1e3`` to go from V to mV or
``y / 1e-9`` to read current in nA. It is evaluated with NumPy, so ``y``
is the whole spectra matrix at once and ``x`` a column that broadcasts
against it. This is what qtiplot / Origin call *Set Column Values*, made
aware of the spectral layout: one formula for the axis, one for every
spectrum, applied across a whole selection of datasets rather than column
by column.

The evaluator is deliberately not ``eval``: the source is parsed to an
AST and every node is checked against a whitelist before anything runs,
so a formula can do arithmetic and call the listed functions and nothing
else. Names are limited to the two data symbols, the constants and the
functions below.
"""

from __future__ import annotations

import ast
import math
from typing import Any, Dict, Optional

import numpy as np

# Functions a formula may call. Every one is elementwise or a reduction
# over the sample axis, so the result keeps the spectra's shape (or
# broadcasts back to it).
FUNCTIONS: Dict[str, Any] = {
    'sqrt': np.sqrt, 'cbrt': np.cbrt,
    'log': np.log, 'ln': np.log, 'log10': np.log10, 'log2': np.log2,
    'exp': np.exp, 'abs': np.abs, 'sign': np.sign,
    'sin': np.sin, 'cos': np.cos, 'tan': np.tan,
    'arcsin': np.arcsin, 'arccos': np.arccos, 'arctan': np.arctan,
    'sinh': np.sinh, 'cosh': np.cosh, 'tanh': np.tanh,
    'floor': np.floor, 'ceil': np.ceil, 'round': np.round,
    'clip': np.clip, 'where': np.where, 'minimum': np.minimum, 'maximum': np.maximum,
    'isfinite': np.isfinite, 'nan_to_num': np.nan_to_num,
    # Reductions along the sample axis, keepdims so they broadcast back:
    # ``y - min(y)`` shifts every spectrum by its own minimum.
    'min': lambda a, axis=0: np.nanmin(a, axis=axis, keepdims=True),
    'max': lambda a, axis=0: np.nanmax(a, axis=axis, keepdims=True),
    'mean': lambda a, axis=0: np.nanmean(a, axis=axis, keepdims=True),
    'median': lambda a, axis=0: np.nanmedian(a, axis=axis, keepdims=True),
    'std': lambda a, axis=0: np.nanstd(a, axis=axis, keepdims=True),
    'sum': lambda a, axis=0: np.nansum(a, axis=axis, keepdims=True),
    'cumsum': lambda a, axis=0: np.nancumsum(a, axis=axis),
    'gradient': lambda a, axis=0: np.gradient(a, axis=axis),
}

CONSTANTS: Dict[str, float] = {
    'pi': math.pi, 'e': math.e,
    # Physical constants in SI, for unit work: hc in eV·nm is the one that
    # comes up (wavelength ↔ photon energy), the rest are there for
    # completeness.
    'h': 6.62607015e-34, 'hbar': 1.054571817e-34, 'c': 299792458.0,
    'kB': 1.380649e-23, 'q': 1.602176634e-19, 'eV': 1.602176634e-19,
    'hc_eVnm': 1239.841984,
    'nan': float('nan'), 'inf': float('inf'),
}

_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Name, ast.Load,
    ast.Constant, ast.Compare, ast.BoolOp, ast.IfExp, ast.Tuple,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd, ast.Invert,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.And, ast.Or, ast.Not,
    ast.keyword,
)


class FormulaError(ValueError):
    """A formula that cannot be run: bad syntax or a name outside the whitelist."""


def normalise(source: str) -> str:
    """Accept the spreadsheet spellings: ``^`` for power, ``**`` as is."""
    text = (source or '').strip()
    # Only bare '^' — a '**' is already Python.
    return text.replace('^', '**')


def compile_formula(source: str) -> ast.Expression:
    """Parse and validate. Raises :class:`FormulaError` on anything not allowed."""
    text = normalise(source)
    if not text:
        raise FormulaError("empty formula")
    try:
        tree = ast.parse(text, mode='eval')
    except SyntaxError as exc:
        raise FormulaError(f"syntax error: {exc.msg}") from exc
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise FormulaError(f"'{type(node).__name__}' is not allowed in a formula")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
                name = getattr(getattr(node, 'func', None), 'id', '?')
                raise FormulaError(f"unknown function '{name}'")
        elif isinstance(node, ast.Name):
            if node.id not in ('x', 'y', 'i') and node.id not in CONSTANTS \
                    and node.id not in FUNCTIONS:
                raise FormulaError(f"unknown name '{node.id}' — use x, y, i, a constant or a function")
        elif isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, bool)):
            raise FormulaError("only numbers are allowed as literals")
    return tree


def evaluate(source: str, x: np.ndarray, y: np.ndarray,
             index: Optional[np.ndarray] = None) -> np.ndarray:
    """Run a formula with ``x`` as a column vector and ``y`` the spectra.

    ``x`` is reshaped to ``(n_samples, 1)`` so ``x * y`` broadcasts across
    every spectrum; ``i`` is the 0-based sample index, the same shape.
    """
    tree = compile_formula(source)
    x = np.asarray(x, dtype=np.float64).reshape(-1, 1)
    y = np.asarray(y, dtype=np.float64)
    if y.ndim == 1:
        y = y.reshape(-1, 1)
    i = (np.arange(x.shape[0], dtype=np.float64).reshape(-1, 1)
         if index is None else np.asarray(index, dtype=np.float64).reshape(-1, 1))
    namespace: Dict[str, Any] = {**FUNCTIONS, **CONSTANTS, 'x': x, 'y': y, 'i': i}
    code = compile(tree, '<formula>', 'eval')
    with np.errstate(all='ignore'):
        out = eval(code, {'__builtins__': {}}, namespace)  # noqa: S307 - AST-whitelisted
    return np.asarray(out, dtype=np.float64)


def apply_formulas(x: np.ndarray, y: np.ndarray, x_formula: str = '',
                   y_formula: str = ''):
    """New ``(x, y)`` after the two formulas; an empty formula leaves its
    side untouched. Both see the ORIGINAL x and y, so ``x`` in the y
    formula is the axis before conversion — a change of axis unit does not
    silently change what ``y / x`` means.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if y.ndim == 1:
        y = y.reshape(-1, 1)
    new_x, new_y = x, y
    if (x_formula or '').strip():
        res = np.asarray(evaluate(x_formula, x, y), dtype=np.float64)
        if res.size == 1:
            new_x = np.full(x.shape, float(res.reshape(-1)[0]))
        elif res.size == x.size:
            new_x = res.reshape(x.shape)
        else:
            raise FormulaError(
                f"the x formula must give one value per sample ({x.size}), got {res.size}")
    if (y_formula or '').strip():
        res = evaluate(y_formula, x, y)
        try:
            new_y = np.broadcast_to(res, y.shape).copy()
        except ValueError as exc:
            raise FormulaError(
                f"the y formula gives shape {res.shape}, the spectra are {y.shape}") from exc
    return new_x, new_y
