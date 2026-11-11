"""
@author: Moon-NE
@title: MoonNe_Nodes
@description: Text utilities and NTD11 video mosaic nodes for ComfyUI. Includes weighted random prompts, text concatenation, a video file picker, and folder batch processing.
"""
import logging

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

try:
    from .video_mosaic.nodes import NTD11BatchMosaic, NTD11VideoMosaic, NTD11VideoFile
except ImportError as error:
    logging.getLogger(__name__).warning(
        "MoonNe video nodes could not load: %s. Install this pack's requirements.txt in the ComfyUI Python environment.", error
    )
else:
    NODE_CLASS_MAPPINGS.update({
        "NTD11BatchMosaic": NTD11BatchMosaic,
        "NTD11VideoMosaic": NTD11VideoMosaic,
        "NTD11VideoFile": NTD11VideoFile,
    })
    NODE_DISPLAY_NAME_MAPPINGS.update({
        "NTD11BatchMosaic": "NTD11 Folder Mosaic",
        "NTD11VideoMosaic": "NTD11 Video Mosaic",
        "NTD11VideoFile": "NTD11 Video File",
    })
