"""Geometry-first STL and limited artistic-palette 3MF checks."""

from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from PIL import Image
import pytest
import trimesh

from recraft.core_engine import ColourMode, CoreSettings, render_core
from recraft.core_engine.export import export_core_3mf, export_core_stl


ASSET = Path(__file__).parent / "assets" / "benchmark_face_colour.png"
NAMESPACE = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}


@pytest.fixture(scope="module")
def export_result():
    image = Image.open(ASSET).convert("RGB")
    return render_core(
        image,
        CoreSettings(colour_mode=ColourMode.ARTISTIC, palette_size=4, export_resolution=160),
        preview=False,
    )


def test_stl_is_geometry_only_watertight_and_millimetres(export_result, tmp_path: Path) -> None:
    path = tmp_path / "benchmark.stl"
    export_core_stl(export_result.mesh, path)
    loaded = trimesh.load(path, force="mesh")
    assert loaded.is_watertight
    assert loaded.bounds[0, 2] == pytest.approx(0)
    assert loaded.extents[0] == pytest.approx(160, rel=1e-5)
    assert b"COLOR" not in path.read_bytes()[:200]


def test_3mf_is_one_object_with_palette_and_neutral_base(export_result, tmp_path: Path) -> None:
    path = tmp_path / "benchmark.3mf"
    export_core_3mf(export_result.mesh, path)
    with ZipFile(path) as package:
        assert set(package.namelist()) == {"[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"}
        model = ET.fromstring(package.read("3D/3dmodel.model"))
    assert model.attrib["unit"] == "millimeter"
    assert len(model.findall(".//m:object", NAMESPACE)) == 1
    materials = model.findall(".//m:base", NAMESPACE)
    triangles = model.findall(".//m:triangle", NAMESPACE)
    assert len(materials) == 5
    assert len(triangles) == export_result.mesh.result.triangle_count
    assert {triangle.attrib["pid"] for triangle in triangles} == {"1"}
    assert {int(triangle.attrib["p1"]) for triangle in triangles} == {0, 1, 2, 3, 4}


def test_preview_and_export_share_orientation_and_proportions() -> None:
    image = Image.open(ASSET).convert("RGB")
    settings = CoreSettings(colour_mode=ColourMode.ORIGINAL, preview_resolution=96, export_resolution=160)
    preview = render_core(image, settings, preview=True)
    export = render_core(image, settings, preview=False)
    assert preview.mesh.result.width_mm == export.mesh.result.width_mm
    assert preview.mesh.result.height_mm == pytest.approx(export.mesh.result.height_mm)
    assert preview.mesh.uv_coordinates[:, 0].min() == export.mesh.uv_coordinates[:, 0].min() == 0
    assert preview.mesh.uv_coordinates[:, 0].max() == export.mesh.uv_coordinates[:, 0].max() == 1
    assert export.mesh.result.triangle_count > preview.mesh.result.triangle_count
    assert export.mesh.result.triangle_count < 350_000
