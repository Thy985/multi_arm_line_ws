"""Lightweight Behavior Tree framework compatible with BehaviorTree.CPP XML format.

This provides a Python implementation of behavior trees that can load
XML definitions compatible with BehaviorTree.CPP's Groot editor.
In Phase 3+, this will be replaced with BehaviorTree.CPP + C++ plugins
for production use.
"""

from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional
import xml.etree.ElementTree as ET


class NodeStatus(Enum):
    """Behavior tree node execution status."""
    SUCCESS = auto()
    FAILURE = auto()
    RUNNING = auto()


class Blackboard:
    """Shared data store for behavior tree nodes."""

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def has(self, key: str) -> bool:
        return key in self._data

    def remove(self, key: str) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()


class BTNode:
    """Base class for behavior tree nodes."""

    def __init__(self, name: str = "", blackboard: Optional[Blackboard] = None) -> None:
        self.name = name
        self._blackboard = blackboard or Blackboard()
        self._children: List["BTNode"] = []
        self._status = NodeStatus.FAILURE

    @property
    def status(self) -> NodeStatus:
        return self._status

    @property
    def blackboard(self) -> Blackboard:
        return self._blackboard

    @blackboard.setter
    def blackboard(self, bb: Blackboard) -> None:
        self._blackboard = bb
        for child in self._children:
            child.blackboard = bb

    def add_child(self, child: "BTNode") -> None:
        child.blackboard = self._blackboard
        self._children.append(child)

    def tick(self) -> NodeStatus:
        """Execute one tick of this node. Must be overridden."""
        raise NotImplementedError

    def reset(self) -> None:
        """Reset node state."""
        self._status = NodeStatus.FAILURE
        for child in self._children:
            child.reset()

    def halt(self) -> None:
        """Halt execution."""
        for child in self._children:
            child.halt()


class Sequence(BTNode):
    """Execute children in order. Succeeds if all succeed. Fails on first failure.

    Remembers the last RUNNING child and resumes from it on next tick.
    """

    def __init__(self, name: str = "", blackboard: Optional[Blackboard] = None) -> None:
        super().__init__(name=name, blackboard=blackboard)
        self._running_child_idx: int = 0

    def tick(self) -> NodeStatus:
        self._status = NodeStatus.RUNNING
        while self._running_child_idx < len(self._children):
            child = self._children[self._running_child_idx]
            child_status = child.tick()
            if child_status == NodeStatus.RUNNING:
                return NodeStatus.RUNNING
            if child_status == NodeStatus.FAILURE:
                self._status = NodeStatus.FAILURE
                self._running_child_idx = 0
                return NodeStatus.FAILURE
            self._running_child_idx += 1
        self._status = NodeStatus.SUCCESS
        self._running_child_idx = 0
        return NodeStatus.SUCCESS

    def reset(self) -> None:
        self._running_child_idx = 0
        super().reset()


class Selector(BTNode):
    """Execute children in order. Succeeds on first success. Fails if all fail.

    Remembers the last RUNNING child and resumes from it on next tick.
    """

    def __init__(self, name: str = "", blackboard: Optional[Blackboard] = None) -> None:
        super().__init__(name=name, blackboard=blackboard)
        self._running_child_idx: int = 0

    def tick(self) -> NodeStatus:
        self._status = NodeStatus.RUNNING
        while self._running_child_idx < len(self._children):
            child = self._children[self._running_child_idx]
            child_status = child.tick()
            if child_status == NodeStatus.RUNNING:
                return NodeStatus.RUNNING
            if child_status == NodeStatus.SUCCESS:
                self._status = NodeStatus.SUCCESS
                self._running_child_idx = 0
                return NodeStatus.SUCCESS
            self._running_child_idx += 1
        self._status = NodeStatus.FAILURE
        self._running_child_idx = 0
        return NodeStatus.FAILURE

    def reset(self) -> None:
        self._running_child_idx = 0
        super().reset()


class ActionNode(BTNode):
    """Leaf node that executes a callable action."""

    def __init__(
        self,
        name: str = "",
        action_fn: Optional[Callable[[], NodeStatus]] = None,
        blackboard: Optional[Blackboard] = None,
    ) -> None:
        super().__init__(name=name, blackboard=blackboard)
        self._action_fn = action_fn or (lambda: NodeStatus.FAILURE)

    def tick(self) -> NodeStatus:
        self._status = self._action_fn()
        return self._status


