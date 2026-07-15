# ReCraft Core

ReCraft interprets photographs and rebuilds them as distinctive printable
artwork. Portrait Relief is the first physical style. It is aimed initially at
one person, pet, or vehicle against a reasonably simple background.

The reusable pipeline is:

`PreparedImage -> SubjectAnalysis -> FeatureImportance -> ArtisticSimplification -> ReliefField -> ColourMap -> ReliefMesh`

`PreparedImage` holds composed pixels and transform metadata. `SubjectAnalysis`
uses the existing Image DNA maps plus a largest coherent foreground region. It
reports either that fallback or a centre-weighted fallback; it does not claim
semantic recognition. `FeatureImportance` combines the likely subject,
silhouette, faces when detected, internal edges, contrast, and centre evidence.

`ArtisticSimplification` merges tones, removes regions smaller than the
configured physical feature size, and retains supported structural edges. The
relief is not a literal luminance emboss. Broad subject form occupies the useful
height range, important boundaries receive restrained reinforcement, and the
background is held lower.

The rear surface is Z=0. The front has a 1.5 mm base by default and a positive
1.8 mm relief. One structured grid supplies front, flat rear, and closed walls.
Preview and export share orientation and proportions; preview only lowers grid
resolution. Default Bambu H2C assumptions are a 0.4 mm nozzle, 0.2 mm layers,
160 mm width, and a conservative 0.8 mm minimum feature.

Subject Emphasis controls likely-subject priority. Background chooses Remove,
Simplify, or Keep. Detail chooses physical simplification scale and the number
of retained broad tones. These are creative controls, not semantic promises.

The old Contour and reset pipelines remain internally for reference, but the
default application exposes only Portrait Relief.

