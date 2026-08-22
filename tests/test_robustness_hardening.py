from __future__ import annotations

import time

import pytest

from src.lottery_api import (
    fetch_reserve_button_status,
    is_upower_dynamic,
    resolve_reserve_business,
)
from src.retry_utils import retry_call


class _FakeClient:
    def get_text(self, *args, **kwargs):
        return "<html></html>"


def test_retry_call_reraises_keyboard_interrupt_immediately() -> None:
    calls: list[int] = []

    def boom() -> int:
        calls.append(1)
        raise KeyboardInterrupt()

    start = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        retry_call(boom, attempts=3, base_delay=5.0)
    assert time.monotonic() - start < 1.0
    assert len(calls) == 1


def test_retry_call_reraises_system_exit_immediately() -> None:
    calls: list[int] = []

    def boom() -> int:
        calls.append(1)
        raise SystemExit(2)

    with pytest.raises(SystemExit):
        retry_call(boom, attempts=3, base_delay=5.0)
    assert len(calls) == 1


def test_retry_call_still_retries_runtime_errors() -> None:
    calls: list[int] = []

    def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("transient")
        return "ok"

    assert retry_call(flaky, attempts=3, base_delay=0.0) == "ok"
    assert len(calls) == 3


def _opus_shape_item(additional: dict) -> dict:
    return {"modules": [{"module_dynamic": {"additional": additional}}]}


def test_is_upower_dynamic_handles_opus_list_modules() -> None:
    # opus/detail 的 modules 是列表结构，旧实现会 AttributeError。
    assert is_upower_dynamic(_opus_shape_item({})) is False
    item = _opus_shape_item({"type": "ADDITIONAL_TYPE_UPOWER_LOTTERY"})
    assert is_upower_dynamic(item) is True


def test_is_upower_dynamic_handles_dict_modules() -> None:
    item = {"modules": {"module_dynamic": {"additional": {"upower_lottery": {"lottery_id": 1}}}}}
    assert is_upower_dynamic(item) is True


def test_resolve_reserve_business_with_opus_list_modules_does_not_crash() -> None:
    item = _opus_shape_item({"reserve": {}})
    resolved = resolve_reserve_business(_FakeClient(), "123", detail_item=item)
    assert resolved is None


def test_fetch_reserve_button_status_bad_status_returns_none() -> None:
    item = {"modules": {"module_dynamic": {"additional": {"reserve": {"button": {"status": "二"}}}}}}
    assert fetch_reserve_button_status(None, "123", detail_item=item) is None


def test_fetch_reserve_button_status_accepts_digit_strings() -> None:
    reserved = {"modules": {"module_dynamic": {"additional": {"reserve": {"button": {"status": "2"}}}}}}
    pending = {"modules": {"module_dynamic": {"additional": {"reserve": {"button": {"status": "1"}}}}}}
    assert fetch_reserve_button_status(None, "123", detail_item=reserved) is True
    assert fetch_reserve_button_status(None, "123", detail_item=pending) is False


def test_interact_notice_garbage_sender_uid_does_not_crash(monkeypatch) -> None:
    from src import participation as P

    monkeypatch.setattr(P, "fetch_dynamic_detail", lambda *a, **k: None)
    monkeypatch.setattr(P, "is_upower_dynamic", lambda *a, **k: False)
    notice = {"status": 0, "lottery_time": 0, "sender_uid": "not-a-number"}
    monkeypatch.setattr(P, "fetch_notice_for_interact", lambda *a, **k: (notice, 1, "d"))
    monkeypatch.setattr(P, "execute_full_participation", lambda *a, **k: ([], None))

    result = P.participate_five_action_lottery(
        client=None,
        dynamic_id="123",
        lottery_type="互动抽奖",
        dry_run=True,
        persist=False,
    )
    assert result.status in {"dry_run", "failed"}
