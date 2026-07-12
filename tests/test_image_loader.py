from pathlib import Path

import pytest
from PIL import Image

from recraft.core.image_loader import ImageLoadError, load_image


def test_load_valid_image(tmp_path: Path) -> None:
    path = tmp_path / "source.png"
    Image.new("RGBA", (12, 8), (10, 20, 30, 128)).save(path)
    result = load_image(path)
    assert result.size == (12, 8)
    assert result.mode == "RGB"


def test_invalid_path_has_useful_exception(tmp_path: Path) -> None:
    with pytest.raises(ImageLoadError, match="does not exist"):
        load_image(tmp_path / "missing.png")
