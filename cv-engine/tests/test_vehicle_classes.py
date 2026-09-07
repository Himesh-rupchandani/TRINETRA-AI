"""Stable vehicle class mapping for COCO + the fine-tuned 5-class model."""
from detection.classes import (
    TRAINED_VEHICLE_CLASSES,
    VEHICLE_CLASS_IDS,
    is_coco_layout,
    normalize_vehicle_class,
)


def test_coco_ids_unchanged():
    assert VEHICLE_CLASS_IDS[2] == "car"
    assert VEHICLE_CLASS_IDS[3] == "motorcycle"
    assert VEHICLE_CLASS_IDS[5] == "bus"
    assert VEHICLE_CLASS_IDS[7] == "truck"


def test_trained_classes_include_autorickshaw():
    assert TRAINED_VEHICLE_CLASSES == ["car", "motorcycle", "bus", "truck", "autorickshaw"]


def test_aliases():
    assert normalize_vehicle_class("motorbike") == "motorcycle"
    assert normalize_vehicle_class("auto") == "autorickshaw"
    assert normalize_vehicle_class("auto-rickshaw") == "autorickshaw"
    assert normalize_vehicle_class("lorry") == "truck"
    assert normalize_vehicle_class("SUV") == "car"
    assert normalize_vehicle_class("person") is None
    assert normalize_vehicle_class("") is None


def test_coco_layout_detection():
    coco = {0: "person", 2: "car", 3: "motorcycle"}
    custom = {0: "car", 1: "motorcycle", 2: "bus", 3: "truck", 4: "autorickshaw"}
    assert is_coco_layout(coco) is True
    assert is_coco_layout(custom) is False
