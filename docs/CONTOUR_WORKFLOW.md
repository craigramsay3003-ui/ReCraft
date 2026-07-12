# Preview-led Contour workspace

The five-page wizard was tested and rejected: it separated controls from the
artwork and made comparisons slow. Contour now uses one creative workspace with
persistent prepared/analysis, 2D Contour, and actual 3D export-geometry views.
A collapsible side panel holds interpretation, presets, preparation, advanced
Contour/relief settings, printer profile, colours, and export.

The 2D views support wheel zoom, drag pan, fit, and 100% navigation. The 3D view
uses the same mesh as STL/3MF and supports left-drag orbit, Shift/centre-drag
pan, wheel zoom, fit/reset, standard views, perspective/orthographic projection,
and optional edges. Camera and colour changes never rebuild geometry.

## Suggestions and focus

Image DNA is analysed first. ReCraft presents uncertain candidates such as
Likely subject, Possible face, Suggested silhouette, bright areas, and prominent
background texture. Each may remain automatic, add focus, reduce focus, or be
ignored. Candidate masks and manual brushes feed the same combined-importance
model and survive preset changes.

The description box performs an honest local keyword mapping. Supported words
such as face, silhouette, subject, clothing, background, ceiling, lights, and
architecture map onto existing masks and settings. It is not an arbitrary
scene-language model; unsupported wording is ignored.

## Creative presets

- **Detailed**: 24 bands, simplification 0.45, 1 px line, 0.9 mm nominal ridge,
  0.3–2.2 mm relief, and mesh quality 230.
- **Standard**: 15 bands, simplification 1.0, 2 px line, 1.2 mm ridge,
  0.4–1.8 mm relief, and mesh quality 160. This is the default.
- **Abstract**: 8 bands, simplification 2.8, 3 px line, 1.8 mm ridge,
  0.6–1.6 mm relief, stronger background reduction, and mesh quality 100.

Advanced controls remain available in collapsed sections. Focus selections are
preserved when presets change.

## Relief, width, and printing

Each `ContourPath` stores importance, subject/background membership, smoothed
point heights, and optional point widths. Importance, subject/face evidence,
contrast, and inverse background evidence influence retention, simplification,
height, and width. Uniform modes remain available. Diagnostics explain whether
a path was removed, retained, simplified, raised, lowered, or widened.

Print assumptions live in profiles. **Bambu H2C** is the initial test profile,
with editable nozzle diameter and layer height; **Custom printer** keeps the
pipeline portable. Warnings cover narrow contours, sub-layer relief changes,
thin bases, excessive complexity, and small physical size. Fast/Balanced/Final
affect preview geometry only; export uses full requested settings.

Image X maps directly to Cartesian X and image Y is inverted once. Preview, STL,
and 3MF consume the same mesh. STL contains geometry only; 3MF stores separate
Base and Contour Relief materials and colours.

The private golden family image is for local manual evaluation only. Never
commit, package, fixture, or publish screenshots of it.
