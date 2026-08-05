"""ResourceManager for unified management of Robot/Zone/Tool/Sensor/Fixture resources."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional
import yaml


class ResourceType(Enum):
    """Resource type classification."""
    ROBOT = auto()
    ZONE = auto()
    TOOL = auto()
    SENSOR = auto()
    FIXTURE = auto()


class ResourceState(Enum):
    """Resource lifecycle state."""
    FREE = auto()
    ALLOCATED = auto()
    RESERVED = auto()
    ERROR = auto()


@dataclass
class Resource:
    """Represents a managed resource in the system."""
    name: str
    resource_type: ResourceType
    state: ResourceState = ResourceState.FREE
    allocated_to: Optional[str] = None
    capabilities: Dict[str, Any] = field(default_factory=dict)
    waiting_queue: List[str] = field(default_factory=list)

    def is_available(self) -> bool:
        """Check if resource is available for allocation."""
        return self.state == ResourceState.FREE

    def allocate(self, task_id: str) -> bool:
        """Allocate resource to a task."""
        if self.state == ResourceState.FREE:
            self.state = ResourceState.ALLOCATED
            self.allocated_to = task_id
            return True
        if task_id not in self.waiting_queue:
            self.waiting_queue.append(task_id)
        return False

    def release(self, task_id: str) -> Optional[str]:
        """Release resource and grant to next in queue."""
        if self.allocated_to == task_id:
            self.state = ResourceState.FREE
            self.allocated_to = None
            if task_id in self.waiting_queue:
                self.waiting_queue.remove(task_id)
            if self.waiting_queue:
                next_task = self.waiting_queue.pop(0)
                self.state = ResourceState.ALLOCATED
                self.allocated_to = next_task
                return next_task
        return None

    def reserve(self, task_id: str) -> bool:
        """Reserve resource for future use."""
        if self.state == ResourceState.FREE:
            self.state = ResourceState.RESERVED
            self.allocated_to = task_id
            return True
        return False

    def cancel_reservation(self, task_id: str) -> bool:
        """Cancel a reservation or remove from queue."""
        if self.allocated_to == task_id and self.state == ResourceState.RESERVED:
            self.state = ResourceState.FREE
            self.allocated_to = None
            return True
        if task_id in self.waiting_queue:
            self.waiting_queue.remove(task_id)
            return True
        return False


class ResourceManager:
    """Unified manager for all resource types in the multi-arm system.

    Manages Robot, Zone, Tool, Sensor, and Fixture resources.
    Zone is a special case with mutual exclusion semantics.
    Configuration is driven by YAML files.
    """

    def __init__(self) -> None:
        self._resources: Dict[str, Resource] = {}

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "ResourceManager":
        """Create ResourceManager from a YAML configuration file.

        Args:
            yaml_path: Path to the robots.yaml configuration file.

        Returns:
            Configured ResourceManager instance.
        """
        manager = cls()
        with open(yaml_path, "r") as f:
            config = yaml.safe_load(f)

        for robot_cfg in config.get("robots", []):
            name = robot_cfg["name"]
            capabilities = robot_cfg.get("capabilities", {})
            capabilities["namespace"] = robot_cfg.get("namespace", f"/{name}")
            capabilities["controllers"] = robot_cfg.get("controllers", {})
            capabilities["safety"] = robot_cfg.get("safety", {})
            manager.register(
                Resource(
                    name=name,
                    resource_type=ResourceType.ROBOT,
                    capabilities=capabilities,
                )
            )

        resources_cfg = config.get("resources", {})
        for zone_name in resources_cfg.get("zones", []):
            manager.register(
                Resource(
                    name=zone_name,
                    resource_type=ResourceType.ZONE,
                    capabilities={"zone_type": "shared"},
                )
            )
        for tool_name in resources_cfg.get("tools", []):
            if isinstance(tool_name, str):
                manager.register(
                    Resource(
                        name=tool_name,
                        resource_type=ResourceType.TOOL,
                    )
                )
            else:
                manager.register(
                    Resource(
                        name=tool_name["name"],
                        resource_type=ResourceType.TOOL,
                        capabilities=tool_name.get("capabilities", {}),
                    )
                )
        for sensor_name in resources_cfg.get("sensors", []):
            if isinstance(sensor_name, str):
                manager.register(
                    Resource(
                        name=sensor_name,
                        resource_type=ResourceType.SENSOR,
                    )
                )
            else:
                manager.register(
                    Resource(
                        name=sensor_name["name"],
                        resource_type=ResourceType.SENSOR,
                        capabilities=sensor_name.get("capabilities", {}),
                    )
                )
        for fixture_name in resources_cfg.get("fixtures", []):
            if isinstance(fixture_name, str):
                manager.register(
                    Resource(
                        name=fixture_name,
                        resource_type=ResourceType.FIXTURE,
                    )
                )
            else:
                manager.register(
                    Resource(
                        name=fixture_name["name"],
                        resource_type=ResourceType.FIXTURE,
                        capabilities=fixture_name.get("capabilities", {}),
                    )
                )

        return manager

    def register(self, resource: Resource) -> None:
        """Register a new resource."""
        self._resources[resource.name] = resource

    def get(self, name: str) -> Optional[Resource]:
        """Get resource by name."""
        return self._resources.get(name)

    def get_by_type(self, resource_type: ResourceType) -> List[Resource]:
        """Get all resources of a given type."""
        return [r for r in self._resources.values() if r.resource_type == resource_type]

    def get_robots(self) -> List[Resource]:
        """Get all robot resources."""
        return self.get_by_type(ResourceType.ROBOT)

    def get_zones(self) -> List[Resource]:
        """Get all zone resources."""
        return self.get_by_type(ResourceType.ZONE)

    def allocate(self, resource_name: str, task_id: str) -> bool:
        """Allocate a resource to a task.

        Args:
            resource_name: Name of the resource.
            task_id: ID of the task requesting allocation.

        Returns:
            True if allocation was granted immediately.
        """
        resource = self._resources.get(resource_name)
        if resource is None:
            return False
        return resource.allocate(task_id)

    def release(self, resource_name: str, task_id: str) -> Optional[str]:
        """Release a resource from a task.

        Args:
            resource_name: Name of the resource.
            task_id: ID of the task releasing the resource.

        Returns:
            Next task_id granted the resource, or None.
        """
        resource = self._resources.get(resource_name)
        if resource is None:
            return None
        return resource.release(task_id)

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all resources.

        Returns:
            Dict mapping resource name to its status info.
        """
        result = {}
        for name, r in self._resources.items():
            result[name] = {
                "type": r.resource_type.name,
                "state": r.state.name,
                "allocated_to": r.allocated_to,
                "capabilities": r.capabilities,
            }
        return result

    @property
    def resource_names(self) -> List[str]:
        """Get all resource names."""
        return list(self._resources.keys())

    def __len__(self) -> int:
        return len(self._resources)