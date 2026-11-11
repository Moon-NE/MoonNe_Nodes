import json
from pathlib import Path

import folder_paths
from comfy import model_management
from comfy.utils import ProgressBar

from .pipeline import BatchOptions, VIDEO_EXTENSIONS, run_folder, run_video


class NTD11BatchMosaic:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "detector": ("BBOX_DETECTOR",),
            "input_folder": ("STRING", {"default": str(Path(folder_paths.get_input_directory()) / "mosaic_input")}),
            "output_folder": ("STRING", {"default": str(Path(folder_paths.get_output_directory()) / "ntd11_mosaic")}),
            "file_pattern": ("STRING", {"default": "*", "tooltip": "Match video filenames. Separate patterns with semicolons, for example *.mp4;*.webm."}),
            "recursive": ("BOOLEAN", {"default": False}),
            "target_classes": ("STRING", {"default": "pussy,penis,testicles"}),
            "detect_size": ("INT", {"default": 640, "min": 320, "max": 2048, "step": 32}),
            "batch_size": ("INT", {"default": 16, "min": 1, "max": 64}),
            "confidence": ("FLOAT", {"default": 0.60, "min": 0.01, "max": 0.95, "step": 0.01, "tooltip": "A tracked target needs at least one detection above this score to be confirmed."}),
            "retry_uncertain": ("BOOLEAN", {"default": True, "tooltip": "Check uncertain frames again at a higher resolution."}),
            "retry_size": ("INT", {"default": 960, "min": 320, "max": 2048, "step": 32}),
            "padding_percent": ("FLOAT", {"default": 3.0, "min": 0, "max": 100, "step": 1}),
            "padding_pixels": ("INT", {"default": 2, "min": 0, "max": 128}),
            "bridge_ms": ("INT", {"default": 400, "min": 0, "max": 1000, "step": 10}),
            "hold_ms": ("INT", {"default": 42, "min": 0, "max": 500, "step": 1}),
            "smooth_radius": ("INT", {"default": 1, "min": 0, "max": 8}),
            "min_track_frames": ("INT", {"default": 2, "min": 1, "max": 10, "tooltip": "Minimum detections needed to confirm a target. A value of 1 can catch brief targets but may add false positives."}),
            "block_pixels": ("INT", {"default": 16, "min": 4, "max": 128, "tooltip": "Block size in source pixels. The grid stays fixed to reduce flicker."}),
            "scene_threshold": ("FLOAT", {"default": 0.30, "min": 0.05, "max": 0.95, "step": 0.01}),
            "encoder": (["h264_nvenc", "libx264"],),
            "quality": ("INT", {"default": 18, "min": 0, "max": 40, "tooltip": "Lower values give higher quality and larger files. Uses CQ for NVENC and CRF for x264."}),
            "tracking_confidence": ("FLOAT", {"default": 0.30, "min": 0.01, "max": 0.95, "step": 0.01, "tooltip": "Lower-confidence detections can extend an already confirmed target."}),
            "male_recheck": ("BOOLEAN", {"default": True, "tooltip": "Run additional checks at 320 and 416 pixels and track motion between detections for male targets."}),
            "male_confidence": ("FLOAT", {"default": 0.80, "min": 0.01, "max": 0.99, "step": 0.01, "tooltip": "Confirmation score for male targets. Brief single-frame detections scoring at least 0.90 are also kept."}),
            "male_flow_ms": ("INT", {"default": 600, "min": 0, "max": 1500, "step": 10, "tooltip": "Maximum time in milliseconds to follow a confirmed male target through a detection gap."}),
            "male_hold_ms": ("INT", {"default": 84, "min": 0, "max": 300, "step": 1, "tooltip": "Keep the mask briefly when a male target disappears. The default is about 2 frames at 24 fps."}),
            "male_reacquire_ms": ("INT", {"default": 6000, "min": 0, "max": 15000, "step": 100, "tooltip": "How long to look for a male target reappearing near its previous position in the same shot, in milliseconds. Set to 0 to disable."}),
            "male_reacquire_confidence": ("FLOAT", {"default": 0.50, "min": 0.10, "max": 0.95, "step": 0.01, "tooltip": "Score used for a target reappearing near a confirmed position. Requires at least two candidate frames."}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("report",)
    FUNCTION = "process"
    OUTPUT_NODE = True
    CATEGORY = "MoonNe/Video"
    DESCRIPTION = "Apply mosaic to detected regions in a folder of videos. Supports subfolders, keeps audio, and saves results to a separate output folder."

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def process(self, detector, input_folder, output_folder, file_pattern, recursive, **kwargs):
        progress = ProgressBar(1000)
        options = BatchOptions(**kwargs)
        report = run_folder(
            detector.bbox_model, Path(input_folder.strip().strip('"')),
            Path(output_folder.strip().strip('"')), file_pattern, recursive, options,
            check_cancel=model_management.throw_exception_if_processing_interrupted,
            progress=lambda value: progress.update_absolute(round(value * 1000)),
        )
        return (json.dumps(report, ensure_ascii=False, indent=2),)


class NTD11VideoMosaic(NTD11BatchMosaic):
    @classmethod
    def INPUT_TYPES(cls):
        fields = dict(super().INPUT_TYPES()['required'])
        for name in ('input_folder', 'file_pattern', 'recursive'):
            fields.pop(name)
        detector = fields.pop('detector')
        return {'required': {'detector': detector, 'video': ('NTD11_VIDEO',), **fields}}

    DESCRIPTION = 'Apply mosaic to the selected video and keep its audio. Connect a Video File node and an NTD11 segmentation detector, then run.'

    def process(self, detector, video, output_folder, **kwargs):
        progress = ProgressBar(1000)
        report = run_video(
            detector.bbox_model, NTD11VideoFile.resolve_video(video), Path(output_folder.strip().strip('"')),
            BatchOptions(**kwargs), check_cancel=model_management.throw_exception_if_processing_interrupted,
            progress=lambda value: progress.update_absolute(round(value * 1000)),
        )
        return (json.dumps(report, ensure_ascii=False, indent=2),)


class NTD11VideoFile:
    @classmethod
    def INPUT_TYPES(cls):
        input_root = Path(folder_paths.get_input_directory())
        videos = sorted(p.relative_to(input_root).as_posix() for p in (input_root/'ntd11_videos').glob('*')
                        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS)
        return {'required': {'video': ([''] + videos, {'tooltip': 'Click Choose video file... to select a video from your computer.'})}}

    RETURN_TYPES = ('NTD11_VIDEO',)
    RETURN_NAMES = ('video',)
    FUNCTION = 'select'
    CATEGORY = 'MoonNe/Video'
    DESCRIPTION = 'Choose a video from your computer and connect this node to NTD11 Video Mosaic.'

    @staticmethod
    def resolve_video(video):
        input_root = Path(folder_paths.get_input_directory()).resolve()
        path = (input_root / video).resolve()
        if not video or not path.is_relative_to(input_root) or not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
            raise ValueError('Click Choose video file... and select a supported video first.')
        return path

    @classmethod
    def VALIDATE_INPUTS(cls, video):
        try:
            cls.resolve_video(video)
        except ValueError as error:
            return str(error)
        return True

    @classmethod
    def IS_CHANGED(cls, video):
        return cls.resolve_video(video).stat().st_mtime_ns

    def select(self, video):
        self.resolve_video(video)
        return (video,)


NODE_CLASS_MAPPINGS = {'NTD11BatchMosaic': NTD11BatchMosaic, 'NTD11VideoMosaic': NTD11VideoMosaic, 'NTD11VideoFile': NTD11VideoFile}
NODE_DISPLAY_NAME_MAPPINGS = {'NTD11BatchMosaic': 'NTD11 Folder Mosaic', 'NTD11VideoMosaic': 'NTD11 Video Mosaic', 'NTD11VideoFile': 'NTD11 Video File'}
