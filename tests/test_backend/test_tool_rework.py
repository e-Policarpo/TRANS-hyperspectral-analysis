"""
Tests for the tool rework: list-selection batch specs, the Map Generator's
spatial-averaging step, the reworked 1D FFT, the Unit Converter backend,
Curve Plotting and the Gradient Filter's source resolution.
"""

from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from src.backend import batch_tools
from src.backend.app_backend import AppBackend
from src.backend.tool_implementations import ToolImplementations
from src.models.spectral_data import SpectralData, SpectralMetadata


class Task:
    cancelled = False
    progress = 0.0


def make_dataset(n_points=50, n_spectra=6, dims=(3, 2), x_unit='V', y_unit='A'):
    x = np.linspace(-1, 1, n_points)
    spectra = np.column_stack([np.exp(-(x - 0.1 * i) ** 2 / 0.05) + i
                               for i in range(n_spectra)])
    df = pd.DataFrame(np.column_stack([x, spectra]),
                      columns=['Bias'] + [f'S{i}' for i in range(n_spectra)])
    meta = SpectralMetadata(source_type='test', dimensions=dims, scan_mode='raster',
                            units={'independent': x_unit, 'dependent': y_unit},
                            additional_info={})
    return SpectralData(df, meta)


@pytest.fixture
def stub(tmp_path):
    """An AppBackend-shaped object with only what the tested methods touch."""
    class Stub(ToolImplementations):
        def __init__(self):
            self._datasets = {}
            self._images = {}
            self.maps = []
            self._maps_inmem = {}
            self._workflow_mode = False
            self.status = ""
            self.errorOccurred = Mock()
            self.dataLoaded = Mock()
            self.openDatasetEmbedded = Mock()
            self.toolCompleted = Mock()
            self._mark_project_modified = Mock()
            self._route_derived_datasets = Mock()
            self._out = tmp_path

        def _ensure_output_dir(self, sub):
            p = self._out / sub
            p.mkdir(parents=True, exist_ok=True)
            return p

        def _sanitize_filename(self, name):
            return "".join(c if c.isalnum() else "_" for c in name)

        def _extract_clean_base_name(self, name):
            return name

        def _apply_naming_convention(self, name, operation=""):
            return f"{name}_{operation}" if operation else name

    return Stub()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry:
    @pytest.mark.parametrize("key,method", [
        ('average_curves', 'average_curves'),
        ('smooth_curves', 'smooth_curves'),
        ('fft_1d', '_do_fft1D'),
        ('truncate', '_do_truncate_data'),
        ('curve_background_flattening', 'fit_curves'),
        ('gradient_filter', 'apply_gradient_filter'),
        ('multi_peak_fit', 'fit_multipeak_dataset'),
        ('axis_convert', 'convert_axis_dataset'),
        ('unit_formula', 'apply_formula_dataset'),
    ])
    def test_every_list_enabled_tool_is_registered(self, key, method):
        spec = batch_tools.get_spec(key)
        assert spec is not None and spec.method == method
        assert spec.takes_task

    def test_every_spec_names_a_real_method(self):
        for key, spec in batch_tools.BATCH_TOOLS.items():
            assert hasattr(AppBackend, spec.method), f"{key}: {spec.method}"
            if spec.completion:
                assert hasattr(AppBackend, spec.completion), f"{key}: {spec.completion}"

    def test_renamed_tools_carry_the_new_labels(self):
        assert batch_tools.get_spec('curve_background_flattening').label == "Curve Background Flattening"
        assert batch_tools.get_spec('unit_formula').label == "Unit Converter"

    def test_qml_floats_reach_the_smoother_as_ints(self):
        kw = batch_tools.get_spec('smooth_curves').coerce({'window_size': 11.0, 'poly_order': 3.0})
        assert kw['window_size'] == 11 and isinstance(kw['window_size'], int)
        assert kw['smoothing_type'] == 'savgol'


# ---------------------------------------------------------------------------
# Map Generator: spatial averaging step
# ---------------------------------------------------------------------------

