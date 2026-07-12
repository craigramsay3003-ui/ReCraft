"""Top-level ReCraft Engine image interpretation pipeline."""

import cv2
import numpy as np
from PIL import Image

from recraft.engine.analysis_result import ImageAnalysis
from recraft.engine.colour import cluster_colours
from recraft.engine.edges import edge_features, texture_map
from recraft.engine.faces import detect_faces
from recraft.engine.importance import build_importance
from recraft.engine.segmentation import centre_weight, saliency_map, segment_subject

MAX_ANALYSIS_DIMENSION = 1200


def analyse_image(image: Image.Image, colour_clusters: int = 6) -> ImageAnalysis:
    """Analyse one prepared image and return reusable Image DNA."""
    if image.width < 1 or image.height < 1:
        raise ValueError("Image analysis requires a non-empty image")
    source = image.convert("RGB")
    working = source.copy()
    working.thumbnail((MAX_ANALYSIS_DIMENSION, MAX_ANALYSIS_DIMENSION), Image.Resampling.LANCZOS)
    rgb = np.asarray(working, dtype=np.uint8)
    grey_u8 = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    greyscale = grey_u8.astype(np.float32) / 255.0
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(grey_u8).astype(np.float32) / 255.0
    edges, gradient, local_contrast = edge_features(enhanced)
    texture = texture_map(greyscale)
    saliency = saliency_map(greyscale)
    centre = centre_weight(greyscale.shape)
    face_rectangles, face_mask, landmarks = detect_faces(greyscale)
    subject, background = segment_subject(saliency, centre, edges)
    labels, centres = cluster_colours(rgb, colour_clusters)
    importance = build_importance(
        edges, gradient, saliency, face_mask, local_contrast, subject, centre
    )
    return ImageAnalysis(
        image=source.copy(),
        greyscale=greyscale,
        enhanced_greyscale=enhanced,
        edge_map=edges,
        gradient_magnitude=gradient,
        colour_labels=labels,
        colour_centres=centres,
        texture_map=texture,
        saliency_map=saliency,
        face_rectangles=tuple(face_rectangles),
        face_landmarks=tuple(landmarks),
        face_mask=face_mask,
        background_mask=background,
        subject_mask=subject,
        centre_weight=centre,
        local_contrast=local_contrast,
        automatic_importance=importance,
    )
