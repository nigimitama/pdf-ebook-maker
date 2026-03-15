import numpy as np
import cv2


def contrast_adjustments(image: np.ndarray, contrast=1.0, brightness=0.0):
    dst = contrast * image.astype(np.uint16) + brightness
    # [0, 255] でクリップし、uint8 型にする。
    return np.clip(dst, 0, 255).astype(np.uint8)


def gamma_correction(image: np.ndarray, gamma: float) -> np.ndarray:
    """ガンマ補正 (gamma correction)

    次のような変換を行う
        y = (x / 255)^gamma * 255
    """
    # 非線形関数（look up table）を作る
    look_up_table = np.empty((1, 256), np.uint8)
    for i in range(256):
        look_up_table[0, i] = np.clip(pow(i / 255.0, gamma) * 255.0, 0, 255)
    # 補正をかける
    return cv2.LUT(image, look_up_table)


def transform_intensity(
    image: np.ndarray,
    brightness: int = 20,
    gamma: float = 1.6,
    gamma_target: str = "gray",
):
    """文書の文字を鮮明にするため、画像の輝度を変換する"""
    is_color = image.ndim == 3
    # MEMO: gamma=1.5くらいがIrfanviewで0.6にしたときに近い（IrfanViewは逆数(1/0.6=1.66)にしてる?）
    if gamma_target == "all" or ((gamma_target == "gray") and (not is_color)):
        # ガンマ補正
        image = gamma_correction(image, gamma=gamma)
        # コントラスト補正
        image = contrast_adjustments(image, contrast=1, brightness=brightness)
    return image
