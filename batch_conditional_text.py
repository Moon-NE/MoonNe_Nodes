import random


class BatchConditionalText:

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
        self, batch_index, text, greater_than, less_than, probability, seed
    ):
        probability = max(0.0, min(1.0, probability))

        rng = random.Random(f"{seed}_{batch_index}")

        condition = False

        if greater_than < less_than:
            condition = greater_than <= batch_index <= less_than
        elif greater_than > less_than:
            condition = batch_index > greater_than or batch_index < less_than
        else:
            condition = batch_index == greater_than

        if condition and rng.random() < probability:
            return (text,)

        return ("",)