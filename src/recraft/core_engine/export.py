"""Reliable geometry-first STL and limited-material 3MF export."""

from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np

from recraft.core_engine.models import ColourMapData, ColourMode, ReliefMeshData
from recraft.relief.mesh import export_relief_stl


def export_core_stl(mesh: ReliefMeshData, path: str | Path) -> None:
    """Export one watertight geometry-only millimetre STL."""
    export_relief_stl(mesh.result, path)


def _mean_colour(pixels: np.ndarray) -> str:
    mean = np.asarray(pixels, np.float32).reshape(-1, 3).mean(axis=0).astype(np.uint8)
    return "#" + "".join(f"{int(value):02X}" for value in mean)


def export_core_3mf(mesh_data: ReliefMeshData, path: str | Path) -> None:
    """Export one watertight object with reliable limited material metadata."""
    result = mesh_data.result
    colour = mesh_data.colour_map
    palette = colour.palette or (_mean_colour(colour.pixels),)
    # Original photographic colour is deliberately represented by one display
    # material. Artistic Palette carries its requested limited assignments.
    use_regions = colour.mode is ColourMode.ARTISTIC and len(palette) > 1
    base_index = len(palette)
    materials = (*palette, "#6F7378")

    namespace = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    ET.register_namespace("", namespace)
    model = ET.Element(f"{{{namespace}}}model", {"unit": "millimeter", "xml:lang": "en-US"})
    resources = ET.SubElement(model, f"{{{namespace}}}resources")
    material_node = ET.SubElement(resources, f"{{{namespace}}}basematerials", {"id": "1"})
    for index, value in enumerate(materials):
        ET.SubElement(material_node, f"{{{namespace}}}base", {"name": f"ReCraft {index + 1}", "displaycolor": value.upper() + "FF"})
    object_node = ET.SubElement(resources, f"{{{namespace}}}object", {"id": "2", "type": "model", "name": "ReCraft Portrait Relief"})
    mesh_node = ET.SubElement(object_node, f"{{{namespace}}}mesh")
    vertices_node = ET.SubElement(mesh_node, f"{{{namespace}}}vertices")
    vertices = np.asarray(result.mesh.vertices)
    for x, y, z in vertices:
        ET.SubElement(vertices_node, f"{{{namespace}}}vertex", {"x": f"{x:.6f}", "y": f"{y:.6f}", "z": f"{z:.6f}"})
    triangles_node = ET.SubElement(mesh_node, f"{{{namespace}}}triangles")
    rows, columns = colour.labels.shape
    top_count = rows * columns
    for face in np.asarray(result.mesh.faces, np.int64):
        material = base_index
        if np.all(face < top_count):
            if use_regions:
                centre = vertices[face].mean(axis=0)
                column = int(np.clip(round(centre[0] / result.width_mm * (columns - 1)), 0, columns - 1))
                row = int(np.clip(round((1 - centre[1] / result.height_mm) * (rows - 1)), 0, rows - 1))
                material = int(colour.labels[row, column])
            else:
                material = 0
        ET.SubElement(
            triangles_node,
            f"{{{namespace}}}triangle",
            {"v1": str(int(face[0])), "v2": str(int(face[1])), "v3": str(int(face[2])), "pid": "1", "p1": str(material)},
        )
    build = ET.SubElement(model, f"{{{namespace}}}build")
    ET.SubElement(build, f"{{{namespace}}}item", {"objectid": "2"})
    content_types = '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>'
    relationships = '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
    with ZipFile(path, "w", ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", content_types)
        package.writestr("_rels/.rels", relationships)
        package.writestr("3D/3dmodel.model", ET.tostring(model, encoding="utf-8", xml_declaration=True))
