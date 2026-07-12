# Architecture

## UI layer

`recraft.ui` owns desktop interaction and image presentation. It asks the registry for style metadata and parameter definitions, so it contains no style-specific processing rules.

## Processing layer

`recraft.core` loads and normalises images. Each processor accepts a Pillow image plus a parameter mapping and returns a new Pillow image. This API is usable by future batch and command-line tools without starting the UI.

## Image preparation layer

The complete processing order is:

`imported image → image preparation → prepared working canvas → style processing → preview/export`

`ImageTransformSettings` stores pan, zoom, quarter-turn rotation, flips, target
aspect ratio, output dimensions, Fit/Fill mode, and aspect-lock state separately
from the imported image. `prepare_image` always regenerates a new RGB canvas
from the untouched source. Controls never progressively resize or overwrite the
source, which avoids cumulative quality loss.

The fixed output viewport acts as the crop frame. Fill covers it and crops any
overflow; Fit preserves the complete image and uses a white background where
necessary. Normalized pan values make the same composition reproducible at
different resolutions. The preparation layer has no PySide6 dependency.

`prepared_image.py` coordinates preparation with styles. Interactive previews
are capped at a smaller size while preserving output aspect and composition.
Export separately prepares the original source and runs the style at configured
full resolution. A preview is never enlarged for export. Output dimensions are
limited to 8,000 pixels per side as a memory-safety guard.

## Style plugin system

`ArtStyle` defines the contract: identifier, display name, description, parameters, validation, and processing. `StyleRegistry` stores unique styles and supplies them to clients.

To add a style, create a module in `recraft.styles`, subclass `ArtStyle`, define its parameter metadata and processor, and add an instance to `create_default_registry`. The UI will discover it automatically.

## Future exporters and mesh generation

Exporters should consume processing results without depending on the UI. Vector exporters can initially consume style-specific paths, while a later geometry layer can translate depth maps or procedural primitives into validated meshes. Keeping these layers separate prevents manufacturing concerns from complicating image interpretation.
