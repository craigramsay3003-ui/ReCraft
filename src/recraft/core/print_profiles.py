"""Printer-profile defaults and actionable printability validation."""

from dataclasses import dataclass, replace
from enum import Enum


class PrintProfileName(str, Enum):
    """Available printer profile families."""

    BAMBU_H2C = "Bambu H2C"
    CUSTOM = "Custom printer"


@dataclass(frozen=True)
class PrintProfile:
    """Configurable manufacturing assumptions, not engine hard-coding."""

    name: PrintProfileName
    nozzle_diameter: float = .4
    layer_height: float = .2
    minimum_contour_width: float = .8
    minimum_height_change: float = .2
    recommended_base_thickness: float = 2.0
    recommended_ridge_width: float = 1.2
    recommended_width: float = 150
    mesh_resolution_limit: int = 260
    triangle_guidance: int = 160_000

    def customised(self, **changes: object) -> "PrintProfile":
        """Return a profile with user-selected hardware values."""
        return replace(self, **changes)


PROFILES = {
    PrintProfileName.BAMBU_H2C: PrintProfile(PrintProfileName.BAMBU_H2C),
    PrintProfileName.CUSTOM: PrintProfile(PrintProfileName.CUSTOM),
}


def validate_printability(profile: PrintProfile, *, minimum_width: float, height_range: tuple[float, float], base_thickness: float, mesh_resolution: int, triangle_count: int, physical_width: float) -> list[str]:
    """Return actionable warnings for likely manufacturing problems."""
    warnings: list[str] = []
    if minimum_width < max(profile.minimum_contour_width, profile.nozzle_diameter * 1.5): warnings.append("Contours may be narrower than the selected nozzle can reproduce; increase minimum width or use a smaller nozzle.")
    if height_range[1] - height_range[0] < max(profile.minimum_height_change, profile.layer_height): warnings.append("Relief variation is below one reliable layer step; increase maximum height or reduce layer height.")
    if base_thickness < profile.recommended_base_thickness: warnings.append("Base may be too thin; increase base thickness to reduce warping.")
    if mesh_resolution > profile.mesh_resolution_limit or triangle_count > profile.triangle_guidance: warnings.append("Mesh complexity is high for this profile; lower Final mesh quality or simplify paths.")
    if physical_width < 60: warnings.append("Physical width may make important details too small; increase artwork width.")
    return warnings
