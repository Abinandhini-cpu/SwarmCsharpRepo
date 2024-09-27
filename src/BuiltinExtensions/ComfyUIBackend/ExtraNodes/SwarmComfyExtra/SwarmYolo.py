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
                "sort_order": (["left-right", "right-left", "top-bottom", "bottom-top", "largest-smallest", "smallest-largest"], ),
            }
        }

    CATEGORY = "SwarmUI/masks"
    RETURN_TYPES = ("MASK",)
    FUNCTION = "seg"

    def seg(self, image, model_name, index, sort_order="left-right"):
        # TODO: Batch support?
        i = 255.0 * image[0].cpu().numpy()
        img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
        # TODO: Cache the model in RAM in some way?
        model_path = folder_paths.get_full_path("yolov8", model_name)
        if model_path is None:
            raise ValueError(f"Model {model_name} not found, or yolov8 folder path not defined")
        from ultralytics import YOLO
        model = YOLO(model_path)
        results = model(img)
        masks = results[0].masks
        if masks is None:
            boxes = results[0].boxes
            if boxes is None or len(boxes) == 0:
                return (torch.zeros(1, image.shape[1], image.shape[2]), )
            masks = torch.zeros((len(boxes), image.shape[1], image.shape[2]), dtype=torch.float32, device="cpu")
            for i, box in enumerate(boxes):
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                masks[i, int(y1):int(y2), int(x1):int(x2)] = 1.0
        else:
            masks = masks.data.cpu()
        masks = torch.nn.functional.interpolate(masks.unsqueeze(1), size=(image.shape[1], image.shape[2]), mode="bilinear").squeeze(1)

        sortedindices = self.sort_masks(masks, sort_order)
        sortedindices = torch.tensor(np.ascontiguousarray(sortedindices))
        masks = masks[sortedindices]

        if index == 0:
            result = masks[0]
            for i in range(1, len(masks)):
                result = torch.max(result, masks[i])
            return (result.unsqueeze(0),)
        elif index > len(masks):
            return (torch.zeros_like(masks[0]).unsqueeze(0),)
        else:
            return (masks[index - 1].unsqueeze(0),)

    def sort_masks(self, masks, sort_order):
        sortedindices = []
        for mask in masks:
            match sort_order:
                case "left-right":
                    sum_x = (torch.sum(mask, dim=0) != 0).to(dtype=torch.int)
                    val = torch.argmax(sum_x).item()
                case "right-left":
                    sum_x = (torch.sum(mask, dim=0) != 0).to(dtype=torch.int)
                    val = mask.shape[1] - torch.argmax(torch.flip(sum_x, [0])).item() - 1
                case "top-bottom":
                    sum_y = (torch.sum(mask, dim=1) != 0).to(dtype=torch.int)
                    val = torch.argmax(sum_y).item()
                case "bottom-top":
                    sum_y = (torch.sum(mask, dim=1) != 0).to(dtype=torch.int)
                    val = mask.shape[0] - torch.argmax(torch.flip(sum_y, [0])).item() - 1
                case "largest-smallest" | "smallest-largest":
                    val = torch.sum(mask).item()
            sortedindices.append(val)

        sorted_indices_array = np.array(sortedindices)
        if sort_order in ["right-left", "bottom-top", "largest-smallest"]:
            return np.argsort(sorted_indices_array)[::-1].copy()
        else:
            return np.argsort(sorted_indices_array)

NODE_CLASS_MAPPINGS = {
    "SwarmYoloDetection": SwarmYoloDetection,
}
