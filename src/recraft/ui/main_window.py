"""Minimal preview-first image-to-relief workspace."""

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QSplitter, QVBoxLayout, QWidget,
)

from recraft.core.diagnostics import diagnostic_log_path
from recraft.core.image_loader import ImageLoadError, load_image
from recraft.core.image_transform import FitMode, ImageTransformSettings, prepare_image
from recraft.relief.presets import RELIEF_PRESETS, ReliefSettings, ReliefStyle
from recraft.ui.collapsible import CollapsibleSection
from recraft.ui.image_view import ImageView
from recraft.ui.mesh_view import MeshView
from recraft.ui.relief_worker import ReliefWorker


class MainWindow(QMainWindow):
    """Convert one photograph into a positive printable relief plaque."""

    def __init__(self) -> None:
        super().__init__(); self.source_image: Image.Image | None = None; self.prepared_image: Image.Image | None = None; self.relief_result = None
        self._thread: QThread | None = None; self._worker: ReliefWorker | None = None; self.preview_up_to_date = False
        self.setWindowTitle("ReCraft — Printable Relief"); self.resize(1200, 720); self.setMinimumSize(900, 600)
        self._build_ui(); self._mark_stale(initial=True)

    def _build_ui(self) -> None:
        central = QWidget(); root = QVBoxLayout(central); root.setContentsMargins(8, 8, 8, 8); root.setSpacing(6)
        heading = QHBoxLayout(); title = QLabel("ReCraft Relief"); title.setStyleSheet("font-size:24px;font-weight:700")
        tagline = QLabel("One photograph. One printable positive relief."); tagline.setStyleSheet("color:#68717d")
        heading.addWidget(title); heading.addWidget(tagline); heading.addStretch(); root.addLayout(heading)

        workspace = QSplitter(Qt.Orientation.Horizontal); preview_splitter = QSplitter(Qt.Orientation.Horizontal)
        source_panel = QWidget(); source_layout = QVBoxLayout(source_panel); source_layout.setContentsMargins(0, 0, 0, 0)
        source_bar = QHBoxLayout(); source_bar.addWidget(QLabel("Source / crop")); source_bar.addStretch()
        source_fit = QPushButton("Fit view"); source_fit.clicked.connect(self._fit_source_view); source_bar.addWidget(source_fit)
        source_layout.addLayout(source_bar); self.source_view = ImageView("Open a photograph to begin", interactive=True); self.source_view.enable_view_navigation(True); source_layout.addWidget(self.source_view, 1)
        mesh_panel = QWidget(); mesh_layout = QVBoxLayout(mesh_panel); mesh_layout.setContentsMargins(0, 0, 0, 0)
        camera = QHBoxLayout(); camera.addWidget(QLabel("Positive relief preview")); camera.addStretch()
        for label, action in (("Fit", self._fit_mesh), ("Reset", self._reset_camera), ("Front", lambda: self.mesh_view.set_standard_view("Front")), ("Perspective", lambda: self.mesh_view.set_standard_view("Perspective"))):
            button = QPushButton(label); button.clicked.connect(action); camera.addWidget(button)
        self.orthographic = QCheckBox("Orthographic"); self.orthographic.toggled.connect(lambda checked: self.mesh_view.set_projection("orthographic" if checked else "perspective")); camera.addWidget(self.orthographic)
        mesh_layout.addLayout(camera); self.mesh_view = MeshView(); mesh_layout.addWidget(self.mesh_view, 1)
        preview_splitter.addWidget(source_panel); preview_splitter.addWidget(mesh_panel); preview_splitter.setSizes([430, 600]); preview_splitter.setStretchFactor(0, 2); preview_splitter.setStretchFactor(1, 3)

        controls = QWidget(); controls_layout = QVBoxLayout(controls); controls_layout.setContentsMargins(8, 4, 8, 4); controls_layout.setSpacing(7)
        self.open_button = QPushButton("Open Image"); self.open_button.clicked.connect(self._open_image); controls_layout.addWidget(self.open_button)
        form = QFormLayout(); form.setVerticalSpacing(6)
        self.framing_combo = QComboBox(); self.framing_combo.addItem("Fit full image", "fit"); self.framing_combo.addItem("Crop to 4:5 plaque", "crop"); self.framing_combo.currentIndexChanged.connect(self._framing_changed); form.addRow("Crop / fit", self.framing_combo)
        self.style_combo = QComboBox()
        for style in ReliefStyle: self.style_combo.addItem(style.value, style)
        self.style_combo.currentIndexChanged.connect(self._style_changed); form.addRow("Output style", self.style_combo)
        self.style_description = QLabel(RELIEF_PRESETS[ReliefStyle.PORTRAIT].description); self.style_description.setWordWrap(True); form.addRow(self.style_description)
        self.width_spin = QDoubleSpinBox(); self.width_spin.setRange(40, 500); self.width_spin.setValue(160); self.width_spin.setSuffix(" mm"); self.width_spin.valueChanged.connect(self._settings_changed); form.addRow("Physical width", self.width_spin)
        self.depth_spin = QDoubleSpinBox(); self.depth_spin.setRange(.5, 5); self.depth_spin.setValue(1.8); self.depth_spin.setSingleStep(.1); self.depth_spin.setSuffix(" mm"); self.depth_spin.valueChanged.connect(self._settings_changed); form.addRow("Relief depth", self.depth_spin)
        self.background_spin = QDoubleSpinBox(); self.background_spin.setRange(0, 1); self.background_spin.setValue(.65); self.background_spin.setSingleStep(.05); self.background_spin.valueChanged.connect(self._settings_changed); form.addRow("Background reduction", self.background_spin)
        self.subject_spin = QDoubleSpinBox(); self.subject_spin.setRange(0, 1); self.subject_spin.setValue(.65); self.subject_spin.setSingleStep(.05); self.subject_spin.valueChanged.connect(self._settings_changed); form.addRow("Subject emphasis", self.subject_spin)
        controls_layout.addLayout(form)
        self.generate_button = QPushButton("Generate Relief"); self.generate_button.setMinimumHeight(38); self.generate_button.setStyleSheet("font-weight:700"); self.generate_button.clicked.connect(self._generate); controls_layout.addWidget(self.generate_button)
        self.state_label = QLabel(); self.state_label.setWordWrap(True); controls_layout.addWidget(self.state_label)
        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.hide(); controls_layout.addWidget(self.progress)
        self.summary = QLabel("No relief generated."); self.summary.setWordWrap(True); controls_layout.addWidget(self.summary)
        export_row = QHBoxLayout(); self.stl_button = QPushButton("Export STL"); self.stl_button.clicked.connect(lambda: self._export("stl")); self.threemf_button = QPushButton("Export 3MF"); self.threemf_button.clicked.connect(lambda: self._export("3mf")); export_row.addWidget(self.stl_button); export_row.addWidget(self.threemf_button); controls_layout.addLayout(export_row)

        advanced = QWidget(); advanced_form = QFormLayout(advanced)
        self.preview_quality = QComboBox(); self.preview_quality.addItem("Fast", 110); self.preview_quality.addItem("Balanced", 150); self.preview_quality.addItem("Fine", 190); self.preview_quality.setCurrentIndex(1); self.preview_quality.currentIndexChanged.connect(self._settings_changed); advanced_form.addRow("Preview quality", self.preview_quality)
        self.export_quality = QComboBox(); self.export_quality.addItem("Standard", 220); self.export_quality.addItem("Fine", 260); self.export_quality.addItem("Maximum", 320); self.export_quality.setCurrentIndex(1); advanced_form.addRow("Export quality", self.export_quality)
        self.contrast_spin = QDoubleSpinBox(); self.contrast_spin.setRange(.5, 2); self.contrast_spin.setValue(1); self.contrast_spin.setSingleStep(.1); self.contrast_spin.valueChanged.connect(self._settings_changed); advanced_form.addRow("Relief contrast", self.contrast_spin)
        self.base_spin = QDoubleSpinBox(); self.base_spin.setRange(.8, 8); self.base_spin.setValue(1.5); self.base_spin.setSuffix(" mm"); self.base_spin.valueChanged.connect(self._settings_changed); advanced_form.addRow("Base thickness", self.base_spin)
        self.minimum_feature_spin = QDoubleSpinBox(); self.minimum_feature_spin.setRange(.6, 3); self.minimum_feature_spin.setValue(.8); self.minimum_feature_spin.setSuffix(" mm"); self.minimum_feature_spin.valueChanged.connect(self._settings_changed); advanced_form.addRow("Minimum feature", self.minimum_feature_spin)
        self.nozzle_spin = QDoubleSpinBox(); self.nozzle_spin.setRange(.2, 1.2); self.nozzle_spin.setValue(.4); self.nozzle_spin.setSuffix(" mm"); self.nozzle_spin.valueChanged.connect(self._settings_changed); advanced_form.addRow("Nozzle", self.nozzle_spin)
        self.layer_spin = QDoubleSpinBox(); self.layer_spin.setRange(.05, .6); self.layer_spin.setValue(.2); self.layer_spin.setSuffix(" mm"); self.layer_spin.valueChanged.connect(self._settings_changed); advanced_form.addRow("Layer height", self.layer_spin)
        self.invert_check = QCheckBox("Invert relief (advanced)"); self.invert_check.toggled.connect(self._settings_changed); advanced_form.addRow(self.invert_check)
        self._conflicting_controls = (self.framing_combo, self.style_combo, self.width_spin, self.depth_spin, self.background_spin, self.subject_spin, self.preview_quality, self.export_quality, self.contrast_spin, self.base_spin, self.minimum_feature_spin, self.nozzle_spin, self.layer_spin, self.invert_check)
        self.advanced_section = CollapsibleSection("Advanced", advanced, expanded=False); controls_layout.addWidget(self.advanced_section); controls_layout.addStretch()
        controls_scroll = QScrollArea(); controls_scroll.setWidgetResizable(True); controls_scroll.setWidget(controls); controls_scroll.setMinimumWidth(280); controls_scroll.setMaximumWidth(360)
        workspace.addWidget(preview_splitter); workspace.addWidget(controls_scroll); workspace.setSizes([900, 300]); workspace.setStretchFactor(0, 1); root.addWidget(workspace, 1)
        self.setCentralWidget(central); self.statusBar().showMessage("Open a photograph to create a printable relief")

    def _fit_source_view(self) -> None: self.source_view.fit_to_view()
    def _fit_mesh(self) -> None: self.mesh_view.fit_mesh()
    def _reset_camera(self) -> None: self.mesh_view.reset_camera()

    def _open_image(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Open photograph", "", "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)")
        if not filename: return
        try: self.source_image = load_image(filename)
        except ImageLoadError as exc: QMessageBox.critical(self, "Could not open image", str(exc)); return
        self._refresh_prepared(); self.relief_result = None; self.mesh_view.set_mesh(None); self._mark_stale(); self.statusBar().showMessage(f"Loaded {Path(filename).name}")

    def _preparation_settings(self) -> ImageTransformSettings:
        if self.source_image is None: return ImageTransformSettings()
        if self.framing_combo.currentData() == "crop": width, height, ratio, mode = 960, 1200, (4, 5), FitMode.FILL
        else:
            scale = min(1.0, 1200 / max(self.source_image.size)); width, height = max(1, round(self.source_image.width * scale)), max(1, round(self.source_image.height * scale)); ratio, mode = self.source_image.size, FitMode.FIT
        return ImageTransformSettings(output_width=width, output_height=height, aspect_ratio=ratio, fit_mode=mode)

    def _refresh_prepared(self) -> None:
        if self.source_image is None: return
        self.prepared_image = prepare_image(self.source_image, self._preparation_settings()); self.source_view.set_image(self.prepared_image)

    def _relief_settings(self) -> ReliefSettings:
        return ReliefSettings(style=self.style_combo.currentData(), physical_width_mm=self.width_spin.value(), relief_depth_mm=self.depth_spin.value(), base_thickness_mm=self.base_spin.value(), background_strength=self.background_spin.value(), subject_emphasis=self.subject_spin.value(), relief_contrast=self.contrast_spin.value(), minimum_feature_mm=self.minimum_feature_spin.value(), invert=self.invert_check.isChecked(), preview_resolution=int(self.preview_quality.currentData()), export_resolution=int(self.export_quality.currentData()), nozzle_diameter_mm=self.nozzle_spin.value(), layer_height_mm=self.layer_spin.value()).validated()

    def _framing_changed(self) -> None: self._refresh_prepared(); self._mark_stale()
    def _style_changed(self) -> None:
        style = self.style_combo.currentData(); self.style_description.setText(RELIEF_PRESETS[style].description); self._mark_stale()
    def _settings_changed(self) -> None: self._mark_stale()

    def _mark_stale(self, initial: bool = False) -> None:
        self.preview_up_to_date = False; self.state_label.setText("Open an image" if initial or self.source_image is None else "Settings changed — regenerate")
        self.state_label.setStyleSheet("color:#9A6700"); self.generate_button.setEnabled(self.source_image is not None and self._thread is None); self.stl_button.setEnabled(False); self.threemf_button.setEnabled(False)

    def _generate(self) -> None:
        if self.prepared_image is None: QMessageBox.information(self, "No image", "Open an image first."); return
        try: settings = self._relief_settings()
        except ValueError as exc: QMessageBox.warning(self, "Check print settings", str(exc)); return
        self._start_worker(ReliefWorker(self.prepared_image, settings))

    def _export(self, format_name: str) -> None:
        if not self.preview_up_to_date or self.prepared_image is None: return
        suffix = f".{format_name}"; label = "STL mesh (*.stl)" if format_name == "stl" else "3MF model (*.3mf)"
        filename, _ = QFileDialog.getSaveFileName(self, f"Export {format_name.upper()}", f"recraft-relief{suffix}", label)
        if not filename: return
        if not filename.lower().endswith(suffix): filename += suffix
        try: settings = self._relief_settings()
        except ValueError as exc: QMessageBox.warning(self, "Check print settings", str(exc)); return
        self._start_worker(ReliefWorker(self.prepared_image, settings, format_name, filename))

    def _start_worker(self, worker: ReliefWorker) -> None:
        if self._thread is not None: return
        thread = QThread(self); worker.moveToThread(thread); thread.started.connect(worker.run); worker.stage_changed.connect(self._stage_changed); worker.preview_ready.connect(self._preview_ready); worker.export_ready.connect(self._export_ready); worker.failed.connect(self._generation_failed); worker.finished.connect(thread.quit); worker.finished.connect(worker.deleteLater); thread.finished.connect(self._worker_finished); thread.finished.connect(thread.deleteLater)
        self._thread = thread; self._worker = worker; self.open_button.setEnabled(False); self.generate_button.setEnabled(False); self.stl_button.setEnabled(False); self.threemf_button.setEnabled(False)
        for control in self._conflicting_controls: control.setEnabled(False)
        self.progress.setValue(0); self.progress.show(); self.state_label.setText("Generating"); self.state_label.setStyleSheet("color:#0969DA"); thread.start()

    def _stage_changed(self, stage: str, progress: int) -> None: self.state_label.setText(f"Generating — {stage}"); self.progress.setValue(progress); self.statusBar().showMessage(stage)

    def _preview_ready(self, prepared: object, height_map: object, result: object) -> None:
        self.relief_result = result; self.mesh_view.set_mesh(result); self.preview_up_to_date = True; self.state_label.setText("Preview up to date"); self.state_label.setStyleSheet("color:#1A7F37")
        self.summary.setText(f"{result.width_mm:.1f} × {result.height_mm:.1f} mm\nBase {self.base_spin.value():.1f} mm + relief {self.depth_spin.value():.1f} mm\nMinimum feature {self.minimum_feature_spin.value():.1f} mm\n{self.nozzle_spin.value():.1f} mm nozzle / {self.layer_spin.value():.2f} mm layers\n{result.triangle_count:,} preview triangles\nWatertight: yes")

    def _export_ready(self, path: str, height_map: object, result: object) -> None:
        self.summary.setText(f"Exported {Path(path).name}\n{result.width_mm:.1f} × {result.height_mm:.1f} mm\n{result.triangle_count:,} triangles\nWatertight: yes")
        self.statusBar().showMessage(f"Saved {Path(path).name}")

    def _generation_failed(self, message: str) -> None:
        self.state_label.setText("Generation failed — previous preview preserved"); self.state_label.setStyleSheet("color:#CF222E"); QMessageBox.critical(self, "Relief generation failed safely", f"{message}\n\nDiagnostic log: {diagnostic_log_path()}")

    def _worker_finished(self) -> None:
        self._thread = None; self._worker = None; self.progress.hide(); self.open_button.setEnabled(True)
        for control in self._conflicting_controls: control.setEnabled(True)
        self.generate_button.setEnabled(self.source_image is not None); self.stl_button.setEnabled(self.preview_up_to_date); self.threemf_button.setEnabled(self.preview_up_to_date)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._thread is not None: QMessageBox.information(self, "Generation active", "Please wait for the current relief operation to finish."); event.ignore(); return
        super().closeEvent(event)
