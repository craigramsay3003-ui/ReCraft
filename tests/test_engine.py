import numpy as np
import pytest
from PIL import Image

from recraft.engine import analyse_image


@pytest.fixture
def analysis():  # type: ignore[no-untyped-def]
    y, x = np.mgrid[0:48, 0:64]
    rgb = np.stack(((x * 4) % 256, (y * 5) % 256, ((x + y) * 3) % 256), axis=-1).astype(np.uint8)
    return analyse_image(Image.fromarray(rgb, "RGB"), colour_clusters=4)


def test_analysis_produces_complete_image_dna(analysis) -> None:  # type: ignore[no-untyped-def]
    shape = (48, 64)
    for layer in (
        analysis.greyscale, analysis.enhanced_greyscale, analysis.edge_map,
        analysis.gradient_magnitude, analysis.texture_map, analysis.saliency_map,
        analysis.face_mask, analysis.background_mask, analysis.subject_mask,
        analysis.centre_weight, analysis.local_contrast, analysis.importance_map,
    ):
        assert layer.shape == shape
        assert layer.dtype == np.float32
        assert 0 <= float(layer.min()) <= float(layer.max()) <= 1
    assert analysis.colour_labels.shape == shape
    assert analysis.colour_centres.shape == (4, 3)


def test_analysis_owns_independent_source_copy() -> None:
    source = Image.new("RGB", (20, 10), "red")
    result = analyse_image(source)
    source.paste("blue", (0, 0, 20, 10))
    assert result.image.getpixel((0, 0)) == (255, 0, 0)


def test_large_image_uses_bounded_analysis_maps() -> None:
    result = analyse_image(Image.new("RGB", (1800, 900), "grey"), colour_clusters=3)
    assert result.image.size == (1800, 900)
    assert result.greyscale.shape == (600, 1200)
    assert result.map_at_image_size(result.importance_map).shape == (900, 1800)


def test_user_masks_add_and_subtract_importance(analysis) -> None:  # type: ignore[no-untyped-def]
    additive = np.zeros((48, 64), dtype=np.float32); additive[:, :20] = 1
    subtractive = np.zeros((48, 64), dtype=np.float32); subtractive[:, 40:] = 1
    edited = analysis.with_user_masks(additive=additive, subtractive=subtractive)
    assert float(edited.importance_map[:, :20].mean()) >= float(analysis.importance_map[:, :20].mean())
    assert float(edited.importance_map[:, 40:].mean()) <= float(analysis.importance_map[:, 40:].mean())


def test_invalid_user_mask_shape_is_rejected(analysis) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="must match"):
        analysis.with_user_masks(additive=np.zeros((2, 2), dtype=np.float32))


@pytest.mark.parametrize("name", ["Edge Map", "Importance Map", "Face Mask", "Background Mask", "Saliency", "Colour Clusters", "Texture", "Subject Mask"])
def test_all_developer_views_render(analysis, name: str) -> None:  # type: ignore[no-untyped-def]
    image = analysis.debug_image(name)
    assert image.size == (64, 48)
    assert image.mode == "RGB"
