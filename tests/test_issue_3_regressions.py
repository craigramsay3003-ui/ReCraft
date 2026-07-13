"""Synthetic regressions for GitHub issue #3."""

import gc
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication
import pytest

from recraft.core.image_transform import ImageTransformSettings
from recraft.engine import analyse_image
from recraft.engine.focus_features import FocusFeature
from recraft.engine.user_importance import UserImportanceState
from recraft.exporters.contour_mesh import (
    ContourMeshSettings, MeshComplexityError, build_contour_mesh,
    estimate_mesh_resources,
)
from recraft.styles.contour import ContourStyle
from recraft.styles.contour_geometry import ContourPath, ContourResult
from recraft.ui.image_view import ImageView
from recraft.ui.main_window import MainWindow
from recraft.ui.mesh_view import MeshView
from recraft.ui.mesh_worker import MeshWorker


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def sample_contours(points: int = 50) -> ContourResult:
    coordinates = tuple((float(index), float(10 + index % 8)) for index in range(points))
    path = ContourPath(coordinates, .5, .8, False, .9, .7, .1, tuple(np.linspace(.2, 1, points)))
    return ContourResult(max(points, 2), 30, (path,), (path,), max(points, 2) / 30)


def test_source_preview_is_in_workspace_and_valid_result_is_preserved(app: QApplication) -> None:
    window = MainWindow(); image = Image.new("RGB", (80, 50), "navy")
    window.source_image = image; window.prepared_preview = image.copy(); window.prepared_view.set_image(image)
    window.output_image = image.copy(); window.output_view.set_image(image)
    assert window.prepared_view.parent() is window.preview_page
    window._invalidate_output()
    assert window.prepared_view._image is not None and window.output_view._image is not None
    window.close()


def test_brush_coordinates_follow_display_zoom_and_pan(app: QApplication) -> None:
    view = ImageView("test", interactive=True); view.resize(400, 300); view.set_image(Image.new("RGB", (200, 100)))
    view._view_zoom = 2.0; view._view_offset.setX(25); view._view_offset.setY(-15)
    scale = view._display_scale(); expected = (73.0, 41.0)
    widget_x = (view.width() - 200 * scale) / 2 + 25 + expected[0] * scale
    widget_y = (view.height() - 100 * scale) / 2 - 15 + expected[1] * scale
    assert view.map_widget_to_image(widget_x, widget_y) == pytest.approx(expected)


def test_focus_description_does_not_blank_preview(app: QApplication) -> None:
    window = MainWindow(); image = Image.new("RGB", (100, 80), "white")
    window.source_image = image; window.prepared_preview = image.copy(); window.prepared_view.set_image(image)
    window.output_image = image.copy(); window.output_view.set_image(image)
    window.user_importance = UserImportanceState.create(image.size)
    window.focus_features = [FocusFeature("possible-face-0", "Possible face", "test", np.ones((40, 50), np.float32))]
    window.focus_description.setPlainText("Focus on the face")
    window._apply_focus_description()
    assert window.output_view._image is not None and window.prepared_view._image is not None
    window.close()


def test_detailed_geometry_is_bounded_and_excessive_grid_fails_safely() -> None:
    result = sample_contours(5_000)
    bounded = build_contour_mesh(result, ContourMeshSettings(resolution=230, maximum_sampled_points=1_000))
    assert bounded.sampled_point_count <= 1_002
    assert bounded.warnings and bounded.watertight
    _, faces, _ = estimate_mesh_resources(500, 500)
    assert faces > 250_000
    square = ContourResult(result.width, result.width, result.paths, result.raw_paths, 1.0)
    with pytest.raises(MeshComplexityError, match="safe limit"):
        build_contour_mesh(square, ContourMeshSettings(resolution=500))


def test_cached_analysis_avoids_reanalysis(monkeypatch: pytest.MonkeyPatch) -> None:
    image = Image.new("RGB", (100, 70), "white"); analysis = analyse_image(image); errors: list[str] = []; meshes: list[object] = []
    monkeypatch.setattr("recraft.ui.mesh_worker.analyse_prepared_preview", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("analysis reran")))
    worker = MeshWorker(image, ImageTransformSettings(output_width=100, output_height=70), None, ContourStyle().defaults(), ContourMeshSettings(resolution=45), None, analysis=analysis, preset="Standard")
    worker.failed.connect(errors.append); worker.mesh_ready.connect(meshes.append); worker.run()
    assert not errors and meshes


def test_camera_navigation_uses_stable_owned_render_buffers(app: QApplication) -> None:
    result = build_contour_mesh(sample_contours(), ContourMeshSettings(resolution=45)); viewer = MeshView(); viewer.resize(500, 350); viewer.set_mesh(result)
    vertices = viewer._vertices.copy(); faces = viewer._faces.copy(); del result; gc.collect()
    for _ in range(25):
        viewer.camera.orbit(3, -1); viewer.camera.zoom(.99); viewer.camera.pan(.002, -.001); viewer.update()
    viewer.reset_camera(); viewer.grab()
    assert viewer.result is not None and np.array_equal(vertices, viewer._vertices) and np.array_equal(faces, viewer._faces)
    assert not viewer._vertices.flags.writeable and viewer._render_error is None
