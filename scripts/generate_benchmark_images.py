"""Generate deterministic synthetic ReCraft benchmark portraits."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


SIZE = 1024
OUTPUT_DIRECTORY = Path(__file__).resolve().parents[1] / "tests" / "assets"


def _radial_layer(
    size: tuple[int, int], centre: tuple[float, float], radius: tuple[float, float]
) -> np.ndarray:
    """Return a clipped elliptical highlight field."""
    y, x = np.mgrid[0 : size[1], 0 : size[0]]
    distance = ((x - centre[0]) / radius[0]) ** 2 + ((y - centre[1]) / radius[1]) ** 2
    return np.clip(1 - distance, 0, 1).astype(np.float32)


def generate_face_benchmark() -> Image.Image:
    """Create one fictional, asymmetric, colour-region portrait benchmark."""
    image = Image.new("RGB", (SIZE, SIZE), "#CAD8D6")
    draw = ImageDraw.Draw(image, "RGBA")

    # Broad shoulders and an asymmetric teal/coral neckline test silhouette,
    # clothing boundaries, coherent palette regions, and left/right orientation.
    draw.ellipse((170, 720, 870, 1220), fill="#315D72")
    draw.polygon([(350, 790), (512, 910), (680, 790), (620, 1024), (395, 1024)], fill="#E56F61")
    draw.rounded_rectangle((443, 650, 582, 835), radius=45, fill="#B8755E")

    # Ears precede the face so the silhouette remains coherent.
    draw.ellipse((274, 335, 385, 610), fill="#C9856D", outline="#7D433C", width=12)
    draw.ellipse((650, 350, 754, 612), fill="#C9856D", outline="#7D433C", width=12)
    draw.ellipse((305, 394, 356, 553), fill="#9C5D53")
    draw.ellipse((675, 410, 724, 558), fill="#9C5D53")

    # Face base and broad directional modelling are intentionally graphic, not
    # photorealistic and do not resemble a real person.
    draw.ellipse((318, 178, 713, 760), fill="#D99B78", outline="#6E4037", width=15)
    highlight = _radial_layer((SIZE, SIZE), (450, 390), (230, 330))
    shadow = _radial_layer((SIZE, SIZE), (670, 480), (215, 390))
    pixels = np.asarray(image).astype(np.float32)
    mask_image = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask_image).ellipse((325, 185, 706, 752), fill=255)
    mask = np.asarray(mask_image, np.float32) / 255
    modelling = (highlight * 24 - shadow * 30)[..., None]
    pixels = np.clip(pixels + modelling * mask[..., None], 0, 255)
    image = Image.fromarray(pixels.astype(np.uint8))
    draw = ImageDraw.Draw(image, "RGBA")

    # Asymmetric swept hair and a deliberate left-side curl detect mirroring.
    draw.pieslice((255, 92, 740, 490), 180, 360, fill="#3A2530", outline="#1E1720", width=14)
    draw.polygon([(270, 300), (322, 140), (478, 102), (424, 280), (352, 430)], fill="#3A2530")
    draw.polygon([(500, 105), (690, 168), (735, 345), (660, 293), (580, 180)], fill="#6F3C48")
    draw.ellipse((235, 290, 330, 520), fill="#3A2530")
    draw.arc((210, 385, 350, 610), 80, 300, fill="#D78B58", width=22)

    # Brows, eyes, nose, and expression use broad printable features.
    draw.arc((350, 330, 486, 420), 190, 340, fill="#49292B", width=18)
    draw.arc((535, 337, 665, 423), 200, 350, fill="#49292B", width=18)
    draw.ellipse((370, 386, 468, 454), fill="#F4E8D5", outline="#6E4037", width=8)
    draw.ellipse((545, 392, 641, 458), fill="#F4E8D5", outline="#6E4037", width=8)
    draw.ellipse((408, 399, 447, 444), fill="#3D7975")
    draw.ellipse((573, 404, 612, 449), fill="#3D7975")
    draw.ellipse((419, 412, 438, 438), fill="#202633")
    draw.ellipse((584, 416, 603, 442), fill="#202633")
    draw.ellipse((425, 409, 434, 419), fill="white")
    draw.ellipse((590, 413, 599, 423), fill="white")
    draw.polygon([(505, 405), (475, 555), (520, 577), (552, 548)], fill="#B66E5C")
    draw.line([(482, 575), (521, 586), (550, 569)], fill="#6E4037", width=11)
    draw.arc((412, 565, 620, 690), 8, 168, fill="#7B3040", width=24)
    draw.arc((438, 594, 596, 665), 15, 165, fill="#F0B4A5", width=14)

    # A single right earring is the unambiguous asymmetric orientation marker.
    draw.ellipse((697, 570, 742, 615), outline="#E9B949", width=12)
    draw.ellipse((704, 610, 735, 650), fill="#E9B949")

    # A restrained blur removes vector aliasing without erasing feature edges.
    return image.filter(ImageFilter.GaussianBlur(1.2))


def main() -> None:
    """Write deterministic colour and greyscale benchmark files."""
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    colour = generate_face_benchmark()
    colour.save(OUTPUT_DIRECTORY / "benchmark_face_colour.png", optimize=True)
    colour.convert("L").save(OUTPUT_DIRECTORY / "benchmark_face_greyscale.png", optimize=True)


if __name__ == "__main__":
    main()
