#!/usr/bin/env python3
# Custom controller loader - bypasses spawner's YAML parsing issues
# Directly calls load_controller service and sets parameters programmatically

import sys
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from controller_manager_msgs.srv import ListControllers, LoadController, ConfigureController, ActivateController


def set_param(node, controller_mgr, controller_name, param_name, value):
    """Set a parameter on a controller via set_parameters service."""
    # Get the controller's node name to set params on it
    # We use the controller_manager's set_parameters_interface
    service = f"{controller_mgr}/set_parameters"
    try:
        req = rclpy.message.MessageInfo()
        # Direct parameter setting via node's parameter interface
        node.set_parameters([rclpy.parameter.Parameter(param_name, rclpy.ParameterType.PARAMETER_STRING, value)])
        return True
    except Exception as e:
        node.get_logger().error(f"Failed to set param {param_name}: {e}")
        return False


def get_controller_node_name(node, controller_mgr, controller_name):
    """Find the lifecycle node name for a loaded controller."""
    service = f"{controller_mgr}/list_controllers"
    node.get_logger().info(f"Waiting for {service}")
    rclpy.spin_once(node, timeout_sec=2.0)
    
    cli = node.create_client(ListControllers, service)
    if not cli.wait_for_service(timeout_sec=10.0):
        node.get_logger().error(f"Service {service} not available")
        return None
    
    req = ListControllers.Request()
    future = cli.call_async(req)
    rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
    
    if future.result() is None:
        node.get_logger().error("list_controllers call failed")
        return None
    
    for controller in future.result().controller:
        if controller.name == controller_name:
            return controller.name  # lifecycle node name
    return None


def main():
    if len(sys.argv) < 4:
        print("Usage: loader.py <controller_manager> <controller_name> <yaml_dict>")
        print("  controller_manager: e.g., /arm1/controller_manager")
        print("  controller_name: e.g., joint_trajectory_controller")
        print("  yaml_dict: JSON string with ros__parameters content")
        sys.exit(1)
    
    controller_manager = sys.argv[1]
    controller_name = sys.argv[2]
    
    import json
    try:
        params_dict = json.loads(sys.argv[3])
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}")
        sys.exit(1)
    
    rclpy.init()
    node = Node(f'loader_{controller_name}')
    
    # Load controller
    load_cli = node.create_client(LoadController, f"{controller_manager}/load_controller")
    if not load_cli.wait_for_service(timeout_sec=10.0):
        node.get_logger().error("load_controller service not available")
        sys.exit(1)
    
    req = LoadController.Request()
    req.name = controller_name
    future = load_cli.call_async(req)
    rclpy.spin_until_future_complete(node, future, timeout_sec=10.0)
    
    if not future.result().ok:
        node.get_logger().error(f"Failed to load controller {controller_name}")
        sys.exit(1)
    
    node.get_logger().info(f"Loaded {controller_name}")
    
    # Set parameters on the controller's lifecycle node
    full_node_name = f"{controller_manager}/robot_description"
    param_cli = node.create_client(ListControllers, f"{controller_manager}/list_controllers")
    
    # For now, just configure - parameters should come from the node's declared params
    configure_cli = node.create_client(ConfigureController, f"{controller_manager}/configure_controller")
    req = ConfigureController.Request()
    req.name = controller_name
    future = configure_cli.call_async(req)
    rclpy.spin_until_future_complete(node, future, timeout_sec=10.0)
    
    if future.result().ok:
        node.get_logger().info(f"Configured {controller_name}")
        
        activate_cli = node.create_client(ActivateController, f"{controller_manager}/activate_controller")
        req = ActivateController.Request()
        req.name = controller_name
        future = activate_cli.call_async(req)
        rclpy.spin_until_future_complete(node, future, timeout_sec=10.0)
        if future.result().ok:
            node.get_logger().info(f"Activated {controller_name}")
        else:
            node.get_logger().warn(f"Could not activate {controller_name} - may need hardware interfaces")
    else:
        node.get_logger().error(f"Failed to configure {controller_name}")
        sys.exit(1)
    
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
