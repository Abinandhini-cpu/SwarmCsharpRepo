import torch, folder_paths, comfy
from PIL import Image
import numpy as np

class SwarmYoloDetection:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "model_name": (folder_paths.get_filename_list("yolov8"), ),
                "index": ("INT", { "default": 0, "min": 0, "max": 256, "step": 1 }),
            },
            "optional": {
                "class_filter": ("STRING", { "default": "", "multiline": False }),
            }
        }

    CATEGORY = "SwarmUI/masks"
    RETURN_TYPES = ("MASK",)
    FUNCTION = "seg"

    def seg(self, image, model_name, index, class_filter=None):
        # TODO: Batch support?
        i = 255.0 * image[0].cpu().numpy()
        img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
        # TODO: Cache the model in RAM in some way?
        model_path = folder_paths.get_full_path("yolov8", model_name)
        if model_path is None:
            raise ValueError(f"Model {model_name} not found, or yolov8 folder path not defined")
        from ultralytics import YOLO
        model = YOLO(model_path)
        class_labels = model.names
        results = model(img)
        boxes = results[0].boxes
        class_ids = boxes.cls.cpu().numpy() if boxes is not None else []
        selected_classes = []
        if class_filter and class_filter.strip():
            class_filter_list = [cls.strip() for cls in class_filter.split(",") if cls.strip()]
            label_to_id = {name.lower(): id for id, name in class_labels.items()}
            for cls in class_filter_list:
                if cls.isdigit():
                    selected_classes.append(int(cls))
                else:
                    class_id = label_to_id.get(cls.lower())
                    if class_id is not None:
                        selected_classes.append(class_id)
            selected_classes = selected_classes if selected_classes else None
        else:
            selected_classes = None
        masks = results[0].masks
        if masks is not None and selected_classes is not None:
            selected_masks = []
            for i, class_id in enumerate(class_ids):
                if class_id in selected_classes:
                    selected_masks.append(masks.data[i].cpu())
            if selected_masks:
                masks = torch.stack(selected_masks)
            else:
                masks = None
        if masks is None or masks.shape[0] == 0:
            if boxes is None or len(boxes) == 0:
                return (torch.zeros(1, image.shape[1], image.shape[2]), )
            else:
                if selected_classes:
                    boxes = [box for i, box in enumerate(boxes) if class_ids[i] in selected_classes]
            masks = torch.zeros((len(boxes), image.shape[1], image.shape[2]), dtype=torch.float32, device="cpu")
            for i, box in enumerate(boxes):
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                masks[i, int(y1):int(y2), int(x1):int(x2)] = 1.0
        else:
            masks = masks.data.cpu()
        if masks is None or masks.shape[0] == 0:
            return (torch.zeros(1, image.shape[1], image.shape[2]), )
        masks = torch.nn.functional.interpolate(masks.unsqueeze(1), size=(image.shape[1], image.shape[2]), mode="bilinear").squeeze(1)
        if index == 0:
            result = masks[0]
            for i in range(1, len(masks)):
                result = torch.max(result, masks[i])
            return (result, )
        elif index > len(masks):
            return (torch.zeros_like(masks[0]), )
        else:
            sortedindices = []
            for mask in masks:
                sum_x = (torch.sum(mask, dim=0) != 0).to(dtype=torch.int)
                val = torch.argmax(sum_x).item()
                sortedindices.append(val)
            sortedindices = np.argsort(sortedindices)
            masks = masks[sortedindices]
            return (masks[index - 1].unsqueeze(0), )

NODE_CLASS_MAPPINGS = {
    "SwarmYoloDetection": SwarmYoloDetection,
}
