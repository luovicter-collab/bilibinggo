from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.activity_exclusions import delete_activity
from src.activity_store import replace_all_activities
from src.participate_preflight import ensure_activity_participatable


def test_ensure_activity_participatable_rejects_joined(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = isolated_home
    dynamic_id = "1000000000000000001"
    replace_all_activities(
        [
            {
                "dynamic_id": dynamic_id,
                "lottery_type": "互动抽奖",
                "activity_status": "未参加",
                "draw_status": "active",
                "lottery_time": 9_999_999_999,
                "conditions": {},
            }
        ]
    )

    notice = {
        "participated": True,
        "lottery_time": 9_999_999_999,
        "status": 0,
    }
    client = MagicMock()
    monkeypatch.setattr(
        "src.participate_preflight.fetch_dynamic_detail",
        lambda _client, _did: {"modules": {}},
    )
    monkeypatch.setattr("src.participate_preflight.is_upower_dynamic", lambda _item: False)
    monkeypatch.setattr(
        "src.participate_preflight.fetch_notice_for_interact",
        lambda _client, _did: (notice, 0, dynamic_id),
    )
    monkeypatch.setattr("src.participate_preflight.load_participations", lambda: {})

    with pytest.raises(RuntimeError, match="已参加"):
        ensure_activity_participatable(client, dynamic_id, lottery_type_hint="互动抽奖")


def test_ensure_activity_participatable_rejects_deleted_activity(isolated_home: Path) -> None:
    _ = isolated_home
    dynamic_id = "1000000000000000002"
    replace_all_activities(
        [
            {
                "dynamic_id": dynamic_id,
                "lottery_type": "互动抽奖",
                "activity_status": "未参加",
                "draw_status": "active",
            }
        ]
    )
    delete_activity(dynamic_id)
    client = MagicMock()

    with pytest.raises(RuntimeError, match="已删除列表"):
        ensure_activity_participatable(client, dynamic_id, lottery_type_hint="互动抽奖")
    assert client.method_calls == []
