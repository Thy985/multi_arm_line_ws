"""BenchmarkRecorder — collects execution data into SQLite database.

Records task execution metrics including timing, success/failure,
resource wait time, recovery count, and collision events.
"""

import json
import os
import sqlite3
import time as _time
from typing import Any, Dict, List, Optional


class BenchmarkRecorder:
    """Records benchmark execution data to SQLite.

    Schema:
        runs — one row per benchmark run (scenario, timestamp, git_hash)
        task_records — one row per task execution within a run

    Usage:
        recorder = BenchmarkRecorder(db_path="/tmp/benchmark.db")
        run_id = recorder.start_run("single_arm")
        record_id = recorder.record_task_start(run_id, "left_arm", "move", "left_arm:zone_a:ready")
        recorder.record_task_end(record_id, success=True, planning_time=0.5, execution_time=3.2)
        recorder.end_run(run_id)
    """

    def __init__(self, db_path: str = "") -> None:
        if not db_path:
            ros_home = os.environ.get("ROS_HOME", os.path.expanduser("~/.ros"))
            bench_dir = os.path.join(ros_home, "benchmark")
            os.makedirs(bench_dir, exist_ok=True)
            db_path = os.path.join(bench_dir, "benchmark.db")

        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                scenario_name TEXT NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL,
                total_duration REAL,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                git_hash TEXT,
                metadata TEXT
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS task_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                task_id TEXT NOT NULL,
                arm_name TEXT NOT NULL,
                action_type TEXT NOT NULL,
                description TEXT,
                task_start REAL NOT NULL,
                task_end REAL,
                planning_time REAL,
                execution_time REAL,
                total_time REAL,
                success INTEGER DEFAULT 0,
                failure_reason TEXT,
                resource_wait_time REAL DEFAULT 0.0,
                recovery_count INTEGER DEFAULT 0,
                collision_count INTEGER DEFAULT 0,
                safety_rejections INTEGER DEFAULT 0,
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_records_run_id
            ON task_records(run_id)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_records_arm
            ON task_records(arm_name)
        """)
        self._conn.commit()

    @property
    def db_path(self) -> str:
        return self._db_path

    def start_run(self, scenario_name: str, git_hash: str = "", metadata: Optional[Dict[str, Any]] = None) -> int:
        """Start a new benchmark run.

        Args:
            scenario_name: Name of the benchmark scenario.
            git_hash: Current git commit hash.
            metadata: Optional metadata dict (stored as JSON).

        Returns:
            run_id for the new run.
        """
        cursor = self._conn.execute(
            "INSERT INTO runs (scenario_name, start_time, git_hash, metadata) VALUES (?, ?, ?, ?)",
            (scenario_name, _time.time(), git_hash, json.dumps(metadata) if metadata else None)
        )
        self._conn.commit()
        return cursor.lastrowid

    def end_run(self, run_id: int) -> None:
        """End a benchmark run, computing aggregate stats.

        Args:
            run_id: The run to end.
        """
        row = self._conn.execute(
            "SELECT COUNT(*) FROM task_records WHERE run_id=? AND success=1",
            (run_id,)
        ).fetchone()
        success_count = row[0] if row else 0

        row = self._conn.execute(
            "SELECT COUNT(*) FROM task_records WHERE run_id=? AND success=0",
            (run_id,)
        ).fetchone()
        failure_count = row[0] if row else 0

        start_row = self._conn.execute(
            "SELECT start_time FROM runs WHERE run_id=?", (run_id,)
        ).fetchone()
        start_time = start_row[0] if start_row else _time.time()
        total_duration = _time.time() - start_time

        self._conn.execute(
            "UPDATE runs SET end_time=?, total_duration=?, success_count=?, failure_count=? WHERE run_id=?",
            (_time.time(), total_duration, success_count, failure_count, run_id)
        )
        self._conn.commit()

    def record_task_start(
        self, run_id: int, task_id: str, arm_name: str,
        action_type: str, description: str = ""
    ) -> int:
        """Record the start of a task execution.

        Args:
            run_id: Parent benchmark run.
            task_id: Task identifier.
            arm_name: Arm executing the task.
            action_type: Type of action (move, pick_place, etc.).
            description: Task description string.

        Returns:
            record_id for the task record.
        """
        cursor = self._conn.execute(
            "INSERT INTO task_records (run_id, task_id, arm_name, action_type, description, task_start) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, task_id, arm_name, action_type, description, _time.time())
        )
        self._conn.commit()
        return cursor.lastrowid

    def record_task_end(
        self, record_id: int, success: bool,
        planning_time: float = 0.0, execution_time: float = 0.0,
        failure_reason: str = "", resource_wait_time: float = 0.0,
        recovery_count: int = 0, collision_count: int = 0,
        safety_rejections: int = 0
    ) -> None:
        """Record the end of a task execution.

        Args:
            record_id: The task record to update.
            success: Whether the task succeeded.
            planning_time: Time spent on motion planning.
            execution_time: Time spent on trajectory execution.
            failure_reason: Reason for failure (if any).
            resource_wait_time: Time spent waiting for resource allocation.
            recovery_count: Number of recovery attempts.
            collision_count: Number of collision events.
            safety_rejections: Number of safety rejections.
        """
        now = _time.time()
        row = self._conn.execute(
            "SELECT task_start FROM task_records WHERE record_id=?", (record_id,)
        ).fetchone()
        task_start = row[0] if row else now
        total_time = now - task_start

        self._conn.execute(
            """UPDATE task_records SET
                task_end=?, planning_time=?, execution_time=?, total_time=?,
                success=?, failure_reason=?, resource_wait_time=?,
                recovery_count=?, collision_count=?, safety_rejections=?
               WHERE record_id=?""",
            (now, planning_time, execution_time, total_time,
             1 if success else 0, failure_reason, resource_wait_time,
             recovery_count, collision_count, safety_rejections, record_id)
        )
        self._conn.commit()

    def get_run_summary(self, run_id: int) -> Optional[Dict[str, Any]]:
        """Get summary statistics for a benchmark run.

        Args:
            run_id: The run to summarize.

        Returns:
            Dict with run summary, or None if not found.
        """
        row = self._conn.execute(
            "SELECT * FROM runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if row is None:
            return None

        cols = [d[0] for d in self._conn.execute(
            "SELECT * FROM runs WHERE run_id=?", (run_id,)
        ).description]
        result = dict(zip(cols, row))

        if result.get("metadata"):
            result["metadata"] = json.loads(result["metadata"])

        tasks = self._conn.execute(
            "SELECT * FROM task_records WHERE run_id=?", (run_id,)
        ).fetchall()
        task_cols = [d[0] for d in self._conn.execute(
            "SELECT * FROM task_records WHERE run_id=?", (run_id,)
        ).description]
        result["tasks"] = [dict(zip(task_cols, t)) for t in tasks]

        success_count = result.get("success_count", 0)
        failure_count = result.get("failure_count", 0)
        total = success_count + failure_count
        result["success_rate"] = success_count / total if total > 0 else 0.0

        planning_times = [t[0] for t in self._conn.execute(
            "SELECT planning_time FROM task_records WHERE run_id=? AND planning_time IS NOT NULL",
            (run_id,)
        ).fetchall() if t[0] is not None]
        result["avg_planning_time"] = sum(planning_times) / len(planning_times) if planning_times else 0.0

        execution_times = [t[0] for t in self._conn.execute(
            "SELECT execution_time FROM task_records WHERE run_id=? AND execution_time IS NOT NULL",
            (run_id,)
        ).fetchall() if t[0] is not None]
        result["avg_execution_time"] = sum(execution_times) / len(execution_times) if execution_times else 0.0

        return result

    def get_scenario_history(self, scenario_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get historical runs for a scenario.

        Args:
            scenario_name: Scenario to query.
            limit: Maximum number of runs to return.

        Returns:
            List of run summary dicts.
        """
        rows = self._conn.execute(
            "SELECT run_id FROM runs WHERE scenario_name=? ORDER BY start_time DESC LIMIT ?",
            (scenario_name, limit)
        ).fetchall()
        return [self.get_run_summary(r[0]) for r in rows if self.get_run_summary(r[0]) is not None]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None