class TestSpatialBinning:
    def test_one_by_one_is_identity(self):
        s = np.arange(12.0).reshape(3, 4)
        out, dims, kind, cols, members = ToolImplementations._bin_spectra_spatially(
            s, (4, 1), 'map_raster', 1, 1, list('abcd'))
        np.testing.assert_array_equal(out, s)
        assert cols == list('abcd') and members == [[0], [1], [2], [3]]

    def test_raster_blocks_average_neighbours(self):
        # 4 wide x 2 high, values equal to the spectrum index
        s = np.tile(np.arange(8.0), (3, 1))
        out, dims, kind, cols, members = ToolImplementations._bin_spectra_spatially(
            s, (4, 2), 'map_raster', 2, 2)
        assert dims == (2, 1) and kind == 'map_raster'
        # block 0: spectra 0,1 (row 0) and 4,5 (row 1) -> mean 2.5
        assert members[0] == [0, 1, 4, 5]
        np.testing.assert_allclose(out[:, 0], 2.5)
        np.testing.assert_allclose(out[:, 1], np.mean([2, 3, 6, 7]))

    def test_meander_reverses_odd_rows_before_blocking(self):
        s = np.tile(np.arange(8.0), (3, 1))
        _, _, _, _, members = ToolImplementations._bin_spectra_spatially(
            s, (4, 2), 'map_meander', 2, 2)
        # Row 1 was acquired right-to-left: its first two positions are
        # spectra 7 and 6, which sit under spectra 0 and 1.
        assert members[0] == [0, 1, 7, 6]

    def test_line_bins_along_the_line_only(self):
        s = np.tile(np.arange(5.0), (3, 1))
        out, dims, kind, cols, members = ToolImplementations._bin_spectra_spatially(
            s, (5, 1), 'line', 2, 7)
        assert kind == 'line' and dims == (3, 1)
        assert members == [[0, 1], [2, 3], [4]]     # ragged edge kept
        np.testing.assert_allclose(out[0], [0.5, 2.5, 4.0])

    def test_grid_mismatch_is_an_error(self):
        with pytest.raises(ValueError):
            ToolImplementations._bin_spectra_spatially(np.zeros((3, 7)), (4, 2),
                                                       'map_raster', 2, 2)

    def test_map_generator_registers_the_averaged_spectra(self, stub):
        stub._datasets['d'] = make_dataset(n_spectra=6, dims=(3, 2))
        name = stub._register_binned_spectra(
            stub._datasets['d'], 'd', np.zeros((50, 2)), np.linspace(-1, 1, 50),
            (2, 1), 'map_raster', ['Block_0_0', 'Block_0_1'], [[0, 1, 3, 4], [2, 5]], 2, 2)
        assert name == 'd - Spatially Averaged (2x2)'
        ds = stub._datasets[name]
        assert ds.metadata.dimensions == (2, 1)
        assert ds.metadata.additional_info['spatial_bin'] == [2, 2]
        assert ds.metadata.additional_info['original'] == 'd'


# ---------------------------------------------------------------------------
# 1D FFT
# ---------------------------------------------------------------------------

class TestFFT:
    def test_magnitude_and_phase_datasets_with_reciprocal_unit(self, stub):
        stub._datasets['d'] = make_dataset(x_unit='V')
        path = AppBackend._do_fft1D(stub, Task(), 'd', window='hann', detrend=True,
                                    one_sided=True, power_spectrum=False)
        assert path.endswith('_Magnitude.csv')
        mag = stub._datasets['d - FFT Magnitude']
        ph = stub._datasets['d - FFT Phase']
        assert mag.metadata.units['independent'] == '1/V'
        assert ph.metadata.units['dependent'] == 'rad'
        assert mag.independent_var_name == 'Frequency (1/V)'
        assert np.all(mag.independent_var >= 0)         # one-sided
        assert mag.num_spectra == 6

    def test_detrend_removes_the_dc_term(self, stub):
        stub._datasets['d'] = make_dataset()
        AppBackend._do_fft1D(stub, Task(), 'd', window='none', detrend=True)
        mag = stub._datasets['d - FFT Magnitude']
        assert np.allclose(mag.spectra.values[0], 0, atol=1e-8)

    def test_power_spectrum_is_named_and_squared(self, stub):
        stub._datasets['d'] = make_dataset()
        AppBackend._do_fft1D(stub, Task(), 'd', window='none', detrend=False,
                             power_spectrum=False)
        AppBackend._do_fft1D(stub, Task(), 'd', window='none', detrend=False,
                             power_spectrum=True)
        m = stub._datasets['d - FFT Magnitude'].spectra.values
        p = stub._datasets['d - FFT Power'].spectra.values
        np.testing.assert_allclose(p, m ** 2)


# ---------------------------------------------------------------------------
# Unit Converter
# ---------------------------------------------------------------------------

