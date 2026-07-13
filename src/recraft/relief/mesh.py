"""Efficient watertight plaque meshes from normalized height fields."""

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import trimesh

from recraft.relief.presets import ReliefSettings


MAX_PREVIEW_TRIANGLES = 150_000
MAX_EXPORT_TRIANGLES = 350_000


@dataclass(frozen=True)
class ReliefMeshResult:
    """Printable mesh plus UI/export diagnostics."""

    mesh: trimesh.Trimesh
    width_mm: float
    height_mm: float
    watertight: bool
    ridge_height_range: tuple[float, float]
    relief_map: np.ndarray
    triangle_count: int
    estimated_memory_mb: float


def expected_triangle_count(width: int, height: int) -> int:
    """Return the exact structured-plaque triangle count."""
    return 4 * (width - 1) * (height - 1) + 4 * width + 4 * height - 8


def build_relief_mesh(height_values: np.ndarray, settings: ReliefSettings, *, preview: bool) -> ReliefMeshResult:
    """Build positive front relief, flat rear, and closed side walls."""
    state = settings.validated(); height = np.asarray(height_values, np.float32)
    if height.ndim != 2 or min(height.shape) < 2: raise ValueError("Height map must be a two-dimensional surface")
    if not np.isfinite(height).all(): raise ValueError("Height map contains invalid values")
    height = np.clip(height, 0, 1); ny, nx = height.shape; triangles = expected_triangle_count(nx, ny)
    limit = MAX_PREVIEW_TRIANGLES if preview else MAX_EXPORT_TRIANGLES
    if triangles > limit: raise ValueError(f"Relief would contain {triangles:,} triangles, above the safe {'preview' if preview else 'export'} limit of {limit:,}")
    physical_height = state.physical_width_mm * ny / nx
    xs = np.linspace(0, state.physical_width_mm, nx); ys = np.linspace(0, physical_height, ny); xx, yy = np.meshgrid(xs, ys)
    # Image top becomes Cartesian +Y; X remains unchanged, preserving left/right.
    field = np.flipud(height); top_z = state.base_thickness_mm + field * state.relief_depth_mm
    top = np.column_stack((xx.ravel(), yy.ravel(), top_z.ravel())); bottom = np.column_stack((xx.ravel(), yy.ravel(), np.zeros(nx * ny))); vertices = np.vstack((top, bottom))
    cell_y, cell_x = np.mgrid[0:ny - 1, 0:nx - 1]; a = (cell_y * nx + cell_x).ravel(); b = a + 1; d = a + nx; c = d + 1; offset = nx * ny
    faces = np.vstack((np.column_stack((a, b, c)), np.column_stack((a, c, d)), np.column_stack((offset + a, offset + c, offset + b)), np.column_stack((offset + a, offset + d, offset + c))))
    boundary = list(range(nx)) + [j * nx + nx - 1 for j in range(1, ny)] + list(range((ny - 1) * nx + nx - 2, (ny - 1) * nx - 1, -1)) + [j * nx for j in range(ny - 2, 0, -1)]
    edge = np.asarray(boundary, np.int64); next_edge = np.roll(edge, -1); sides = np.vstack((np.column_stack((edge, offset + next_edge, next_edge)), np.column_stack((edge, offset + edge, offset + next_edge))))
    faces = np.vstack((faces, sides)).astype(np.int64, copy=False); mesh = trimesh.Trimesh(vertices, faces, process=False)
    if not mesh.is_watertight: raise ValueError("Relief plaque could not be closed into a watertight mesh")
    memory = (vertices.nbytes + faces.nbytes + field.nbytes) / (1024 * 1024)
    return ReliefMeshResult(mesh, state.physical_width_mm, physical_height, True, (float(field.min() * state.relief_depth_mm), float(field.max() * state.relief_depth_mm)), field.copy(), len(faces), memory)


def export_relief_stl(result: ReliefMeshResult, path: str | Path) -> None:
    """Save one millimetre-scale watertight geometry-only STL."""
    result.mesh.export(str(path), file_type="stl")


def export_relief_3mf(result: ReliefMeshResult, path: str | Path, colour: str = "#D99A52") -> None:
    """Save one reliable coloured 3MF model in millimetres."""
    namespace = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"; ET.register_namespace("", namespace)
    model = ET.Element(f"{{{namespace}}}model", {"unit": "millimeter", "xml:lang": "en-US"}); resources = ET.SubElement(model, f"{{{namespace}}}resources")
    materials = ET.SubElement(resources, f"{{{namespace}}}basematerials", {"id": "1"}); ET.SubElement(materials, f"{{{namespace}}}base", {"name": "Relief", "displaycolor": colour.upper() + "FF"})
    obj = ET.SubElement(resources, f"{{{namespace}}}object", {"id": "2", "type": "model", "name": "ReCraft Printable Relief", "pid": "1", "pindex": "0"}); mesh_node = ET.SubElement(obj, f"{{{namespace}}}mesh")
    vertices_node = ET.SubElement(mesh_node, f"{{{namespace}}}vertices")
    for x, y, z in result.mesh.vertices: ET.SubElement(vertices_node, f"{{{namespace}}}vertex", {"x": f"{x:.6f}", "y": f"{y:.6f}", "z": f"{z:.6f}"})
    triangles_node = ET.SubElement(mesh_node, f"{{{namespace}}}triangles")
    for a, b, c in result.mesh.faces: ET.SubElement(triangles_node, f"{{{namespace}}}triangle", {"v1": str(a), "v2": str(b), "v3": str(c)})
    build = ET.SubElement(model, f"{{{namespace}}}build"); ET.SubElement(build, f"{{{namespace}}}item", {"objectid": "2"})
    types = '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>'
    rels = '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
    with ZipFile(path, "w", ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", types); package.writestr("_rels/.rels", rels); package.writestr("3D/3dmodel.model", ET.tostring(model, encoding="utf-8", xml_declaration=True))
