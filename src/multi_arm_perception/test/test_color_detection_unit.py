"""Unit test for ColorDetectorNode detection logic."""

from __future__ import annotations

import sys
import os
import numpy as np
import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_color_detection_direct():
    """Test OpenCV color detection directly on synthetic image."""
    img = np.zeros((720, 1280, 3), dtype=np.uint8)
    img[:] = (200, 200, 200)

    cv2.rectangle(img, (600, 400), (680, 480), (0, 0, 255), -1)
    cv2.rectangle(img, (1000, 440), (1080, 520), (255, 0, 0), -1)

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    red_mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    red_mask |= cv2.inRange(hsv, np.array([0, 80, 80]), np.array([10, 255, 255]))
    red_mask |= cv2.inRange(hsv, np.array([170, 80, 80]), np.array([180, 255, 255]))

    red_contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    print(f"\n  Red contours: {len(red_contours)}")
    if red_contours:
        area = cv2.contourArea(max(red_contours, key=cv2.contourArea))
        print(f"  Red max area: {area}")
        m = cv2.moments(max(red_contours, key=cv2.contourArea))
        if m["m00"] > 0:
            cx = m["m10"] / m["m00"]
            cy = m["m01"] / m["m00"]
            print(f"  Red centroid: ({cx:.1f}, {cy:.1f})")

    blue_mask = cv2.inRange(hsv, np.array([100, 80, 80]), np.array([130, 255, 255]))
    blue_contours, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    print(f"  Blue contours: {len(blue_contours)}")
    if blue_contours:
        area = cv2.contourArea(max(blue_contours, key=cv2.contourArea))
        print(f"  Blue max area: {area}")

    assert len(red_contours) > 0, "No red contour detected"
    assert len(blue_contours) > 0, "No blue contour detected"
    print("  ✓ Direct color detection works")


def test_synthetic_camera_projection():
    """Test SyntheticCamera projection logic."""
    camera_x, camera_y, camera_z = 0.0, 0.0, 0.5
    fx = fy = (1280 / 2.0) / np.tan(1.5708 / 2.0)
    cx, cy = 640.0, 360.0

    objects = [
        ("red_cube", 0.5, 0.0, 0.435),
        ("blue_cylinder", 0.3, 0.2, 0.44),
    ]

    for name, x, y, z in objects:
        dx = x - camera_x
        dy = y - camera_y
        dz = z - camera_z

        if dx <= 0.1:
            print(f"\n  {name}: BEHIND CAMERA (dx={dx})")
            continue

        u = fx * dy / dx + cx
        v = -fy * dz / dx + cy

        in_bounds = 0 <= u < 1280 and 0 <= v < 720
        print(f"\n  {name} at ({x},{y},{z}):")
        print(f"    dx={dx}, dy={dy}, dz={dz}")
        print(f"    pixel=({u:.1f}, {v:.1f}), in_bounds={in_bounds}")

        assert in_bounds, f"{name} projected outside image bounds"

    print("\n  ✓ All objects project within image bounds")


def test_full_pipeline_synthetic():
    """Test full pipeline: create image → detect → estimate pose."""
    camera_x, camera_y, camera_z = 0.0, 0.0, 0.5
    ground_z = 0.44
    fx = fy = (1280 / 2.0) / np.tan(1.5708 / 2.0)
    cx, cy = 640.0, 360.0

    img = np.zeros((720, 1280, 3), dtype=np.uint8)
    img[:] = (200, 200, 200)

    objects = [
        ("red_cube", 0.5, 0.0, 0.435, (0, 0, 255)),
        ("blue_cylinder", 0.3, 0.2, 0.44, (255, 0, 0)),
    ]

    for name, x, y, z, color in objects:
        dx = x - camera_x
        dy = y - camera_y
        dz = z - camera_z
        u = int(fx * dy / dx + cx)
        v = int(-fy * dz / dx + cy)
        cv2.rectangle(img, (u - 30, v - 30), (u + 30, v + 30), color, -1)
        print(f"\n  {name}: drew at ({u},{v}), actual pos=({x},{y},{z})")

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    for name, x, y, z, color in objects:
        if "red" in name:
            mask = cv2.inRange(hsv, np.array([0, 80, 80]), np.array([10, 255, 255]))
            mask |= cv2.inRange(hsv, np.array([170, 80, 80]), np.array([180, 255, 255]))
        else:
            mask = cv2.inRange(hsv, np.array([100, 80, 80]), np.array([130, 255, 255]))

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        assert len(contours) > 0, f"No contour for {name}"

        largest = max(contours, key=cv2.contourArea)
        m = cv2.moments(largest)
        u = m["m10"] / m["m00"]
        v = m["m01"] / m["m00"]

        ray_y = (u - cx) / fx
        ray_z = -(v - cy) / fy
        t = (camera_z - ground_z) / abs(ray_z)
        est_x = camera_x + t
        est_y = camera_y + t * ray_y
        est_z = ground_z

        error = ((est_x - x)**2 + (est_y - y)**2 + (est_z - z)**2) ** 0.5
        print(f"  {name}: detected at ({u:.1f},{v:.1f}), estimated pos=({est_x:.3f},{est_y:.3f},{est_z:.3f}), error={error:.3f}m")

        assert error < 0.10, f"Error too large for {name}: {error:.3f}m"

    print("\n  ✓ Full pipeline: image→detect→pose works correctly")