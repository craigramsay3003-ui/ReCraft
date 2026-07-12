"""Watertight raised-ridge meshes generated directly from Contour paths."""

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import trimesh

from recraft.styles.contour_geometry import ContourResult


@dataclass(frozen=True)
class ContourMeshSettings:
    """Physical raised-ridge settings in millimetres."""

    physical_width: float = 150.0
    base_thickness: float = 2.0
    ridge_height: float = 1.2
    ridge_width: float = 1.2
    border_width: float = 3.0
    resolution: int = 160
    minimum_feature_width: float = 0.8

    def validated(self) -> "ContourMeshSettings":
        """Validate printable physical dimensions."""
        if not 20 <= self.physical_width <= 1000: raise ValueError("Physical width must be between 20 and 1000 mm")
        if not 0.4 <= self.base_thickness <= 20: raise ValueError("Base thickness must be between 0.4 and 20 mm")
        if not 0.2 <= self.ridge_height <= 20: raise ValueError("Ridge height must be between 0.2 and 20 mm")
        if not self.minimum_feature_width <= self.ridge_width <= 20: raise ValueError("Ridge width must meet the minimum printable feature width")
        if not 0 <= self.border_width <= 50: raise ValueError("Border width must be between 0 and 50 mm")
        if not 40 <= self.resolution <= 500: raise ValueError("Mesh resolution must be between 40 and 500")
        return self


@dataclass(frozen=True)
class ContourMeshResult:
    """Validated mesh plus physical summary."""

    mesh: trimesh.Trimesh
    width_mm: float
    height_mm: float
    watertight: bool


def build_contour_mesh(result: ContourResult, settings: ContourMeshSettings) -> ContourMeshResult:
    """Create a continuous watertight ridge solid directly from paths."""
    state = settings.validated()
    if not result.paths: raise ValueError("Contour result contains no printable paths")
    inner_w = state.physical_width; inner_h = inner_w / result.source_aspect_ratio
    total_w = inner_w + 2 * state.border_width; total_h = inner_h + 2 * state.border_width
    nx = state.resolution; ny = max(20, round(nx * total_h / total_w))
    ridge = np.zeros((ny, nx), np.uint8)
    sx = (nx - 1) * inner_w / total_w / max(result.width - 1, 1)
    sy = (ny - 1) * inner_h / total_h / max(result.height - 1, 1)
    ox = (nx - 1) * state.border_width / total_w; oy = (ny - 1) * state.border_width / total_h
    pixel_mm = total_w / (nx - 1); thickness = max(1, round(state.ridge_width / pixel_mm))
    for path in result.paths:
        points = np.asarray([(ox + x * sx, oy + y * sy) for x, y in path.points], np.int32).reshape(-1, 1, 2)
        cv2.polylines(ridge, [points], path.closed, 255, thickness, cv2.LINE_AA)
    top_z = state.base_thickness + (ridge.astype(np.float64) / 255.0) * state.ridge_height
    xs = np.linspace(0, total_w, nx); ys = np.linspace(0, total_h, ny)
    vertices = [[x, y, top_z[j, i]] for j, y in enumerate(ys) for i, x in enumerate(xs)]
    vertices += [[x, y, 0.0] for j, y in enumerate(ys) for i, x in enumerate(xs)]
    faces: list[tuple[int, int, int]] = []; offset = nx * ny
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i; b = a + 1; d = (j + 1) * nx + i; c = d + 1
            faces.extend(((a, b, c), (a, c, d), (offset + a, offset + c, offset + b), (offset + a, offset + d, offset + c)))
    boundary = list(range(nx)) + [j * nx + nx - 1 for j in range(1, ny)] + list(range((ny - 1) * nx + nx - 2, (ny - 1) * nx - 1, -1)) + [j * nx for j in range(ny - 2, 0, -1)]
    for index, a in enumerate(boundary):
        b = boundary[(index + 1) % len(boundary)]
        faces.extend(((a, offset + b, b), (a, offset + a, offset + b)))
    mesh = trimesh.Trimesh(np.asarray(vertices), np.asarray(faces), process=True)
    if not mesh.is_watertight: raise ValueError("Contour geometry could not produce a watertight mesh")
    return ContourMeshResult(mesh, total_w, total_h, True)


def export_contour_stl(result: ContourResult, settings: ContourMeshSettings, path: str | Path) -> ContourMeshResult:
    """Build, validate, and save a Contour ridge STL."""
    mesh_result = build_contour_mesh(result, settings)
    mesh_result.mesh.export(str(path), file_type="stl")
    return mesh_result
