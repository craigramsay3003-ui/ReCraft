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

`feature/contour-workflow-relief` adds the guided workflow, variable relief,
independent materials, coloured 3MF, stage-aware caching, and corrected shared
mesh orientation. It remains separate from stable main pending review.