class TestUnitConverter:
    def test_relabel_changes_units_and_names_in_place(self, stub):
        stub._datasets['d'] = make_dataset()
        n = AppBackend.relabelDatasets(stub, ['d', 'missing'],
                                       {'x_unit': 'mV', 'y_unit': 'nA', 'x_name': 'Sample bias',
                                        'y_name': 'Current'})
        assert n == 1
        ds = stub._datasets['d']
        assert ds.metadata.units['independent'] == 'mV'
        assert ds.metadata.units['dependent'] == 'nA'
        assert ds.independent_var_name == 'Sample bias'
        assert ds.metadata.additional_info['quantity'] == 'Current'
        assert 'd' in stub._datasets and len(stub._datasets) == 1   # nothing copied

    def test_relabel_leaves_blank_fields_alone(self, stub):
        stub._datasets['d'] = make_dataset(x_unit='V', y_unit='A')
        AppBackend.relabelDatasets(stub, ['d'], {'y_unit': 'S'})
        assert stub._datasets['d'].metadata.units['independent'] == 'V'
        assert stub._datasets['d'].metadata.units['dependent'] == 'S'

    def test_relabel_with_nothing_to_do_returns_zero(self, stub):
        stub._datasets['d'] = make_dataset()
        assert AppBackend.relabelDatasets(stub, ['d'], {}) == 0

    def test_preview_shows_before_and_after(self, stub):
        stub._datasets['d'] = make_dataset()
        r = AppBackend.previewFormula(stub, 'd', 'x * 1e3', 'y * 2', rows=5)
        assert r['ok'] and not r['error']
        assert len(r['rows']) == 5
        idx, x0, x1, y0, y1 = r['rows'][0]
        assert x1 == pytest.approx(x0 * 1e3) and y1 == pytest.approx(y0 * 2)
        assert r['new_x_range'] == pytest.approx([-1000, 1000])
        assert r['non_finite'] == 0

    def test_preview_reports_a_bad_formula_instead_of_raising(self, stub):
        stub._datasets['d'] = make_dataset()
        r = AppBackend.previewFormula(stub, 'd', 'open("x")', '', 5)
        assert not r['ok'] and 'open' in r['error']

    def test_formula_makes_a_new_dataset_with_the_new_units(self, stub):
        stub._datasets['d'] = make_dataset()
        out = AppBackend.apply_formula_dataset(stub, Task(), 'd', x_formula='x * 1e3',
                                               y_formula='', x_unit='mV', y_unit='',
                                               x_name='Bias (mV)')
        assert out == 'd · x=x * 1e3'
        ds = stub._datasets[out]
        np.testing.assert_allclose(ds.independent_var, stub._datasets['d'].independent_var * 1e3)
        assert ds.metadata.units['independent'] == 'mV'
        assert ds.metadata.units['dependent'] == 'A'         # untouched
        assert ds.independent_var_name == 'Bias (mV)'
        assert ds.metadata.additional_info['original'] == 'd'

    def test_formula_can_replace_in_place(self, stub):
        stub._datasets['d'] = make_dataset()
        before = stub._datasets['d'].spectra.values.copy()
        out = AppBackend.apply_formula_dataset(stub, Task(), 'd', y_formula='y / 1e-9',
                                               y_unit='nA', replace=True)
        assert out == 'd' and len(stub._datasets) == 1
        np.testing.assert_allclose(stub._datasets['d'].spectra.values, before / 1e-9)
        assert 'original' not in stub._datasets['d'].metadata.additional_info

    def test_completion_does_not_register_a_name_as_a_file(self, stub):
        AppBackend._on_unit_converter_completed(stub, 'd · y=y*2')
        stub.toolCompleted.emit.assert_called_once_with("Unit Converter", 'd · y=y*2')
        stub._route_derived_datasets.assert_called_once()


# ---------------------------------------------------------------------------
# Curve Plotting
# ---------------------------------------------------------------------------

class TestCurvePlotting:
    def test_overlays_several_datasets_in_one_window(self, stub):
        stub._datasets['a'] = make_dataset(n_spectra=3)
        stub._datasets['b'] = make_dataset(n_spectra=2)
        AppBackend.plotDatasetCurves(stub, ['a', 'b'], {'mode': 'all'})
        stub.openDatasetEmbedded.emit.assert_called_once()
        title, curves, xl, yl = stub.openDatasetEmbedded.emit.call_args.args
        assert len(curves) == 5
        assert curves[0]['label'] == 'a - S0' and curves[-1]['label'] == 'b - S1'
        assert title.startswith('Plot: a')

    def test_selection_modes(self, stub):
        stub._datasets['a'] = make_dataset(n_spectra=6)
        for opts, n in [({'mode': 'first', 'count': 2}, 2),
                        ({'mode': 'every', 'step': 4}, 2),
                        ({'mode': 'range', 'start': 2, 'stop': 4}, 3)]:
            stub.openDatasetEmbedded.emit.reset_mock()
            AppBackend.plotDatasetCurves(stub, ['a'], opts)
            assert len(stub.openDatasetEmbedded.emit.call_args.args[1]) == n

    def test_normalise_and_offset(self, stub):
        stub._datasets['a'] = make_dataset(n_spectra=2)
        AppBackend.plotDatasetCurves(stub, ['a'], {'mode': 'all', 'normalize': True, 'offset': 1.0})
        curves = stub.openDatasetEmbedded.emit.call_args.args[1]
        assert max(curves[0]['y']) == pytest.approx(1.0)
        assert max(curves[1]['y']) == pytest.approx(2.0)

    def test_empty_selection_is_reported(self, stub):
        AppBackend.plotDatasetCurves(stub, ['nope'], {})
        stub.errorOccurred.emit.assert_called_once()
        stub.openDatasetEmbedded.emit.assert_not_called()


