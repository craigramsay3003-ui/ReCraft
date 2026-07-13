# Architecture

## Experimental printable-relief pipeline

On `feature/printable-relief-reset`, the default application uses this bounded
pipeline:

`original image -> non-destructive fit/crop -> ReliefHeightMap -> structured plaque mesh -> preview/export`

`recraft.relief.presets` owns the three centrally defined physical presets and
the validated `ReliefSettings`. `heightmap.py` analyses only a bounded RGB copy,
then combines broad luminance, local contrast, restrained gradient evidence,
generic subject/face evidence, and background suppression. Robust normalization,
morphological minimum-feature cleanup, and spike smoothing convert this into an
immutable floating-point 0..1 field. Normal relief maps larger values outward;
inversion is explicit and off by default.

`relief.mesh` maps the field onto a regular millimetre grid. It creates a raised
front, a flat rear at Z=0, and closed side walls as one object. Image X is kept
unchanged and image Y alone is converted to Cartesian coordinates, so left and
right are preserved. Preview and export call the same functions at different
bounded resolutions. Triangle budgets are 150,000 for preview and 350,000 for
export.

`ReliefWorker` performs analysis, mesh construction, and file writing on a
`QThread`. The last valid mesh remains visible until a replacement succeeds.
Only geometry-affecting controls make the preview stale; camera interaction
uses copied immutable render buffers and never regenerates geometry. Recoverable
exceptions are shown to the user and written with tracebacks to the diagnostic
log without image data or deliberate private filenames.

The legacy Engine, styles, and Contour packages remain isolated so this branch
can be evaluated without deleting prior research. `MainWindow` exposes only the
relief workflow; there are not two competing primary interfaces.

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

## Background rendering

`RenderWorker` receives an isolated snapshot of the source image, preparation
settings, selected style, and parameters. It performs style preview rendering
or full-resolution preparation, style processing, and PNG writing on a
`QThread`. The main window remains responsive, presents indeterminate progress,
and temporarily locks conflicting controls until the job finishes. Results and
useful error messages return through Qt signals; processing algorithms remain
independent of Qt.

## Guided variable-height relief

Each Contour path now carries peak importance, subject/background membership,
and a smoothed local relief profile. The mesh maps it between validated minimum
and maximum heights after relief-strength and background-reduction controls.
`ContourWorkflowState` retains dependency invalidation and material state while
the UI uses one persistent-preview workspace rather than progressive pages:
colours do not invalidate geometry, relief preserves analysis/paths, and
preparation invalidates all downstream products.

The shared mesh transform keeps image X as Cartesian X and converts downward
image Y to upward Cartesian Y. Material preview, STL, and 3MF use that mesh.
3MF contains Base and Contour Relief material assignments; STL is colourless.

## Style plugin system

`ArtStyle` defines the contract: identifier, display name, description, parameters, validation, and processing. `StyleRegistry` stores unique styles and supplies them to clients.

To add a style, create a module in `recraft.styles`, subclass `ArtStyle`, define its parameter metadata and processor, and add an instance to `create_default_registry`. The UI will discover it automatically.

## ReCraft Engine and Image DNA

`recraft.engine` is the interpretation layer between image preparation and
procedural artwork:

`prepared canvas → analyse_image → ImageAnalysis → selected style`

The engine computes greyscale, CLAHE-enhanced greyscale, edges, gradient
magnitude, local contrast, k-means colour clusters, local texture, spectral
saliency, optional face signals, generic subject/background segmentation, and
elliptical centre weighting. `importance.py` combines gradient, saliency, face
confidence, local contrast, boundaries, subject evidence, and centre distance
into a normalized 0..1 preservation priority.

The result is computed once for a render and the same `ImageAnalysis` instance
is supplied to its style. Analysis maps are capped at 1,200 pixels on their
longest side to avoid multi-gigabyte allocations on large exports. The full
prepared RGB image remains available, and styles resize only required maps.

`ImageAnalysis.with_user_masks` already supports an absolute importance mask
plus additive and subtractive brush layers. These arrays are validated and
combined non-destructively; UI painting tools are intentionally deferred.

Face detection is capability-based because OpenCV distributions differ. A
supported Haar detector adds a soft face-confidence map. Otherwise the map is
zero and the general saliency, boundary, subject, contrast, and centre signals
continue normally. Landmark collections are available in the contract for a
future model but are empty when no compatible estimator is installed.

Current styles use the shared analysis differently: Fragment distributes points
by importance and constrains triangle size with a base grid; Contour smooths
brightness bands, removes tiny loops, and reinforces important edges; Halftone
uses local normalization and adaptive dot spacing/sizing. The developer dropdown
renders reusable maps without changing PNG export behavior.

## Future exporters and mesh generation

Exporters should consume processing results without depending on the UI. Vector exporters can initially consume style-specific paths, while a later geometry layer can translate depth maps or procedural primitives into validated meshes. Keeping these layers separate prevents manufacturing concerns from complicating image interpretation.

## User importance and assisted selection

`UserImportanceState` stores additive/subtractive masks in a bounded proxy of
original-source coordinates. `canvas_to_source` inversely maps prepared-view
strokes through crop, Fit/Fill, pan, zoom, rotation, and flips. The same masks
are transformed forward for preview or export. Combined importance applies
automatic strength, user additions/reductions, and background suppression,
then clamps deterministically to 0..1.

`colour_selection.py` uses Lab distance; `region_selection.py` retains a
connected visual region. Both are UI-independent and preview before application.

## Contour geometry and mesh export

Contour extracts smoothed luminance iso-levels into `ContourPath`, then filters
by length, enclosed area, background evidence, spacing, and combined importance.
`ContourResult` retains raw and filtered paths as the source for diagnostics,
PNG, future SVG, and physical geometry.

`contour_mesh.py` maps paths into millimetres and builds a continuous raised
ridge top, flat base, and closed side walls. `trimesh` validates watertightness
before STL output. `MeshWorker` performs generation, validation, and writing off
the UI thread. Mesh export is intentionally Contour-only.
