# Benchmark Images

`scripts/generate_benchmark_images.py` deterministically creates two 1024 x
1024 public test assets:

- `tests/assets/benchmark_face_colour.png`
- `tests/assets/benchmark_face_greyscale.png`

The fictional vector face has no source photograph and resembles no real
person. A plain background and connected head-and-shoulder silhouette test
subject isolation. Eyes, brows, nose, smiling mouth, ears, neck, and neckline
test internal feature retention. Broad highlight/shadow regions test tonal form.

Dark hair is deliberately heavier on the image left, while a gold earring
exists only on the image right. Those sentinels detect mirroring in analysis,
colour, UV mapping, preview, STL, and 3MF. Coherent hair, skin, clothing, collar,
eyes, background, shadow, and highlight regions test palette reduction.

Acceptance is assessed at three scales: the plaque reads as head and shoulders
from a distance; eyes, nose, mouth, hair, and neckline can be located normally;
and the asymmetric hair, expression, and broad modelling survive close viewing.
The monochrome result must remain recognisable before colour is considered.

Regenerate from the repository root with:

```powershell
.\.venv\Scripts\python.exe scripts\generate_benchmark_images.py
```
