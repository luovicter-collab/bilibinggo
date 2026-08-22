from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Literal

from src.bilibili_auth import require_login
from src.bilibili_client import BilibiliClient
from src.lottery_actions import (
    ACTION_INTERVAL_SEC,
    DEFAULT_PARTICIPATE_TEXT,
    ActionResult,
    execute_full_participation,
    follow_user,
    is_following,
    resolve_sender_uid,
    _api_code,
)
from src.lottery_api import (
    fetch_dynamic_detail,
    fetch_notice_for_interact,
    fetch_notice_for_reserve,
    is_upower_dynamic,
)
from src.participation_log import (
    ParticipationActionRecord,
    ParticipationOutcome,
    participation_succeeded,
    append_action_record_unlocked,
    serialize_actions,
)
from src.participation_store import set_participation_unlocked
from src.user_data_lock import user_data_lock
from src.participate_text import resolve_participate_text_for_activity
from src.fetch_activity_info import mark_enriched_joined
from src.lottery_classifier import PARTICIPATABLE_TYPES
from src.sources.common import is_valid_dynamic_id, opus_link

RESERVE_CLICK_URL = "https://api.bilibili.com/x/dynamic/feed/reserve/click"
RESERVE_RESERVED_STATUS = 2
RESERVE_PARTICIPATE_STEPS = 2

@dataclass
class ParticipateResult:
    dynamic_id: str
    lottery_type: str
    status: ParticipationOutcome
    message: str
    action_text: str
    actions: list[ActionResult]
    context_snapshot: dict[str, Any]

    def to_dict(self) -> dict:
        return {
            "dynamic_id": self.dynamic_id,
            "lottery_type": self.lottery_type,
            "status": self.status,
            "message": self.message,
            "action_text": self.action_text,
            "actions": serialize_actions(self.actions),
            "context_snapshot": self.context_snapshot,
        }


def _notice_snapshot(notice: dict | None) -> dict[str, Any]:
    if not notice:
        return {}
    return {
        "lottery_id": notice.get("lottery_id"),
        "sender_uid": notice.get("sender_uid"),
        "need_post": notice.get("need_post"),
        "followed": notice.get("followed"),
        "reposted": notice.get("reposted"),
        "participated": notice.get("participated"),
        "status": notice.get("status"),
        "lottery_time": notice.get("lottery_time"),
    }


