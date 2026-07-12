from recraft.core.contour_workflow import ContourStage, ContourWorkflowState
from recraft.exporters.contour_mesh import ReliefColours


def test_forward_and_back_preserve_settings() -> None:
    state = ContourWorkflowState(); state.set_colours(ReliefColours("#112233", "#AABBCC"))
    assert state.next() is ContourStage.IMPORTANCE
    assert state.next() is ContourStage.DESIGN
    assert state.back() is ContourStage.IMPORTANCE
    assert state.colours == ReliefColours("#112233", "#AABBCC")


def test_advanced_defaults_collapsed_and_invalidation_is_staged() -> None:
    state = ContourWorkflowState(analysis_valid=True, contour_valid=True, mesh_valid=True)
    assert not state.advanced_expanded
    state.invalidate_relief(); assert state.analysis_valid and state.contour_valid and not state.mesh_valid
    state.mesh_valid = True; state.invalidate_contours(); assert state.analysis_valid and not state.contour_valid and not state.mesh_valid
    state.analysis_valid = state.contour_valid = state.mesh_valid = True
    state.invalidate_preparation(); assert not state.analysis_valid and not state.contour_valid and not state.mesh_valid


def test_colour_change_does_not_invalidate_geometry() -> None:
    state = ContourWorkflowState(analysis_valid=True, contour_valid=True, mesh_valid=True)
    state.set_colours(ReliefColours("#010203", "#F0E0D0"))
    assert state.analysis_valid and state.contour_valid and state.mesh_valid
