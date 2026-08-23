"""
Tests for features as plain data.

The editor's whole vocabulary: a feature is a map of numbers it can list,
edit, drag and save, and a physics object it can build a potential from. What
has to hold is that the two agree — a spec built into a feature and read back
is the same spec — and that positions mean the same thing to a hit test as to
a drag, which is where an anchored rectangle catches people out.
"""

from __future__ import annotations

import pytest

from src.physics import feature_specs as specs


class TestTheTable:
    def test_every_kind_builds_from_its_defaults(self):
        """A kind nobody can construct is a kind that will crash an editor."""
        for kind in specs.FEATURE_FIELDS:
            spec = specs.default_spec(kind)
            assert specs.build_feature(spec) is not None, kind

    def test_every_kind_has_a_label_and_a_position(self):
        for kind in specs.FEATURE_FIELDS:
            assert kind in specs.KIND_LABELS, kind
            assert kind in specs.POSITION_FIELDS, kind

    def test_the_kinds_are_split_by_dimensionality(self):
        """A 1D feature in a 2D box has no meaning, and offering it is how a
        nonsense potential gets built."""
        assert set(specs.KINDS_1D + specs.KINDS_2D + specs.KINDS_3D) == \
            set(specs.FEATURE_FIELDS)
        assert set(specs.KINDS_2D).isdisjoint(specs.KINDS_3D)

    def test_every_field_has_a_label(self):
        for kind in specs.FEATURE_FIELDS:
            for name in specs.field_names(kind):
                assert name in specs.FIELD_LABELS, f"{kind}.{name}"

    def test_the_common_fields_are_on_every_kind(self):
        for kind in specs.FEATURE_FIELDS:
            names = specs.field_names(kind)
            assert 'V0' in names and 'meff' in names, kind

    def test_an_unknown_kind_is_refused_by_name(self):
        with pytest.raises(ValueError, match="unknown feature kind"):
            specs.field_names('trapezoid')
        with pytest.raises(ValueError, match="unknown feature kind"):
            specs.build_feature({'kind': 'trapezoid'})


class TestBuildingAndReadingBack:
    def test_a_spec_round_trips_through_its_feature(self):
        for kind in specs.FEATURE_FIELDS:
            spec = specs.default_spec(kind, position=(5.0, 6.0, 7.0))
            back = specs.spec_from_feature(specs.build_feature(spec))
            assert back == pytest.approx(spec), kind

    def test_the_1d_and_2d_gaussians_are_told_apart(self):
        """They share a `kind` on the class, so only the type identifies
        them — reading one back as the other would silently change what a
        model means."""
        one_d = specs.build_feature(specs.default_spec('gaussian_1d'))
        two_d = specs.build_feature(specs.default_spec('gaussian_2d'))

        assert specs.spec_from_feature(one_d)['kind'] == 'gaussian_1d'
        assert specs.spec_from_feature(two_d)['kind'] == 'gaussian_2d'

    def test_a_polygon_keeps_its_side_count_as_a_whole_number(self):
        spec = specs.default_spec('prism')
        spec['n_sides'] = 6
        back = specs.spec_from_feature(specs.build_feature(spec))

        assert back['n_sides'] == 6
        assert isinstance(back['n_sides'], int)

    def test_unknown_keys_are_ignored_rather_than_refused(self):
        """A spec that has been through a UI carries selection state and
        labels the physics has no use for."""
        spec = specs.default_spec('circle')
        spec.update({'selected': True, 'label': "F0", 'colour': "#fff"})

        assert specs.build_feature(spec) is not None

    def test_one_bad_feature_does_not_cost_the_others(self):
        built = specs.build_features([specs.default_spec('circle'),
                                      {'kind': 'nonsense'},
                                      specs.default_spec('rect')])

        assert len(built) == 2


