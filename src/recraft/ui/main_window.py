"""Main ReCraft desktop window."""

from dataclasses import replace
import copy
from pathlib import Path

from PIL import Image
import numpy as np
from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QCloseEvent, QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QProgressBar, QSpinBox, QStackedWidget, QVBoxLayout, QWidget, QColorDialog,
    QSplitter, QScrollArea, QTabWidget, QPlainTextEdit,
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
from recraft.exporters.contour_mesh import ContourMeshSettings, ReliefColours, render_relief_preview
from recraft.core.contour_workflow import ContourStage, ContourWorkflowState
from recraft.core.contour_presets import ContourPresetName, PRESETS, PresetState
from recraft.core.preview_settings import PreviewQuality, PreviewSettings
from recraft.core.print_profiles import PROFILES, PrintProfileName, validate_printability
from recraft.engine.focus_features import FocusAction, interpret_focus_description, suggest_focus_features
from recraft.ui.mesh_view import MeshView
from recraft.ui.collapsible import CollapsibleSection
from recraft.styles.contour_geometry import contour_height_image
from recraft.core.diagnostics import PipelineMetrics, diagnostic_log_path


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
        self.workflow_state = ContourWorkflowState()
        self.cached_contour_result = None
        self.cached_mesh_result = None
        self.preset_state = PresetState()
        self.focus_features = []
        self.current_analysis = None
        self.print_profile = PROFILES[PrintProfileName.BAMBU_H2C]
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
        heading.addWidget(self.open_button)
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

        self.style_box = QGroupBox("3. Apply Art Style")
        style_layout = QHBoxLayout(self.style_box)
        self.style_combo = QComboBox()
        for style in self.registry: self.style_combo.addItem(style.display_name, style.identifier)
        self.style_combo.currentIndexChanged.connect(self._rebuild_parameters)
        self.debug_combo = QComboBox()
        self.debug_combo.addItem("Artwork", None)
        for name in ("Automatic Importance", "Combined Importance", "User Add Mask", "User Reduce Mask", "Background Suppression", "Colour Selection Preview", "Region Selection Preview", "Raw Contour Paths", "Filtered Contour Paths", "Contour Importance View", "Contour Height View", "Edge Map", "Face Mask", "Background Mask", "Saliency", "Colour Clusters", "Texture", "Subject Mask"):
            self.debug_combo.addItem(name, name)
        self.debug_combo.setToolTip("Developer view of reusable ReCraft Engine analysis maps")
        self.debug_combo.hide(); self.developer_button = QPushButton("Developer Diagnostics"); self.developer_button.setCheckable(True); self.developer_button.toggled.connect(self.debug_combo.setVisible)
        heading.insertWidget(heading.count() - 1, self.developer_button); heading.insertWidget(heading.count() - 1, self.debug_combo)
        self.description = QLabel(); self.parameter_container = QWidget(); self.parameter_form = QFormLayout(self.parameter_container)
        self.advanced_button = QPushButton("Advanced"); self.advanced_button.setCheckable(True); self.advanced_button.toggled.connect(self._toggle_advanced)
        self.generate_button = QPushButton("Generate Preview"); self.generate_button.clicked.connect(self._generate)
        style_layout.addWidget(QLabel("Style")); style_layout.addWidget(self.style_combo); style_layout.addWidget(self.description, 1); style_layout.addWidget(self.parameter_container); style_layout.addWidget(self.advanced_button); style_layout.addWidget(self.generate_button)

        self.mesh_box = QGroupBox("4. Build Relief")
        mesh_layout = QGridLayout(self.mesh_box)
        self.mesh_width = QDoubleSpinBox(); self.mesh_width.setRange(20, 1000); self.mesh_width.setValue(150); self.mesh_width.setSuffix(" mm")
        self.base_thickness = QDoubleSpinBox(); self.base_thickness.setRange(0.4, 20); self.base_thickness.setValue(2); self.base_thickness.setSuffix(" mm")
        self.minimum_height = QDoubleSpinBox(); self.minimum_height.setRange(0.1, 20); self.minimum_height.setValue(.4); self.minimum_height.setSuffix(" mm")
        self.maximum_height = QDoubleSpinBox(); self.maximum_height.setRange(0.1, 20); self.maximum_height.setValue(1.8); self.maximum_height.setSuffix(" mm")
        self.ridge_width = QDoubleSpinBox(); self.ridge_width.setRange(0.8, 20); self.ridge_width.setValue(1.2); self.ridge_width.setSuffix(" mm")
        self.border_width = QDoubleSpinBox(); self.border_width.setRange(0, 50); self.border_width.setValue(3); self.border_width.setSuffix(" mm")
        self.relief_strength = QDoubleSpinBox(); self.relief_strength.setRange(.1, 4); self.relief_strength.setValue(1); self.relief_strength.setSingleStep(.1)
        self.height_smoothing = QDoubleSpinBox(); self.height_smoothing.setRange(0, 3); self.height_smoothing.setValue(.6); self.height_smoothing.setSingleStep(.1)
        self.background_relief = QDoubleSpinBox(); self.background_relief.setRange(0, 1); self.background_relief.setValue(.55); self.background_relief.setSingleStep(.05)
        self.mesh_resolution = QSpinBox(); self.mesh_resolution.setRange(40, 500); self.mesh_resolution.setValue(160)
        self.minimum_feature = QDoubleSpinBox(); self.minimum_feature.setRange(.2, 10); self.minimum_feature.setValue(.8); self.minimum_feature.setSuffix(" mm")
        self.uniform_height = QCheckBox("Uniform-height comparison mode")
        self.orientation_marker = QCheckBox("Developer orientation arrow")
        self.physical_height_label = QLabel("Calculated height: 75.0 mm")
        controls = (("Physical width", self.mesh_width), ("Base thickness", self.base_thickness), ("Minimum contour height", self.minimum_height), ("Maximum contour height", self.maximum_height), ("Ridge width", self.ridge_width), ("Border", self.border_width), ("Relief strength", self.relief_strength), ("Height smoothing", self.height_smoothing), ("Background relief reduction", self.background_relief), ("Curve sampling quality", self.mesh_resolution), ("Minimum printable width", self.minimum_feature))
        for index, (label, widget) in enumerate(controls):
            row, column = divmod(index, 3); mesh_layout.addWidget(QLabel(label), row, column * 2); mesh_layout.addWidget(widget, row, column * 2 + 1)
        mesh_layout.addWidget(self.physical_height_label, 4, 0, 1, 2); mesh_layout.addWidget(self.uniform_height, 4, 2, 1, 2); mesh_layout.addWidget(self.orientation_marker, 4, 4, 1, 2)
        for widget in (self.mesh_width, self.base_thickness, self.minimum_height, self.maximum_height, self.ridge_width, self.border_width, self.relief_strength, self.height_smoothing, self.background_relief, self.mesh_resolution, self.minimum_feature): widget.valueChanged.connect(self._relief_changed)
        self.uniform_height.toggled.connect(self._relief_changed); self.orientation_marker.toggled.connect(self._relief_changed)

        self.preview_page = QWidget(); preview_root = QVBoxLayout(self.preview_page); panels = QHBoxLayout()
        left = QVBoxLayout(); source_bar = QHBoxLayout(); self.prepared_label = QLabel("Source and analysis — wheel to zoom, drag to pan"); source_bar.addWidget(self.prepared_label)
        self.source_view_mode = QComboBox(); self.source_view_mode.addItems(("Prepared image", "Suggested focus features", "Importance overlay", "Background suppression", "Relief-height map")); self.source_view_mode.currentIndexChanged.connect(self._refresh_source_mode); source_bar.addWidget(self.source_view_mode)
        left.addLayout(source_bar); self.prepared_view = ImageView("Open an image to begin", interactive=True); self.prepared_view.enable_view_navigation(True); left.addWidget(self.prepared_view)
        self.prepared_view.zoom_requested.connect(self._gesture_zoom); self.prepared_view.pan_requested.connect(self._gesture_pan)
        self.prepared_view.image_painted.connect(self._paint_importance); self.prepared_view.image_clicked.connect(self._selection_clicked)
        right = QVBoxLayout(); contour_bar = QHBoxLayout(); contour_bar.addWidget(QLabel("2D Contour")); contour_bar.addStretch(); self.contour_fit = QPushButton("Fit"); self.contour_fit.clicked.connect(lambda: self.output_view.fit_to_view()); contour_bar.addWidget(self.contour_fit); right.addLayout(contour_bar); self.output_view = ImageView("Generate a style preview", interactive=True); self.output_view.enable_view_navigation(True); right.addWidget(self.output_view)
        self.mesh_view = MeshView()
        relief = QVBoxLayout(); mesh_toolbar = QHBoxLayout(); mesh_toolbar.addWidget(QLabel("Actual 3D relief"))
        for view_name in ("Perspective", "Front", "Back", "Left", "Right", "Top"):
            button = QPushButton(view_name); button.clicked.connect(lambda checked=False, name=view_name: self.mesh_view.set_standard_view(name)); mesh_toolbar.addWidget(button)
        reset_camera = QPushButton("Reset"); reset_camera.clicked.connect(self.mesh_view.reset_camera); mesh_toolbar.addWidget(reset_camera)
        fit_camera = QPushButton("Fit"); fit_camera.clicked.connect(self.mesh_view.fit_mesh); mesh_toolbar.addWidget(fit_camera)
        self.projection_combo = QComboBox(); self.projection_combo.addItems(("perspective", "orthographic")); self.projection_combo.currentTextChanged.connect(self.mesh_view.set_projection); mesh_toolbar.addWidget(self.projection_combo)
        self.wireframe_check = QCheckBox("Edges"); self.wireframe_check.toggled.connect(lambda checked: (setattr(self.mesh_view, "wireframe", checked), self.mesh_view.update())); mesh_toolbar.addWidget(self.wireframe_check)
        relief.addLayout(mesh_toolbar); relief.addWidget(self.mesh_view)
        panels.addLayout(left, 1); panels.addLayout(right, 1); panels.addLayout(relief, 1); preview_root.addLayout(panels, 1)
        material_row = QHBoxLayout(); self.base_colour_button = QPushButton(); self.contour_colour_button = QPushButton(); self.reset_colours_button = QPushButton("Reset colours")
        self.base_colour_button.clicked.connect(lambda: self._choose_colour("base")); self.contour_colour_button.clicked.connect(lambda: self._choose_colour("contour")); self.reset_colours_button.clicked.connect(self._reset_colours)
        material_row.addWidget(QLabel("Base Colour")); material_row.addWidget(self.base_colour_button); material_row.addWidget(QLabel("Contour Colour")); material_row.addWidget(self.contour_colour_button); material_row.addWidget(self.reset_colours_button)
        self.mesh_summary = QLabel("Build a relief to see dimensions and mesh validation."); material_row.addWidget(self.mesh_summary, 1)
        self.build_relief_button = QPushButton("Build Relief Preview"); self.build_relief_button.clicked.connect(self._build_relief_preview)
        self.stl_button = QPushButton("Export STL (geometry only)"); self.stl_button.clicked.connect(lambda: self._save_mesh("stl"))
        self.threemf_button = QPushButton("Export Coloured 3MF"); self.threemf_button.clicked.connect(lambda: self._save_mesh("3mf"))
        material_row.addWidget(self.build_relief_button); material_row.addWidget(self.save_button); material_row.addWidget(self.stl_button); material_row.addWidget(self.threemf_button); preview_root.addLayout(material_row)
        self.stl_note = QLabel("STL stores geometry only and does not contain Base or Contour colours. Use 3MF for colour/material assignments."); self.stl_note.setWordWrap(True); preview_root.addWidget(self.stl_note)

        self.preset_combo = QComboBox()
        for preset_name in ContourPresetName: self.preset_combo.addItem(preset_name.value, preset_name)
        self.preset_combo.setCurrentIndex(self.preset_combo.findData(ContourPresetName.STANDARD)); self.preset_combo.currentIndexChanged.connect(self._preset_changed)
        self.preset_description = QLabel(PRESETS[ContourPresetName.STANDARD].description); self.preset_description.setWordWrap(True)
        self.preset_modified = QLabel("Standard defaults")
        reset_preset = QPushButton("Reset to preset"); reset_preset.clicked.connect(self._reset_to_preset)
        preset_panel = QWidget(); preset_layout = QFormLayout(preset_panel); preset_layout.addRow("Creative preset", self.preset_combo); preset_layout.addRow(self.preset_description); preset_layout.addRow(self.preset_modified, reset_preset)

        self.analysis_summary = QLabel("Open an image to see editable analysis suggestions."); self.analysis_summary.setWordWrap(True)
        self.focus_cards = QWidget(); self.focus_cards_layout = QVBoxLayout(self.focus_cards); self.focus_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.focus_description = QPlainTextEdit(); self.focus_description.setMaximumHeight(62); self.focus_description.setPlaceholderText("Example: focus on faces and silhouettes; simplify the background")
        apply_focus = QPushButton("Apply description"); apply_focus.clicked.connect(self._apply_focus_description)
        reset_focus = QPushButton("Reset suggestions"); reset_focus.clicked.connect(self._reset_focus_suggestions)
        focus_panel = QWidget(); focus_layout = QVBoxLayout(focus_panel); focus_layout.addWidget(self.analysis_summary); focus_layout.addWidget(self.focus_cards); focus_layout.addWidget(self.focus_description); focus_buttons = QHBoxLayout(); focus_buttons.addWidget(apply_focus); focus_buttons.addWidget(reset_focus); focus_layout.addLayout(focus_buttons); focus_layout.addWidget(self.importance_box)

        self.profile_combo = QComboBox()
        for profile_name in PrintProfileName: self.profile_combo.addItem(profile_name.value, profile_name)
        self.profile_combo.currentIndexChanged.connect(self._profile_changed)
        self.nozzle_spin = QDoubleSpinBox(); self.nozzle_spin.setRange(.2, 1.2); self.nozzle_spin.setValue(.4); self.nozzle_spin.setSuffix(" mm"); self.nozzle_spin.valueChanged.connect(self._print_settings_changed)
        self.layer_spin = QDoubleSpinBox(); self.layer_spin.setRange(.05, .6); self.layer_spin.setValue(.2); self.layer_spin.setSuffix(" mm"); self.layer_spin.valueChanged.connect(self._print_settings_changed)
        self.preview_quality = QComboBox(); self.preview_quality.addItems([quality.value for quality in PreviewQuality]); self.preview_quality.setCurrentText(PreviewQuality.BALANCED.value)
        print_panel = QWidget(); print_layout = QFormLayout(print_panel); print_layout.addRow("Printer profile", self.profile_combo); print_layout.addRow("Nozzle", self.nozzle_spin); print_layout.addRow("Layer height", self.layer_spin); print_layout.addRow("Preview quality", self.preview_quality)
        self.print_warnings = QLabel("Printability checks appear after the mesh is built."); self.print_warnings.setWordWrap(True); print_layout.addRow(self.print_warnings)

        controls_content = QWidget(); controls_layout = QVBoxLayout(controls_content); controls_layout.setContentsMargins(4, 4, 4, 4)
        for section_title, section_widget, expanded in (("Creative style", preset_panel, True), ("Image interpretation & focus", focus_panel, True), ("Image preparation", self.setup_box, False), ("Contour controls", self.style_box, True), ("Relief and print setup", self.mesh_box, False), ("Printer profile", print_panel, True)):
            controls_layout.addWidget(CollapsibleSection(section_title, section_widget, expanded=expanded))
        controls_layout.addStretch()
        controls_scroll = QScrollArea(); controls_scroll.setWidgetResizable(True); controls_scroll.setWidget(controls_content); controls_scroll.setMinimumWidth(370)
        workspace = QSplitter(Qt.Orientation.Horizontal); workspace.addWidget(self.preview_page); workspace.addWidget(controls_scroll); workspace.setSizes([880, 370]); workspace.setStretchFactor(0, 1); root.addWidget(workspace, 1)
        collapse_controls = QPushButton("Collapse controls"); collapse_controls.setCheckable(True); collapse_controls.toggled.connect(lambda collapsed: controls_scroll.setVisible(not collapsed)); heading.insertWidget(heading.count() - 1, collapse_controls)
        self._update_colour_buttons()
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
        self._advanced_widgets = []
        for parameter in style.parameters:
            if any(isinstance(value, float) for value in (parameter.default, parameter.minimum, parameter.maximum, parameter.step)):
                widget: QSpinBox | QDoubleSpinBox = QDoubleSpinBox(); widget.setDecimals(2)
            else: widget = QSpinBox()
            widget.setRange(parameter.minimum, parameter.maximum); widget.setSingleStep(parameter.step); widget.setValue(parameter.default)
            widget.valueChanged.connect(self._contour_controls_changed)
            self.parameter_widgets[parameter.key] = widget; self.parameter_form.addRow(parameter.label, widget)
            if parameter.key in ("major_only", "invert"):
                label = self.parameter_form.labelForField(widget); self._advanced_widgets.append((label, widget)); label.hide(); widget.hide()
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
            self.current_analysis = None
            self._sync_setup_controls(); self._refresh_prepared(); self._invalidate_output(clear=True)
            self.statusBar().showMessage(f"Loaded {Path(filename).name} at {self.source_image.width} × {self.source_image.height}")
            self._generate()
        except ImageLoadError as exc: QMessageBox.critical(self, "Could not open image", str(exc))

    def _setup_changed(self) -> None:
        if self._updating_setup: return
        try: self.transform_settings = self._settings_from_controls(); self.workflow_state.invalidate_preparation(); self.current_analysis = None; self.cached_contour_result = self.cached_mesh_result = None; self._refresh_prepared(); self._invalidate_output()
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
        self.transform_settings = replace(self._settings_from_controls(), rotation_quarters=self.transform_settings.rotation_quarters + turns); self.workflow_state.invalidate_preparation(); self.current_analysis = None; self.cached_contour_result = self.cached_mesh_result = None; self._refresh_prepared(); self._invalidate_output()

    def _flip_horizontal(self) -> None:
        self.transform_settings = replace(self._settings_from_controls(), flip_horizontal=not self.transform_settings.flip_horizontal); self.workflow_state.invalidate_preparation(); self.current_analysis = None; self.cached_contour_result = self.cached_mesh_result = None; self._refresh_prepared(); self._invalidate_output()

    def _flip_vertical(self) -> None:
        self.transform_settings = replace(self._settings_from_controls(), flip_vertical=not self.transform_settings.flip_vertical); self.workflow_state.invalidate_preparation(); self.current_analysis = None; self.cached_contour_result = self.cached_mesh_result = None; self._refresh_prepared(); self._invalidate_output()

    def _reset_setup(self) -> None:
        self.transform_settings = self.transform_settings.reset(self.source_image.size if self.source_image else None); self.workflow_state.invalidate_preparation(); self.current_analysis = None; self.cached_contour_result = self.cached_mesh_result = None; self._sync_setup_controls(); self._refresh_prepared(); self._invalidate_output()

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

    def _invalidate_output(self, clear: bool = False) -> None:
        """Mark derived output stale while preserving the last valid previews."""
        if clear:
            self.output_image = None; self.output_view.set_image(None)
            self.cached_mesh_result = None; self.mesh_view.set_mesh(None)
        self.save_button.setEnabled(self.source_image is not None)

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
            self.current_analysis,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.preview_ready.connect(self._preview_finished)
        worker.geometry_ready.connect(self._contour_geometry_ready)
        worker.analysis_ready.connect(self._analysis_finished)
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
        QMessageBox.critical(self, "Rendering failed safely", f"{message}\n\nThe previous valid preview has been preserved. Diagnostic log:\n{diagnostic_log_path()}")
        self.statusBar().showMessage("Rendering failed safely — previous preview preserved")

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
        self.workflow_state.invalidate_importance(); self.cached_contour_result = self.cached_mesh_result = None
        self._invalidate_output()

    def _clear_importance(self) -> None:
        if self.user_importance is not None: self.user_importance.clear()
        self.workflow_state.invalidate_importance(); self.cached_contour_result = self.cached_mesh_result = None; self._refresh_prepared(); self._invalidate_output()

    def _paint_importance(self, x: float, y: float) -> None:
        if self.source_image is None or self.user_importance is None or self.prepared_preview is None: return
        mapped = canvas_to_source((x, y), self.source_image.size, self.transform_settings, self.prepared_preview.size)
        if mapped is None: return
        mode = self.brush_mode.currentData()
        try: mode = BrushMode(mode)
        except ValueError: return
        radius = self.brush_size.value() / max(self.prepared_preview.size)
        self.user_importance.paint_source(*mapped, radius, self.brush_strength.value(), mode)
        self.workflow_state.invalidate_importance(); self.cached_contour_result = self.cached_mesh_result = None
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
        self.workflow_state.invalidate_importance(); self.cached_contour_result = self.cached_mesh_result = None
        self._cancel_selection(); self._invalidate_output()

    def _cancel_selection(self) -> None:
        if self.user_importance is not None:
            self.user_importance.colour_preview = None; self.user_importance.region_preview = None
        self._selection_kind = None; self._selection_point = None; self._importance_mode_changed(); self._refresh_prepared()

    def _mesh_settings(self) -> ContourMeshSettings:
        """Build validated relief settings from the guided controls."""
        return ContourMeshSettings(
            physical_width=self.mesh_width.value(), base_thickness=self.base_thickness.value(),
            minimum_contour_height=self.minimum_height.value(), maximum_contour_height=self.maximum_height.value(),
            ridge_width=self.ridge_width.value(), border_width=self.border_width.value(), resolution=self.mesh_resolution.value(),
            minimum_feature_width=self.minimum_feature.value(), relief_strength=self.relief_strength.value(),
            height_smoothing=self.height_smoothing.value(), background_relief_reduction=self.background_relief.value(),
            uniform_height=self.uniform_height.isChecked(), orientation_marker=self.orientation_marker.isChecked(),
            minimum_ridge_width=self.minimum_feature.value(), maximum_ridge_width=max(self.minimum_feature.value(), self.ridge_width.value() * 1.8),
            width_variation_strength=float(self.parameter_widgets.get("width_variation").value()) if "width_variation" in self.parameter_widgets else .5,
            uniform_width=bool(self.parameter_widgets.get("uniform_width").value()) if "uniform_width" in self.parameter_widgets else False,
        ).validated()

    def _build_relief_preview(self) -> None:
        self._start_mesh_job(None, "preview")

    def _save_mesh(self, export_format: str) -> None:
        if self.source_image is None: return
        extension = export_format.lower(); label = "3MF model (*.3mf)" if extension == "3mf" else "STL mesh (*.stl)"
        filename, _ = QFileDialog.getSaveFileName(self, f"Save Contour {extension.upper()}", f"recraft-contour.{extension}", label)
        if not filename: return
        if not filename.lower().endswith(f".{extension}"): filename += f".{extension}"
        self._start_mesh_job(filename, extension)

    def _start_mesh_job(self, path: str | None, export_format: str) -> None:
        if self.source_image is None or self._render_thread is not None: return
        try: settings = self._mesh_settings()
        except ValueError as exc: QMessageBox.warning(self, "Invalid relief settings", str(exc)); return
        if export_format == "preview":
            quality = PreviewSettings(PreviewQuality(self.preview_quality.currentText()))
            settings = replace(settings, resolution=max(40, round(settings.resolution * quality.mesh_resolution_scale)))
        thread = QThread(self); worker = MeshWorker(
            self.source_image, self._settings_from_controls(), copy.deepcopy(self.user_importance), self._style_parameters(),
            settings, path, self.workflow_state.colours, export_format, self.cached_contour_result, self.current_analysis, self.preset_state.selected.value,
        )
        worker.moveToThread(thread); thread.started.connect(worker.run); worker.exported.connect(self._mesh_exported)
        worker.geometry_ready.connect(self._contour_geometry_ready); worker.mesh_ready.connect(self._mesh_geometry_ready)
        worker.metrics_ready.connect(self._mesh_metrics_ready); worker.failed.connect(self._render_failed); worker.finished.connect(thread.quit); worker.finished.connect(worker.deleteLater); thread.finished.connect(self._render_cleanup); thread.finished.connect(thread.deleteLater)
        self._render_thread = thread; self._render_worker = worker; self._set_rendering(True); self.statusBar().showMessage("Building variable-height Contour relief…"); thread.start()

    def _mesh_exported(self, path: str, width: float, height: float, vertices: int, faces: int, watertight: bool) -> None:
        summary = f"Saved {Path(path).name}\nDimensions: {width:.1f} × {height:.1f} mm\nVertices: {vertices:,}\nFaces: {faces:,}\nWatertight: {'yes' if watertight else 'no'}"
        self.statusBar().showMessage(summary.replace("\n", " — ")); QMessageBox.information(self, "Contour STL exported", summary)

    def _mesh_geometry_ready(self, result: object) -> None:
        self.cached_mesh_result = result; self.workflow_state.mesh_valid = True
        self.mesh_view.set_mesh(result, self.workflow_state.colours)
        self.mesh_summary.setText(
            f"{result.width_mm:.1f} × {result.height_mm:.1f} mm | {len(result.mesh.vertices):,} vertices | "
            f"{len(result.mesh.faces):,} faces | Watertight: {'yes' if result.watertight else 'no'} | "
            f"Relief: {result.ridge_height_range[0]:.2f}–{result.ridge_height_range[1]:.2f} mm"
        )
        profile = self.print_profile.customised(nozzle_diameter=self.nozzle_spin.value(), layer_height=self.layer_spin.value())
        warnings = validate_printability(profile, minimum_width=self.minimum_feature.value(), height_range=result.ridge_height_range, base_thickness=self.base_thickness.value(), mesh_resolution=self.mesh_resolution.value(), triangle_count=len(result.mesh.faces), physical_width=self.mesh_width.value())
        self.print_warnings.setText("No printability warnings." if not warnings else "\n".join(f"• {warning}" for warning in warnings))

    def _mesh_metrics_ready(self, metrics: PipelineMetrics) -> None:
        """Show stage timings and bounded-geometry diagnostics."""
        timings = ", ".join(f"{name} {seconds:.2f}s" for name, seconds in metrics.stage_seconds.items())
        self.mesh_summary.setText(self.mesh_summary.text() + f" | {timings} | estimated memory {metrics.estimated_mesh_memory_mb:.1f} MB")
        if metrics.warnings: self.print_warnings.setText("\n".join(f"• {warning}" for warning in metrics.warnings))

    def _contour_geometry_ready(self, result: object) -> None:
        self.cached_contour_result = result; self.workflow_state.contour_valid = True; self.workflow_state.analysis_valid = True

    def _contour_controls_changed(self) -> None:
        self.workflow_state.invalidate_contours(); self.cached_contour_result = self.cached_mesh_result = None

    def _relief_changed(self) -> None:
        self.workflow_state.invalidate_relief(); self.cached_mesh_result = None
        if hasattr(self, "physical_height_label"):
            ratio = self.width_spin.value() / max(self.height_spin.value(), 1)
            self.physical_height_label.setText(f"Calculated height: {self.mesh_width.value() / ratio:.1f} mm")

    def _toggle_advanced(self, visible: bool) -> None:
        self.workflow_state.advanced_expanded = visible
        for label, widget in getattr(self, "_advanced_widgets", []): label.setVisible(visible); widget.setVisible(visible)

    def _next_stage(self) -> None:
        self.workflow_state.next(); self._sync_workflow_stage()

    def _previous_stage(self) -> None:
        self.workflow_state.back(); self._sync_workflow_stage()

    def _sync_workflow_stage(self) -> None:
        names = ("Prepare Image", "Choose Subject Importance", "Design Contours", "Build Relief", "Preview and Export")
        index = int(self.workflow_state.stage); self.workflow_stack.setCurrentIndex(index)
        self.stage_label.setText(f"Stage {index + 1} of 5 — {names[index]}")
        self.back_button.setEnabled(index > 0); self.next_button.setEnabled(index < 4)

    def _choose_colour(self, target: str) -> None:
        current = self.workflow_state.colours.base if target == "base" else self.workflow_state.colours.contour
        chosen = QColorDialog.getColor(QColor(current), self, f"Choose {target} colour")
        if not chosen.isValid(): return
        colours = ReliefColours(chosen.name().upper(), self.workflow_state.colours.contour) if target == "base" else ReliefColours(self.workflow_state.colours.base, chosen.name().upper())
        self.workflow_state.set_colours(colours); self._update_colour_buttons()
        self.mesh_view.set_colours(colours)

    def _reset_colours(self) -> None:
        self.workflow_state.set_colours(ReliefColours()); self._update_colour_buttons()
        self.mesh_view.set_colours(self.workflow_state.colours)

    def _update_colour_buttons(self) -> None:
        for button, colour in ((self.base_colour_button, self.workflow_state.colours.base), (self.contour_colour_button, self.workflow_state.colours.contour)):
            button.setText(colour); button.setStyleSheet(f"background-color: {colour}; color: {'white' if QColor(colour).lightness() < 128 else 'black'};")

    def _analysis_finished(self, analysis: object) -> None:
        """Present editable, deliberately uncertain findings from Image DNA."""
        prior_actions = {feature.identifier: feature.action for feature in self.focus_features}
        self.current_analysis = analysis
        self.focus_features = suggest_focus_features(analysis)
        for feature in self.focus_features:
            feature.action = prior_actions.get(feature.identifier, feature.action)
        self._rebuild_focus_cards()
        faces = len(getattr(analysis, "face_rectangles", ()))
        parts = ["ReCraft found a likely central subject and candidate silhouette"]
        if faces: parts.append(f"{faces} possible face region{'s' if faces != 1 else ''}")
        if any(feature.identifier == "background-pattern" for feature in self.focus_features): parts.append("prominent background texture")
        self.analysis_summary.setText("; ".join(parts) + ". These are visual suggestions, not certain scene labels. Choose what Contour should preserve.")

    def _rebuild_focus_cards(self) -> None:
        while self.focus_cards_layout.count():
            item = self.focus_cards_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for feature in self.focus_features:
            row = QWidget(); layout = QHBoxLayout(row); layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(f"{feature.label} — {feature.explanation}"); label.setWordWrap(True); layout.addWidget(label, 1)
            choice = QComboBox()
            for action in FocusAction: choice.addItem(action.value.title(), action)
            choice.setCurrentIndex(choice.findData(feature.action)); choice.currentIndexChanged.connect(lambda index, candidate=feature, combo=choice: self._focus_action_changed(candidate, combo.currentData()))
            layout.addWidget(choice); self.focus_cards_layout.addWidget(row)

    def _focus_action_changed(self, feature: object, action: FocusAction) -> None:
        feature.action = action
        self._apply_focus_masks()

    def _apply_focus_masks(self) -> None:
        if self.user_importance is None or not self.focus_features: return
        shape = self.focus_features[0].mask.shape; add = np.zeros(shape, np.float32); reduce = np.zeros(shape, np.float32)
        for feature in self.focus_features:
            if feature.action is FocusAction.ADD: add = np.maximum(add, feature.mask)
            elif feature.action in (FocusAction.REDUCE, FocusAction.IGNORE): reduce = np.maximum(reduce, feature.mask * (1 if feature.action is FocusAction.IGNORE else .65))
        self.user_importance.focus_add_prepared = add; self.user_importance.focus_reduce_prepared = reduce
        self.workflow_state.invalidate_importance(); self.cached_contour_result = self.cached_mesh_result = None; self._invalidate_output(); self._refresh_source_mode()

    def _reset_focus_suggestions(self) -> None:
        for feature in self.focus_features: feature.action = FocusAction.AUTO
        self._apply_focus_masks(); self._rebuild_focus_cards()

    def _apply_focus_description(self) -> None:
        intent = interpret_focus_description(self.focus_description.toPlainText())
        for feature in self.focus_features:
            identity = feature.identifier
            if ("face" in identity and "face" in intent.add_types) or ("subject" in identity and "subject" in intent.add_types) or ("silhouette" in identity and "silhouette" in intent.add_types) or ("background" in identity and "background" in intent.add_types): feature.action = FocusAction.ADD
            if ("background" in identity and "background" in intent.reduce_types) or ("bright" in identity and "bright" in intent.reduce_types): feature.action = FocusAction.REDUCE
        if intent.background_amount is not None: self.background_strength.setValue(intent.background_amount)
        self.analysis_summary.setText(f"Description mapped to existing analysis: {intent.explanation}. Unsupported wording is ignored rather than treated as scene understanding.")
        self._apply_focus_masks(); self._rebuild_focus_cards()

    def _preset_changed(self) -> None:
        name = self.preset_combo.currentData()
        if name is not None: self._apply_preset(self.preset_state.select(name))

    def _reset_to_preset(self) -> None:
        self._apply_preset(self.preset_state.reset())

    def _apply_preset(self, preset: object) -> None:
        values = {"detail": preset.detail, "smoothing": preset.smoothing, "simplification": preset.simplification, "minimum_path_length": preset.minimum_path_length, "minimum_spacing": preset.minimum_spacing, "line_weight": preset.line_weight, "subject_emphasis": preset.subject_emphasis, "background_reduction": preset.background_reduction}
        for key, value in values.items():
            if key in self.parameter_widgets: self.parameter_widgets[key].setValue(value)
        self.ridge_width.setValue(preset.ridge_width); self.minimum_height.setValue(preset.minimum_height); self.maximum_height.setValue(preset.maximum_height); self.relief_strength.setValue(preset.relief_strength); self.mesh_resolution.setValue(preset.mesh_resolution)
        self.preset_description.setText(preset.description); self.preset_modified.setText(f"{preset.name.value} defaults")
        self.cached_contour_result = self.cached_mesh_result = None
        if self.source_image is not None: self._generate()

    def _profile_changed(self) -> None:
        self.print_profile = PROFILES[self.profile_combo.currentData()]
        self.nozzle_spin.setValue(self.print_profile.nozzle_diameter); self.layer_spin.setValue(self.print_profile.layer_height); self.minimum_feature.setValue(self.print_profile.minimum_contour_width)

    def _print_settings_changed(self) -> None:
        self.cached_mesh_result = None; self.workflow_state.invalidate_relief()

    def _refresh_source_mode(self) -> None:
        if self.prepared_preview is None: return
        mode = self.source_view_mode.currentText()
        if mode == "Prepared image": self.prepared_view.set_image(self.prepared_preview)
        elif mode == "Importance overlay": self._refresh_prepared()
        elif mode == "Background suppression" and self.current_analysis is not None: self.prepared_view.set_image(self.current_analysis.debug_image("Background Mask"))
        elif mode == "Relief-height map" and self.cached_contour_result is not None: self.prepared_view.set_image(contour_height_image(self.cached_contour_result))
        elif mode == "Suggested focus features" and self.current_analysis is not None:
            base = np.asarray(self.prepared_preview).astype(np.float32); overlay = np.zeros(base.shape[:2], np.float32)
            for feature in self.focus_features: overlay = np.maximum(overlay, np.asarray(Image.fromarray((feature.mask * 255).astype(np.uint8)).resize(self.prepared_preview.size, Image.Resampling.BILINEAR), np.float32) / 255)
            tint = np.zeros_like(base); tint[..., 1] = 255; alpha = overlay[..., None] * .42; self.prepared_view.set_image(Image.fromarray(np.clip(base * (1 - alpha) + tint * alpha, 0, 255).astype(np.uint8)))
        else: self.prepared_view.set_image(self.prepared_preview)

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
