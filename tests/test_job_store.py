from __future__ import annotations

import time
from pathlib import Path

from src.db.schema import SCHEMA_VERSION, init_db
from src.db.session import session_scope
from src.db.models import JobRow, SchemaMeta
from src.job_store import (
    finish_job,
    get_job,
    get_latest_job,
    insert_running_job,
    mark_interrupted_running,
    prune_old_jobs,
    sanitize_params,
    truncate_log_summary,
    update_job_progress,
)


def test_schema_version_is_v3(isolated_home: Path) -> None:
    _ = isolated_home
    assert SCHEMA_VERSION == 3
    with session_scope() as session:
        meta = session.get(SchemaMeta, 1)
        assert meta is not None
        assert int(meta.version) == 3


def test_insert_progress_finish_roundtrip(isolated_home: Path) -> None:
    _ = isolated_home
    job_id = insert_running_job(
        action="refresh_status",
        label="刷新任务状态",
        source="ui",
        params={"x": 1},
    )
    assert job_id > 0
    update_job_progress(
        job_id,
        step=1,
        total=1,
        message="进行中",
        log_summary="line1",
        result={"a": 1},
    )
    assert finish_job(
        job_id,
        state="success",
        message="完成",
        log_summary="line1\nline2",
        result={"a": 1, "ok": True},
        error_kind=None,
    )
    row = get_job(job_id)
    assert row is not None
    assert row["state"] == "success"
    assert row["source"] == "ui"
    assert row["params"]["x"] == 1
    assert row["result"]["ok"] is True
    assert get_latest_job()["id"] == job_id


def test_a1_busy_does_not_require_second_row_here(isolated_home: Path) -> None:
    """占槽语义在 JobRunner；此处验证 running 行不会被 finish 以外改终态误伤。"""
    _ = isolated_home
    job_id = insert_running_job(action="login", label="扫码登录", source="ui", params={})
    assert not finish_job(
        job_id + 999,
        state="success",
        message="x",
        log_summary="",
    )
    row = get_job(job_id)
    assert row is not None
    assert row["state"] == "running"


def test_mark_interrupted_and_prune(isolated_home: Path) -> None:
    _ = isolated_home
    running_id = insert_running_job(action="refresh_all", label="一键更新", source="auto", params={})
    old_id = insert_running_job(action="refresh_status", label="刷新", source="ui", params={})
    old_finished = int(time.time()) - 8 * 86400
    assert finish_job(
        old_id,
        state="success",
        message="旧任务",
        log_summary="old",
        finished_at=old_finished,
    )
    marked = mark_interrupted_running(message="进程退出，任务中断")
    assert marked == 1
    row = get_job(running_id)
    assert row is not None
    assert row["state"] == "interrupted"
    assert row["error_kind"] == "interrupted"
    deleted = prune_old_jobs()
    assert deleted >= 1
    assert get_job(old_id) is None
    assert get_job(running_id) is not None


def test_truncate_log_summary_keeps_tail(isolated_home: Path) -> None:
    _ = isolated_home
    body = ("汉字abc" * 5000) + "TAIL_MARKER"
    out = truncate_log_summary(body, max_bytes=2048)
    assert "TAIL_MARKER" in out
    assert out.encode("utf-8").startswith("…(truncated)\n".encode("utf-8"))
    assert len(out.encode("utf-8")) <= 2048


def test_sanitize_params_strips_secrets(isolated_home: Path) -> None:
    _ = isolated_home
    cleaned = sanitize_params(
        {
            "dynamic_id": "123",
            "cookie": "SECRET",
            "api_key": "k",
            "nested": {"token": "t", "ok": 1},
        }
    )
    assert cleaned["dynamic_id"] == "123"
    assert "cookie" not in cleaned
    assert "api_key" not in cleaned
    assert "token" not in cleaned["nested"]
    assert cleaned["nested"]["ok"] == 1


def test_schema_migrations_are_idempotent(isolated_home: Path) -> None:
    _ = isolated_home
    init_db()
    init_db()
    with session_scope() as session:
        meta = session.get(SchemaMeta, 1)
        assert meta is not None
        assert int(meta.version) == 3
        # 新列可写
        row = JobRow(
            action="login",
            label="扫码登录",
            state="success",
            source="ui",
            params_json="{}",
            message="ok",
            log_summary="",
            created_at=1,
            started_at=1,
            finished_at=1,
        )
        session.add(row)
