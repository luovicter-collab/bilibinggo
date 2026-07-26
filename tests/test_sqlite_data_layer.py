from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.activity_store import (
    activity_count,
    activity_exists,
    append_activities,
    dismiss_activity,
    known_activity_ids,
    load_activities,
    replace_all_activities,
    update_activity,
)
from src.db.activity_codec import activity_dict_to_row, row_to_activity_dict
from src.db.engine import db_path, reset_engine_for_tests
from src.db.import_json import EXIT_NONEMPTY, EXIT_SOURCE, ImportError as JsonImportError, run_import
from src.db.schema import SCHEMA_VERSION, init_db
from src.db.session import session_scope
from src.db.models import SchemaMeta
from src.participation_store import load_participations, set_participation
from src.state_store import get_last_container, save_state, set_last_container


def test_init_db_idempotent(isolated_home: Path) -> None:
    init_db()
    init_db()
    with session_scope() as session:
        meta = session.get(SchemaMeta, 1)
        assert meta is not None
        assert int(meta.version) == SCHEMA_VERSION
    assert db_path().exists()
    assert db_path().parent == isolated_home / "data"


def test_activity_codec_preserves_business_type_int(isolated_home: Path) -> None:
    _ = isolated_home
    item = {
        "dynamic_id": "1234567890123456789",
        "business_type": 10,
        "lottery_type": "互动抽奖",
        "prizes": [{"description": "奖", "winner_count": 1}],
    }
    row = activity_dict_to_row(item, updated_at=1)
    back = row_to_activity_dict(row)
    assert back["business_type"] == 10
    assert back["prizes"][0]["description"] == "奖"


def test_activity_crud_counts(isolated_home: Path) -> None:
    replace_all_activities(
        [
            {
                "dynamic_id": "1",
                "lottery_type": "转发抽奖",
                "draw_status": "active",
                "activity_status": "未参加",
            },
            {
                "dynamic_id": "2",
                "lottery_type": "互动抽奖",
                "draw_status": "ended",
                "activity_status": "已结束",
            },
        ]
    )
    assert activity_count() == 2
    assert {a["dynamic_id"] for a in load_activities()} == {"1", "2"}


def test_dismissed_activity_cannot_be_restored_by_stale_writers(isolated_home: Path) -> None:
    _ = isolated_home
    item = {
        "dynamic_id": "100000000000000001",
        "lottery_type": "转发抽奖",
        "draw_status": "active",
        "activity_status": "未参加",
    }
    replace_all_activities([item])

    assert dismiss_activity(item["dynamic_id"]) is True
    assert activity_exists(item["dynamic_id"]) is False
    assert activity_count() == 0
    assert item["dynamic_id"] in known_activity_ids()

    # 数据源刷新、状态刷新与参与完成写回都不能让已移除活动复活。
    assert append_activities([item]) == 0
    replace_all_activities([item])
    update_activity(item["dynamic_id"], item)
    assert load_activities() == []
    assert dismiss_activity(item["dynamic_id"]) is False


def test_state_checkpoint_roundtrip(isolated_home: Path) -> None:
    save_state({"sources": {}})
    assert get_last_container("DS-2") is None
    set_last_container("DS-2", "https://example.com/cv1", container_id="cv1", title="t")
    assert get_last_container("DS-2") == "https://example.com/cv1"


def test_participation_roundtrip(isolated_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.db.uids.participation_uid", lambda: "test-uid")
    monkeypatch.setattr("src.participation_store.participation_uid", lambda: "test-uid")
    set_participation("111", "已参加")
    loaded = load_participations()
    assert loaded["111"].user_status == "已参加"


def _write_minimal_json_tree(home: Path) -> None:
    data = home / "data"
    config = home / "config"
    (data / "output").mkdir(parents=True, exist_ok=True)
    (data / "cache").mkdir(parents=True, exist_ok=True)
    (data / "users" / "1").mkdir(parents=True, exist_ok=True)
    config.mkdir(parents=True, exist_ok=True)

    (data / "output" / "activities_latest.json").write_text(
        json.dumps(
            {
                "updated_at": 1,
                "activities": [
                    {
                        "dynamic_id": "1000000000000000001",
                        "lottery_type": "互动抽奖",
                        "business_type": 10,
                        "draw_status": "active",
                        "activity_status": "未参加",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (data / "state.json").write_text(
        json.dumps(
            {
                "sources": {
                    "DS-1": {
                        "container_url": "https://example.com/a",
                        "container_id": "a",
                        "checked_at": 1,
                    }
                },
                "watch": {"last_synced_at": 2},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (config / "watch_users.json").write_text(
        json.dumps({"updated_at": 1, "users": [{"mid": 42, "name": "测试"}]}),
        encoding="utf-8",
    )
    (data / "users" / "1" / "participations.json").write_text(
        json.dumps(
            {
                "entries": {
                    "1000000000000000001": {
                        "dynamic_id": "1000000000000000001",
                        "user_status": "已参加",
                        "updated_at": 1,
                        "source": "participate",
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def test_import_json_dry_and_nonempty_guard(isolated_home: Path) -> None:
    _write_minimal_json_tree(isolated_home)
    report = run_import(force=True, yes=True, archive=False)
    assert any(line.kind == "activities" and line.imported == 1 for line in report.lines)
    assert activity_count() == 1
    assert get_last_container("DS-1") == "https://example.com/a"

    with pytest.raises(JsonImportError) as exc:
        run_import(force=False, yes=False, archive=False)
    assert exc.value.code == EXIT_NONEMPTY


def test_import_json_missing_required_fails(isolated_home: Path) -> None:
    # 仅建目录，不写 activities / state / watch_users
    (isolated_home / "data" / "output").mkdir(parents=True, exist_ok=True)
    with pytest.raises(JsonImportError) as exc:
        run_import(force=True, yes=True, archive=False)
    assert exc.value.code == EXIT_SOURCE


def test_import_json_archives_sources(isolated_home: Path) -> None:
    _write_minimal_json_tree(isolated_home)
    run_import(force=True, yes=True, archive=True)
    assert not (isolated_home / "data" / "output" / "activities_latest.json").exists()
    archived = (
        isolated_home / "data" / "backup" / "json_pre_sqlite" / "data" / "output" / "activities_latest.json"
    )
    assert archived.is_file()
    assert (isolated_home / "data" / "binggo.db").is_file()
