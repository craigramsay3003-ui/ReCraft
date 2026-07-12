"""Main ReCraft desktop window."""

from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from recraft.core.image_loader import ImageLoadError, load_image
from recraft.core.image_utils import fit_within
from recraft.core.style_registry import create_default_registry
from recraft.styles.base import ParameterValue
from recraft.ui.image_view import ImageView


class MainWindow(QMainWindow):
    """Coordinate image selection, style controls, preview, and export."""

    def __init__(self) -> None:
        super().__init__()
        self.registry = create_default_registry()
        self.source_image: Image.Image | None = None
        self.output_image: Image.Image | None = None
        self.parameter_widgets: dict[str, QSpinBox | QDoubleSpinBox] = {}
        self.setWindowTitle("ReCraft — Create the impossible.")
        self.resize(1100, 720)
        self._build_ui()
        self._rebuild_parameters()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        title = QLabel("ReCraft")
        title.setStyleSheet("font-size: 28px; font-weight: 700;")
        subtitle = QLabel("Create the impossible.")
        subtitle.setStyleSheet("font-size: 15px; color: #68717d;")
        root.addWidget(title)
        root.addWidget(subtitle)

        toolbar = QHBoxLayout()
        open_button = QPushButton("Open Image")
        open_button.clicked.connect(self._open_image)
        self.save_button = QPushButton("Save Output")
        self.save_button.clicked.connect(self._save_output)
        self.save_button.setEnabled(False)
        self.style_combo = QComboBox()
        for style in self.registry:
            self.style_combo.addItem(style.display_name, style.identifier)
        self.style_combo.currentIndexChanged.connect(self._rebuild_parameters)
        toolbar.addWidget(open_button)
        toolbar.addWidget(self.save_button)
        toolbar.addStretch()
        toolbar.addWidget(QLabel("Art style:"))
        toolbar.addWidget(self.style_combo)
        root.addLayout(toolbar)

        self.description = QLabel()
        root.addWidget(self.description)
        self.parameter_container = QWidget()
        self.parameter_form = QFormLayout(self.parameter_container)
        root.addWidget(self.parameter_container)
        generate = QPushButton("Generate")
        generate.clicked.connect(self._generate)
        root.addWidget(generate, alignment=Qt.AlignmentFlag.AlignRight)

        panels = QHBoxLayout()
        left = QVBoxLayout(); left.addWidget(QLabel("Original")); self.original_view = ImageView("Open an image to begin"); left.addWidget(self.original_view)
        right = QVBoxLayout(); right.addWidget(QLabel("Transformed preview")); self.output_view = ImageView("Generate a style preview"); right.addWidget(self.output_view)
        panels.addLayout(left); panels.addLayout(right)
        root.addLayout(panels, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Ready — open an image to begin")

    def _current_style(self):  # type: ignore[no-untyped-def]
        return self.registry.get(str(self.style_combo.currentData()))

    def _rebuild_parameters(self) -> None:
        while self.parameter_form.rowCount():
            self.parameter_form.removeRow(0)
        self.parameter_widgets.clear()
        style = self._current_style()
        self.description.setText(style.description)
        for parameter in style.parameters:
            widget: QSpinBox | QDoubleSpinBox
            if any(isinstance(value, float) for value in (parameter.default, parameter.minimum, parameter.maximum, parameter.step)):
                widget = QDoubleSpinBox(); widget.setDecimals(2)
            else:
                widget = QSpinBox()
            widget.setRange(parameter.minimum, parameter.maximum)
            widget.setSingleStep(parameter.step)
            widget.setValue(parameter.default)
            self.parameter_widgets[parameter.key] = widget
            self.parameter_form.addRow(parameter.label, widget)

    def _open_image(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Open image", "", "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)")
        if not filename:
            return
        try:
            self.source_image = fit_within(load_image(filename))
            self.original_view.set_image(self.source_image)
            self.output_image = None; self.output_view.set_image(None); self.save_button.setEnabled(False)
            self.statusBar().showMessage(f"Loaded {Path(filename).name}")
        except ImageLoadError as exc:
            QMessageBox.critical(self, "Could not open image", str(exc))

    def _generate(self) -> None:
        if self.source_image is None:
            QMessageBox.information(self, "No image", "Open an image before generating artwork.")
            return
        try:
            parameters: dict[str, ParameterValue] = {key: widget.value() for key, widget in self.parameter_widgets.items()}
            self.output_image = self._current_style().process(self.source_image, parameters)
            self.output_view.set_image(self.output_image); self.save_button.setEnabled(True)
            self.statusBar().showMessage(f"Generated {self._current_style().display_name} preview")
        except (ValueError, RuntimeError) as exc:
            QMessageBox.critical(self, "Generation failed", str(exc))

    def _save_output(self) -> None:
        if self.output_image is None:
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Save output", "recraft-output.png", "PNG image (*.png)")
        if not filename:
            return
        if not filename.lower().endswith(".png"):
            filename += ".png"
        try:
            self.output_image.save(filename, "PNG")
            self.statusBar().showMessage(f"Saved {Path(filename).name}")
        except OSError as exc:
            QMessageBox.critical(self, "Could not save output", str(exc))
