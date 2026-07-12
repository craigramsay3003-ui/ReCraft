"""Optional face and landmark signals for the general image engine."""

import cv2
import numpy as np


def detect_faces(greyscale: np.ndarray) -> tuple[list[tuple[int, int, int, int]], np.ndarray, list[np.ndarray]]:
    """Return face rectangles, a soft face mask, and landmarks when available.

    OpenCV's bundled cascade provides an optional importance cue. Landmark
    output remains empty when no compatible landmark model is installed.
    """
    grey = np.clip(greyscale * 255, 0, 255).astype(np.uint8)
    classifier = getattr(cv2, "CascadeClassifier", None)
    data = getattr(cv2, "data", None)
    if classifier is None or data is None:
        return [], np.zeros(grey.shape, dtype=np.float32), []
    cascade = classifier(data.haarcascades + "haarcascade_frontalface_default.xml")
    detected = () if cascade.empty() else cascade.detectMultiScale(grey, 1.1, 5, minSize=(24, 24))
    rectangles = [tuple(int(value) for value in item) for item in detected]
    mask = np.zeros(grey.shape, dtype=np.float32)
    for x, y, width, height in rectangles:
        centre = (x + width // 2, y + height // 2)
        cv2.ellipse(mask, centre, (width // 2, height // 2), 0, 0, 360, 1.0, -1)
    if rectangles:
        mask = cv2.GaussianBlur(mask, (0, 0), max(2, min(grey.shape) / 100))
        mask = np.clip(mask, 0, 1)
    return rectangles, mask, []
