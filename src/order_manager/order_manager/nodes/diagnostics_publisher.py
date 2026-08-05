"""
Diagnostics publisher for multi-arm system health monitoring.
Publishes /diagnostics topic with arm health status for rqt_robot_dashboard.
"""

import time
from diagnostic_msgs.msg import DiagnosticStatus, DiagnosticArray, KeyValue
from order_manager.nodes.arm_state import ArmState, ArmStatus, Zone


class DiagnosticsPublisher:
    """Publishes diagnostic information for all arms and zones."""

    def __init__(self, node, arm_status: dict, zones: dict, joint_states: dict):
        self._node = node
        self._arm_status = arm_status
        self._zones = zones
        self._joint_states = joint_states
        self._start_time = time.time()

        self._pub = node.create_publisher(DiagnosticArray, '/diagnostics', 10)
        node.create_timer(1.0, self._publish)

    def _arm_state_to_level(self, state: ArmState) -> int:
        mapping = {
            ArmState.IDLE: DiagnosticStatus.OK,
            ArmState.WORKING: DiagnosticStatus.OK,
            ArmState.REQUESTING: DiagnosticStatus.WARN,
            ArmState.QUEUED: DiagnosticStatus.WARN,
            ArmState.ERROR: DiagnosticStatus.ERROR,
        }
        return mapping.get(state, DiagnosticStatus.STALE)

    def _build_arm_status(self, name: str, status: ArmStatus) -> DiagnosticStatus:
        diag = DiagnosticStatus()
        diag.name = f'multi_arm/{name}'
        diag.hardware_id = name
        diag.level = self._arm_state_to_level(status.state)
        diag.message = f'{status.state.name}'

        diag.values.append(KeyValue(key='state', value=status.state.name))
        diag.values.append(KeyValue(key='current_zone', value=status.current_zone or 'none'))
        diag.values.append(KeyValue(key='requested_zone', value=status.requested_zone or 'none'))

        if status.goal_start_time:
            elapsed = time.time() - status.goal_start_time
            diag.values.append(KeyValue(key='goal_elapsed_s', value=f'{elapsed:.1f}'))

        if status.error_message:
            diag.values.append(KeyValue(key='error_message', value=status.error_message))

        js = self._joint_states.get(name)
        if js and js.position:
            for i, (jname, jval) in enumerate(zip(js.name, js.position)):
                short_name = jname.replace(f'{name}_', '')
                diag.values.append(KeyValue(key=f'joint_{short_name}_rad', value=f'{jval:.4f}'))

        return diag

    def _build_zone_status(self, zone: Zone) -> DiagnosticStatus:
        diag = DiagnosticStatus()
        diag.name = f'multi_arm/zone/{zone.name}'
        diag.hardware_id = zone.name
        diag.level = DiagnosticStatus.WARN if zone.occupied_by else DiagnosticStatus.OK
        diag.message = f'occupied_by={zone.occupied_by or "FREE"}'

        diag.values.append(KeyValue(key='type', value=zone.zone_type.name))
        diag.values.append(KeyValue(key='occupied_by', value=zone.occupied_by or 'none'))
        diag.values.append(KeyValue(key='queue_depth', value=str(len(zone.waiting_queue))))
        if zone.waiting_queue:
            diag.values.append(KeyValue(key='queue', value=','.join(zone.waiting_queue)))

        return diag

    def _build_system_status(self) -> DiagnosticStatus:
        diag = DiagnosticStatus()
        diag.name = 'multi_arm/system'
        diag.hardware_id = 'coordinator'
        diag.level = DiagnosticStatus.OK
        diag.message = 'running'

        uptime = time.time() - self._start_time
        diag.values.append(KeyValue(key='uptime_s', value=f'{uptime:.0f}'))
        diag.values.append(KeyValue(key='num_arms', value=str(len(self._arm_status))))

        idle = sum(1 for s in self._arm_status.values() if s.state == ArmState.IDLE)
        working = sum(1 for s in self._arm_status.values() if s.state == ArmState.WORKING)
        error = sum(1 for s in self._arm_status.values() if s.state == ArmState.ERROR)
        diag.values.append(KeyValue(key='arms_idle', value=str(idle)))
        diag.values.append(KeyValue(key='arms_working', value=str(working)))
        diag.values.append(KeyValue(key='arms_error', value=str(error)))

        if error > 0:
            diag.level = DiagnosticStatus.ERROR
            diag.message = f'{error} arm(s) in ERROR'
        elif working > 0:
            diag.message = f'{working} arm(s) working'

        return diag

    def _publish(self):
        msg = DiagnosticArray()
        msg.header.stamp = self._node.get_clock().now().to_msg()
        msg.header.frame_id = ''

        for name, status in self._arm_status.items():
            msg.status.append(self._build_arm_status(name, status))

        for zone in self._zones.values():
            msg.status.append(self._build_zone_status(zone))

        msg.status.append(self._build_system_status())

        self._pub.publish(msg)