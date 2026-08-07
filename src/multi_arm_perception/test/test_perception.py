"""Tests for PerceptionNode and ObjectDetector."""

import pytest

from multi_arm_perception.perception_node import ObjectDetector, DetectedObject


class TestObjectDetector:
    """Tests for ObjectDetector."""

    def test_register_and_detect(self) -> None:
        detector = ObjectDetector()
        detector.register_object("cube1", "cube", [0.5, 0.0, 0.1])
        detections = detector.detect()
        assert len(detections) == 1
        assert detections[0].object_id == "cube1"

    def test_detect_with_noise(self) -> None:
        detector = ObjectDetector({"position_noise": 0.01, "seed": 42})
        detector.register_object("cube1", "cube", [0.5, 0.0, 0.1])
        d1 = detector.detect()[0]
        d2 = detector.detect()[0]
        assert d1.position != d2.position

    def test_detect_no_noise(self) -> None:
        detector = ObjectDetector({"position_noise": 0.0})
        detector.register_object("cube1", "cube", [0.5, 0.0, 0.1])
        d1 = detector.detect()[0]
        d2 = detector.detect()[0]
        assert d1.position == d2.position

    def test_detect_multiple(self) -> None:
        detector = ObjectDetector()
        detector.register_object("cube1", "cube", [0.5, 0.0, 0.1])
        detector.register_object("cyl1", "cylinder", [-0.3, 0.2, 0.1])
        detections = detector.detect()
        assert len(detections) == 2

    def test_confidence(self) -> None:
        detector = ObjectDetector({"confidence": 0.8})
        detector.register_object("cube1", "cube", [0, 0, 0])
        detection = detector.detect()[0]
        assert detection.confidence == 0.8

    def test_empty_detector(self) -> None:
        detector = ObjectDetector()
        detections = detector.detect()
        assert detections == []


class TestDetectedObject:
    """Tests for DetectedObject."""

    def test_creation(self) -> None:
        obj = DetectedObject(object_id="test", object_type="cube")
        assert obj.object_id == "test"
        assert obj.position == [0.0, 0.0, 0.0]
        assert obj.confidence == 1.0