# Roadmap

## Phase 0.1

Completed: image loading, non-destructive preparation, fixed crop viewport,
pan, zoom, rotation, flips, aspect-ratio presets, Fit/Fill, independent preview
and export resolution, modular styles, preview, PNG export, Contour, Halftone,
and Fragment. Also completed: the Phase 1 ReCraft Engine foundation, reusable
Image DNA maps, weighted importance, user-mask extension points, importance-aware
versions of all three styles, and developer analysis views.
Completed next: source-aligned importance painting, Lab colour selection,
connected region selection, formal combined weighting, path-native Contour,
raised-ridge STL, watertight validation, background mesh export, and a private
golden-image protocol.

## Phase 0.2

Project files, undo and redo, batch processing, and better performance.
Asynchronous style preview and full-resolution export rendering moved into and
completed in Phase 0.1. Initial image-preparation parameter controls were also
moved into and completed in Phase 0.1.
Future importance work includes undo/redo and semantic selection. Future mesh
work includes engraved channels, adaptive curve meshing, and slicer presets.

## Phase 0.3

Vector and SVG output, line and ribbon styles, and Voronoi and flow-field styles.

## Phase 0.4

Depth-map generation, relief meshes, STL export, and 3MF investigation.

## Phase 1.0

A polished desktop application with saved presets, an installer, a gallery, and physical-print validation.

## Experimental Contour relief branch

`feature/contour-workflow-relief` adds variable relief, independent materials,
coloured 3MF, dependency-aware caching, and corrected shared mesh orientation.
The multi-page wizard was tested and rejected. The branch now uses persistent
2D/3D previews, editable visual-analysis suggestions, creative presets,
importance-driven width/height, and Bambu H2C/Custom print profiles. It remains
separate from stable main pending review.

## Printable relief reset branch

`feature/printable-relief-reset` is a controlled product reset with a single
near-term target: one recognisable, positive, watertight photograph relief that
can be inspected and printed. The line-contour workspace is bypassed by a
structured bas-relief height field, a flat-backed plaque mesh, a reduced
interactive preview, and three physical presets. STL reliability, responsive
UI, and conservative 0.4 mm nozzle defaults take precedence over semantic
selection, painting, diagnostic dashboards, or additional art styles.

The branch must remain experimental until a private golden-image print is
inspected in Bambu Studio and physically printed. The private photograph, its
filename, and screenshots must never enter the repository or package.
