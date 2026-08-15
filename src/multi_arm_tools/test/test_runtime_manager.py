"""Unit tests for Robot OS Shell runtime: session ownership, PATH safety.

These tests cover the runtime/doctor/shell layer without requiring a live
ROS 2 stack. Process killing is mocked so we can assert that ``stop`` only
ever targets processes belonging to the session that issued the stop.
"""

import os
import signal
from pathlib import Path
from unittest import mock

import pytest

from multi_arm_tools.runtime_manager import (
    FALLBACK_PATH,
    ProcessInfo,
    RuntimeManager,
    SessionManifest,
    safe_env,
)


# --------------------------------------------------------------------------
# safe_env / PATH robustness
# --------------------------------------------------------------------------

def test_safe_env_populates_empty_path():
    with mock.patch.dict(os.environ, {}, clear=True):
        env = safe_env()
    assert "/usr/bin" in env["PATH"].split(":")


def test_safe_env_keeps_existing_and_appends_missing():
    with mock.patch.dict(os.environ, {"PATH": "/custom/bin"}, clear=True):
        env = safe_env()
    parts = env["PATH"].split(":")
    assert "/custom/bin" in parts
    assert "/usr/bin" in parts
    # existing entries are preserved, fallback appended (not overriding)
    assert parts.index("/custom/bin") < parts.index("/usr/bin")


def test_fallback_path_contains_standard_bins():
    for needed in ("/usr/bin", "/opt/ros/jazzy/bin"):
        assert needed in FALLBACK_PATH.split(":")


def test_subprocess_calls_inject_safe_env(monkeypatch):
    captured = {}

    def fake_check_output(cmd, *a, **kw):
        captured["env"] = kw.get("env")
        raise FileNotFoundError  # stop early, we only care about the env

    monkeypatch.setattr(
        "multi_arm_tools.runtime_manager.subprocess.check_output", fake_check_output
    )
    mgr = RuntimeManager(runtime_dir=Path("/tmp/rtm-test-nonexistent"))
    mgr.discover_processes()
    assert captured["env"] is not None
    assert "/usr/bin" in captured["env"]["PATH"]


# --------------------------------------------------------------------------
# session lifecycle
# --------------------------------------------------------------------------

def test_create_session_writes_manifest_and_current(tmp_path):
    mgr = RuntimeManager(runtime_dir=tmp_path)
    manifest = mgr.create_session()
    assert (tmp_path / manifest.session_id / "manifest.yaml").exists()
    assert (tmp_path / "current").is_symlink()
    loaded = mgr.get_active_session()
    assert loaded is not None
    assert loaded.session_id == manifest.session_id


def test_get_active_session_none_without_current(tmp_path):
    mgr = RuntimeManager(runtime_dir=tmp_path)
    assert mgr.get_active_session() is None


def test_allocate_domain_returns_pool_value(tmp_path):
    mgr = RuntimeManager(runtime_dir=tmp_path)
    assert mgr._allocate_domain() in range(40, 60)


def test_allocate_domain_avoids_used(tmp_path):
    session_dir = tmp_path / "session-x"
    session_dir.mkdir()
    (session_dir / "manifest.yaml").write_text(
        "session_id: session-x\ncreated_at: t\ndomain_id: 40\nstatus: running\n"
    )
    mgr = RuntimeManager(runtime_dir=tmp_path)
    assert mgr._allocate_domain() == 41


# --------------------------------------------------------------------------
# session ownership: stop must NOT kill foreign processes
# --------------------------------------------------------------------------

