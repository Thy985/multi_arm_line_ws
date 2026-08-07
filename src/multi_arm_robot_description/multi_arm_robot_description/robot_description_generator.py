"""Robot Description Generator — YAML to URDF/SRDF/controllers code generation."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class GeneratedFile:
    """Represents a generated file."""

    path: Path
    content: str


class RobotDescriptionGenerator:
    """Generate ROS model files from robot.yaml.

    Generates:
        - URDF (xacro with parameterized arms)
        - controllers.yaml (ros2_control)
        - kinematics.yaml (MoveIt IK)
    """

    UR5E_JOINT_NAMES = [
        "shoulder_pan_joint",
        "shoulder_lift_joint",
        "elbow_joint",
        "wrist_1_joint",
        "wrist_2_joint",
        "wrist_3_joint",
    ]

    def __init__(self, robot_yaml_path: str | Path) -> None:
        """Initialize generator with robot.yaml path.

        Args:
            robot_yaml_path: Path to robot.yaml file.

        Raises:
            FileNotFoundError: If YAML file does not exist.

        """
        path = Path(robot_yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Robot YAML not found: {robot_yaml_path}")

        with open(path) as f:
            self._config: dict[str, Any] = yaml.safe_load(f)

    @property
    def robot_name(self) -> str:
        """Get robot name."""
        return self._config.get("robot", {}).get("name", "unknown")

    @property
    def arms(self) -> list[dict]:
        """Get list of arm configurations."""
        return self._config.get("components", {}).get("arms", [])

    def generate_urdf(self) -> GeneratedFile:
        """Generate URDF xacro from robot.yaml.

        Returns:
            GeneratedFile with URDF content.

        """
        arms = self.arms
        lines: list[str] = [
            '<?xml version="1.0"?>',
            '<robot xmlns:xacro="http://www.ros.org/wiki/xacro" '
            f'name="{self.robot_name}">',
            "",
            '  <xacro:include filename="$(find ur_description)/urdf/ur_macro.xacro"/>',
            "",
        ]

        for arm in arms:
            prefix = arm.get("prefix", f"{arm['name']}_")
            origin = arm.get("origin", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
            origin_str = " ".join(str(v) for v in origin)

            lines.extend([
                f"  <!-- {arm['name']} ({arm['type']}) -->",
                f'  <xacro:ur_robot prefix="{prefix}" ',
                f'           joint_limits_package="ur_description" ',
                f'           joint_limits_file="config/joint_limits.yaml" ',
                f'           kinematics_file="config/ur5e/default_kinematics.yaml" ',
                f'           visual_parameters_file="config/ur5e/visual_parameters.yaml" ',
                f'           transmission_hw_interface="hardware_interface/PositionJointInterface" ',
                f'           safety_limits="true" ',
                f'           safety_pos_margin="0.15" ',
                f'           safety_k_position="20" />',
                "",
                f'  <joint name="{prefix}base_joint" type="fixed">',
                f'    <parent link="world"/>',
                f'    <child link="{prefix}base_link"/>',
                f'    <origin xyz="{origin_str[:origin_str.rfind(" ") + 1]}" '
                f'rpy="{origin_str[origin_str.rfind(" ") + 1:]}"/>',
                f"  </joint>",
                "",
            ])

        lines.append("</robot>")
        return GeneratedFile(Path("generated_robot.urdf.xacro"), "\n".join(lines))

    def generate_controllers(self) -> GeneratedFile:
        """Generate controllers.yaml from robot.yaml.

        Returns:
            GeneratedFile with controllers YAML content.

        """
        arms = self.arms
        controllers: dict[str, Any] = {
            "controller_manager": {"ros__parameters": {"update_rate": 500}},
        }

        for arm in arms:
            prefix = arm.get("prefix", f"{arm['name']}_")
            jtc_name = arm["controller"]
            jsb_name = arm.get(
                "joint_state_broadcaster", f"{arm['name']}_joint_state_broadcaster"
            )

            joint_names = [
                f"{prefix}{jn}" for jn in self.UR5E_JOINT_NAMES
            ]

            controllers["controller_manager"]["ros__parameters"][jtc_name] = {
                "type": "joint_trajectory_controller/JointTrajectoryController"
            }
            controllers["controller_manager"]["ros__parameters"][jsb_name] = {
                "type": "joint_state_broadcaster/JointStateBroadcaster"
            }

            controllers[jtc_name] = {
                "ros__parameters": {
                    "joints": joint_names,
                    "command_interfaces": ["position"],
                    "state_interfaces": ["position", "velocity"],
                    "allow_integration_in_goal_states": True,
                }
            }

        content = yaml.dump(controllers, default_flow_style=False, sort_keys=False)
        return GeneratedFile(Path("generated_controllers.yaml"), content)

    def generate_kinematics(self) -> GeneratedFile:
        """Generate kinematics.yaml for MoveIt.

        Returns:
            GeneratedFile with kinematics YAML content.

        """
        arms = self.arms
        kinematics: dict[str, Any] = {}

        for arm in arms:
            prefix = arm.get("prefix", f"{arm['name']}_")
            kinematics[arm["name"]] = {
                "kinematics_solver": "kdl_kinematics_plugin/KDLKinematicsPlugin",
                "kinematics_solver_timeout": 0.005,
                "kinematics_solver_attempts": 3,
            }

        if len(arms) > 1:
            kinematics["dual_arm"] = {
                "kinematics_solver": "kdl_kinematics_plugin/KDLKinematicsPlugin",
                "kinematics_solver_timeout": 0.005,
                "kinematics_solver_attempts": 3,
            }

        content = yaml.dump(kinematics, default_flow_style=False, sort_keys=False)
        return GeneratedFile(Path("generated_kinematics.yaml"), content)

    def generate_all(self, output_dir: str | Path) -> list[GeneratedFile]:
        """Generate all ROS model files.

        Args:
            output_dir: Directory to write generated files.

        Returns:
            List of generated files.

        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        files = [
            self.generate_urdf(),
            self.generate_controllers(),
            self.generate_kinematics(),
        ]

        for f in files:
            full_path = out / f.path.name
            full_path.write_text(f.content)

        return files


def main(args: list[str] | None = None) -> None:
    """CLI entry point for robot description generator.

    Args:
        args: Command line arguments.

    """
    if args is None:
        args = sys.argv[1:]

    if len(args) < 1:
        print("Usage: generate_robot_description <robot.yaml> [output_dir]")
        sys.exit(1)

    yaml_path = args[0]
    output_dir = args[1] if len(args) > 1 else "generated"

    generator = RobotDescriptionGenerator(yaml_path)
    files = generator.generate_all(output_dir)

    print(f"Generated {len(files)} files in {output_dir}:")
    for f in files:
        print(f"  {f.path.name}")


if __name__ == "__main__":
    main()