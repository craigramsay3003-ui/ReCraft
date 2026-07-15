# Colour Relief

Colour is independent from geometry and aligned to the prepared image and mesh.

- **Original Colour** maps the prepared photograph onto the front. It helps
  compare photograph and relief, but is preview-only for ordinary filament
  printing.
- **Artistic Palette** clusters perceptual Lab colour into 2, 3, 4, or 6
  coherent regions. Median filtering, connected-region cleanup, and the
  physical feature limit remove small islands. Colours can be replaced/locked.
- **Monochrome Material** provides matte white, stone, warm grey, black, or a
  custom neutral preview with restrained height-revealing lighting.

Changing preview colour does not rerun analysis, simplification, geometry, or
camera setup. The renderer owns copied compact buffers and projectively maps a
matte colour texture over the coherent relief preview.

STL is geometry-only and never stores selected colour. ReCraft 3MF exports one
watertight object in millimetres. Artistic Palette mode assigns materials to
broad regions and a neutral material to sides/rear. Original Colour currently
becomes one representative display material, not a photographic texture. This
is useful metadata, not a guarantee of automatic multi-material slicing.

Geometry reliability, units, orientation, and a printable object take priority
over colour metadata. Full-colour photographic filament output is not claimed.

