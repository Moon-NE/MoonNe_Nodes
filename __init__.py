from .batch_conditional_text import BatchConditionalText
from .TextHorizontalToVertical import TextHorizontalToVertical
from .Moon_NE_Text_Concatenate import Moon_NE_Text_Concatenate
from .batch_conditional_text_Weight import BatchConditionalTextWeight
from .batch_randoml_text import batch_randoml_text

NODE_CLASS_MAPPINGS = {
    "BatchConditionalText": BatchConditionalText,
    "TextHorizontalToVertical": TextHorizontalToVertical,
    "Moon_NE_Text_Concatenate": Moon_NE_Text_Concatenate,
    "BatchConditionalTextWeight": BatchConditionalTextWeight,
    "batch_randoml_text": batch_randoml_text,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "BatchConditionalText": "Batch Conditional Text",
    "TextHorizontalToVertical": "Text Horizontal To Vertical",
    "Moon_NE_Text_Concatenate": "∞ Text Concatenate",
    "BatchConditionalTextWeight": "Batch Conditional Text Weight",
    "batch_randoml_text": "batch random text",
}

WEB_DIRECTORY = "./js"

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']