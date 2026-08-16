"""Tests for GripperController."""

import pytest

from multi_arm_manipulation.gripper_controller import (
    GripperController,
    GripperState,
    GripperStatus,
)


@pytest.fixture
def controller() -> GripperController:
    """Create a test gripper controller."""
    ctrl = GripperController({"max_opening_mm": 85, "max_force_n": 100.0})
    ctrl.register_gripper("left_arm")
    return ctrl


class TestGripperController:
    """Tests for GripperController."""

    def test_register(self) -> None:
        ctrl = GripperController()
        ctrl.register_gripper("left_arm")
        status = ctrl.get_status("left_arm")
        assert status is not None
        assert status.state == GripperState.OPEN

    def test_open(self, controller: GripperController) -> None:
        success, msg = controller.open("left_arm")
        assert success is True
        assert controller.is_open("left_arm")

    def test_close(self, controller: GripperController) -> None:
        success, msg = controller.close("left_arm", force=20.0)
        assert success is True
        assert controller.is_closed("left_arm")

    def test_close_with_force_limit(self, controller: GripperController) -> None:
        success, msg = controller.close("left_arm", force=200.0)
        assert success is True
        status = controller.get_status("left_arm")
        assert status.force == 100.0

    def test_attach_requires_closed(self, controller: GripperController) -> None:
        success, msg = controller.attach("left_arm", "cube1")
        assert success is False
        assert "closed" in msg

    def test_attach_after_close(self, controller: GripperController) -> None:
        controller.close("left_arm")
        success, msg = controller.attach("left_arm", "cube1")
        assert success is True
        assert controller.has_object("left_arm")
        assert controller.get_attached_object("left_arm") == "cube1"

    def test_attach_already_attached(self, controller: GripperController) -> None:
        controller.close("left_arm")
        controller.attach("left_arm", "cube1")
        success, msg = controller.attach("left_arm", "cube2")
        assert success is False

    def test_detach(self, controller: GripperController) -> None:
        controller.close("left_arm")
        controller.attach("left_arm", "cube1")
        success, msg = controller.detach("left_arm")
        assert success is True
        assert not controller.has_object("left_arm")

    def test_detach_nothing(self, controller: GripperController) -> None:
        success, msg = controller.detach("left_arm")
        assert success is False

    def test_open_blocks_with_attachment(self, controller: GripperController) -> None:
        controller.close("left_arm")
        controller.attach("left_arm", "cube1")
        success, msg = controller.open("left_arm")
        assert success is False
        assert "attached" in msg

    def test_unregistered_gripper(self) -> None:
        ctrl = GripperController()
        success, msg = ctrl.open("nonexistent")
        assert success is False

    def test_full_grasp_cycle(self, controller: GripperController) -> None:
        success, _ = controller.close("left_arm", force=30.0)
        assert success

        success, _ = controller.attach("left_arm", "red_cube")
        assert success
        assert controller.get_attached_object("left_arm") == "red_cube"

        success, _ = controller.detach("left_arm")
        assert success

        success, _ = controller.open("left_arm")
        assert success
        assert controller.is_open("left_arm")