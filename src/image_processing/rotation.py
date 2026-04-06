"""Rotation estimation and correction for scanned document images."""

from __future__ import annotations

import math

import cv2
import numpy as np


def _line_skew_angle(
    binary: np.ndarray, x: int, y: int, w: int, h: int
) -> float | None:
    """Compute the skew correction angle for one text-line bounding box.

    Uses cv2.fitLine on the foreground pixels within the bbox crop.
    Works for both horizontal (w > h) and vertical (h > w) text lines.

    Returns:
        CCW-positive correction angle (i.e. the negation of the tilt),
        or None when the crop has too few pixels.
    """
    if w <= 0 or h <= 0:
        return None
    # Skip roughly-square regions (isolated glyphs or noise).
    if max(w, h) < 2 * min(w, h):
        return None
    crop = binary[y : y + h, x : x + w]
    ys, xs = np.where(crop > 0)
    if len(ys) < 5:
        return None
    pts = np.column_stack([xs, ys]).astype(np.float32)
    vx, vy = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01).flatten()[:2]
    tilt = float(np.degrees(np.arctan2(float(vy), float(vx))))
    # Fold into (−45, 45]: angles near ±90° come from vertical lines and
    # represent the same skew information as near-zero angles after folding.
    while tilt > 45.0:
        tilt -= 90.0
    while tilt <= -45.0:
        tilt += 90.0
    # fitLine returns the line direction; negate to get the correction angle.
    return -tilt


def estimate_rotation_angle(
    image: np.ndarray,
    bboxes: list[tuple[int, int, int, int]],
) -> float:
    """Estimate page skew using the median angle of OCR-detected line bboxes.

    For each line bbox (x, y, w, h), fits a line through the foreground pixels
    to obtain the individual tilt. Returns the median correction angle across
    all lines. Both horizontal and vertical lines are used.

    Args:
        image:  RGB numpy array (H, W, 3) uint8
        bboxes: List of (x, y, w, h) bounding boxes from OCR line detection.

    Returns:
        Angle in degrees (CCW positive) to rotate in order to correct tilt.
        Returns 0.0 if no usable lines are found.
    """
    if not bboxes:
        return 0.0

    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    angles: list[float] = []
    for x, y, w, h in bboxes:
        angle = _line_skew_angle(binary, x, y, w, h)
        if angle is not None:
            angles.append(angle)

    if not angles:
        return 0.0
    return float(np.median(angles))


def transform_bboxes(
    bboxes: list[tuple[int, int, int, int]],
    angle: float,
    orig_h: int,
    orig_w: int,
    new_h: int,
    new_w: int,
) -> list[tuple[int, int, int, int]]:
    """Map (x, y, w, h) bboxes from the original image to the rotated image.

    Args:
        bboxes: List of (x, y, w, h) bounding boxes in original image space.
        angle:  CCW-positive rotation angle that was applied (degrees).
        orig_h, orig_w: Shape of the original image.
        new_h, new_w:   Shape of the rotated image.

    Returns:
        Transformed bboxes clipped to the new image bounds.
        Boxes that end up fully outside are omitted.
    """

    cx, cy = orig_w / 2.0, orig_h / 2.0
    new_cx, new_cy = new_w / 2.0, new_h / 2.0
    cos_a = math.cos(math.radians(angle))
    sin_a = math.sin(math.radians(angle))

    result: list[tuple[int, int, int, int]] = []
    for bx0, by0, bw, bh in bboxes:
        cx_bbox = bx0 + bw / 2.0
        cy_bbox = by0 + bh / 2.0
        dx, dy = cx_bbox - cx, cy_bbox - cy
        new_cx_bbox = cos_a * dx - sin_a * dy + new_cx
        new_cy_bbox = sin_a * dx + cos_a * dy + new_cy
        nx = max(0, int(round(new_cx_bbox - bw / 2.0)))
        ny = max(0, int(round(new_cy_bbox - bh / 2.0)))
        nw = min(bw, new_w - nx)
        nh = min(bh, new_h - ny)
        if nw > 0 and nh > 0:
            result.append((nx, ny, nw, nh))
    return result


def rotate_image(image: np.ndarray, angle: float) -> np.ndarray:
    """Rotate image counter-clockwise by angle degrees to correct tilt.

    Positive angle corrects rightward droop (text right side lower than left).

    Args:
        image: RGB numpy array (H, W, 3) uint8
        angle: rotation angle in degrees (CCW positive)

    Returns:
        Rotated RGB numpy array, expanded to fit the full rotated content.
    """
    h, w = image.shape[:2]
    cx, cy = w / 2.0, h / 2.0

    # OpenCV's getRotationMatrix2D uses clockwise-positive convention
    # (mathematically), so negate to get CCW-positive behaviour.
    M = cv2.getRotationMatrix2D((cx, cy), -angle, 1.0)

    # Compute the bounding box of the rotated image.
    cos_a = abs(M[0, 0])
    sin_a = abs(M[0, 1])
    new_w = int(round(h * sin_a + w * cos_a))
    new_h = int(round(h * cos_a + w * sin_a))

    # Shift the rotation centre so the whole image stays visible.
    M[0, 2] += (new_w - w) / 2.0
    M[1, 2] += (new_h - h) / 2.0

    return cv2.warpAffine(
        image,
        M,
        (new_w, new_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def correct_skew(
    image: np.ndarray,
    bboxes: list[tuple[int, int, int, int]],
    min_angle: float = 0.05,
    extra_threshold: float = 0.2,
    max_extra_passes: int = 2,
) -> tuple[np.ndarray, float]:
    """Estimate and iteratively correct image skew.

    Pass 1 is always applied when |angle| >= min_angle.
    If the first-pass angle exceeds extra_threshold, up to max_extra_passes
    additional correction rounds are applied on the already-corrected image,
    stopping early when the residual angle drops below min_angle.

    Args:
        image:            RGB numpy array (H, W, 3) uint8.
        bboxes:           OCR line bboxes (x, y, w, h) for angle estimation.
        min_angle:        Skip correction when |angle| is below this (degrees).
        extra_threshold:  Trigger extra passes when first-pass |angle| exceeds
                          this value (degrees).
        max_extra_passes: Maximum number of additional correction passes.

    Returns:
        (corrected_image, first_pass_angle)
        corrected_image is the same object as *image* when no correction was
        applied.  first_pass_angle is the angle estimated on the original image
        (CCW positive, degrees); useful for display even when the image is
        returned unchanged.
    """
    angle = estimate_rotation_angle(image, bboxes)
    if abs(angle) < min_angle:
        return image, angle

    need_extra = abs(angle) > extra_threshold
    prev_img = image
    corrected = rotate_image(prev_img, angle)
    current_bboxes = bboxes
    current_angle = angle

    if need_extra:
        for _ in range(max_extra_passes):
            prev_h, prev_w = prev_img.shape[:2]
            new_h, new_w = corrected.shape[:2]
            current_bboxes = transform_bboxes(
                current_bboxes, current_angle, prev_h, prev_w, new_h, new_w
            )
            next_angle = estimate_rotation_angle(corrected, current_bboxes)
            if abs(next_angle) < min_angle:
                break
            prev_img = corrected
            current_angle = next_angle
            corrected = rotate_image(prev_img, current_angle)

    return corrected, angle
