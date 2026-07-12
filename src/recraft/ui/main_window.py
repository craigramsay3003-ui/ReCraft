"""Main ReCraft desktop window."""

from dataclasses import replace
import copy
from pathlib import Path

from PIL import Image
import numpy as np
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
from recraft.ui.mesh_worker import MeshWorker
from recraft.engine.user_importance import BrushMode, UserImportanceState, canvas_to_source, render_source_mask
from recraft.engine.colour_selection import select_similar_colour
from recraft.engine.region_selection import select_connected_region
from recraft.exporters.contour_mesh import ContourMeshSettings


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
        self._render_worker: RenderWorker | MeshWorker | None = None
        self.user_importance: UserImportanceState | None = None
        self._selection_kind: str | None = None
        self._selection_point: tuple[float, float] | None = None
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

        self.importance_box = QGroupBox("2. Importance")
        importance_layout = QGridLayout(self.importance_box)
        self.brush_mode = QComboBox(); self.brush_mode.addItem("Pan image", "pan"); self.brush_mode.addItem("Add importance brush", BrushMode.ADD); self.brush_mode.addItem("Reduce importance brush", BrushMode.REDUCE); self.brush_mode.addItem("Erase to automatic", BrushMode.ERASE)
        self.brush_mode.currentIndexChanged.connect(self._importance_mode_changed)
        self.brush_size = QSpinBox(); self.brush_size.setRange(5, 200); self.brush_size.setValue(45); self.brush_size.setSuffix(" px")
        self.brush_strength = QDoubleSpinBox(); self.brush_strength.setRange(0.05, 1.0); self.brush_strength.setSingleStep(0.05); self.brush_strength.setValue(0.8)
        self.auto_strength = QDoubleSpinBox(); self.user_strength = QDoubleSpinBox(); self.background_strength = QDoubleSpinBox()
        for spin, value in ((self.auto_strength, 1.0), (self.user_strength, 1.0), (self.background_strength, 0.35)):
            spin.setRange(0, 2); spin.setSingleStep(0.05); spin.setValue(value); spin.valueChanged.connect(self._importance_weights_changed)
        self.show_overlay = QCheckBox("Show overlay"); self.show_overlay.setChecked(True); self.show_overlay.toggled.connect(self._refresh_prepared)
        clear = QPushButton("Clear user mask"); clear.clicked.connect(self._clear_importance)
        importance_layout.addWidget(self.brush_mode, 0, 0); importance_layout.addWidget(QLabel("Brush size"), 0, 1); importance_layout.addWidget(self.brush_size, 0, 2); importance_layout.addWidget(QLabel("Strength"), 0, 3); importance_layout.addWidget(self.brush_strength, 0, 4); importance_layout.addWidget(self.show_overlay, 0, 5); importance_layout.addWidget(clear, 0, 6)
        importance_layout.addWidget(QLabel("Automatic"), 1, 0); importance_layout.addWidget(self.auto_strength, 1, 1); importance_layout.addWidget(QLabel("User"), 1, 2); importance_layout.addWidget(self.user_strength, 1, 3); importance_layout.addWidget(QLabel("Background suppression"), 1, 4); importance_layout.addWidget(self.background_strength, 1, 5)
        self.selection_tolerance = QDoubleSpinBox(); self.selection_tolerance.setRange(2, 80); self.selection_tolerance.setValue(18); self.selection_tolerance.setSuffix(" tolerance")
        self.selection_feather = QDoubleSpinBox(); self.selection_feather.setRange(0, 20); self.selection_feather.setValue(3); self.selection_connected = QCheckBox("Connected only")
        self.selection_tolerance.valueChanged.connect(self._selection_parameters_changed); self.selection_feather.valueChanged.connect(self._selection_parameters_changed); self.selection_connected.toggled.connect(self._selection_parameters_changed)
        colour = QPushButton("Pick Colour"); colour.clicked.connect(lambda: self._begin_selection("colour")); region = QPushButton("Pick Region"); region.clicked.connect(lambda: self._begin_selection("region"))
        add_selection = QPushButton("Add Selection"); add_selection.clicked.connect(lambda: self._apply_selection(BrushMode.ADD)); reduce_selection = QPushButton("Reduce Selection"); reduce_selection.clicked.connect(lambda: self._apply_selection(BrushMode.REDUCE)); cancel_selection = QPushButton("Cancel"); cancel_selection.clicked.connect(self._cancel_selection)
        importance_layout.addWidget(colour, 2, 0); importance_layout.addWidget(region, 2, 1); importance_layout.addWidget(self.selection_tolerance, 2, 2); importance_layout.addWidget(QLabel("Feather"), 2, 3); importance_layout.addWidget(self.selection_feather, 2, 4); importance_layout.addWidget(self.selection_connected, 2, 5)
        selection_actions = QHBoxLayout(); selection_actions.addWidget(add_selection); selection_actions.addWidget(reduce_selection); selection_actions.addWidget(cancel_selection); importance_layout.addLayout(selection_actions, 3, 0, 1, 7)
        root.addWidget(self.importance_box)

        self.style_box = QGroupBox("3. Apply Art Style")
        style_layout = QHBoxLayout(self.style_box)
        self.style_combo = QComboBox()
        for style in self.registry: self.style_combo.addItem(style.display_name, style.identifier)
        self.style_combo.currentIndexChanged.connect(self._rebuild_parameters)
        self.debug_combo = QComboBox()
        self.debug_combo.addItem("Artwork", None)
        for name in ("Automatic Importance", "Combined Importance", "User Add Mask", "User Reduce Mask", "Background Suppression", "Colour Selection Preview", "Region Selection Preview", "Raw Contour Paths", "Filtered Contour Paths", "Contour Importance View", "Edge Map", "Face Mask", "Background Mask", "Saliency", "Colour Clusters", "Texture", "Subject Mask"):
            self.debug_combo.addItem(name, name)
        self.debug_combo.setToolTip("Developer view of reusable ReCraft Engine analysis maps")
        self.description = QLabel(); self.parameter_container = QWidget(); self.parameter_form = QFormLayout(self.parameter_container)
        self.generate_button = QPushButton("Generate Preview"); self.generate_button.clicked.connect(self._generate)
        style_layout.addWidget(QLabel("Style")); style_layout.addWidget(self.style_combo); style_layout.addWidget(self.description, 1); style_layout.addWidget(self.parameter_container); style_layout.addWidget(QLabel("Developer view")); style_layout.addWidget(self.debug_combo); style_layout.addWidget(self.generate_button)
        root.addWidget(self.style_box)

        self.mesh_box = QGroupBox("4. Contour STL")
        mesh_layout = QHBoxLayout(self.mesh_box)
        self.mesh_width = QDoubleSpinBox(); self.mesh_width.setRange(20, 1000); self.mesh_width.setValue(150); self.mesh_width.setSuffix(" mm")
        self.base_thickness = QDoubleSpinBox(); self.base_thickness.setRange(0.4, 20); self.base_thickness.setValue(2); self.base_thickness.setSuffix(" mm")
        self.ridge_height = QDoubleSpinBox(); self.ridge_height.setRange(0.2, 20); self.ridge_height.setValue(1.2); self.ridge_height.setSuffix(" mm")
        self.ridge_width = QDoubleSpinBox(); self.ridge_width.setRange(0.8, 20); self.ridge_width.setValue(1.2); self.ridge_width.setSuffix(" mm")
        self.border_width = QDoubleSpinBox(); self.border_width.setRange(0, 50); self.border_width.setValue(3); self.border_width.setSuffix(" mm")
        for label, widget in (("Width", self.mesh_width), ("Base", self.base_thickness), ("Ridge height", self.ridge_height), ("Ridge width", self.ridge_width), ("Border", self.border_width)):
            mesh_layout.addWidget(QLabel(label)); mesh_layout.addWidget(widget)
        self.stl_button = QPushButton("Export Contour STL"); self.stl_button.clicked.connect(self._save_stl); mesh_layout.addWidget(self.stl_button)
        root.addWidget(self.mesh_box)

        panels = QHBoxLayout()
        left = QVBoxLayout(); left.addWidget(QLabel("Prepared image — wheel to zoom, drag to pan")); self.prepared_view = ImageView("Open an image to begin", interactive=True); left.addWidget(self.prepared_view)
        self.prepared_view.zoom_requested.connect(self._gesture_zoom); self.prepared_view.pan_requested.connect(self._gesture_pan)
        self.prepared_view.image_painted.connect(self._paint_importance); self.prepared_view.image_clicked.connect(self._selection_clicked)
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
        if hasattr(self, "mesh_box"): self.mesh_box.setEnabled(style.identifier == "contour")

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
            self.user_importance = UserImportanceState.create(self.source_image.size)
            self.user_importance.automatic_strength = self.auto_strength.value()
            self.user_importance.user_strength = self.user_strength.value()
            self.user_importance.background_suppression = self.background_strength.value()
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
        self.prepared_preview = render_prepared_preview(self.source_image, self.transform_settings)
        display = self.prepared_preview.copy()
        if self.show_overlay.isChecked() and self.user_importance is not None:
            add = render_source_mask(self.user_importance.add_mask, self.transform_settings, display.size)
            reduce = render_source_mask(self.user_importance.reduce_mask, self.transform_settings, display.size)
            if self.user_importance.colour_preview is not None:
                colour = render_source_mask(self.user_importance.colour_preview, self.transform_settings, display.size)
            else: colour = np.zeros_like(add)
            if self.user_importance.region_preview is not None:
                region = render_source_mask(self.user_importance.region_preview, self.transform_settings, display.size)
            else: region = np.zeros_like(add)
            pixels = np.asarray(display).astype(np.float32)
            overlay = np.zeros_like(pixels); overlay[..., 0] = np.maximum(add, colour) * 255; overlay[..., 2] = np.maximum(reduce, region) * 255
            alpha = np.clip(np.maximum.reduce((add, reduce, colour, region)) * 0.42, 0, 0.55)[..., None]
            display = Image.fromarray(np.clip(pixels * (1 - alpha) + overlay * alpha, 0, 255).astype(np.uint8), "RGB")
        self.prepared_view.set_image(display)

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
            self.source_image,
            settings,
            style,
            parameters,
            export_path,
            None if export_path else self.debug_combo.currentData(),
            copy.deepcopy(self.user_importance),
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
        operation = "Exporting full-resolution PNG" if export_path else "Generating Engine preview"
        self.statusBar().showMessage(f"{operation}…")
        thread.start()

    def _set_rendering(self, active: bool) -> None:
        """Prevent conflicting changes and show indeterminate progress."""
        self.open_button.setEnabled(not active)
        self.setup_box.setEnabled(not active)
        self.importance_box.setEnabled(not active)
        self.style_box.setEnabled(not active)
        self.mesh_box.setEnabled(not active and self._current_style().identifier == "contour")
        self.save_button.setEnabled(not active and self.source_image is not None)
        self.progress.setVisible(active)

    def _preview_finished(self, result: object) -> None:
        if not isinstance(result, Image.Image):
            self._render_failed("The preview renderer returned an invalid image")
            return
        self.output_image = result
        self.output_view.set_image(result)
        label = self.debug_combo.currentText() if self.debug_combo.currentData() else self._current_style().display_name
        self.statusBar().showMessage(
            f"Generated {label} preview at "
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

    def _importance_mode_changed(self) -> None:
        mode = self.brush_mode.currentData()
        self._selection_kind = None
        self.prepared_view.set_interaction_mode("pan" if mode == "pan" else "paint")

    def _importance_weights_changed(self) -> None:
        if self.user_importance is None: return
        self.user_importance.automatic_strength = self.auto_strength.value()
        self.user_importance.user_strength = self.user_strength.value()
        self.user_importance.background_suppression = self.background_strength.value()
        self._invalidate_output()

    def _clear_importance(self) -> None:
        if self.user_importance is not None: self.user_importance.clear()
        self._refresh_prepared(); self._invalidate_output()

    def _paint_importance(self, x: float, y: float) -> None:
        if self.source_image is None or self.user_importance is None or self.prepared_preview is None: return
        mapped = canvas_to_source((x, y), self.source_image.size, self.transform_settings, self.prepared_preview.size)
        if mapped is None: return
        mode = self.brush_mode.currentData()
        try: mode = BrushMode(mode)
        except ValueError: return
        radius = self.brush_size.value() / max(self.prepared_preview.size)
        self.user_importance.paint_source(*mapped, radius, self.brush_strength.value(), mode)
        self._refresh_prepared(); self._invalidate_output()

    def _begin_selection(self, kind: str) -> None:
        if self.source_image is None or self.user_importance is None:
            QMessageBox.information(self, "No image", "Open an image before selecting a colour or region."); return
        self._selection_kind = kind; self._selection_point = None; self.prepared_view.set_interaction_mode("select")
        self.statusBar().showMessage(f"Click the prepared image to preview a {kind} selection")

    def _selection_clicked(self, x: float, y: float) -> None:
        if self._selection_kind is None or self.source_image is None or self.user_importance is None or self.prepared_preview is None: return
        mapped = canvas_to_source((x, y), self.source_image.size, self.transform_settings, self.prepared_preview.size)
        if mapped is None: return
        self._selection_point = mapped
        self._update_selection_preview()

    def _selection_parameters_changed(self) -> None:
        if self._selection_kind is not None and self._selection_point is not None:
            self._update_selection_preview()

    def _update_selection_preview(self) -> None:
        """Regenerate the pending selection after tolerance changes."""
        if self._selection_kind is None or self._selection_point is None or self.source_image is None or self.user_importance is None: return
        proxy = self.source_image.copy(); proxy.thumbnail(self.user_importance.mask_size, Image.Resampling.LANCZOS)
        rgb = np.asarray(proxy); point = (min(proxy.width - 1, round(self._selection_point[0] * (proxy.width - 1))), min(proxy.height - 1, round(self._selection_point[1] * (proxy.height - 1))))
        if self._selection_kind == "colour":
            mask = select_similar_colour(rgb, point, self.selection_tolerance.value(), self.selection_feather.value(), self.selection_connected.isChecked())
            self.user_importance.colour_preview = mask; self.user_importance.region_preview = None
        else:
            mask = select_connected_region(rgb, point, self.selection_tolerance.value(), self.selection_feather.value())
            self.user_importance.region_preview = mask; self.user_importance.colour_preview = None
        self._refresh_prepared(); self.statusBar().showMessage("Selection preview ready — add, reduce, or cancel")

    def _apply_selection(self, mode: BrushMode) -> None:
        if self.user_importance is None: return
        mask = self.user_importance.colour_preview if self.user_importance.colour_preview is not None else self.user_importance.region_preview
        if mask is None: return
        self.user_importance.apply_selection(mask, mode, self.brush_strength.value())
        self._cancel_selection(); self._invalidate_output()

    def _cancel_selection(self) -> None:
        if self.user_importance is not None:
            self.user_importance.colour_preview = None; self.user_importance.region_preview = None
        self._selection_kind = None; self._selection_point = None; self._importance_mode_changed(); self._refresh_prepared()

    def _save_stl(self) -> None:
        if self.source_image is None: return
        if self._current_style().identifier != "contour":
            QMessageBox.information(self, "Contour only", "STL export is currently available only for Contour."); return
        filename, _ = QFileDialog.getSaveFileName(self, "Save Contour STL", "recraft-contour.stl", "STL mesh (*.stl)")
        if not filename: return
        if not filename.lower().endswith(".stl"): filename += ".stl"
        settings = ContourMeshSettings(physical_width=self.mesh_width.value(), base_thickness=self.base_thickness.value(), ridge_height=self.ridge_height.value(), ridge_width=self.ridge_width.value(), border_width=self.border_width.value())
        thread = QThread(self); worker = MeshWorker(self.source_image, self._settings_from_controls(), copy.deepcopy(self.user_importance), self._style_parameters(), settings, filename)
        worker.moveToThread(thread); thread.started.connect(worker.run); worker.exported.connect(self._mesh_exported); worker.failed.connect(self._render_failed); worker.finished.connect(thread.quit); worker.finished.connect(worker.deleteLater); thread.finished.connect(self._render_cleanup); thread.finished.connect(thread.deleteLater)
        self._render_thread = thread; self._render_worker = worker; self._set_rendering(True); self.statusBar().showMessage("Generating and validating Contour STL…"); thread.start()

    def _mesh_exported(self, path: str, width: float, height: float, vertices: int, faces: int, watertight: bool) -> None:
        summary = f"Saved {Path(path).name}\nDimensions: {width:.1f} × {height:.1f} mm\nVertices: {vertices:,}\nFaces: {faces:,}\nWatertight: {'yes' if watertight else 'no'}"
        self.statusBar().showMessage(summary.replace("\n", " — ")); QMessageBox.information(self, "Contour STL exported", summary)

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
