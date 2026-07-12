"""Main ReCraft desktop window."""

from dataclasses import replace
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QProgressBar, QSpinBox, QVBoxLayout, QWidget,
)

from recraft.core.image_loader import ImageLoadError, load_image
from recraft.core.image_transform import (
    ASPECT_RATIO_PRESETS, MAX_OUTPUT_DIMENSION, FitMode, ImageTransformSettings,
    size_for_aspect_ratio,
)
from recraft.core.prepared_image import render_prepared_preview
from recraft.core.style_registry import create_default_registry
from recraft.styles.base import ArtStyle, ParameterValue
from recraft.ui.image_view import ImageView
from recraft.ui.render_worker import RenderWorker


class MainWindow(QMainWindow):
    """Coordinate non-destructive preparation, style preview, and export."""

    def __init__(self) -> None:
        super().__init__()
        self.registry = create_default_registry()
        self.source_image: Image.Image | None = None
        self.prepared_preview: Image.Image | None = None
        self.output_image: Image.Image | None = None
        self.transform_settings = ImageTransformSettings()
        self.parameter_widgets: dict[str, QSpinBox | QDoubleSpinBox] = {}
        self._render_thread: QThread | None = None
        self._render_worker: RenderWorker | None = None
        self._updating_setup = False
        self.setWindowTitle("ReCraft — Create the impossible.")
        self.resize(1250, 800)
        self._build_ui()
        self._rebuild_parameters()
        self._sync_setup_controls()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        heading = QHBoxLayout()
        title = QLabel("ReCraft"); title.setStyleSheet("font-size: 28px; font-weight: 700;")
        subtitle = QLabel("Create the impossible."); subtitle.setStyleSheet("font-size: 15px; color: #68717d;")
        heading.addWidget(title); heading.addWidget(subtitle); heading.addStretch()
        self.open_button = QPushButton("Open Image"); self.open_button.clicked.connect(self._open_image)
        self.save_button = QPushButton("Save Full-Resolution PNG"); self.save_button.clicked.connect(self._save_output); self.save_button.setEnabled(False)
        heading.addWidget(self.open_button); heading.addWidget(self.save_button)
        root.addLayout(heading)

        self.setup_box = QGroupBox("1. Prepare Image")
        setup_layout = QGridLayout(self.setup_box)
        self.aspect_combo = QComboBox()
        for name, ratio in ASPECT_RATIO_PRESETS.items(): self.aspect_combo.addItem(name, ratio)
        self.aspect_combo.currentIndexChanged.connect(self._aspect_changed)
        self.mode_combo = QComboBox(); self.mode_combo.addItem("Fill frame", FitMode.FILL); self.mode_combo.addItem("Fit full image", FitMode.FIT)
        self.mode_combo.currentIndexChanged.connect(self._setup_changed)
        self.width_spin = QSpinBox(); self.height_spin = QSpinBox()
        for spin in (self.width_spin, self.height_spin): spin.setRange(1, MAX_OUTPUT_DIMENSION); spin.setSuffix(" px"); spin.valueChanged.connect(self._dimensions_changed)
        self.lock_check = QCheckBox("Lock aspect ratio"); self.lock_check.setChecked(True); self.lock_check.toggled.connect(self._setup_changed)
        self.zoom_spin = QDoubleSpinBox(); self.zoom_spin.setRange(1.0, 10.0); self.zoom_spin.setSingleStep(0.1); self.zoom_spin.setSuffix("×"); self.zoom_spin.valueChanged.connect(self._setup_changed)
        self.pan_x = QDoubleSpinBox(); self.pan_y = QDoubleSpinBox()
        for spin in (self.pan_x, self.pan_y): spin.setRange(-1.0, 1.0); spin.setSingleStep(0.05); spin.valueChanged.connect(self._setup_changed)
        setup_layout.addWidget(QLabel("Aspect ratio"), 0, 0); setup_layout.addWidget(self.aspect_combo, 0, 1)
        setup_layout.addWidget(QLabel("Scale"), 0, 2); setup_layout.addWidget(self.mode_combo, 0, 3)
        setup_layout.addWidget(QLabel("Output width"), 1, 0); setup_layout.addWidget(self.width_spin, 1, 1)
        setup_layout.addWidget(QLabel("Output height"), 1, 2); setup_layout.addWidget(self.height_spin, 1, 3); setup_layout.addWidget(self.lock_check, 1, 4)
        setup_layout.addWidget(QLabel("Zoom"), 2, 0); setup_layout.addWidget(self.zoom_spin, 2, 1)
        setup_layout.addWidget(QLabel("Pan X"), 2, 2); setup_layout.addWidget(self.pan_x, 2, 3); setup_layout.addWidget(QLabel("Pan Y"), 2, 4); setup_layout.addWidget(self.pan_y, 2, 5)
        actions = QHBoxLayout()
        for label, handler in (("Rotate left", lambda: self._rotate(-1)), ("Rotate right", lambda: self._rotate(1)), ("Flip horizontal", self._flip_horizontal), ("Flip vertical", self._flip_vertical), ("Reset", self._reset_setup)):
            button = QPushButton(label); button.clicked.connect(handler); actions.addWidget(button)
        setup_layout.addLayout(actions, 3, 0, 1, 6)
        root.addWidget(self.setup_box)

        self.style_box = QGroupBox("2. Apply Art Style")
        style_layout = QHBoxLayout(self.style_box)
        self.style_combo = QComboBox()
        for style in self.registry: self.style_combo.addItem(style.display_name, style.identifier)
        self.style_combo.currentIndexChanged.connect(self._rebuild_parameters)
        self.description = QLabel(); self.parameter_container = QWidget(); self.parameter_form = QFormLayout(self.parameter_container)
        self.generate_button = QPushButton("Generate Preview"); self.generate_button.clicked.connect(self._generate)
        style_layout.addWidget(QLabel("Style")); style_layout.addWidget(self.style_combo); style_layout.addWidget(self.description, 1); style_layout.addWidget(self.parameter_container); style_layout.addWidget(self.generate_button)
        root.addWidget(self.style_box)

        panels = QHBoxLayout()
        left = QVBoxLayout(); left.addWidget(QLabel("Prepared image — wheel to zoom, drag to pan")); self.prepared_view = ImageView("Open an image to begin", interactive=True); left.addWidget(self.prepared_view)
        self.prepared_view.zoom_requested.connect(self._gesture_zoom); self.prepared_view.pan_requested.connect(self._gesture_pan)
        right = QVBoxLayout(); right.addWidget(QLabel("Transformed preview")); self.output_view = ImageView("Generate a style preview"); right.addWidget(self.output_view)
        panels.addLayout(left); panels.addLayout(right); root.addLayout(panels, 1)
        self.progress = QProgressBar(); self.progress.setRange(0, 0); self.progress.setMaximumWidth(180); self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.setCentralWidget(central); self.statusBar().showMessage("Ready — open an image to begin")

    def _current_style(self) -> ArtStyle:
        return self.registry.get(str(self.style_combo.currentData()))

    def _style_parameters(self) -> dict[str, ParameterValue]:
        return {key: widget.value() for key, widget in self.parameter_widgets.items()}

    def _rebuild_parameters(self) -> None:
        while self.parameter_form.rowCount(): self.parameter_form.removeRow(0)
        self.parameter_widgets.clear(); style = self._current_style(); self.description.setText(style.description)
        for parameter in style.parameters:
            if any(isinstance(value, float) for value in (parameter.default, parameter.minimum, parameter.maximum, parameter.step)):
                widget: QSpinBox | QDoubleSpinBox = QDoubleSpinBox(); widget.setDecimals(2)
            else: widget = QSpinBox()
            widget.setRange(parameter.minimum, parameter.maximum); widget.setSingleStep(parameter.step); widget.setValue(parameter.default)
            self.parameter_widgets[parameter.key] = widget; self.parameter_form.addRow(parameter.label, widget)

    def _settings_from_controls(self) -> ImageTransformSettings:
        return replace(self.transform_settings, pan_x=self.pan_x.value(), pan_y=self.pan_y.value(), zoom=self.zoom_spin.value(), aspect_ratio=self.aspect_combo.currentData(), output_width=self.width_spin.value(), output_height=self.height_spin.value(), fit_mode=self.mode_combo.currentData(), lock_aspect_ratio=self.lock_check.isChecked()).validated()

    def _sync_setup_controls(self) -> None:
        self._updating_setup = True
        state = self.transform_settings
        self.width_spin.setValue(state.output_width); self.height_spin.setValue(state.output_height); self.zoom_spin.setValue(state.zoom); self.pan_x.setValue(state.pan_x); self.pan_y.setValue(state.pan_y); self.lock_check.setChecked(state.lock_aspect_ratio)
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(state.fit_mode)); self.aspect_combo.setCurrentIndex(self.aspect_combo.findData(state.aspect_ratio))
        self._updating_setup = False

    def _open_image(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Open image", "", "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)")
        if not filename: return
        try:
            self.source_image = load_image(filename)
            self.transform_settings = self.transform_settings.reset(self.source_image.size)
            self._sync_setup_controls(); self._refresh_prepared(); self._invalidate_output()
            self.statusBar().showMessage(f"Loaded {Path(filename).name} at {self.source_image.width} × {self.source_image.height}")
        except ImageLoadError as exc: QMessageBox.critical(self, "Could not open image", str(exc))

    def _setup_changed(self) -> None:
        if self._updating_setup: return
        try: self.transform_settings = self._settings_from_controls(); self._refresh_prepared(); self._invalidate_output()
        except ValueError as exc: QMessageBox.warning(self, "Invalid image setup", str(exc))

    def _dimensions_changed(self) -> None:
        if self._updating_setup: return
        self._updating_setup = True
        ratio = self.aspect_combo.currentData()
        if ratio is None and self.source_image is not None:
            ratio = self.source_image.size
        if self.lock_check.isChecked() and ratio:
            sender = self.sender()
            rw, rh = ratio
            if sender is self.width_spin: self.height_spin.setValue(max(1, min(MAX_OUTPUT_DIMENSION, round(self.width_spin.value() * rh / rw))))
            else: self.width_spin.setValue(max(1, min(MAX_OUTPUT_DIMENSION, round(self.height_spin.value() * rw / rh))))
        self._updating_setup = False; self._setup_changed()

    def _aspect_changed(self) -> None:
        if self._updating_setup: return
        ratio = self.aspect_combo.currentData()
        if ratio is None and self.source_image is not None: ratio = self.source_image.size
        width, height = size_for_aspect_ratio((self.width_spin.value(), self.height_spin.value()), ratio)
        self._updating_setup = True; self.width_spin.setValue(width); self.height_spin.setValue(min(height, MAX_OUTPUT_DIMENSION)); self._updating_setup = False; self._setup_changed()

    def _rotate(self, turns: int) -> None:
        self.transform_settings = replace(self._settings_from_controls(), rotation_quarters=self.transform_settings.rotation_quarters + turns); self._refresh_prepared(); self._invalidate_output()

    def _flip_horizontal(self) -> None:
        self.transform_settings = replace(self._settings_from_controls(), flip_horizontal=not self.transform_settings.flip_horizontal); self._refresh_prepared(); self._invalidate_output()

    def _flip_vertical(self) -> None:
        self.transform_settings = replace(self._settings_from_controls(), flip_vertical=not self.transform_settings.flip_vertical); self._refresh_prepared(); self._invalidate_output()

    def _reset_setup(self) -> None:
        self.transform_settings = self.transform_settings.reset(self.source_image.size if self.source_image else None); self._sync_setup_controls(); self._refresh_prepared(); self._invalidate_output()

    def _gesture_zoom(self, delta: float) -> None:
        self.zoom_spin.setValue(max(1.0, min(10.0, self.zoom_spin.value() + delta)))

    def _gesture_pan(self, dx: float, dy: float) -> None:
        self.pan_x.setValue(max(-1.0, min(1.0, self.pan_x.value() + dx * 2))); self.pan_y.setValue(max(-1.0, min(1.0, self.pan_y.value() + dy * 2)))

    def _refresh_prepared(self) -> None:
        if self.source_image is None: return
        self.prepared_preview = render_prepared_preview(self.source_image, self.transform_settings); self.prepared_view.set_image(self.prepared_preview)

    def _invalidate_output(self) -> None:
        self.output_image = None; self.output_view.set_image(None); self.save_button.setEnabled(self.source_image is not None)

    def _generate(self) -> None:
        if self.source_image is None: QMessageBox.information(self, "No image", "Open an image before generating artwork."); return
        self._start_render(export_path=None)

    def _save_output(self) -> None:
        if self.source_image is None: return
        filename, _ = QFileDialog.getSaveFileName(self, "Save output", "recraft-output.png", "PNG image (*.png)")
        if not filename: return
        if not filename.lower().endswith(".png"): filename += ".png"
        self._start_render(export_path=filename)

    def _start_render(self, export_path: str | None) -> None:
        """Start one preview or export job on a background Qt thread."""
        if self.source_image is None or self._render_thread is not None:
            return
        try:
            settings = self._settings_from_controls()
            style = self._current_style()
            parameters = self._style_parameters()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid settings", str(exc))
            return

        thread = QThread(self)
        worker = RenderWorker(
            self.source_image, settings, style, parameters, export_path
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.preview_ready.connect(self._preview_finished)
        worker.export_ready.connect(self._export_finished)
        worker.failed.connect(self._render_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._render_cleanup)
        thread.finished.connect(thread.deleteLater)
        self._render_thread = thread
        self._render_worker = worker
        self._set_rendering(True)
        operation = "Exporting full-resolution PNG" if export_path else "Generating style preview"
        self.statusBar().showMessage(f"{operation}…")
        thread.start()

    def _set_rendering(self, active: bool) -> None:
        """Prevent conflicting changes and show indeterminate progress."""
        self.open_button.setEnabled(not active)
        self.setup_box.setEnabled(not active)
        self.style_box.setEnabled(not active)
        self.save_button.setEnabled(not active and self.source_image is not None)
        self.progress.setVisible(active)

    def _preview_finished(self, result: object) -> None:
        if not isinstance(result, Image.Image):
            self._render_failed("The preview renderer returned an invalid image")
            return
        self.output_image = result
        self.output_view.set_image(result)
        self.statusBar().showMessage(
            f"Generated {self._current_style().display_name} preview at "
            f"{result.width} × {result.height}"
        )

    def _export_finished(self, filename: str, width: int, height: int) -> None:
        self.statusBar().showMessage(
            f"Saved {Path(filename).name} at {width} × {height}"
        )

    def _render_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Rendering failed", message)
        self.statusBar().showMessage("Rendering failed")

    def _render_cleanup(self) -> None:
        self._render_thread = None
        self._render_worker = None
        self._set_rendering(False)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Keep the window alive until its current worker safely finishes."""
        if self._render_thread is not None:
            QMessageBox.information(
                self,
                "Rendering in progress",
                "Please wait for the current render or export to finish before closing ReCraft.",
            )
            event.ignore()
            return
        super().closeEvent(event)
