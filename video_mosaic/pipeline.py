import fnmatch
import json
import math
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np
import torch
from ultralytics.models.yolo.segment import SegmentationPredictor
from ultralytics.utils import nms


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi"}


@dataclass
class BatchOptions:
    target_classes: str = "pussy,penis,testicles"
    detect_size: int = 640
    batch_size: int = 16
    confidence: float = 0.60
    retry_uncertain: bool = True
    retry_size: int = 960
    padding_percent: float = 3.0
    padding_pixels: int = 2
    bridge_ms: int = 400
    hold_ms: int = 42
    smooth_radius: int = 1
    min_track_frames: int = 2
    block_pixels: int = 16
    scene_threshold: float = 0.30
    encoder: str = "h264_nvenc"
    quality: int = 18
    tracking_confidence: float = 0.30
    male_recheck: bool = True
    male_confidence: float = 0.80
    male_flow_ms: int = 600
    male_hold_ms: int = 84
    male_reacquire_ms: int = 6000
    male_reacquire_confidence: float = .50


def no_cancel():
    pass


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def find_ffmpeg():
    found = shutil.which("ffmpeg")
    if found:
        return found
    winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WinGet/Packages"
    candidates = sorted(winget.glob("Gyan.FFmpeg_*/ffmpeg-*/bin/ffmpeg.exe"))
    if candidates:
        return str(candidates[-1])
    raise FileNotFoundError("FFmpeg was not found. Add its bin folder to PATH.")


class NTD11SegmentPredictor(SegmentationPredictor):
    def postprocess(self, predictions, image, originals, **kwargs):
        # Current Ultralytics Segment returns ((detections, prototypes), training_data).
        head = predictions[0]
        detections, prototypes = head if isinstance(head, tuple) else (head, predictions[1])
        predictions = nms.non_max_suppression(
            detections, self.args.conf, self.args.iou, self.args.classes,
            nc=len(self.model.names), max_det=self.args.max_det,
            max_time_img=float("inf"),
        )
        return self.construct_results(predictions, image, originals, prototypes)


class Detector:
    def __init__(self, yolo, options):
        names = {int(k): v.lower().strip() for k, v in yolo.names.items()}
        wanted = {n.strip().lower() for n in options.target_classes.split(",") if n.strip()}
        unknown = wanted - set(names.values())
        if unknown:
            raise ValueError(f"Unknown model classes: {sorted(unknown)}; available classes: {list(names.values())}")
        if not wanted:
            raise ValueError("Enter at least one target class.")
        if not torch.cuda.is_available():
            raise RuntimeError("Video detection requires an NVIDIA CUDA GPU. Check the driver and the PyTorch build used by ComfyUI.")
        if yolo.task != "segment":
            raise ValueError("Select an NTD11 segmentation model from the segm folder.")
        self.class_ids = [i for i, name in names.items() if name in wanted]
        self.names = names
        self.predictor = NTD11SegmentPredictor(overrides={
            "task": "segment", "device": "0", "quantize": 16,
            "imgsz": options.detect_size, "batch": options.batch_size,
            "conf": min(options.tracking_confidence, options.confidence), "iou": 0.65, "classes": self.class_ids,
            "max_det": 100, "verbose": False, "save": False, "rect": True, "retina_masks": True,
        })
        self.predictor.setup_model(model=yolo.model, verbose=False)
        self.options = options

    def detect(self, images, retry=False, size=None, classes=None):
        self.predictor.args.imgsz = size or (self.options.retry_size if retry else self.options.detect_size)
        self.predictor.args.conf = min(self.options.tracking_confidence, self.options.confidence)
        self.predictor.args.classes = self.class_ids if classes is None else classes
        results = self.predictor(images)
        output = []
        for result in results:
            data = {"raw": [], "segments": []}
            if result.masks is not None:
                boxes = result.boxes.data.cpu().numpy().astype(float).tolist()
                masks = result.masks.data.cpu().numpy().astype(np.uint8)
                for box, mask in zip(boxes, masks):
                    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    polygons = [cv2.approxPolyDP(c, 0.75, True).reshape(-1, 2).tolist()
                                for c in contours if cv2.contourArea(c) >= 2]
                    if polygons:
                        data["raw"].append(box)
                        data["segments"].append(polygons)
            output.append(data)
        return output

    def detect_primary(self, images):
        results = self.detect(images)
        male_ids = [i for i in self.class_ids if self.names[i] == 'penis']
        if self.options.male_recheck and male_ids:
            for size in (320, 416):
                if size != self.options.detect_size:
                    results = [merge_detections(a, b) for a, b in zip(results, self.detect(images, size=size, classes=male_ids))]
        return results


