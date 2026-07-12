from dataclasses import replace

import numpy as np
import pytest

from recraft.core.image_transform import FitMode, ImageTransformSettings
from recraft.engine.colour_selection import select_similar_colour
from recraft.engine.region_selection import select_connected_region
from recraft.engine.user_importance import BrushMode, UserImportanceState, canvas_to_source, combine_importance, render_source_mask


def test_add_reduce_and_erase_brush_masks() -> None:
    state = UserImportanceState.create((200, 100))
    state.paint_source(0.5, 0.5, 0.1, 0.8, BrushMode.ADD)
    assert state.add_mask.max() > 0.75 and state.reduce_mask.max() == 0
    state.paint_source(0.5, 0.5, 0.1, 1, BrushMode.REDUCE)
    assert state.reduce_mask.max() == 1 and state.add_mask[state.mask_size[1] // 2, state.mask_size[0] // 2] == 0
    state.paint_source(0.5, 0.5, 0.1, 1, BrushMode.ERASE)
    assert state.reduce_mask[state.mask_size[1] // 2, state.mask_size[0] // 2] == 0


def test_painting_never_changes_source_image() -> None:
    source = np.full((30, 40, 3), 127, np.uint8); before = source.copy()
    state = UserImportanceState.create((40, 30)); state.paint_source(.2, .8, .1, 1, BrushMode.ADD)
    assert np.array_equal(source, before)


@pytest.mark.parametrize("settings", [
    ImageTransformSettings(output_width=160, output_height=120, fit_mode=FitMode.FILL),
    ImageTransformSettings(output_width=160, output_height=120, zoom=1.7, pan_x=.3, pan_y=-.2),
    ImageTransformSettings(output_width=160, output_height=120, rotation_quarters=1),
    ImageTransformSettings(output_width=160, output_height=120, rotation_quarters=3, flip_horizontal=True, flip_vertical=True),
])
def test_mask_alignment_after_transformations(settings: ImageTransformSettings) -> None:
    state = UserImportanceState.create((200, 100)); state.paint_source(.5, .5, .04, 1, BrushMode.ADD)
    rendered = render_source_mask(state.add_mask, settings, (160, 120))
    ys, xs = np.where(rendered > .5); assert len(xs)
    mapped = canvas_to_source((float(xs.mean()), float(ys.mean())), (200, 100), settings, (160, 120))
    assert mapped is not None and mapped[0] == pytest.approx(.5, abs=.04) and mapped[1] == pytest.approx(.5, abs=.04)


def test_colour_tolerance_and_connected_only() -> None:
    rgb = np.zeros((20, 30, 3), np.uint8); rgb[:, :10] = (200, 20, 20); rgb[:, 10:20] = (205, 25, 25); rgb[:, 20:] = (20, 20, 200)
    loose = select_similar_colour(rgb, (5, 5), 15); tight = select_similar_colour(rgb, (5, 5), 2)
    assert loose[:, 15].mean() > tight[:, 15].mean(); assert loose[:, 25].max() == 0
    rgb[:, 14:16] = 0
    connected = select_similar_colour(rgb, (5, 5), 20, connected_only=True)
    assert connected[:, 18].max() == 0


def test_region_selection_stays_connected() -> None:
    rgb = np.zeros((30, 30, 3), np.uint8); rgb[2:12, 2:12] = (220, 40, 40); rgb[18:28, 18:28] = (220, 40, 40)
    mask = select_connected_region(rgb, (5, 5), 8, 0)
    assert mask[5, 5] == 1 and mask[22, 22] == 0


def test_combined_importance_is_normalized_and_user_override_wins() -> None:
    automatic = np.full((10, 10), .9, np.float32); add = np.zeros_like(automatic); reduce = np.ones_like(automatic); background = np.ones_like(automatic)
    combined = combine_importance(automatic, add, reduce, background, 1, 2, 1)
    assert combined.min() == combined.max() == 0
    add.fill(1); reduce.fill(0)
    combined = combine_importance(automatic * 0, add, reduce, background * 0, .2, 2, 0)
    assert combined.min() == combined.max() == 1
