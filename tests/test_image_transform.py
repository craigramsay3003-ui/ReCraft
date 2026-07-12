from dataclasses import replace

import numpy as np
import pytest
from PIL import Image

from recraft.core.image_transform import (
    ASPECT_RATIO_PRESETS, FitMode, ImageTransformSettings, prepare_image,
    size_for_aspect_ratio,
)


@pytest.fixture
def source() -> Image.Image:
    array = np.zeros((20, 40, 3), dtype=np.uint8)
    array[:, :20] = (255, 0, 0)
    array[:10, 20:] = (0, 255, 0)
    array[10:, 20:] = (0, 0, 255)
    return Image.fromarray(array, "RGB")


def test_prepare_image_does_not_modify_original(source: Image.Image) -> None:
    before = source.tobytes()
    prepare_image(source, ImageTransformSettings(output_width=30, output_height=30))
    assert source.size == (40, 20)
    assert source.tobytes() == before


def test_prepare_image_returns_requested_dimensions(source: Image.Image) -> None:
    result = prepare_image(source, ImageTransformSettings(), (37, 23))
    assert result.size == (37, 23)
    assert result.mode == "RGB"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Square 1:1", (600, 600)),
        ("Portrait 4:5", (600, 750)),
        ("Portrait 2:3", (600, 900)),
        ("Landscape 3:2", (600, 400)),
        ("Landscape 16:9", (600, 338)),
    ],
)
def test_aspect_ratio_presets_produce_expected_shapes(name: str, expected: tuple[int, int]) -> None:
    assert size_for_aspect_ratio((600, 600), ASPECT_RATIO_PRESETS[name]) == expected


def test_fit_mode_preserves_full_image(source: Image.Image) -> None:
    result = prepare_image(source, ImageTransformSettings(fit_mode=FitMode.FIT), (40, 40))
    pixels = np.asarray(result)
    assert np.all(pixels[0] == 255)  # letterbox remains visible
    assert np.any(np.all(pixels[20] == (255, 0, 0), axis=1))


def test_fill_mode_fills_output_frame(source: Image.Image) -> None:
    result = prepare_image(source, ImageTransformSettings(fit_mode=FitMode.FILL), (40, 40))
    assert not np.any(np.all(np.asarray(result) == (255, 255, 255), axis=2))


def test_zoom_and_pan_change_composition(source: Image.Image) -> None:
    base = ImageTransformSettings(output_width=20, output_height=20)
    normal = np.asarray(prepare_image(source, base))
    zoomed = np.asarray(prepare_image(source, replace(base, zoom=2.0)))
    panned = np.asarray(prepare_image(source, replace(base, pan_x=0.8)))
    assert not np.array_equal(normal, zoomed)
    assert not np.array_equal(normal, panned)


def test_rotation_works(source: Image.Image) -> None:
    result = prepare_image(
        source,
        ImageTransformSettings(rotation_quarters=1, fit_mode=FitMode.FIT),
        (20, 40),
    )
    assert np.all(np.asarray(result)[5, 5] == (255, 0, 0))
    assert np.all(np.asarray(result)[5, 15] == (255, 0, 0))


def test_horizontal_and_vertical_flips_work(source: Image.Image) -> None:
    settings = ImageTransformSettings(fit_mode=FitMode.FIT)
    horizontal = np.asarray(prepare_image(source, replace(settings, flip_horizontal=True), (40, 20)))
    vertical = np.asarray(prepare_image(source, replace(settings, flip_vertical=True), (40, 20)))
    assert np.all(horizontal[5, 35] == (255, 0, 0))
    assert np.all(vertical[15, 5] == (255, 0, 0))
    assert np.all(vertical[5, 25] == (0, 0, 255))


def test_reset_returns_centred_defaults() -> None:
    changed = ImageTransformSettings(pan_x=0.7, zoom=4, rotation_quarters=3, flip_horizontal=True)
    reset = changed.reset((640, 480))
    assert reset.pan_x == reset.pan_y == 0
    assert reset.zoom == 1
    assert reset.rotation_quarters == 0
    assert not reset.flip_horizontal and not reset.flip_vertical
    assert (reset.output_width, reset.output_height) == (640, 480)


@pytest.mark.parametrize(
    "settings",
    [
        ImageTransformSettings(output_width=0),
        ImageTransformSettings(output_height=8001),
        ImageTransformSettings(zoom=0.5),
        ImageTransformSettings(pan_x=2),
        ImageTransformSettings(aspect_ratio=(0, 1)),
    ],
)
def test_invalid_settings_raise_useful_errors(settings: ImageTransformSettings) -> None:
    with pytest.raises(ValueError):
        settings.validated()


def test_very_small_source_can_be_prepared() -> None:
    result = prepare_image(Image.new("RGB", (1, 1), "purple"), ImageTransformSettings(), (20, 10))
    assert result.size == (20, 10)
