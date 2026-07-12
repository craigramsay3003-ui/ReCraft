"""Headless tests for preview-workspace models."""

import numpy as np

from recraft.core.contour_presets import ContourPresetName, PRESETS, PresetState
from recraft.core.mesh_camera import MeshCamera, ProjectionMode
from recraft.core.print_profiles import PROFILES, PrintProfileName, validate_printability
from recraft.engine.focus_features import interpret_focus_description


def test_presets_have_meaningful_ordered_differences() -> None:
    detailed, standard, abstract = (PRESETS[name] for name in ContourPresetName)
    assert detailed.detail > standard.detail > abstract.detail
    assert detailed.mesh_resolution > standard.mesh_resolution > abstract.mesh_resolution
    assert detailed.simplification < standard.simplification < abstract.simplification
    assert abstract.background_reduction > standard.background_reduction > detailed.background_reduction


def test_preset_modified_and_reset() -> None:
    state = PresetState(); state.modify(detail=20)
    assert state.modified
    assert state.reset() == PRESETS[ContourPresetName.STANDARD]
    assert not state.modified


def test_focus_language_maps_only_supported_visual_features() -> None:
    intent = interpret_focus_description("Focus on the children's faces and dresses. Ignore the ceiling lights.")
    assert {"face", "subject", "silhouette"} <= intent.add_types
    assert {"background", "bright"} <= intent.reduce_types
    assert "prioritise" in intent.explanation


def test_camera_navigation_and_projection_do_not_mutate_geometry() -> None:
    camera = MeshCamera(); original = np.array([[0., 0., 0.], [1., 2., 3.]])
    camera.orbit(20, -10); camera.zoom(.8); camera.pan(.1, -.2); camera.set_view("Top")
    camera.projection = ProjectionMode.ORTHOGRAPHIC
    screen, depth = camera.project(original, (800, 600))
    assert screen.shape == (2, 2) and depth.shape == (2,)
    assert np.array_equal(original, np.array([[0., 0., 0.], [1., 2., 3.]]))
    camera.reset(); assert (camera.yaw, camera.pitch, camera.distance, camera.pan_x, camera.pan_y) == (-35, 55, 2.6, 0, 0)


def test_printer_profiles_and_nozzle_validation() -> None:
    assert PrintProfileName.BAMBU_H2C in PROFILES and PrintProfileName.CUSTOM in PROFILES
    profile = PROFILES[PrintProfileName.BAMBU_H2C].customised(nozzle_diameter=.8)
    warnings = validate_printability(profile, minimum_width=.8, height_range=(.4, .5), base_thickness=1, mesh_resolution=300, triangle_count=200_000, physical_width=50)
    assert len(warnings) >= 5
