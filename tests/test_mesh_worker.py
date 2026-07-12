from pathlib import Path

import numpy as np
from PIL import Image

from recraft.core.image_transform import ImageTransformSettings
from recraft.exporters.contour_mesh import ContourMeshSettings
from recraft.styles.contour import ContourStyle
from recraft.ui.mesh_worker import MeshWorker


def test_background_mesh_worker_exports_watertight_stl(tmp_path: Path) -> None:
    y, x = np.mgrid[0:80, 0:120]
    image = Image.fromarray(np.stack((x * 2, y * 3, (x + y) % 255), axis=-1).astype(np.uint8), "RGB")
    path = tmp_path / "worker.stl"; exported: list[tuple] = []; errors: list[str] = []
    worker = MeshWorker(image, ImageTransformSettings(output_width=240, output_height=160), None, ContourStyle().defaults(), ContourMeshSettings(resolution=45), str(path))
    worker.exported.connect(lambda *values: exported.append(values)); worker.failed.connect(errors.append); worker.run()
    assert not errors and exported and exported[0][-1] is True and path.is_file()
