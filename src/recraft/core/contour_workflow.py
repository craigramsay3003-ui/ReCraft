"""Guided Contour workflow state and stage invalidation rules."""

from dataclasses import dataclass, field
from enum import IntEnum

from recraft.exporters.contour_mesh import ReliefColours


class ContourStage(IntEnum):
    """Ordered stages in the guided Contour experience."""

    PREPARE = 0
    IMPORTANCE = 1
    DESIGN = 2
    RELIEF = 3
    EXPORT = 4


@dataclass
class ContourWorkflowState:
    """Preserve session choices and invalidate only dependent products."""

    stage: ContourStage = ContourStage.PREPARE
    colours: ReliefColours = field(default_factory=ReliefColours)
    analysis_valid: bool = False
    contour_valid: bool = False
    mesh_valid: bool = False
    advanced_expanded: bool = False

    def next(self) -> ContourStage:
        """Advance one stage without losing settings."""
        self.stage = ContourStage(min(int(self.stage) + 1, int(ContourStage.EXPORT)))
        return self.stage

    def back(self) -> ContourStage:
        """Return one stage without losing settings."""
        self.stage = ContourStage(max(int(self.stage) - 1, int(ContourStage.PREPARE)))
        return self.stage

    def invalidate_preparation(self) -> None:
        """Preparation changes invalidate analysis, paths, and mesh."""
        self.analysis_valid = self.contour_valid = self.mesh_valid = False

    def invalidate_importance(self) -> None:
        """Importance changes preserve preparation but invalidate paths onward."""
        self.analysis_valid = True; self.contour_valid = self.mesh_valid = False

    def invalidate_contours(self) -> None:
        """Art changes preserve analysis but invalidate paths and mesh."""
        self.contour_valid = self.mesh_valid = False

    def invalidate_relief(self) -> None:
        """Relief changes invalidate only mesh geometry."""
        self.mesh_valid = False

    def set_colours(self, colours: ReliefColours) -> None:
        """Update preview/export materials without invalidating geometry."""
        self.colours = colours.validated()
