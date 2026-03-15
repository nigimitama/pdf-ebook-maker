import numpy as np
import cv2


def resize_image(
    image: np.ndarray,
    new_width: int = 1080,
):
    height, width = image.shape[0:2]
    new_height = round((height / width) * new_width)
    resized_image = cv2.resize(src=image, dsize=(new_width, new_height))

    return resized_image
