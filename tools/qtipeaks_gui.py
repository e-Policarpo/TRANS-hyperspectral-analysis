#!/usr/bin/env python3
"""Qt front-end for qtipeaks.

    python tools/qtipeaks_gui.py [file.csv]

Pick the input CSV and the output folder, set the parameters, watch the live
preview of the selected curve, then Run to write the peak matrix and the peak
list for every curve.

All the work lives in qtipeaks.py -- this module is only widgets.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter,
    QVBoxLayout, QWidget,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qtipeaks as qp  # noqa: E402


PREVIEW_DEBOUNCE_MS = 150


# --------------------------------------------------------------------------
# Background worker
# --------------------------------------------------------------------------

class RunWorker(QThread):
    """Runs the whole batch off the UI thread -- 200 curves takes seconds."""

    done = Signal(str)
    failed = Signal(str)

    def __init__(self, table, names, ys, params, options, parent=None):
        super().__init__(parent)
        self.table, self.names, self.ys = table, names, ys
        self.params, self.options = params, options

    def run(self) -> None:
        try:
            o = self.options
            results = [qp.analyze(self.table.x, y, self.params) for y in self.ys]
            peaks = [r.peaks for r in results]

            os.makedirs(o["outdir"], exist_ok=True)
            matrix_path = os.path.join(o["outdir"], f"{o['prefix']}_peak_matrix.csv")
            list_path = os.path.join(o["outdir"], f"{o['prefix']}_peak_list.csv")

            qp.write_matrix(matrix_path, self.table.x, self.names, peaks,
                            o["delimiter"], o["decimal"], o["precision"],
                            o["x_scale"], o["transpose"])
            qp.write_peak_list(list_path, self.names, peaks,
                               o["delimiter"], o["decimal"], o["precision"], o["x_scale"])

            plot_note = ""
            if o["plots"]:
                plot_dir = os.path.join(o["outdir"], f"{o['prefix']}_plots")
                qp.write_plots(plot_dir, self.table.x, self.names, self.ys, results, self.params)
                plot_note = f"\n{len(self.names)} plots in {plot_dir}"

            total = sum(len(p) for p in peaks)
            self.done.emit(
                f"{total} peaks over {len(self.names)} curves.\n\n"
                f"{matrix_path}\n{list_path}{plot_note}"
            )
        except Exception as exc:  # surfaced in a dialog rather than a traceback on stderr
            self.failed.emit(f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------
# Main window
# --------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, initial: str | None = None):
        super().__init__()
        self.setWindowTitle("qtipeaks -- batch peak finding")
        self.resize(1180, 760)

        self.table: qp.Table | None = None
        self.worker: RunWorker | None = None

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._preview_timer.timeout.connect(self._refresh_preview)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_controls())
        splitter.addWidget(self._build_preview())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([430, 750])
        self.setCentralWidget(splitter)

        self.statusBar().showMessage("Choose an input CSV to begin.")
        self._set_enabled(False)

        if initial:
            self._load(initial)

    # -- construction ------------------------------------------------------

    def _build_controls(self) -> QWidget:
        panel = QWidget()
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(8, 8, 8, 8)

        # Files ------------------------------------------------------------
        files = QGroupBox("Files")
        form = QFormLayout(files)

        self.input_edit = QLineEdit()
        self.input_edit.setReadOnly(True)
        self.input_edit.setPlaceholderText("no file selected")
        self.input_edit.setToolTip("CSV with X in the first column, one curve per further column")
        form.addRow("Input CSV", self._with_button(self.input_edit, "Browse...", self._choose_input))

        self.outdir_edit = QLineEdit()
        self.outdir_edit.setPlaceholderText("same folder as the input")
        form.addRow("Output folder", self._with_button(self.outdir_edit, "Browse...", self._choose_outdir))

        self.prefix_edit = QLineEdit()
        form.addRow("File name prefix", self.prefix_edit)
        self.prefix_edit.textChanged.connect(self._update_output_hint)
        self.outdir_edit.textChanged.connect(self._update_output_hint)
        self.output_hint = QLabel()
        self.output_hint.setWordWrap(True)
        self.output_hint.setStyleSheet("color: gray; font-size: 11px;")
        form.addRow(self.output_hint)
        outer.addWidget(files)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        box = QVBoxLayout(inner)
        box.setContentsMargins(0, 0, 6, 0)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        # File format ------------------------------------------------------
        group = QGroupBox("File format")
        form = QFormLayout(group)
        auto = [("auto-detect", None)]
        delims = [(qp.DELIMITER_NAMES[d], d) for d in (",", ";", "\t", qp.WHITESPACE)]
        decimals = [("period  1.5", "."), ("comma  1,5", ",")]

        self.in_delim = self._data_combo(auto + delims)
        self.in_decimal = self._data_combo(auto + decimals)
        self.in_decimal.setToolTip("Files exported in a pt-BR locale use '1,339224585931E-07'.")
        form.addRow("Input delimiter", self.in_delim)
        form.addRow("Input decimal", self.in_decimal)

        same = [("same as input", None)]
        self.out_delim = self._data_combo(same + delims[:3])
        self.out_decimal = self._data_combo(same + decimals)
        form.addRow("Output delimiter", self.out_delim)
        form.addRow("Output decimal", self.out_decimal)

        self.in_delim.currentIndexChanged.connect(self._reload_input)
        self.in_decimal.currentIndexChanged.connect(self._reload_input)
        self.out_delim.currentIndexChanged.connect(self._update_output_hint)
        self.out_decimal.currentIndexChanged.connect(self._update_output_hint)
        box.addWidget(group)

        # Search range -----------------------------------------------------
        group = QGroupBox("Search range (Dados)")
        form = QFormLayout(group)
        self.limit_range = QCheckBox("Limit the X range")
        self.xmin_spin = self._double(-0.3, decimals=6)
        self.xmax_spin = self._double(0.3, decimals=6)
        self.limit_range.toggled.connect(self.xmin_spin.setEnabled)
        self.limit_range.toggled.connect(self.xmax_spin.setEnabled)
        self.xmin_spin.setEnabled(False)
        self.xmax_spin.setEnabled(False)
        form.addRow(self.limit_range)
        form.addRow("From Xmin", self.xmin_spin)
        form.addRow("To Xmax", self.xmax_spin)
        box.addWidget(group)

        # Background -------------------------------------------------------
        group = QGroupBox("Polynomial background (Fundo)")
        form = QFormLayout(group)
        self.baseline_combo = self._combo(list(qp.BASELINE_KINDS), "poly-iter")
        self.baseline_combo.setToolTip(
            "poly-iter strips the peaks out of the fit, so small features are measured\n"
            "against a flat zero instead of against the band edges.")
        self.baseline_degree = self._int(3, 0, 15)
        self.baseline_iter = self._int(25, 1, 500)
        form.addRow("Background", self.baseline_combo)
        form.addRow("Degree", self.baseline_degree)
        form.addRow("Iterations", self.baseline_iter)
        self.baseline_combo.currentTextChanged.connect(self._sync_baseline_enabled)
        box.addWidget(group)

        # Filter -----------------------------------------------------------
        group = QGroupBox("Filter (Filtro)")
        form = QFormLayout(group)
        self.direction_combo = self._combo(["positive", "negative", "both"], "positive")
        self.height_spin = self._double(5.0, decimals=3, lo=0.0, hi=100.0, step=0.5, suffix=" %")
        self.height_mode = self._combo(["range", "prominence", "max"], "range")
        self.height_mode.setToolTip(
            "range: height above the window minimum, as % of the window span\n"
            "prominence: drop to the higher neighbouring valley, as % of the span\n"
            "max: absolute value, as % of the window maximum")
        self.smooth_spin = self._int(0, 0, 500)
        self.smooth_type = self._combo(["average", "savgol"], "average")
        form.addRow("Direction", self.direction_combo)
        form.addRow("Height", self.height_spin)
        form.addRow("Measured as", self.height_mode)
        form.addRow("Smooth (half-width)", self.smooth_spin)
        form.addRow("Smoother", self.smooth_type)
        box.addWidget(group)

        # Derivative smoothing ---------------------------------------------
        group = QGroupBox("Derivative smoothing (Suavizar Derivada)")
        form = QFormLayout(group)
        self.deriv_type = self._combo(["none", "average", "savgol"], "none")
        self.deriv_points = self._int(2, 0, 500)
        form.addRow("Type", self.deriv_type)
        form.addRow("Points (half-width)", self.deriv_points)
        box.addWidget(group)

        # Selection ---------------------------------------------------------
        group = QGroupBox("Peak selection")
        form = QFormLayout(group)
        self.max_peaks = self._int(0, 0, 100000)
        self.max_peaks.setSpecialValueText("all")
        self.min_distance = self._double(0.0, decimals=6, lo=0.0, hi=1e9)
        self.interpolate = QCheckBox("Interpolate peak centres")
        self.interpolate.setToolTip("Sub-sample centres in the peak list; the 1/0 table still snaps to the grid.")
        form.addRow("Keep at most", self.max_peaks)
        form.addRow("Min. separation", self.min_distance)
        form.addRow(self.interpolate)
        box.addWidget(group)

        # Output ------------------------------------------------------------
        group = QGroupBox("Output")
        form = QFormLayout(group)
        self.x_scale = self._double(1.0, decimals=6, lo=-1e9, hi=1e9)
        self.x_scale.setToolTip("Multiplies X in both output files. Use 1000 to report volts as meV.")
        self.precision = self._int(10, 1, 17)
        self.transpose = QCheckBox("Curves as rows, X as columns")
        self.save_plots = QCheckBox("Also save one PNG per curve")
        form.addRow("Scale X by", self.x_scale)
        form.addRow("Significant digits", self.precision)
        form.addRow(self.transpose)
        form.addRow(self.save_plots)
        box.addWidget(group)
        box.addStretch(1)

        # Run ----------------------------------------------------------------
        self.run_button = QPushButton("Run and write CSVs")
        self.run_button.setMinimumHeight(34)
        self.run_button.clicked.connect(self._run)
        outer.addWidget(self.run_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        outer.addWidget(self.progress)

        for widget in (self.limit_range, self.interpolate, self.transpose):
            widget.toggled.connect(self._queue_preview)
        for widget in (self.xmin_spin, self.xmax_spin, self.height_spin,
                       self.min_distance, self.x_scale):
            widget.valueChanged.connect(self._queue_preview)
        for widget in (self.baseline_degree, self.baseline_iter, self.smooth_spin,
                       self.deriv_points, self.max_peaks, self.precision):
            widget.valueChanged.connect(self._queue_preview)
        for widget in (self.baseline_combo, self.direction_combo, self.height_mode,
                       self.smooth_type, self.deriv_type):
            widget.currentTextChanged.connect(self._queue_preview)

        self._sync_baseline_enabled()
        return panel

    def _build_preview(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 8, 8, 8)

        row = QHBoxLayout()
        row.addWidget(QLabel("Preview curve"))
        self.curve_combo = QComboBox()
        self.curve_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.curve_combo.currentIndexChanged.connect(self._queue_preview)
        row.addWidget(self.curve_combo, 1)
        self.count_label = QLabel()
        self.count_label.setStyleSheet("font-weight: bold;")
        row.addWidget(self.count_label)
        layout.addLayout(row)

        self.figure = Figure(figsize=(7, 5))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes = self.figure.add_subplot(111)
        layout.addWidget(NavigationToolbar2QT(self.canvas, panel))
        layout.addWidget(self.canvas, 1)
        return panel

    # -- small widget factories -------------------------------------------

    @staticmethod
    def _with_button(edit: QLineEdit, text: str, slot) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(edit, 1)
        button = QPushButton(text)
        button.clicked.connect(slot)
        row.addWidget(button)
        return holder

    @staticmethod
    def _double(value, decimals=3, lo=-1e12, hi=1e12, step=0.01, suffix="") -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(decimals)
        spin.setRange(lo, hi)
        spin.setSingleStep(step)
        spin.setValue(value)
        if suffix:
            spin.setSuffix(suffix)
        spin.setKeyboardTracking(False)
        return spin

    @staticmethod
    def _int(value, lo, hi) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(lo, hi)
        spin.setValue(value)
        spin.setKeyboardTracking(False)
        return spin

    @staticmethod
    def _combo(items, current) -> QComboBox:
        combo = QComboBox()
        combo.addItems(items)
        combo.setCurrentText(current)
        return combo

    @staticmethod
    def _data_combo(pairs) -> QComboBox:
        """Combo whose entries carry a value, e.g. ('tab', '\\t')."""
        combo = QComboBox()
        for label, value in pairs:
            combo.addItem(label, value)
        return combo

    # -- state -------------------------------------------------------------

    def _set_enabled(self, on: bool) -> None:
        self.run_button.setEnabled(on)
        self.curve_combo.setEnabled(on)

    def _sync_baseline_enabled(self) -> None:
        kind = self.baseline_combo.currentText()
        self.baseline_degree.setEnabled(kind != "none")
        self.baseline_iter.setEnabled(kind == "poly-iter")

    def _choose_input(self) -> None:
        start = os.path.dirname(self.input_edit.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Select the input CSV", start,
            "Data files (*.csv *.txt *.dat *.tsv);;All files (*)")
        if path:
            self._load(path)

    def _choose_outdir(self) -> None:
        start = self.outdir_edit.text() or os.path.dirname(self.input_edit.text()) or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, "Select the output folder", start)
        if path:
            self.outdir_edit.setText(path)

    def _reload_input(self) -> None:
        """Re-read the current file after the format override changed."""
        path = self.input_edit.text()
        if path and os.path.exists(path):
            self._load(path, keep_outputs=True)

    def _load(self, path: str, keep_outputs: bool = False) -> None:
        try:
            table = qp.read_table(path, self.in_delim.currentData(), self.in_decimal.currentData())
        except SystemExit as exc:  # read_table reports bad files this way
            QMessageBox.critical(self, "Could not read the file", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Could not read the file", f"{type(exc).__name__}: {exc}")
            return

        if not table.names:
            QMessageBox.critical(self, "Could not read the file",
                                 "No curve columns found next to the X column.")
            return

        self.table = table
        self.input_edit.setText(path)
        if not keep_outputs:
            self.outdir_edit.setText(os.path.dirname(os.path.abspath(path)))
            self.prefix_edit.setText(os.path.splitext(os.path.basename(path))[0])

        lo, hi = float(table.x.min()), float(table.x.max())
        step = max((hi - lo) / 100.0, 1e-9)
        for spin, value in ((self.xmin_spin, lo), (self.xmax_spin, hi)):
            spin.blockSignals(True)
            spin.setRange(lo, hi)
            spin.setSingleStep(step)
            spin.setValue(value)
            spin.blockSignals(False)
        self.min_distance.setSingleStep(step)

        self.curve_combo.blockSignals(True)
        self.curve_combo.clear()
        self.curve_combo.addItems(table.names)
        self.curve_combo.blockSignals(False)

        self._set_enabled(True)
        self._update_output_hint()
        detected = "" if self.in_delim.currentData() and self.in_decimal.currentData() else " (detected)"
        self.statusBar().showMessage(
            f"{os.path.basename(path)}: {len(table.x)} x-values, {len(table.names)} curves -- "
            f"{qp.DELIMITER_NAMES.get(table.delimiter, table.delimiter)} delimited, "
            f"decimal {table.decimal!r}{detected}")
        self._refresh_preview()

    def _output_format(self) -> tuple[str, str]:
        """The (delimiter, decimal) actually used for writing."""
        table = self.table
        delimiter = self.out_delim.currentData() or (table.delimiter if table else ",")
        decimal = self.out_decimal.currentData() or (table.decimal if table else ".")
        return qp.effective_output_format(delimiter, decimal)

    def _update_output_hint(self) -> None:
        outdir = self.outdir_edit.text() or "<input folder>"
        prefix = self.prefix_edit.text() or "<prefix>"
        delimiter, decimal = self._output_format()
        self.output_hint.setText(
            f"Writes {prefix}_peak_matrix.csv and {prefix}_peak_list.csv into {outdir}, "
            f"{qp.DELIMITER_NAMES.get(delimiter, delimiter)} delimited with "
            f"{'comma' if decimal == ',' else 'period'} decimals")

    # -- parameters --------------------------------------------------------

    def _params(self) -> qp.Params:
        limited = self.limit_range.isChecked()
        return qp.Params(
            xmin=self.xmin_spin.value() if limited else None,
            xmax=self.xmax_spin.value() if limited else None,
            direction=self.direction_combo.currentText(),
            height=self.height_spin.value(),
            height_mode=self.height_mode.currentText(),
            smooth_type=self.smooth_type.currentText(),
            smooth_points=self.smooth_spin.value(),
            deriv_smooth_type=self.deriv_type.currentText(),
            deriv_smooth_points=self.deriv_points.value(),
            baseline=self.baseline_combo.currentText(),
            baseline_degree=self.baseline_degree.value(),
            baseline_iterations=self.baseline_iter.value(),
            max_peaks=self.max_peaks.value() or None,
            min_distance=self.min_distance.value(),
            interpolate_center=self.interpolate.isChecked(),
        )

    # -- preview -----------------------------------------------------------

    def _queue_preview(self) -> None:
        if self.table is not None:
            self._preview_timer.start()

    def _refresh_preview(self) -> None:
        if self.table is None:
            return
        index = self.curve_combo.currentIndex()
        if index < 0:
            return

        name = self.table.names[index]
        y = self.table.ys[index]
        params = self._params()
        self.axes.clear()
        try:
            result = qp.analyze(self.table.x, y, params)
        except Exception as exc:
            self.count_label.setText("error")
            self.axes.text(0.5, 0.5, f"{type(exc).__name__}: {exc}",
                           ha="center", va="center", transform=self.axes.transAxes)
            self.canvas.draw_idle()
            return

        qp.draw_curve(self.axes, self.table.x, y, name, result, params)
        self.figure.tight_layout()
        self.canvas.draw_idle()
        self.count_label.setText(f"{len(result.peaks)} peaks")

    # -- run ---------------------------------------------------------------

    def _run(self) -> None:
        if self.table is None or self.worker is not None:
            return

        outdir = self.outdir_edit.text() or os.path.dirname(os.path.abspath(self.input_edit.text()))
        prefix = self.prefix_edit.text() or os.path.splitext(os.path.basename(self.input_edit.text()))[0]

        delimiter, decimal = self._output_format()

        options = {
            "outdir": outdir,
            "prefix": prefix,
            "delimiter": delimiter,
            "decimal": decimal,
            "precision": self.precision.value(),
            "x_scale": self.x_scale.value(),
            "transpose": self.transpose.isChecked(),
            "plots": self.save_plots.isChecked(),
        }

        self.run_button.setEnabled(False)
        self.progress.show()
        self.statusBar().showMessage(f"Processing {len(self.table.names)} curves...")

        self.worker = RunWorker(self.table, self.table.names, self.table.ys,
                                self._params(), options, self)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_done(self, message: str) -> None:
        self.statusBar().showMessage(message.splitlines()[0])
        QMessageBox.information(self, "Done", message)

    def _on_failed(self, message: str) -> None:
        self.statusBar().showMessage("Failed.")
        QMessageBox.critical(self, "Run failed", message)

    def _on_finished(self) -> None:
        self.progress.hide()
        self.run_button.setEnabled(True)
        self.worker = None

    def closeEvent(self, event) -> None:
        self._preview_timer.stop()
        if self.worker is not None:
            self.worker.wait(5000)
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setApplicationName("qtipeaks")
    window = MainWindow(argv[1] if len(argv) > 1 else None)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
