"""Tests for LED status node (Phase 2.5)."""

from __future__ import annotations

import pytest
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, ColorRGBA

from multi_arm_runtime_api.led_status_node import LedStatusNode, LED_COLORS


@pytest.fixture
def rclpy_init():
    """Initialize and shutdown rclpy."""
    rclpy.init()
    yield
    rclpy.shutdown()


@pytest.fixture
def led_node(rclpy_init):
    """Create LED status node."""
    node = LedStatusNode()
    yield node
    node.destroy_node()


class TestLedStatusNode:
    """Test LED status node functionality."""

    def test_node_starts(self, led_node) -> None:
        """Node starts with INITIALIZING state."""
        assert led_node._state == "INITIALIZING"

    def test_led_colors_defined(self) -> None:
        """All expected LED states have colors."""
        expected_states = {"READY", "RUNNING", "FAILED", "SAFETY_STOP", "INITIALIZING"}
        assert expected_states.issubset(set(LED_COLORS.keys()))

    def test_ready_color_is_green(self) -> None:
        """READY state is green."""
        r, g, b = LED_COLORS["READY"]
        assert g > r and g > b

    def test_failed_color_is_red(self) -> None:
        """FAILED state is red."""
        r, g, b = LED_COLORS["FAILED"]
        assert r > g and r > b

    def test_running_color_is_blue(self) -> None:
        """RUNNING state is blue."""
        r, g, b = LED_COLORS["RUNNING"]
        assert b > r and b > g

    def test_safety_stop_color_is_red(self) -> None:
        """SAFETY_STOP state is red."""
        r, g, b = LED_COLORS["SAFETY_STOP"]
        assert r > g and r > b

    def test_determine_state_initializing(self, led_node) -> None:
        """No services available -> INITIALIZING."""
        led_node._safety_available = False
        led_node._coordinator_available = False
        assert led_node._determine_state() == "INITIALIZING"

    def test_determine_state_failed_safety(self, led_node) -> None:
        """Safety unavailable, coordinator available -> FAILED."""
        led_node._safety_available = False
        led_node._coordinator_available = True
        assert led_node._determine_state() == "FAILED"

    def test_determine_state_failed_coord(self, led_node) -> None:
        """Safety available, coordinator unavailable -> FAILED."""
        led_node._safety_available = True
        led_node._coordinator_available = False
        assert led_node._determine_state() == "FAILED"

    def test_determine_state_ready(self, led_node) -> None:
        """All services available -> READY."""
        led_node._safety_available = True
        led_node._coordinator_available = True
        assert led_node._determine_state() == "READY"

    def test_publishes_status(self, led_node) -> None:
        """Node publishes status on /led/status."""
        received = []

        listener = Node("test_listener")
        listener.create_subscription(
            String, "/led/status", lambda msg: received.append(msg.data), 10
        )

        led_node._safety_available = True
        led_node._coordinator_available = True
        led_node._tick()

        rclpy.spin_once(listener, timeout_sec=0.5)
        listener.destroy_node()

        assert len(received) > 0
        assert received[0] in ["READY", "INITIALIZING", "FAILED", "SAFETY_STOP", "OFF"]

    def test_publishes_color(self, led_node) -> None:
        """Node publishes color on /led/color."""
        received = []

        listener = Node("test_listener_color")
        listener.create_subscription(
            ColorRGBA, "/led/color", lambda msg: received.append(msg), 10
        )

        led_node._safety_available = True
        led_node._coordinator_available = True
        led_node._tick()

        rclpy.spin_once(listener, timeout_sec=0.5)
        listener.destroy_node()

        assert len(received) > 0
        assert received[0].a == 1.0