class AsyncActionNode(ActionNode):
    """Base class for async BT nodes that use shared ROS2 Node.

    Implements the AsyncTick pattern:
    - First tick: send ROS2 request, return RUNNING
    - Subsequent ticks: check if future completed, return SUCCESS/FAILURE
    - Never blocks the executor — no _time.sleep() polling

    Subclasses must implement:
    - _send_request(): Send the ROS2 service/action request
    - _check_result(): Check if the request completed and return status

    The shared ROS2 Node is injected via set_ros2_node() before
    the tree is ticked, typically by the TaskPlannerNode.
    """

    def __init__(
        self,
        name: str = "",
        blackboard: Optional[Blackboard] = None,
    ) -> None:
        super().__init__(name=name, blackboard=blackboard)
        self._ros2_node: Optional[Any] = None
        self._pending_future: Optional[Any] = None
        self._request_sent: bool = False
        self._result_checked: bool = False

    def set_ros2_node(self, node: Any) -> None:
        """Inject the shared ROS2 node for creating clients.

        Args:
            node: The rclpy Node instance to share.
        """
        self._ros2_node = node

    def _make_completed_future(self, result: Any = None) -> Any:
        """Create an already-completed future for synchronous actions.

        Used by simplified plugins (Grasp, Place, Lift, Recover) that
        don't need actual ROS2 calls but still need to follow the
        AsyncTick pattern.

        Args:
            result: The result value to set on the future.

        Returns:
            A completed Future object.
        """
        from concurrent.futures import Future
        f = Future()
        f.set_result(result)
        return f

    def tick(self) -> NodeStatus:
        """Execute async tick: send request on first call, check result on subsequent.

        Returns:
            RUNNING if request is pending, SUCCESS/FAILURE when complete.
        """
        if not self._request_sent:
            self._pending_future = self._send_request()
            self._request_sent = True
            if self._pending_future is None:
                self._status = NodeStatus.FAILURE
                return NodeStatus.FAILURE
            return NodeStatus.RUNNING

        if self._pending_future is not None and self._pending_future.done():
            self._status = self._check_result(self._pending_future)
            return self._status

        return NodeStatus.RUNNING

    def _send_request(self) -> Optional[Any]:
        """Send the ROS2 request. Override in subclass.

        Returns:
            The future object to track, or None on error.
        """
        return None

    def _check_result(self, future: Any) -> NodeStatus:
        """Check the completed future and return final status. Override in subclass.

        Args:
            future: The completed future from _send_request.

        Returns:
            SUCCESS or FAILURE.
        """
        return NodeStatus.FAILURE

    def reset(self) -> None:
        """Reset async state for re-execution."""
        self._request_sent = False
        self._result_checked = False
        self._pending_future = None
        super().reset()


class ConditionNode(BTNode):
    """Leaf node that checks a condition."""

    def __init__(
        self,
        name: str = "",
        condition_fn: Optional[Callable[[], bool]] = None,
        blackboard: Optional[Blackboard] = None,
    ) -> None:
        super().__init__(name=name, blackboard=blackboard)
        self._condition_fn = condition_fn or (lambda: False)

    def tick(self) -> NodeStatus:
        self._status = NodeStatus.SUCCESS if self._condition_fn() else NodeStatus.FAILURE
        return self._status


class DecoratorNode(BTNode):
    """Base decorator that modifies child status."""

    def __init__(self, name: str = "", blackboard: Optional[Blackboard] = None) -> None:
        super().__init__(name=name, blackboard=blackboard)

    def tick(self) -> NodeStatus:
        if not self._children:
            return NodeStatus.FAILURE
        return self._decorate(self._children[0].tick())

    def _decorate(self, status: NodeStatus) -> NodeStatus:
        return status


class Inverter(DecoratorNode):
    """Inverts child status (SUCCESS↔FAILURE, RUNNING unchanged)."""

    def _decorate(self, status: NodeStatus) -> NodeStatus:
        if status == NodeStatus.SUCCESS:
            return NodeStatus.FAILURE
        if status == NodeStatus.FAILURE:
            return NodeStatus.SUCCESS
        return NodeStatus.RUNNING


