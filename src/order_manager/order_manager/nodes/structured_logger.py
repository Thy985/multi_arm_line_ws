"""
Structured JSON logger with dynamic log level adjustment for ROS2 nodes.

Features:
- All log output in single-line JSON format (machine-parseable)
- Structured fields: timestamp, level, logger, node, arm, component, data
- Runtime log level change via ROS2 service ~/set_log_level (std_srvs/srv/SetBool)
  - Request.data=True  -> DEBUG level
  - Request.data=False -> INFO level (default)
  - Or use the set_level() method directly

Usage:
    from order_manager.nodes.structured_logger import StructuredLogger
    logger = StructuredLogger(node)
    logger.info('Arm moved', arm='left_arm', component='coordinator', data={'zone': 'zone_a'})
    logger.set_level('DEBUG')
"""

import json
import logging
import traceback
from datetime import datetime, timezone
from std_srvs.srv import SetBool


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    FIELDS = ('timestamp', 'level', 'logger', 'message', 'node', 'arm', 'component')

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'node': getattr(record, '_ros_node', ''),
            'arm': getattr(record, '_arm', ''),
            'component': getattr(record, '_component', ''),
        }

        if record.exc_info and record.exc_info[0] is not None:
            log_entry['exception'] = ''.join(traceback.format_exception(*record.exc_info))

        extra_data = getattr(record, '_extra', None)
        if extra_data:
            log_entry['data'] = extra_data

        return json.dumps(log_entry, ensure_ascii=False, default=str)


class StructuredLogger:
    """
    Structured JSON logger with dynamic level control for ROS2 nodes.

    Replaces node.get_logger() with JSON-formatted output and a ROS2 service
    for runtime log level adjustment.
    """

    LEVEL_MAP = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARN': logging.WARNING,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'FATAL': logging.CRITICAL,
    }

    ROS_LEVEL_MAP = {
        'DEBUG': 0, 'INFO': 1, 'WARN': 2, 'ERROR': 3, 'FATAL': 4,
    }

    LEVEL_BOOL_MAP = {
        True: 'DEBUG',
        False: 'INFO',
    }

    def __init__(self, node, log_file: str = None):
        self._node = node
        self._node_name = node.get_name()
        self._current_level = 'INFO'

        self._py_logger = logging.getLogger(f'ros2.{self._node_name}')
        self._py_logger.propagate = False
        self._py_logger.setLevel(logging.DEBUG)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(JsonFormatter())
        console_handler.setLevel(logging.INFO)
        self._py_logger.addHandler(console_handler)
        self._console_handler = console_handler

        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(JsonFormatter())
            file_handler.setLevel(logging.DEBUG)
            self._py_logger.addHandler(file_handler)
            self._file_handler = file_handler
        else:
            self._file_handler = None

        self._set_ros_logger_level('INFO')

        self._srv = node.create_service(
            SetBool,
            '~/set_log_level',
            self._on_set_level,
        )

    def _set_ros_logger_level(self, level_name: str):
        ros_level = self.ROS_LEVEL_MAP.get(level_name.upper(), 1)
        self._node.get_logger().set_level(ros_level)

    def _on_set_level(self, request, response):
        target_level = self.LEVEL_BOOL_MAP.get(request.data, 'INFO')
        self.set_level(target_level)
        response.success = True
        response.message = f'Log level set to {self._current_level}'
        return response

    def set_level(self, level_name: str) -> bool:
        """
        Dynamically change log level at runtime.

        Args:
            level_name: One of DEBUG, INFO, WARN, ERROR, FATAL

        Returns:
            True if level was changed successfully
        """
        level = level_name.upper()
        if level not in self.LEVEL_MAP:
            return False

        self._current_level = level
        py_level = self.LEVEL_MAP[level]
        self._py_logger.setLevel(py_level)
        for handler in self._py_logger.handlers:
            handler.setLevel(py_level)
        self._set_ros_logger_level(level)
        self.info(f'Log level changed to {level}', component='logger')
        return True

    @property
    def current_level(self) -> str:
        return self._current_level

    def _make_extra(self, arm='', component='', data=None):
        return {
            '_ros_node': self._node_name,
            '_arm': arm,
            '_component': component,
            '_extra': data,
        }

    def debug(self, msg, arm='', component='', data=None):
        self._py_logger.debug(msg, extra=self._make_extra(arm, component, data))

    def info(self, msg, arm='', component='', data=None):
        self._py_logger.info(msg, extra=self._make_extra(arm, component, data))

    def warn(self, msg, arm='', component='', data=None):
        self._py_logger.warning(msg, extra=self._make_extra(arm, component, data))

    def error(self, msg, arm='', component='', data=None):
        self._py_logger.error(msg, extra=self._make_extra(arm, component, data))

    def fatal(self, msg, arm='', component='', data=None):
        self._py_logger.critical(msg, extra=self._make_extra(arm, component, data))
