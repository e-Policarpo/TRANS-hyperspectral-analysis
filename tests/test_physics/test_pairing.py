"""
Testes do emparelhamento elétron–buraco.

O ponto do módulo é decidir quando duas candidatas — uma de cada portador —
descrevem o mesmo poço. Aqui isso é verificado sem Tk e sem solver.
"""

import pytest

from src.physics.pairing import (confinement_size_nm, dims_in_nm, geometry_mismatch,
                          pair_candidates, pair_score)
from src.physics.quantum_dot import hw_from_length, length_from_hw


def _sol(dims, rrmse=0.0, meff=0.067, ndim="1D", coords="cartesian"):
    return {"dims": tuple(dims), "RRMSE": rrmse, "meff": meff,
            "ndim": ndim, "coords": coords, "matches": [], "Ec": []}


# ─── dimensões e tamanho ─────────────────────────────────────────────────────

def test_dimensions_are_already_nanometres_for_ordinary_wells():
    assert dims_in_nm(_sol((8.0,))) == (8.0,)


def test_a_parabolic_dot_is_converted_from_meV_to_nanometres():
    """ħω depende da massa: comparar meV diria que geometrias iguais diferem."""
    l_nm = 6.0
    hw_e = hw_from_length(l_nm, 0.067)
    hw_h = hw_from_length(l_nm, 0.45)
    assert hw_e != pytest.approx(hw_h, rel=0.01)      # os meV são bem diferentes

    e = _sol((hw_e, hw_e), meff=0.067, ndim="0D", coords="parabolic")
    h = _sol((hw_h, hw_h), meff=0.45, ndim="0D", coords="parabolic")
    assert dims_in_nm(e, 0.067)[0] == pytest.approx(l_nm, rel=1e-9)
    mismatch_nm, _pct = geometry_mismatch(e, h)
    assert mismatch_nm == pytest.approx(0.0, abs=1e-6)  # é o mesmo ponto


def test_the_effective_size_is_the_geometric_mean():
    assert confinement_size_nm(_sol((2.0, 8.0), ndim="2D")) == pytest.approx(4.0)


# ─── discordância ────────────────────────────────────────────────────────────

def test_mismatch_is_the_worst_dimension_not_the_average():
    """3×12 e 12×3 têm o mesmo tamanho efetivo e não são a mesma coisa."""
    a = _sol((3.0, 12.0), ndim="2D")
    b = _sol((12.0, 3.0), ndim="2D")
    assert confinement_size_nm(a) == pytest.approx(confinement_size_nm(b))
    mismatch_nm, mismatch_pct = geometry_mismatch(a, b)
    assert mismatch_nm == pytest.approx(9.0)
    assert mismatch_pct == pytest.approx(120.0)


def test_a_small_disagreement_is_reported_in_nm_and_percent():
    mismatch_nm, mismatch_pct = geometry_mismatch(_sol((7.908,)), _sol((8.090,)))
    assert mismatch_nm == pytest.approx(0.182, abs=1e-3)
    assert mismatch_pct == pytest.approx(2.275, abs=0.01)


# ─── erro do par ─────────────────────────────────────────────────────────────

def test_the_pair_error_needs_all_three_terms_small():
    assert pair_score(0.0, 0.0, 0.0) == 0.0
    # Um lado perfeito não salva um par cuja geometria discorda.
    assert pair_score(0.0, 0.0, 6.0) > pair_score(2.0, 2.0, 0.0)


def test_the_geometry_term_can_be_weighted_down():
    assert pair_score(0, 0, 6.0, geometry_weight=0.1) < pair_score(0, 0, 6.0)


# ─── emparelhamento ──────────────────────────────────────────────────────────

def test_the_best_partner_is_chosen_for_each_electron():
    electrons = [_sol((8.0,), rrmse=0.1)]
    holes = [_sol((8.6,), rrmse=0.1, meff=0.45),
             _sol((8.05,), rrmse=0.1, meff=0.45)]
    pairs = pair_candidates(electrons, holes, tol_nm=1.0)
    assert len(pairs) == 1                      # um par por geometria de elétron
    assert pairs[0]["hole"]["dims"][0] == pytest.approx(8.05)


def test_pairs_beyond_the_tolerance_are_dropped():
    electrons = [_sol((8.0,))]
    holes = [_sol((9.5,), meff=0.45)]
    assert pair_candidates(electrons, holes, tol_nm=1.0) == []
    assert len(pair_candidates(electrons, holes, tol_nm=2.0)) == 1


def test_a_slight_mismatch_still_pairs():
    """7.908 nm para o elétron e 8.09 para o buraco são o mesmo poço."""
    pairs = pair_candidates([_sol((7.908,), rrmse=0.2)],
                            [_sol((8.090,), rrmse=0.3, meff=0.45)],
                            tol_nm=0.5)
    assert len(pairs) == 1
    assert pairs[0]["mismatch_nm"] == pytest.approx(0.182, abs=1e-3)
    assert pairs[0]["size_nm"] == pytest.approx(7.999, abs=1e-2)


def test_pairs_come_back_ranked_by_the_pair_error():
    electrons = [_sol((8.0,), rrmse=3.0), _sol((8.0,), rrmse=0.1)]
    holes = [_sol((8.0,), rrmse=0.1, meff=0.45)]
    pairs = pair_candidates(electrons, holes, tol_nm=1.0)
    assert [p["electron"]["RRMSE"] for p in pairs] == [0.1, 3.0]


def test_no_holes_means_no_pairs():
    assert pair_candidates([_sol((8.0,))], [], tol_nm=1.0) == []


# ─── bordas de banda a partir dos deslocamentos ──────────────────────────────

from src.physics.pairing import band_edges, edges_from_pair


def test_the_offsets_are_the_band_edges():
    """offset = E_modelo − E_medido, então ele É a posição da borda."""
    edges = band_edges(offset_e=-0.35, offset_h=-0.25)
    assert edges["E_c"] == pytest.approx(0.35)
    assert edges["E_v"] == pytest.approx(-0.25)
    assert edges["gap"] == pytest.approx(0.60)


def test_boundaries_and_offsets_add_up_the_same_way():
    """Medir a partir da fronteira ou de E_F tem de dar a mesma borda."""
    de_ef = band_edges(-0.35, -0.25, split_e=0.0, split_h=0.0)
    da_borda = band_edges(0.0, 0.0, split_e=0.35, split_h=-0.25)
    assert da_borda == pytest.approx(de_ef)


def test_a_charged_well_puts_the_conduction_edge_below_ef():
    """E_c < 0 é o poço dopado n: níveis de elétron ocupados."""
    # E_c = −offset_e e E_v = +offset_h (fronteiras em zero).
    edges = band_edges(offset_e=+0.10, offset_h=-0.75)
    assert edges["E_c"] == pytest.approx(-0.10)
    assert edges["E_v"] == pytest.approx(-0.75)
    assert edges["gap"] == pytest.approx(0.65)


def test_edges_from_a_pair_read_each_side_of_it():
    pair = {"electron": {"offset": -0.35}, "hole": {"offset": -0.25}}
    assert edges_from_pair(pair)["gap"] == pytest.approx(0.60)
    assert edges_from_pair({"electron": None, "hole": None}) is None
