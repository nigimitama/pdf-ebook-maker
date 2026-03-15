from pathlib import Path
import numpy as np
import cv2
from PIL import Image


def load_image(
    input_path: Path,
):
    # read
    # cv2.imread()/cv2.imwrite()はパスが日本語を含むとき文字化けしてエラーになるためPILを使う
    img = np.array([])
    with Image.open(input_path) as pil_img:
        img = np.array(pil_img)

    is_color = img.ndim == 3
    if is_color:  # カラー画像のときは、RGBからBGRへ変換する
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    return img
