import sys
import copy
import unittest
import tempfile
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video_mosaic"))
from pipeline import BatchOptions, Detector, find_ffmpeg, flow_mask, merge_detections, pixelate, recover_male_reappearances, region_mask, render_video, stabilize, uncovered_ranges


def polygons(box):
    x1, y1, x2, y2 = box[:4]
    return [[[x1, y1], [x2-1, y1], [x2-1, y2-1], [x1, y2-1]]]


def region(box):
    return {"box": box, "polygons": polygons(box), "padding": [0, 0]}


def frame(t, boxes=(), scene=0):
    return {"time": t, "scene": scene, "raw": list(boxes), "segments": [polygons(b) for b in boxes]}


def detection(x, cls=1):
    return [x, 20, x + 20, 40, 0.8, cls]


class TemporalTests(unittest.TestCase):
    def setUp(self):
        self.options = BatchOptions(bridge_ms=250, hold_ms=0, smooth_radius=0,
                                    padding_percent=0, padding_pixels=0, block_pixels=4, min_track_frames=1)

    def test_bidirectional_gap_and_detection_coverage(self):
        frames = [frame(0, [detection(20)]), frame(.05), frame(.10, [detection(32)])]
        boxes, stats = stabilize(frames, 100, 100, self.options)
        self.assertEqual(stats["track_count"], 1)
        self.assertEqual(boxes[1][0]["box"], [26, 20, 46, 40])
        self.assertEqual(stats["temporally_filled_frames"], 1)
        for f, masks in zip(frames, boxes):
            for d in f["raw"]:
                self.assertTrue(any(r["box"][0] <= d[0] and r["box"][1] <= d[1] and r["box"][2] >= d[2] and r["box"][3] >= d[3] for r in masks))

    def test_no_cross_scene_propagation(self):
        self.options.hold_ms = 200
        frames = [frame(0, [detection(20)]), frame(.05, scene=1), frame(.10, [detection(24)], scene=2)]
        boxes, stats = stabilize(frames, 100, 100, self.options)
        self.assertEqual(boxes[1], [])
        self.assertEqual(stats["track_count"], 2)

    def test_long_gap_not_bridged(self):
        frames = [frame(i / 20) for i in range(21)]
        frames[0]["raw"], frames[-1]["raw"] = [detection(20)], [detection(24)]
        frames[0]["segments"], frames[-1]["segments"] = [polygons(detection(20))], [polygons(detection(24))]
        boxes, _ = stabilize(frames, 100, 100, self.options)
        self.assertFalse(boxes[10])

    def test_distinct_objects_do_not_merge(self):
        frames = [frame(0, [detection(5), detection(70)]), frame(.05, [detection(7), detection(68)])]
        boxes, stats = stabilize(frames, 100, 100, self.options)
        self.assertEqual(stats["track_count"], 2)
        self.assertEqual(len(boxes[1]), 2)

    def test_smoothing_does_not_cover_the_motion_path(self):
        self.options.smooth_radius = 2
        frames = [frame(0, [detection(10)]), frame(.05, [detection(20)]), frame(.10, [detection(30)])]
        boxes, _ = stabilize(frames, 100, 100, self.options)
        mask = region_mask(100, 100, boxes[1])
        self.assertEqual(int(mask.sum()), 400)
        self.assertFalse(mask[:, :20].any())
        self.assertFalse(mask[:, 40:].any())

    def test_grid_is_stable_and_only_masked_pixels_change(self):
        rng = np.random.default_rng(1)
        image = rng.integers(0, 256, (65, 67, 3), dtype=np.uint8)
        a = pixelate(image, [region([16, 16, 48, 48])], 16)
        b = pixelate(image, [region([16, 16, 64, 64])], 16)
        np.testing.assert_array_equal(a[16:48, 16:48], b[16:48, 16:48])
        np.testing.assert_array_equal(a[:16], image[:16])
        self.assertFalse(np.array_equal(a[16:48, 16:48], image[16:48, 16:48]))

    def test_zero_detection_ranges(self):
        frames = [frame(0), frame(.04), frame(.08)]
        self.assertEqual(uncovered_ranges(frames, [[], [], [[0, 0, 1, 1]]], 25),
                         [{"start_seconds": 0, "end_seconds": .08, "frames": 2}])

    def test_no_scene_wide_mask_on_empty_frames(self):
        frames = [frame(0, [[0, 0, 20, 20, .9, 1]]), frame(.1), frame(.2, [[80, 80, 100, 100, .9, 1]])]
        regions, _ = stabilize(frames, 100, 100, self.options)
        self.assertEqual(regions[1], [])
        self.assertEqual(region_mask(100, 100, regions[1]).sum(), 0)

    def test_segmentation_preserves_pixels_inside_box_outside_contour(self):
        r = region([16, 16, 48, 48])
        r["polygons"] = [[[32, 16], [47, 47], [16, 47]]]
        image = np.random.default_rng(5).integers(0, 256, (64, 64, 3), dtype=np.uint8)
        output = pixelate(image, [r], 16)
        np.testing.assert_array_equal(output[16:23, 16:23], image[16:23, 16:23])
        self.assertFalse(np.array_equal(output[36:40, 30:34], image[36:40, 30:34]))

    def test_isolated_false_detection_is_removed(self):
        self.options.min_track_frames = 2
        frames = [frame(0, [detection(10)]), frame(.04, [detection(12), detection(75)]), frame(.08, [detection(14)])]
        regions, stats = stabilize(frames, 100, 100, self.options)
        self.assertEqual(stats["rejected_isolated_detections"], 1)
        self.assertTrue(all(len(r) == 1 for r in regions))

    def test_retry_does_not_inflate_overlapping_regions(self):
        a, b = frame(0, [detection(20)]), frame(0, [[18, 18, 42, 42, .65, 1]])
        merged = merge_detections(a, b)
        self.assertEqual(merged["raw"], a["raw"])
        self.assertEqual(merged["segments"], a["segments"])

    def test_retry_keeps_confidence_threshold(self):
        from types import SimpleNamespace
        class FakePredictor:
            args = SimpleNamespace(imgsz=640, conf=.6)
            def __call__(self, images):
                return []
        detector = Detector.__new__(Detector)
        detector.options = BatchOptions(confidence=.6)
        detector.class_ids = [1, 3, 6]
        detector.predictor = FakePredictor()
        detector.detect([], retry=False)
        first_threshold = detector.predictor.args.conf
        detector.detect([], retry=True)
        self.assertEqual(detector.predictor.args.conf, first_threshold)

    def test_weak_track_requires_a_strong_anchor(self):
        self.options.min_track_frames = 2
        weak = [[10, 20, 30, 40, .4, 1]]
        frames = [frame(0, weak), frame(.04, weak), frame(.08, weak)]
        regions, stats = stabilize(frames, 100, 100, self.options)
        self.assertTrue(all(not r for r in regions))
        self.assertEqual(stats["rejected_weak_detections"], 3)
        frames[1]["raw"][0] = [10, 20, 30, 40, .8, 1]
        regions, _ = stabilize(frames, 100, 100, self.options)
        self.assertTrue(all(regions))

    def test_removed_weak_span_is_not_bridged_again(self):
        frames = [frame(i / 10, [[20, 20, 40, 40, .4, 1]]) for i in range(21)]
        frames[0]["raw"][0][4] = .8
        frames[-1]["raw"][0][4] = .8
        regions, _ = stabilize(frames, 100, 100, self.options)
        self.assertTrue(regions[0])
        self.assertTrue(regions[-1])
        self.assertFalse(regions[10])

    def test_male_entry_survives_scale_change_and_later_confirmation(self):
        self.options.min_track_frames = 2
        self.options.bridge_ms = 400
        frames = [frame(i/24) for i in range(13)]
        boxes = {0: [0,126,21,176,.68,3], 1: [0,107,48,180,.65,3],
                 11: [24,260,159,401,.85,3], 12: [37,264,171,405,.90,3]}
        for i, box in boxes.items():
            frames[i] = frame(i/24,[box])
        regions, _ = stabilize(frames,640,640,self.options)
        self.assertTrue(regions[0])
        self.assertTrue(regions[1])

    def test_confident_single_frame_male_is_retained(self):
        self.options.min_track_frames = 2
        regions, _ = stabilize([frame(0,[[0,400,90,486,.94,3]])],640,640,self.options)
        self.assertTrue(regions[0])

    def test_male_exit_has_short_hold_and_then_stops(self):
        frames = [frame(0,[[0,400,90,486,.94,3]])] + [frame(i/24) for i in range(1,6)]
        regions, _ = stabilize(frames,640,640,self.options)
        self.assertTrue(regions[1])
        self.assertTrue(regions[2])
        self.assertFalse(any(regions[3:]))

    def test_persistent_weak_male_false_positive_is_rejected(self):
        frames = [frame(i/24,[[510,600,550,640,.72,3]]) for i in range(6)]
        regions, _ = stabilize(frames,640,640,self.options)
        self.assertFalse(any(regions))

    def test_optical_flow_follows_translation_and_rejects_occlusion(self):
        rng = np.random.default_rng(3)
        previous = rng.integers(0,256,(96,96),dtype=np.uint8)
        current = cv2.warpAffine(previous,np.float32([[1,0,5],[0,1,3]]),(96,96))
        mask = np.zeros((96,96),np.uint8)
        mask[30:55,30:55] = 1
        flow = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        actual = flow_mask(previous,current,mask,flow)
        expected = cv2.warpAffine(mask,np.float32([[1,0,5],[0,1,3]]),(96,96))
        self.assertIsNotNone(actual)
        self.assertGreater(np.logical_and(actual,expected).sum()/np.logical_or(actual,expected).sum(),.90)
        self.assertIsNone(flow_mask(previous,np.full_like(previous,255),mask,flow))

    def test_reappearance_uses_prior_target_and_preserves_existing_masks(self):
        self.options.male_flow_ms = 0
        frames = [frame(0,[[20,20,40,40,.95,3]]), frame(.04,[[20,20,40,40,.94,3]]),
                  frame(1,[[21,20,41,40,.55,3],[75,70,95,90,.7,3]]),
                  frame(1.04,[[22,20,42,40,.4,3],[76,70,96,90,.7,3]])]
        original, _ = stabilize(frames,100,100,self.options)
        snapshot = copy.deepcopy(original)
        recovered = recover_male_reappearances(Path('unused.mp4'),frames,original,100,100,self.options)
        self.assertEqual(recovered,2)
        self.assertEqual(original[:2],snapshot[:2])
        for rr in original[2:]:
            self.assertEqual(len(rr),1)
            self.assertLess(rr[0]['box'][2],50)
            self.assertEqual(rr[0]['source'],'reacquired_detected')

    def test_reappearance_rejects_cut_expiry_and_single_weak_frame(self):
        self.options.male_flow_ms = 0
        for scene,times,boxes in [(1,[1,1.04],[.6,.6]),(0,[7,7.04],[.6,.6]),(0,[1,1.04],[.6,None])]:
            frames = [frame(0,[[20,20,40,40,.95,3]])]
            frames += [frame(t,[[20,20,40,40,score,3]] if score else [],scene=scene) for t,score in zip(times,boxes)]
            regions, _ = stabilize(frames,100,100,self.options)
            self.assertEqual(recover_male_reappearances(Path('unused.mp4'),frames,regions,100,100,self.options),0)


