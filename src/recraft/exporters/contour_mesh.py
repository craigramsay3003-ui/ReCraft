"""Watertight raised-ridge meshes generated directly from Contour paths."""

from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET

import cv2
import numpy as np
import trimesh
from PIL import Image

from recraft.styles.contour_geometry import ContourResult


@dataclass(frozen=True)
class ContourMeshSettings:
    """Physical raised-ridge settings in millimetres."""

    physical_width: float = 150.0
    base_thickness: float = 2.0
    minimum_contour_height: float = 0.4
    maximum_contour_height: float = 1.8
    ridge_width: float = 1.2
    minimum_ridge_width: float = 0.8
    maximum_ridge_width: float = 1.8
    width_variation_strength: float = 0.5
    uniform_width: bool = False
    border_width: float = 3.0
    resolution: int = 160
    minimum_feature_width: float = 0.8
    relief_strength: float = 1.0
    height_smoothing: float = 0.6
    background_relief_reduction: float = 0.55
    uniform_height: bool = False
    orientation_marker: bool = False
    maximum_paths: int = 12_000
    maximum_sampled_points: int = 300_000
    maximum_triangles: int = 250_000
    maximum_estimated_memory_mb: float = 256.0

    def validated(self) -> "ContourMeshSettings":
        """Validate printable physical dimensions."""
        if not 20 <= self.physical_width <= 1000: raise ValueError("Physical width must be between 20 and 1000 mm")
        if not 0.4 <= self.base_thickness <= 20: raise ValueError("Base thickness must be between 0.4 and 20 mm")
        if not 0.1 <= self.minimum_contour_height <= self.maximum_contour_height: raise ValueError("Minimum contour height must be positive and no greater than maximum contour height")
        if self.maximum_contour_height > 20: raise ValueError("Maximum contour height must not exceed 20 mm")
        if not self.minimum_feature_width <= self.ridge_width <= 20: raise ValueError("Ridge width must meet the minimum printable feature width")
        if not self.minimum_feature_width <= self.minimum_ridge_width <= self.maximum_ridge_width <= 20: raise ValueError("Contour width range must respect the minimum printable feature width")
        if not 0 <= self.width_variation_strength <= 1: raise ValueError("Width variation strength must be between 0 and 1")
        if not 0 <= self.border_width <= 50: raise ValueError("Border width must be between 0 and 50 mm")
        if not 40 <= self.resolution <= 500: raise ValueError("Mesh resolution must be between 40 and 500")
        if self.maximum_paths < 100 or self.maximum_sampled_points < 1_000: raise ValueError("Mesh path and sampling limits are too small")
        if self.maximum_triangles < 10_000 or self.maximum_estimated_memory_mb < 32: raise ValueError("Mesh safety budgets are too small")
        if not 0.1 <= self.relief_strength <= 4: raise ValueError("Relief strength must be between 0.1 and 4")
        if not 0 <= self.height_smoothing <= 3: raise ValueError("Height smoothing must be between 0 and 3")
        if not 0 <= self.background_relief_reduction <= 1: raise ValueError("Background relief reduction must be between 0 and 1")
        return self


@dataclass(frozen=True)
class ReliefColours:
    """Independent base and Contour colours stored as #RRGGBB."""

    base: str = "#30343B"
    contour: str = "#F0B44C"

    def validated(self) -> "ReliefColours":
        """Validate both readable hexadecimal colour values."""
        import re
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", self.base) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", self.contour):
            raise ValueError("Base and Contour colours must use #RRGGBB format")
        return self


@dataclass(frozen=True)
class ContourMeshResult:
    """Validated mesh plus physical summary."""

    mesh: trimesh.Trimesh
    width_mm: float
    height_mm: float
    watertight: bool
    ridge_height_range: tuple[float, float]
    relief_map: np.ndarray
    retained_path_count: int = 0
    sampled_point_count: int = 0
    estimated_memory_mb: float = 0.0
    warnings: tuple[str, ...] = ()


class MeshComplexityError(ValueError):
    """Raised before allocation when requested mesh complexity is unsafe."""


