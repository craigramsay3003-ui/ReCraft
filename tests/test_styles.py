import numpy as np
import pytest
from PIL import Image

from recraft.core.style_registry import create_default_registry


@pytest.fixture
def sample_image() -> Image.Image:
    y, x = np.mgrid[0:48, 0:64]
    array = np.stack(((x * 4) % 256, (y * 5) % 256, ((x + y) * 3) % 256), axis=-1).astype(np.uint8)
    return Image.fromarray(array, "RGB")


@pytest.mark.parametrize("style", list(create_default_registry()), ids=lambda style: style.identifier)
def test_every_style_produces_valid_image(style, sample_image: Image.Image) -> None:
    result = style.process(sample_image)
    assert result.size == sample_image.size
    assert result.mode == "RGB"


@pytest.mark.parametrize("style", list(create_default_registry()), ids=lambda style: style.identifier)
def test_parameter_validation_rejects_out_of_range(style) -> None:
    parameter = style.parameters[0]
    with pytest.raises(ValueError, match="must be between"):
        style.validate_parameters({parameter.key: parameter.maximum + 1})


def test_parameter_validation_rejects_unknown_parameter() -> None:
    style = next(iter(create_default_registry()))
    with pytest.raises(ValueError, match="Unknown parameter"):
        style.validate_parameters({"surprise": 1})
