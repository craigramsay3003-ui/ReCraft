"""Focused acceptance tests for the ReCraft core and synthetic face."""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import pytest

from recraft.core_engine import (
    BackgroundTreatment,
    ColourMode,
    CoreSettings,
    DetailLevel,
    SubjectEmphasis,
    render_core,
)
from recraft.core_engine.colour import artistic_palette
from scripts.generate_benchmark_images import generate_face_benchmark


ASSETS = Path(__file__).parent / "assets"


@pytest.fixture(scope="module")
def benchmark() -> Image.Image:
    return Image.open(ASSETS / "benchmark_face_colour.png").convert("RGB")


def test_benchmark_is_deterministic_and_has_expected_regions(benchmark: Image.Image) -> None:
    generated = generate_face_benchmark()
    assert generated.size == (1024, 1024)
    assert np.array_equal(np.asarray(generated), np.asarray(benchmark))
    rgb = np.asarray(benchmark)
    assert len(np.unique(rgb.reshape(-1, 3), axis=0)) > 20
    # Right-only gold earring and left-heavy dark curl are mirror sentinels.
    gold = (rgb[..., 0] > 210) & (rgb[..., 1] > 140) & (rgb[..., 2] < 100)
    dark = rgb.mean(axis=2) < 75
    assert gold[:, 600:].sum() > gold[:, :424].sum() * 2
    assert dark[:, :400].sum() > dark[:, 624:].sum()


def test_subject_analysis_and_importance_are_bounded(benchmark: Image.Image) -> None:
    result = render_core(benchmark, CoreSettings(preview_resolution=160))
    assert result.analysis.subject_mask.shape == (160, 160)
    assert 0 <= result.analysis.confidence <= 1
    assert result.analysis.fallback_state in {"largest coherent foreground region", "centre-weighted fallback"}
    assert np.isfinite(result.importance.values).all()
    assert 0 <= result.importance.values.min() <= result.importance.values.max() <= 1


def test_high_subject_and_remove_background_create_separation(benchmark: Image.Image) -> None:
    result = render_core(
        benchmark,
        CoreSettings(
            subject_emphasis=SubjectEmphasis.HIGH,
            background=BackgroundTreatment.REMOVE,
            preview_resolution=160,
        ),
    )
    subject = result.analysis.subject_mask > .55
    background = result.analysis.subject_mask < .15
    assert subject.any() and background.any()
    assert result.relief.values[subject].mean() > result.relief.values[background].mean() + .2
    assert result.relief.background_height_range[1] < result.relief.subject_height_range[1]


def test_detail_modes_change_artistic_simplification(benchmark: Image.Image) -> None:
    simple = render_core(benchmark, CoreSettings(detail=DetailLevel.SIMPLE, preview_resolution=140))
    fine = render_core(benchmark, CoreSettings(detail=DetailLevel.FINE, preview_resolution=140))
    assert simple.simplification.minimum_feature_pixels >= fine.simplification.minimum_feature_pixels
    assert len(np.unique(simple.simplification.tonal_regions)) < len(np.unique(fine.simplification.tonal_regions))
    assert fine.simplification.reinforced_edges.sum() >= simple.simplification.reinforced_edges.sum()


def test_face_features_have_meaningful_monochrome_relief(benchmark: Image.Image) -> None:
    result = render_core(benchmark, CoreSettings(preview_resolution=190))
    field = result.relief.values
    # Regions are scaled benchmark coordinates: left eye, nose, mouth, clothing.
    def region(x1: int, y1: int, x2: int, y2: int) -> np.ndarray:
        scale = field.shape[0] / 1024
        return field[round(y1 * scale):round(y2 * scale), round(x1 * scale):round(x2 * scale)]
    feature_means = [region(370, 380, 465, 460).mean(), region(470, 420, 555, 590).mean(), region(420, 580, 620, 680).mean(), region(340, 780, 680, 980).mean()]
    assert np.ptp(feature_means) > .08
    assert np.ptp(field) > .65


@pytest.mark.parametrize("palette_size", (2, 3, 4, 6))
def test_artistic_palette_size_and_cleanup(benchmark: Image.Image, palette_size: int) -> None:
    settings = CoreSettings(colour_mode=ColourMode.ARTISTIC, palette_size=palette_size, preview_resolution=140)
    result = render_core(benchmark, settings)
    assert len(result.colour.palette) == palette_size
    assert len(np.unique(result.colour.labels)) <= palette_size
    assert result.colour.pixels.shape == (140, 140, 3)


def test_palette_locked_colour_and_tiny_island_cleanup() -> None:
    rgb = np.full((80, 80, 3), (210, 180, 150), np.uint8)
    rgb[:, 40:] = (40, 80, 130)
    rgb[10, 10] = (255, 0, 255)
    pixels, labels, palette = artistic_palette(rgb, 2, 10, ("#112233", None))
    assert palette[0] == "#112233"
    assert len(np.unique(labels[8:13, 8:13])) == 1
    assert pixels.shape == rgb.shape


def test_mesh_is_positive_watertight_oriented_and_uv_aligned(benchmark: Image.Image) -> None:
    result = render_core(benchmark, CoreSettings(colour_mode=ColourMode.ORIGINAL, preview_resolution=150))
    mesh = result.mesh.result
    assert mesh.watertight and mesh.mesh.is_watertight
    assert mesh.mesh.bounds[0, 2] == pytest.approx(0)
    assert mesh.mesh.bounds[1, 2] > 1.5
    assert mesh.width_mm == pytest.approx(160)
    assert mesh.triangle_count <= 150_000
    uv = result.mesh.uv_coordinates
    assert np.all((0 <= uv) & (uv <= 1))
    # Geometry X and texture U increase together; neither is mirrored.
    top_count = result.relief.values.size
    correlation = np.corrcoef(mesh.mesh.vertices[:top_count, 0], uv[:top_count, 0])[0, 1]
    assert correlation > .999