def estimate_mesh_resources(nx: int, ny: int) -> tuple[int, int, float]:
    """Return projected vertex/face counts and working memory in MiB."""
    vertices = 2 * nx * ny
    faces = 4 * (nx - 1) * (ny - 1) + 2 * (2 * nx + 2 * ny - 4)
    bytes_required = vertices * 3 * 8 + faces * 3 * 8 + nx * ny * 24
    return vertices, faces, bytes_required / (1024 * 1024)


def build_contour_mesh(result: ContourResult, settings: ContourMeshSettings) -> ContourMeshResult:
    """Create a continuous watertight ridge solid directly from paths."""
    state = settings.validated()
    if not result.paths: raise ValueError("Contour result contains no printable paths")
    inner_w = state.physical_width; inner_h = inner_w / result.source_aspect_ratio
    total_w = inner_w + 2 * state.border_width; total_h = inner_h + 2 * state.border_width
    nx = state.resolution; ny = max(20, round(nx * total_h / total_w))
    projected_vertices, projected_faces, estimated_memory = estimate_mesh_resources(nx, ny)
    if projected_faces > state.maximum_triangles:
        raise MeshComplexityError(f"Mesh would contain about {projected_faces:,} triangles, above the safe limit of {state.maximum_triangles:,}. Lower mesh quality or use a simpler preset.")
    if estimated_memory > state.maximum_estimated_memory_mb:
        raise MeshComplexityError(f"Mesh needs about {estimated_memory:.1f} MB, above the safe limit of {state.maximum_estimated_memory_mb:.1f} MB. Lower mesh quality.")
    ridge = np.zeros((ny, nx), np.float32)
    sx = (nx - 1) * inner_w / total_w / max(result.width - 1, 1)
    sy = (ny - 1) * inner_h / total_h / max(result.height - 1, 1)
    ox = (nx - 1) * state.border_width / total_w; oy = (ny - 1) * state.border_width / total_h
    pixel_mm = total_w / (nx - 1); thickness = max(1, round(state.ridge_width / pixel_mm))
    warnings: list[str] = []
    selected_paths = list(result.paths)
    if len(selected_paths) > state.maximum_paths:
        selected_paths = sorted(selected_paths, key=lambda path: (path.importance + path.peak_importance, path.length), reverse=True)[:state.maximum_paths]
        warnings.append(f"Retained the {state.maximum_paths:,} most important paths from {len(result.paths):,} to stay within the safe path budget.")
    total_points = sum(len(path.points) for path in selected_paths)
    point_stride = max(1, int(np.ceil(total_points / state.maximum_sampled_points)))
    if point_stride > 1: warnings.append(f"Sampled every {point_stride}th path point to stay within the safe point budget.")
    sampled_points = 0
    for path in selected_paths:
        # Image X is retained; image Y is inverted into Cartesian +Y.
        indexes = list(range(0, len(path.points), point_stride))
        if len(path.points) > 1 and indexes[-1] != len(path.points) - 1: indexes.append(len(path.points) - 1)
        sampled_points += len(indexes)
        points = np.asarray([(ox + path.points[i][0] * sx, (ny - 1) - (oy + path.points[i][1] * sy)) for i in indexes], np.float32)
        original_values = path.relief_values or tuple(path.importance for _ in path.points)
        original_widths = path.width_values or tuple(1.0 for _ in path.points)
        values = tuple(original_values[min(i, len(original_values) - 1)] for i in indexes)
        widths = tuple(original_widths[min(i, len(original_widths) - 1)] for i in indexes)
        if state.uniform_height: values = tuple(1.0 for _ in path.points)
        for index in range(max(0, len(points) - 1)):
            value = (values[min(index, len(values) - 1)] + values[min(index + 1, len(values) - 1)]) / 2
            value *= 1.0 - state.background_relief_reduction * path.background_membership
            value = float(np.clip(value, 0, 1)) ** state.relief_strength
            if state.uniform_width:
                segment_width = state.ridge_width
            else:
                factor = (widths[min(index, len(widths) - 1)] + widths[min(index + 1, len(widths) - 1)]) / 2
                factor = 1 + (factor - 1) * state.width_variation_strength
                normalized = np.clip((factor - .5), 0, 1)
                segment_width = state.minimum_ridge_width + normalized * (state.maximum_ridge_width - state.minimum_ridge_width)
            segment_thickness = max(1, round(max(state.minimum_feature_width, segment_width) / pixel_mm))
            cv2.line(ridge, tuple(np.rint(points[index]).astype(int)), tuple(np.rint(points[index + 1]).astype(int)), value, segment_thickness, cv2.LINE_AA)
        if path.closed and len(points) > 2:
            cv2.line(ridge, tuple(np.rint(points[-1]).astype(int)), tuple(np.rint(points[0]).astype(int)), float(np.mean(values)), thickness, cv2.LINE_AA)
    if state.orientation_marker:
        cv2.arrowedLine(ridge, (max(2, round(ox)), ny - max(3, round(oy)) - 2), (max(8, round(ox)) + 12, ny - max(3, round(oy)) - 2), 1.0, max(1, thickness), tipLength=.35)
    if state.height_smoothing > 0 and np.any(ridge):
        blurred = cv2.GaussianBlur(ridge, (0, 0), state.height_smoothing)
        ridge = np.where(ridge > 0, np.maximum(ridge * .65, blurred), 0)
    height_span = state.maximum_contour_height - state.minimum_contour_height
    relief_height = np.where(ridge > 0, state.minimum_contour_height + ridge * height_span, 0)
    top_z = state.base_thickness + relief_height.astype(np.float64)
    xs = np.linspace(0, total_w, nx); ys = np.linspace(0, total_h, ny)
    xx, yy = np.meshgrid(xs, ys)
    top_vertices = np.column_stack((xx.ravel(), yy.ravel(), top_z.ravel()))
    bottom_vertices = np.column_stack((xx.ravel(), yy.ravel(), np.zeros(nx * ny)))
    vertices = np.vstack((top_vertices, bottom_vertices))
    offset = nx * ny
    cell_y, cell_x = np.mgrid[0:ny - 1, 0:nx - 1]; a = (cell_y * nx + cell_x).ravel(); b = a + 1; d = a + nx; c = d + 1
    faces = np.vstack((np.column_stack((a, b, c)), np.column_stack((a, c, d)), np.column_stack((offset + a, offset + c, offset + b)), np.column_stack((offset + a, offset + d, offset + c))))
    boundary = list(range(nx)) + [j * nx + nx - 1 for j in range(1, ny)] + list(range((ny - 1) * nx + nx - 2, (ny - 1) * nx - 1, -1)) + [j * nx for j in range(ny - 2, 0, -1)]
    boundary_array = np.asarray(boundary, dtype=np.int64); boundary_next = np.roll(boundary_array, -1)
    side_faces = np.vstack((np.column_stack((boundary_array, offset + boundary_next, boundary_next)), np.column_stack((boundary_array, offset + boundary_array, offset + boundary_next))))
    faces = np.vstack((faces, side_faces)).astype(np.int64, copy=False)
    mesh = trimesh.Trimesh(vertices, faces, process=False)
    if not mesh.is_watertight: raise ValueError("Contour geometry could not produce a watertight mesh")
    used = relief_height[relief_height > 0]
    height_range = (float(used.min()), float(used.max())) if used.size else (0.0, 0.0)
    return ContourMeshResult(mesh, total_w, total_h, True, height_range, relief_height.astype(np.float32), len(selected_paths), sampled_points, estimated_memory, tuple(warnings))