def scene_signature(image):
    small = cv2.resize(image, (64, 64), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    hist = cv2.calcHist([small], [0, 1, 2], None, [4, 4, 4], [0, 256] * 3)
    hist /= max(float(hist.sum()), 1.0)
    return gray, hist


def detect_video(path, detector, options, check_cancel, progress):
    frames, batch, indices = [], [], []
    scene = 0
    previous = None
    started = time.perf_counter()
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        rate = stream.average_rate or Fraction(24)
        expected = stream.frames or max(1, round(float(container.duration or 0) / av.time_base * float(rate)))
        width, height = stream.width, stream.height
        rotation = stream.metadata.get("rotate", "0")
        if int(float(rotation)) % 360:
            raise ValueError("This video has rotation metadata. Export it with the rotation applied before processing.")
        origin = None
        for index, frame in enumerate(container.decode(stream)):
            check_cancel()
            if frame.rotation % 360:
                raise ValueError("This video has a rotation matrix. Apply the rotation before processing.")
            if frame.pts is None:
                raise ValueError("The video has missing frame timestamps, so audio synchronization cannot be preserved.")
            if origin is None:
                origin = frame.pts * frame.time_base
            timestamp = float(frame.pts * frame.time_base - origin)
            if frames and timestamp <= frames[-1]["time"]:
                raise ValueError("Video timestamps are not increasing. Repair or re-encode the source video first.")
            image = frame.to_ndarray(format="bgr24")
            signature = scene_signature(image)
            if previous is not None:
                difference = float(np.mean(np.abs(signature[0] - previous[0])))
                hist_difference = cv2.compareHist(signature[1], previous[1], cv2.HISTCMP_BHATTACHARYYA)
                if difference > options.scene_threshold or (difference > 0.12 and hist_difference > 0.80):
                    scene += 1
            previous = signature
            duration = float(frame.duration * frame.time_base) if frame.duration else 1 / float(rate)
            frames.append({"time": timestamp, "duration": duration, "scene": scene, "raw": [], "segments": []})
            batch.append(image)
            indices.append(index)
            if len(batch) == options.batch_size:
                for frame_index, detections in zip(indices, detector.detect_primary(batch)):
                    frames[frame_index].update(detections)
                batch, indices = [], []
                progress(min(0.50, len(frames) / expected * 0.50))
        if batch:
            for frame_index, detections in zip(indices, detector.detect_primary(batch)):
                frames[frame_index].update(detections)
    if not frames:
        raise ValueError("No video frames could be decoded.")
    retry_indices = set()
    if options.retry_uncertain:
        for i, frame in enumerate(frames):
            neighbors = [frames[j] for j in (i - 1, i + 1) if 0 <= j < len(frames) and frames[j]["scene"] == frame["scene"]]
            if not frame["raw"] or max(d[4] for d in frame["raw"]) < 0.75 or any(len(n["raw"]) > len(frame["raw"]) for n in neighbors):
                retry_indices.add(i)
    recovered = 0
    if retry_indices:
        batch, indices = [], []
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            stream.thread_type = "AUTO"
            for index, frame in enumerate(container.decode(stream)):
                check_cancel()
                if index in retry_indices:
                    batch.append(frame.to_ndarray(format="bgr24"))
                    indices.append(index)
                if len(batch) == options.batch_size or (index == len(frames) - 1 and batch):
                    for frame_index, detections in zip(indices, detector.detect(batch, retry=True)):
                        old = frames[frame_index]["raw"]
                        recovered += int(not old and bool(detections["raw"]))
                        frames[frame_index].update(merge_detections(frames[frame_index], detections))
                    batch, indices = [], []
                progress(0.50 + 0.20 * (index + 1) / len(frames))
    progress(0.70)
    return frames, {
        "width": width, "height": height, "fps": str(rate), "frame_count": len(frames),
        "duration_seconds": frames[-1]["time"] + frames[-1]["duration"], "scene_count": scene + 1,
        "source_video_start_seconds": float(origin),
        "retried_frames": len(retry_indices), "recovered_frames": recovered,
        "detection_seconds": round(time.perf_counter() - started, 3),
    }


def iou(a, b):
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = w * h
    area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    return inter / max(1.0, area_a + area_b - inter)


def merge_detections(first, second):
    candidates = list(zip(first["raw"], first["segments"])) + list(zip(second["raw"], second["segments"]))
    merged = {"raw": [], "segments": []}
    for box, polygons in sorted(candidates, key=lambda item: item[0][4], reverse=True):
        if any(int(box[5]) == int(old[5]) and iou(box, old) > 0.45 for old in merged["raw"]):
            continue
        merged["raw"].append(box)
        merged["segments"].append(polygons)
    return merged


def match_score(a, b):
    if int(a[5]) != int(b[5]):
        return -1
    aw, ah = max(1, a[2] - a[0]), max(1, a[3] - a[1])
    bw, bh = max(1, b[2] - b[0]), max(1, b[3] - b[1])
    distance = math.hypot((a[0] + a[2] - b[0] - b[2]) / 2, (a[1] + a[3] - b[1] - b[3]) / 2)
    normalized = distance / max(math.hypot(aw, ah), math.hypot(bw, bh))
    ratio = max(aw * ah / (bw * bh), bw * bh / (aw * ah))
    max_distance, max_ratio = (1.1, 8) if int(a[5]) == 3 else (.65, 3)
    if normalized > max_distance or ratio > max_ratio:
        return -1
    return iou(a, b) + 0.5 * (1 - normalized / max_distance)


def stabilize(frames, width, height, options):
    tracks = []
    bridge = options.bridge_ms / 1000
    for i, frame in enumerate(frames):
        candidates = []
        for track_id, track in enumerate(tracks):
            last_i, last_box, _ = track[-1]
            if frames[last_i]["scene"] != frame["scene"]:
                continue
            # Adjacent detections always match; bridge controls only missing frames.
            gap_time = frame["time"] - frames[min(last_i + 1, i)]["time"]
            if gap_time > bridge + 1e-6:
                continue
            for detection_id, box in enumerate(frame["raw"]):
                score = match_score(last_box, box)
                if score >= 0:
                    candidates.append((score, track_id, detection_id))
        used_tracks, used_detections = set(), set()
        for score, track_id, detection_id in sorted(candidates, reverse=True):
            if track_id not in used_tracks and detection_id not in used_detections:
                tracks[track_id].append((i, frame["raw"][detection_id], frame["segments"][detection_id]))
                used_tracks.add(track_id)
                used_detections.add(detection_id)
        for detection_id, box in enumerate(frame["raw"]):
            if detection_id not in used_detections:
                tracks.append([(i, box, frame["segments"][detection_id])])
    regions = [[] for _ in frames]
    filled_frames = set()
    rejected = 0
    rejected_weak = 0
    accepted_tracks = 0
    for track in tracks:
        male = int(track[0][1][5]) == 3
        strong_single = male and max(box[4] for _, box, _ in track) >= max(.90, options.male_confidence)
        if len(track) < options.min_track_frames and not strong_single:
            rejected += len(track)
            continue
        threshold = options.male_confidence if male else options.confidence
        anchors = [i for i, box, _ in track if box[4] >= threshold]
        if not anchors:
            rejected_weak += len(track)
            continue
        supported = [(i, box, polygons) for i, box, polygons in track
                     if min(abs(frames[i]["time"] - frames[a]["time"]) for a in anchors) <= max(0.5, bridge)]
        rejected_weak += len(track) - len(supported)
        track = supported
        if len(track) < options.min_track_frames and not strong_single:
            rejected += len(track)
            continue
        accepted_tracks += 1
        positions = {i: (list(box[:4]), polygons, "detected") for i, box, polygons in track}
        for (left_i, left_box, left_polygons), (right_i, right_box, right_polygons) in zip(track, track[1:]):
            if frames[right_i]["time"] - frames[min(left_i + 1, right_i)]["time"] > bridge + 1e-6:
                continue
            span = frames[right_i]["time"] - frames[left_i]["time"]
            for i in range(left_i + 1, right_i):
                alpha = (frames[i]["time"] - frames[left_i]["time"]) / span
                box = [a * (1 - alpha) + b * alpha for a, b in zip(left_box[:4], right_box[:4])]
                anchor_box, anchor_polygons = (left_box, left_polygons) if alpha < 0.5 else (right_box, right_polygons)
                positions[i] = (box, warp_polygons(anchor_polygons, anchor_box, box), "interpolated")
                filled_frames.add(i)
        for anchor, direction in ((track[0], -1), (track[-1], 1)):
            anchor_i, anchor_box, anchor_polygons = anchor
            i = anchor_i + direction
            while 0 <= i < len(frames) and frames[i]["scene"] == frames[anchor_i]["scene"]:
                elapsed = abs(frames[i]["time"] - frames[anchor_i]["time"])
                hold_ms = options.male_hold_ms if male else options.hold_ms
                if elapsed > hold_ms / 1000 + 1e-6:
                    break
                positions[i] = (list(anchor_box[:4]), anchor_polygons, "held")
                filled_frames.add(i)
                i += direction
        for i, (box, polygons, source) in positions.items():
            contours = list(polygons)
            for j in range(max(0, i - options.smooth_radius), min(len(frames), i + options.smooth_radius + 1)):
                if j != i and j in positions:
                    neighbor_box, neighbor_polygons, _ = positions[j]
                    contours.extend(warp_polygons(neighbor_polygons, neighbor_box, box))
            x1, y1, x2, y2 = box
            px = (x2 - x1) * options.padding_percent / 100 + options.padding_pixels
            py = (y2 - y1) * options.padding_percent / 100 + options.padding_pixels
            regions[i].append({"box": box, "polygons": contours, "padding": [math.ceil(px), math.ceil(py)],
                               "source": source, "class": int(track[0][1][5])})
    return regions, {"track_count": accepted_tracks, "temporally_filled_frames": len(filled_frames),
                     "rejected_isolated_detections": rejected, "rejected_weak_detections": rejected_weak}


def warp_polygons(polygons, source_box, target_box):
    source = np.asarray(source_box[:4], dtype=np.float32)
    target = np.asarray(target_box[:4], dtype=np.float32)
    scale = (target[2:] - target[:2]) / np.maximum(source[2:] - source[:2], 1)
    return [((np.asarray(p, dtype=np.float32) - source[:2]) * scale + target[:2]).tolist() for p in polygons]


def region_mask(height, width, regions):
    mask = np.zeros((height, width), dtype=np.uint8)
    for region in regions:
        x1, y1, x2, y2 = region["box"]
        px, py = region["padding"]
        left, top = max(0, math.floor(x1) - px), max(0, math.floor(y1) - py)
        right, bottom = min(width, math.ceil(x2) + px + 1), min(height, math.ceil(y2) + py + 1)
        if right <= left or bottom <= top:
            continue
        local = np.zeros((bottom - top, right - left), dtype=np.uint8)
        for polygon in region["polygons"]:
            points = np.rint(np.asarray(polygon) - [left, top]).astype(np.int32)
            cv2.fillPoly(local, [points], 1)
        if px or py:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (px * 2 + 1, py * 2 + 1))
            local = cv2.dilate(local, kernel)
        mask[top:bottom, left:right] |= local
    return mask


