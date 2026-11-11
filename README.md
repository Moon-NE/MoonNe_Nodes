# MoonNe_Nodes

Text utilities and NTD11 video mosaic nodes for ComfyUI. Join prompts, pick weighted random text, or apply mosaic to detected regions in a video or a folder of videos.

[中文说明](README.zh-CN.md)

## Install or update

Search for **MoonNe_Nodes** in ComfyUI Manager. Install or update the pack, restart ComfyUI, and refresh the page.

For a manual install, clone this repository into `ComfyUI/custom_nodes`:

```sh
git clone https://github.com/Moon-NE/MoonNe_Nodes.git
```

Install dependencies using **the Python environment that runs ComfyUI**. From the ComfyUI directory:

```sh
python -m pip install -r custom_nodes/MoonNe_Nodes/requirements.txt
```

For the Windows portable build, run this from the directory containing `python_embeded`:

```bat
python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\MoonNe_Nodes\requirements.txt
```

If you previously installed `ComfyUI-NTD11-BatchMosaic`, disable that pack in Manager or move its folder out of `custom_nodes`, then restart. The three video node IDs are unchanged, so existing workflows still load.

## Video mosaic

Video detection currently requires an **NVIDIA CUDA GPU**. You also need:

1. **ComfyUI Impact Subpack**, available in Manager, for `UltralyticsDetectorProvider`.
2. `ntd11_anime_nsfw_segm_v4_all.pt` in `ComfyUI/models/ultralytics/segm/`. Model weights are not included in this repository.
3. [FFmpeg](https://ffmpeg.org/download.html) on your PATH. On Windows, the Gyan FFmpeg package installed through WinGet is also detected.

### One video

Load [the file picker workflow](examples/ntd11_video_file.json). Click **Choose video file...** on the **NTD11 Video File** node, wait for the filename to appear, and click **Run**.

The selected video is copied to `ComfyUI/input/ntd11_videos`. Results go to `ComfyUI/output/ntd11_mosaic`, with a new folder for each run. The original file is kept.

### A folder of videos

Load [the batch workflow](examples/ntd11_folder_batch.json), set `input_folder` and `output_folder`, and run it.

- `file_pattern`: use `*` for all supported videos, or patterns such as `*.mp4;*.webm`.
- `recursive`: include subfolders when enabled.
- Supported inputs: MP4, MKV, WebM, MOV, M4V, and AVI. Output is MP4 with audio preserved.

### Settings

Start with the workflow defaults and adjust after checking a result.

| Setting | What it does |
| --- | --- |
| `target_classes` | Defaults to `pussy,penis,testicles`. Add `anus` or `nipples` if needed, separated by commas. |
| `block_pixels` | Mosaic block size in source pixels. Default: 16. Larger values make coarser blocks. |
| `padding_pixels` / `padding_percent` | Expand mask edges. Increase slightly if the edges of a target remain visible. |
| `confidence` | Detection confirmation score. Raising it can reduce false positives but may miss more targets. |
| `batch_size` | Frames processed together. Lower it if you run out of VRAM. |
| `male_recheck` | Additional checks for male targets that appear briefly or return after an occlusion. |
| `encoder` | `h264_nvenc` uses NVIDIA hardware encoding. Try `libx264` if encoding fails; detection still requires CUDA. |
| `quality` | Default: 18. Lower values give higher quality and larger files. |

Masks follow the detected contours. Short gaps are filled to reduce flicker. Check the finished video for missed or incorrect regions. A report marked `needs_review` means some sections need checking, not that processing failed. If the entire video has no detections, the node saves a report without exporting a video.

## Text nodes

| Node | Usage |
| --- | --- |
| **∞ Text Concatenate** | Join inputs in socket order using `delimiter`. Connecting an input adds another socket. |
| **Text Horizontal To Vertical** | Turn horizontal lines into vertical columns read from right to left. Disable `enable_convert` to keep the original text. |
| **Batch Conditional Text** | Output text when `batch_index` matches the range and `probability` settings. |
| **Batch Conditional Text Weight** | Conditional text output with a random weight for each comma-separated tag, between `min_weight` and `max_weight`. |
| **batch random text** | Pick one input using `weights` in socket order. With `1, 2, 3`, the third input is most likely to be selected. |

For the two conditional nodes, `greater_than < less_than` selects the range including both endpoints. Reversing them selects values strictly outside the range. Equal values select that exact index. A failed condition outputs an empty string.

For example, `greater_than=25`, `less_than=40`, and `probability=0.5` give indices 25 through 40 a 50% chance of outputting the text. Keep `seed` fixed to repeat a result, or set its after-generation control to `randomize` for a new selection each run.

## Video module license

The video processing module is distributed under [AGPL-3.0-or-later](video_mosaic/LICENSE.txt). Third-party models and dependencies retain their own licenses.