# ---------------------------------------------------------------------------
# Gradient Filter sources
# ---------------------------------------------------------------------------

class TestGradientSources:
    def test_image_ref_resolves_to_a_calibrated_field(self, stub):
        from src.models.image_data import ImageData, ImageMetadata
        arr = np.outer(np.arange(8.0), np.ones(6))
        meta = ImageMetadata(source='test', pixel_size_nm=(2.0, 3.0))
        stub._images['img1'] = ImageData(arr, metadata=meta, name='Ramp')
        field, info, title = stub._resolve_field_source('image:img1')
        np.testing.assert_array_equal(field, arr)
        assert info['pixel_size'] == {'dx': 3.0, 'dy': 2.0, 'unit': 'nm'}
        assert title == 'Ramp'

    def test_unknown_ref_is_an_error(self, stub):
        with pytest.raises(ValueError):
            stub._resolve_field_source('map:nope')
        with pytest.raises(ValueError):
            stub._resolve_field_source('/no/such/file.png')

    def test_gradient_of_a_ramp_is_its_slope_per_unit(self, stub):
        from src.models.image_data import ImageData, ImageMetadata
        arr = np.outer(np.ones(8), np.arange(6.0))          # 1 per pixel along x
        meta = ImageMetadata(source='test', pixel_size_nm=(2.0, 2.0))
        stub._images['img1'] = ImageData(arr, metadata=meta, name='Ramp')
        out = stub.apply_gradient_filter(Task(), 'image:img1', 'sobel')
        assert out.endswith('.tiff')
        import tifffile
        g = tifffile.imread(out)
        # Interior: slope 1 per pixel = 0.5 per nm; edges are convolution artefacts.
        np.testing.assert_allclose(g[2:-2, 2:-2], 0.5, rtol=1e-6)

    def test_field_source_list_names_maps_and_images(self, stub):
        from src.models.image_data import ImageData
        stub.maps.append({'id': 'map_1', 'title': 'Height', 'path': '/x.tiff'})
        stub._images['i'] = ImageData(np.zeros((2, 2)), name='Pic')
        refs = AppBackend.getFieldSourceList(stub)
        assert refs == [{'ref': 'map:map_1', 'label': 'Height'},
                        {'ref': 'image:i', 'label': 'Pic'}]


# ---------------------------------------------------------------------------
# Multi-Peak Fitting over a dataset
# ---------------------------------------------------------------------------

class TestMultiPeakDataset:
    def test_fits_every_spectrum_into_a_table_and_fitted_curves(self, stub):
        x = np.linspace(-1, 1, 200)
        peaks = [(-0.4, 1.0), (0.3, 0.6)]
        cols = {}
        for i in range(3):
            y = 0.02 + sum(a * np.exp(-(x - c - 0.01 * i) ** 2 / (2 * 0.05 ** 2)) for c, a in peaks)
            cols[f'S{i}'] = y
        df = pd.DataFrame({'Bias': x, **cols})
        stub._datasets['d'] = SpectralData(df, SpectralMetadata(
            source_type='test', dimensions=(3, 1), scan_mode='line',
            units={'independent': 'V', 'dependent': 'A'}, additional_info={}))

        path = stub.fit_multipeak_dataset(Task(), 'd', peak_shape='gaussian',
                                          n_peaks_auto=2, baseline_degree=0)
        assert path.endswith('_PeakFit.csv')

        table = stub._datasets['d - Peak Fit']
        assert table.metadata.data_type == 'flat'
        assert 'original' not in table.metadata.additional_info
        frame = table.data
        assert list(frame['n_peaks']) == [2, 2, 2]
        assert (frame['rsq'] > 0.99).all()
        np.testing.assert_allclose(frame['peak1_center'], [-0.4, -0.39, -0.38], atol=0.01)
        np.testing.assert_allclose(frame['peak2_center'], [0.3, 0.31, 0.32], atol=0.01)

        fitted = stub._datasets['d - Fitted']
        assert fitted.metadata.additional_info['original'] == 'd'
        assert fitted.num_spectra == 3
        np.testing.assert_allclose(fitted.spectra.values, df[['S0', 'S1', 'S2']].values, atol=0.02)

        long = pd.read_csv(path)
        assert len(long) == 6 and set(long['shape']) == {'gaussian'}

    def test_cancel_between_spectra_returns_nothing(self, stub):
        stub._datasets['d'] = make_dataset()
        t = Task(); t.cancelled = True
        assert stub.fit_multipeak_dataset(t, 'd') == ""
        assert 'd - Peak Fit' not in stub._datasets
