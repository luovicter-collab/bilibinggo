from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from src.activity_store import replace_all_activities
from web.app import app

client = TestClient(app)


def test_reject_unknown_job_action() -> None:
    resp = client.post("/api/jobs", json={"action": "delete_all", "params": {}})
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "UNSUPPORTED_ACTION"
    assert data["detail"] == data["error"]["message"]


def test_watch_users_api_seeds_and_lists() -> None:
    with patch("web.app.seed_from_candidates_if_empty", return_value=True):
        with patch(
            "web.app.get_watch_users_payload",
            return_value={"count": 1, "users": [{"mid": 1, "name": "u"}], "updated_at": 0},
        ):
            with patch("web.app.get_watch_last_synced_at", return_value=None):
                resp = client.get("/api/watch-users")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert "next_window" in data


def test_participate_triple_job_accepts_filter_params() -> None:
    with patch("web.app.runner.try_start", return_value=1) as start_mock:
        resp = client.post(
            "/api/jobs",
            json={
                "action": "participate_triple",
                "params": {"status": "未参加", "sort": "heat", "order": "desc"},
            },
        )
    assert resp.status_code in (200, 401)
    if resp.status_code == 200:
        start_mock.assert_called_once()
        assert start_mock.call_args.args[0] == "participate_triple"


def test_reject_invalid_dynamic_id() -> None:
    resp = client.post(
        "/api/jobs",
        json={"action": "participate", "params": {"dynamic_id": "not-valid"}},
    )
    assert resp.status_code in (400, 401)


def test_activities_pagination_bounds() -> None:
    resp = client.get("/api/activities", params={"page": 1, "page_size": 20})
    assert resp.status_code == 200
    data = resp.json()
    assert data["page_size"] == 20
    assert "triple_targets" in data
    assert "count" in data["triple_targets"]
    assert "items" in data["triple_targets"]


def test_activities_triple_targets_empty_for_joined_filter() -> None:
    rows = [
        {
            "dynamic_id": "100000000000000001",
            "activity_title": "已参加活动",
            "lottery_type": "转发抽奖",
            "activity_status": "已参加",
            "draw_status": "active",
            "can_participate": False,
            "prize": "奖品",
            "repost_count": 0,
        }
    ]
    with patch("web.activity_service._filtered_activity_rows", return_value=rows):
        resp = client.get("/api/activities", params={"status": "已参加"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["triple_targets"]["count"] == 0
    assert data["triple_targets"]["items"] == []


def test_delete_activity_removes_it_from_list_and_triple_targets(isolated_home) -> None:
    dynamic_id = "100000000000000001"
    replace_all_activities(
        [
            {
                "dynamic_id": dynamic_id,
                "source_url": f"https://www.bilibili.com/opus/{dynamic_id}",
                "lottery_type": "转发抽奖",
                "draw_status": "active",
                "activity_status": "未参加",
                "lottery_time": 9_999_999_999,
                "prizes": [{"description": "测试奖品", "winner_count": 1}],
            }
        ]
    )

    before = client.get("/api/activities", params={"status": "未参加"}).json()
    assert before["total"] == 1
    assert before["triple_targets"]["items"][0]["dynamic_id"] == dynamic_id

    resp = client.delete(f"/api/activities/{dynamic_id}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    after = client.get("/api/activities", params={"status": "未参加"}).json()
    assert after["total"] == 0
    assert after["triple_targets"]["items"] == []
    assert client.get("/api/summary").json()["total_count"] == 0

    repeated = client.delete(f"/api/activities/{dynamic_id}")
    assert repeated.status_code == 404
    assert repeated.json()["error"]["code"] == "NOT_FOUND"


def test_delete_activity_rejects_invalid_dynamic_id() -> None:
    resp = client.delete("/api/activities/not-valid")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_delete_activity_rejects_while_job_is_running() -> None:
    dynamic_id = "100000000000000001"
    with patch("web.app.runner.is_running", return_value=True):
        resp = client.delete(f"/api/activities/{dynamic_id}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "JOB_BUSY"


def test_settings_includes_participate_text_mode() -> None:
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("participate_text_mode") in {"custom", "random_comment"}
    assert data.get("default_participate_fallback_text") == "好运连连！"


def test_save_participate_fallback_text_when_logged_in() -> None:
    with patch("web.app.get_account_profile", return_value={"logged_in": True}):
        resp = client.put(
            "/api/settings/participate-text",
            json={"participate_fallback_text": "好运连连！"},
        )
    assert resp.status_code == 200
    assert resp.json().get("participate_fallback_text") == "好运连连！"


def test_login_qrcode_does_not_crash() -> None:
    resp = client.get("/api/login/qrcode")
    assert resp.status_code in (200, 404)


def test_api_account_does_not_crash() -> None:
    resp = client.get("/api/account")
    assert resp.status_code == 200
    assert "logged_in" in resp.json()


def test_api_account_extras_requires_login_or_returns() -> None:
    resp = client.get("/api/account/extras")
    assert resp.status_code in (200, 401)
