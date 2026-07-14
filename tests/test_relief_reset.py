"""Focused physical and interpretation tests for the relief reset."""

from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import cv2
import numpy as np
from PIL import Image
import pytest
import trimesh

from recraft.relief.heightmap import compose_relief_values, create_relief_height_map, suppress_isolated_spikes
from recraft.relief.mesh import MAX_PREVIEW_TRIANGLES, build_relief_mesh, export_relief_3mf, export_relief_stl
from recraft.relief.presets import ReliefSettings, ReliefStyle


def maps(shape: tuple[int, int] = (40, 60)) -> tuple[np.ndarray, ...]:
    luminance = np.tile(np.linspace(0, 1, shape[1], dtype=np.float32), (shape[0], 1)); zero = np.zeros(shape, np.float32)
    return luminance, zero.copy(), zero.copy(), zero.copy(), zero.copy(), zero.copy()


def test_dark_to_light_mapping_and_normal_invert() -> None:
    normal = compose_relief_values(*maps(), ReliefSettings())
    inverted = compose_relief_values(*maps(), ReliefSettings(invert=True))
    assert normal[:, -5:].mean() > normal[:, :5].mean()
    assert np.allclose(normal + inverted, 1, atol=1e-5)
    assert 0 <= normal.min() <= normal.max() <= 1


def test_ui_style_string_is_normalized_to_enum() -> None:
    settings = ReliefSettings(style="Graphic Relief").validated()
    assert settings.style is ReliefStyle.GRAPHIC
    with pytest.raises(ValueError, match="Unknown relief style"):
        ReliefSettings(style="Missing Relief").validated()


def test_spike_smoothing_and_flat_area_cleanup() -> None:
    spike = np.zeros((31, 31), np.float32); spike[15, 15] = 1
    smooth = suppress_isolated_spikes(spike)
    assert smooth.max() < 1 and np.count_nonzero(smooth > .01) > 1
    flat = np.full((30, 40), .5, np.float32); zero = np.zeros_like(flat)
    assert np.count_nonzero(compose_relief_values(flat, zero, zero, zero, zero, zero, ReliefSettings())) == 0


def test_subject_emphasis_and_background_suppression() -> None:
    luminance, gradient, contrast, subject, background, face = maps(); subject[10:30, 20:40] = 1; background[:, :20] = 1
    low = compose_relief_values(luminance, gradient, contrast, subject, background, face, ReliefSettings(subject_emphasis=0, background_strength=0))
    high = compose_relief_values(luminance, gradient, contrast, subject, background, face, ReliefSettings(subject_emphasis=1, background_strength=0))
    suppressed = compose_relief_values(luminance, gradient, contrast, subject, background, face, ReliefSettings(subject_emphasis=0, background_strength=1))
    assert high[10:30, 20:40].mean() > low[10:30, 20:40].mean()
    assert suppressed[:, :20].mean() < low[:, :20].mean()


@pytest.mark.parametrize("style", list(ReliefStyle))
def test_all_styles_create_bounded_height_maps(style: ReliefStyle) -> None:
    y, x = np.mgrid[0:120, 0:180]; rgb = np.stack((x, y * 2, (x + y) % 255), -1).astype(np.uint8)
    result = create_relief_height_map(Image.fromarray(rgb), ReliefSettings(style=style), 120)
    assert result.values.shape == (80, 120) and result.values.dtype == np.float32
    assert 0 <= result.values.min() <= result.values.max() <= 1


def test_mesh_is_positive_watertight_flat_back_and_correct_size() -> None:
    values = np.tile(np.linspace(0, 1, 100, dtype=np.float32), (70, 1)); settings = ReliefSettings(physical_width_mm=160, base_thickness_mm=1.5, relief_depth_mm=1.8)
    result = build_relief_mesh(values, settings, preview=True)
    assert result.watertight and result.mesh.is_watertight
    assert result.width_mm == pytest.approx(160) and result.height_mm == pytest.approx(112)
    assert result.mesh.vertices[:, 2].min() == 0 and result.mesh.vertices[:, 2].max() == pytest.approx(3.3)
    assert np.count_nonzero(result.mesh.vertices[:, 2] == 0) == values.size
    assert result.triangle_count <= MAX_PREVIEW_TRIANGLES


def test_left_right_orientation_and_preview_export_structure_match() -> None:
    values = np.zeros((50, 80), np.float32); values[:, :20] = 1
    preview = build_relief_mesh(values, ReliefSettings(), preview=True); export = build_relief_mesh(cv2.resize(values, (160, 100)), ReliefSettings(export_resolution=160), preview=False)
    ptop = preview.mesh.vertices[:values.size]; etop = export.mesh.vertices[:160 * 100]
    assert ptop[ptop[:, 0] < 40, 2].mean() > ptop[ptop[:, 0] > 120, 2].mean()
    assert etop[etop[:, 0] < 40, 2].mean() > etop[etop[:, 0] > 120, 2].mean()


def test_stl_round_trip_is_watertight(tmp_path: Path) -> None:
    values = np.tile(np.linspace(0, 1, 80, dtype=np.float32), (60, 1)); result = build_relief_mesh(values, ReliefSettings(), preview=True); path = tmp_path / "printable-relief.stl"
    export_relief_stl(result, path); loaded = trimesh.load_mesh(path)
    assert path.is_file() and loaded.is_watertight and loaded.bounds[0, 2] == 0


def test_3mf_is_one_millimetre_model_with_material(tmp_path: Path) -> None:
    values = np.tile(np.linspace(0, 1, 40, dtype=np.float32), (30, 1))
    result = build_relief_mesh(values, ReliefSettings(), preview=True)
    path = tmp_path / "printable-relief.3mf"
    export_relief_3mf(result, path, "#D99A52")
    with ZipFile(path) as package:
        model = ET.fromstring(package.read("3D/3dmodel.model"))
    namespace = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
    assert model.attrib["unit"] == "millimeter"
    assert len(model.findall(".//m:object", namespace)) == 1
    assert len(model.findall(".//m:build/m:item", namespace)) == 1
    material = model.find(".//m:basematerials/m:base", namespace)
    assert material is not None and material.attrib["displaycolor"] == "#D99A52FF"
