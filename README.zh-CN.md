# MoonNe_Nodes

ComfyUI 的文本处理和视频打码节点。文本节点可以拼接提示词、随机选词、设置出现概率和权重；视频节点使用 NTD11 分割模型给指定部位打马赛克，支持单个视频和文件夹批量处理。

## 安装与更新

在 ComfyUI Manager 中搜索 **MoonNe_Nodes**，安装或更新后重启 ComfyUI，再刷新网页。

也可以在 `ComfyUI/custom_nodes` 中安装：

```sh
git clone https://github.com/Moon-NE/MoonNe_Nodes.git
```

用 **ComfyUI 自己的 Python 环境**安装依赖：

```sh
python -m pip install -r custom_nodes/MoonNe_Nodes/requirements.txt
```

Windows 便携版在 ComfyUI 上一级目录执行：

```bat
python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\MoonNe_Nodes\requirements.txt
```

如果之前安装过 `ComfyUI-NTD11-BatchMosaic`，请先在 Manager 中禁用旧包，或将旧目录移出 `custom_nodes`，再重启。三个视频节点的内部名称保持不变，已有工作流可以继续使用。

## 视频打码

目前视频检测需要 **NVIDIA CUDA 显卡**，并需要以下组件：

1. 在 Manager 中安装 **ComfyUI Impact Subpack**，用于加载检测模型。
2. 将 `ntd11_anime_nsfw_segm_v4_all.pt` 放入 `ComfyUI/models/ultralytics/segm/`。模型需自行准备，仓库不包含权重。
3. 安装 [FFmpeg](https://ffmpeg.org/download.html)，让命令行可以找到 `ffmpeg`。Windows 下也支持通过 WinGet 安装的 Gyan FFmpeg。

### 处理单个视频

导入 [选择视频工作流](examples/ntd11_video_file.json)，在“NTD11 Video File”节点点击 **Choose video file...**。等文件名显示后，点击 ComfyUI 的“运行”。

视频会复制到 `ComfyUI/input/ntd11_videos`。处理结果默认保存在 `ComfyUI/output/ntd11_mosaic`，每次运行新建一个文件夹。原视频不会被覆盖。

### 批量处理

导入 [文件夹批量工作流](examples/ntd11_folder_batch.json)，设置 `input_folder` 和 `output_folder` 后运行。

- `file_pattern`：默认 `*`，也可填写 `*.mp4;*.webm`。
- `recursive`：开启后处理子文件夹。
- 支持 MP4、MKV、WebM、MOV、M4V、AVI；结果为 MP4，并保留音轨。

### 常用设置

先使用工作流中的默认值，再按成品调整。

| 参数 | 用途 |
| --- | --- |
| `target_classes` | 默认处理 `pussy,penis,testicles`。需要时添加 `anus` 或 `nipples`，用英文逗号分隔。 |
| `block_pixels` | 马赛克块大小，默认 16。数值越大，块越粗。 |
| `padding_pixels` / `padding_percent` | 扩大打码边缘。边缘漏出时可适当增加。 |
| `confidence` | 检测确认阈值。调高可减少误码，也可能增加漏码。 |
| `batch_size` | 一次检测的帧数。显存不足时减小。 |
| `male_recheck` | 对男性目标额外检测，用于减少快速出现、遮挡后出现时的漏码。 |
| `encoder` | 默认 `h264_nvenc`，使用 NVIDIA 硬件编码。编码失败时可改成 `libx264`；检测仍需要 CUDA。 |
| `quality` | 默认 18，越小画质越高、文件越大。 |

节点会根据目标轮廓打码，并补齐短暂漏检，减少马赛克闪烁。自动检测仍会误码或漏码，完成后请检查成品。报告中的 `needs_review` 表示有时段需要检查，不代表处理失败；全片没有检测到目标时，只生成报告。

## 文本节点

| 节点 | 用法 |
| --- | --- |
| **∞ Text Concatenate** | 按接口顺序拼接文本。设置 `delimiter` 分隔符；连接后自动增加输入接口。 |
| **Text Horizontal To Vertical** | 将多行文字转为从右向左的竖排格式。关闭 `enable_convert` 可输出原文。 |
| **Batch Conditional Text** | 根据 `batch_index` 范围和 `probability` 决定是否输出文本。 |
| **Batch Conditional Text Weight** | 在条件输出的基础上，为每个逗号分隔的词分配随机权重。范围由 `min_weight`、`max_weight` 设置。 |
| **batch random text** | 从输入文本中随机选一段，`weights` 按接口顺序填写。比如 `1, 2, 3` 表示第三段被选中的机会最大。 |

两个条件文本节点的范围规则相同：`greater_than < less_than` 时包含两端；顺序反过来时取两端范围之外；相等时只匹配该编号。不满足条件时输出空字符串。

例如，`greater_than=25`、`less_than=40`、`probability=0.5`，表示编号 25 到 40 之间有一半机会输出文本。固定 `seed` 可复现结果；需要每次换结果时，将种子操作设为 `randomize`。

## 视频代码许可

视频处理模块沿用 [AGPL-3.0-or-later](video_mosaic/LICENSE.txt)。第三方模型和依赖按各自发布条款使用。
