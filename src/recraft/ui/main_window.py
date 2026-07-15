"""Preview-first ReCraft Portrait Relief workspace."""

from dataclasses import replace
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QColor, QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from recraft.core.diagnostics import diagnostic_log_path
from recraft.core.image_loader import ImageLoadError, load_image
from recraft.core.image_transform import FitMode, ImageTransformSettings, prepare_image
from recraft.core_engine import (
    BackgroundTreatment,
    ColourMode,
    CoreRenderResult,
    CoreSettings,
    DetailLevel,
    MonochromeMaterial,
    SubjectEmphasis,
)
from recraft.core_engine.colour import build_colour_map
from recraft.ui.collapsible import CollapsibleSection
from recraft.ui.core_worker import CoreWorker
from recraft.ui.image_view import ImageView
from recraft.ui.mesh_view import MeshView


class MainWindow(QMainWindow):
    """Turn one simple subject photograph into designed printable artwork."""

    def __init__(self) -> None:
        super().__init__()
        self.source_image: Image.Image | None = None
        self.prepared_image: Image.Image | None = None
        self.core_result: CoreRenderResult | None = None
        self._thread: QThread | None = None
        self._worker: CoreWorker | None = None
        self.preview_up_to_date = False
        self._palette_values: list[str | None] = [None] * 6
        self._custom_material_colour = "#A59D90"
        self.setWindowTitle("ReCraft — Portrait Relief")
        self.resize(1200, 720)
        self.setMinimumSize(880, 580)
        self._build_ui()
        self._mark_stale(initial=True)

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(7, 7, 7, 7)
        root.setSpacing(5)
        heading = QHBoxLayout()
        title = QLabel("ReCraft Portrait Relief")
        title.setStyleSheet("font-size:22px;font-weight:700")
        statement = QLabel("Photographs rebuilt as distinctive printable artwork.")
        statement.setStyleSheet("color:#68717d")
        heading.addWidget(title)
        heading.addWidget(statement)
        heading.addStretch()
        root.addLayout(heading)

        workspace = QSplitter(Qt.Orientation.Horizontal)
        previews = QSplitter(Qt.Orientation.Horizontal)
        source_panel = QWidget()
        source_layout = QVBoxLayout(source_panel)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_bar = QHBoxLayout()
        source_bar.addWidget(QLabel("Source image"))
        source_bar.addStretch()
        fit_source = QPushButton("Fit")
        fit_source.clicked.connect(self.source_view_fit)
        source_bar.addWidget(fit_source)
        source_layout.addLayout(source_bar)
        self.source_view = ImageView("Open a simple portrait, pet, or vehicle photograph", interactive=True)
        self.source_view.enable_view_navigation(True)
        source_layout.addWidget(self.source_view, 1)

        relief_panel = QWidget()
        relief_layout = QVBoxLayout(relief_panel)
        relief_layout.setContentsMargins(0, 0, 0, 0)
        camera = QHBoxLayout()
        camera.addWidget(QLabel("Relief preview"))
        camera.addStretch()
        for label, action in (
            ("Fit", self.mesh_fit),
            ("Reset", self.mesh_reset),
            ("Front", lambda: self.mesh_view.set_standard_view("Front")),
            ("Perspective", lambda: self.mesh_view.set_standard_view("Perspective")),
        ):
            button = QPushButton(label)
            button.clicked.connect(action)
            camera.addWidget(button)
        self.orthographic = QCheckBox("Orthographic")
        self.orthographic.toggled.connect(lambda checked: self.mesh_view.set_projection("orthographic" if checked else "perspective"))
        camera.addWidget(self.orthographic)
        relief_layout.addLayout(camera)
        self.mesh_view = MeshView()
        relief_layout.addWidget(self.mesh_view, 1)
        previews.addWidget(source_panel)
        previews.addWidget(relief_panel)
        previews.setSizes([430, 610])
        previews.setStretchFactor(0, 2)
        previews.setStretchFactor(1, 3)

        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(7, 3, 7, 3)
        controls_layout.setSpacing(6)
        self.open_button = QPushButton("Open Image")
        self.open_button.clicked.connect(self._open_image)
        controls_layout.addWidget(self.open_button)
        framing_row = QHBoxLayout()
        self.framing_combo = QComboBox()
        self.framing_combo.addItem("Fit full image", "fit")
        self.framing_combo.addItem("Crop to 4:5 artwork", "crop")
        self.framing_combo.currentIndexChanged.connect(self._framing_changed)
        reset_image = QPushButton("Reset")
        reset_image.clicked.connect(self._reset_image)
        framing_row.addWidget(self.framing_combo, 1)
        framing_row.addWidget(reset_image)
        controls_layout.addLayout(framing_row)

        form = QFormLayout()
        self._controls_form = form
        form.setVerticalSpacing(5)
        self.subject_combo = QComboBox()
        for value in SubjectEmphasis:
            self.subject_combo.addItem(value.value, value)
        self.subject_combo.setCurrentIndex(self.subject_combo.findData(SubjectEmphasis.MEDIUM))
        self.subject_combo.setToolTip("How strongly likely subject form is prioritised over its surroundings.")
        self.subject_combo.currentIndexChanged.connect(self._geometry_setting_changed)
        form.addRow("Subject emphasis", self.subject_combo)
        self.background_combo = QComboBox()
        for value in BackgroundTreatment:
            self.background_combo.addItem(value.value, value)
        self.background_combo.setCurrentIndex(self.background_combo.findData(BackgroundTreatment.SIMPLIFY))
        self.background_combo.setToolTip("Remove flattens the background; Simplify keeps broad structure; Keep retains more scene form.")
        self.background_combo.currentIndexChanged.connect(self._geometry_setting_changed)
        form.addRow("Background", self.background_combo)
        self.detail_combo = QComboBox()
        for value in DetailLevel:
            self.detail_combo.addItem(value.value, value)
        self.detail_combo.setCurrentIndex(self.detail_combo.findData(DetailLevel.BALANCED))
        self.detail_combo.setToolTip("Physical design detail; all modes remain bounded by the minimum printable feature.")
        self.detail_combo.currentIndexChanged.connect(self._geometry_setting_changed)
        form.addRow("Detail", self.detail_combo)
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(40, 500)
        self.width_spin.setValue(160)
        self.width_spin.setSuffix(" mm")
        self.width_spin.valueChanged.connect(self._geometry_setting_changed)
        form.addRow("Physical width", self.width_spin)
        self.depth_spin = QDoubleSpinBox()
        self.depth_spin.setRange(.5, 5)
        self.depth_spin.setValue(1.8)
        self.depth_spin.setSingleStep(.1)
        self.depth_spin.setSuffix(" mm")
        self.depth_spin.valueChanged.connect(self._geometry_setting_changed)
        form.addRow("Relief depth", self.depth_spin)
        self.colour_combo = QComboBox()
        for value in ColourMode:
            self.colour_combo.addItem(value.value, value)
        self.colour_combo.setCurrentIndex(self.colour_combo.findData(ColourMode.MONOCHROME))
        self.colour_combo.currentIndexChanged.connect(self._colour_setting_changed)
        form.addRow("Preview colour", self.colour_combo)
        self.palette_size_combo = QComboBox()
        for count in (2, 3, 4, 6):
            self.palette_size_combo.addItem(f"{count} colours", count)
        self.palette_size_combo.setCurrentIndex(2)
        self.palette_size_combo.currentIndexChanged.connect(self._colour_setting_changed)
        form.addRow("Palette size", self.palette_size_combo)
        self.material_combo = QComboBox()
        for material in MonochromeMaterial:
            self.material_combo.addItem(material.value, material)
        self.material_combo.setCurrentIndex(self.material_combo.findData(MonochromeMaterial.STONE))
        self.material_combo.currentIndexChanged.connect(self._colour_setting_changed)
        form.addRow("Material", self.material_combo)
        self.custom_material_button = QPushButton(self._custom_material_colour)
        self.custom_material_button.clicked.connect(self._choose_material_colour)
        form.addRow("Custom colour", self.custom_material_button)
        controls_layout.addLayout(form)

        self.palette_panel = QWidget()
        palette_layout = QVBoxLayout(self.palette_panel)
        palette_layout.setContentsMargins(0, 0, 0, 0)
        palette_layout.addWidget(QLabel("Palette colours — click to replace, lock to retain"))
        self.palette_buttons: list[QPushButton] = []
        self.palette_locks: list[QCheckBox] = []
        palette_row = QHBoxLayout()
        for index in range(6):
            column = QVBoxLayout()
            button = QPushButton(str(index + 1))
            button.setFixedWidth(36)
            button.clicked.connect(lambda checked=False, slot=index: self._choose_palette_colour(slot))
            lock = QCheckBox("Lock")
            lock.toggled.connect(self._colour_setting_changed)
            column.addWidget(button)
            column.addWidget(lock)
            palette_row.addLayout(column)
            self.palette_buttons.append(button)
            self.palette_locks.append(lock)
        palette_layout.addLayout(palette_row)
        reset_palette = QPushButton("Reset automatic palette")
        reset_palette.clicked.connect(self._reset_palette)
        palette_layout.addWidget(reset_palette)
        controls_layout.addWidget(self.palette_panel)

        self.generate_button = QPushButton("Generate Relief")
        self.generate_button.setMinimumHeight(36)
        self.generate_button.setStyleSheet("font-weight:700")
        self.generate_button.clicked.connect(self._generate)
        controls_layout.addWidget(self.generate_button)
        self.state_label = QLabel()
        self.state_label.setWordWrap(True)
        controls_layout.addWidget(self.state_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.hide()
        controls_layout.addWidget(self.progress)
        self.summary = QLabel("No relief generated.")
        self.summary.setWordWrap(True)
        controls_layout.addWidget(self.summary)
        export_row = QHBoxLayout()
        self.stl_button = QPushButton("Export STL")
        self.stl_button.setToolTip("STL stores geometry only; it does not contain colour.")
        self.stl_button.clicked.connect(lambda: self._export("stl"))
        self.threemf_button = QPushButton("Export 3MF")
        self.threemf_button.setToolTip("3MF stores one printable object and limited display/material assignments.")
        self.threemf_button.clicked.connect(lambda: self._export("3mf"))
        export_row.addWidget(self.stl_button)
        export_row.addWidget(self.threemf_button)
        controls_layout.addLayout(export_row)

        advanced = QWidget()
        advanced_form = QFormLayout(advanced)
        self.preview_quality = QComboBox()
        self.preview_quality.addItem("Fast", 140)
        self.preview_quality.addItem("Balanced", 170)
        self.preview_quality.addItem("Fine", 190)
        self.preview_quality.setCurrentIndex(2)
        self.preview_quality.currentIndexChanged.connect(self._geometry_setting_changed)
        advanced_form.addRow("Preview quality", self.preview_quality)
        self.export_quality = QComboBox()
        self.export_quality.addItem("Standard", 240)
        self.export_quality.addItem("Fine", 270)
        self.export_quality.addItem("Maximum", 290)
        self.export_quality.setCurrentIndex(1)
        advanced_form.addRow("Export quality", self.export_quality)
        self.base_spin = QDoubleSpinBox()
        self.base_spin.setRange(.8, 8)
        self.base_spin.setValue(1.5)
        self.base_spin.setSuffix(" mm")
        self.base_spin.valueChanged.connect(self._geometry_setting_changed)
        advanced_form.addRow("Base thickness", self.base_spin)
        self.minimum_feature_spin = QDoubleSpinBox()
        self.minimum_feature_spin.setRange(.6, 3)
        self.minimum_feature_spin.setValue(.8)
        self.minimum_feature_spin.setSuffix(" mm")
        self.minimum_feature_spin.valueChanged.connect(self._geometry_setting_changed)
        advanced_form.addRow("Minimum feature", self.minimum_feature_spin)
        self.nozzle_spin = QDoubleSpinBox()
        self.nozzle_spin.setRange(.2, 1.2)
        self.nozzle_spin.setValue(.4)
        self.nozzle_spin.setSuffix(" mm")
        self.nozzle_spin.valueChanged.connect(self._geometry_setting_changed)
        advanced_form.addRow("Nozzle", self.nozzle_spin)
        self.layer_spin = QDoubleSpinBox()
        self.layer_spin.setRange(.05, .6)
        self.layer_spin.setValue(.2)
        self.layer_spin.setSuffix(" mm")
        self.layer_spin.valueChanged.connect(self._geometry_setting_changed)
        advanced_form.addRow("Layer height", self.layer_spin)
        self.invert_check = QCheckBox("Invert relief")
        self.invert_check.toggled.connect(self._geometry_setting_changed)
        advanced_form.addRow(self.invert_check)
        self.advanced_section = CollapsibleSection("Advanced", advanced, expanded=False)
        controls_layout.addWidget(self.advanced_section)
        controls_layout.addStretch()

        self._geometry_controls = (
            self.framing_combo, self.subject_combo, self.background_combo, self.detail_combo,
            self.width_spin, self.depth_spin, self.preview_quality, self.export_quality,
            self.base_spin, self.minimum_feature_spin, self.nozzle_spin, self.layer_spin,
            self.invert_check,
        )
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(controls)
        scroll.setMinimumWidth(285)
        scroll.setMaximumWidth(370)
        workspace.addWidget(previews)
        workspace.addWidget(scroll)
        workspace.setSizes([900, 310])
        workspace.setStretchFactor(0, 1)
        root.addWidget(workspace, 1)
        self.setCentralWidget(central)
        self._sync_colour_controls()

    def source_view_fit(self) -> None:
        self.source_view.fit_to_view()

    def mesh_fit(self) -> None:
        self.mesh_view.fit_mesh()

    def mesh_reset(self) -> None:
        self.mesh_view.reset_camera()

    def _open_image(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Open photograph", "", "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)")
        if not filename:
            return
        try:
            self.source_image = load_image(filename)
        except ImageLoadError as exc:
            QMessageBox.critical(self, "Could not open image", str(exc))
            return
        self._refresh_prepared()
        self.core_result = None
        self.mesh_view.set_mesh(None)
        self._mark_stale()

    def _preparation_settings(self) -> ImageTransformSettings:
        if self.source_image is None:
            return ImageTransformSettings()
        if self.framing_combo.currentData() == "crop":
            return ImageTransformSettings(output_width=960, output_height=1200, aspect_ratio=(4, 5), fit_mode=FitMode.FILL)
        scale = min(1.0, 1200 / max(self.source_image.size))
        width = max(1, round(self.source_image.width * scale))
        height = max(1, round(self.source_image.height * scale))
        return ImageTransformSettings(output_width=width, output_height=height, aspect_ratio=self.source_image.size, fit_mode=FitMode.FIT)

    def _refresh_prepared(self) -> None:
        if self.source_image is None:
            return
        self.prepared_image = prepare_image(self.source_image, self._preparation_settings())
        self.source_view.set_image(self.prepared_image)

    def _reset_image(self) -> None:
        self.framing_combo.setCurrentIndex(0)
        self._refresh_prepared()
        self.source_view.fit_to_view()
        self._mark_stale()

    def _locked_palette(self) -> tuple[str | None, ...]:
        count = int(self.palette_size_combo.currentData())
        return tuple(self._palette_values[index] if self.palette_locks[index].isChecked() else None for index in range(count))

    def _settings(self) -> CoreSettings:
        return CoreSettings(
            subject_emphasis=self.subject_combo.currentData(),
            background=self.background_combo.currentData(),
            detail=self.detail_combo.currentData(),
            colour_mode=self.colour_combo.currentData(),
            palette_size=int(self.palette_size_combo.currentData()),
            locked_palette=self._locked_palette(),
            monochrome_material=self.material_combo.currentData(),
            custom_material_colour=self._custom_material_colour,
            physical_width_mm=self.width_spin.value(),
            relief_depth_mm=self.depth_spin.value(),
            base_thickness_mm=self.base_spin.value(),
            nozzle_diameter_mm=self.nozzle_spin.value(),
            layer_height_mm=self.layer_spin.value(),
            minimum_feature_mm=self.minimum_feature_spin.value(),
            preview_resolution=int(self.preview_quality.currentData()),
            export_resolution=int(self.export_quality.currentData()),
            invert=self.invert_check.isChecked(),
        ).validated()

    def _framing_changed(self) -> None:
        self._refresh_prepared()
        self._mark_stale()

    def _geometry_setting_changed(self) -> None:
        self._mark_stale()

    def _colour_setting_changed(self) -> None:
        self._sync_colour_controls()
        if self.core_result is not None:
            self._recolour_existing_result()

    def _sync_colour_controls(self) -> None:
        artistic = self.colour_combo.currentData() == ColourMode.ARTISTIC
        monochrome = self.colour_combo.currentData() == ColourMode.MONOCHROME
        self.palette_size_combo.setVisible(artistic)
        self._controls_form.labelForField(self.palette_size_combo).setVisible(artistic)
        self.palette_panel.setVisible(artistic)
        self.material_combo.setVisible(monochrome)
        self._controls_form.labelForField(self.material_combo).setVisible(monochrome)
        custom = monochrome and self.material_combo.currentData() == MonochromeMaterial.CUSTOM
        self.custom_material_button.setVisible(
            custom
        )
        self._controls_form.labelForField(self.custom_material_button).setVisible(custom)

    def _choose_material_colour(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._custom_material_colour), self, "Choose matte material colour")
        if not chosen.isValid():
            return
        self._custom_material_colour = chosen.name().upper()
        self.custom_material_button.setText(self._custom_material_colour)
        self.custom_material_button.setStyleSheet(f"background:{self._custom_material_colour}")
        self._recolour_existing_result()

    def _recolour_existing_result(self) -> None:
        if self.core_result is None:
            return
        try:
            settings = self._settings()
            size = (self.core_result.relief.values.shape[1], self.core_result.relief.values.shape[0])
            colour = build_colour_map(
                self.core_result.prepared.pixels,
                settings,
                size,
                max(4, self.core_result.simplification.minimum_feature_pixels**2),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Check colour settings", str(exc))
            return
        self.core_result = replace(self.core_result, colour=colour, mesh=replace(self.core_result.mesh, colour_map=colour))
        self.mesh_view.set_surface_texture(colour.pixels)
        self._update_palette_buttons(colour.palette)

    def _choose_palette_colour(self, index: int) -> None:
        current = self._palette_values[index] or "#808080"
        chosen = QColorDialog.getColor(QColor(current), self, f"Replace palette colour {index + 1}")
        if not chosen.isValid():
            return
        self._palette_values[index] = chosen.name().upper()
        self.palette_locks[index].setChecked(True)
        self._colour_setting_changed()

    def _reset_palette(self) -> None:
        self._palette_values = [None] * 6
        for lock in self.palette_locks:
            lock.setChecked(False)
        self._recolour_existing_result()

    def _update_palette_buttons(self, palette: tuple[str, ...]) -> None:
        count = int(self.palette_size_combo.currentData())
        for index, button in enumerate(self.palette_buttons):
            visible = index < count
            button.setVisible(visible)
            self.palette_locks[index].setVisible(visible)
            if index < len(palette):
                colour = palette[index]
                if not self.palette_locks[index].isChecked():
                    self._palette_values[index] = colour
                button.setText("")
                button.setToolTip(colour)
                button.setStyleSheet(f"background:{colour};border:1px solid #444")

    def _mark_stale(self, initial: bool = False) -> None:
        self.preview_up_to_date = False
        text = "Open an image" if initial or self.source_image is None else "Settings changed — regenerate"
        self.state_label.setText(text)
        self.state_label.setStyleSheet("color:#9A6700")
        self.generate_button.setEnabled(self.source_image is not None and self._thread is None)
        self.stl_button.setEnabled(False)
        self.threemf_button.setEnabled(False)

    def _generate(self) -> None:
        if self.prepared_image is None:
            QMessageBox.information(self, "No image", "Open an image first.")
            return
        try:
            settings = self._settings()
        except ValueError as exc:
            QMessageBox.warning(self, "Check settings", str(exc))
            return
        self._start_worker(CoreWorker(self.prepared_image, settings))

    def _export(self, format_name: str) -> None:
        if not self.preview_up_to_date or self.prepared_image is None:
            return
        suffix = f".{format_name}"
        label = "STL geometry only (*.stl)" if format_name == "stl" else "3MF colour/material model (*.3mf)"
        filename, _ = QFileDialog.getSaveFileName(self, f"Export {format_name.upper()}", f"recraft-portrait-relief{suffix}", label)
        if not filename:
            return
        if not filename.lower().endswith(suffix):
            filename += suffix
        try:
            settings = self._settings()
        except ValueError as exc:
            QMessageBox.warning(self, "Check settings", str(exc))
            return
        self._start_worker(CoreWorker(self.prepared_image, settings, format_name, filename))

    def _start_worker(self, worker: CoreWorker) -> None:
        if self._thread is not None:
            return
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.stage_changed.connect(self._stage_changed)
        worker.preview_ready.connect(self._preview_ready)
        worker.export_ready.connect(self._export_ready)
        worker.failed.connect(self._generation_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._worker_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread, self._worker = thread, worker
        self.open_button.setEnabled(False)
        self.generate_button.setEnabled(False)
        self.stl_button.setEnabled(False)
        self.threemf_button.setEnabled(False)
        for control in self._geometry_controls:
            control.setEnabled(False)
        self.progress.setValue(0)
        self.progress.show()
        self.state_label.setText("Generating")
        self.state_label.setStyleSheet("color:#0969DA")
        thread.start()

    def _stage_changed(self, stage: str, progress: int) -> None:
        self.state_label.setText(f"Generating — {stage}")
        self.progress.setValue(progress)

    def _preview_ready(self, result: CoreRenderResult) -> None:
        self.core_result = result
        mesh = result.mesh.result
        self.mesh_view.set_mesh(mesh, surface_pixels=result.colour.pixels)
        self.preview_up_to_date = True
        self.state_label.setText("Preview up to date")
        self.state_label.setStyleSheet("color:#1A7F37")
        warnings = (*result.relief.warnings, *result.colour.warnings)
        warning_text = "\n".join(f"Warning: {warning}" for warning in warnings)
        self.summary.setText(
            f"{mesh.width_mm:.1f} × {mesh.height_mm:.1f} mm\n"
            f"Base {self.base_spin.value():.1f} mm + relief {self.depth_spin.value():.1f} mm\n"
            f"{mesh.triangle_count:,} preview triangles · Watertight\n"
            f"Subject analysis: {result.analysis.fallback_state} ({result.analysis.confidence:.0%})"
            + (f"\n{warning_text}" if warning_text else "")
        )
        self._update_palette_buttons(result.colour.palette)

    def _export_ready(self, path: str, result: CoreRenderResult) -> None:
        mesh = result.mesh.result
        colour_note = "Geometry only; STL contains no colour." if path.lower().endswith(".stl") else "One watertight object with display/material assignments."
        self.summary.setText(f"Exported {Path(path).name}\n{mesh.width_mm:.1f} × {mesh.height_mm:.1f} mm\n{mesh.triangle_count:,} triangles · Watertight\n{colour_note}")

    def _generation_failed(self, message: str) -> None:
        self.state_label.setText("Generation failed — previous preview preserved")
        self.state_label.setStyleSheet("color:#CF222E")
        QMessageBox.critical(self, "ReCraft generation failed safely", f"{message}\n\nDiagnostic log: {diagnostic_log_path()}")

    def _worker_finished(self) -> None:
        self._thread = None
        self._worker = None
        self.progress.hide()
        self.open_button.setEnabled(True)
        for control in self._geometry_controls:
            control.setEnabled(True)
        self.generate_button.setEnabled(self.source_image is not None)
        self.stl_button.setEnabled(self.preview_up_to_date)
        self.threemf_button.setEnabled(self.preview_up_to_date)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._thread is not None:
            QMessageBox.information(self, "Generation active", "Please wait for the current operation to finish.")
            event.ignore()
            return
        super().closeEvent(event)
