import numpy as np
import cv2


def resize_image(
    image: np.ndarray,
    *,
    target_width: int | None = None,
    target_height: int | None = None,
) -> np.ndarray:
    """Resize image to target dimensions while maintaining aspect ratio.

    Parameters
    ----------
    image:         RGB or grayscale numpy array.
    target_width:  Desired output width in pixels. Height scales proportionally.
    target_height: Desired output height in pixels. Width scales proportionally.

    If both are given, the image is scaled to fit within that bounding box
    (the smaller scale factor wins, similar to CSS ``object-fit: contain``).
    If neither is given, the image is returned unchanged.
    """
    if not target_width and not target_height:
        return image

    h, w = image.shape[:2]
    if target_width and target_height:
        scale = min(target_width / w, target_height / h)
        new_w, new_h = round(w * scale), round(h * scale)
    elif target_width:
        new_w = target_width
        new_h = round(h / w * new_w)
    elif target_height:
        new_h = target_height
        new_w = round(w / h * new_h)
    else:
        return image  # unreachable: both None was handled at entry

    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
