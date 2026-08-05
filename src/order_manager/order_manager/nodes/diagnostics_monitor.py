#!/usr/bin/env python3
"""
Standalone diagnostics monitor node.
Subscribes to /diagnostics and prints arm health summaries.
Can be used independently of the coordinator for monitoring.
"""

import rclpy
from rclpy.node import Node
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus


class DiagnosticsMonitor(Node):
    """Monitors /diagnostics and prints human-readable arm health status."""

    LEVEL_NAMES = {
        DiagnosticStatus.OK: 'OK',
        DiagnosticStatus.WARN: 'WARN',
        DiagnosticStatus.ERROR: 'ERROR',
        DiagnosticStatus.STALE: 'STALE',
    }

    def __init__(self):
        super().__init__('diagnostics_monitor')

        self.create_subscription(DiagnosticArray, '/diagnostics', self._on_diagnostics, 10)
        self.get_logger().info('Diagnostics monitor started, listening on /diagnostics')

    def _on_diagnostics(self, msg: DiagnosticArray):
        for status in msg.status:
            level_str = self.LEVEL_NAMES.get(status.level, 'UNKNOWN')
            if status.level >= DiagnosticStatus.WARN:
                self.get_logger().warn(
                    f'[{status.name}] {level_str}: {status.message}'
                )
            elif status.level == DiagnosticStatus.OK and status.name.startswith('multi_arm/'):
                arm_name = status.name.replace('multi_arm/', '')
                kv = {kv.key: kv.value for kv in status.values}
                self.get_logger().info(
                    f'[{arm_name}] {kv.get("state", "?")} '
                    f'zone={kv.get("current_zone", "-")}'
                )


def main(args=None):
    rclpy.init(args=args)
    node = DiagnosticsMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()