def test_stop_session_only_kills_owned_tree(tmp_path, monkeypatch):
    mgr = RuntimeManager(runtime_dir=tmp_path)
    manifest = mgr.create_session()
    manifest.launch_pid = 4242
    mgr._save_manifest(manifest)

    killed_pids: list[int] = []

    def fake_kill(pid, sig):
        killed_pids.append(pid)

    def fake_killpg(pgid, sig):
        killed_pids.append(pgid)

    monkeypatch.setattr("multi_arm_tools.runtime_manager.os.kill", fake_kill)
    monkeypatch.setattr("multi_arm_tools.runtime_manager.os.killpg", fake_killpg)
    monkeypatch.setattr("multi_arm_tools.runtime_manager.os.getpgid", lambda pid: pid)
    monkeypatch.setattr(mgr, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(mgr, "_find_children", lambda pid: [4243, 4244])

    # The cross-session killer must be gone entirely.
    assert not hasattr(RuntimeManager, "_kill_owned_processes"), \
        "cross-session killer must be removed to avoid killing foreign processes"

    mgr.stop_session(manifest)

    # Only the owned launch PID and its descendants are touched.
    assert set(killed_pids) == {4242, 4243, 4244}
    # current symlink removed
    assert not (tmp_path / "current").exists()


def test_stop_session_without_manifest_is_noop(tmp_path):
    mgr = RuntimeManager(runtime_dir=tmp_path)
    assert mgr.stop_session(None) is False


def test_kill_process_tree_uses_killpg(tmp_path, monkeypatch):
    mgr = RuntimeManager(runtime_dir=tmp_path)
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "multi_arm_tools.runtime_manager.os.killpg",
        lambda pgid, sig: calls.append((pgid, sig)),
    )
    monkeypatch.setattr("multi_arm_tools.runtime_manager.os.getpgid", lambda pid: pid)
    monkeypatch.setattr("multi_arm_tools.runtime_manager.os.kill", lambda pid, sig: None)
    monkeypatch.setattr(mgr, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(mgr, "_find_children", lambda pid: [])
    mgr._kill_process_tree(7777)
    assert (7777, signal.SIGTERM) in calls


# --------------------------------------------------------------------------
# duplicate / stale detection
# --------------------------------------------------------------------------

def test_detect_duplicates(tmp_path, monkeypatch):
    mgr = RuntimeManager(runtime_dir=tmp_path)
    procs = [
        ProcessInfo("gazebo", 1, 0, "gz sim", True),
        ProcessInfo("gazebo", 2, 0, "gz sim", True),
    ]
    monkeypatch.setattr(mgr, "discover_processes", lambda: procs)
    dups = mgr.detect_duplicates()
    assert "gazebo" in dups
    assert len(dups["gazebo"]) == 2


def test_detect_stale_nodes(tmp_path, monkeypatch):
    mgr = RuntimeManager(runtime_dir=tmp_path)
    out = "/world_model_node\n/world_model_node\n"
    monkeypatch.setattr(
        "multi_arm_tools.runtime_manager.subprocess.check_output",
        lambda *a, **k: out,
    )
    assert mgr.detect_stale_nodes() == ["/world_model_node"]


def test_detect_stale_nodes_handles_failure(tmp_path, monkeypatch):
    mgr = RuntimeManager(runtime_dir=tmp_path)
    monkeypatch.setattr(
        "multi_arm_tools.runtime_manager.subprocess.check_output",
        mock.Mock(side_effect=FileNotFoundError),
    )
    assert mgr.detect_stale_nodes() == []


# --------------------------------------------------------------------------
# repair
# --------------------------------------------------------------------------

def test_repair_restarts_dds_on_duplicates(tmp_path, monkeypatch):
    mgr = RuntimeManager(runtime_dir=tmp_path)
    monkeypatch.setattr(
        mgr,
        "detect_duplicates",
        lambda: {
            "gazebo": [
                ProcessInfo("gazebo", 1, 0, "gz sim", True),
                ProcessInfo("gazebo", 2, 0, "gz sim", True),
            ]
        },
    )
    monkeypatch.setattr(mgr, "_find_zombie_processes", lambda: [])

    # avoid signalling real PIDs in this environment
    monkeypatch.setattr("multi_arm_tools.runtime_manager.os.kill", lambda *a, **k: None)

    daemon_calls: list[list[str]] = []

    def fake_run(cmd, **k):
        daemon_calls.append(cmd)
        run = mock.Mock()
        run.returncode = 0
        return run

    monkeypatch.setattr("multi_arm_tools.runtime_manager.subprocess.run", fake_run)
    report = mgr.repair()
    assert report["dds_reset"] is True
    assert any("daemon" in " ".join(c) for c in daemon_calls)


# --------------------------------------------------------------------------
# doctor (runtime health) — no ROS required
# --------------------------------------------------------------------------

def _patch_runtime_manager(monkeypatch, duplicates, stale):
    mgr = mock.MagicMock()
    mgr.detect_duplicates.return_value = duplicates
    mgr.detect_stale_nodes.return_value = stale
    monkeypatch.setattr(
        "multi_arm_tools.runtime_manager.RuntimeManager", lambda: mgr
    )
    return mgr


def test_doctor_runtime_health_clean(monkeypatch):
    _patch_runtime_manager(monkeypatch, {}, [])
    from multi_arm_tools.doctor import Doctor

    doc = Doctor()
    doc._check_runtime_health()
    assert any(
        c["category"] in ("Runtime", "DDS") and c["pass"] for c in doc._checks
    )
    assert doc._total > 0


def test_doctor_runtime_health_reports_duplicates(monkeypatch):
    _patch_runtime_manager(
        monkeypatch,
        {"gazebo": [mock.MagicMock(pid=1), mock.MagicMock(pid=2)]},
        [],
    )
    from multi_arm_tools.doctor import Doctor

    doc = Doctor()
    doc._check_runtime_health()
    assert any(
        c["category"] == "Runtime" and not c["pass"] for c in doc._checks
    )


def test_doctor_subprocess_injects_safe_env(monkeypatch):
    captured = {}

    def fake_run(cmd, **kw):
        captured["env"] = kw.get("env")
        run = mock.Mock()
        run.returncode = 1
        run.stdout = ""
        return run

    monkeypatch.setattr("multi_arm_tools.doctor.subprocess.run", fake_run)
    from multi_arm_tools.doctor import Doctor

    doc = Doctor()
    doc._get_nodes()
    assert captured["env"] is not None
    assert "/usr/bin" in captured["env"]["PATH"]


# --------------------------------------------------------------------------
# interactive shell — bootstrap / repair flow
# --------------------------------------------------------------------------

def test_shell_bootstrap_success(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "multi_arm_tools.interactive_shell._verify_runtime",
        lambda: (True, "no active session"),
    )
    monkeypatch.chdir(tmp_path)
    (tmp_path / "install").mkdir()
    (tmp_path / "install" / "setup.bash").write_text("")
    monkeypatch.setenv("ROS_DISTRO", "jazzy")
    monkeypatch.setenv("RMW_IMPLEMENTATION", "rmw_cyclonedds_cpp")

    from multi_arm_tools.interactive_shell import InteractiveShell

    shell = InteractiveShell.__new__(InteractiveShell)  # skip __init__ (makes RuntimeManager)
    assert shell._bootstrap() is True


def test_shell_check_and_repair_skips_when_clean(tmp_path, monkeypatch):
    from multi_arm_tools.interactive_shell import InteractiveShell

    shell = InteractiveShell.__new__(InteractiveShell)
    shell._mgr = mock.MagicMock()
    shell._mgr.detect_duplicates.return_value = {}
    shell._mgr.detect_stale_nodes.return_value = []

    shell._check_and_repair()  # must return without calling input/repair
    shell._mgr.repair.assert_not_called()


# --------------------------------------------------------------------------
# runtime_client — singleton (skipped without ROS runtime)
# --------------------------------------------------------------------------

def test_runtime_client_singleton():
    try:
        from multi_arm_tools.runtime_client import RuntimeClient
    except ImportError:
        pytest.skip("runtime_client requires ROS message packages")
    try:
        a = RuntimeClient()
        b = RuntimeClient()
    except Exception:
        pytest.skip("runtime_client requires a live ROS runtime")
    assert a is b