def flow_mask(previous, current, mask, optical_flow):
    backward = optical_flow.calc(current, previous, None)
    forward = optical_flow.calc(previous, current, None)
    yy, xx = np.mgrid[:current.shape[0], :current.shape[1]].astype(np.float32)
    map_x, map_y = xx + backward[..., 0], yy + backward[..., 1]
    warped = cv2.remap(mask, map_x, map_y, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT)
    selected = warped != 0
    area = int(selected.sum())
    if area < 8 or not .35 <= area / max(1, int(mask.sum())) <= 2.5:
        return None
    sampled = cv2.remap(previous, map_x, map_y, cv2.INTER_LINEAR)
    error = np.abs(current.astype(np.float32) - sampled.astype(np.float32))
    reverse = cv2.remap(forward, map_x, map_y, cv2.INTER_LINEAR)
    consistency = np.linalg.norm(backward + reverse, axis=2)
    if float(np.median(error[selected])) > 28 or float(np.mean(consistency[selected] < 3)) < .55:
        return None
    return warped


def propagate_male_masks(path, frames, regions, options, check_cancel=no_cancel, local_flow=False):
    seeds = [i for i, rr in enumerate(regions) if any(r['class'] == 3 and r['source'] == 'detected' for r in rr)]
    if not options.male_recheck or not seeds or options.male_flow_ms <= 0:
        return 0
    limit = options.male_flow_ms / 1000
    wanted = {i for i, f in enumerate(frames)
              if any(frames[s]['scene'] == f['scene'] and abs(frames[s]['time'] - f['time']) <= limit for s in seeds)}
    gray_frames = {}
    with av.open(str(path)) as container:
        for i, frame in enumerate(container.decode(video=0)):
            check_cancel()
            if i in wanted:
                image = frame.to_ndarray(format='gray')
                height, width = image.shape
                scale = min(1., 640 / max(height, width))
                size = (max(1, round(width * scale)), max(1, round(height * scale)))
                gray_frames[i] = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
    optical_flow = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    candidates = {}
    for direction in (1, -1):
        carry, anchor, previous_i = None, None, None
        order = range(len(frames)) if direction == 1 else range(len(frames)-1, -1, -1)
        for i in order:
            check_cancel()
            if i not in gray_frames:
                carry = None
                continue
            model_regions = [r for r in regions[i] if r['class'] == 3 and r['source'] == 'detected']
            if model_regions:
                carry = cv2.resize(region_mask(height, width, model_regions), size, interpolation=cv2.INTER_NEAREST)
                anchor, previous_i = i, i
                continue
            if carry is None:
                continue
            age = abs(frames[i]['time'] - frames[anchor]['time'])
            if age > limit or frames[i]['scene'] != frames[anchor]['scene'] or previous_i != i-direction:
                carry = None
                continue
            if local_flow:
                x, y, w, h = cv2.boundingRect(carry)
                margin = max(48, w // 2, h // 2)
                left, top = max(0, x-margin), max(0, y-margin)
                right, bottom = min(size[0], x+w+margin), min(size[1], y+h+margin)
                crop = np.s_[top:bottom, left:right]
                warped = flow_mask(np.ascontiguousarray(gray_frames[previous_i][crop]),
                                   np.ascontiguousarray(gray_frames[i][crop]),
                                   np.ascontiguousarray(carry[crop]), optical_flow)
                if warped is None:
                    carry = flow_mask(gray_frames[previous_i], gray_frames[i], carry, optical_flow)
                else:
                    carry = np.zeros_like(carry)
                    carry[crop] = warped
            else:
                carry = flow_mask(gray_frames[previous_i], gray_frames[i], carry, optical_flow)
            previous_i = i
            if carry is None:
                continue
            before = any(s < i and frames[s]['scene'] == frames[i]['scene'] and frames[i]['time']-frames[s]['time'] <= 2*limit for s in seeds)
            after = any(s > i and frames[s]['scene'] == frames[i]['scene'] and frames[s]['time']-frames[i]['time'] <= 2*limit for s in seeds)
            if not (before and after) and age * 1000 > options.male_hold_ms + 1e-6:
                continue
            if i in candidates and candidates[i]['flow_age_ms'] <= age * 1000:
                continue
            full_mask = cv2.resize(carry, (width, height), interpolation=cv2.INTER_NEAREST)
            contours, _ = cv2.findContours(full_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            polygons = [cv2.approxPolyDP(c, .75, True).reshape(-1, 2).tolist() for c in contours if cv2.contourArea(c) >= 2]
            if not polygons:
                continue
            x, y, w, h = cv2.boundingRect(full_mask)
            candidates[i] = {'box': [x, y, x+w, y+h], 'polygons': polygons, 'padding': [0, 0],
                             'source': 'optical_flow', 'class': 3, 'flow_age_ms': round(age*1000, 2)}
    for i, region in candidates.items():
        regions[i] = [r for r in regions[i] if r['class'] != 3]
        regions[i].append(region)
    return len(candidates)


def recover_male_reappearances(path, frames, regions, width, height, options, check_cancel=no_cancel):
    if not options.male_recheck or options.male_reacquire_ms <= 0:
        return 0
    references = [(i, box) for i, f in enumerate(frames) for box in f['raw']
                  if int(box[5]) == 3 and box[4] >= options.male_confidence
                  and any(r['class'] == 3 and r['source'] == 'detected' and iou(box, r['box']) >= .5 for r in regions[i])]
    if not references:
        return 0
    candidates = []
    for i, f in enumerate(frames):
        check_cancel()
        item = {**f, 'raw': [], 'segments': []}
        if not any(r['class'] == 3 for r in regions[i]):
            for box, polygons in zip(f['raw'], f['segments']):
                if int(box[5]) != 3:
                    continue
                supported = any(j < i and frames[j]['scene'] == f['scene']
                                and (f['time'] - frames[j]['time']) * 1000 <= options.male_reacquire_ms
                                and iou(box, reference) >= .30 for j, reference in references)
                if supported:
                    item['raw'].append(box)
                    item['segments'].append(polygons)
        candidates.append(item)
    recovery_options = replace(options, male_confidence=options.male_reacquire_confidence,
                               min_track_frames=max(2, options.min_track_frames), male_hold_ms=0)
    recovered, _ = stabilize(candidates, width, height, recovery_options)
    # New appearances get short, image-checked propagation, not a continuous mask through occlusion.
    flow_options = replace(recovery_options, male_flow_ms=min(options.male_flow_ms, 250), male_hold_ms=250)
    propagate_male_masks(path, candidates, recovered, flow_options, check_cancel, local_flow=True)
    added = 0
    for current, extra in zip(regions, recovered):
        if not any(r['class'] == 3 for r in current) and extra:
            for r in extra:
                r['source'] = 'reacquired_' + r['source']
            current.extend(extra)
            added += 1
    return added


def pixelate(image, regions, block):
    if not regions:
        return image
    height, width = image.shape[:2]
    padded_height = math.ceil(height / block) * block
    padded_width = math.ceil(width / block) * block
    padded = cv2.copyMakeBorder(image, 0, padded_height - height, 0, padded_width - width, cv2.BORDER_REPLICATE)
    small = cv2.resize(padded, (padded_width // block, padded_height // block), interpolation=cv2.INTER_AREA)
    mosaic = cv2.resize(small, (padded_width, padded_height), interpolation=cv2.INTER_NEAREST)
    result = image.copy()
    mask = region_mask(height, width, regions).astype(bool)
    result[mask] = mosaic[:height, :width][mask]
    return result


def uncovered_ranges(frames, boxes, fps):
    result, start = [], None
    for i in range(len(frames) + 1):
        empty = i < len(frames) and not boxes[i]
        if empty and start is None:
            start = i
        if not empty and start is not None:
            end = frames[i]["time"] if i < len(frames) else frames[-1]["time"] + frames[-1].get("duration", 1 / fps)
            result.append({"start_seconds": round(frames[start]["time"], 4), "end_seconds": round(end, 4), "frames": i - start})
            start = None
    return result


def render_video(source, destination, frames, boxes, info, options, ffmpeg, check_cancel, progress):
    with tempfile.TemporaryDirectory(prefix="ntd11_", dir=destination.parent) as temp:
        video_file = Path(temp) / "video.mp4"
        with av.open(str(source)) as input_file, av.open(str(video_file), mode="w") as output_file:
            input_stream = input_file.streams.video[0]
            input_stream.thread_type = "AUTO"
            rate = Fraction(info["fps"])
            stream = output_file.add_stream(options.encoder, rate=rate)
            # yuv420p requires even dimensions; pad odd sizes without scaling.
            stream.width = (info["width"] + 1) // 2 * 2
            stream.height = (info["height"] + 1) // 2 * 2
            stream.pix_fmt = "yuv420p"
            stream.time_base = Fraction(1, 90000)
            stream.codec_context.time_base = stream.time_base
            stream.codec_context.max_b_frames = 0
            durations = {round(f["time"] * 90000): round(f["duration"] * 90000) for f in frames}
            if options.encoder == "h264_nvenc":
                stream.options = {"preset": "p4", "rc": "vbr", "cq": str(options.quality), "b": "0"}
            else:
                stream.options = {"preset": "fast", "crf": str(options.quality)}
            encoded = 0
            for index, frame in enumerate(input_file.decode(input_stream)):
                check_cancel()
                image = pixelate(frame.to_ndarray(format="bgr24"), boxes[index], options.block_pixels)
                if image.shape[:2] != (stream.height, stream.width):
                    image = cv2.copyMakeBorder(image, 0, stream.height - image.shape[0], 0, stream.width - image.shape[1], cv2.BORDER_REPLICATE)
                censored = av.VideoFrame.from_ndarray(image, format="bgr24")
                censored.pts = round(frames[index]["time"] * 90000)
                censored.time_base = Fraction(1, 90000)
                censored.duration = durations[censored.pts]
                for packet in stream.encode(censored):
                    packet.duration = durations[packet.pts]
                    output_file.mux(packet)
                encoded += 1
                progress(0.72 + 0.25 * encoded / len(frames))
            for packet in stream.encode():
                packet.duration = durations[packet.pts]
                output_file.mux(packet)
        if encoded != len(frames):
            raise RuntimeError("Frame counts changed between decoding passes. Export was stopped.")
        partial = Path(temp) / "muxed.mp4"
        origin = info["source_video_start_seconds"]
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-copyts",
                   "-i", str(video_file), "-i", str(source), "-map", "0:v:0", "-map", "1:a?",
                   "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-af", f"atrim=start={origin},asetpts=PTS-{origin}/TB",
                   "-map_metadata", "-1", "-avoid_negative_ts", "disabled",
                   "-movflags", "+faststart", str(partial)]
        with tempfile.TemporaryFile() as error_log:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=error_log,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                while process.poll() is None:
                    check_cancel()
                    time.sleep(0.1)
                if process.returncode:
                    error_log.seek(0)
                    raise RuntimeError("FFmpeg could not mux the audio: " + error_log.read().decode("utf-8", errors="replace")[-3000:])
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait()
        if destination.exists():
            raise FileExistsError(f"Output file already exists: {destination}")
        partial.rename(destination)
    progress(1.0)


def process_video(path, destination, detector, options, ffmpeg, check_cancel=no_cancel, progress=lambda value: None):
    started = time.perf_counter()
    original_stat = path.stat()
    frames, info = detect_video(path, detector, options, check_cancel, progress)
    boxes, tracking = stabilize(frames, info["width"], info["height"], options)
    info.update(tracking)
    info['male_flow_frames'] = propagate_male_masks(path, frames, boxes, options, check_cancel)
    info['male_reacquired_frames'] = recover_male_reappearances(path, frames, boxes, info['width'], info['height'], options, check_cancel)
    info['male_detected_frames'] = sum(any(int(b[5]) == 3 for b in f['raw']) for f in frames)
    info['male_covered_frames'] = sum(any(r['class'] == 3 for r in rr) for rr in boxes)
    info["pipeline_version"] = 4
    info["fallback_frames"] = 0
    areas = [float(region_mask(info["height"], info["width"], regions).mean()) for regions in boxes]
    info["mask_coverage"] = {"mean": float(np.mean(areas)), "max": max(areas),
                              "near_full_frame_count": sum(a >= 0.9 for a in areas)}
    info["raw_detected_frames"] = sum(bool(f["raw"]) for f in frames)
    info["covered_frames"] = sum(bool(b) for b in boxes)
    info["uncovered_intervals"] = uncovered_ranges(frames, boxes, float(Fraction(info["fps"])))
    info["input"] = str(path)
    info["options"] = asdict(options)
    current_stat = path.stat()
    if (original_stat.st_size, original_stat.st_mtime_ns) != (current_stat.st_size, current_stat.st_mtime_ns):
        raise RuntimeError("The input video changed during processing. Run again.")
    if info["covered_frames"]:
        render_video(path, destination, frames, boxes, info, options, ffmpeg, check_cancel, progress)
        info["output"] = str(destination)
        info["status"] = "needs_review" if info["uncovered_intervals"] or info["rejected_isolated_detections"] else "processed"
    else:
        info["status"] = "no_detection_review_required"
        info["output"] = None
        progress(1.0)
    info["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    info["processing_fps"] = round(len(frames) / max(time.perf_counter() - started, 0.001), 2)
    audit = {**info, "frames": [{**f, "mosaic_regions": b, "mask_area_ratio": a} for f, b, a in zip(frames, boxes, areas)]}
    write_json(destination.with_suffix(".audit.json"), audit)
    return info


def run_folder(yolo, input_root, output_root, pattern, recursive, options, check_cancel=no_cancel, progress=lambda value: None):
    input_root, output_root = input_root.resolve(), output_root.resolve()
    if not input_root.is_dir():
        raise FileNotFoundError(f"Input folder does not exist: {input_root}")
    if input_root.is_relative_to(output_root):
        raise ValueError("The output folder cannot be the input folder or one of its parent folders.")
    patterns = [p.strip().lower() for p in pattern.split(";") if p.strip()]
    iterator = input_root.rglob("*") if recursive else input_root.iterdir()
    paths = sorted(p for p in iterator if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
                   and not p.resolve().is_relative_to(output_root)
                   and any(fnmatch.fnmatchcase(p.name.lower(), q) for q in patterns))
    if not paths:
        raise ValueError("No matching videos found. Check input_folder and file_pattern.")
    return run_paths(yolo, paths, input_root, output_root, options, check_cancel, progress)


def run_video(yolo, video_path, output_root, options, check_cancel=no_cancel, progress=lambda value: None):
    path = video_path.resolve()
    if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError("Choose a supported video file.")
    return run_paths(yolo, [path], path.parent, output_root.resolve(), options, check_cancel, progress)


def run_paths(yolo, paths, input_root, output_root, options, check_cancel, progress):
    if options.encoder not in {"h264_nvenc", "libx264"}:
        raise ValueError("Unsupported encoder.")
    ffmpeg = find_ffmpeg()
    check_cancel()
    detector = Detector(yolo, options)
    run_dir = output_root / (datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    run_dir.mkdir(parents=True, exist_ok=False)
    report = {"run_directory": str(run_dir), "model_classes": detector.names, "files": [],
              "note": "Review the output for missed or incorrect regions. uncovered_intervals lists times without a mask; these are not necessarily missed detections. If no target is detected in the entire video, only a report is saved."}
    write_json(run_dir / "report.json", report)
    try:
        for file_number, path in enumerate(paths):
            check_cancel()
            relative = path.relative_to(input_root)
            destination = run_dir / relative.parent / (path.stem + "_" + path.suffix[1:] + "_mosaic.mp4")
            destination.parent.mkdir(parents=True, exist_ok=True)
            print(f"[NTD11] {file_number + 1}/{len(paths)}: {ascii(path.name)}", flush=True)
            # Only per-file media/runtime errors continue; Comfy cancellation propagates.
            try:
                result = process_video(path, destination, detector, options, ffmpeg, check_cancel,
                                       lambda value: progress((file_number + value) / len(paths)))
                report["files"].append(result)
                print(f"[NTD11] {result['status']}: {result['elapsed_seconds']} s, {result['covered_frames']}/{result['frame_count']} frames", flush=True)
            except (av.error.FFmpegError, OSError, ValueError, RuntimeError) as error:
                report["files"].append({"input": str(path), "status": "error", "error": str(error)})
            write_json(run_dir / "report.json", report)
    finally:
        write_json(run_dir / "report.json", report)
    progress(1.0)
    return report
