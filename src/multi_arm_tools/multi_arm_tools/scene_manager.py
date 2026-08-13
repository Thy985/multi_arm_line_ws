"""Scene Manager — list and show scene assets for M7.2."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

try:
    from ament_index_python.packages import get_package_share_directory
    _SIM_SHARE = get_package_share_directory("multi_arm_simulation")
except Exception:
    _SIM_SHARE = ""


@dataclass
class SceneInfo:
    """Scene summary info."""
    name: str
    description: str
    num_static: int
    num_dynamic: int
    num_zones: int
    has_body: bool = False
    has_sensors: bool = False
    has_perception: bool = False
    sensor_types: list = None

    def __post_init__(self) -> None:
        if self.sensor_types is None:
            self.sensor_types = []


class SceneManager:
    """Manage scene assets (environments/objects/tasks)."""

    def __init__(self, scenes_dir: Optional[str] = None) -> None:
        if scenes_dir is not None:
            self._scenes_dir = Path(scenes_dir)
        elif _SIM_SHARE:
            self._scenes_dir = Path(_SIM_SHARE) / "scenes"
        else:
            self._scenes_dir = Path(".")

    @property
    def environments_dir(self) -> Path:
        return self._scenes_dir / "environments"

    @property
    def objects_dir(self) -> Path:
        return self._scenes_dir / "objects"

    @property
    def tasks_dir(self) -> Path:
        return self._scenes_dir / "tasks"

    def list_environments(self) -> list[SceneInfo]:
        """List all available environments."""
        result: list[SceneInfo] = []
        if not self.environments_dir.exists():
            return result
        for path in sorted(self.environments_dir.glob("*.yaml")):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                sensors = data.get("sensors", {})
                sensor_types = []
                for sname, sdata in sensors.items():
                    if isinstance(sdata, dict):
                        stype = sdata.get("type", "unknown")
                        if stype not in sensor_types:
                            sensor_types.append(stype)
                result.append(SceneInfo(
                    name=data.get("name", path.stem),
                    description=data.get("description", ""),
                    num_static=len(data.get("static_models", [])),
                    num_dynamic=len(data.get("dynamic_models", [])),
                    num_zones=len(data.get("zones", {})),
                    has_body=bool(data.get("body")),
                    has_sensors=bool(sensors),
                    has_perception=bool(data.get("perception")),
                    sensor_types=sensor_types,
                ))
            except Exception:
                pass
        return result

    def list_objects(self) -> list[dict]:
        """List all available object definitions."""
        result: list[dict] = []
        if not self.objects_dir.exists():
            return result
        for path in sorted(self.objects_dir.glob("*.yaml")):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                result.append(data)
            except Exception:
                pass
        return result

    def list_tasks(self) -> list[dict]:
        """List all available task definitions."""
        result: list[dict] = []
        if not self.tasks_dir.exists():
            return result
        for path in sorted(self.tasks_dir.glob("*.yaml")):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                result.append(data)
            except Exception:
                pass
        return result

    def get_environment(self, name: str) -> Optional[dict]:
        """Get environment details by name."""
        path = self.environments_dir / f"{name}.yaml"
        if not path.exists():
            return None
        with open(path) as f:
            return yaml.safe_load(f)

    def get_object(self, name: str) -> Optional[dict]:
        """Get object definition by name."""
        path = self.objects_dir / f"{name}.yaml"
        if not path.exists():
            return None
        with open(path) as f:
            return yaml.safe_load(f)

    def get_task(self, name: str) -> Optional[dict]:
        """Get task definition by name."""
        path = self.tasks_dir / f"{name}.yaml"
        if not path.exists():
            return None
        with open(path) as f:
            return yaml.safe_load(f)

    def print_list(self) -> None:
        """Print all available scenes."""
        envs = self.list_environments()
        print("\n=== Available Scenes ===")
        print()
        if not envs:
            print("  No scenes found.")
            return
        for env in envs:
            print(f"  {env.name}")
            print(f"    {env.description}")
            print(f"    Static: {env.num_static}  Dynamic: {env.num_dynamic}  Zones: {env.num_zones}")
            m7_tags = []
            if env.has_body:
                m7_tags.append("body")
            if env.has_sensors:
                m7_tags.append(f"sensors({','.join(env.sensor_types)})")
            if env.has_perception:
                m7_tags.append("perception")
            if m7_tags:
                print(f"    M7: {' + '.join(m7_tags)}")
            print()

        objs = self.list_objects()
        print(f"=== Object Types ({len(objs)}) ===")
        for obj in objs:
            graspable = "graspable" if obj.get("graspable") else "not graspable"
            print(f"  {obj.get('name', '?'):12s}  {obj.get('type', '?'):10s}  {graspable}")
        print()

        tasks = self.list_tasks()
        print(f"=== Task Types ({len(tasks)}) ===")
        for task in tasks:
            print(f"  {task.get('name', '?'):12s}  {task.get('description', '')}")
        print()

    def print_scene(self, name: str) -> None:
        """Print scene details."""
        env = self.get_environment(name)
        if env is None:
            print(f"Scene '{name}' not found.")
            return

        print(f"\n=== Scene: {env.get('name', name)} ===")
        print(f"  Description: {env.get('description', '')}")
        print(f"  Version: {env.get('version', '?')}")
        print()

        print("Static Models:")
        for model in env.get("static_models", []):
            pos = model.get("position", [0, 0, 0])
            print(f"  {model.get('name', '?'):20s}  pos=[{pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f}]")
        print()

        print("Dynamic Models:")
        for model in env.get("dynamic_models", []):
            obj = model.get("object", "?")
            variant = model.get("variant", "")
            pos = model.get("position", [0, 0, 0])
            print(f"  {obj}/{variant:8s}  pos=[{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}]")
        print()

        print("Zones:")
        for zname, zdata in env.get("zones", {}).items():
            print(f"  {zname:10s}  {zdata.get('description', '')}")
        print()

        body = env.get("body", {})
        if body:
            print("Body (M7.1):")
            torso = body.get("torso", {})
            head = body.get("head", {})
            if torso:
                print(f"  Torso: init={torso.get('initial_position', 0.0)}  max_vel={torso.get('max_velocity', '?')}")
            if head:
                print(f"  Head:  init={head.get('initial_position', 0.0)}  max_vel={head.get('max_velocity', '?')}  look_at={head.get('look_at', '?')}")
            print()

        sensors = env.get("sensors", {})
        if sensors:
            print(f"Sensors ({len(sensors)}):")
            for sname, sdata in sensors.items():
                if isinstance(sdata, dict):
                    stype = sdata.get("type", "?")
                    active = "ACTIVE" if sdata.get("active", True) else "INACTIVE"
                    detail = f"type={stype}  {active}"
                    if stype == "rgbd":
                        detail += f"  rgb={sdata.get('rgb', True)}  depth={sdata.get('depth', True)}"
                    elif stype == "camera":
                        detail += f"  rgb={sdata.get('rgb', True)}"
                    elif stype == "imu":
                        detail += f"  frame={sdata.get('frame', '?')}"
                    res = sdata.get("resolution")
                    if res:
                        detail += f"  res={res[0]}x{res[1]}"
                    fps = sdata.get("fps")
                    if fps:
                        detail += f"  fps={fps}"
                    print(f"  {sname:20s}  {detail}")
            print()

        perception = env.get("perception", {})
        if perception:
            print("Perception (M7.4/M7.5):")
            for pname, pdata in perception.items():
                if isinstance(pdata, dict):
                    active = "ACTIVE" if pdata.get("active", True) else "INACTIVE"
                    print(f"  {pname:20s}  {active}")
                    for pk, pv in pdata.items():
                        if pk != "active":
                            print(f"    {pk}: {pv}")
            print()

        bounds = env.get("workspace_bounds", {})
        print(f"Workspace: x={bounds.get('x', '?')}  y={bounds.get('y', '?')}  z={bounds.get('z', '?')}")