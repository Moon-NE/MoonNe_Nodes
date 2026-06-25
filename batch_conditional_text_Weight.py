import random


class BatchConditionalTextWeight:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "batch_index": ("INT", {"default": 0, "min": 0, "max": 999999}),
                "text": ("STRING", {"multiline": True, "default": ""}),
                "greater_than": ("INT", {"default": 0}),
                "less_than": ("INT", {"default": 999}),
                "probability": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01},
                ),
                "min_weight": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.01},
                ),
                "max_weight": (
                    "FLOAT",
                    {"default": 1.4, "min": 0.0, "max": 10.0, "step": 0.01},
                ),
                "seed": (
                    "INT",
                    {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF},
                ),
            }
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "process"
    CATEGORY = "Text/Conditional"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("NaN")

    def process(
        self,
        batch_index,
        text,
        greater_than,
        less_than,
        probability,
        min_weight,
        max_weight,
        seed,
    ):
        probability = max(0.0, min(1.0, probability))

        if min_weight > max_weight:
            min_weight, max_weight = max_weight, min_weight

        rng = random.Random(f"{seed}_{batch_index}")

        condition = False

        if greater_than < less_than:
            condition = greater_than <= batch_index <= less_than
        elif greater_than > less_than:
            condition = batch_index > greater_than or batch_index < less_than
        else:
            condition = batch_index == greater_than

        if condition and rng.random() < probability:
            # 按逗号拆分并清理空格
            normalized_text = text.replace("，", ",")
            tags = [tag.strip() for tag in normalized_text.split(",") if tag.strip()]

            weighted_tags = []
            for tag in tags:
                weight = rng.uniform(min_weight, max_weight)
                weighted_tags.append(f"({tag}:{weight:.2f})")

            return (",".join(weighted_tags),)

        return ("",)