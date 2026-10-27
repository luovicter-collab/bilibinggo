from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from src.bilibili_client import BilibiliClient
from src.fetch_activity_info import ENRICHED_OUTPUT_PATH
from src.lottery_api import (
    fetch_dynamic_detail,
    fetch_notice_for_interact,
    fetch_notice_for_reserve,
    fetch_reserve_button_status,
    is_upower_dynamic,
)
from src.lottery_classifier import PARTICIPATABLE_TYPES, is_charging_lottery_activity
from src.lottery_time import lottery_time_unix
from src.participation_store import ParticipationRecord, load_participations
from src.sources.common import is_valid_dynamic_id, load_previous_output
from src.status_refresh import persist_activity_record


def _load_activity_item(dynamic_id: str) -> dict | None:
    payload = load_previous_output(ENRICHED_OUTPUT_PATH) or {}
    for item in payload.get("activities") or []:
        if isinstance(item, dict) and str(item.get("dynamic_id") or "") == dynamic_id:
            return dict(item)
    return None


def _apply_notice_fields(item: dict, notice: dict) -> None:
    if "participated" in notice:
        item["platform_participated"] = bool(notice.get("participated"))
    lottery_time = int(notice.get("lottery_time") or 0)
    if lottery_time:
        item["lottery_time"] = lottery_time
    status = int(notice.get("status") or 0)
    if status != 0 or notice.get("lottery_result"):
        item["draw_status"] = "ended"
    elif lottery_time and lottery_time <= int(time.time()):
        item["draw_status"] = "ended"
    else:
        item["draw_status"] = "active"


def _sync_live_fields(
    client: BilibiliClient,
    item: dict,
    *,
    lottery_type: str,
) -> None:
    dynamic_id = str(item.get("dynamic_id") or "")
    detail = fetch_dynamic_detail(client, dynamic_id)
    if not detail:
        raise RuntimeError("无法打开活动链接，请稍后重试")
    if is_upower_dynamic(detail):
        raise RuntimeError("充电专属抽奖，不参与")

    if lottery_type == "互动抽奖":
        resolved = fetch_notice_for_interact(client, dynamic_id)
        if not resolved:
            raise RuntimeError("无法获取抽奖信息，活动可能已结束或不可参与")
        notice, _, _ = resolved
        _apply_notice_fields(item, notice)
        return

    if lottery_type == "预约抽奖":
        item["reserve_reserved"] = fetch_reserve_button_status(client, dynamic_id)
        try:
            resolved = fetch_notice_for_reserve(client, dynamic_id)
        except RuntimeError:
            resolved = None
        if resolved:
            notice, _, _ = resolved
            _apply_notice_fields(item, notice)
        else:
            lottery_ts = lottery_time_unix(item)
            item["draw_status"] = "ended" if lottery_ts and lottery_ts <= int(time.time()) else "active"
        return

    if lottery_type == "转发抽奖":
        lottery_ts = lottery_time_unix(item)
        item["draw_status"] = "ended" if lottery_ts and lottery_ts <= int(time.time()) else "active"
        return

    raise RuntimeError(f"不支持的抽奖类型: {lottery_type}")


def refresh_activity_status_from_live(
    client: BilibiliClient,
    dynamic_id: str,
    *,
    lottery_type_hint: str | None = None,
) -> dict[str, Any]:
    """打开活动链接同步最新状态，写回本地并返回更新后的记录。"""
    dynamic_id = str(dynamic_id or "").strip()
    if not is_valid_dynamic_id(dynamic_id):
        raise ValueError("活动 ID 无效")

    item = _load_activity_item(dynamic_id)
    if not item:
        raise RuntimeError("未找到活动信息，请先执行一键更新")

    if is_charging_lottery_activity(item):
        raise RuntimeError("充电专属抽奖，不参与")

    lottery_type = str(lottery_type_hint or item.get("lottery_type") or "").strip()
    if lottery_type not in PARTICIPATABLE_TYPES:
        raise RuntimeError("未找到可参与的活动类型，请先执行一键更新")

    item["lottery_type"] = lottery_type
    _sync_live_fields(client, item, lottery_type=lottery_type)
    participation = load_participations().get(dynamic_id)
    return persist_activity_record(item, participation=participation)


def ensure_activity_participatable(
    client: BilibiliClient,
    dynamic_id: str,
    *,
    lottery_type_hint: str | None = None,
) -> dict[str, Any]:
    """参与前检查：同步状态后必须为未参加且未结束。"""
    from src.activity_exclusions import is_activity_deleted

    if is_activity_deleted(dynamic_id):
        raise RuntimeError("该活动已在已删除列表中，不会参与")
    item = refresh_activity_status_from_live(
        client,
        dynamic_id,
        lottery_type_hint=lottery_type_hint,
    )
    status = str(item.get("activity_status") or "")
    if status != "未参加":
        raise RuntimeError(f"活动当前为「{status}」，无法参与")
    if str(item.get("draw_status") or "") == "ended":
        raise RuntimeError("活动已结束，无法参与")
    return item