class RetryNode(DecoratorNode):
    """Retries child on failure up to N times."""

    def __init__(self, name: str = "", max_retries: int = 3,
                 blackboard: Optional[Blackboard] = None) -> None:
        super().__init__(name=name, blackboard=blackboard)
        self._max_retries = max_retries
        self._attempt = 0

    def tick(self) -> NodeStatus:
        if not self._children:
            return NodeStatus.FAILURE
        while self._attempt < self._max_retries:
            status = self._children[0].tick()
            if status == NodeStatus.SUCCESS:
                self._attempt = 0
                self._status = NodeStatus.SUCCESS
                return NodeStatus.SUCCESS
            if status == NodeStatus.RUNNING:
                return NodeStatus.RUNNING
            self._attempt += 1
            self._children[0].reset()
        self._attempt = 0
        self._status = NodeStatus.FAILURE
        return NodeStatus.FAILURE

    def reset(self) -> None:
        self._attempt = 0
        super().reset()


class BehaviorTree:
    """Behavior tree that can be loaded from XML and executed.

    XML format is compatible with BehaviorTree.CPP / Groot for visualization.
    """

    NODE_MAP = {
        "Sequence": Sequence,
        "Selector": Selector,
        "Inverter": Inverter,
    }

    def __init__(self, root: Optional[BTNode] = None, blackboard: Optional[Blackboard] = None) -> None:
        self._root = root
        self._blackboard = blackboard or Blackboard()
        self._plugin_registry: Dict[str, type] = {}
        self._subtree_defs: Dict[str, ET.Element] = {}

    def register_plugin(self, name: str, node_class: type) -> None:
        """Register a BT plugin node type."""
        self._plugin_registry[name] = node_class

    def register_plugins(self, plugins: Dict[str, type]) -> None:
        """Register multiple BT plugin node types."""
        self._plugin_registry.update(plugins)

    @property
    def blackboard(self) -> Blackboard:
        return self._blackboard

    @property
    def root(self) -> Optional[BTNode]:
        return self._root

    def tick(self) -> NodeStatus:
        """Execute one tick of the tree."""
        if self._root is None:
            return NodeStatus.FAILURE
        return self._root.tick()

    def reset(self) -> None:
        """Reset the entire tree."""
        if self._root:
            self._root.reset()

    def load_xml(self, xml_path: str) -> None:
        """Load behavior tree from XML file (BehaviorTree.CPP compatible format).

        Args:
            xml_path: Path to the XML file.
        """
        tree = ET.parse(xml_path)
        root_element = tree.getroot()

        bt_elements = root_element.findall("BehaviorTree")
        if not bt_elements:
            if root_element.tag == "BehaviorTree":
                bt_elements = [root_element]

        for bt_elem in bt_elements:
            bt_id = bt_elem.get("ID", "")
            for child in bt_elem:
                if child.tag != "TreeNodesModel":
                    self._subtree_defs[bt_id] = child
                    break

        main_key = ""
        if self._subtree_defs:
            main_key = next(iter(self._subtree_defs))

        if main_key and main_key in self._subtree_defs:
            self._root = self._build_node(self._subtree_defs[main_key])
            if self._root:
                self._root.blackboard = self._blackboard

    def _build_node(self, element: ET.Element) -> BTNode:
        """Recursively build BT nodes from XML elements."""
        tag = element.tag
        name = element.get("name", tag)

        if tag == "SubTree":
            subtree_id = element.get("ID", "")
            subtree_element = self._subtree_defs.get(subtree_id)
            if subtree_element is not None:
                return self._build_node(subtree_element)
            return ActionNode(
                name=f"SubTree:{subtree_id}",
                action_fn=lambda: NodeStatus.FAILURE,
                blackboard=self._blackboard,
            )

        node_class = self._plugin_registry.get(tag) or self.NODE_MAP.get(tag)

        if node_class is not None:
            node = node_class(name=name, blackboard=self._blackboard)
        else:
            node = ActionNode(name=name, blackboard=self._blackboard)

        for child_element in element:
            if child_element.tag == "TreeNodesModel":
                continue
            child_node = self._build_node(child_element)
            if hasattr(node, "add_child"):
                node.add_child(child_node)

        return node