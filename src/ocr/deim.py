# Copyright (c) 2023, National Diet Library, Japan
#
# This software is released under the CC BY 4.0.
# https://creativecommons.org/licenses/by/4.0/
#
# Source: ndlocr-lite/src/deim.py
# https://github.com/ndl-lab/ndlocr-lite
# Modifications: removed debug print statement; removed unused visualization
#                methods (draw_detections, drawxml_detections, get_label_name)
#                and their associated imports.

import yaml
import onnxruntime
import numpy as np
import cv2


class DEIM:
    def __init__(self,
                 model_path: str,
                 class_mapping_path: str,
                 original_size: tuple[int, int] = (1280, 1280),
                 score_threshold: float = 0.1,
                 conf_threshold: float = 0.1,
                 iou_threshold: float = 0.4,
                 device: str = "CPU") -> None:
        self.model_path = model_path
        self.class_mapping_path = class_mapping_path
        self.image_width, self.image_height = original_size
        self.device = device
        self.score_threshold = score_threshold
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.create_session()

    def create_session(self) -> None:
        opt_session = onnxruntime.SessionOptions()
        opt_session.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        providers = ['CPUExecutionProvider']
        if self.device.casefold() == "cuda":
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        session = onnxruntime.InferenceSession(self.model_path, opt_session, providers=providers)
        self.session = session
        self.model_inputs = self.session.get_inputs()
        self.input_names = [self.model_inputs[i].name for i in range(len(self.model_inputs))]
        self.input_shape = self.model_inputs[0].shape
        self.model_output = self.session.get_outputs()
        self.output_names = [self.model_output[i].name for i in range(len(self.model_output))]
        self.input_height, self.input_width = self.input_shape[2:]

        if self.class_mapping_path is not None:
            with open(self.class_mapping_path, 'r') as file:
                yaml_file = yaml.safe_load(file)
                self.classes = yaml_file['names']
                self.color_palette = np.random.uniform(0, 255, size=(len(self.classes), 3))

    def preprocess(self, img: np.ndarray) -> np.ndarray:
        max_wh = max(img.shape[0], img.shape[1])
        paddedimg = np.zeros((max_wh, max_wh, 3), dtype=np.uint8)
        paddedimg[:img.shape[0], :img.shape[1], :] = img
        self.image_width = max_wh
        self.image_height = max_wh
        resized = cv2.resize(paddedimg, (self.input_width, self.input_height), interpolation=cv2.INTER_CUBIC)
        input_image = resized.astype(np.float32)
        input_image /= 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        input_image -= mean
        input_image /= std
        input_image = input_image.transpose(2, 0, 1)
        return input_image[np.newaxis, :, :, :].astype(np.float32)

    def xywh2xyxy(self, x: np.ndarray) -> np.ndarray:
        # Convert bounding box (x, y, w, h) to bounding box (x1, y1, x2, y2)
        y = np.copy(x)
        y[..., 0] = x[..., 0] - x[..., 2] / 2
        y[..., 1] = x[..., 1] - x[..., 3] / 2
        y[..., 2] = x[..., 0] + x[..., 2] / 2
        y[..., 3] = x[..., 1] + x[..., 3] / 2
        return y

    def postprocess(self, outputs: list) -> list:
        if len(outputs) == 4:
            class_ids, bboxes, scores, char_counts = outputs
            char_counts = np.squeeze(char_counts)
        elif len(outputs) == 3:
            class_ids, bboxes, scores = outputs
            char_counts = np.array([100.0] * np.squeeze(scores).shape[0])
        else:
            return []

        class_ids = np.squeeze(class_ids)
        predictions = np.squeeze(bboxes)
        scores = np.squeeze(scores)

        predictions = predictions[scores > self.conf_threshold, :]
        scores = scores[scores > self.conf_threshold]
        scales = np.array([
            self.image_width / self.input_width,
            self.image_height / self.input_width,
            self.image_width / self.input_width,
            self.image_height / self.input_width,
        ], dtype=np.float32)
        boxes = (predictions[:, :4] * scales).astype(np.int32)

        return [
            {
                "class_index": int(label) - 1,
                "confidence": score,
                "box": bbox,
                "pred_char_count": char_count,
                "class_name": self.classes[int(label) - 1],
            }
            for bbox, score, label, char_count in zip(boxes, scores, class_ids, char_counts)
        ]

    def detect(self, img: np.ndarray) -> list:
        input_tensor = self.preprocess(img)
        outputs = self.session.run(
            self.output_names,
            {self.input_names[0]: input_tensor, self.input_names[1]: np.array([[self.input_height, self.input_width]], np.int64)},
        )
        return self.postprocess(outputs)
