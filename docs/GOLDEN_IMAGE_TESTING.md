# Golden Image Testing

Use one representative local photograph repeatedly to judge improvement across
versions. Never add a private family photograph to this public repository.

## Workflow

1. Pull `main`, launch ReCraft, and open the same local image.
2. Reproduce the Prepared Image crop, aspect ratio, zoom, pan, and rotation.
3. Inspect **Automatic Importance** and **Subject Mask**.
4. Paint Add/Reduce importance or use colour/region selection, then inspect
   **Combined Importance**.
5. Generate the Contour PNG with recorded settings.
6. Export Contour STL with recorded physical settings.
7. Keep the source photograph and private derivatives outside Git.

## Manual scorecard

Score each item from 1 (poor) to 5 (excellent), with a short observation.

| Criterion | Score | Notes |
| --- | ---: | --- |
| Subject recognisability |  |  |
| Face recognisability |  |  |
| Background suppression |  |  |
| Artistic appeal |  |  |
| Line cleanliness |  |  |
| Physical printability |  |  |

Confirm STL dimensions, vertex/face counts, and watertight status, then inspect
the file in a trusted slicer before printing.
