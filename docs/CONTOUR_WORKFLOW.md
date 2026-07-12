# Guided Contour Workflow

The Contour experience has five compact stages. The prepared canvas remains
visible beside them so composition and painting stay immediate.

1. **Prepare Image** — crop viewport, rotate, flip, Fit/Fill, aspect and size.
2. **Choose Subject Importance** — optional automatic/user importance, brushes,
   selections, overlay, and background suppression.
3. **Design Contours** — Detail, Smoothing, Subject Emphasis, Background
   Reduction, Simplification, Minimum Line Length/Spacing, and Line Weight.
   Major-only and inversion controls are collapsed under Advanced.
4. **Build Relief** — physical size, base, variable minimum/maximum height,
   ridge width, border, relief contrast/smoothing, background reduction, curve
   quality, printable minimum, and uniform-height comparison.
5. **Preview and Export** — 2D artwork, material relief, mesh summary,
   independent colours, PNG, geometry-only STL, and coloured 3MF.

Back and Next preserve settings. Preparation invalidates all later stages;
importance/art changes invalidate paths and mesh; relief invalidates only mesh;
colours only redraw materials.

## Variable-height calculation

Each `ContourPath` stores average/peak importance, subject/background membership,
and a smoothed per-point relief profile. The profile combines importance,
subject/face evidence, local contrast, and inverse background evidence. Mesh
generation applies background reduction and relief strength, then maps safely
between minimum and maximum millimetres. Uniform mode uses one height.

## Orientation

Image X maps directly to Cartesian X. Downward image Y is inverted to upward
Cartesian Y during mesh generation. Preview, STL, and 3MF consume the same mesh.
An optional developer arrow is off for normal exports.

## Colour and formats

Base and Contour colours are separate validated `#RRGGBB` values. The preview
shades the real mesh with both. STL contains geometry only. 3MF carries Base and
Contour Relief material assignments for slicer mapping.
