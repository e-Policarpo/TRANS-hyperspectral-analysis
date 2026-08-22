"""
Testes do confinamento 0D (ponto quântico).

Cada caso é conferido contra um resultado que se conhece de antemão: os zeros
de j_l, a fórmula do poço esférico infinito, as degenerescências de camada e
os números mágicos de preenchimento.
"""

import numpy as np
import pytest
from scipy.constants import hbar, m_e, e

from src.physics.quantum_dot import (spherical_dot, disc_dot, parabolic_dot,
                              shell_table, addition_energies, level_spectrum,
                              orbital_label, _spherical_jn_zeros)


# ─── zeros de j_l ────────────────────────────────────────────────────────────

def test_spherical_bessel_zeros_match_the_known_values():
    np.testing.assert_allclose(_spherical_jn_zeros(0, 3),
                               [np.pi, 2 * np.pi, 3 * np.pi], rtol=1e-6)
    np.testing.assert_allclose(_spherical_jn_zeros(1, 2), [4.493409, 7.725252], rtol=1e-5)
    np.testing.assert_allclose(_spherical_jn_zeros(2, 2), [5.763459, 9.095011], rtol=1e-5)


# ─── esférico, barreira infinita ─────────────────────────────────────────────

def test_ground_state_matches_the_analytic_formula():
    R_nm, meff = 5.0, 0.067
    levels = spherical_dot(R_nm, V0_eV=None, meff=meff, l_max=0, n_per_channel=1)
    expected = (hbar ** 2 * np.pi ** 2) / (2 * meff * m_e * (R_nm * 1e-9) ** 2) / e
    assert levels[0].E_eV == pytest.approx(expected, rel=1e-9)
    assert levels[0].label == "1s"


def test_energies_scale_as_one_over_R_squared():
    a = spherical_dot(4.0, meff=0.067, l_max=0, n_per_channel=1)[0].E_eV
    b = spherical_dot(8.0, meff=0.067, l_max=0, n_per_channel=1)[0].E_eV
    assert a / b == pytest.approx(4.0, rel=1e-6)


def test_shells_have_the_2l_plus_1_degeneracy():
    levels = spherical_dot(5.0, meff=0.067, l_max=3, n_per_channel=1)
    by_label = {lv.label: lv for lv in levels}
    assert by_label["1s"].degeneracy == 1
    assert by_label["1p"].degeneracy == 3
    assert by_label["1d"].degeneracy == 5
    assert by_label["1f"].degeneracy == 7


def test_the_filling_numbers_are_the_magic_ones():
    """2, 8, 18, 20 — as camadas fechadas de uma caixa esférica."""
    levels = spherical_dot(5.0, meff=0.067, l_max=3, n_per_channel=2)
    filled = [shell[3] for shell in shell_table(levels)]
    assert filled[:4] == [2, 8, 18, 20]


def test_the_ordering_is_1s_1p_1d_2s():
    levels = spherical_dot(5.0, meff=0.067, l_max=2, n_per_channel=2)
    assert [lv.label for lv in levels[:4]] == ["1s", "1p", "1d", "2s"]


# ─── esférico, barreira finita ───────────────────────────────────────────────

def test_a_finite_barrier_lowers_every_level():
    """A função vaza para a barreira, então o poço confina menos."""
    infinite = spherical_dot(5.0, V0_eV=None, meff=0.067, l_max=1, n_per_channel=1)
    finite = spherical_dot(5.0, V0_eV=1.0, meff=0.067, l_max=1, n_per_channel=1, N=1200)

    for lv_inf, lv_fin in zip(infinite, finite):
        assert lv_fin.label == lv_inf.label
        assert lv_fin.E_eV < lv_inf.E_eV


def test_a_deeper_barrier_approaches_the_infinite_result():
    infinite = spherical_dot(5.0, V0_eV=None, meff=0.067, l_max=0, n_per_channel=1)[0]
    shallow = spherical_dot(5.0, V0_eV=0.5, meff=0.067, l_max=0, n_per_channel=1, N=1500)[0]
    deep = spherical_dot(5.0, V0_eV=5.0, meff=0.067, l_max=0, n_per_channel=1, N=1500)[0]

    assert abs(deep.E_eV - infinite.E_eV) < abs(shallow.E_eV - infinite.E_eV)


def test_states_above_the_barrier_are_not_reported():
    """Um poço raso liga poucos estados; os demais não são ligados."""
    levels = spherical_dot(5.0, V0_eV=0.1, meff=0.067, l_max=3, n_per_channel=3, N=1200)
    assert levels, "o estado fundamental deveria caber"
    assert all(lv.E_eV < 0.1 for lv in levels)
    assert len(levels) < 4 * 3


def test_a_shallow_enough_dot_binds_nothing():
    assert spherical_dot(1.0, V0_eV=0.005, meff=0.067, l_max=0,
                         n_per_channel=1, N=1200) == []


