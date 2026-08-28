"""
Tests for the two feature shapes whose geometry is easy to get half right.

A triangle and a lens are both tapers, and a taper is where "it looks about
right on screen" stops being evidence: the outline can be drawn correctly
while ``contains`` disagrees with it, or the body can sit half its height off
and still fill the box it is expected to. Both are checked here against the
closed form of the shape rather than against a picture.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import numpy as np
import pytest

from src.physics import feature_specs as specs
from src.physics.features import LensFeature3D, TriangleFeature2D


def _mask(feature, *axes):
    """``contains`` over a mesh of the axes given, in index order."""
    meshes = np.meshgrid(*axes, indexing='ij')
    return feature.contains(*meshes)


def _span(axis, mask, which):
    """First and last coordinate on `which` axis that the mask covers."""
    collapsed = mask.any(axis=tuple(i for i in range(mask.ndim)
                                    if i != which))
    hits = axis[collapsed]
    return (hits.min(), hits.max()) if hits.size else (np.nan, np.nan)


class TestTheTriangle:
    """Isoceles, apex toward +y, base on y = cy - h/2."""

    @pytest.fixture
    def tri(self):
        return TriangleFeature2D(6.0, 5.0, 4.0, 3.0, -0.3, 0.067)

    def test_it_fills_the_box_its_fields_describe(self, tri):
        x = np.arange(2.0, 10.0, 0.01)
        y = np.arange(2.0, 8.0, 0.01)
        mask = _mask(tri, x, y)

        assert _span(x, mask, 0) == pytest.approx((4.0, 8.0), abs=0.011)
        assert _span(y, mask, 1) == pytest.approx((3.5, 6.5), abs=0.011)

    @pytest.mark.parametrize("y_at,width", [(3.5, 4.0), (5.0, 2.0), (6.5, 0.0)])
    def test_the_taper_closes_linearly_onto_the_apex(self, tri, y_at, width):
        """Full width at the base, nothing at the apex, and half way in
        between — the cone's rule read in the plane."""
        x = np.arange(2.0, 10.0, 0.001)
        inside = tri.contains(x, np.full_like(x, y_at))

        assert inside.sum() * 0.001 == pytest.approx(width, abs=0.01)

    def test_its_area_is_half_the_bounding_box(self, tri):
        x = np.arange(2.0, 10.0, 0.005)
        y = np.arange(2.0, 8.0, 0.005)

        area = _mask(tri, x, y).sum() * 0.005 ** 2
        assert area == pytest.approx(4.0 * 3.0 / 2, rel=0.01)

    def test_the_apex_points_at_positive_y(self, tri):
        """Which end is the point is the one thing a symmetric outline cannot
        tell you, and getting it backwards flips every model built with one."""
        x = np.arange(2.0, 10.0, 0.01)
        near_base = tri.contains(x, np.full_like(x, 3.6)).sum()
        near_apex = tri.contains(x, np.full_like(x, 6.4)).sum()

        assert near_base > near_apex

    def test_a_height_of_zero_is_an_empty_shape_not_a_crash(self):
        """A form can hand this in the moment someone clears the field, so it
        has to be a non-answer rather than a division by zero."""
        flat = TriangleFeature2D(6.0, 5.0, 4.0, 0.0, -0.3)
        x = np.arange(2.0, 10.0, 0.01)
        y = np.arange(2.0, 8.0, 0.01)
        mask = _mask(flat, x, y)

        assert mask.sum() * 0.01 ** 2 == pytest.approx(0.0, abs=1e-3)
        assert not mask[:, y != pytest.approx(5.0, abs=0.011)].any()

    def test_a_width_of_zero_leaves_nothing_but_the_centre_line(self):
        thin = TriangleFeature2D(6.0, 5.0, 0.0, 3.0, -0.3)
        x = np.arange(2.0, 10.0, 0.01)
        y = np.arange(2.0, 8.0, 0.01)
        mask = _mask(thin, x, y)

        assert mask.sum() * 0.01 ** 2 == pytest.approx(0.0, abs=1e-3)
        assert not mask[np.abs(x - 6.0) > 0.011, :].any()

    def test_a_negative_size_is_a_non_answer(self):
        for w, h in [(-4.0, 3.0), (4.0, -3.0)]:
            feature = TriangleFeature2D(6.0, 5.0, w, h, -0.3)
            x = np.arange(2.0, 10.0, 0.02)
            y = np.arange(2.0, 8.0, 0.02)

            assert _mask(feature, x, y).sum() < 5, (w, h)

    def test_it_is_where_the_editor_says_it_is(self, tri):
        assert tri.center_nm() == pytest.approx((6.0, 5.0))


