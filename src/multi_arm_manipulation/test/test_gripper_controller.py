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
    ctrl.register_gripper("arm1")
    return ctrl


class TestGripperController:
    """Tests for GripperController."""

    def test_register(self) -> None:
        ctrl = GripperController()
        ctrl.register_gripper("arm1")
        status = ctrl.get_status("arm1")
        assert status is not None
        assert status.state == GripperState.OPEN

    def test_open(self, controller: GripperController) -> None:
        success, msg = controller.open("arm1")
        assert success is True
        assert controller.is_open("arm1")

    def test_close(self, controller: GripperController) -> None:
        success, msg = controller.close("arm1", force=20.0)
        assert success is True
        assert controller.is_closed("arm1")

    def test_close_with_force_limit(self, controller: GripperController) -> None:
        success, msg = controller.close("arm1", force=200.0)
        assert success is True
        status = controller.get_status("arm1")
        assert status.force == 100.0

    def test_attach_requires_closed(self, controller: GripperController) -> None:
        success, msg = controller.attach("arm1", "cube1")
        assert success is False
        assert "closed" in msg

    def test_attach_after_close(self, controller: GripperController) -> None:
        controller.close("arm1")
        success, msg = controller.attach("arm1", "cube1")
        assert success is True
        assert controller.has_object("arm1")
        assert controller.get_attached_object("arm1") == "cube1"

    def test_attach_already_attached(self, controller: GripperController) -> None:
        controller.close("arm1")
        controller.attach("arm1", "cube1")
        success, msg = controller.attach("arm1", "cube2")
        assert success is False

    def test_detach(self, controller: GripperController) -> None:
        controller.close("arm1")
        controller.attach("arm1", "cube1")
        success, msg = controller.detach("arm1")
        assert success is True
        assert not controller.has_object("arm1")

    def test_detach_nothing(self, controller: GripperController) -> None:
        success, msg = controller.detach("arm1")
        assert success is False

    def test_open_blocks_with_attachment(self, controller: GripperController) -> None:
        controller.close("arm1")
        controller.attach("arm1", "cube1")
        success, msg = controller.open("arm1")
        assert success is False
        assert "attached" in msg

    def test_unregistered_gripper(self) -> None:
        ctrl = GripperController()
        success, msg = ctrl.open("nonexistent")
        assert success is False

    def test_full_grasp_cycle(self, controller: GripperController) -> None:
        success, _ = controller.close("arm1", force=30.0)
        assert success

        success, _ = controller.attach("arm1", "red_cube")
        assert success
        assert controller.get_attached_object("arm1") == "red_cube"

        success, _ = controller.detach("arm1")
        assert success

        success, _ = controller.open("arm1")
        assert success
        assert controller.is_open("arm1")