def _context_snapshot(context: Any | None, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if context is not None:
        payload = {
            "sender_uid": getattr(context, "sender_uid", None),
            "liked": getattr(context, "liked", None),
            "followed": getattr(context, "followed", None),
            "favorited": getattr(context, "favorited", None),
            "favorite_available": getattr(context, "favorite_available", None),
            "reposted": getattr(context, "reposted", None),
            "commented": getattr(context, "commented", None),
            "comment_rid": getattr(context, "comment_rid", None),
        }
    if extra:
        payload.update(extra)
    return payload


def _persist_result(
    *,
    result: ParticipateResult,
    persist: bool,
    dry_run: bool,
) -> None:
    if not persist or dry_run:
        return
    joined = result.status == "joined" and participation_succeeded(
        result.actions,
        lottery_type=result.lottery_type,
    )
    record = ParticipationActionRecord(
        recorded_at=int(time.time()),
        dynamic_id=result.dynamic_id,
        lottery_type=result.lottery_type,
        status=result.status,
        message=result.message,
        action_text=result.action_text,
        actions=serialize_actions(result.actions),
        context_snapshot=result.context_snapshot,
    )
    with user_data_lock():
        append_action_record_unlocked(record)
        if joined:
            set_participation_unlocked(result.dynamic_id, "已参加")
    if joined:
        mark_enriched_joined(result.dynamic_id)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_notice_active(notice: dict | None) -> tuple[bool, str]:
    if not notice:
        return False, "未找到抽奖信息"
    if _safe_int(notice.get("status")) != 0:
        return False, "抽奖已结束或不可参与"
    lottery_time = _safe_int(notice.get("lottery_time"))
    if lottery_time and lottery_time <= int(time.time()):
        return False, "已过开奖时间"
    return True, ""


def _resolve_action_text(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    action_text: str | None,
) -> tuple[str, dict[str, Any]]:
    if action_text is None:
        resolved = resolve_participate_text_for_activity(client, dynamic_id=dynamic_id)
        return resolved.text, {
            "participate_text_source": resolved.source,
            "participate_text_pool_size": resolved.pool_size,
        }
    text = (action_text or DEFAULT_PARTICIPATE_TEXT).strip() or DEFAULT_PARTICIPATE_TEXT
    return text, {
        "participate_text_source": "custom",
        "participate_text_pool_size": 0,
    }


def participate_five_action_lottery(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    lottery_type: Literal["互动抽奖", "转发抽奖"],
    action_text: str | None = None,
    dry_run: bool = False,
    persist: bool = True,
    on_step: Callable[[int, int, str, str], None] | None = None,
) -> ParticipateResult:
    text, text_meta = _resolve_action_text(client, dynamic_id=dynamic_id, action_text=action_text)
    notice: dict | None = None
    sender_uid: int | None = None

    try:
        detail_item = fetch_dynamic_detail(client, dynamic_id)
        if is_upower_dynamic(detail_item):
            result = ParticipateResult(
                dynamic_id=dynamic_id,
                lottery_type=lottery_type,
                status="skipped",
                message="充电专属抽奖，不参与",
                action_text=text,
                actions=[],
                context_snapshot={},
            )
            _persist_result(result=result, persist=persist, dry_run=dry_run)
            return result
    except RuntimeError:
        pass

    if lottery_type == "互动抽奖":
        resolved = fetch_notice_for_interact(client, dynamic_id)
        if not resolved:
            result = ParticipateResult(
                dynamic_id=dynamic_id,
                lottery_type=lottery_type,
                status="failed",
                message="未找到互动抽奖信息",
                action_text=text,
                actions=[],
                context_snapshot={},
            )
            _persist_result(result=result, persist=persist, dry_run=dry_run)
            return result
        notice, _, _ = resolved
        active, reason = _is_notice_active(notice)
        if not active:
            result = ParticipateResult(
                dynamic_id=dynamic_id,
                lottery_type=lottery_type,
                status="skipped",
                message=reason,
                action_text=text,
                actions=[],
                context_snapshot=_notice_snapshot(notice),
            )
            _persist_result(result=result, persist=persist, dry_run=dry_run)
            return result
        # notice.sender_uid 理论上是 int，但接口偶发返回字符串/异常值；
        # 裸 int() 会让整个参与流程以未处理异常崩溃，走 _safe_int 兜底。
        sender_uid = _safe_int(notice.get("sender_uid") or 0) or None

    try:
        actions, context = execute_full_participation(
            client,
            dynamic_id=dynamic_id,
            sender_uid=sender_uid,
            action_text=text,
            dry_run=dry_run,
            on_step=on_step,
        )
    except RuntimeError as exc:
        message = str(exc).strip() or "参与失败"
        if "无法获取动态详情" in message:
            message = "无法获取动态详情，请稍后重试"
        result = ParticipateResult(
            dynamic_id=dynamic_id,
            lottery_type=lottery_type,
            status="failed",
            message=message,
            action_text=text,
            actions=[],
            context_snapshot=_notice_snapshot(notice),
        )
        _persist_result(result=result, persist=persist, dry_run=dry_run)
        return result

    if dry_run:
        status: ParticipationOutcome = "dry_run"
        message = "预演完成，未实际请求 B 站"
    elif participation_succeeded(actions, lottery_type=lottery_type):
        status = "joined"
        comment = next((item for item in actions if item.action == "comment"), None)
        if lottery_type == "互动抽奖" and comment and not comment.ok:
            message = "核心操作已完成（评论受限，已视为参与成功）"
        else:
            message = "五项操作均已完成" if lottery_type == "转发抽奖" else "核心操作均已完成"
    else:
        status = "failed"
        failed = [item for item in actions if not item.ok]
        message = failed[-1].detail if failed else "部分操作失败"

    snapshot = _context_snapshot(
        context,
        extra={**_notice_snapshot(notice), **text_meta},
    )
    result = ParticipateResult(
        dynamic_id=dynamic_id,
        lottery_type=lottery_type,
        status=status,
        message=message,
        action_text=text,
        actions=actions,
        context_snapshot=snapshot,
    )
    _persist_result(result=result, persist=persist, dry_run=dry_run)
    return result


def _resolve_reserve_info(client: BilibiliClient, dynamic_id: str) -> dict[str, Any]:
    item = fetch_dynamic_detail(client, dynamic_id)
    if not item:
        raise RuntimeError("无法获取动态详情，预约信息解析失败")
    additional = ((item.get("modules") or {}).get("module_dynamic") or {}).get("additional") or {}
    reserve = additional.get("reserve") or {}
    button = reserve.get("button") or {}
    reserve_id = reserve.get("rid")
    if not reserve_id:
        raise RuntimeError("动态中未找到预约组件 rid")
    sender_uid: int | None
    try:
        sender_uid = resolve_sender_uid(item)
    except RuntimeError:
        sender_uid = None
    return {
        "reserve_id": int(reserve_id),
        "reserve_total": int(reserve.get("reserve_total") or 0),
        "button_status": int(button.get("status") or 0),
        "title": str(reserve.get("title") or ""),
        "sender_uid": sender_uid,
        "referer": opus_link(dynamic_id),
    }


def _reserve_click(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    reserve_id: int,
    reserve_total: int,
    button_status: int,
    dry_run: bool,
) -> ActionResult:
    if button_status == RESERVE_RESERVED_STATUS:
        return ActionResult("reserve", True, "已预约，跳过")

    if dry_run:
        return ActionResult("reserve", True, f"将预约 reserve_id={reserve_id}")

    csrf, _ = require_login()
    referer = opus_link(dynamic_id)
    payload = client.post_json(
        RESERVE_CLICK_URL,
        {
            "reserve_id": reserve_id,
            "cur_btn_status": button_status,
            "dynamic_id_str": dynamic_id,
            "reserve_total": reserve_total,
            "spmid": "333.1369.0.0",
        },
        params={"csrf": csrf},
        referer=referer,
        raise_on_code=False,
    )
    code = _api_code(payload)
    if code == 0:
        data = payload.get("data") or {}
        final_status = int(data.get("final_btn_status") or 0)
        toast = str(data.get("toast") or "")
        if final_status == RESERVE_RESERVED_STATUS:
            return ActionResult("reserve", True, toast or "预约成功")
        if "预约成功" in toast or "已参与" in toast:
            return ActionResult("reserve", True, toast)
        if "取消" in toast:
            return ActionResult("reserve", False, toast or "预约操作被取消")
        return ActionResult(
            "reserve",
            False,
            toast or f"预约结果未确认（status={final_status}）",
        )
    message = str(payload.get("message") or payload.get("msg") or "")
    if "已预约" in message:
        return ActionResult("reserve", True, "已预约")
    return ActionResult("reserve", False, f"code={code} {message}".strip())


def participate_reserve_lottery(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    dry_run: bool = False,
    persist: bool = True,
    on_step: Callable[[int, int, str, str], None] | None = None,
) -> ParticipateResult:
    notice: dict | None = None
    try:
        resolved = fetch_notice_for_reserve(client, dynamic_id)
        if resolved:
            notice, _, _ = resolved
            active, reason = _is_notice_active(notice)
            if not active:
                result = ParticipateResult(
                    dynamic_id=dynamic_id,
                    lottery_type="预约抽奖",
                    status="skipped",
                    message=reason,
                    action_text="",
                    actions=[],
                    context_snapshot=_notice_snapshot(notice),
                )
                _persist_result(result=result, persist=persist, dry_run=dry_run)
                return result
    except RuntimeError:
        notice = None

    try:
        reserve_info = _resolve_reserve_info(client, dynamic_id)
    except (RuntimeError, ValueError) as exc:
        result = ParticipateResult(
            dynamic_id=dynamic_id,
            lottery_type="预约抽奖",
            status="failed",
            message=str(exc),
            action_text="",
            actions=[],
            context_snapshot=_notice_snapshot(notice),
        )
        _persist_result(result=result, persist=persist, dry_run=dry_run)
        return result

    total_steps = RESERVE_PARTICIPATE_STEPS
    sender_uid = _safe_int(reserve_info.get("sender_uid"))
    if not sender_uid:
        sender_uid = _safe_int((notice or {}).get("sender_uid"))
    if not sender_uid:
        result = ParticipateResult(
            dynamic_id=dynamic_id,
            lottery_type="预约抽奖",
            status="failed",
            message="无法解析 UP 主 UID，无法完成关注",
            action_text="",
            actions=[],
            context_snapshot={
                **_notice_snapshot(notice),
                "reserve_id": reserve_info["reserve_id"],
                "reserve_total": reserve_info["reserve_total"],
                "button_status": reserve_info["button_status"],
                "title": reserve_info["title"],
            },
        )
        _persist_result(result=result, persist=persist, dry_run=dry_run)
        return result

    referer = str(reserve_info["referer"])

    if on_step:
        on_step(1, total_steps, f"正在关注（1/{total_steps}）", "follow")
    try:
        if dry_run:
            followed = is_following(client, uid=sender_uid, referer=referer)
            follow_action = ActionResult(
                "follow",
                True,
                f"uid={sender_uid} 已关注，跳过" if followed else f"将关注 uid={sender_uid}",
            )
        else:
            csrf, _ = require_login()
            if is_following(client, uid=sender_uid, referer=referer):
                follow_action = ActionResult("follow", True, f"uid={sender_uid} 已关注，跳过")
            else:
                follow_action = follow_user(client, uid=sender_uid, csrf=csrf, referer=referer)
    except RuntimeError as exc:
        follow_action = ActionResult("follow", False, str(exc).strip() or "关注失败")

    actions: list[ActionResult] = [follow_action]
    snapshot = _context_snapshot(
        None,
        extra={
            **_notice_snapshot(notice),
            "sender_uid": sender_uid,
            "reserve_id": reserve_info["reserve_id"],
            "reserve_total": reserve_info["reserve_total"],
            "button_status": reserve_info["button_status"],
            "title": reserve_info["title"],
        },
    )

    if not follow_action.ok:
        result = ParticipateResult(
            dynamic_id=dynamic_id,
            lottery_type="预约抽奖",
            status="failed",
            message=follow_action.detail,
            action_text="",
            actions=actions,
            context_snapshot=snapshot,
        )
        _persist_result(result=result, persist=persist, dry_run=dry_run)
        return result

    if not dry_run:
        time.sleep(ACTION_INTERVAL_SEC)

    if on_step:
        on_step(2, total_steps, f"正在预约（2/{total_steps}）", "reserve")
    reserve_action = _reserve_click(
        client,
        dynamic_id=dynamic_id,
        reserve_id=reserve_info["reserve_id"],
        reserve_total=reserve_info["reserve_total"],
        button_status=reserve_info["button_status"],
        dry_run=dry_run,
    )
    actions.append(reserve_action)

    if dry_run:
        status: ParticipationOutcome = "dry_run"
        message = "预演完成，未实际请求 B 站"
    elif participation_succeeded(actions, lottery_type="预约抽奖"):
        status = "joined"
        message = "关注与预约均已完成"
    else:
        status = "failed"
        message = reserve_action.detail if not reserve_action.ok else "部分操作失败"

    result = ParticipateResult(
        dynamic_id=dynamic_id,
        lottery_type="预约抽奖",
        status=status,
        message=message,
        action_text="",
        actions=actions,
        context_snapshot=snapshot,
    )
    _persist_result(result=result, persist=persist, dry_run=dry_run)
    return result


def participate_activity(
    client: BilibiliClient,
    *,
    dynamic_id: str,
    lottery_type: str,
    action_text: str | None = None,
    dry_run: bool = False,
    persist: bool = True,
    on_step: Callable[[int, int, str, str], None] | None = None,
) -> ParticipateResult:
    if not is_valid_dynamic_id(dynamic_id):
        raise ValueError("dynamic_id 无效")
    if lottery_type == "充电抽奖":
        result = ParticipateResult(
            dynamic_id=dynamic_id,
            lottery_type=lottery_type,
            status="skipped",
            message="充电专属抽奖，不参与",
            action_text=action_text,
            actions=[],
            context_snapshot={},
        )
        _persist_result(result=result, persist=persist, dry_run=dry_run)
        return result
    if lottery_type not in PARTICIPATABLE_TYPES:
        raise RuntimeError(f"不支持的抽奖类型: {lottery_type}")
    if lottery_type == "互动抽奖":
        return participate_five_action_lottery(
            client,
            dynamic_id=dynamic_id,
            lottery_type="互动抽奖",
            action_text=action_text,
            dry_run=dry_run,
            persist=persist,
            on_step=on_step,
        )
    if lottery_type == "转发抽奖":
        return participate_five_action_lottery(
            client,
            dynamic_id=dynamic_id,
            lottery_type="转发抽奖",
            action_text=action_text,
            dry_run=dry_run,
            persist=persist,
            on_step=on_step,
        )
    if lottery_type == "预约抽奖":
        return participate_reserve_lottery(
            client,
            dynamic_id=dynamic_id,
            dry_run=dry_run,
            persist=persist,
            on_step=on_step,
        )
    raise RuntimeError(f"不支持的抽奖类型: {lottery_type}")
