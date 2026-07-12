import numpy as np
from PIL import Image

from recraft.engine import analyse_image
from recraft.styles.contour_geometry import ContourSettings, extract_contours, render_contours


def test_contour_path_extraction_filtering_and_rendering() -> None:
    y, x = np.mgrid[0:100, 0:140]
    grey = np.clip((x + y) * 1.1, 0, 255).astype(np.uint8)
    grey[45:50, 65:70] = 255  # isolated highlight should make tiny raw loops
    analysis = analyse_image(Image.fromarray(grey, "L").convert("RGB"))
    result = extract_contours(analysis, ContourSettings(detail=12, smoothing=2, simplification=1))
    assert result.raw_paths and result.paths
    assert len(result.paths) <= len(result.raw_paths)
    assert all(path.length >= 10 for path in result.paths)
    rendered = render_contours(result, 2)
    assert rendered.size == (140, 100) and rendered.mode == "RGB"


def test_simplification_reduces_path_points_and_background_suppression_filters() -> None:
    y, x = np.mgrid[0:100, 0:120]
    grey = ((np.sin(x / 5) + np.cos(y / 7) + 2) * 63).astype(np.uint8)
    analysis = analyse_image(Image.fromarray(grey, "L").convert("RGB"))
    simple = extract_contours(analysis, ContourSettings(detail=10, simplification=4, background_reduction=1))
    detailed = extract_contours(analysis, ContourSettings(detail=10, simplification=.1, background_reduction=0))
    assert sum(len(p.points) for p in simple.raw_paths) <= sum(len(p.points) for p in detailed.raw_paths)
    assert len(simple.paths) <= len(detailed.paths)
