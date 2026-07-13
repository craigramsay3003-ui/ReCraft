from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

import numpy as np
import pytest

from recraft.exporters.contour_mesh import ContourMeshSettings, ReliefColours, build_contour_mesh, export_contour_3mf, render_relief_preview
from recraft.styles.contour_geometry import ContourPath, ContourResult


def relief_result(background: float = 0.0) -> ContourResult:
    high = ContourPath(((8, 12), (18, 12), (28, 12)), .5, .9, False, .95, .9, background, (.85, .95, .9))
    low = ContourPath(((72, 35), (82, 35), (90, 35)), .5, .2, False, .25, .1, background, (.15, .2, .15))
    return ContourResult(100, 50, (high, low), (high, low), 2.0)


def test_variable_height_mapping_and_bounds() -> None:
    settings = ContourMeshSettings(base_thickness=2, minimum_contour_height=.4, maximum_contour_height=2, background_relief_reduction=0, height_smoothing=0, resolution=100)
    result = build_contour_mesh(relief_result(), settings)
    raised = result.mesh.vertices[result.mesh.vertices[:, 2] > 2.01]
    left = raised[raised[:, 0] < result.width_mm / 2, 2].max(); right = raised[raised[:, 0] > result.width_mm / 2, 2].max()
    assert left > right
    assert result.ridge_height_range[0] >= .4
    assert result.ridge_height_range[1] <= 2
    assert result.watertight


def test_uniform_height_mode_and_background_reduction() -> None:
    uniform = build_contour_mesh(relief_result(), ContourMeshSettings(uniform_height=True, background_relief_reduction=0, height_smoothing=0, resolution=90))
    assert uniform.ridge_height_range[0] == pytest.approx(uniform.ridge_height_range[1])
    foreground = build_contour_mesh(relief_result(0), ContourMeshSettings(background_relief_reduction=.9, height_smoothing=0, resolution=90))
    background = build_contour_mesh(relief_result(1), ContourMeshSettings(background_relief_reduction=.9, height_smoothing=0, resolution=90))
    assert background.ridge_height_range[1] < foreground.ridge_height_range[1]


def test_height_smoothing_removes_isolated_peak() -> None:
    spike = ContourPath(((10, 20), (25, 20), (40, 20), (55, 20), (70, 20)), .5, .5, False, 1, .5, 0, (0, 0, 1, 0, 0))
    result = ContourResult(80, 40, (spike,), (spike,), 2)
    sharp = build_contour_mesh(result, ContourMeshSettings(height_smoothing=0, resolution=100))
    smooth = build_contour_mesh(result, ContourMeshSettings(height_smoothing=1.5, resolution=100))
    assert smooth.ridge_height_range[1] < sharp.ridge_height_range[1]


def test_asymmetric_orientation_preserves_left_and_right() -> None:
    result = build_contour_mesh(relief_result(), ContourMeshSettings(height_smoothing=0, background_relief_reduction=0, resolution=100))
    highest = result.mesh.vertices[np.argmax(result.mesh.vertices[:, 2])]
    assert highest[0] < result.width_mm / 2  # large/high source feature remains left
    assert highest[1] > result.height_mm / 2  # image top maps to Cartesian +Y
    assert result.mesh.bounds[0, 0] == pytest.approx(0)
    assert result.mesh.bounds[1, 0] == pytest.approx(result.width_mm)


def test_colours_preview_and_3mf_material_assignments(tmp_path: Path) -> None:
    colours = ReliefColours("#112233", "#E0A020"); settings = ContourMeshSettings(resolution=50)
    mesh = build_contour_mesh(relief_result(), settings)
    preview = render_relief_preview(mesh, colours, (240, 160)); assert preview.size == (240, 160)
    path = tmp_path / "coloured.3mf"; export_contour_3mf(relief_result(), settings, colours, path)
    with ZipFile(path) as package:
        model = ET.fromstring(package.read("3D/3dmodel.model"))
    xml = ET.tostring(model, encoding="unicode")
    assert "#112233FF" in xml and "#E0A020FF" in xml
    assignments = {element.attrib.get("p1") for element in model.iter() if element.tag.endswith("triangle")}
    assert assignments == {"0", "1"}
    vertices = [element.attrib for element in model.iter() if element.tag.endswith("vertex")]
    highest = max(vertices, key=lambda vertex: float(vertex["z"]))
    assert float(highest["x"]) < mesh.width_mm / 2  # 3MF matches source left/right


def test_relief_validation_and_colour_validation() -> None:
    with pytest.raises(ValueError, match="Minimum contour height"):
        ContourMeshSettings(minimum_contour_height=2, maximum_contour_height=1).validated()
    with pytest.raises(ValueError, match="RRGGBB"):
        ReliefColours("red", "#FFFFFF").validated()
