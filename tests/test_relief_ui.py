"""Headless checks for the ReCraft Portrait Relief workspace and viewer."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication
import numpy as np
import pytest

from recraft.relief.mesh import build_relief_mesh
from recraft.core_engine import ColourMode, CoreSettings, DetailLevel, render_core
from recraft.ui.main_window import MainWindow
from recraft.ui.mesh_view import (
    MAX_RENDER_FACES,
    MeshView,
    build_coherent_render_surface,
    colour_relief_texture,
    relief_shading_texture,
)
from recraft.ui.core_worker import CoreWorker
from recraft.relief.presets import ReliefSettings


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_workspace_fits_laptop_and_advanced_is_hidden(app: QApplication) -> None:
    window = MainWindow(); window.resize(1366, 768); window.show(); app.processEvents()
    assert window.width() <= 1366 and window.height() <= 768
    assert window.source_view.isVisible() and window.mesh_view.isVisible() and window.generate_button.isVisible()
    assert window.generate_button.geometry().bottom() <= window.height()
    assert not window.advanced_section.content.isVisible()
    window.close()


def test_detail_change_marks_preview_stale_and_camera_does_not(app: QApplication) -> None:
    window = MainWindow(); window.source_image = Image.new("RGB", (180, 120), "white"); window._refresh_prepared(); window.preview_up_to_date = True
    window.detail_combo.setCurrentIndex(window.detail_combo.findData(DetailLevel.FINE)); assert not window.preview_up_to_date
    window.preview_up_to_date = True; window.mesh_view.camera.orbit(10, 5); window.mesh_view.camera.zoom(.9); window.mesh_view.camera.pan(.1, .1)
    assert window.preview_up_to_date and window._thread is None
    window.close()


def test_worker_generates_reliable_preview_and_reports_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    class Logger:
        def info(self, *args: object, **kwargs: object) -> None: pass
        def exception(self, *args: object, **kwargs: object) -> None: pass

    monkeypatch.setattr("recraft.ui.core_worker.get_diagnostic_logger", lambda: Logger())
    image = Image.new("RGB", (180, 120), "#777777"); stages: list[str] = []; results: list[object] = []; errors: list[str] = []
    worker = CoreWorker(image, CoreSettings(preview_resolution=96)); worker.stage_changed.connect(lambda stage, value: stages.append(stage)); worker.preview_ready.connect(results.append); worker.failed.connect(errors.append); worker.run()
    assert not errors and results and results[0].mesh.result.watertight and len(stages) >= 6


def test_preview_colour_change_does_not_regenerate_geometry(app: QApplication) -> None:
    window = MainWindow()
    window.source_image = Image.new("RGB", (120, 120), "#778899")
    window._refresh_prepared()
    result = render_core(window.prepared_image, CoreSettings(preview_resolution=96))
    window._preview_ready(result)
    vertices = window.mesh_view._vertices
    window.colour_combo.setCurrentIndex(window.colour_combo.findData(ColourMode.ORIGINAL))
    assert window.preview_up_to_date
    assert window.mesh_view._vertices is vertices
    assert window._thread is None
    window.close()


def test_mesh_preview_is_a_coherent_complete_surface(app: QApplication) -> None:
    values = np.zeros((112, 150), np.float32)
    values[:, :40] = 1
    result = build_relief_mesh(values, ReliefSettings(), preview=True)
    vertices, faces = build_coherent_render_surface(result)
    assert len(faces) <= MAX_RENDER_FACES
    assert vertices[:, 0].min() == pytest.approx(0)
    assert vertices[:, 0].max() == pytest.approx(result.width_mm)
    assert vertices[:, 1].min() == pytest.approx(0)
    assert vertices[:, 1].max() == pytest.approx(result.height_mm)
    top = vertices[vertices[:, 2] > 0]
    assert top[top[:, 0] < 40, 2].mean() > top[top[:, 0] > 120, 2].mean()
    assert len(np.unique(faces)) == len(vertices)

    view = MeshView()
    view.resize(640, 480)
    view.set_mesh(result)
    assert len(view._faces) == len(faces)
    assert view._raised.all()
    assert view._relief_texture is not None
    assert view._relief_texture.size().width() == values.shape[1]
    assert view._relief_texture.size().height() == values.shape[0]


def test_full_height_map_texture_retains_detail() -> None:
    values = np.zeros((190, 152), np.float32)
    values[45:48, 70:73] = 1
    texture = relief_shading_texture(values)
    assert texture.width() == 152 and texture.height() == 190
    pixels = np.frombuffer(texture.bits(), dtype=np.uint8).reshape(190, texture.bytesPerLine())
    assert np.ptp(pixels) > 80


def test_colour_texture_is_aligned_and_camera_independent(app: QApplication) -> None:
    values = np.tile(np.linspace(0, 1, 96, dtype=np.float32), (96, 1))
    result = build_relief_mesh(values, ReliefSettings(preview_resolution=96), preview=True)
    colours = np.zeros((96, 96, 3), np.uint8)
    colours[:, :48] = (240, 20, 10)
    colours[:, 48:] = (10, 20, 240)
    texture = colour_relief_texture(colours, values)
    view = MeshView(); view.set_mesh(result, surface_pixels=colours)
    vertices, faces, texture_key = view._vertices, view._faces, view._relief_texture.cacheKey()
    view.camera.orbit(15, 7); view.camera.zoom(.9); view.camera.pan(.1, -.1)
    assert view._vertices is vertices and view._faces is faces
    assert view._relief_texture.cacheKey() == texture_key
    pixels = np.frombuffer(texture.bits(), np.uint8).reshape(texture.height(), texture.bytesPerLine())
    assert pixels[:, : texture.width() * 3 // 2].mean() != pixels[:, texture.width() * 3 // 2 : texture.width() * 3].mean()


def test_failure_state_preserves_last_valid_result(app: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("recraft.ui.main_window.QMessageBox.critical", lambda *args, **kwargs: None)
    window = MainWindow(); marker = object(); window.core_result = marker; window.preview_up_to_date = True
    window._generation_failed("synthetic failure")
    assert window.core_result is marker and "previous preview preserved" in window.state_label.text().lower()
    window.close()
