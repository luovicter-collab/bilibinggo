from __future__ import annotations

from fastapi.testclient import TestClient

from src.activity_exclusions import (
    auto_failed_activity_ids,
    clear_auto_participation_failure,
    delete_activity,
    deleted_activity_ids,
    load_deleted_activities,
    record_auto_participation_failure,
    restore_activity,
)
from src.activity_store import append_activities, load_activities, replace_all_activities
from src.pipeline.refresh_all_pipeline import _dedupe_new_dynamic_ids
from web.app import app


def _activity(dynamic_id: str) -> dict:
    return {
        "dynamic_id": dynamic_id,
        "source_url": f"https://www.bilibili.com/opus/{dynamic_id}",
        "lottery_type": "互动抽奖",
        "draw_status": "active",
        "activity_status": "未参加",
        "prizes": [{"description": "测试奖品", "winner_count": 2}],
    }


def test_delete_activity_moves_snapshot_to_deleted_list(isolated_home) -> None:
    _ = isolated_home
    dynamic_id = "1234567890123456789"
    replace_all_activities([_activity(dynamic_id)])

    deleted = delete_activity(dynamic_id)

    assert deleted is not None
    assert deleted["dynamic_id"] == dynamic_id
    assert deleted["activity_title"] == "测试奖品 ×2"
    assert load_activities() == []
    assert deleted_activity_ids() == {dynamic_id}
    assert load_deleted_activities()[0]["source_url"].endswith(dynamic_id)


def test_deleted_activity_is_not_reinserted_until_restored(isolated_home) -> None:
    _ = isolated_home
    dynamic_id = "1234567890123456789"
    replace_all_activities([_activity(dynamic_id)])
    delete_activity(dynamic_id)

    assert append_activities([_activity(dynamic_id)]) == 0
    assert _dedupe_new_dynamic_ids([f"https://www.bilibili.com/opus/{dynamic_id}"]) == []
    replace_all_activities([_activity(dynamic_id)])
    assert load_activities() == []

    restored = restore_activity(dynamic_id)
    assert restored is not None
    assert [item["dynamic_id"] for item in load_activities()] == [dynamic_id]
    assert deleted_activity_ids() == set()


def test_auto_failure_list_roundtrip(isolated_home) -> None:
    _ = isolated_home
    dynamic_id = "1234567890123456789"
    record_auto_participation_failure(dynamic_id, "打开链接失败")
    assert auto_failed_activity_ids() == {dynamic_id}
    clear_auto_participation_failure(dynamic_id)
    assert auto_failed_activity_ids() == set()


def test_deleted_activity_api_roundtrip(isolated_home) -> None:
    _ = isolated_home
    dynamic_id = "1234567890123456789"
    replace_all_activities([_activity(dynamic_id)])
    client = TestClient(app)

    deleted_response = client.delete(f"/api/activities/{dynamic_id}")
    assert deleted_response.status_code == 200
    assert deleted_response.json()["deleted"]["dynamic_id"] == dynamic_id

    listed = client.get("/api/activities/deleted")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["dynamic_id"] == dynamic_id

    restored_response = client.post(f"/api/activities/{dynamic_id}/restore")
    assert restored_response.status_code == 200
    assert restored_response.json()["restored"]["dynamic_id"] == dynamic_id
    assert [item["dynamic_id"] for item in load_activities()] == [dynamic_id]