def export_contour_stl(result: ContourResult, settings: ContourMeshSettings, path: str | Path) -> ContourMeshResult:
    """Build, validate, and save a Contour ridge STL."""
    mesh_result = build_contour_mesh(result, settings)
    mesh_result.mesh.export(str(path), file_type="stl")
    return mesh_result


def export_contour_3mf(result: ContourResult, settings: ContourMeshSettings, colours: ReliefColours, path: str | Path) -> ContourMeshResult:
    """Export a coloured 3MF with separate base/Contour material assignments."""
    colours = colours.validated(); mesh_result = build_contour_mesh(result, settings); mesh = mesh_result.mesh
    namespace = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    ET.register_namespace("", namespace)
    model = ET.Element(f"{{{namespace}}}model", {"unit": "millimeter", "xml:lang": "en-US"})
    resources = ET.SubElement(model, f"{{{namespace}}}resources")
    materials = ET.SubElement(resources, f"{{{namespace}}}basematerials", {"id": "1"})
    ET.SubElement(materials, f"{{{namespace}}}base", {"name": "Base", "displaycolor": colours.base.upper() + "FF"})
    ET.SubElement(materials, f"{{{namespace}}}base", {"name": "Contour Relief", "displaycolor": colours.contour.upper() + "FF"})
    obj = ET.SubElement(resources, f"{{{namespace}}}object", {"id": "2", "type": "model", "name": "ReCraft Contour Relief"})
    mesh_node = ET.SubElement(obj, f"{{{namespace}}}mesh"); vertices_node = ET.SubElement(mesh_node, f"{{{namespace}}}vertices")
    for x, y, z in mesh.vertices: ET.SubElement(vertices_node, f"{{{namespace}}}vertex", {"x": f"{x:.6f}", "y": f"{y:.6f}", "z": f"{z:.6f}"})
    triangles_node = ET.SubElement(mesh_node, f"{{{namespace}}}triangles")
    for face in mesh.faces:
        contour_face = bool(np.max(mesh.vertices[face, 2]) > settings.base_thickness + 1e-6)
        ET.SubElement(triangles_node, f"{{{namespace}}}triangle", {"v1": str(face[0]), "v2": str(face[1]), "v3": str(face[2]), "pid": "1", "p1": "1" if contour_face else "0"})
    build = ET.SubElement(model, f"{{{namespace}}}build"); ET.SubElement(build, f"{{{namespace}}}item", {"objectid": "2"})
    content_types = '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>'
    relationships = '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
    with ZipFile(path, "w", ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", content_types); package.writestr("_rels/.rels", relationships)
        package.writestr("3D/3dmodel.model", ET.tostring(model, encoding="utf-8", xml_declaration=True))
    return mesh_result


def render_relief_preview(mesh_result: ContourMeshResult, colours: ReliefColours, size: tuple[int, int] = (640, 420)) -> Image.Image:
    """Render a fast perspective-shaded preview from the actual relief map."""
    colours = colours.validated(); height = mesh_result.relief_map
    base_rgb = np.array([int(colours.base[index:index + 2], 16) for index in (1, 3, 5)], np.float32)
    contour_rgb = np.array([int(colours.contour[index:index + 2], 16) for index in (1, 3, 5)], np.float32)
    gy, gx = np.gradient(height); light = np.clip(.78 - gx * .35 + gy * .25, .35, 1.15)
    raised = np.clip(height / max(float(height.max()), 1e-6), 0, 1)[..., None]
    surface = (base_rgb * (1 - raised) + contour_rgb * raised) * light[..., None]
    surface = np.clip(surface, 0, 255).astype(np.uint8)
    target_w, target_h = size; margin = 24
    source = np.array([[0, 0], [surface.shape[1] - 1, 0], [surface.shape[1] - 1, surface.shape[0] - 1], [0, surface.shape[0] - 1]], np.float32)
    destination = np.array([[margin + 45, margin], [target_w - margin, margin + 35], [target_w - margin - 45, target_h - margin - 20], [margin, target_h - margin - 55]], np.float32)
    transform = cv2.getPerspectiveTransform(source, destination)
    canvas = np.full((target_h, target_w, 3), (21, 24, 29), np.uint8)
    warped = cv2.warpPerspective(surface, transform, (target_w, target_h)); mask = cv2.warpPerspective(np.full(height.shape, 255, np.uint8), transform, (target_w, target_h))
    canvas[mask > 0] = warped[mask > 0]
    return Image.fromarray(canvas, "RGB")