class TestTheTriangleAsASpec:
    def test_the_editor_offers_it_in_two_dimensions_only(self):
        assert 'triangle' in specs.KINDS_2D
        assert 'triangle' not in specs.KINDS_3D

    def test_its_fields_are_the_ones_the_class_takes(self):
        assert specs.field_names('triangle') == ('cx', 'cy', 'w', 'h',
                                                 'V0', 'meff')

    def test_a_spec_round_trips_through_its_feature(self):
        spec = dict(specs.default_spec('triangle', (6.0, 5.0)), w=4.0, h=3.0)
        back = specs.spec_from_feature(specs.build_feature(spec))

        assert back == pytest.approx(spec)

    def test_a_drag_moves_it_by_its_centre(self):
        spec = specs.default_spec('triangle', (6.0, 5.0))
        moved = specs.move_spec(spec, (12.0, 9.0))

        assert specs.spec_position(moved) == pytest.approx((12.0, 9.0))

    def test_its_extent_is_the_half_size_a_handle_grabs(self):
        spec = dict(specs.default_spec('triangle'), w=4.0, h=3.0)

        assert specs.spec_extent(spec) == pytest.approx((2.0, 1.5))


class TestTheLensSpansItsCentre:
    """cz is the centre of the body, not the base it used to be."""

    @pytest.fixture
    def lens(self):
        return LensFeature3D(10.0, 10.0, 7.0, 4.0, 3.0, -0.3, 0.067)

    def test_the_body_is_centred_on_cz(self, lens):
        """Half above, half below — what the position and extent tables have
        claimed all along, and what a box, a sphere and a cylinder do."""
        z = np.arange(4.0, 10.0, 0.02) + 1e-9
        centre = np.full_like(z, 10.0)
        inside = lens.contains(centre, centre, z)

        assert z[inside].min() == pytest.approx(5.5, abs=0.021)
        assert z[inside].max() == pytest.approx(8.5, abs=0.021)

    def test_nothing_sits_below_the_base_plane(self, lens):
        assert not lens.contains(np.float64(10.0), np.float64(10.0),
                                 np.float64(5.48))

    def test_its_widest_section_is_on_the_base(self, lens):
        """A spherical cap is widest where it stands. Anywhere else and R is
        not the radius the field says it is."""
        x = np.arange(4.0, 16.0, 0.01)
        on_base = lens.contains(x, np.full_like(x, 10.0),
                                np.full_like(x, 5.5 + 1e-9))

        assert (x[on_base].max() - x[on_base].min()) == pytest.approx(8.0,
                                                                      abs=0.03)

    def test_it_closes_to_a_point_at_the_apex(self, lens):
        x = np.arange(4.0, 16.0, 0.01)
        at_apex = lens.contains(x, np.full_like(x, 10.0),
                                np.full_like(x, 8.5 - 1e-9))

        assert at_apex.sum() * 0.01 < 0.1

    def test_the_section_follows_the_cap_it_is_cut_from(self, lens):
        """Rs = (R² + H²)/2H, centred H - Rs above the base — derived here
        rather than read off the class, so a shifted body cannot pass."""
        Rs = (4.0 ** 2 + 3.0 ** 2) / (2 * 3.0)
        x = np.arange(4.0, 16.0, 0.005)

        for z_rel in (0.0, 0.75, 1.5, 2.25):
            expected = np.sqrt(Rs ** 2 - (z_rel - (3.0 - Rs)) ** 2)
            cut = lens.contains(x, np.full_like(x, 10.0),
                                np.full_like(x, 5.5 + z_rel + 1e-9))
            radius = (x[cut].max() - x[cut].min()) / 2

            assert radius == pytest.approx(expected, abs=0.01), z_rel

    def test_the_position_and_extent_tables_are_true_of_it(self, lens):
        spec = specs.spec_from_feature(lens)

        assert specs.spec_position(spec, (0, 1, 2)) == \
            pytest.approx((10.0, 10.0, 7.0))
        assert specs.spec_extent(spec, (0, 2)) == pytest.approx((4.0, 1.5))
