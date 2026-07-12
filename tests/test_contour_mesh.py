from pathlib import Path

import pytest
import trimesh

from recraft.exporters.contour_mesh import ContourMeshSettings, build_contour_mesh, export_contour_stl
from recraft.styles.contour_geometry import ContourPath, ContourResult


def sample_result() -> ContourResult:
    path = ContourPath(((5, 10), (25, 12), (45, 30), (75, 35), (95, 40)), .5, .8, False)
    return ContourResult(100, 50, (path,), (path,), 2.0)


def test_contour_mesh_is_watertight_and_has_physical_dimensions() -> None:
    result = build_contour_mesh(sample_result(), ContourMeshSettings(physical_width=100, border_width=2, resolution=60))
    assert result.watertight and result.mesh.is_watertight
    assert result.width_mm == pytest.approx(104); assert result.height_mm == pytest.approx(54)
    assert result.mesh.bounds[1, 2] == pytest.approx(3.2, abs=.1)


def test_stl_export_loads_as_watertight_mesh(tmp_path: Path) -> None:
    path = tmp_path / "contour.stl"
    export_contour_stl(sample_result(), ContourMeshSettings(resolution=50), path)
    loaded = trimesh.load_mesh(path)
    assert path.is_file() and loaded.is_watertight


def test_minimum_printable_width_and_invalid_geometry() -> None:
    with pytest.raises(ValueError, match="minimum printable"):
        build_contour_mesh(sample_result(), ContourMeshSettings(ridge_width=.4))
    empty = ContourResult(100, 50, (), (), 2)
    with pytest.raises(ValueError, match="no printable paths"):
        build_contour_mesh(empty, ContourMeshSettings())