def test_the_radial_function_is_normalised_and_vanishes_at_the_wall():
    lv = spherical_dot(5.0, meff=0.067, l_max=0, n_per_channel=1)[0]
    r_m = lv.r_nm * 1e-9
    assert np.trapz(lv.radial ** 2, r_m) == pytest.approx(1.0, rel=1e-3)
    assert abs(lv.radial[-1]) < 1e-6 * np.max(np.abs(lv.radial))


# ─── disco ───────────────────────────────────────────────────────────────────

def test_disc_levels_are_the_plane_plus_z_energies():
    from src.physics.analytical import disk_energies, box_energies_1d_eV

    R_nm, Lz_nm, meff = 10.0, 3.0, 0.067
    levels = disc_dot(R_nm, Lz_nm, V0_eV=None, meff=meff,
                      m_max=0, n_per_channel=1, nz_max=1)
    plane = disk_energies(R_nm, meff, 1)[0][0]      # já em eV
    z = box_energies_1d_eV(Lz_nm, meff, 1)[0][0]
    assert levels[0].E_eV == pytest.approx(plane + z, rel=1e-6)


def test_nonzero_m_states_are_doubly_degenerate():
    levels = disc_dot(10.0, 3.0, meff=0.067, m_max=2, n_per_channel=1, nz_max=1)
    for lv in levels:
        _n, m_q, _nz = lv.quantum_numbers
        assert lv.degeneracy == (1 if m_q == 0 else 2)


def test_a_thinner_disc_pushes_everything_up():
    thick = disc_dot(10.0, 6.0, meff=0.067, m_max=0, n_per_channel=1, nz_max=1)[0]
    thin = disc_dot(10.0, 2.0, meff=0.067, m_max=0, n_per_channel=1, nz_max=1)[0]
    assert thin.E_eV > thick.E_eV


# ─── parabólico ──────────────────────────────────────────────────────────────

def test_parabolic_levels_follow_the_oscillator_formula():
    levels = parabolic_dot(30.0, 100.0, n_shells=3)
    assert levels[0].E_eV * 1000 == pytest.approx(30 * 1 + 100 * 0.5)
    assert levels[0].degeneracy == 1


def test_parabolic_shell_degeneracy_grows_with_the_shell():
    levels = parabolic_dot(30.0, 500.0, n_shells=4)   # z bem separado
    in_plane = [lv for lv in levels if lv.quantum_numbers[1] == 0]
    assert [lv.degeneracy for lv in in_plane[:4]] == [1, 2, 3, 4]


def test_parabolic_rejects_a_zero_confinement():
    with pytest.raises(ValueError):
        parabolic_dot(0.0, 100.0)


# ─── análise ─────────────────────────────────────────────────────────────────

def test_addition_energy_peaks_at_a_closed_shell():
    """Fechar 1s (2 elétrons) custa o salto até 1p; dentro da camada, nada."""
    levels = spherical_dot(5.0, meff=0.067, l_max=1, n_per_channel=1)
    add = addition_energies(levels)
    gap = levels[1].E_eV - levels[0].E_eV

    assert add[1] == pytest.approx(gap)     # 2 -> 3: muda de camada
    assert add[0] == pytest.approx(0.0)     # 1 -> 2: mesmo nível
    assert add[2] == pytest.approx(0.0)     # dentro de 1p


def test_the_charging_energy_offsets_every_addition():
    levels = spherical_dot(5.0, meff=0.067, l_max=1, n_per_channel=1)
    plain = addition_energies(levels)
    charged = addition_energies(levels, charging_eV=0.02)
    np.testing.assert_allclose(np.array(charged) - np.array(plain), 0.02)


def test_the_dos_puts_a_taller_peak_on_a_more_degenerate_shell():
    levels = spherical_dot(5.0, meff=0.067, l_max=1, n_per_channel=1)
    grid, dos = level_spectrum(levels, broadening_eV=0.002)

    height_at = lambda E: dos[np.argmin(np.abs(grid - E))]
    assert height_at(levels[1].E_eV) > 2 * height_at(levels[0].E_eV)   # 1p vs 1s


def test_the_dos_is_empty_for_a_dot_with_no_states():
    grid, dos = level_spectrum([])
    assert grid.size == 0 and dos.size == 0


def test_occupancy_counts_spin():
    levels = spherical_dot(5.0, meff=0.067, l_max=1, n_per_channel=1)
    assert levels[0].occupancy == 2       # 1s
    assert levels[1].occupancy == 6       # 1p


def test_orbital_labels_run_s_p_d_f():
    assert [orbital_label(1, l) for l in range(4)] == ["1s", "1p", "1d", "1f"]
    assert orbital_label(2, 0) == "2s"


def test_a_negative_radius_is_refused():
    with pytest.raises(ValueError):
        spherical_dot(-1.0)