class TestWhereAFeatureIs:
    def test_a_centred_shape_sits_where_it_was_put(self):
        spec = specs.default_spec('circle', position=(5.0, 6.0))

        assert specs.spec_position(spec) == pytest.approx((5.0, 6.0))

    def test_a_rectangle_is_anchored_by_its_corner(self):
        """The class stores x0/y0; a hit test and a drag both want the
        centre, so the correction has to live in one place."""
        spec = specs.default_spec('rect', position=(10.0, 10.0))

        assert spec['x0'] == pytest.approx(10.0 - spec['w'] / 2)
        assert specs.spec_position(spec) == pytest.approx((10.0, 10.0))

    def test_moving_and_reading_back_agree(self):
        """On as many axes as the kind has: a 1D feature has one position,
        and asking where its y is would be asking about an axis it does not
        live on."""
        for kind in specs.FEATURE_FIELDS:
            spec = specs.default_spec(kind)
            axes = (0,) if kind in specs.KINDS_1D else (0, 1)
            target = (3.0, 4.0)[:len(axes)]
            moved = specs.move_spec(spec, target, axes=axes)
            assert specs.spec_position(moved, axes) == pytest.approx(target), kind

    def test_a_drag_in_a_projection_moves_only_its_two_axes(self):
        """Editing a volume one plane at a time is what makes the interaction
        unambiguous: the hidden coordinate stays where it was."""
        spec = specs.default_spec('sphere', position=(5.0, 6.0, 7.0))
        moved = specs.move_spec(spec, (1.0, 2.0), axes=(0, 2))

        assert moved['cx'] == pytest.approx(1.0)
        assert moved['cz'] == pytest.approx(2.0)
        assert moved['cy'] == pytest.approx(6.0)

    def test_a_2d_shape_has_nothing_on_the_third_axis(self):
        spec = specs.default_spec('circle', position=(5.0, 6.0))

        assert specs.spec_position(spec, axes=(0, 2))[1] == 0.0


class TestHowBigAFeatureIs:
    def test_a_size_is_halved_and_a_radius_is_not(self):
        circle = specs.default_spec('circle')
        rect = specs.default_spec('rect')

        assert specs.spec_extent(circle)[0] == pytest.approx(circle['r'])
        assert specs.spec_extent(rect)[0] == pytest.approx(rect['w'] / 2)

    def test_a_gaussian_ends_where_it_stops_counting(self):
        """It has no edge; 3σ is where `contains` stops, so that is what a
        hit test and an outline both use."""
        spec = specs.default_spec('gaussian_2d')

        assert specs.spec_extent(spec)[0] == pytest.approx(3 * spec['sx'])

    def test_a_cylinder_is_round_from_above_and_square_from_the_side(self):
        spec = specs.default_spec('cylinder')
        spec.update({'R': 3.0, 'H': 8.0})

        assert specs.spec_extent(spec, (0, 1)) == pytest.approx((3.0, 3.0))
        assert specs.spec_extent(spec, (0, 2)) == pytest.approx((3.0, 4.0))

    def test_an_unknown_axis_has_no_extent(self):
        spec = specs.default_spec('circle')

        assert specs.spec_extent(spec, axes=(0, 2))[1] == 0.0


class TestNewFeatures:
    def test_a_new_feature_is_visible_rather_than_a_point(self):
        """Defaults of zero would add a feature nobody can see or grab."""
        for kind in specs.FEATURE_FIELDS:
            spec = specs.default_spec(kind)
            extent = specs.spec_extent(spec, (0, 1))
            assert max(extent) > 0, kind

    def test_a_new_feature_is_a_well_by_default(self):
        """A barrier is the unusual case; a well is what people are placing."""
        assert specs.default_spec('circle')['V0'] < 0

    def test_the_depth_and_mass_can_be_asked_for(self):
        spec = specs.default_spec('circle', V0_eV=-0.75, meff=0.045)

        assert spec['V0'] == pytest.approx(-0.75)
        assert spec['meff'] == pytest.approx(0.045)