class VideoTimingTests(unittest.TestCase):
    def test_variable_timing_and_no_audio(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            source = Path(directory) / "source.mp4"
            output = Path(directory) / "output.mp4"
            pts = [0, 3600, 18000, 21600]
            durations = {0: 3600, 3600: 14400, 18000: 3600, 21600: 7200}
            with av.open(str(source), "w") as container:
                stream = container.add_stream("libx264", rate=25)
                stream.width = stream.height = 64
                stream.pix_fmt = "yuv420p"
                stream.time_base = stream.codec_context.time_base = Fraction(1, 90000)
                stream.codec_context.max_b_frames = 0
                for i, timestamp in enumerate(pts):
                    image = np.full((64, 64, 3), i * 60, dtype=np.uint8)
                    f = av.VideoFrame.from_ndarray(image, format="bgr24")
                    f.pts, f.time_base = timestamp, Fraction(1, 90000)
                    for packet in stream.encode(f):
                        packet.duration = durations[packet.pts]
                        container.mux(packet)
                for packet in stream.encode():
                    packet.duration = durations[packet.pts]
                    container.mux(packet)
            with av.open(str(source)) as container:
                decoded = list(container.decode(video=0))
                metadata = [{"time": float(f.pts * f.time_base), "duration": float(f.duration * f.time_base)} for f in decoded]
            info = {"fps": "25", "width": 64, "height": 64, "source_video_start_seconds": 0.0}
            render_video(source, output, metadata, [[region([16, 16, 48, 48])]] * 4, info,
                         BatchOptions(encoder="libx264"), find_ffmpeg(), lambda: None, lambda v: None)
            with av.open(str(output)) as container:
                actual = list(container.decode(video=0))
                self.assertEqual(len(container.streams.audio), 0)
                self.assertEqual(len(actual), 4)
                for expected, f in zip(metadata, actual):
                    self.assertAlmostEqual(float(f.pts * f.time_base), expected["time"], places=4)
                self.assertAlmostEqual(float(actual[-1].duration * actual[-1].time_base), metadata[-1]["duration"], places=4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
