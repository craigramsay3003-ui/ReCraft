"""Headless checks for the minimal relief workspace and worker."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication
import pytest

from recraft.relief.presets import ReliefSettings, ReliefStyle
from recraft.ui.main_window import MainWindow
from recraft.ui.relief_worker import ReliefWorker


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


def test_style_change_marks_preview_stale_and_camera_does_not(app: QApplication) -> None:
    window = MainWindow(); window.source_image = Image.new("RGB", (180, 120), "white"); window._refresh_prepared(); window.preview_up_to_date = True
    window.style_combo.setCurrentIndex(window.style_combo.findData(ReliefStyle.GRAPHIC)); assert not window.preview_up_to_date
    window.preview_up_to_date = True; window.mesh_view.camera.orbit(10, 5); window.mesh_view.camera.zoom(.9); window.mesh_view.camera.pan(.1, .1)
    assert window.preview_up_to_date and window._thread is None
    window.close()


def test_worker_generates_reliable_preview_and_reports_progress() -> None:
    image = Image.new("RGB", (180, 120), "#777777"); stages: list[str] = []; results: list[object] = []; errors: list[str] = []
    worker = ReliefWorker(image, ReliefSettings(preview_resolution=100)); worker.stage_changed.connect(lambda stage, value: stages.append(stage)); worker.preview_ready.connect(lambda image, heights, result: results.append(result)); worker.failed.connect(errors.append); worker.run()
    assert not errors and results and results[0].watertight and len(stages) >= 3


def test_worker_accepts_style_value_from_qt_combo_box() -> None:
    image = Image.new("RGB", (120, 90), "#777777")
    errors: list[str] = []
    results: list[object] = []
    worker = ReliefWorker(image, ReliefSettings(style="Portrait Relief", preview_resolution=80))
    worker.preview_ready.connect(lambda image, heights, result: results.append(result))
    worker.failed.connect(errors.append)
    worker.run()
    assert not errors and results


def test_failure_state_preserves_last_valid_result(app: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("recraft.ui.main_window.QMessageBox.critical", lambda *args, **kwargs: None)
    window = MainWindow(); marker = object(); window.relief_result = marker; window.preview_up_to_date = True
    window._generation_failed("synthetic failure")
    assert window.relief_result is marker and "previous preview preserved" in window.state_label.text().lower()
    window.close()
