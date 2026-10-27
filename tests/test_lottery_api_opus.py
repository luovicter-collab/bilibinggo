from __future__ import annotations

from src.lottery_api import (
    _normalize_dynamic_item,
    extract_activity_heat,
    extract_repost_count_from_detail,
    fetch_dynamic_detail,
)


def test_normalize_opus_modules_list() -> None:
    item = {
        "basic": {"comment_id_str": "1"},
        "modules": [
            {
                "module_type": "MODULE_TYPE_STAT",
                "module_stat": {"forward": {"count": 123}},
            },
            {
                "module_type": "MODULE_TYPE_AUTHOR",
                "module_author": {"mid": 42},
            },
        ],
    }
    normalized = _normalize_dynamic_item(item)
    assert isinstance(normalized["modules"], dict)
    assert normalized["modules"]["module_stat"]["forward"]["count"] == 123
    assert normalized["modules"]["module_author"]["mid"] == 42
    assert extract_repost_count_from_detail(normalized) == 123


def test_extract_repost_from_opus_list_without_normalize() -> None:
    item = {
        "modules": [
            {"module_stat": {"forward": {"count": 456}}},
        ]
    }
    assert extract_repost_count_from_detail(item) == 456


def test_extract_activity_heat_uses_reserve_for_reserve_lottery() -> None:
    item = {
        "modules": {
            "module_dynamic": {
                "additional": {
                    "reserve": {"reserve_total": 43},
                }
            },
            "module_stat": {"forward": {"count": 5}},
        }
    }
    heat, from_reserve = extract_activity_heat(item, lottery_type="预约抽奖")
    assert heat == 43
    assert from_reserve is True


def test_extract_activity_heat_uses_forward_for_interact() -> None:
    item = {
        "modules": {
            "module_dynamic": {
                "additional": {
                    "reserve": {"reserve_total": 43},
                }
            },
            "module_stat": {"forward": {"count": 5}},
        }
    }
    heat, from_reserve = extract_activity_heat(item, lottery_type="互动抽奖")
    assert heat == 5
    assert from_reserve is False


def test_fetch_dynamic_detail_opus_fallback(monkeypatch) -> None:
    class FakeClient:
        def get_json(self, url, params=None, referer=None, retries=1):
            if "opus/detail" in url:
                return {
                    "code": 0,
                    "data": {
                        "item": {
                            "basic": {"uid": "1"},
                            "modules": [
                                {
                                    "module_stat": {"forward": {"count": 99}},
                                },
                                {"module_author": {"mid": 1}},
                            ],
                        }
                    },
                }
            return {"code": -1, "message": "fail"}

    item = fetch_dynamic_detail(FakeClient(), "1212858623676383239")
    assert item is not None
    assert extract_repost_count_from_detail(item) == 99


def test_opus_detail_retries_with_legacy_dynamic_referer() -> None:
    from src.lottery_api import _fetch_opus_detail_item

    class FakeClient:
        def __init__(self) -> None:
            self.referers: list[str | None] = []

        def get_json(self, url, params=None, referer=None, retries=1):
            self.referers.append(referer)
            if referer and referer.startswith("https://t.bilibili.com/"):
                return {"code": 0, "data": {"item": {"modules": []}}}
            return {"code": -352, "message": "-352"}

    client = FakeClient()
    assert _fetch_opus_detail_item(client, "1235221925682217012") is not None
    assert client.referers[:2] == [
        "https://www.bilibili.com/opus/1235221925682217012",
        "https://t.bilibili.com/1235221925682217012",
    ]


def test_probe_detail_retries_with_legacy_dynamic_referer() -> None:
    from src.lottery_api import probe_dynamic_detail_api

    class FakeClient:
        def __init__(self) -> None:
            self.referers: list[str | None] = []

        def get_json(self, url, params=None, referer=None, retries=1):
            self.referers.append(referer)
            if referer and referer.startswith("https://t.bilibili.com/"):
                return {"code": 0, "message": "0", "data": {"item": {"type": "DYNAMIC_TYPE_DRAW"}}}
            return {"code": -352, "message": "-352"}

    client = FakeClient()
    item, code, _ = probe_dynamic_detail_api(client, "1235221925682217012", retries=0)
    assert code == 0
    assert item and item["type"] == "DYNAMIC_TYPE_DRAW"
    assert client.referers[:2] == [
        "https://www.bilibili.com/opus/1235221925682217012",
        "https://t.bilibili.com/1235221925682217012",
    ]
